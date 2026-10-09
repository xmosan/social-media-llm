"""Create the same private creator workspace for password, Google and invited signup.

Caller owns validation and transaction; this function never grants platform access.
"""
from app.models import User, Org, OrgMember


def provision_creator(db, *, email, name, password_hash=None, google_id=None, tester_expires_at=None):
    user = User(email=email.strip().lower(), name=name.strip(), password_hash=password_hash,
                google_id=google_id, is_active=True, is_superadmin=False,
                onboarding_complete=False, tester_expires_at=tester_expires_at)
    db.add(user)
    db.flush()
    org = Org(name=f"{user.name}'s Workspace", tester_expires_at=tester_expires_at)
    db.add(org)
    db.flush()
    db.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
    user.active_org_id = org.id
    return user, org
