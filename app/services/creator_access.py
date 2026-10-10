"""End access while retaining creator records, sources, media and published work."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func
from app.models import User, Org, OrgMember, ApiKey, Post, TopicAutomation


def end_workspace_access(db, org_id, now):
    db.query(Org).filter(Org.id == org_id).update({Org.tester_revoked_at: now})
    db.query(ApiKey).filter(ApiKey.org_id == org_id, ApiKey.revoked_at.is_(None)).update({ApiKey.revoked_at: now})
    db.query(TopicAutomation).filter(TopicAutomation.org_id == org_id).update({TopicAutomation.enabled: False})
    db.query(Post).filter(Post.org_id == org_id, Post.status == "scheduled").update({
        Post.status: "drafted", Post.scheduled_time: None})


def legacy_access_plan(db, owner_email):
    owner_email = owner_email.strip().lower()
    owners = db.query(User).filter(func.lower(User.email) == owner_email).all()
    if not owners or not any(u.is_active and u.is_superadmin for u in owners):
        raise HTTPException(409, "The protected owner account could not be verified.")
    targets = db.query(User).filter(func.lower(User.email) != owner_email,
                                   User.tester_expires_at.is_(None)).order_by(User.id).all()
    ids = {u.id for u in targets}
    memberships = db.query(OrgMember).all()
    affected = {m.org_id for m in memberships if m.user_id in ids}
    protected = {m.org_id for m in memberships if m.user_id not in ids}
    return {"user_ids": sorted(ids), "owner_ids": sorted(u.id for u in owners),
            "workspace_ids": sorted(affected - protected),
            "protected_workspace_ids": sorted(protected),
            "key_workspace_ids": sorted(affected)}


def retire_legacy_access(db, *, owner_email, expected_user_ids):
    # Operator-only service: caller previews the exact IDs, takes a backup, and
    # commits with a restricted audit record. Never run from app startup.
    db.query(User).order_by(User.id).with_for_update().all()
    db.query(Org).order_by(Org.id).with_for_update().all()
    plan = legacy_access_plan(db, owner_email)
    if plan["user_ids"] != sorted(set(expected_user_ids)):
        raise HTTPException(409, "Accounts changed since the preview. Review the access plan again.")
    now = datetime.now(timezone.utc)
    for user in db.query(User).filter(User.id.in_(plan["user_ids"])).all():
        if user.is_active or user.is_superadmin:
            user.session_version = (user.session_version or 0) + 1
        user.is_active = user.is_superadmin = False
    for org_id in plan["workspace_ids"]:
        end_workspace_access(db, org_id, now)
    # A shared key cannot be attributed to an individual member. End old keys in
    # affected shared workspaces too, without changing the owner's workspace.
    db.query(ApiKey).filter(ApiKey.org_id.in_(plan["key_workspace_ids"]),
                            ApiKey.revoked_at.is_(None)).update({ApiKey.revoked_at: now})
    db.flush()
    return plan
