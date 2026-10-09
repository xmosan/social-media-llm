# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import Request, HTTPException, Depends, Header, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, OrgMember, Org
from app.security.auth import get_current_user, require_user

def _resolve_current_org_id(
    request: Request,
    user: User | None = Depends(get_current_user),
    org_id: str | None = Header(default=None, alias="X-Org-Id"),
    db: Session = Depends(get_db)
) -> int:
    """
    Drop-in replacement for require_api_key.
    Returns the org_id the request is authorized for based on user membership and scoping.
    """
    # Parse explicit scoping before choosing either a service or user principal.
    target_org_id = None
    if org_id:
        try:
            target_org_id = int(org_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-Org-Id")
        if target_org_id <= 0 or target_org_id > 2_147_483_647:
            raise HTTPException(status_code=400, detail="Invalid X-Org-Id")

    key_org_id = getattr(request.state, "api_key_org_id", None)
    if key_org_id is not None:
        if target_org_id is not None and target_org_id != key_org_id:
            raise HTTPException(status_code=403, detail="API key cannot access this organization")
        return key_org_id

    user = require_user(user)

    if target_org_id:
        if user.is_superadmin:
            return target_org_id
        
        membership = db.query(OrgMember).filter(
            OrgMember.user_id == user.id,
            OrgMember.org_id == target_org_id
        ).first()
        
        if membership:
            # Sticky update for convenience
            if user.active_org_id != target_org_id:
                user.active_org_id = target_org_id
                db.commit()
            return target_org_id
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this organization"
            )

    # 3. Use active_org_id if set
    if user.active_org_id:
        if user.is_superadmin:
            return user.active_org_id
        membership = db.query(OrgMember).filter(
            OrgMember.user_id == user.id,
            OrgMember.org_id == user.active_org_id,
        ).first()
        if membership:
            return user.active_org_id
        raise HTTPException(status_code=403, detail="You no longer have access to the active organization")

    # 4. Fallback behavior: return the first org the user belongs to
    if user.is_superadmin:
        first_org = db.query(Org).order_by(Org.id.asc()).first()
        if first_org:
            user.active_org_id = first_org.id
            db.commit()
            return first_org.id
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No organizations exist in the system"
        )
        
    first_membership = db.query(OrgMember).filter(OrgMember.user_id == user.id).first()
    if not first_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not belong to any organizations"
        )
    
    user.active_org_id = first_membership.org_id
    db.commit()
    return first_membership.org_id

def get_current_org_id(
    request: Request,
    user: User | None = Depends(get_current_user),
    org_id: str | None = Header(default=None, alias="X-Org-Id"),
    db: Session = Depends(get_db)
) -> int:
    from app.security.usage_context import bind_workspace
    return bind_workspace(_resolve_current_org_id(request, user, org_id, db))


def require_superadmin(user: User = Depends(require_user)) -> User:
    """
    Dependency that enforces the user must be a superadmin.
    """
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a platform superadmin to perform this action."
        )
    return user
