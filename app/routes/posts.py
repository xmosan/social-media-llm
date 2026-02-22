import os, shutil
from datetime import datetime, timezone, timedelta
import pytz
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..db import get_db
from ..config import settings
from ..models import Post, IGAccount
from ..schemas import PostOut, ApproveIn, GenerateOut, PostUpdate
from ..services.llm import generate_draft
from ..services.policy import keyword_flags
from ..services.publisher import publish_to_instagram
from ..services.automation_runner import resolve_media_url
from ..security import require_api_key

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
    image: UploadFile = File(...),
    org_id: int = Depends(require_api_key),
):
    print(f"DEBUG: Intake attempt - Account={ig_account_id}, File={image.filename}, Type={image.content_type}")
    _ensure_uploads_dir()

    # Verify Account belongs to Org
    acc = db.query(IGAccount).filter(IGAccount.id == ig_account_id, IGAccount.org_id == org_id).first()
    if not acc:
        raise HTTPException(status_code=403, detail="IG Account not found or not in your org")

    if image.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        error_msg = f"Rejected: File type '{image.content_type}' is not supported. Please use PNG, JPG, or WEBP."
        print(f"DEBUG: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

    filename = f"{int(_utcnow().timestamp())}_{image.filename}"
    local_path = os.path.join(settings.uploads_dir, filename)

    with open(local_path, "wb") as f:
        shutil.copyfileobj(image.file, f)

    public_url = f"{settings.public_base_url}/uploads/{filename}"

    post = Post(
        org_id=org_id,
        ig_account_id=ig_account_id,
        status="submitted",
        source_type=source_type,
        source_text=source_text,
        media_url=public_url,
        flags={},
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post

@router.post("/{post_id}/generate", response_model=GenerateOut)
def generate_for_post(
    post_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
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
    org_id: int = Depends(require_api_key),
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
    org_id: int = Depends(require_api_key),
):
    stmt = select(Post.status, func.count(Post.id)).where(Post.org_id == org_id).group_by(Post.status)
    if ig_account_id:
        stmt = stmt.where(Post.ig_account_id == ig_account_id)
        
    rows = db.execute(stmt).all()
    return {"counts": {status: count for status, count in rows}}

@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
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
    org_id: int = Depends(require_api_key),
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

@router.post("/{post_id}/regenerate-caption", response_model=PostOut)
def regenerate_caption(
    post_id: int,
    instructions: str | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
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
    org_id: int = Depends(require_api_key),
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
    org_id: int = Depends(require_api_key),
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
    org_id: int = Depends(require_api_key),
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
        raise HTTPException(status_code=400, detail="Missing caption or media_url")

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
    return post

@router.post("/{post_id}/publish", response_model=PostOut)
def publish_post(
    post_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
):
    post = db.query(Post).filter(Post.id == post_id, Post.org_id == org_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if not post.caption or not post.media_url:
        raise HTTPException(status_code=400, detail="Missing caption or media_url")

    acc = db.get(IGAccount, post.ig_account_id)
    caption_full = post.caption
    if post.hashtags:
        caption_full += "\n\n" + " ".join(post.hashtags)

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
        raise HTTPException(status_code=502, detail=f"Publish failed: {res.get('error')}")

    post.status = "published"
    post.published_time = _utcnow()
    db.commit()
    db.refresh(post)
    return post

@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
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
