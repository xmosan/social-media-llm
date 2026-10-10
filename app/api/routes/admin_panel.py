from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, ConfigDict, StrictBool
from typing import Literal
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
import os

from app.db import get_db
from app.models import User, Org, IGAccount, TopicAutomation, Post, WaitlistEntry, TesterInvitation, InboundMessage
from app.config import settings
from app.security.rbac import require_superadmin
from app.services.automation_runner import run_automation_once

router = APIRouter(prefix="/api/admin", tags=["Admin Panel"])

@router.get("/overview")
def get_platform_overview(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    from app.models import ContentItem
    import json
    
    # Check if synced (manifested Surah 114)
    fully_synced = db.query(ContentItem).filter(
        ContentItem.item_type == "quran",
        ContentItem.title.like("Surah 114, Verse %")
    ).count() > 0
    
    # Read background status
    sync_status = {}
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    status_file = os.path.join(base_dir, "sync_status.json")
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                sync_status = json.load(f)
        except: pass

    return {
        "ok": True,
        "owner": {"name": admin_user.name or "Sabeel owner", "email": admin_user.email},
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "signup_enabled": settings.signup_enabled,
        "creators": db.query(User).filter(User.id != admin_user.id).count(),
        "pilot": {
            "pending": db.query(TesterInvitation).filter(TesterInvitation.redeemed_at.is_(None), TesterInvitation.revoked_at.is_(None), TesterInvitation.expires_at > datetime.now(timezone.utc)).count(),
            "active": db.query(TesterInvitation).filter(TesterInvitation.redeemed_at.is_not(None), TesterInvitation.revoked_at.is_(None), TesterInvitation.access_expires_at > datetime.now(timezone.utc)).count(),
        },
        "inbox": {
            "feedback": db.query(InboundMessage).filter(InboundMessage.source == "creator_pilot").count(),
            "support_pending": db.query(InboundMessage).filter(InboundMessage.source.is_distinct_from("creator_pilot"), InboundMessage.status == "received").count(),
        },
        "users": db.query(User).count(),
        "orgs": db.query(Org).count(),
        "ig_accounts": db.query(IGAccount).count(),
        "automations": db.query(TopicAutomation).count(),
        "library": db.query(ContentItem).count(),
        "is_quran_synced": fully_synced,
        "sync_status": sync_status,
        "posts": {
            "total": db.query(Post).count(),
            "scheduled": db.query(Post).filter(Post.status == "scheduled").count(),
            "published": db.query(Post).filter(Post.status == "published").count(),
            "failed": db.query(Post).filter(Post.status == "failed").count(),
            "publish_unknown": db.query(Post).filter(Post.status == "publish_unknown").count(),
        },
        "waitlist": db.query(WaitlistEntry).count()
    }

@router.get("/automations")
def list_system_automations(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Lists every automation in the system with context."""
    automations = db.query(TopicAutomation).all()
    
    results = []
    for a in automations:
        org = db.query(Org).filter(Org.id == a.org_id).first()
        acc = db.query(IGAccount).filter(IGAccount.id == a.ig_account_id).first()
        
        results.append({
            "id": a.id,
            "name": a.name,
            "org_name": org.name if org else "Unknown",
            "ig_username": acc.username if acc else "Not Linked",
            "enabled": a.enabled,
            "post_time": a.post_time_local,
            "style": a.style_preset,
            "last_run": a.last_run_at.isoformat() if a.last_run_at else None,
            "last_error": a.last_error
        })
    
    return {"ok": True, "items": results}

class AutomationState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@router.patch("/automations/{id}")
def patch_automation(
    id: int,
    payload: AutomationState,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Update global automation status (e.g. pause/resume)."""
    auto = db.query(TopicAutomation).filter(TopicAutomation.id == id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    # Reuse the creator route's canonical account and schedule validation.
    # Pausing must remain possible even after a workspace's pilot has ended.
    if payload.enabled:
        from app.security.tester_access import require_workspace_access
        require_workspace_access(db, auto.org_id)
    from app.routes.automations import update_automation
    from app.schemas import TopicAutomationUpdate
    update_automation(id, TopicAutomationUpdate(enabled=payload.enabled), db, auto.org_id)

    return {"ok": True}

@router.post("/automations/{id}/run")
def run_automation_now(
    id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Manually triggers an automation run."""
    auto = db.query(TopicAutomation).filter(TopicAutomation.id == id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
        
    post = run_automation_once(db, auto.id)
    if not post:
        return {"ok": False, "message": "Run failed or skipped."}
        
    return {"ok": True, "post_id": post.id}

@router.get("/ig-accounts")
def list_system_accounts(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Lists system-wide connected Instagram accounts."""
    accounts = db.query(IGAccount).all()
    results = []
    for a in accounts:
        org = db.query(Org).filter(Org.id == a.org_id).first()
        results.append({
            "id": a.id,
            "username": a.username,
            "name": a.name,
            "org_name": org.name if org else "Unknown",
            "active": a.active,
            "created_at": a.created_at.isoformat() if a.created_at else None
        })
    return {"ok": True, "items": results}

@router.get("/activity")
def get_recent_activity(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Unified feed of recent system events."""
    # 1. Recent Waitlist
    waitlist = db.query(WaitlistEntry).order_by(WaitlistEntry.created_at.desc()).limit(10).all()
    
    # 2. Recent Posts
    posts = db.query(Post).order_by(Post.created_at.desc()).limit(10).all()
    
    # 3. Recent Accounts
    accounts = db.query(IGAccount).order_by(IGAccount.created_at.desc()).limit(5).all()
    
    feed = []
    
    for w in waitlist:
        feed.append({
            "type": "waitlist",
            "text": f"{w.email} joined from {w.source}",
            "time": w.created_at.isoformat() if w.created_at else None,
            "id": w.id
        })
        
    for p in posts:
        status_msg = "published" if p.status == "published" else "generated"
        feed.append({
            "type": "post",
            "text": f"Org {p.org_id}: {status_msg}",
            "time": p.created_at.isoformat() if p.created_at else None,
            "id": p.id,
            "status": p.status
        })
        
    for a in accounts:
        feed.append({
            "type": "account",
            "text": f"Connected: @{a.username}",
            "time": a.created_at.isoformat() if a.created_at else None,
            "id": a.id
        })
        
    # Sort by time
    feed.sort(key=lambda x: x["time"] if x["time"] else "", reverse=True)
    
    return {"ok": True, "items": feed[:15]}

@router.get("/diagnostics")
def get_diagnostics(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """System heartbeat and environment check."""
    from app.services.scheduler import _global_scheduler
    from sqlalchemy import text
    db.execute(text("SELECT 1"))
    
    scheduler_running = False
    active_jobs = 0
    if _global_scheduler:
        scheduler_running = _global_scheduler.running
        active_jobs = len(_global_scheduler.get_jobs())

    return {
        "ok": True,
        "database": "connected",
        "signup_enabled": settings.signup_enabled,
        "owner_email": admin_user.email,
        "scheduler": {
            "status": ("running" if scheduler_running else "stopped") if settings.scheduler_enabled else "disabled",
            "active_jobs": active_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "environment": {
            "openai_configured": bool(settings.openai_api_key),
            "instagram_configured": bool(settings.fb_app_id and settings.fb_app_secret),
            "logging_configured": bool(settings.axiom_token),
            "backup_configured": settings.backup_storage_type.lower() == "s3" and all((settings.s3_access_key, settings.s3_secret_key, settings.s3_bucket_name)),
        },
        "stats": {
            "total_posts": db.query(Post).count(),
            "failed_posts": db.query(Post).filter(Post.status == "failed").count()
        }
    }

@router.get("/failed-posts")
def list_failed_posts(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Deep dive into platform-wide post failures."""
    posts = db.query(Post).filter(Post.status.in_(["failed", "publish_unknown"]))\
               .order_by(Post.created_at.desc())\
               .limit(limit).all()
    
    return {
        "ok": True,
        "items": [
            {
                "id": p.id,
                "org_id": p.org_id,
                "topic": p.topic,
                "status": p.status,
                "error": (p.flags or {}).get("publish_error") or p.last_error,
                "created_at": p.created_at.isoformat() if p.created_at else None
            } for p in posts
        ]
    }

@router.get("/messages")
def list_inbound_messages(
    status: Optional[Literal["received", "resolved", "archived"]] = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Admin-only view of support messages with filters."""
    from app.models.inbound_message import InboundMessage
    q = db.query(InboundMessage).filter(InboundMessage.source.is_distinct_from("creator_pilot"))
    if status:
        q = q.filter(InboundMessage.status == status)
        
    messages = q.order_by(InboundMessage.created_at.desc()).limit(limit).all()
    
    return {
        "ok": True,
        "items": [
            {
                "id": m.id,
                "email": m.email,
                "name": m.name,
                "subject": m.subject,
                "message": m.message,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None
            } for m in messages
        ]
    }

class MessageState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["received", "resolved", "archived"]


@router.patch("/messages/{id}")
def update_message_status(
    id: int,
    payload: MessageState,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Update support message status (Resolve/Archive)."""
    from app.models.inbound_message import InboundMessage
    msg = db.query(InboundMessage).filter(InboundMessage.id == id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    msg.status = payload.status
        
    db.commit()
    return {"ok": True}

@router.post("/sync/full-quran")
async def trigger_full_quran_sync(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Triggers a full-Quran foundation sync in the background."""
    from app.services.quran_ingestion import sync_entire_quran
    
    # We pass the SessionLocal factory for the background worker
    from app.db import SessionLocal
    background_tasks.add_task(sync_entire_quran, SessionLocal)
    
    return {
        "ok": True, 
        "message": "Full Quran synchronization spawned in background matrix."
    }

@router.get("/system/health")
def get_system_health(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Read-only diagnostics; configuration is not proof of backup recovery."""
    from fastapi.responses import JSONResponse
    from app.config import settings
    try:
        with db.no_autoflush:
            counts = {
                "waitlist": db.query(WaitlistEntry).count(),
                "users": db.query(User).count(),
                "posts": db.query(Post).count(),
                "orgs": db.query(Org).count(),
            }
    except Exception:
        db.rollback()
        return JSONResponse(status_code=503, content={
            "status": "unhealthy", "database": "unavailable", "write_test": "not_run",
            "backup_status": "unverified", "backup_verified": False,
            "error": "Database diagnostics are unavailable",
        })
    durable_configured = settings.backup_storage_type.lower() == "s3" and all((
        settings.s3_access_key, settings.s3_secret_key, settings.s3_bucket_name,
    ))
    return {
        "status": "healthy" if durable_configured else "degraded",
        "database": "connected",
        "write_test": "not_run",
        "backup_status": "configured" if durable_configured else "not_configured",
        "backup_verified": False,
        "tables": counts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
