# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from app.db import get_db
from app.models import User, Org, OrgMember
from app.security.auth import create_access_token
from app.config import settings
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
    """Redirects the user to the Google OAuth consent screen."""
    try:
        from app.main import is_prod
        print("AUTH DIAGNOSTIC: Initiating Google OAuth redirect...")
        if not oauth.google.client_id or not oauth.google.client_secret:
            print("AUTH DIAGNOSTIC: Google Client ID/Secret missing or empty")
            return RedirectResponse(url="/login?error=google_config_missing")
        
        # 1. DYNAMIC REDIRECT RESOLUTION: Prefer explicit GOOGLE_REDIRECT_URI, fallback to Base URL + /auth/google/callback
        redirect_uri = settings.google_redirect_uri or f"{settings.public_base_url.rstrip('/')}/auth/google/callback"
        
        # 2. SCHEME STABILIZATION: Force HTTPS in production
        if is_prod or request.headers.get("x-forwarded-proto") == "https":
            redirect_uri = str(redirect_uri).replace("http://", "https://")
            # This is critical for Authlib/Starlette session matching
            request.scope['scheme'] = 'https'
        
        print(f"AUTH DIAGNOSTIC: Final Google redirect_uri: {redirect_uri}")
        response = await oauth.google.authorize_redirect(request, str(redirect_uri))
        
        # 3. DEBUG: Check if session state was actually set by Authlib
        # Note: Authlib sets '_google_state' in the session during authorize_redirect
        sess_state = request.session.get('_google_state')
        print(f"AUTH DIAGNOSTIC: Google OAuth State generated: {sess_state}")
        
        return response
    except Exception as e:
        print(f"AUTH DIAGNOSTIC: Google Login start ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to start Google Auth: {str(e)}")

@router.get("/callback")
async def google_auth(request: Request, db: Session = Depends(get_db)):
    """Handles the OAuth callback, provisions users/orgs, and sets the JWT cookie."""
    from app.main import is_prod
    from authlib.integrations.base_client.errors import MismatchedStateError
    
    # 1. DYNAMIC REDIRECT RESOLUTION: Must match the one used in google_login
    redirect_uri = settings.google_redirect_uri or f"{settings.public_base_url.rstrip('/')}/auth/google/callback"
    
    # 2. SCHEME STABILIZATION
    if is_prod or request.headers.get("x-forwarded-proto") == "https":
        redirect_uri = str(redirect_uri).replace("http://", "https://")
        request.scope['scheme'] = 'https'

    try:
        sess_state = request.session.get('_google_state')
        returned_state = request.query_params.get('state')
        
        print(f"AUTH DIAGNOSTIC: Google OAuth callback received.")
        print(f"AUTH DIAGNOSTIC: Session State: {sess_state}")
        print(f"AUTH DIAGNOSTIC: Return State: {returned_state}")
        print(f"AUTH DIAGNOSTIC: Using Redirect URI: {redirect_uri}")
        
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            print("AUTH DIAGNOSTIC: Google user_info is missing")
            raise Exception("Failed to fetch user info from Google")
        print(f"AUTH DIAGNOSTIC: Google user info: {user_info.get('email')}")
    except MismatchedStateError:
        print("AUTH DIAGNOSTIC: CSRF State Mismatch Detected")
        fail_msg = "OAuth session expired or domain mismatch detected. Please ensure you are logging in from app.sabeelstudio.com and try again."
        raise HTTPException(status_code=400, detail=fail_msg)
    except Exception as e:
        # LOGGING SENSITIVE DATA SAFELY FOR DIAGNOSTICS
        diag_msg = f"OAuth verification failed: {str(e)}"
        print(f"AUTH DIAGNOSTIC: {diag_msg}")
        print(f"AUTH DIAGNOSTIC: Session keys present: {list(request.session.keys())}")
        raise HTTPException(status_code=400, detail=diag_msg)

    google_id = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name")

    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by Google")

    # 1. Match or Create User
    user = db.query(User).filter((User.google_id == google_id) | (User.email == email)).first()
    
    if not user:
        print(f"AUTH DIAGNOSTIC: Creating NEW user via Google: {email}")
        # Create new User
        user = User(
            email=email,
            name=name,
            google_id=google_id,
            onboarding_complete=False
        )
        db.add(user)
        db.flush() # get user.id

        # Provision personal Organization for the new User
        org_name = f"{name}'s Workspace" if name else "Personal Workspace"
        org = Org(name=org_name)
        db.add(org)
        db.flush() # get org.id
        
        # Link User as Owner
        member = OrgMember(org_id=org.id, user_id=user.id, role="owner")
        db.add(member)
        
        db.commit()
        db.refresh(user)
    else:
        print(f"AUTH DIAGNOSTIC: Found existing user via Google: {user.email}")
        # User exists, optionally synchronize google_id if matched via email
        if not user.google_id:
            user.google_id = google_id
            db.commit()

    # 2. Issue Cookie-based JWT
    access_token_expires = timedelta(days=7)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    print(f"AUTH DIAGNOSTIC: Google login successful for {user.email}. Setting cookie...")
    response = RedirectResponse(url="/app")
    
    # 3. DOMAIN STABILIZATION: Extract domain for cookie
    from urllib.parse import urlparse
    domain = urlparse(settings.public_base_url).hostname if is_prod else None
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_prod, # MUST be True in production (HTTPS)
        samesite="lax",
        max_age=int(access_token_expires.total_seconds()),
        path="/",
        domain=domain
    )
    return response
