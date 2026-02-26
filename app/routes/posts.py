import os, shutil
from datetime import datetime, timezone, timedelta
import pytz
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..db import get_db
from ..config import settings
from ..models import Post, IGAccount, TopicAutomation
from ..schemas import PostOut, ApproveIn, GenerateOut, PostUpdate
from ..services.llm import generate_draft, generate_ai_image
import requests
from ..services.policy import keyword_flags
from ..services.publisher import publish_to_instagram
from ..services.automation_runner import resolve_media_url
from ..security.rbac import get_current_org_id
from ..logging_setup import log_event
router = APIRouter(prefix="/posts", tags=["posts"])
def _utcnow():
    return datetime.now(timezone.utc)
def _ensure_uploads_dir():
    os.makedirs(settings.uploads_dir, exist_ok=True)
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
    org_id: int = Depends(get_current_org_id),
):
    print(f"DEBUG: Intake attempt - Account={ig_account_id}, AI={use_ai_image}, File={image.filename if image else 'None'}")
    _ensure_uploads_dir()
    acc = db.query(IGAccount).filter(IGAccount.id == ig_account_id, IGAccount.org_id == org_id).first()
    if not acc:
        raise HTTPException(status_code=403, detail="IG Account not found or not in your workspace")
    
    if not acc.access_token or not acc.ig_user_id:
         raise HTTPException(status_code=400, detail="Incomplete IG Account connection. Please reconnect your account.")
    public_url = None
    # 1. Handle AI Generation
    if use_ai_image:
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
                public_url = f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
            else:
                raise Exception(f"Failed to download AI image, status: {res.status_code}")
        except Exception as e:
            print(f"FAILED AI IMAGE SAVE: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save AI generated image: {str(e)}")
    # 2. Handle Manual Upload
    elif image:
        if image.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
            raise HTTPException(status_code=400, detail=f"File type '{image.content_type}' is not supported. Use PNG, JPG, or WEBP.")
        filename = f"{int(_utcnow().timestamp())}_{image.filename}"
        local_path = os.path.join(settings.uploads_dir, filename)
        try:
            with open(local_path, "wb") as f:
                shutil.copyfileobj(image.file, f)
            public_url = f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
        except Exception as e:
            print(f"FAILED FILE SAVE: {e}")
            raise HTTPException(status_code=500, detail="Critical error: Could not save uploaded file. Check disk space/permissions.")
    
    else:
        # Allow text-only initial intake
        print("[INTAKE] No image provided. Creating text-only draft.")
        pass
    post = Post(
        org_id=org_id,
        ig_account_id=ig_account_id,
        status="drafted",
        source_type=source_type,
        source_text=source_text,
        media_url=public_url,
        flags={},
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    log_event("post_intake", post_id=post.id, org_id=org_id, ig_account_id=ig_account_id, ai_generated=use_ai_image)
    return post
@router.post("/{post_id}/generate", response_model=GenerateOut)
def generate_for_post(
    post_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    draft = generate_draft(post.source_text or "")
    flags = keyword_flags((post.source_text or "") + "\n" + (draft.get("caption") or ""))
    post.caption = draft["caption"]
    post.hashtags = draft["hashtags"]
    post.alt_text = draft["alt_text"]
    post.flags = flags
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
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(post, k, v)
    
    db.commit()
    db.refresh(post)
    return post

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Optional logic: delete associated media file if local, etc.
    db.delete(post)
    db.commit()
    return None

@router.post("/{post_id}/regenerate-caption", response_model=PostOut)
def regenerate_caption(
    post_id: int,
    instructions: str | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    prompt = post.source_text or ""
    if instructions:
        prompt += f"\n\nAdditional Instructions: {instructions}"
    
    draft = generate_draft(prompt)
    post.caption = draft["caption"]
    post.hashtags = draft["hashtags"]
    post.alt_text = draft["alt_text"]
    
    # Re-run policy check
    flags = keyword_flags(post.caption)
    post.flags = flags
    if flags.get("needs_review"):
        post.status = "needs_review"
    
    db.commit()
    db.refresh(post)
    return post
@router.post("/{post_id}/regenerate-image", response_model=PostOut)
def regenerate_image(
    post_id: int,
    image_mode: str | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
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
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    _ensure_uploads_dir()
    filename = f"manual_{int(_utcnow().timestamp())}_{image.filename}"
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
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    flags = post.flags or {}
    if flags.get("needs_review") and not payload.approve_anyway:
        raise HTTPException(
            status_code=400,
            detail="Flagged. Set approve_anyway=true or edit first."
        )
    if not post.caption or not post.media_url:
        post.status = "failed"
        post.flags = {**(post.flags or {}), "reason": "missing_content"}
        db.commit()
        raise HTTPException(status_code=422, detail="Approval denied: Missing caption or visual assets.")
    # Set scheduled time
    if payload.scheduled_time:
        post.scheduled_time = payload.scheduled_time
    else:
        # Auto-calculate based on account's post time
        acc = db.get(IGAccount, post.ig_account_id)
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
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if not post.caption or not post.media_url:
        post.status = "failed"
        post.flags = {**(post.flags or {}), "reason": "missing_media_at_publish"}
        db.commit()
        raise HTTPException(status_code=422, detail="Publishing impossible: Visual asset is missing from the record.")
    acc = db.get(IGAccount, post.ig_account_id)
    caption_full = post.caption
    if post.hashtags:
        caption_full += "\n\n" + " ".join(post.hashtags)
    log_event("post_publish_start", post_id=post.id)
    res = publish_to_instagram(
        caption=caption_full, 
        media_url=post.media_url,
        ig_user_id=acc.ig_user_id,
        access_token=acc.access_token
    )
    
    if not res.get("ok"):
        post.status = "failed"
        post.flags = {**(post.flags or {}), "publish_error": res.get("error")}
        db.commit()
        log_event("post_publish_fail", post_id=post.id, error=res.get("error"))
        raise HTTPException(status_code=502, detail=f"Publish failed: {res.get('error')}")
    post.status = "published"
    post.published_time = _utcnow()
    db.commit()
    db.refresh(post)
    log_event("post_publish_success", post_id=post.id, remote_id=res.get("id"))
    return post
@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.media_url and "uploads" in post.media_url:
        try:
            filename = post.media_url.split("/")[-1]
            local_path = os.path.join(settings.uploads_dir, filename)
            if os.path.exists(local_path):
                os.remove(local_path)
        except Exception as e:
            print(f"Error deleting file for post {post_id}: {e}")
    db.delete(post)
    db.commit()
    return {"ok": True, "message": f"Post {post_id} deleted"}
