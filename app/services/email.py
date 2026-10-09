import resend
import logging
import asyncio
from app.config import settings

logger = logging.getLogger(__name__)

async def send_email(to: str, subject: str, body: str):
    """
    Returns whether Resend accepted the message, not whether it reached an inbox.
    """
    api_key = settings.resend_api_key
    from_email = settings.resend_from_email

    # Check for configuration
    if not api_key:
        logger.warning("email_not_configured")
        return False

    try:
        resend.api_key = api_key
        
        params = {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "text": body,
        }
        
        # Async-safe send via SDK
        r = await asyncio.to_thread(resend.Emails.send, params)
        
        if not isinstance(r, dict) or not r.get("id"):
            logger.error("email_acceptance_unconfirmed")
            return False
        logger.info("email_accepted")
        return True
    except Exception:
        # Graceful failure: Log it but don't crash the calling process (e.g. waitlist signup)
        logger.error("email_send_failed")
        
        return False

async def send_contact_acknowledgment(
    email: str,
    name: str | None = None,
    subject: str | None = None
) -> dict:
    """
    Sends an automatic confirmation email to the user after they submit the contact form.
    """
    msg_subject = "We received your message"
    
    greeting = f"Hi {name}," if name else "Hi there,"
    
    text_body = (
        f"{greeting}\n\n"
        "Thank you for contacting Sabeel Studio.\n\n"
        "We received your message and will review it as soon as possible. "
        "This is an automatic confirmation that your message was received.\n\n"
        "Please do not reply to this message.\n\n"
        "— Sabeel Studio"
    )

    success = await send_email(to=email, subject=msg_subject, body=text_body)
    
    if success:
        logger.info("contact_acknowledgment_accepted")
    else:
        logger.warning("contact_acknowledgment_not_sent")
        
    return {"status": "success" if success else "failed"}
