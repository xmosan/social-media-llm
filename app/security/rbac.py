# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import Request, Response, HTTPException, Depends, Header, status
from urllib.parse import urlsplit
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, OrgMember, Org
from app.security.auth import get_current_user, require_user
from app.config import settings
from app.security.tester_access import user_can_sign_in

OWNER_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                 "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"}


def is_platform_owner(user: User | None) -> bool:
    owner = (settings.platform_owner_email or "").strip().casefold()
    return bool(owner and user_can_sign_in(user) and user.is_superadmin
                and (user.email or "").strip().casefold() == owner)

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
        if is_platform_owner(user):
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
        if is_platform_owner(user):
            return user.active_org_id
        membership = db.query(OrgMember).filter(
            OrgMember.user_id == user.id,
            OrgMember.org_id == user.active_org_id,
        ).first()
        if membership:
            return user.active_org_id
        raise HTTPException(status_code=403, detail="You no longer have access to the active organization")

    # 4. Fallback behavior: return the first org the user belongs to
    if is_platform_owner(user):
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
    from app.security.tester_access import require_workspace_access
    resolved = _resolve_current_org_id(request, user, org_id, db)
    require_workspace_access(db, resolved)
    return bind_workspace(resolved)


def require_superadmin(user: User | None = Depends(get_current_user), request: Request = None,
                       response: Response = None) -> User:
    """Existing platform routes now require the single configured owner account.

    Keep the name for callers; a legacy role flag alone no longer grants access.
    Service keys cannot become user principals in get_current_user.
    """
    if user is None:
        raise HTTPException(401, "Not authenticated", headers={**OWNER_HEADERS, "WWW-Authenticate": "Bearer"})
    if not is_platform_owner(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This area is available only to the Sabeel owner.", headers=OWNER_HEADERS,
        )
    if response is not None:
        response.headers.update(OWNER_HEADERS)
    if request is not None and request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get("access_token"):
        try:
            expected = urlsplit(settings.public_base_url)
            actual = urlsplit(request.headers.get("origin", ""))
            valid_origin = (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc) and actual.path in {"", "/"}
        except ValueError:
            valid_origin = False
        if not valid_origin:
            raise HTTPException(403, "Open this page in Sabeel before continuing.", headers=OWNER_HEADERS)
    return user
