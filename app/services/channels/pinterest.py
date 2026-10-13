"""Pinterest v5 transport, staged pending app approval and lifecycle integration.

No routes, scheduler hooks or default credentials. The caller must validate the
workspace, save a per-destination claim and retain uncertain outcomes before
using create_pin. Never retry a write just because its result was not received.
Contract: pinterest/api-description v5.28.0 (checked 2026-10-13).
"""
from dataclasses import dataclass, field
import re
from urllib.parse import urlencode, urlsplit
import httpx

from app.services.publish_media import is_durable_media_url

API = 'https://api.pinterest.com/v5'
SANDBOX = 'https://api-sandbox.pinterest.com/v5'
# Create Pin declares all four board/pin scopes; identity needs user_accounts:read.
SCOPES = ('boards:read', 'boards:write', 'pins:read', 'pins:write', 'user_accounts:read')


class PinterestError(ValueError):
    """Safe for user-facing errors: never include response bodies or credentials."""


class PinterestOutcomeUnknown(PinterestError):
    """A write may have succeeded. Persist this state; do not send it again."""


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,64}', value):
        raise PinterestError('Choose a valid Pinterest board or Pin.')
    return value


def _https(value):
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and bool(url.hostname) and not url.username
                and not url.password and url.port in (None, 443) and not url.fragment)
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class PinDraft:
    """Separately reviewed social copy; never mutate the canonical post or source."""
    board_id: str
    image_url: str
    title: str
    description: str
    alt_text: str
    ai_modified: bool
    link: str | None = None

    def payload(self):
        _identifier(self.board_id)
        if not is_durable_media_url(self.image_url):
            raise PinterestError('Save the final image to Cloudinary before publishing.')
        for label, value, maximum in (('title', self.title, 100), ('description', self.description, 800), ('image description', self.alt_text, 500)):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise PinterestError(f'Pinterest {label} must contain 1–{maximum} characters. Edit the social copy without rewriting the source.')
        if not isinstance(self.ai_modified, bool):
            raise PinterestError('Review the AI disclosure before publishing.')
        if self.link is not None and (not isinstance(self.link, str) or len(self.link) > 2048 or not _https(self.link)):
            raise PinterestError('Use an HTTPS destination link without credentials or a fragment.')
        result = {'board_id': self.board_id, 'title': self.title, 'description': self.description,
                  'alt_text': self.alt_text, 'media_source': {'source_type': 'image_url', 'url': self.image_url}}
        if self.ai_modified:
            result['ai_disclosures'] = {'values': ['AI_MODIFIED']}
        if self.link:
            result['link'] = self.link
        return result


@dataclass(frozen=True)
class PinterestCredentials:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str

    def validate(self):
        if not self.client_id or not self.client_secret or not _https(self.redirect_uri):
            raise PinterestError('Pinterest connection setup is incomplete.')
        parts = urlsplit(self.redirect_uri)
        if parts.query:
            raise PinterestError('Pinterest needs an exact registered callback URL.')


class PinterestClient:
    def __init__(self, credentials: PinterestCredentials, *, sandbox=True, transport=None):
        credentials.validate()
        if type(sandbox) is not bool:
            raise PinterestError('Choose an explicit Pinterest test or live environment.')
        self.credentials = credentials
        self.sandbox = sandbox
        self.base_url = SANDBOX if self.sandbox else API
        # No automatic transport retries, redirects or environment proxy.
        self.http = httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                                 trust_env=False, transport=transport)

    def close(self):
        self.http.close()

    def authorization_url(self, state):
        if not isinstance(state, str) or not 32 <= len(state) <= 128:
            raise PinterestError('Start a new verified connection attempt.')
        return 'https://www.pinterest.com/oauth/?' + urlencode({
            'client_id': self.credentials.client_id, 'redirect_uri': self.credentials.redirect_uri,
            'response_type': 'code', 'scope': ','.join(SCOPES), 'state': state})

    def _request(self, method, path, *, token=None, form=None, payload=None, uncertain=False):
        if form is None and (not isinstance(token, str) or not token.strip() or '\r' in token or '\n' in token):
            raise PinterestError('Reconnect Pinterest before continuing.')
        try:
            response = self.http.request(method, (API if form is not None else self.base_url) + path,
                headers={'Authorization': 'Bearer ' + token} if token else {},
                auth=httpx.BasicAuth(self.credentials.client_id, self.credentials.client_secret) if form is not None else None,
                data=form, json=payload)
        except httpx.RequestError:
            if uncertain:
                raise PinterestOutcomeUnknown('Pinterest has not confirmed the result. Check the account before retrying.') from None
            raise PinterestError('Pinterest could not be reached. Try again shortly.') from None
        if response.status_code >= 500 or response.status_code == 408:
            if uncertain:
                raise PinterestOutcomeUnknown('Pinterest has not confirmed the result. Check the account before retrying.')
            raise PinterestError('Pinterest is temporarily unavailable.')
        if response.status_code in (401, 403):
            raise PinterestError('Pinterest access is unavailable. Check app approval and reconnect the account.')
        if response.status_code == 429:
            raise PinterestError('Pinterest is limiting requests. Try again later; nothing was retried automatically.')
        if not 200 <= response.status_code < 300:
            if uncertain and 300 <= response.status_code < 400:
                raise PinterestOutcomeUnknown('Pinterest returned an unexpected result. Check the account before retrying.')
            raise PinterestError('Pinterest rejected this request. Check the selected board and Pin details.')
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except ValueError:
            if uncertain:
                raise PinterestOutcomeUnknown('Pinterest returned an unreadable result. Check the account before retrying.') from None
            raise PinterestError('Pinterest returned an unreadable response.') from None

    def exchange_code(self, code):
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise PinterestError('The connection code is missing. Connect Pinterest again.')
        return self._token({'grant_type': 'authorization_code', 'code': code,
                            'redirect_uri': self.credentials.redirect_uri})

    def refresh(self, refresh_token):
        if not isinstance(refresh_token, str) or not refresh_token:
            raise PinterestError('Reconnect Pinterest to renew access.')
        return self._token({'grant_type': 'refresh_token', 'refresh_token': refresh_token})

    def _token(self, form):
        data = self._request('POST', '/oauth/token', form=form)
        scopes = set(str(data.get('scope') or '').replace(',', ' ').split())
        if (not isinstance(data.get('access_token'), str) or not data['access_token']
                or not isinstance(data.get('refresh_token'), str) or not data['refresh_token']
                or str(data.get('token_type', '')).lower() != 'bearer'
                or type(data.get('expires_in')) is not int or not 0 < data['expires_in'] <= 366 * 86400
                or not set(SCOPES).issubset(scopes)):
            raise PinterestError('Pinterest did not return complete publishing access. Reconnect and approve the requested permissions.')
        # A caller must atomically persist the rotated refresh token encrypted.
        return {k: data[k] for k in ('access_token', 'refresh_token', 'expires_in', 'scope',
                                     'refresh_token_expires_in', 'refresh_token_expires_at') if k in data}

    def account(self, token):
        data = self._request('GET', '/user_account', token=token)
        if not isinstance(data.get('username'), str) or not data['username']:
            raise PinterestError('Pinterest account identity could not be verified.')
        return data

    def boards(self, token, bookmark=None):
        if bookmark is not None and (not isinstance(bookmark, str) or len(bookmark) > 4096):
            raise PinterestError('Reload the board list before continuing.')
        query = {'page_size': 100, 'privacy': 'PUBLIC'}
        if bookmark:
            query['bookmark'] = bookmark
        data = self._request('GET', '/boards?' + urlencode(query), token=token)
        if not isinstance(data.get('items'), list):
            raise PinterestError('Pinterest boards could not be read.')
        return data  # Preserve empty-page bookmarks, including in Sandbox.

    def board(self, token, board_id):
        return self._request('GET', '/boards/' + _identifier(board_id), token=token)

    def create_pin(self, token, draft: PinDraft):
        data = self._request('POST', '/pins', token=token, payload=draft.payload(), uncertain=True)
        try:
            _identifier(data.get('id'))
        except PinterestError:
            raise PinterestOutcomeUnknown('Pinterest did not return a Pin ID. Check the account before retrying.') from None
        return {'id': data['id'], 'sandbox': self.sandbox}

    def pin(self, token, pin_id):
        return self._request('GET', '/pins/' + _identifier(pin_id), token=token)
