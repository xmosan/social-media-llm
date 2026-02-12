import os, shutil
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db import get_db
from ..config import settings
from ..models import Post
from ..schemas import PostOut, ApproveIn, GenerateOut
from ..services.llm import generate_draft
from ..services.policy import keyword_flags

router = APIRouter(prefix="/posts", tags=["posts"])

def _ensure_uploads_dir():
    os.makedirs(settings.uploads_dir, exist_ok=True)

def _utcnow():
    return datetime.now(timezone.utc)

@router.post("/intake", response_model=PostOut)
def intake_post(
    db: Session = Depends(get_db),
    source_text: str = Form(""),
    source_type: str = Form("form"),
    image: UploadFile = File(...),
):
    _ensure_uploads_dir()

    if image.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise HTTPException(status_code=400, detail="Only png/jpg/jpeg/webp images supported")

    filename = f"{int(_utcnow().timestamp())}_{image.filename}"
    local_path = os.path.join(settings.uploads_dir, filename)

    with open(local_path, "wb") as f:
        shutil.copyfileobj(image.file, f)

    # PUBLIC URL that Instagram can fetch (requires PUBLIC_BASE_URL to be correct)
    public_url = f"{settings.public_base_url}/uploads/{filename}"

    post = Post(
        status="submitted",
        source_type=source_type,
        source_text=source_text,
        media_url = f"{settings.public_base_url}/uploads/{filename}",
        flags={},
        hashtags=None,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post

@router.post("/{post_id}/generate", response_model=GenerateOut)
def generate_for_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
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

@router.post("/{post_id}/approve", response_model=PostOut)
def approve_and_schedule(post_id: int, payload: ApproveIn, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    flags = post.flags or {}
    if flags.get("needs_review") and not payload.approve_anyway:
        raise HTTPException(status_code=400, detail="Flagged (music/politics). Set approve_anyway=true or edit first.")

    if not post.caption or not post.media_url:
        raise HTTPException(status_code=400, detail="Missing caption or media_url")

    scheduled = payload.scheduled_time
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)

    post.scheduled_time = scheduled.astimezone(timezone.utc)
    post.status = "scheduled"
    db.commit()
    db.refresh(post)
    return post

@router.get("", response_model=list[PostOut])
def list_posts(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Post).order_by(Post.created_at.desc())
    if status:
        stmt = stmt.where(Post.status == status)
    return db.execute(stmt).scalars().all()

@router.get("/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post