"""Single-use, email-bound invitations. Raw bearer links exist only at issuance."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models import TesterInvitation, User, Org, OrgMember
from app.config import settings
from app.security.auth import get_password_hash, verify_password
from app.security.tester_access import utc
from app.services.registration import provision_creator
from app.services.creator_access import end_workspace_access


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


def returning_workspace(db, user):
    if (not user or user.is_active or user.is_superadmin or not user.password_hash
            or user.email.strip().lower() == (settings.platform_owner_email or "").strip().lower()):
        raise HTTPException(409, "Returning invitations require a disabled creator with an existing password. Owner accounts cannot be invited.")
    memberships = db.query(OrgMember).filter(OrgMember.user_id == user.id).all()
    if len(memberships) != 1 or memberships[0].role != "owner":
        raise HTTPException(409, "This account needs a workspace access review before it can return.")
    org = db.query(Org).filter(Org.id == memberships[0].org_id).with_for_update().first()
    if (not org or not org.tester_revoked_at
            or db.query(OrgMember).filter(OrgMember.org_id == org.id).count() != 1):
        raise HTTPException(409, "This account needs a private, disabled workspace before it can return.")
    return org


def issue(db, *, email, admin_id, invitation_days=7, pilot_days=30, returning=False):
    email = email.strip().lower()
    if not 1 <= invitation_days <= 30 or not 1 <= pilot_days <= 90:
        raise HTTPException(422, "Choose 1–30 invitation days and 1–90 pilot days.")
    now = datetime.now(timezone.utc)
    row = db.query(TesterInvitation).filter(TesterInvitation.email == email).with_for_update().first()
    if row and (row.redeemed_at or state(row, now) == "pending"):
        raise HTTPException(409, "An invitation already exists. Revoke an unused invitation before replacing it.")
    users = db.query(User).filter(func.lower(User.email) == email).with_for_update().all()
    existing = users[0] if len(users) == 1 else None
    org = None
    if returning:
        if len(users) != 1:
            raise HTTPException(409, "One existing creator account must match this email.")
        org = returning_workspace(db, existing)
    elif users:
        raise HTTPException(409, "This email already has an account. For a disabled legacy account, choose Returning creator. Active creators can sign in.")
    token = secrets.token_urlsafe(32)
    if row is None:
        row = TesterInvitation(id=str(uuid.uuid4()), email=email)
        db.add(row)
    row.token_hash, row.created_by, row.created_at = digest(token), admin_id, now
    row.expires_at, row.pilot_days = now + timedelta(days=invitation_days), pilot_days
    row.revoked_at = row.revoked_by = None
    row.user_id, row.org_id = (existing.id, org.id) if returning else (None, None)
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
        if row.user_id is not None:
            raise HTTPException(409, "Use this returning invitation with your existing password.")
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


def restore(db, *, token, email, password):
    try:
        row = pending(db, token, lock=True)
        if row.user_id is None or row.email != email.strip().lower():
            raise HTTPException(422, "Check your returning invitation and invited email address.")
        user = db.query(User).filter(User.id == row.user_id).with_for_update().first()
        if (not user or user.email.strip().lower() != row.email or not user.password_hash
                or not verify_password(password, user.password_hash)):
            raise HTTPException(401, "Your existing password did not match. Nothing was changed.")
        org = returning_workspace(db, user)
        if org.id != row.org_id:
            raise HTTPException(409, "This account's workspace changed. Ask Sabeel to review your access.")
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=row.pilot_days)
        # Invalidate every pre-return session, including ones issued before
        # session versioning. No password, profile, content or schedule reset.
        user.session_version = (user.session_version or 0) + 1
        user.is_active, user.tester_expires_at, user.active_org_id = True, expiry, org.id
        org.tester_revoked_at, org.tester_expires_at = None, expiry
        row.redeemed_at, row.access_expires_at = now, expiry
        db.commit()
        return user
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
    if row.user_id and row.redeemed_at:
        db.query(User).filter(User.id == row.user_id).update({User.is_active: False,
            User.session_version: User.session_version + 1})
        end_workspace_access(db, row.org_id, row.revoked_at)
    db.commit()
    return row
