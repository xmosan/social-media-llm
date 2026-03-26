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

oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.google_client_id if hasattr(settings, 'google_client_id') else "",
    client_secret=settings.google_client_secret if hasattr(settings, 'google_client_secret') else "",
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@router.get("/login")
async def google_login(request: Request):
    """Redirects the user to the Google OAuth consent screen."""
    try:
        print("AUTH DIAGNOSTIC: Initiating Google OAuth redirect...")
        if not oauth.google.client_id or not oauth.google.client_secret:
            print("AUTH DIAGNOSTIC: Google Client ID/Secret missing or empty")
            return RedirectResponse(url="/login?error=google_config_missing")
        
        # Use configured redirect URI if present, otherwise generate dynamically
        if settings.google_redirect_uri:
            redirect_uri = settings.google_redirect_uri
        else:
            redirect_uri = request.url_for('google_auth')
            # Force HTTPS for production redirects
            if "railway.app" in str(request.url) or request.headers.get("x-forwarded-proto") == "https":
                redirect_uri = str(redirect_uri).replace("http://", "https://")
        
        print(f"AUTH DIAGNOSTIC: Google redirect_uri: {redirect_uri}")
        return await oauth.google.authorize_redirect(request, str(redirect_uri))
    except Exception as e:
        print(f"AUTH DIAGNOSTIC: Google Login start ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/callback")
async def google_auth(request: Request, db: Session = Depends(get_db)):
    """Handles the OAuth callback, provisions users/orgs, and sets the JWT cookie."""
    try:
        print("AUTH DIAGNOSTIC: Google OAuth callback received")
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            print("AUTH DIAGNOSTIC: Google user_info is missing")
            raise Exception("Failed to fetch user info from Google")
        print(f"AUTH DIAGNOSTIC: Google user info: {user_info.get('email')}")
    except Exception as e:
        # LOGGING SENSITIVE DATA SAFELY FOR DIAGNOSTICS
        cid = (settings.google_client_id or "")[:10] + "..."
        sec = (settings.google_client_secret or "")[:5] + "..."
        uri = settings.google_redirect_uri or "AUTO"
        print(f"AUTH DIAGNOSTIC: Google OAuth callback ERROR: {e}")
        print(f"AUTH DIAGNOSTIC: Using CID: {cid}, SEC: {sec}, URI: {uri}")
        raise HTTPException(status_code=400, detail=f"OAuth verification failed: {e}")

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
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True, # MUST be True in production (HTTPS)
        samesite="lax",
        max_age=int(access_token_expires.total_seconds()),
        path="/"
    )
    return response
