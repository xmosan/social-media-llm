import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import json

from app.db import get_db
from sqlalchemy.orm import Session
from app.models import Post
from app.security.rbac import get_current_org_id

from app.services.quote_message_service import build_quote_card_message
from app.services.visual_service import VisualRequest, generate_visual
# NOTE: Using exactly what main.py used for caption logic to avoid regressions
from app.services.caption_engine import generate_islamic_caption

logger = logging.getLogger(__name__)


def _parse_scheduled_at(value: str | None) -> datetime | None:
    """
    Parse a scheduled_at ISO string into a UTC-aware datetime.
    Accepts: ISO 8601 with or without timezone offset.
    Returns None if value is falsy or unparseable.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception as exc:
        logger.warning(f"[STUDIO] Could not parse scheduled_at='{value}': {exc}")
        return None

router = APIRouter(prefix="/api/studio", tags=["studio"])


@router.post("/generate-card-message")
def studio_generate_card_message(data: dict):
    """
    Phase 3: Generate strictly the structured card message payload.
    Separated from caption generation.
    Supports source_type: quran | hadith | manual
    """
    source_type = data.get("source_type", "manual")
    source_payload = data.get("source_payload", {})
    tone = data.get("tone", "calm")
    intent = data.get("intent", "wisdom")

    try:
        card_msg = build_quote_card_message(source_type, source_payload, tone, intent)
        return {"card_message": card_msg}
    except Exception as e:
        logger.error(f"[STUDIO] Card Message generation failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/generate-caption")
def studio_generate_caption(data: dict):
    """
    Phase 3: Generate the social media caption explicitly.
    Does NOT affect or generate visual card text.

    Source grounding contract:
    - Hadith: uses exact reference + translation_text from source_payload → generate_hadith_caption()
    - Quran:  if source_payload has translation_text → bypass DB re-search, call generate_ai_caption_from_quran() directly
              otherwise fall through to topic-based search (manual/fallback)
    - narrator is cited only if present in source_payload — never fabricated
    """
    source_type = data.get("source_type") or "manual"
    source_payload = data.get("source_payload") or {}
    tone = data.get("tone", "calm")
    intention = data.get("intention") or data.get("intent")
    topic = data.get("topic")

    # ── Hadith: grounded caption from exact metadata ───────────────────────────
    if source_type == "hadith":
        try:
            from app.services.hadith_caption_service import generate_hadith_caption
            caption = generate_hadith_caption(source_payload, tone=tone, intent=intention)
            return {"caption": caption}
        except Exception as e:
            logger.error(f"[STUDIO] Hadith caption generation failed: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ── Quran: bypass DB re-search if payload is complete ─────────────────────
    # This is the critical source-drift fix.
    # If source_payload has both reference and translation_text, we already have
    # exactly what was shown on the card — no need to re-search, which could
    # return a different verse entirely.
    if source_type == "quran" and source_payload.get("translation_text") and source_payload.get("reference"):
        try:
            from app.services.quran_caption_service import generate_ai_caption_from_quran
            caption = generate_ai_caption_from_quran(source_payload, style=tone)
            logger.info(f"[STUDIO] Quran caption grounded directly to: {source_payload.get('reference')}")
            return {"caption": caption}
        except Exception as e:
            logger.error(f"[STUDIO] Quran grounded caption failed: {e}")
            # Fall through to topic-based generation below

    # ── Quran fallback: inject reference into topic for topic-based search ─────
    if source_payload and source_type == "quran":
        reference = source_payload.get("reference") or source_payload.get("verse_key")
        if reference and topic:
            topic = f"{reference} - {topic}"
        elif reference:
            topic = reference

    # ── Manual / fallback ─────────────────────────────────────────────────────
    try:
        caption = generate_islamic_caption(intention, topic, tone)
        return {"caption": caption}
    except Exception as e:
        logger.error(f"[STUDIO] Caption generation failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/generate-visual")
def studio_generate_visual(data: dict):
    """
    Phase 3: Route explicitly into Visual Service Facade for all Studio image generation.
    """
    req = VisualRequest(
        theme=data.get("theme", data.get("style", "sacred_black")),
        atmosphere=data.get("atmosphere", "contemplative"),
        ornament_level=data.get("ornament_level", "corner"),
        custom_prompt=data.get("visual_prompt"),
        card_message=data.get("card_message"),
        style=data.get("style", "quran"),
        mode=data.get("mode", "preset"),
        engine=data.get("engine", "dalle"),
        glossy=data.get("glossy", False),
        readability_priority=data.get("readability_priority", True),
        experimental_mode=data.get("experimental_mode", False),
        text_style_prompt=data.get("text_style_prompt", ""),
    )

    res = generate_visual(req)
    if not res.ok:
        return JSONResponse(status_code=500, content={"error": res.error})

    return {
        "image_url": res.url,
        "mode_used": req.mode or "preset",
        "style_used": req.style,
        "prompt_applied": bool(req.custom_prompt)
    }


@router.post("/create-post")
def studio_create_post(data: dict, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    """
    Phase 3: Safely create a one-off post by assembling the separated payloads.
    Guarantees structural traceability for source data mapping.

    Hadith source validation gate:
    - If source_type == "hadith", source_metadata must contain reference and
      at least one of translation_text / arabic_text / card_text.
    - This prevents saving Hadith posts with broken source integrity.
    - Does NOT affect Quran or manual post creation.
    """
    ig_account_id = data.get("ig_account_id")
    if not ig_account_id:
        raise HTTPException(status_code=400, detail="ig_account_id required")

    source_type = data.get("source_type", "manual")
    source_reference = data.get("source_reference")
    source_metadata = data.get("source_metadata")
    source_text = data.get("source_text") or data.get("topic") or ""

    # ── Hadith Source Integrity Validation Gate ────────────────────────────────
    if source_type == "hadith":
        meta = source_metadata or {}
        missing = []
        if not (meta.get("reference") or source_reference):
            missing.append("reference")
        if not (meta.get("translation_text") or meta.get("arabic_text") or meta.get("card_text")):
            missing.append("translation_text or arabic_text")
        if missing:
            logger.warning(
                f"[STUDIO] Hadith post blocked — missing source integrity fields: {missing}"
            )
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot save Hadith post: missing required source fields: {', '.join(missing)}. "
                    "Please select a Hadith from the Library or Studio before publishing."
                )
            )
        # Normalise: ensure source_reference is always set on the Post
        if not source_reference:
            source_reference = meta.get("reference")

    # Safe isolation
    card_msg = data.get("card_message")
    caption_msg = data.get("caption_message") or data.get("caption", "")

    # Convert structures mapped from UI
    if isinstance(card_msg, str):
        try:
            card_msg = json.loads(card_msg)
        except Exception:
            card_msg = None

    # Derive source_foundation for the Post model
    if source_type == "hadith":
        source_foundation = "hadith"
    elif source_type == "quran":
        source_foundation = "quran"
    else:
        source_foundation = None

    # ── Scheduling ──────────────────────────────────────────────────────────────
    # If the frontend provides a specific scheduled_at datetime, use it as the
    # canonical scheduled_time and promote the post to "scheduled" status.
    # This is the single source of truth for both the Studio and Planning calendar.
    raw_scheduled_at = data.get("scheduled_at")
    scheduled_time = _parse_scheduled_at(raw_scheduled_at)

    # Determine final status
    if scheduled_time:
        final_status = "scheduled"
    else:
        final_status = data.get("status", "drafted")

    post = Post(
        org_id=org_id,
        ig_account_id=ig_account_id,
        status=final_status,
        scheduled_time=scheduled_time,
        source_type=source_type,
        source_reference=source_reference,
        source_metadata=source_metadata,
        source_text=source_text,
        topic=data.get("topic"),
        media_url=data.get("media_url"),
        card_message=card_msg,
        caption=caption_msg.get("caption", "") if isinstance(caption_msg, dict) else caption_msg,
        caption_message=caption_msg if isinstance(caption_msg, dict) else {"caption": caption_msg},
        post_format=data.get("post_format"),
        visual_style=data.get("visual_style"),
        # Intelligence fields
        intent_type=data.get("intent_type"),
        message_hint=data.get("message_hint"),
        source_foundation=source_foundation,
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    logger.info(
        f"[STUDIO] Post {post.id} created — status={post.status}, "
        f"scheduled_time={post.scheduled_time}"
    )
    return post


@router.get("/post/{id}")
def studio_get_post(id: int, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    post = db.query(Post).filter(Post.id == id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.post("/schedule-post")
def studio_schedule_post(
    data: dict,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """
    Schedule an existing draft post.
    Accepts: { post_id: int, scheduled_at: str (ISO 8601) }
    Sets Post.scheduled_time + Post.status = 'scheduled'.
    This is the canonical scheduling action used by the Studio Share step.
    """
    post_id = data.get("post_id")
    raw_scheduled_at = data.get("scheduled_at")

    if not post_id:
        raise HTTPException(status_code=400, detail="post_id required")
    if not raw_scheduled_at:
        raise HTTPException(status_code=400, detail="scheduled_at required")

    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    scheduled_time = _parse_scheduled_at(raw_scheduled_at)
    if not scheduled_time:
        raise HTTPException(status_code=400, detail="Invalid scheduled_at format. Use ISO 8601.")

    post.scheduled_time = scheduled_time
    post.status = "scheduled"
    db.commit()
    db.refresh(post)

    logger.info(f"[STUDIO] Post {post.id} scheduled for {post.scheduled_time}")
    return {
        "ok": True,
        "post_id": post.id,
        "status": post.status,
        "scheduled_time": post.scheduled_time.isoformat(),
    }
