import resend
import logging
from app.config import settings

logger = logging.getLogger(__name__)

async def send_email(to: str, subject: str, body: str):
    """
    Sends an email using Resend if configured, otherwise falls back to console logging.
    """
    api_key = settings.resend_api_key
    from_email = settings.resend_from_email

    # Check for configuration
    if not api_key:
        print(f"\n{'='*60}")
        print(f"⚠️  [EmailService] RESEND NOT CONFIGURED (Missing RESEND_API_KEY)")
        print(f"   Falling back to Console Logging")
        print(f"   To:      {to}")
        print(f"   Subject: {subject}")
        print(f"   Body:    {repr(body)[:100]}...")
        print(f"{'='*60}\n")
        return True

    try:
        resend.api_key = api_key
        
        params = {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "text": body,
        }
        
        # Async-safe send via SDK
        r = resend.Emails.send(params)
        
        logger.info(f"✅ [EmailService] Email sent successfully via Resend to {to}")
        return True
    except Exception as e:
        # Graceful failure: Log it but don't crash the calling process (e.g. waitlist signup)
        logger.error(f"❌ [EmailService] Failed to send email via Resend to {to}: {e}")
        
        # Internal diagnostic print for developers
        print(f"❌ [EmailService] OUTBOUND ERROR: {e}")
        
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

    html_body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #0F3D2E;">Sabeel Studio</h2>
        <p>{greeting}</p>
        <p>Thank you for reaching out to us. We've <strong>received your message</strong> and our team will review it as soon as possible.</p>
        <p>This is an automated confirmation that your submission was successful.</p>
        <p style="color: #666; font-size: 12px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px;">
            Please do not reply to this email directly.<br>
            &copy; 2026 Sabeel Studio
        </p>
    </div>
    """

    # We reuse the main send_email function which handlesResend vs Fallback
    success = await send_email(to=email, subject=msg_subject, body=text_body)
    
    if success:
        logger.info(f"✅ [EmailService] Contact acknowledgment sent to {email}")
    else:
        logger.warning(f"⚠️ [EmailService] Failed to send contact acknowledgment to {email}")
        
    return {"status": "success" if success else "failed"}
