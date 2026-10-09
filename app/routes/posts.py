# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from app.services.usage_limits import UsageLimitError
import os, shutil
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import pytz
from pydantic import BaseModel
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..db import get_db
from ..config import settings
from ..models import Post, IGAccount, TopicAutomation, MediaAsset, ContentItem, User
from ..services.image_renderer import render_quote_card
from ..schemas import PostOut, ApproveIn, GenerateOut, PostUpdate
from ..services.llm import generate_draft, generate_ai_image
import requests
from ..services.policy import keyword_flags
from ..services.post_service import publish_post as publish_saved_post, get_mutable_post, prepare_scheduled_post
from ..services.source_grounding import resolve_selected_source, resolve_saved_source, saved_source_type, validate_source_card, validate_source_edit
from ..services.source_caption import compose_source_caption
from ..services.automation_runner import resolve_media_url
from ..security.rbac import get_current_org_id
from ..security.ownership import require_account, require_content_item, require_media
from ..security.auth import get_current_user
from ..logging_setup import log_event
router = APIRouter(prefix="/posts", tags=["posts"])
def _utcnow():
    return datetime.now(timezone.utc)
def _ensure_uploads_dir():
    os.makedirs(settings.uploads_dir, exist_ok=True)

def _source_caption(db, post, user, tone="calm"):
    if saved_source_type(post) not in {"quran", "hadith"}:
        return None
    try:
        source = resolve_saved_source(db, post, user.id if user else None)
        return compose_source_caption(source, saved_source_type(post), tone)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
def get_next_daily_time(daily_post_time: str, account_timezone: str) -> datetime:
    """Calculate the next occurrence of daily_post_time in the given timezone."""
    tz = pytz.timezone(account_timezone)
    now_tz = datetime.now(tz)
    
    hour, minute = map(int, daily_post_time.split(":"))
    target = now_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    if target <= now_tz:
        target += timedelta(days=1)
    
    # Return as UTC
    return target.astimezone(pytz.utc)
@router.post("/intake", response_model=PostOut)
def intake_post(
    db: Session = Depends(get_db),
    source_text: str = Form(""),
    source_type: str = Form("form"),
    ig_account_id: int = Form(...),
    image: UploadFile | None = File(None),
    use_ai_image: bool = Form(False),
    visual_mode: str = Form("upload"),
    visual_prompt: str | None = Form(None),
    library_item_id: str | None = Form(None), # Changed to str to handle empty string
    topic: str | None = Form(None),
    post_type: str | None = Form(None),
    source_reference: str | None = Form(None),
    
    # Intelligence Fields
    intent_type: str | None = Form(None),
    target_audience: str | None = Form(None),
    source_foundation: str | None = Form(None),
    message_hint: str | None = Form(None),
    emotion: str | None = Form(None),
    depth: str | None = Form(None),
    post_format: str | None = Form(None),
    visual_style: str | None = Form(None),
    hook_style: str | None = Form(None),
    strictness_mode: str = Form("balanced"),
    card_message: str | None = Form(None),
    caption_message: str | None = Form(None),

    org_id: int = Depends(get_current_org_id),
    user: User | None = Depends(get_current_user),
):
    # Parse library_item_id
    lib_id = None
    if library_item_id and library_item_id.strip():
        try:
            lib_id = int(library_item_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid library item ID")

    # Parse structured messages
    import json
    parsed_card_msg = None
    if card_message:
        try:
            parsed_card_msg = json.loads(card_message)
        except:
            pass
    
    parsed_caption_msg = None
    if caption_message:
        try:
            parsed_caption_msg = json.loads(caption_message)
        except:
            pass

    print(f"DEBUG: Intake attempt - Account={ig_account_id}, AI={use_ai_image}, File={image.filename if image else 'None'}")
    acc = require_account(db, org_id, ig_account_id, active=True)
    asset = None
    if visual_mode == "media_library":
        if lib_id is None:
            raise HTTPException(status_code=422, detail="Select a media asset")
        asset = require_media(db, org_id, lib_id)
    elif lib_id is not None:
        require_content_item(db, org_id, lib_id, user_id=user.id if user else None)
    source_metadata = None
    if source_type in {"quran", "hadith"} or source_foundation in {"quran", "hadith"}:
        kind = source_type if source_type in {"quran", "hadith"} else source_foundation
        try:
            source_metadata = resolve_selected_source(db, org_id, kind, {"reference": source_reference}, user.id if user else None)
            validate_source_card(parsed_card_msg, source_metadata, kind)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        source_text = source_metadata["translation_text"]
        source_reference = source_metadata["reference"]
        source_foundation = kind
    _ensure_uploads_dir()
    
    if not acc.access_token or not acc.ig_user_id:
         raise HTTPException(status_code=400, detail="Incomplete IG Account connection. Please reconnect your account.")
    public_url = None
    # 1. Handle AI Generation
    if use_ai_image or visual_mode == "ai_background":
        if not source_text:
            raise HTTPException(status_code=400, detail="Source text/Directives required for AI image generation")
        
        print(f"[INTAKE] Generating AI image for: {source_text[:50]}...")
        ai_url = generate_ai_image(source_text)
        if not ai_url:
            raise HTTPException(status_code=500, detail="AI Image generation failed. Please try again or upload a file.")
        
        # Download and save locally
        filename = f"ai_intake_{int(_utcnow().timestamp())}.jpg"
        local_path = os.path.join(settings.uploads_dir, filename)
        
        try:
            res = requests.get(ai_url, timeout=30)
            if res.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(res.content)
                from app.config import build_public_media_url
                public_url = build_public_media_url(filename, local_path=local_path)
                print(f"[INTAKE] AI image saved. media_url={public_url}")
            else:
                raise Exception(f"Failed to download AI image, status: {res.status_code}")
        except Exception as e:
            print(f"FAILED AI IMAGE SAVE: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save AI generated image: {str(e)}")

    # 2. Handle Manual Upload
    elif visual_mode == "upload" and image and image.filename:
        if image.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
            raise HTTPException(status_code=400, detail=f"File type '{image.content_type}' is not supported. Use PNG, JPG, or WEBP.")
        
        extension = {"image/png": ".png", "image/webp": ".webp"}.get(image.content_type, ".jpg")
        filename = f"upload_{uuid4().hex}{extension}"
        local_path = os.path.join(settings.uploads_dir, filename)
        try:
            with open(local_path, "wb") as f:
                shutil.copyfileobj(image.file, f)
            from app.config import build_public_media_url
            public_url = build_public_media_url(filename, local_path=local_path)
            print(f"[INTAKE] Upload saved. media_url={public_url}")
        except Exception as e:
            print(f"FAILED FILE SAVE: {e}")
            raise HTTPException(status_code=500, detail="Critical error: Could not save uploaded file. Check disk space/permissions.")
    
    # 3. Handle Media
    elif visual_mode == "media_library" and lib_id:
        public_url = asset.url

    else:
        # Allow text-only initial intake or fallback if nothing else matched
        print("[INTAKE] No specific media resolve path hit.")
        pass
    post = Post(
        org_id=org_id,
        ig_account_id=ig_account_id,
        status="drafted",
        source_type=source_type,
        source_text=source_text,
        topic=topic,
        post_type=post_type,
        source_reference=source_reference,
        source_metadata=source_metadata,
        media_url=public_url,
        visual_mode=visual_mode,
        visual_prompt=visual_prompt,
        library_item_id=lib_id if visual_mode != "media_library" else None,
        media_asset_id=asset.id if asset else None,
        
        card_message=parsed_card_msg,
        caption_message=parsed_caption_msg,

        intent_type=intent_type,
        target_audience=target_audience,
        source_foundation=source_foundation or ("quran" if source_type == "quran" else None),
        message_hint=message_hint,
        emotion=emotion,
        depth=depth,
        post_format=post_format,
        visual_style=visual_style,
        hook_style=hook_style,
        strictness_mode=strictness_mode,

        flags={},
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    log_event("post_intake", post_id=post.id, org_id=org_id, ig_account_id=ig_account_id, ai_generated=use_ai_image)
    return post

@router.post("/preview_render")
async def preview_render(
    visual_mode: str = Form(...),
    source_text: str = Form(""),
    visual_prompt: str | None = Form(None),
    library_item_id: str | None = Form(None), # Changed to str
    reference: str | None = Form(""),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    # Parse library_item_id
    lib_id = None
    if library_item_id and library_item_id.strip():
        try:
            lib_id = int(library_item_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid library item ID")

    """
    Generates a temporary quote card preview without creating a database entry.
    """
    _ensure_uploads_dir()
    background_local_path = None
    
    # 1. Resolve Background
    if visual_mode == "upload" and image:
        temp_fn = f"prev_up_{int(_utcnow().timestamp())}.jpg"
        temp_path = os.path.join(settings.uploads_dir, temp_fn)
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        background_local_path = temp_path
    
    elif visual_mode == "ai_background":
        prompt = visual_prompt or source_text
        if not prompt:
            raise HTTPException(status_code=400, detail="AI prompt or source text required")
        
        ai_url = generate_ai_image(prompt)
        if ai_url:
            temp_fn = f"prev_ai_{int(_utcnow().timestamp())}.jpg"
            temp_path = os.path.join(settings.uploads_dir, temp_fn)
            resp = requests.get(ai_url, timeout=30)
            if resp.status_code == 200:
                with open(temp_path, "wb") as f:
                    f.write(resp.content)
                background_local_path = temp_path
    
    elif visual_mode == "media_library":
        # For now, if no specific ID, we try to find the latest media asset or a default
        asset = None
        if lib_id:
            asset = require_media(db, org_id, lib_id)
        
        if not asset:
            asset = db.query(MediaAsset).filter(MediaAsset.org_id == org_id).order_by(MediaAsset.created_at.desc()).first()
            
        if asset and asset.storage_path and os.path.exists(asset.storage_path):
            background_local_path = asset.storage_path
        elif asset and asset.url.startswith("http"):
            # Download it
            temp_fn = f"prev_vault_{int(_utcnow().timestamp())}.jpg"
            temp_path = os.path.join(settings.uploads_dir, temp_fn)
            resp = requests.get(asset.url, timeout=30)
            if resp.status_code == 200:
                with open(temp_path, "wb") as f:
                    f.write(resp.content)
                background_local_path = temp_path

    # Fallback to a placeholder if still nothing
    if not background_local_path:
        # Create a solid black background if nothing else works
        from PIL import Image
        temp_fn = "placeholder_bg.jpg"
        background_local_path = os.path.join(settings.uploads_dir, temp_fn)
        if not os.path.exists(background_local_path):
            img = Image.new('RGB', (1080, 1080), color=(20, 20, 20))
            img.save(background_local_path)

    # 2. Render Quote Card
    try:
        render_url = render_quote_card(
            background_local_path=background_local_path,
            quote=source_text or "Preview Quote Text",
            reference=reference or "",
            output_dir=settings.uploads_dir
        )
        return {"preview_url": render_url}
    except UsageLimitError:
        raise
    except Exception as e:
        print(f"PREVIEW RENDER FAILED: {e}")
        raise HTTPException(status_code=500, detail=f"Rendering failed: {str(e)}")
@router.post("/{post_id}/generate", response_model=GenerateOut)
def generate_for_post(
    post_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
    user: User | None = Depends(get_current_user),
):
    post = get_mutable_post(db, post_id, org_id)
    grounded_caption = _source_caption(db, post, user)
    draft = {"caption": grounded_caption, "hashtags": post.hashtags or [], "alt_text": post.alt_text or ""} if grounded_caption is not None else generate_draft(
        source_text=post.source_text or "",
        intent=post.intent_type,
        audience=post.target_audience,
        source_foundation=post.source_foundation,
        emotion=post.emotion,
        depth=post.depth,
        post_format=post.post_format,
        visual_style=post.visual_style,
        hook_style=post.hook_style,
        strictness=post.strictness_mode or "balanced"
    )
    
    flags = keyword_flags((post.source_text or "") + "\n" + (draft.get("caption") or ""))
    post.caption = draft["caption"]
    post.hashtags = draft["hashtags"]
    post.alt_text = draft["alt_text"]
    post.caption_message = {"caption": post.caption}
    post.flags = {**(post.flags or {}), **flags}
    post.status = "needs_review" if flags.get("needs_review") else "drafted"
    db.commit()
    log_event("post_generate", post_id=post.id, status=post.status)
    return {
        "caption": post.caption,
        "hashtags": post.hashtags or [],
        "alt_text": post.alt_text or "",
        "flags": post.flags or {},
        "status": post.status,
    }
@router.get("", response_model=list[PostOut])
def list_posts(
    status: str | None = None,
    ig_account_id: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    stmt = select(Post).where(Post.org_id == org_id).order_by(Post.created_at.desc())
    if status:
        stmt = stmt.where(Post.status == status)
    if ig_account_id:
        stmt = stmt.where(Post.ig_account_id == ig_account_id)
    limit = max(1, min(limit, 200))
    stmt = stmt.limit(limit)
    return db.execute(stmt).scalars().all()
@router.get("/stats")
def post_stats(
    ig_account_id: int | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    stmt = select(Post.status, func.count(Post.id)).where(Post.org_id == org_id).group_by(Post.status)
    if ig_account_id:
        stmt = stmt.where(Post.ig_account_id == ig_account_id)
        
    rows = db.execute(stmt).all()
    
    # Count Active Automations
    auto_stmt = select(func.count(TopicAutomation.id)).where(TopicAutomation.org_id == org_id)
    if ig_account_id:
        auto_stmt = auto_stmt.where(TopicAutomation.ig_account_id == ig_account_id)
    
    auto_count = db.execute(auto_stmt).scalar() or 0
    
    return {
        "counts": {status: count for status, count in rows},
        "auto_count": auto_count
    }
@router.get("/calendar", response_model=list[PostOut])
def get_calendar_posts(
    start_date: str = Query(..., alias="from"),
    end_date: str = Query(..., alias="to"),
    ig_account_id: int | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    from datetime import datetime
    try:
        dt_from = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        dt_to = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601")
    stmt = select(Post).where(
        Post.org_id == org_id,
        Post.scheduled_time >= dt_from,
        Post.scheduled_time <= dt_to
    )
    if ig_account_id:
        stmt = stmt.where(Post.ig_account_id == ig_account_id)
        
    return db.execute(stmt).scalars().all()
@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post
@router.patch("/{post_id}", response_model=PostOut)
def update_post(
    post_id: int,
    payload: PostUpdate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
    user: User | None = Depends(get_current_user),
):
    post = get_mutable_post(db, post_id, org_id)
    
    data = payload.dict(exclude_unset=True)
    if (post.flags or {}).get("media_manifest") and any(key in data for key in ("media_url", "media_asset_id", "post_format", "card_message")):
        raise HTTPException(status_code=422, detail="Edit the complete sequence in Studio so its source and pages stay together")
    try:
        validate_source_edit(post, data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if "status" in data and data["status"] not in {"drafted", "needs_review", "scheduled", "approved"}:
        raise HTTPException(status_code=422, detail="This status is controlled by the publishing service")
    if "flags" in data:
        incoming = dict(data["flags"] or {})
        protected = {"publication", "media_manifest", "reviewed_manifest", "visual_design", "draft_key", "relevance_check", "automation_error", "rotation_topic", "rotation_style_id", "rotation_pillar", "rotation_used_at", "scheduled_occurrence"}
        for key in protected:
            incoming.pop(key, None)
            if key in (post.flags or {}):
                incoming[key] = post.flags[key]
        data["flags"] = incoming
    if "caption" in data:
        data["caption_message"] = {"caption": data["caption"] or ""}
    elif "caption_message" in data:
        message = data["caption_message"] or {}
        caption = message.get("caption")
        if caption is None:
            parts = [message.get(key) for key in ("hook", "body", "cta") if message.get(key)]
            if any(not isinstance(part, str) for part in parts):
                raise HTTPException(status_code=422, detail="Caption fields must contain text")
            caption = "\n\n".join(parts)
        if not isinstance(caption, str):
            raise HTTPException(status_code=422, detail="Caption must contain text")
        data["caption"] = caption
    if data.get("media_asset_id") is not None:
        asset = require_media(db, org_id, data["media_asset_id"])
        data["media_url"] = asset.url
    if data.get("library_item_id") is not None:
        require_content_item(db, org_id, data["library_item_id"], user_id=user.id if user else None)
    for k, v in data.items():
        setattr(post, k, v)
    if post.status in {"scheduled", "approved"}:
        try:
            prepare_scheduled_post(db, post)
            if post.status == "scheduled" and not post.scheduled_time:
                raise HTTPException(status_code=422, detail="A scheduled time is required")
        except HTTPException:
            db.rollback()
            raise
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/regenerate-caption", response_model=PostOut)
def regenerate_caption(
    post_id: int,
    instructions: str | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
    user: User | None = Depends(get_current_user),
):
    post = get_mutable_post(db, post_id, org_id)
    
    prompt = post.source_text or ""
    if instructions:
        prompt += f"\n\nAdditional Instructions: {instructions}"
    
    grounded_caption = _source_caption(db, post, user, instructions or "calm")
    draft = {"caption": grounded_caption, "hashtags": post.hashtags or [], "alt_text": post.alt_text or ""} if grounded_caption is not None else generate_draft(prompt)
    post.caption = draft["caption"]
    post.caption_message = {"caption": post.caption}
    post.hashtags = draft["hashtags"]
    post.alt_text = draft["alt_text"]
    
    # Re-run policy check
    flags = keyword_flags(post.caption)
    post.flags = {**(post.flags or {}), **flags}
    if flags.get("needs_review"):
        post.status = "needs_review"
    
    db.commit()
    db.refresh(post)
    return post

class RefineBody(BaseModel):
    style: str
    current_caption: str

@router.post("/{post_id}/refine")
def refine_post(
    post_id: int,
    payload: RefineBody,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
    user: User | None = Depends(get_current_user),
):
    post = get_mutable_post(db, post_id, org_id)
    if payload.style in {"ayah", "hadith"}:
        raise HTTPException(status_code=422, detail="Choose a verified Qur'an or Hadith source in Studio before adding it.")
    grounded_caption = _source_caption(db, post, user, payload.style)
    if grounded_caption is not None:
        return {"caption": grounded_caption}
    from app.services.llm import refine_caption
    try:
        refined = refine_caption(payload.current_caption, payload.style)
        return {"caption": refined}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except UsageLimitError:
        raise
    except Exception as e:
        print(f"❌ [REFINE_FAIL] {e}")
        raise HTTPException(status_code=500, detail=f"Refinement failed: {str(e)}")
@router.post("/{post_id}/regenerate-image", response_model=PostOut)
def regenerate_image(
    post_id: int,
    image_mode: str | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = get_mutable_post(db, post_id, org_id)
    
    if (post.flags or {}).get("media_manifest"):
        raise HTTPException(status_code=422, detail="Rebuild the complete sequence in Studio; individual pages cannot be replaced")

    mode = image_mode or "ai_nature_photo"
    
    # Use the new robust resolver
    from app.services.automation_runner import resolve_media_url
    new_url = resolve_media_url(
        db=db,
        org_id=post.org_id,
        ig_account_id=post.ig_account_id,
        image_mode=mode,
        topic=post.source_text or "general"
    )
    
    if new_url:
        post.media_url = new_url
    
    db.commit()
    db.refresh(post)
    return post
@router.post("/{post_id}/attach-media", response_model=PostOut)
def attach_media(
    post_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = get_mutable_post(db, post_id, org_id)
    
    if (post.flags or {}).get("media_manifest"):
        raise HTTPException(status_code=422, detail="Rebuild the complete sequence in Studio; individual pages cannot be replaced")

    _ensure_uploads_dir()
    if image.content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise HTTPException(status_code=400, detail="Use a PNG, JPG, or WEBP image")
    extension = {"image/png": ".png", "image/webp": ".webp"}.get(image.content_type, ".jpg")
    filename = f"manual_{uuid4().hex}{extension}"
    local_path = os.path.join(settings.uploads_dir, filename)
    with open(local_path, "wb") as f:
        shutil.copyfileobj(image.file, f)
    public_url = f"{settings.public_base_url}/uploads/{filename}"
    post.media_url = public_url
    
    db.commit()
    db.refresh(post)
    return post
@router.post("/{post_id}/approve", response_model=PostOut)
def approve_post(
    post_id: int, 
    payload: ApproveIn, 
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = get_mutable_post(db, post_id, org_id)
    acc = require_account(db, org_id, post.ig_account_id, active=True)
    flags = post.flags or {}
    if flags.get("needs_review") and not payload.approve_anyway:
        raise HTTPException(
            status_code=400,
            detail="Flagged. Set approve_anyway=true or edit first."
        )
    if (post.post_format != "story_9_16" and not post.caption) or not post.media_url:
        post.status = "failed"
        post.flags = {**(post.flags or {}), "reason": "missing_content"}
        db.commit()
        raise HTTPException(status_code=422, detail="Approval denied: Missing caption or visual assets.")
    prepare_scheduled_post(db, post)
    # Set scheduled time
    if payload.scheduled_time:
        post.scheduled_time = payload.scheduled_time
    else:
        # Auto-calculate based on account's post time
        post.scheduled_time = get_next_daily_time(acc.daily_post_time, acc.timezone)
    post.status = "scheduled"
    db.commit()
    db.refresh(post)
    log_event("post_approve", post_id=post.id, status=post.status)
    return post
@router.post("/{post_id}/publish", response_model=PostOut)
def publish_post(
    post_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    result = publish_saved_post(db, post_id, org_id)
    if not result.ok:
        raise HTTPException(status_code=result.status_code, detail=result.error)
    return result.post

@router.get("/{post_id}/preflight-check")
def check_media_integrity(
    post_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Checks if the media asset physically exists on the current disk."""
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if not post.media_url:
        return {"stale": True, "reason": "missing_url"}

    # Use the existing publisher preflight logic but in a 'dry-run' mode
    from app.services.publisher import publish_to_instagram
    from app.config import settings
    import os

    if "/uploads/" in post.media_url:
        local_filename = post.media_url.split("/uploads/")[-1]
        local_path = os.path.join(settings.uploads_dir, local_filename)
        if not os.path.exists(local_path):
             return {"stale": True, "reason": "file_not_on_disk"}
    
    return {"stale": False, "url": post.media_url}


@router.post("/{post_id}/reconcile-publication", response_model=PostOut)
def reconcile_post_publication(post_id: int, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    from app.services.post_service import reconcile_publication
    result = reconcile_publication(db, post_id, org_id)
    if not result.ok:
        raise HTTPException(status_code=result.status_code, detail=result.error)
    return result.post

@router.post("/{post_id}/recover")
def recover_post_media(
    post_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Triggers visual regeneration if the asset is stale."""
    post = get_mutable_post(db, post_id, org_id)
    
    if (post.flags or {}).get("media_manifest"):
        raise HTTPException(status_code=422, detail="Rebuild the complete sequence in Studio; individual pages cannot be replaced")

    from app.services.automation_runner import recover_stale_media
    success = recover_stale_media(post, db)
    
    if not success:
        raise HTTPException(
            status_code=422, 
            detail="This post was created before persistent media recovery was added. Please regenerate the visual, then share again."
        )
    
    return {"ok": True, "new_media_url": post.media_url}

@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).populate_existing().with_for_update().first()
    if not post:
        # Debug helper: check if it exists at all to differentiate between "missing" and "permission denied"
        exists = db.query(Post).filter(Post.id == post_id).first()
        if exists:
            print(f"!!! [DELETE FAIL] Post {post_id} found but Org ID mismatch. Post Org={exists.org_id}, User Org={org_id}")
            raise HTTPException(status_code=403, detail="Forbidden: This post belongs to a different organization.")
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.status in {"publishing", "publish_unknown", "publish_partial"}:
        raise HTTPException(status_code=409, detail="Reconcile the publishing attempt before deleting this post")

    try:
        # 1. Manual Cleanup of linked records that might block deletion
        from app.models import ContentUsage
        db.query(ContentUsage).filter(ContentUsage.post_id == post.id).delete()
        
        # 2. Media File Cleanup
        if post.media_url and "uploads" in post.media_url:
            try:
                filename = post.media_url.split("/")[-1]
                local_path = os.path.join(settings.uploads_dir, filename)
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception as e:
                print(f"Error deleting file for post {post_id}: {e}")
        
        # 3. Final Deletion
        db.delete(post)
        db.commit()
        return {"ok": True, "message": f"Post {post_id} deleted"}
    except Exception as e:
        db.rollback()
        print(f"!!! [CRITICAL] Delete failed for post {post_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error during deletion: {str(e)}")


@router.get("/{post_id}/export")
def export_saved_post(post_id: int, db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    from fastapi.responses import StreamingResponse
    from app.services.media_sequence import export_post
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    try:
        archive = export_post(post)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return StreamingResponse(archive, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="sabeel-post-{post_id}.zip"', "Cache-Control": "no-store"})
