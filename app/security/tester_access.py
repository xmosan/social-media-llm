"""Pilot access applies to sessions, workspace keys and background execution alike."""
from datetime import datetime, timezone
from fastapi import HTTPException
from app.models import Org


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def user_can_sign_in(user):
    return bool(user and user.is_active and (
        user.tester_expires_at is None or utc(user.tester_expires_at) > datetime.now(timezone.utc)))


def require_workspace_access(db, org_id):
    # Query columns afresh, rather than a potentially stale ORM identity.
    row = db.query(Org.tester_expires_at, Org.tester_revoked_at).filter(Org.id == org_id).first()
    if row is None:
        raise HTTPException(403, "Workspace is unavailable.")
    if row.tester_revoked_at or (row.tester_expires_at and utc(row.tester_expires_at) <= datetime.now(timezone.utc)):
        raise HTTPException(403, "This workspace's tester access has ended. Your saved work is retained. Contact Sabeel for help.")
