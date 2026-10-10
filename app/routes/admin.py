# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Org, OrgMember, ContactMessage
from app.security.rbac import require_superadmin, is_platform_owner
from app.security.tester_access import user_can_sign_in

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/login")
@router.get("/register")
def owner_sign_in():
    return RedirectResponse("/login", status_code=303)

@router.get("/onboarding", dependencies=[Depends(require_superadmin)])
def owner_onboarding():
    return RedirectResponse("/app", status_code=303)


@router.get("/users")
def list_users(
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    users = db.query(User).order_by(User.id.desc()).all()
    results = []
    for u in users:
        # get orgs
        memberships = db.query(OrgMember).filter(OrgMember.user_id == u.id).all()
        org_names = []
        for m in memberships:
            org = db.query(Org).filter(Org.id == m.org_id).first()
            if org:
                org_names.append(f"{org.name} ({m.role})")
                
        results.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "is_superadmin": is_platform_owner(u),
            "is_active": u.is_active,
            "can_sign_in": user_can_sign_in(u),
            "access_expires_at": u.tester_expires_at,
            "created_at": u.created_at,
            "orgs": ", ".join(org_names)
        })
    return results

@router.delete("/users/{target_id}")
def delete_user(
    target_id: int,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    if target_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
        
    target_user = db.query(User).filter(User.id == target_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    # Delete memberships first
    db.query(OrgMember).filter(OrgMember.user_id == target_id).delete()
    
    # Actually delete the user
    db.delete(target_user)
    db.commit()
    return {"status": "ok"}

@router.get("/inquiries")
def list_inquiries(
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    msgs = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).all()
    return msgs

@router.delete("/inquiries/{id}")
def delete_inquiry(
    id: int,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    msg = db.query(ContactMessage).filter(ContactMessage.id == id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    db.delete(msg)
    db.commit()
    return {"status": "ok"}

@router.post("/backup-now")
def trigger_manual_backup(
    user: User = Depends(require_superadmin)
):
    from ..services.backups import backup_postgres_database
    result = backup_postgres_database()
    if result["status"] != "success":
        raise HTTPException(status_code=503, detail=result["detail"])
    return result

@router.get("/config/export")
def export_safe_config(
    user: User = Depends(require_superadmin)
):
    import os
    from datetime import datetime, timezone
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "keys_present": list(os.environ.keys())
    }

@router.get("/debug/logging")
def debug_logging(user: User = Depends(require_superadmin)):
    import logging
    from ..config import settings
    
    logger = logging.getLogger()
    axiom_handler = None
    for h in logger.handlers:
        if type(h).__name__ == "AxiomHandler":
            axiom_handler = h
            break
            
    return {
        "axiom_enabled": bool(settings.axiom_token),
        "dataset": settings.axiom_dataset,
        "queue_size": axiom_handler.queue.qsize() if axiom_handler else 0,
        "last_ship_status": "active" if axiom_handler and axiom_handler.worker.is_alive() else "inactive"
    }

@router.get("/debug/version", dependencies=[Depends(require_superadmin)])
def debug_version():
    return {
        "version": "1.2.0-redesign",
        "env": "production",
        "engine": "Sabeel v2"
    }
