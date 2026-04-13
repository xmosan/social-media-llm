from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime, timedelta

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
            "text": f"{w.email} joined the waitlist from {w.source}",
            "time": w.created_at.isoformat() if w.created_at else None,
            "id": w.id
        })
        
    for p in posts:
        status_msg = "published" if p.status == "published" else "generated"
        feed.append({
            "type": "post",
            "text": f"New post {status_msg} for Org {p.org_id}",
            "time": p.created_at.isoformat() if p.created_at else None,
            "id": p.id,
            "status": p.status
        })
        
    for a in accounts:
        feed.append({
            "type": "account",
            "text": f"New account connected: @{a.username} ({a.name})",
            "time": a.created_at.isoformat() if a.created_at else None,
            "id": a.id
        })
        
    # Sort by time
    feed.sort(key=lambda x: x["time"] if x["time"] else "", reverse=True)
    
    return {"ok": True, "items": feed[:20]}
