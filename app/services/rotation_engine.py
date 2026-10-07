# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
rotation_engine.py — Intelligent Topic & Style Rotation for Automations
========================================================================

Provides no-repeat rotation logic for automation topic and style pools.
Used by automation_runner.py and automation_service.py.

Key design decisions:
- Rotation is stored with each generated post in the existing Post.flags column.
- Database failures stop selection rather than ignoring saved usage history.
- Works for both single-topic automations (pool=[topic_prompt]) and multi-topic.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

_META_TOPIC_KEY = "rotation_topic"        # key inside Post.flags
_META_STYLE_KEY = "rotation_style_id"     # key inside Post.flags
_META_PAIR_KEY  = "rotation_pair"         # key inside Post.flags


def normalized_text(value):
    return " ".join((value or "").split()).casefold()


def source_identity(item):
    """Compare canonical verse/narration identity, not a translation row ID."""
    if item.item_type == "quran":
        from app.services.quran_serialization import normalize_quran_verse
        verse = normalize_quran_verse(item)
        return "quran:" + verse["verse_key"]
    meta = item.meta or {}
    if item.item_type == "hadith" and meta.get("collection_key") and meta.get("hadith_number"):
        return f"hadith:{meta['collection_key']}:{meta['hadith_number']}"
    return f"library:{item.id}"


def rank_source_items(items, db, automation_id, avoid_days=30):
    """Rank the complete matching library pool before limiting provider results."""
    from app.models import ContentUsage, ContentItem
    if not automation_id:
        return items
    rows = db.query(ContentUsage, ContentItem).join(ContentItem, ContentUsage.content_item_id == ContentItem.id).filter(ContentUsage.automation_id == automation_id).all()
    last_used = {}
    for usage, item in rows:
        try:
            key = source_identity(item)
        except ValueError:
            continue
        used_at = usage.used_at.replace(tzinfo=timezone.utc) if usage.used_at.tzinfo is None else usage.used_at
        last_used[key] = max(last_used.get(key, used_at), used_at)
    random.shuffle(items)
    valid = []
    for item in items:
        try:
            valid.append((item, source_identity(item)))
        except ValueError:
            continue
    cutoff = datetime.now(timezone.utc) - timedelta(days=avoid_days)
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    valid.sort(key=lambda pair: last_used.get(pair[1], oldest))
    if valid and all(last_used.get(key, oldest) >= cutoff for _, key in valid):
        logger.info("Source pool exhausted for automation %s; using least recently used valid candidates", automation_id)
    return [item for item, _ in valid]


def recent_posts(db, automation_id):
    from app.models import Post
    return db.query(Post).filter(Post.automation_id == automation_id,
                                Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)).all()


def rank_provider_items(items, db, automation_id, avoid_days=30):
    """Deduplicate overlapping provider searches and rank by canonical source usage."""
    from app.models import ContentItem
    by_id = {str(item.original_id): item for item in items if str(item.original_id).isdigit()}
    if not by_id:
        return []
    records = db.query(ContentItem).filter(ContentItem.id.in_([int(key) for key in by_id])).all()
    return [by_id[str(item.id)] for item in rank_source_items(records, db, automation_id, avoid_days)]


def repetition_issues(db, post):
    if not post.automation_id:
        return []
    issues = set()
    visual = (post.source_metadata or {}).get("visual_generation") or {}
    for previous in recent_posts(db, post.automation_id):
        if previous.id == post.id:
            continue
        if post.caption and normalized_text(previous.caption) == normalized_text(post.caption):
            issues.add("duplicate_caption")
        reflection = (post.card_message or {}).get("supporting_text")
        if reflection and normalized_text((previous.card_message or {}).get("supporting_text")) == normalized_text(reflection):
            issues.add("duplicate_reflection")
        if post.visual_mode not in {"reuse_last_upload", "use_library_image", "library_fixed", "library_tag", "media_library", "upload", "gallery"}:
            old_visual = (previous.source_metadata or {}).get("visual_generation") or {}
            if (visual.get("background_sha256") and visual["background_sha256"] == old_visual.get("background_sha256")) or (post.media_url and post.media_url == previous.media_url):
                issues.add("duplicate_visual")
    return sorted(issues)


def visual_history(db, automation_id):
    history = {}
    for post in recent_posts(db, automation_id):
        metadata = (post.source_metadata or {}).get("visual_generation") or {}
        signature = metadata.get("prompt_signature")
        if signature:
            at = post.created_at.isoformat()
            history[signature] = max(history.get(signature, at), at)
    return history


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def pick_topic(
    topic_pool: list[str],
    automation_id: int,
    db: Session,
    avoid_days: int = 30,
) -> str:
    """
    Pick the best next topic from the pool.

    Algorithm:
    1. Build a set of topics used within `avoid_days` (the exclusion window).
    2. Candidates = pool entries NOT in the exclusion window.
    3. If no candidates (all excluded), relax to the full pool and pick the
       LEAST recently used topic.
    4. Within candidates, pick randomly (equal probability) to avoid pattern.
    5. If the pool has only one entry, always return it.

    Args:
        topic_pool:   List of topic strings configured by the user.
        automation_id: ID of the automation for scoping usage records.
        db:           SQLAlchemy session.
        avoid_days:   Do not repeat a topic within this many days (default 30).

    Returns:
        A topic string from the pool.
    """
    if not topic_pool:
        return ""
    if len(topic_pool) == 1:
        return topic_pool[0]

    try:
        usages = _load_topic_usages(automation_id, db)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=avoid_days)

        # Topics used recently (within window)
        recently_used: set[str] = set()
        last_used_at: dict[str, datetime] = {}

        for u in usages:
            topic_val = normalized_text(u.get(_META_TOPIC_KEY))
            used_at_str = u.get("used_at")
            if not topic_val or not used_at_str:
                continue
            try:
                used_at = datetime.fromisoformat(used_at_str)
                # Normalize to UTC-aware
                if used_at.tzinfo is None:
                    used_at = used_at.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            last_used_at[topic_val] = max(last_used_at.get(topic_val, used_at), used_at)
            if used_at >= cutoff:
                recently_used.add(topic_val)

        # Candidates: not used within the avoid window
        candidates = [t for t in topic_pool if normalized_text(t) not in recently_used]

        if candidates:
            chosen = random.choice(candidates)
            logger.info(f"[ROTATION] automation_id={automation_id} topic={chosen!r} "
                        f"(from {len(candidates)} fresh candidates, {len(recently_used)} excluded)")
            return chosen

        # All topics are within the window — pick the least recently used
        pool_sorted = sorted(
            topic_pool,
            key=lambda t: last_used_at.get(normalized_text(t), datetime.min.replace(tzinfo=timezone.utc))
        )
        chosen = pool_sorted[0]
        logger.info(f"[ROTATION] automation_id={automation_id} topic={chosen!r} "
                    f"(all excluded, relaxed to LRU)")
        return chosen

    except Exception as e:
        logger.error("[ROTATION] Could not read usage history")
        raise


def pick_style(
    style_dna_pool: list[int],
    last_style_id: Optional[int] = None,
) -> Optional[int]:
    """
    Pick the next style DNA ID from the pool, avoiding the one used last time.

    Algorithm:
    1. If pool is empty, return None (runner uses fallback preset).
    2. If pool has one entry, always return it.
    3. Exclude the last-used style ID, pick randomly from remaining.
    4. If all styles excluded (shouldn't happen unless pool==[last]), return random.

    Args:
        style_dna_pool: List of StyleDNA IDs configured for this automation.
        last_style_id:  The style DNA ID used in the previous run (from flags).

    Returns:
        A StyleDNA ID integer, or None if the pool is empty.
    """
    if not style_dna_pool:
        return None
    if len(style_dna_pool) == 1:
        return style_dna_pool[0]

    candidates = [sid for sid in style_dna_pool if sid != last_style_id]
    if not candidates:
        candidates = style_dna_pool

    chosen = random.choice(candidates)
    logger.info(f"[ROTATION] style_id={chosen} chosen (last={last_style_id}, "
                f"pool={style_dna_pool})")
    return chosen


def record_topic_used(post, topic: str, style_id: Optional[int], pillar=None) -> None:
    """Persist rotation alongside the generated post in the caller's transaction."""
    post.flags = {**(post.flags or {}),
                  _META_TOPIC_KEY: topic, _META_STYLE_KEY: style_id,
                  "rotation_pillar": pillar,
                  "rotation_used_at": datetime.now(timezone.utc).isoformat()}


def latest_rotation(automation_id: int, db: Session) -> dict:
    from app.models import Post
    posts = db.query(Post).filter(Post.automation_id == automation_id).order_by(Post.created_at.desc(), Post.id.desc()).all()
    return next((dict(post.flags) for post in posts if (post.flags or {}).get(_META_TOPIC_KEY)), {})


def _load_topic_usages(automation_id: int, db: Session) -> list[dict]:
    from app.models import Post
    posts = db.query(Post).filter(Post.automation_id == automation_id).order_by(Post.created_at.desc()).all()
    return [{**post.flags, "used_at": post.flags.get("rotation_used_at") or post.created_at.isoformat()}
            for post in posts if (post.flags or {}).get(_META_TOPIC_KEY)]
