import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import json

from app.db import get_db
from sqlalchemy.orm import Session
from app.models import Post, User
from app.security.rbac import get_current_org_id
from app.security.auth import require_user, get_current_user
from app.security.ownership import require_account
from app.services.source_grounding import resolve_selected_source
from app.services.post_service import get_mutable_post, prepare_scheduled_post

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


@router.post("/discover-sources")
def studio_discover_sources(data: dict, db: Session = Depends(get_db),
                           org_id: int = Depends(get_current_org_id), user: User = Depends(require_user)):
    from app.services.creator_discovery import discover_sources
    from app.services.text_provider import TextGenerationError
    try:
        return discover_sources(db, org_id, user.id, data.get("idea"), data.get("source_type", "quran"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except TextGenerationError:
        raise HTTPException(503, "Sabeel could not prepare suggestions. Your idea is kept. Retry or choose a source directly.") from None
    except HTTPException:
        raise
    except Exception:
        logger.exception("Creator source discovery failed")
        raise HTTPException(503, "Source search is unavailable. Your idea is kept; try again shortly.") from None


@router.get("/brand-kit", dependencies=[Depends(require_user)])
def get_brand_kit(db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    from app.services.brand_kit import workspace_brand
    from app.services.media_sequence import card_digest
    kit = workspace_brand(db, org_id)
    return {"brand_kit": kit, "revision": card_digest(kit)}


@router.put("/brand-kit", dependencies=[Depends(require_user)])
def save_brand_kit(data: dict, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    from app.models import Org
    from app.services.brand_kit import normalize_brand
    from app.services.media_sequence import card_digest
    try:
        kit = normalize_brand(data.get("brand_kit"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    org = db.query(Org).filter(Org.id == org_id).populate_existing().with_for_update().first()
    if not org:
        raise HTTPException(404, "Workspace not found")
    if data.get("revision") != card_digest(normalize_brand(org.brand_kit)):
        raise HTTPException(409, "The workspace brand changed in another session. Load it again before saving.")
    org.brand_kit = kit
    db.commit()
    return {"brand_kit": kit, "revision": card_digest(kit)}


def _editorial_context(data):
    from app.services.brand_kit import editorial_context
    try:
        return editorial_context(data.get("audience") or "english_muslims", data.get("purpose") or "reminder")
    except (ValueError, TypeError):
        raise HTTPException(422, "Choose a supported audience and purpose") from None


@router.post("/generate-card-message", dependencies=[Depends(require_user)])
def studio_generate_card_message(data: dict, db: Session = Depends(get_db),
                                 org_id: int = Depends(get_current_org_id), user: User = Depends(require_user)):
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
        source_payload = resolve_selected_source(db, org_id, source_type, source_payload, user.id)
        context = _editorial_context(data)
        custom = (data.get("custom_payload") or {}).get("custom_prompt") or ""
        card_msg = build_quote_card_message(source_type, source_payload, tone, intent,
            custom_prompt=context + "\n" + str(custom)[:2000], include_reflection=data.get("include_reflection", True) is True)
        from app.services.source_display import arabic_display_options
        return {"card_message": card_msg, "source_metadata": source_payload,
                "arabic_display_options": arabic_display_options(card_msg) if source_type == "hadith" else []}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STUDIO] Card Message generation failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/generate-caption", dependencies=[Depends(require_user)])
def studio_generate_caption(data: dict, db: Session = Depends(get_db),
                            org_id: int = Depends(get_current_org_id), user: User = Depends(require_user)):
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
    context = _editorial_context(data)
    try:
        source_payload = resolve_selected_source(db, org_id, source_type, source_payload, user.id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    # ── Hadith: grounded caption from exact metadata ───────────────────────────
    if source_type == "hadith":
        try:
            from app.services.hadith_caption_service import generate_hadith_caption
            caption = generate_hadith_caption(source_payload, tone=tone, intent=intention, editorial_context=context)
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
            caption = generate_ai_caption_from_quran(source_payload, style=tone, editorial_context=context)
            logger.info(f"[STUDIO] Quran caption grounded directly to: {source_payload.get('reference')}")
            return {"caption": caption}
        except Exception as e:
            logger.error(f"[STUDIO] Quran grounded caption failed: {e}")
            raise HTTPException(status_code=422, detail="Could not generate a caption for the selected verse")

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


@router.post("/generate-visual", dependencies=[Depends(require_user)])
def studio_generate_visual(data: dict, org_id: int = Depends(get_current_org_id), db: Session = Depends(get_db)):
    """
    Phase 3: Route explicitly into Visual Service Facade for all Studio image generation.
    """
    from app.services.brand_kit import normalize_brand, workspace_brand
    try:
        brand = normalize_brand(data["brand_kit"]) if "brand_kit" in data else workspace_brand(db, org_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
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
        layout=data.get("layout", "english_first"),
        background_token=data.get("background_token"),
        owner_id=org_id,
        post_format=data.get("post_format", "feed_4_5"),
        brand_kit=brand,
    )

    res = generate_visual(req)
    if not res.ok:
        return JSONResponse(status_code=res.error_status, content={"error": res.error})

    return {
        "image_url": res.url,
        "mode_used": req.mode or "preset",
        "style_used": req.style,
        "prompt_applied": bool(req.custom_prompt),
        "visual_design": res.design
    }


@router.post("/create-post")
def studio_create_post(data: dict, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id),
                       user: User | None = Depends(get_current_user)):
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
    account = require_account(db, org_id, ig_account_id, active=True)
    ig_account_id = account.id

    source_type = data.get("source_type", "manual")
    source_reference = data.get("source_reference")
    source_metadata = data.get("source_metadata")
    source_text = data.get("source_text") or data.get("topic") or ""
    if source_type in {"quran", "hadith"}:
        try:
            source_metadata = resolve_selected_source(db, org_id, source_type, source_metadata or {}, user.id if user else None)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        if source_reference and source_reference != source_metadata["reference"]:
            raise HTTPException(status_code=422, detail="Post reference does not match the selected source")
        source_reference = source_metadata["reference"]
        source_text = source_metadata["translation_text"]

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

    if source_type in {"quran", "hadith"}:
        from app.services.source_grounding import validate_source_card
        try:
            validate_source_card(card_msg, source_metadata, source_type)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))

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
    if raw_scheduled_at and scheduled_time is None:
        raise HTTPException(status_code=422, detail="Invalid scheduled_at format. Use ISO 8601.")

    # Determine final status
    if scheduled_time:
        final_status = "scheduled"
    else:
        final_status = data.get("status", "drafted")
    if final_status not in {"drafted", "needs_review", "scheduled"}:
        raise HTTPException(status_code=422, detail="Invalid initial post status")

    from app.services.media_sequence import validate_manifest
    design = data.get("visual_design") or {}
    if not isinstance(design, dict):
        raise HTTPException(status_code=422, detail="Invalid visual design")
    manifest = design.get("media_manifest")
    if manifest is not None:
        try:
            validate_manifest(manifest, card_msg, org_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        if data.get("media_url") != manifest["pages"][0]["url"]:
            raise HTTPException(status_code=422, detail="The preview and sequence cover do not match")
        if design.get("brand_kit") != manifest.get("brand_kit"):
            raise HTTPException(422, "Apply the latest brand changes before saving")
        if manifest.get("brand_kit") is not None and "brand_kit" in data:
            from app.services.brand_kit import normalize_brand
            try:
                if normalize_brand(data["brand_kit"]) != manifest["brand_kit"]:
                    raise ValueError("Apply the latest brand changes before saving")
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
    elif data.get("post_format") in {"carousel_4_5", "story_9_16"}:
        raise HTTPException(status_code=422, detail="Generate a complete sequence before saving this format")

    # A stable editor key recovers an accepted save after a lost HTTP response.
    # The transaction lock closes the duplicate-create race in PostgreSQL.
    draft_key = data.get("draft_key")
    existing = None
    if draft_key:
        from uuid import UUID
        from sqlalchemy import text
        try:
            draft_key = str(UUID(draft_key))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=422, detail="Invalid draft recovery key") from None
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"studio:{org_id}:{draft_key}"})
        existing = db.query(Post).filter(Post.org_id == org_id, Post.flags["draft_key"].as_string() == draft_key).first()
    if data.get("post_id"):
        existing = get_mutable_post(db, data["post_id"], org_id)
    elif existing:
        existing = get_mutable_post(db, existing.id, org_id)

    values = dict(
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
        post_format=manifest["format"] if manifest else data.get("post_format"),
        visual_style=data.get("visual_style"),
        flags={**(existing.flags or {} if existing else {}), "visual_design": design,
               **({"media_manifest": manifest} if manifest else {}),
               **({"draft_key": draft_key} if draft_key else {})},
        # Intelligence fields
        intent_type=data.get("purpose") or data.get("intent_type"),
        target_audience=data.get("audience"),
        message_hint=data.get("message_hint"),
        source_foundation=source_foundation,
    )
    post = existing or Post()
    # The editor can replace a draft's complete visual, never a partially sent Story.
    values["flags"].pop("publication", None)
    if manifest is None:
        values["flags"].pop("media_manifest", None)
    from app.services.media_sequence import card_digest
    values["flags"]["reviewed_manifest"] = card_digest(manifest) if manifest and data.get("reviewed") is True else None
    for field, value in values.items():
        setattr(post, field, value)

    if final_status == "scheduled":
        if not scheduled_time:
            raise HTTPException(status_code=422, detail="A scheduled time is required")
        prepare_scheduled_post(db, post)
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

    post = get_mutable_post(db, post_id, org_id)

    require_account(db, org_id, post.ig_account_id, active=True)
    if post.status in {"published", "publishing", "publish_unknown"}:
        raise HTTPException(status_code=409, detail="This post cannot be scheduled again")
    scheduled_time = _parse_scheduled_at(raw_scheduled_at)
    if not scheduled_time:
        raise HTTPException(status_code=400, detail="Invalid scheduled_at format. Use ISO 8601.")

    prepare_scheduled_post(db, post)
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
