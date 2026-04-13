from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import os

from app.db import get_db
from app.models import User, Org, IGAccount, TopicAutomation, Post, WaitlistEntry
from app.security.rbac import require_superadmin
from app.services.automation_runner import run_automation_once

router = APIRouter(prefix="/api/admin", tags=["Admin Panel"])

@router.get("/overview")
def get_platform_overview(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Provides high-level system stats."""
    return {
        "ok": True,
        "users": db.query(User).count(),
        "orgs": db.query(Org).count(),
        "ig_accounts": db.query(IGAccount).count(),
        "automations": db.query(TopicAutomation).count(),
        "posts": {
            "total": db.query(Post).count(),
            "scheduled": db.query(Post).filter(Post.status == "scheduled").count(),
            "published": db.query(Post).filter(Post.status == "published").count(),
            "failed": db.query(Post).filter(Post.status == "failed").count(),
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

@router.patch("/automations/{id}")
def patch_automation(
    id: int,
    payload: dict,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Update global automation status (e.g. pause/resume)."""
    auto = db.query(TopicAutomation).filter(TopicAutomation.id == id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
        
    if "enabled" in payload:
        auto.enabled = payload["enabled"]
        
    db.commit()
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
    
    scheduler_running = False
    active_jobs = 0
    if _global_scheduler:
        scheduler_running = _global_scheduler.running
        active_jobs = len(_global_scheduler.get_jobs())

    return {
        "ok": True,
        "scheduler": {
            "status": "running" if scheduler_running else "stopped",
            "active_jobs": active_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "environment": {
            "openai_key": bool(os.getenv("OPENAI_API_KEY")),
            "ig_client_id": bool(os.getenv("INSTAGRAM_CLIENT_ID")),
            "db_url": os.getenv("DATABASE_URL")[:15] + "..." if os.getenv("DATABASE_URL") else "sqlite-default"
        },
        "stats": {
            "total_posts": db.query(Post).count(),
            "failed_posts": db.query(Post).filter(Post.status == "failed").count()
        }
    }

@router.get("/failed-posts")
def list_failed_posts(
    limit: int = 50,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Deep dive into platform-wide post failures."""
    posts = db.query(Post).filter(Post.status == "failed")\
               .order_by(Post.created_at.desc())\
               .limit(limit).all()
    
    return {
        "ok": True,
        "items": [
            {
                "id": p.id,
                "org_id": p.org_id,
                "topic": p.topic,
                "error": p.flags.get("publish_error") if p.flags else p.last_error,
                "created_at": p.created_at.isoformat() if p.created_at else None
            } for p in posts
        ]
    }

@router.get("/messages")
def list_inbound_messages(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Admin-only view of support messages with filters."""
    from app.models.inbound_message import InboundMessage
    q = db.query(InboundMessage)
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

@router.patch("/messages/{id}")
def update_message_status(
    id: int,
    payload: dict,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Update support message status (Resolve/Archive)."""
    from app.models.inbound_message import InboundMessage
    msg = db.query(InboundMessage).filter(InboundMessage.id == id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    if "status" in payload:
        msg.status = payload["status"]
        
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
