"""Owner trial publishing from an immutable, reviewed single-card snapshot.

The existing Post.flags stores a separate Pinterest claim. Instagram state and
copy remain untouched. Commit before the external write; never replay an unknown
outcome, including a process crash or a failed final database commit.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature
from PIL import Image

from app.config import settings
from app.models import Post, PinterestConnection
from app.services import pinterest_connection as connection
from app.services.channels.pinterest import PinDraft, PinterestError, PinterestOutcomeUnknown
from app.services.media_sequence import card_digest, saved_manifest, require_sequence_review, download_image
from app.services.source_grounding import saved_source_type, validate_saved_source_snapshot

KEY = 'pinterest_publication'
LOCKED = {'publishing', 'unknown', 'published'}


def get_post(db, post_id, org_id, *, lock=False):
    query = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).populate_existing()
    post = (query.with_for_update() if lock else query).first()
    if post is None:
        raise HTTPException(404, 'Post not found in this workspace.')
    return post


def state(post):
    record = (post.flags or {}).get(KEY) or {}
    pin_id = record.get('pin_id')
    payload = record.get('payload') or {}
    copy = ({key: payload.get(key) for key in ('title', 'description', 'alt_text', 'link')}
            | {'ai_modified': 'AI_MODIFIED' in (payload.get('ai_disclosures') or {}).get('values', [])}) if payload else None
    return {'post_id': post.id, 'status': record.get('status', 'not_sent'),
            'pin_id': pin_id, 'url': 'https://www.pinterest.com/pin/' + pin_id + '/' if pin_id else None,
            'error': record.get('error'), 'board_name': record.get('board_name'), 'copy': copy}


def eligible(post):
    if post.status in {'publishing', 'publish_unknown', 'publish_partial'}:
        raise PinterestError('Resolve the existing Instagram publishing attempt first.')
    if saved_source_type(post) not in {'quran', 'hadith'} or not post.card_message:
        raise PinterestError('Choose a source-grounded card saved in Studio.')
    if (post.flags or {}).get('relevance_check') == 'failed':
        raise PinterestError('Correct the source relevance issue in Studio first.')
    validate_saved_source_snapshot(post)
    manifest = saved_manifest(post)
    if not manifest or manifest['format'] != 'feed_4_5' or len(manifest['pages']) != 1:
        raise PinterestError('This pilot supports complete single-card feed posts only. Export every page of a carousel or Story instead.')
    require_sequence_review(post, manifest)
    metadata = {**((post.source_metadata or {}).get('metadata') or {}), **(post.source_metadata or {})}
    if (not metadata.get('arabic_text') or post.card_message.get('headline') != metadata.get('translation_text')
            or post.card_message.get('arabic_display') is not None):
        raise PinterestError('Use the complete Arabic and translation in this first Pinterest test.')
    return manifest


def image_digest(url):
    data = download_image(url)
    try:
        with Image.open(BytesIO(data)) as image:
            if image.size != (1080, 1350) or image.format != 'JPEG':
                raise PinterestError('The final single-card image must be a 1080 × 1350 JPEG.')
            image.load()  # Decode all JPEG pixels; header verification alone misses truncation.
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise PinterestError('The saved image could not be read. Regenerate or restore it in Studio before publishing.') from None
    return sha256(data).hexdigest()


def signer():
    return URLSafeTimedSerializer(settings.secret_key, salt='sabeel-pinterest-review-v1')


def snapshot(post, row, copy, manifest, media_hash):
    if not row or not row.active or row.refresh_pending or row.sandbox != settings.pinterest_sandbox or not row.board_id:
        raise PinterestError('Connect Pinterest and choose a public board first.')
    draft = PinDraft(board_id=row.board_id, image_url=post.media_url, **copy)
    payload = draft.payload()
    if post.source_reference not in draft.title + '\n' + draft.description:
        raise PinterestError('Keep the exact source reference in the Pin title or description.')
    source = {'type': saved_source_type(post), 'reference': post.source_reference,
              'text': post.source_text, 'metadata': post.source_metadata, 'card': post.card_message}
    return {'post_id': post.id, 'org_id': post.org_id, 'connection_id': row.id,
            'username': row.username, 'sandbox': row.sandbox, 'board_name': row.board_name,
            'payload': payload, 'source': deepcopy(source), 'manifest': deepcopy(manifest),
            'media_sha256': media_hash}, draft


def review(db, post_id, org_id, user_id, copy):
    post = get_post(db, post_id, org_id)
    if state(post)['status'] in LOCKED:
        raise HTTPException(409, 'This post already has a Pinterest attempt. Check its saved result before continuing.')
    manifest = eligible(post)
    row = connection.connection(db, org_id)
    snap, _ = snapshot(post, row, copy, manifest, image_digest(post.media_url))
    metadata = {**((post.source_metadata or {}).get('metadata') or {}), **(post.source_metadata or {})}
    provenance = metadata.get('translation_provenance') or {}
    details = [label + ': ' + str(value) for label, value in (
        ('Translation', provenance.get('resource_name')), ('Provider', provenance.get('provider')),
        ('Narrator', metadata.get('narrator')), ('Grade', metadata.get('grade'))) if value]
    details.extend('Translator note: ' + str(note['text']) for note in (metadata.get('translation_footnotes') or [])
                   if isinstance(note, dict) and note.get('text'))
    return {'receipt': signer().dumps({'digest': card_digest(snap), 'user_id': user_id, 'org_id': org_id}),
            'image_url': post.media_url, 'source_reference': post.source_reference,
            'arabic': post.card_message['arabic_text'], 'translation': post.card_message['headline'],
            'reflection': post.card_message.get('supporting_text') or '', 'source_details': '\n'.join(details),
            'board_name': row.board_name, 'username': row.username, 'copy': copy}


def publish(db, post_id, org_id, user_id, copy, receipt, api):
    # Fast idempotent response, including after a client loses a successful reply.
    post = get_post(db, post_id, org_id)
    existing = state(post)
    if existing['status'] == 'published':
        return {**existing, 'already_sent': True}
    if existing['status'] in {'publishing', 'unknown'}:
        raise HTTPException(409, 'Pinterest delivery is pending or uncertain. Check the saved result; do not send this post again.')
    try:
        approved = signer().loads(receipt, max_age=900)
    except BadSignature:
        raise PinterestError('Review this Pin again; its approval expired or could not be verified.') from None
    # Refresh may commit, so finish it BEFORE taking the post publishing lock.
    access = connection.token(db, org_id, api)
    post = get_post(db, post_id, org_id, lock=True)
    if state(post)['status'] == 'published':
        return {**state(post), 'already_sent': True}
    if state(post)['status'] in {'publishing', 'unknown'}:
        raise HTTPException(409, 'Another request already claimed this Pin. Check its saved result.')
    row = db.query(PinterestConnection).filter_by(org_id=org_id).populate_existing().with_for_update().one()
    if not row.active or row.sandbox != api.sandbox or connection.decrypt(row).get('access_token') != access:
        raise PinterestError('The Pinterest connection changed. Review this Pin again.')
    manifest = eligible(post)
    from app.services.rotation_engine import repetition_issues
    if repetition_issues(db, post):
        raise PinterestError('Correct repeated automation content before publishing.')
    snap, draft = snapshot(post, row, copy, manifest, image_digest(post.media_url))
    if approved != {'digest': card_digest(snap), 'user_id': user_id, 'org_id': org_id}:
        raise PinterestError('The source, image, Pin copy or destination changed. Review the Pin again.')
    board = api.board(access, row.board_id)
    identity = api.account(access)
    if (board.get('id') != row.board_id or board.get('privacy') != 'PUBLIC'
            or (board.get('owner') or {}).get('username') != row.username or identity.get('username') != row.username):
        raise PinterestError('The connected account no longer owns this public board. Reconnect and review again.')
    attempt = {**snap, 'attempt_id': uuid4().hex, 'status': 'publishing',
               'started_at': datetime.now(timezone.utc).isoformat()}
    post.flags = {**(post.flags or {}), KEY: attempt}
    db.commit()  # A failure here must prevent the provider call.
    try:
        result = api.create_pin(access, draft)
        outcome = {'status': 'published', 'pin_id': result['id'], 'error': None,
                   'published_at': datetime.now(timezone.utc).isoformat()}
    except PinterestOutcomeUnknown as error:
        outcome = {'status': 'unknown', 'error': str(error)}
    except PinterestError as error:
        outcome = {'status': 'failed', 'error': str(error)}
    except Exception:
        outcome = {'status': 'unknown', 'error': 'Pinterest delivery could not be confirmed. Check Pinterest before taking further action.'}
    try:
        post = get_post(db, post_id, org_id, lock=True)
        current = (post.flags or {}).get(KEY) or {}
        if current.get('attempt_id') != attempt['attempt_id']:
            raise RuntimeError('Publishing claim changed')
        post.flags = {**(post.flags or {}), KEY: {**current, **outcome}}
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(503, 'The Pinterest result could not be saved. Do not retry publication; check Pinterest and the saved attempt.') from None
    return state(post)


def verify(db, post_id, org_id, api):
    post = get_post(db, post_id, org_id)
    record = deepcopy((post.flags or {}).get(KEY) or {})
    if record.get('status') != 'published' or not record.get('pin_id'):
        raise HTTPException(409, 'No confirmed Pin ID is available. An uncertain attempt is never resent automatically.')
    access = connection.token(db, org_id, api)
    row = connection.connection(db, org_id)
    if row.username != record['username'] or row.sandbox != record['sandbox']:
        raise PinterestError('Reconnect the original Pinterest account to check this Pin.')
    remote = api.pin(access, record['pin_id'])
    matches = remote.get('id') == record['pin_id'] and all(
        (remote.get(key) or '') == (record['payload'].get(key) or '')
        for key in ('board_id', 'title', 'description', 'alt_text', 'link'))
    return {**state(post), 'verified': matches,
            'message': 'Pinterest returned the saved Pin and matching copy.' if matches else
                       'Pinterest returned different Pin details. Inspect the Pin; it has not been resent.'}
