# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
rotation_engine.py — Intelligent Topic & Style Rotation for Automations
========================================================================

Provides no-repeat rotation logic for automation topic and style pools.
Used by automation_runner.py and automation_service.py.

Key design decisions:
- Zero schema migrations: state is stored in existing ContentUsage.meta (JSON column)
  and TopicAutomation.flags (JSON column).
- Graceful degradation: if usage records are missing or DB fails, falls back to
  random selection so automation never silently fails.
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

_META_TOPIC_KEY = "rotation_topic"        # key inside ContentUsage.meta
_META_STYLE_KEY = "rotation_style_id"     # key inside ContentUsage.meta
_META_PAIR_KEY  = "rotation_pair"         # key inside ContentUsage.meta


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
            topic_val = u.get(_META_TOPIC_KEY)
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
        candidates = [t for t in topic_pool if t not in recently_used]

        if candidates:
            chosen = random.choice(candidates)
            logger.info(f"[ROTATION] automation_id={automation_id} topic={chosen!r} "
                        f"(from {len(candidates)} fresh candidates, {len(recently_used)} excluded)")
            return chosen

        # All topics are within the window — pick the least recently used
        pool_sorted = sorted(
            topic_pool,
            key=lambda t: last_used_at.get(t, datetime.min.replace(tzinfo=timezone.utc))
        )
        chosen = pool_sorted[0]
        logger.info(f"[ROTATION] automation_id={automation_id} topic={chosen!r} "
                    f"(all excluded, relaxed to LRU)")
        return chosen

    except Exception as e:
        logger.warning(f"[ROTATION] pick_topic failed gracefully: {e}")
        return random.choice(topic_pool)


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


def record_topic_used(
    automation_id: int,
    topic: str,
    style_id: Optional[int],
    db: Session,
) -> None:
    """
    Record a topic (and optional style) usage in ContentUsage.meta.
    This powers the no-repeat window for the next run.

    Also updates TopicAutomation.flags["last_style_id"] so the next call to
    pick_style() can avoid the current style.

    Args:
        automation_id: ID of the automation.
        topic:         Topic string that was used this run.
        style_id:      StyleDNA ID used this run (may be None).
        db:            SQLAlchemy session.
    """
    try:
        from app.models import ContentUsage, TopicAutomation
        now = datetime.now(timezone.utc)

        usage = ContentUsage(
            automation_id=automation_id,
            content_item_id=None,      # not a content item
            status="rotation_record",
            used_at=now,
            meta={
                _META_TOPIC_KEY: topic,
                _META_STYLE_KEY: style_id,
                _META_PAIR_KEY: f"{topic}|{style_id}",
                "used_at": now.isoformat(),
                "record_type": "rotation",
            },
        )
        db.add(usage)

        # Persist last_style_id into automation.flags for next run
        if style_id is not None:
            auto = db.get(TopicAutomation, automation_id)
            if auto:
                flags = dict(auto.flags or {})
                flags["last_style_id"] = style_id
                auto.flags = flags

        db.flush()  # Don't commit here — caller controls the transaction
        logger.info(f"[ROTATION] Recorded usage: automation_id={automation_id} "
                    f"topic={topic!r} style_id={style_id}")

    except Exception as e:
        logger.warning(f"[ROTATION] record_topic_used failed gracefully: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_topic_usages(automation_id: int, db: Session) -> list[dict]:
    """
    Load rotation usage records for an automation from ContentUsage.
    Returns a list of meta dicts, most recent first.
    """
    try:
        from app.models import ContentUsage
        from sqlalchemy import select, desc

        stmt = (
            select(ContentUsage)
            .where(
                ContentUsage.automation_id == automation_id,
                ContentUsage.status == "rotation_record",
            )
            .order_by(desc(ContentUsage.used_at))
            .limit(200)   # Enough for 30-day window at 3× daily
        )
        rows = db.execute(stmt).scalars().all()
        return [row.meta for row in rows if row.meta]
    except Exception as e:
        logger.warning(f"[ROTATION] _load_topic_usages failed: {e}")
        return []
