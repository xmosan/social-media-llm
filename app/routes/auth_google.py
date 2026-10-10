# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from app.db import get_db
from app.models import User, Org, OrgMember
from app.security.auth import create_user_access_token, clear_legacy_domain_cookie
from app.config import settings
from app.security.tester_access import user_can_sign_in
from app.services.registration import provision_creator
from datetime import timedelta

router = APIRouter(prefix="/auth/google", tags=["auth"])

# PROACTIVE: Ensure no whitespace in credentials
GLOBAL_GOOGLE_ID = (settings.google_client_id or "").strip()
GLOBAL_GOOGLE_SECRET = (settings.google_client_secret or "").strip()

oauth = OAuth()
oauth.register(
    name='google',
    client_id=GLOBAL_GOOGLE_ID,
    client_secret=GLOBAL_GOOGLE_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@router.get("/login")
async def google_login(request: Request):
    """Existing creators can still sign in during private preview."""
    from app.services.usage_limits import check_auth_attempt
    check_auth_attempt()
    if not oauth.google.client_id or not oauth.google.client_secret:
        return RedirectResponse(url="/login?error=google_config_missing")
    try:
        from app.main import is_prod
        redirect_uri = settings.google_redirect_uri or f"{settings.public_base_url.rstrip('/')}/auth/google/callback"
        if is_prod:
            redirect_uri = str(redirect_uri).replace("http://", "https://")
            request.scope['scheme'] = 'https'
        return await oauth.google.authorize_redirect(request, str(redirect_uri))
    except Exception:
        # Do not log OAuth state, tokens, email addresses or provider bodies.
        raise HTTPException(503, "Google sign-in is unavailable. Please try again shortly.") from None


@router.get("/callback")
async def google_auth(request: Request, db: Session = Depends(get_db)):
    from app.main import is_prod
    from app.services.usage_limits import check_auth_attempt
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    check_auth_attempt()
    if is_prod:
        request.scope['scheme'] = 'https'
    try:
        # Authlib verifies the OAuth state and signed OIDC identity.
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo') or {}
    except Exception:
        raise HTTPException(400, "Google sign-in could not be verified. Please start again from the sign-in page.") from None

    google_id, email = user_info.get("sub"), user_info.get("email")
    if (not isinstance(google_id, str) or not google_id.strip()
            or not isinstance(email, str) or not email.strip()
            or user_info.get("email_verified") is not True):
        raise HTTPException(400, "A verified Google email is required to sign in.")
    email = email.strip()
    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
    if user:
        if not user_can_sign_in(user) or (user.google_id and user.google_id != google_id):
            raise HTTPException(403, "This account cannot sign in. Please contact support.")
        if not user.google_id:
            user.google_id = google_id
    else:
        if not settings.signup_enabled:
            return RedirectResponse(url="/login?error=registration_closed", status_code=303)
        name = user_info.get("name") or "Creator"
        try:
            user, org = provision_creator(db, email=email, name=name, google_id=google_id)
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Sign-in changed while processing. Please start again.") from None
    if not user.active_org_id:
        member = db.query(OrgMember).filter(OrgMember.user_id == user.id).first()
        if member:
            user.active_org_id = member.org_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Sign-in changed while processing. Please start again.") from None
    expires = timedelta(days=7)
    access_token = create_user_access_token(user, expires_delta=expires)
    response = RedirectResponse(url="/app")
    clear_legacy_domain_cookie(response)
    # Match email login/logout's host-only secure cookie.
    response.set_cookie(key="access_token", value=access_token, httponly=True,
                        secure=True, samesite="lax", max_age=int(expires.total_seconds()), path="/")
    return response
