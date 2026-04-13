from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from app.db import get_db
from app.models.inbound_message import InboundMessage
from app.schemas.inbound_message import ContactMessageRequest
from app.services.email import send_contact_acknowledgment
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contact", tags=["Contact"])

@router.post("/")
async def submit_contact(payload: ContactMessageRequest, db: Session = Depends(get_db)):
    """
    Submits a new inbound message from the contact form.
    Saves to DB and optionally sends an auto-reply.
    """
    email_clean = payload.email.lower().strip()
    
    try:
        # 1. Save to DB
        new_msg = InboundMessage(
            email=email_clean,
            name=payload.name,
            subject=payload.subject,
            message=payload.message,
            source=payload.source
        )
        db.add(new_msg)
        db.commit()
        db.refresh(new_msg)
        
        logger.info(f"📬 [ContactAPI] Received message from {email_clean} (ID: {new_msg.id})")
        
        # 2. Optional Auto-reply
        if settings.support_autoreply_enabled:
            # Non-blocking call to acknowledgment service
            try:
                await send_contact_acknowledgment(
                    email=email_clean,
                    name=payload.name,
                    subject=payload.subject
                )
            except Exception as email_err:
                logger.error(f"⚠️ [ContactAPI] Auto-reply failed for {email_clean}: {email_err}")
        
        return {
            "ok": True,
            "message": "We received your message."
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ [ContactAPI] Error processing message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error while saving message.")

@router.get("/all")
def get_all_messages(db: Session = Depends(get_db)):
    """
    Retrieves all inbound messages ordered by newest first.
    """
    messages = db.query(InboundMessage).order_by(InboundMessage.created_at.desc()).all()
    
    return [
        {
            "id": m.id,
            "email": m.email,
            "name": m.name,
            "subject": m.subject,
            "message": m.message,
            "source": m.source,
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None
        } for m in messages
    ]
