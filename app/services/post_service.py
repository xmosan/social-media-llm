# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
post_service.py — Phase 1 Service Wrapper

Single entry point for all post lifecycle operations in Sabeel Studio.
This is a FACADE over the existing logic scattered across:
  - routes/posts.py          (intake, approve, publish, schedule)
  - services/publisher.py    (Instagram API calls)
  - services/policy.py       (content flagging)

IMPORTANT: This file does NOT change any existing route or model.
All existing routes continue to work unchanged.
New routes (Phase 3 Studio API) and the automation engine will call this service.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Post, IGAccount, MediaAsset
from app.config import settings
from app.logging_setup import log_event

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# INPUT / OUTPUT MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PostCreateRequest:
    """
    Structured request to create a post record.
    Maps to fields on the Post model but is framework-agnostic.
    """
    org_id: int
    ig_account_id: int

    # Content
    source_type: str = "studio_manual"
    source_text: Optional[str] = None
    topic: Optional[str] = None
    source_reference: Optional[str] = None

    # Structured content (from decoupled pipeline)
    card_message: Optional[dict] = None       # {eyebrow, headline, supporting_text}
    caption_message: Optional[dict] = None    # {hook, body, cta, hashtags}

    # Visual
    media_url: Optional[str] = None
    visual_mode: str = "upload"               # upload | ai_background | media_library | quote_card
    visual_prompt: Optional[str] = None

    # Scheduling
    status: str = "drafted"                   # drafted | scheduled | approved
    scheduled_time: Optional[datetime] = None

    # Metadata
    is_auto_generated: bool = False
    automation_id: Optional[int] = None
    source_metadata: Optional[dict] = None

    # Islamic content intelligence
    intent_type: Optional[str] = None
    source_foundation: Optional[str] = None   # quran | hadith | reflection
    strictness_mode: str = "balanced"


@dataclass
class PostResult:
    """Result of a post service operation."""
    post: Optional[Post] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.post is not None and self.error is None


# ─────────────────────────────────────────────────────────────────────────────
# CORE SERVICE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def create_post(db: Session, request: PostCreateRequest) -> PostResult:
    """
    Creates and persists a Post record from a structured PostCreateRequest.
    Runs content policy check automatically.

    This is the canonical way to create posts going forward.
    The existing /posts/intake route will eventually call this.
    """
    try:
        # Validate account
        acc = db.query(IGAccount).filter(
            IGAccount.id == request.ig_account_id,
            IGAccount.org_id == request.org_id
        ).first()
        if not acc:
            return PostResult(error="IGAccount not found or not in your organization")

        # Policy check (non-blocking — flags the post, doesn't reject it)
        flags = {}
        if request.source_text or (request.card_message and request.card_message.get("headline")):
            from app.services.policy import keyword_flags
            check_text = (request.source_text or "") + " " + (
                request.card_message.get("headline", "") if request.card_message else ""
            )
            flags = keyword_flags(check_text)

        # Derive status
        status = request.status
        if flags.get("needs_review") and status == "drafted":
            status = "needs_review"

        # Map caption_message to a flat caption string (backwards compat)
        flat_caption = None
        hashtags = None
        if request.caption_message:
            parts = []
            if request.caption_message.get("hook"):
                parts.append(request.caption_message["hook"])
            if request.caption_message.get("body"):
                parts.append(request.caption_message["body"])
            if request.caption_message.get("cta"):
                parts.append(request.caption_message["cta"])
            flat_caption = "\n\n".join(parts) if parts else None
            hashtags = request.caption_message.get("hashtags", [])

        post = Post(
            org_id=request.org_id,
            ig_account_id=request.ig_account_id,
            status=status,
            source_type=request.source_type,
            source_text=request.source_text,
            topic=request.topic,
            source_reference=request.source_reference,
            source_metadata=request.source_metadata,
            card_message=request.card_message,
            caption_message=request.caption_message,
            caption=flat_caption,
            hashtags=hashtags,
            media_url=request.media_url,
            visual_mode=request.visual_mode,
            visual_prompt=request.visual_prompt,
            scheduled_time=request.scheduled_time,
            is_auto_generated=request.is_auto_generated,
            automation_id=request.automation_id,
            intent_type=request.intent_type,
            source_foundation=request.source_foundation or (
                "quran" if request.source_type == "quran" else None
            ),
            strictness_mode=request.strictness_mode,
            flags=flags,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        log_event("post_service_create", post_id=post.id,
                  org_id=request.org_id, status=status,
                  source_type=request.source_type)
        return PostResult(post=post)

    except Exception as e:
        logger.error(f"[PostService] create_post failed: {e}", exc_info=True)
        db.rollback()
        return PostResult(error=str(e))


def schedule_post(db: Session, post_id: int, org_id: int,
                  scheduled_time: Optional[datetime] = None) -> PostResult:
    """
    Marks a post as scheduled. Calculates next slot if no time provided.
    """
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        return PostResult(error="Post not found")

    if not post.caption or not post.media_url:
        return PostResult(error="Cannot schedule: post is missing caption or media")

    acc = db.get(IGAccount, post.ig_account_id)
    if scheduled_time:
        post.scheduled_time = scheduled_time
    else:
        post.scheduled_time = _next_slot(acc)

    post.status = "scheduled"
    db.commit()
    db.refresh(post)
    log_event("post_service_schedule", post_id=post.id, org_id=org_id,
              scheduled_time=post.scheduled_time.isoformat() if post.scheduled_time else None)
    return PostResult(post=post)


def publish_post(db: Session, post_id: int, org_id: int) -> PostResult:
    """
    Immediately publishes a post to Instagram.
    Delegates to the existing publisher.py. Does not replace it.
    """
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        return PostResult(error="Post not found")

    if not post.caption or not post.media_url:
        post.status = "failed"
        post.flags = {**(post.flags or {}), "reason": "missing_content_at_publish"}
        db.commit()
        return PostResult(error="Missing caption or media URL")

    # NEW: Relevance Safety Gate
    if post.flags.get("relevance_check") == "failed":
        log_event("post_publish_blocked_relevance", post_id=post.id, org_id=org_id)
        return PostResult(error="Source relevance check failed. Regenerate this post before publishing.")

    from app.services.publisher import publish_to_instagram

    acc = db.get(IGAccount, post.ig_account_id)
    caption_full = post.caption
    if post.hashtags:
        caption_full += "\n\n" + " ".join(post.hashtags)

    log_event("post_service_publish_start", post_id=post.id, org_id=org_id)

    res = publish_to_instagram(
        caption=caption_full,
        media_url=post.media_url,
        ig_user_id=acc.ig_user_id,
        access_token=acc.access_token,
    )

    if not res.get("ok"):
        post.status = "failed"
        post.flags = {**(post.flags or {}), "publish_error": res.get("error")}
        db.commit()
        log_event("post_service_publish_fail", post_id=post.id, error=res.get("error"))
        return PostResult(post=post, error=f"Publish failed: {res.get('error')}")

    post.status = "published"
    post.published_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(post)
    log_event("post_service_publish_success", post_id=post.id, remote_id=res.get("id"))
    return PostResult(post=post)


def get_post(db: Session, post_id: int, org_id: int) -> Optional[Post]:
    """Fetch a single post scoped to the organization."""
    return db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()


def list_posts(db: Session, org_id: int,
               ig_account_id: Optional[int] = None,
               status: Optional[str] = None,
               limit: int = 50) -> list[Post]:
    """List posts for an org with optional filters."""
    from sqlalchemy import select
    stmt = select(Post).where(Post.org_id == org_id).order_by(Post.created_at.desc())
    if status:
        stmt = stmt.where(Post.status == status)
    if ig_account_id:
        stmt = stmt.where(Post.ig_account_id == ig_account_id)
    stmt = stmt.limit(min(limit, 200))
    return list(db.execute(stmt).scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _next_slot(acc: IGAccount) -> datetime:
    """Calculate the next scheduled post time for a given account."""
    import pytz
    tz = pytz.timezone(acc.timezone or "UTC")
    now_tz = datetime.now(tz)
    time_str = acc.daily_post_time or "09:00"
    hour, minute = map(int, time_str.split(":"))
    target = now_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now_tz:
        target += timedelta(days=1)
    return target.astimezone(pytz.utc)
