# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db import get_db
from app.models import User, OrgMember, Org, ContentProfile
from app.schemas import UserCreate
from app.security.auth import verify_password, create_user_access_token, get_current_user, require_user, get_password_hash, clear_legacy_domain_cookie
from typing import Any
from app.services.usage_limits import check_auth_attempt, require_signup_enabled

from app.security.tester_access import user_can_sign_in
from app.services.registration import provision_creator
from app.security.rbac import is_platform_owner

class AuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def private(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                # Validation responses must not echo submitted credentials.
                detail = "Check your form fields."
                if request.url.path == "/auth/register":
                    detail += " New passwords need at least 8 characters and at most 72 UTF-8 bytes."
                return JSONResponse({"detail": detail},
                                    status_code=422, headers={"Cache-Control": "no-store"})
        return private


router = APIRouter(prefix="/auth", tags=["auth"], route_class=AuthRoute)

@router.post("/login")
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    check_auth_attempt(form_data.username)
    user = db.query(User).filter(func.lower(User.email) == func.lower(form_data.username.strip())).first()

    # Never expose account existence, account state, or the user directory.
    if (not user_can_sign_in(user) or not user.password_hash
            or not verify_password(form_data.password, user.password_hash)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Ensure active_org_id is set
    if not user.active_org_id:
        membership = db.query(OrgMember).filter(OrgMember.user_id == user.id).first()
        if membership:
            user.active_org_id = membership.org_id
            db.commit()

    access_token = create_user_access_token(user)
    
    # Set HttpOnly cookie for web clients
    clear_legacy_domain_cookie(response)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=True, # Should be True in production (HTTPS)
        max_age=7 * 24 * 60 * 60 # 7 days
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register")
def register(
    user_in: UserCreate,
    response: Response,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_signup_enabled()
    check_auth_attempt(user_in.email)
    # 1. Check if user already exists
    existing_user = db.query(User).filter(func.lower(User.email) == func.lower(user_in.email.strip())).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )

    from sqlalchemy.exc import IntegrityError
    
    try:
        new_user, new_org = provision_creator(db, email=user_in.email, name=user_in.name,
                                             password_hash=get_password_hash(user_in.password))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "A user with this email already exists.") from None

    # 5. Automatically log them in (Session Cookie)
    access_token = create_user_access_token(new_user)
    
    clear_legacy_domain_cookie(response)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=7 * 24 * 60 * 60 # 7 days
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    clear_legacy_domain_cookie(response)
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=True
    )
    return {"message": "Logged out successfully"}

from pydantic import BaseModel
class OnboardingPayload(BaseModel):
    name: str
    niche_category: str
    content_goals: str
    tone_style: str
    language: str
    banned_topics: list[str] = []

@router.patch("/complete-onboarding")
def complete_onboarding(
    payload: OnboardingPayload,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Saves the user's initial Content Profile and marks them as onboarded."""
    if user.onboarding_complete:
        raise HTTPException(status_code=400, detail="User is already onboarded.")
        
    # Get the user's default organization
    membership = db.query(OrgMember).filter(OrgMember.user_id == user.id).first()
    if not membership:
        raise HTTPException(status_code=500, detail="User has no associated organization.")
        
    org_id = membership.org_id
    
    # Check if they already have a profile
    existing = db.query(ContentProfile).filter(ContentProfile.org_id == org_id).first()
    if not existing:
        profile = ContentProfile(
            org_id=org_id,
            name=payload.name,
            niche_category=payload.niche_category,
            focus_description="Initial workspace profile",
            content_goals=payload.content_goals,
            tone_style=payload.tone_style,
            language=payload.language,
            banned_topics=payload.banned_topics
        )
        db.add(profile)
        
    user.onboarding_complete = True
    db.commit()
    
    return {"status": "success"}

@router.get("/me")
def get_current_user_profile(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    # Fetch orgs
    orgs = []
    if is_platform_owner(current_user):
        all_orgs = db.query(Org).all()
        orgs = [{"id": o.id, "name": o.name, "role": "superadmin"} for o in all_orgs]
    else:
        memberships = db.query(OrgMember).filter(OrgMember.user_id == current_user.id).all()
        for m in memberships:
            org = db.query(Org).filter(Org.id == m.org_id).first()
            if org:
                orgs.append({"id": org.id, "name": org.name, "role": m.role})
    
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "is_superadmin": is_platform_owner(current_user),
        "onboarding_complete": current_user.onboarding_complete,
        "orgs": orgs
    }
