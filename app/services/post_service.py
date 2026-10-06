# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
post_service.py — Phase 1 Service Wrapper

Single entry point for all post lifecycle operations in Sabeel Studio.
This is a FACADE over the existing logic scattered across:
  - routes/posts.py          (intake, approve, publish, schedule)
  - services/publisher.py    (Instagram API calls)
  - services/policy.py       (content flagging)

Manual, scheduled, and automation publishing share publish_post below.
Other lifecycle helpers remain available for legacy callers.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import update
from fastapi import HTTPException
from uuid import uuid4

from app.security.ownership import require_account
from app.services.publish_media import prepare_publish_media
from app.services.source_grounding import validate_saved_source_snapshot

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
    status_code: int = 400

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
        if status in {"scheduled", "approved"}:
            prepare_scheduled_post(db, post)
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
    try:
        post = get_mutable_post(db, post_id, org_id)
        acc = prepare_scheduled_post(db, post)
    except HTTPException as error:
        return PostResult(error=error.detail, status_code=error.status_code)
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


def prepare_scheduled_post(db: Session, post: Post) -> IGAccount:
    """Persist the selected image on the CDN before accepting a schedule."""
    account = require_account(db, post.org_id, post.ig_account_id, active=True)
    if not post.caption or not post.caption.strip() or not post.media_url:
        raise HTTPException(status_code=422, detail="A saved caption and image are required before scheduling")
    hashtags = " ".join(post.hashtags) if isinstance(post.hashtags, list) else (post.hashtags or "")
    if len(post.caption + ("\n\n" + hashtags if hashtags else "")) > 2200:
        raise HTTPException(status_code=422, detail="Shorten the caption before scheduling; preserve the source wording")
    if (post.flags or {}).get("relevance_check") == "failed":
        raise HTTPException(status_code=422, detail="The source relevance check failed")
    from app.services.rotation_engine import repetition_issues
    repeats = repetition_issues(db, post)
    if repeats:
        raise HTTPException(status_code=422, detail="Repeated content requires correction: " + ", ".join(repeats))
    try:
        validate_saved_source_snapshot(post)
        post.media_url = prepare_publish_media(post.media_url)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return account


def get_mutable_post(db: Session, post_id: int, org_id: int) -> Post:
    """Serialize edits with the publish claim and protect confirmed/uncertain outcomes."""
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).populate_existing().with_for_update().first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    publication = (post.flags or {}).get("publication") or {}
    if post.status in {"published", "publishing", "publish_unknown"} or post.published_time or publication.get("remote_id"):
        raise HTTPException(status_code=409, detail="This post is published or has an unresolved publishing attempt")
    return post


def publish_post(db: Session, post_id: int, org_id: int) -> PostResult:
    """Shared saved-post publish path for manual, scheduled and automation calls."""
    from app.services.publisher import publish_to_instagram

    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).populate_existing().with_for_update().first()
    if post is None:
        return PostResult(error="Post not found", status_code=404)
    publication = (post.flags or {}).get("publication") or {}
    if post.status == "published" or post.published_time or publication.get("remote_id"):
        return PostResult(post=post)  # Already published: never send it again.
    if post.status in {"publishing", "publish_unknown"}:
        return PostResult(post=post, error="Publishing is in progress or its outcome needs reconciliation", status_code=409)
    if post.status not in {"drafted", "submitted", "approved", "scheduled", "failed", "needs_review"}:
        return PostResult(post=post, error="This post cannot be published from its current state", status_code=409)
    if not post.caption or not post.caption.strip() or not post.media_url:
        return PostResult(post=post, error="A saved caption and image are required", status_code=422)
    if (post.flags or {}).get("relevance_check") == "failed":
        return PostResult(post=post, error="The source relevance check failed", status_code=422)
    try:
        account = require_account(db, org_id, post.ig_account_id, active=True)
        validate_saved_source_snapshot(post)
        from app.services.rotation_engine import repetition_issues
        repeats = repetition_issues(db, post)
        if repeats:
            return PostResult(post=post, error="Repeated content requires correction before publishing: " + ", ".join(repeats), status_code=422)
        media_url = prepare_publish_media(post.media_url)
    except HTTPException as error:
        return PostResult(post=post, error=error.detail, status_code=error.status_code)
    except ValueError as error:
        return PostResult(post=post, error=str(error), status_code=422)
    caption = post.caption
    if post.hashtags:
        hashtags = " ".join(post.hashtags) if isinstance(post.hashtags, list) else post.hashtags
        caption += "\n\n" + hashtags
    if len(caption) > 2200:
        return PostResult(post=post, error="The caption exceeds Instagram's limit. Shorten the social copy without rewriting scripture.", status_code=422)

    # Commit a conditional claim before any Instagram publish request. This also
    # prevents competing workers that read the same scheduled post from sending it.
    attempt = {"attempt_id": uuid4().hex, "started_at": datetime.now(timezone.utc).isoformat(),
               "ig_user_id": account.ig_user_id}
    previous_status = post.status
    flags = {**(post.flags or {}), "publication": attempt}
    claimed = db.execute(update(Post).where(
        Post.id == post_id, Post.org_id == org_id, Post.status == previous_status, Post.published_time.is_(None),
    ).values(status="publishing", media_url=media_url, flags=flags).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        return PostResult(error="Another worker already claimed this post", status_code=409)
    db.commit()
    db.refresh(post)
    ig_user_id, access_token = account.ig_user_id, account.access_token

    def record_container(creation_id):
        post.flags = {**(post.flags or {}), "publication": {**attempt, "creation_id": creation_id}}
        db.commit()

    try:
        result = publish_to_instagram(caption=caption, media_url=media_url,
                                     ig_user_id=ig_user_id, access_token=access_token,
                                     on_container_created=record_container)
        if not isinstance(result, dict):
            raise ValueError("Invalid publisher result")
    except Exception:
        # Never infer that an exception means Instagram did not publish.
        db.rollback()
        db.refresh(post)
        result = {"ok": False, "outcome": "unknown", "error": "Publishing outcome is unknown. Check Instagram before retrying."}

    publication = {**((post.flags or {}).get("publication") or attempt)}
    if result.get("creation_id"):
        publication["creation_id"] = result["creation_id"]
    if result.get("ok") and result.get("remote_id"):
        publication["remote_id"] = result["remote_id"]
        publication["outcome"] = "published"
        post.status = "published"
        post.published_time = datetime.now(timezone.utc)
        post.flags = {**(post.flags or {}), "publication": publication}
        db.commit()
        db.refresh(post)
        return PostResult(post=post)

    unknown = result.get("outcome") == "unknown" or bool(result.get("ok"))
    publication["outcome"] = "unknown" if unknown else "not_published"
    post.status = "publish_unknown" if unknown else "failed"
    error = result.get("error") or "Instagram did not return a confirmed publication ID"
    post.flags = {**(post.flags or {}), "publication": publication, "publish_error": error}
    db.commit()
    return PostResult(post=post, error=str(error), status_code=502)


def reconcile_publication(db: Session, post_id: int, org_id: int) -> PostResult:
    """Resolve an uncertain attempt using only its stored provider container."""
    from app.services.publisher import get_container_status
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).populate_existing().with_for_update().first()
    if post is None:
        return PostResult(error="Post not found", status_code=404)
    if post.status == "published":
        return PostResult(post=post)
    if post.status not in {"publishing", "publish_unknown"}:
        return PostResult(post=post, error="This post has no unresolved publication", status_code=409)
    attempt = dict((post.flags or {}).get("publication") or {})
    now = datetime.now(timezone.utc)
    try:
        started = datetime.fromisoformat(attempt["started_at"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if post.status == "publishing" and now - started < timedelta(minutes=10):
            return PostResult(post=post, error="Publishing is still in progress", status_code=409)
    except (KeyError, TypeError, ValueError):
        return PostResult(post=post, error="This attempt needs manual investigation because its start time is missing", status_code=409)
    if not attempt.get("creation_id"):
        return PostResult(post=post, error="No container ID was saved. Check Instagram before resolving this attempt.", status_code=409)
    try:
        account = require_account(db, org_id, post.ig_account_id, active=True)
    except HTTPException as error:
        return PostResult(post=post, error=error.detail, status_code=error.status_code)
    if attempt.get("ig_user_id") and attempt["ig_user_id"] != account.ig_user_id:
        return PostResult(post=post, error="The connected Instagram account changed after this attempt", status_code=409)
    code = get_container_status(str(attempt["creation_id"]), account.access_token)
    attempt.update(provider_status=code or "UNAVAILABLE", reconciled_at=now.isoformat())
    if code == "PUBLISHED":
        post.status = "published"
        attempt["outcome"] = "published"
        # A container ID is not a published media ID. Do not invent the missing
        # remote_id or publication timestamp when only status was recovered.
    elif code in {"ERROR", "EXPIRED"}:
        post.status = "failed"
        attempt["outcome"] = "not_published"
    else:
        post.status = "publish_unknown"
    post.flags = {**(post.flags or {}), "publication": attempt}
    if code in {"PUBLISHED", "ERROR", "EXPIRED"}:
        post.flags = {key: value for key, value in post.flags.items() if key != "publish_error"}
    db.commit()
    db.refresh(post)
    if code in {"PUBLISHED", "ERROR", "EXPIRED"}:
        return PostResult(post=post)
    return PostResult(post=post, error="Instagram has not confirmed a final outcome. Publishing remains blocked.", status_code=409)


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
