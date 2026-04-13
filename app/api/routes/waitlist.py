from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Any
import logging
import io
import csv
from datetime import datetime, timedelta

from app.db import get_db
from app.models.waitlist import WaitlistEntry
from app.schemas.waitlist import WaitlistJoinRequest
from app.security.rbac import require_superadmin
from app.models import User
from app.services.email import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/waitlist", tags=["Waitlist"])

@router.post("/join")
async def waitlist_join(
    payload: WaitlistJoinRequest, 
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Submits a new email to the waitlist.
    Captures metadata (IP, UA, UTMs) for acquisition tracking.
    """
    # 1. Normalize email
    email_clean = payload.email.lower().strip()
    
    # 2. Check if already exists
    existing = db.query(WaitlistEntry).filter(WaitlistEntry.email == email_clean).first()
    if existing:
        return {
            "ok": True,
            "message": "You're already on the waitlist.",
            "already_exists": True,
            "id": existing.id
        }
    
    # 3. Extract Metadata from Headers & Params
    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    referer = request.headers.get("referer")
    
    # UTMs: Prioritize payload, fallback to query params
    utm_source = payload.utm_source or request.query_params.get("utm_source")
    utm_medium = payload.utm_medium or request.query_params.get("utm_medium")
    utm_campaign = payload.utm_campaign or request.query_params.get("utm_campaign")
    
    # 4. Insert into DB
    try:
        new_entry = WaitlistEntry(
            email=email_clean,
            name=payload.name,
            source=payload.source,
            wants_updates=payload.wants_updates,
            ip_address=ip_addr,
            user_agent=user_agent,
            referrer=referer,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign
        )
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)
        
        logger.info(f"✅ Waitlist: New entry for {email_clean} (ID: {new_entry.id}) Source: {payload.source} UTM: {utm_source}")
        
        # 5. Email Confirmation (Non-blocking)
        try:
            subject = "You’re on the Sabeel waitlist"
            body = (
                f"Hi {payload.name if payload.name else 'there'},\n\n"
                "Thank you for joining the Sabeel waitlist.\n"
                "We’ve received your email and added you to our early access list. "
                "You’ll be among the first to hear about updates and access.\n\n"
                "— Sabeel Studio"
            )
            await send_email(to=email_clean, subject=subject, body=body)
        except Exception as email_err:
            logger.error(f"Failed to send waitlist confirmation email: {email_err}")
            
        return {
            "ok": True,
            "message": "Successfully joined the waitlist.",
            "already_exists": False,
            "id": new_entry.id
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving waitlist entry: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred.")

@router.get("/stats")
def get_waitlist_stats(db: Session = Depends(get_db)):
    """
    Returns high-level growth analytics for the waitlist.
    Includes time-based counts and source breakdowns.
    """
    logger.info("📊 [WaitlistAPI] Growth stats requested")
    now = datetime.utcnow()
    one_day_ago = now - timedelta(days=1)
    one_week_ago = now - timedelta(days=7)
    
    total = db.query(WaitlistEntry).count()
    today = db.query(WaitlistEntry).filter(WaitlistEntry.created_at >= one_day_ago).count()
    this_week = db.query(WaitlistEntry).filter(WaitlistEntry.created_at >= one_week_ago).count()
    
    # Top Sources
    sources_query = db.query(
        WaitlistEntry.source, 
        func.count(WaitlistEntry.id).label("count")
    ).group_by(WaitlistEntry.source).order_by(func.count(WaitlistEntry.id).desc()).limit(10).all()
    
    # Top UTM Sources
    utm_sources_query = db.query(
        WaitlistEntry.utm_source,
        func.count(WaitlistEntry.id).label("count")
    ).filter(WaitlistEntry.utm_source != None).group_by(WaitlistEntry.utm_source).order_by(func.count(WaitlistEntry.id).desc()).limit(10).all()
    
    return {
        "ok": True,
        "total": total,
        "today": today,
        "this_week": this_week,
        "top_sources": {s[0]: s[1] for s in sources_query},
        "top_utm_sources": {s[0]: s[1] for s in utm_sources_query}
    }

@router.get("/export")
def export_waitlist_csv(db: Session = Depends(get_db)):
    """
    Generates and returns a CSV export of all waitlist entries.
    """
    logger.info("📋 [WaitlistAPI] CSV export requested")
    entries = db.query(WaitlistEntry).order_by(WaitlistEntry.created_at.asc()).all()
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "email", "name", "source", "wants_updates", "status", "created_at", 
        "utm_source", "utm_medium", "utm_campaign", "referrer"
    ])
    
    writer.writeheader()
    for e in entries:
        writer.writerow({
            "id": e.id,
            "email": e.email,
            "name": e.name or "",
            "source": e.source,
            "wants_updates": e.wants_updates,
            "status": e.status,
            "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "",
            "utm_source": e.utm_source or "",
            "utm_medium": e.utm_medium or "",
            "utm_campaign": e.utm_campaign or "",
            "referrer": e.referrer or ""
        })
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="waitlist.csv"'}
    )

@router.get("/all")
def get_all_entries(
    limit: int = 100,
    offset: int = 0,
    q: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    wants_updates: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Returns waitlist entries with pagination, search, and filtering.
    """
    query = db.query(WaitlistEntry)

    if q:
        search = f"%{q}%"
        query = query.filter(
            (WaitlistEntry.email.ilike(search)) | 
            (WaitlistEntry.name.ilike(search))
        )
    
    if status:
        query = query.filter(WaitlistEntry.status == status)
    
    if source:
        query = query.filter(WaitlistEntry.source == source)
        
    if wants_updates is not None:
        query = query.filter(WaitlistEntry.wants_updates == wants_updates)

    total_count = query.count()
    entries = query.order_by(WaitlistEntry.created_at.desc())\
                .limit(limit)\
                .offset(offset)\
                .all()
    
    items = [
        {
            "id": e.id,
            "email": e.email,
            "name": e.name,
            "source": e.source,
            "wants_updates": e.wants_updates,
            "status": e.status,
            "tags": e.tags,
            "admin_notes": e.admin_notes,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "utm_source": e.utm_source,
            "utm_medium": e.utm_medium,
            "utm_campaign": e.utm_campaign
        } for e in entries
    ]

    return {
        "ok": True,
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "items": items
    }

@router.patch("/{id}")
async def patch_waitlist_entry(
    id: int,
    payload: dict,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Updates a waitlist entry (Admin Only)."""
    entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    allowed_fields = ["status", "tags", "admin_notes", "name", "source"]
    for field in allowed_fields:
        if field in payload:
            setattr(entry, field, payload[field])
            
    db.commit()
    db.refresh(entry)
    return {"ok": True, "id": entry.id}

@router.delete("/{id}")
async def delete_waitlist_entry(
    id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_superadmin)
):
    """Deletes a waitlist entry (Admin Only)."""
    entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    db.delete(entry)
    db.commit()
    return {"ok": True}
