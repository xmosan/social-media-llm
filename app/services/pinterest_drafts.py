"""Versioned creator copy, separate from canonical sources and publications."""
from datetime import datetime, timezone
from fastapi import HTTPException
from app.services import pinterest_publishing as publishing
from app.services.pinterest_connection import creator_enabled
from app.services.channels.pinterest import PinDraft, PinterestError
from app.services.media_sequence import card_digest

KEY = 'pinterest_draft'


def source_version(post):
    return card_digest({'source': post.source_text, 'metadata': post.source_metadata,
        'reference': post.source_reference, 'card': post.card_message, 'image': post.media_url,
        'manifest': (post.flags or {}).get('media_manifest')})


def copy_issues(post, copy):
    try:
        # Reuse the actual publisher's copy/media contract without a provider call.
        PinDraft(board_id='1', image_url=post.media_url, **copy).payload()
        if post.source_reference not in copy['title'] + '\n' + copy['description']:
            return ['Keep the exact source reference in the title or description.']
    except PinterestError as error:
        return [str(error)]
    return []


def read(post):
    publishing.eligible(post)
    record = (post.flags or {}).get(KEY) or {}
    publication = publishing.state(post)
    locked = publication['status'] in publishing.LOCKED
    reference = post.source_reference or ''
    copy = publication['copy'] if locked else record.get('copy')
    copy = copy or {'title': reference if len(reference) <= 100 else '', 'description': '',
                    'alt_text': '', 'ai_modified': None, 'link': None}
    current = source_version(post)
    return {'post_id': post.id, **publishing.source_preview(post), 'copy': copy,
            'revision': record.get('revision', 0), 'source_version': current,
            'source_changed': bool(record and record.get('source_version') != current),
            'saved_at': record.get('saved_at'), 'locked': locked, 'publication_status': publication['status'],
            'issues': copy_issues(post, copy), 'publishing_enabled': creator_enabled(),
            'publication': publication}


def reviewed_copy(post, revision, expected_source):
    """Only the saved revision may enter the shared review/publish pipeline."""
    record = (post.flags or {}).get(KEY) or {}
    if (not record or record.get('revision') != revision
            or record.get('source_version') != expected_source
            or source_version(post) != expected_source):
        raise HTTPException(409, 'Your card or Pin draft changed. Save and review the latest version before publishing.')
    copy = record['copy']
    issues = copy_issues(post, copy)
    if issues:
        raise HTTPException(422, issues[0])
    return copy


def save(db, post_id, org_id, copy, revision, expected_source):
    post = publishing.get_post(db, post_id, org_id, lock=True)
    publishing.eligible(post)
    if publishing.state(post)['status'] in publishing.LOCKED:
        raise HTTPException(409, 'This card has a Pinterest publishing attempt. Its submitted copy is read-only.')
    if source_version(post) != expected_source:
        raise HTTPException(409, 'This card changed in Studio. Reload it and review the latest source and image before saving.')
    record = (post.flags or {}).get(KEY) or {}
    current_revision = record.get('revision', 0)
    if revision != current_revision:
        # A retry after a lost successful response returns the same saved draft.
        if (revision == current_revision - 1 and record.get('copy') == copy
                and record.get('source_version') == expected_source):
            result = read(post); db.commit(); return result
        raise HTTPException(409, 'This Pin draft was saved in another tab. Copy your changes, then reload the saved version.')
    post.flags = {**(post.flags or {}), KEY: {'copy': copy, 'revision': current_revision + 1,
        'source_version': expected_source, 'saved_at': datetime.now(timezone.utc).isoformat()}}
    db.commit()
    return read(post)
