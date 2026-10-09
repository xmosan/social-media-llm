"""Bounded Meta discovery with sanitized errors and no credential logging."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
import re
import httpx
from fastapi import HTTPException
from app.config import settings
from app.services.publisher import GRAPH_URL


class InstagramAuthError(RuntimeError):
    pass


class InstagramAuthService:
    def __init__(self):
        self.client_id = settings.fb_app_id
        self.client_secret = settings.fb_app_secret
        self.redirect_uri = settings.fb_redirect_uri or f"{settings.public_base_url.rstrip('/')}/auth/instagram/callback"

    def validate_configuration(self):
        uri, base = urlsplit(self.redirect_uri), urlsplit(settings.public_base_url)
        local = uri.hostname in {"localhost", "127.0.0.1"}
        if (not self.client_id or not self.client_secret or uri.username or uri.password
                or (uri.scheme, uri.netloc) != (base.scheme, base.netloc)
                or (uri.scheme != "https" and not (local and uri.scheme == "http"))
                or uri.path not in {"/auth/instagram/callback", "/auth/meta/callback"}
                or uri.query or uri.fragment):
            raise HTTPException(503, "Instagram connection is not configured. Please contact support.")

    def get_auth_url(self, state):
        self.validate_configuration()
        return f"https://www.facebook.com/{GRAPH_URL.rsplit('/', 1)[-1]}/dialog/oauth?" + urlencode({
            "client_id": self.client_id, "redirect_uri": self.redirect_uri, "state": state,
            "scope": "instagram_basic,instagram_content_publish,pages_show_list", "response_type": "code"})

    async def _get(self, client, path, *, params=None, token=None):
        try:
            response = await client.get(f"{GRAPH_URL}/{path}", params=params,
                headers={"Authorization": "Bearer " + token} if token else None)
            data = response.json()
            if response.status_code != 200 or not isinstance(data, dict) or data.get("error"):
                raise InstagramAuthError("Meta could not complete this connection")
            return data
        except (httpx.RequestError, ValueError):
            raise InstagramAuthError("Meta is temporarily unavailable") from None

    async def exchange_code_for_token(self, code):
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            data = await self._get(client, "oauth/access_token", params={
                "client_id": self.client_id, "redirect_uri": self.redirect_uri,
                "client_secret": self.client_secret, "code": code})
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise InstagramAuthError("Meta did not return an access token")
        return token

    async def get_long_lived_token(self, short_token):
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            data = await self._get(client, "oauth/access_token", params={
                "grant_type": "fb_exchange_token", "client_id": self.client_id,
                "client_secret": self.client_secret, "fb_exchange_token": short_token})
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise InstagramAuthError("Meta did not return an access token")
        expiry = data.get("expires_in")
        # Unknown expiration remains unknown; never invent a fresh 60-day lifetime.
        expires_at = None
        if expiry is not None:
            if isinstance(expiry, bool) or not isinstance(expiry, int) or not 0 < expiry <= 366 * 24 * 3600:
                raise InstagramAuthError("Meta returned an invalid token expiration")
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiry)
        return {"access_token": token, "expires_at": expires_at}

    async def discover_ig_business_account(self, user_token):
        accounts, seen_ids, cursors = [], set(), set()
        params = {"fields": "id,name,instagram_business_account{id,username,name,profile_picture_url}", "limit": 100}
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            for _ in range(10):
                data = await self._get(client, "me/accounts", params=params, token=user_token)
                pages = data.get("data")
                if not isinstance(pages, list):
                    raise InstagramAuthError("Meta returned invalid account discovery")
                for page in pages:
                    if not isinstance(page, dict) or not re.fullmatch(r"[0-9]{1,64}", str(page.get("id", ""))):
                        raise InstagramAuthError("Meta returned invalid page data")
                    page_id = str(page["id"])
                    ig = page.get("instagram_business_account")
                    if not ig:
                        deep = await self._get(client, page_id, params={"fields": "instagram_business_account{id,username,name,profile_picture_url}"}, token=user_token)
                        ig = deep.get("instagram_business_account")
                    if not ig:
                        continue
                    if not isinstance(ig, dict) or not re.fullmatch(r"[0-9]{1,64}", str(ig.get("id", ""))):
                        raise InstagramAuthError("Meta returned invalid Instagram data")
                    ig_id = str(ig["id"])
                    if ig_id in seen_ids:
                        continue
                    seen_ids.add(ig_id)
                    picture = ig.get("profile_picture_url")
                    if not isinstance(picture, str) or not picture.startswith("https://"):
                        picture = None
                    accounts.append({"ig_user_id": ig_id, "fb_page_id": page_id,
                        "username": str(ig.get("username") or "")[:150],
                        "name": str(ig.get("name") or ig.get("username") or "Instagram account")[:250],
                        "profile_picture_url": picture[:2000] if picture else None})
                paging = data.get("paging") or {}
                if not isinstance(paging, dict):
                    raise InstagramAuthError("Meta returned invalid pagination")
                if not paging.get("next"):
                    return accounts
                cursor = (paging.get("cursors") or {}).get("after")
                if not isinstance(cursor, str) or not cursor or len(cursor) > 4096 or cursor in cursors:
                    raise InstagramAuthError("Meta returned invalid pagination")
                cursors.add(cursor)
                # Never follow a provider-supplied next URL with credentials.
                params = {**params, "after": cursor}
        raise InstagramAuthError("Account discovery exceeded its supported page limit")


instagram_auth_service = InstagramAuthService()
