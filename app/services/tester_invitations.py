"""Single-use, email-bound invitations. Raw bearer links exist only at issuance."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models import TesterInvitation, User, Org, Post, TopicAutomation
from app.security.auth import get_password_hash
from app.security.tester_access import utc
from app.services.registration import provision_creator


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def state(row, now=None):
    now = now or datetime.now(timezone.utc)
    if row.revoked_at:
        return "revoked"
    if row.redeemed_at:
        return "active" if utc(row.access_expires_at) > now else "ended"
    return "pending" if utc(row.expires_at) > now else "expired"


def describe(row):
    return {field: getattr(row, field) for field in (
        "id", "email", "created_at", "expires_at", "pilot_days", "redeemed_at",
        "access_expires_at", "revoked_at")} | {"status": state(row)}


def issue(db, *, email, admin_id, invitation_days=7, pilot_days=30):
    email = email.strip().lower()
    if not 1 <= invitation_days <= 30 or not 1 <= pilot_days <= 90:
        raise HTTPException(422, "Choose 1–30 invitation days and 1–90 pilot days.")
    if db.query(User.id).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "This email already has an account. Invitations are for new testers.")
    now = datetime.now(timezone.utc)
    row = db.query(TesterInvitation).filter(TesterInvitation.email == email).with_for_update().first()
    if row and (row.redeemed_at or state(row, now) == "pending"):
        raise HTTPException(409, "An invitation already exists. Revoke an unused invitation before replacing it.")
    token = secrets.token_urlsafe(32)
    if row is None:
        row = TesterInvitation(id=str(uuid.uuid4()), email=email)
        db.add(row)
    row.token_hash, row.created_by, row.created_at = digest(token), admin_id, now
    row.expires_at, row.pilot_days = now + timedelta(days=invitation_days), pilot_days
    row.revoked_at = row.revoked_by = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An invitation already exists. Refresh the list before continuing.") from None
    return row, token


def pending(db, token, *, lock=False):
    query = db.query(TesterInvitation).filter(TesterInvitation.token_hash == digest(token))
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row or state(row) != "pending":
        raise HTTPException(410, "This invitation is unavailable, already used, or expired. Ask Sabeel for a new invitation, or sign in if you already joined.")
    return row


def redeem(db, *, token, email, name, password):
    try:
        row = pending(db, token, lock=True)
        if row.email != email.strip().lower():
            raise HTTPException(422, "Use the email address that received this invitation.")
        if db.query(User.id).filter(func.lower(User.email) == row.email).first():
            raise HTTPException(409, "This email already has an account. Please sign in.")
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=row.pilot_days)
        user, org = provision_creator(db, email=row.email, name=name,
                                     password_hash=get_password_hash(password), tester_expires_at=expiry)
        row.redeemed_at, row.access_expires_at = now, expiry
        row.user_id, row.org_id = user.id, org.id
        db.commit()
        return user
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This invitation could not be accepted. Please sign in if you already joined.") from None
    except Exception:
        db.rollback()
        raise


def revoke(db, invitation_id, admin_id):
    row = db.query(TesterInvitation).filter(TesterInvitation.id == invitation_id).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Invitation not found.")
    if row.revoked_at:
        return row
    row.revoked_at, row.revoked_by = datetime.now(timezone.utc), admin_id
    if row.user_id:
        db.query(User).filter(User.id == row.user_id).update({User.is_active: False})
        db.query(Org).filter(Org.id == row.org_id).update({Org.tester_revoked_at: row.revoked_at})
        db.query(TopicAutomation).filter(TopicAutomation.org_id == row.org_id).update({TopicAutomation.enabled: False})
        db.query(Post).filter(Post.org_id == row.org_id, Post.status == "scheduled").update({
            Post.status: "drafted", Post.scheduled_time: None})
    db.commit()
    return row
