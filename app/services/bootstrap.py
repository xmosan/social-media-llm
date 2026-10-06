"""Explicit, create-only provisioning for a new installation."""

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Org, OrgMember, User
from app.security.auth import get_password_hash

logger = logging.getLogger(__name__)


def bootstrap_saas(db: Session, config: Settings) -> None:
    if not config.bootstrap_superadmin:
        return

    # Settings validates credentials when opt-in is enabled. Existing accounts
    # are deliberately never promoted, reactivated, or given a new password.
    email = config.superadmin_email.strip().lower()
    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        logger.info("Bootstrap skipped: the configured account already exists")
        return

    org = db.query(Org).order_by(Org.id.asc()).first()
    if org is None:
        org = Org(name="Default Workspace")
        db.add(org)
        db.flush()

    admin = User(
        email=email,
        password_hash=get_password_hash(config.superadmin_password),
        is_superadmin=True,
        is_active=True,
        active_org_id=org.id,
        name="Platform Superadmin",
    )
    db.add(admin)
    db.flush()
    db.add(OrgMember(org_id=org.id, user_id=admin.id, role="owner"))
    db.commit()
    logger.info("Bootstrap created an initial administrator and workspace membership")
