from fastapi import Request, HTTPException, Depends, Header, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, OrgMember, Org
from app.security.auth import require_user

def get_current_org_id(
    request: Request,
    user: User = Depends(require_user),
    org_id: str | None = Header(default=None, alias="X-Org-Id"),
    db: Session = Depends(get_db)
) -> int:
    """
    Drop-in replacement for require_api_key.
    Returns the org_id the request is authorized for based on user membership and scoping.
    """
    # 1. Check if the auth system already determined an org_id via legacy API Key compat mode
    if hasattr(request.state, "api_key_org_id"):
        return request.state.api_key_org_id

    # 2. Check explicitly requested org
    target_org_id = None
    if org_id:
        try:
            target_org_id = int(org_id)
        except ValueError:
            pass

    if target_org_id:
        if user.is_superadmin:
            return target_org_id
        
        membership = db.query(OrgMember).filter(
            OrgMember.user_id == user.id,
            OrgMember.org_id == target_org_id
        ).first()
        
        if membership:
            return target_org_id
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this organization"
            )

    # 3. Default behavior: return the first org the user belongs to
    if user.is_superadmin:
        first_org = db.query(Org).order_by(Org.id.asc()).first()
        if first_org:
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
        
    return first_membership.org_id

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
