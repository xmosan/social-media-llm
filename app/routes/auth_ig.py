# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, IGAccount
from app.security.auth import require_user
from app.services.instagram_auth import instagram_auth_service
from app.security.rbac import get_current_org_id
from app.logging_setup import log_event
import traceback
import os

router = APIRouter(prefix="/auth/instagram", tags=["auth"])
# ALIAS ROUTER: To handle legacy /auth/meta/callback without breaking existing config
meta_alias_router = APIRouter(prefix="/auth/meta", tags=["auth"])

@router.get("/login")
async def instagram_login(
    request: Request,
    user: User = Depends(require_user)
):
    """Redirects the user to the Meta OAuth consent screen."""
    from app.config import settings
    
    # 1. LIVE DIAGNOSTIC: Check settings and raw env
    app_id = settings.fb_app_id or "MISSING"
    log_event("ig_auth_attempt", user_id=user.id, app_id_present=bool(settings.fb_app_id))
    
    # Debug print for server logs
    print(f"DEBUG: IG Login Attempt for User {user.id}")
    print(f"DEBUG: settings.fb_app_id: {app_id}")
    print(f"DEBUG: META_APP_ID env: {os.getenv('META_APP_ID', 'NOT SET')}")

    if not settings.fb_app_id:
        log_event("ig_auth_config_missing", user_id=user.id)
        raise HTTPException(status_code=400, detail=f"Instagram connection is not configured properly (Missing App ID). Detected Env: {os.getenv('META_APP_ID', 'NOT SET')}")

    # 4. FINAL SAFETY CHECK: Ensure the redirect URI is correctly resolved
    redirect_uri = instagram_auth_service.redirect_uri
    print(f"DEBUG: Final Meta Redirect URI: {redirect_uri}")
    
    if "app.sabeelstudio.com" not in redirect_uri and "localhost" not in redirect_uri and "127.0.0.1" not in redirect_uri:
        log_event("ig_auth_bad_redirect", user_id=user.id, redirect=redirect_uri)
        raise HTTPException(
            status_code=400, 
            detail=f"Instagram connection is not configured correctly. The redirect URL '{redirect_uri}' does not match the allowed domains."
        )

    auth_url = instagram_auth_service.get_auth_url()
    
    log_event("ig_auth_redirect", user_id=user.id)
    return RedirectResponse(url=auth_url)

@router.get("/callback")
@meta_alias_router.get("/callback")
async def instagram_callback(
    request: Request,
    code: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    """Handles the Meta OAuth callback."""
    # 1. HANDLE CANCEL OR ERROR FROM META
    error = request.query_params.get("error")
    if error or not code:
        log_event("ig_auth_cancelled", user_id=user.id, error=error)
        msg = "Instagram connection was not completed. Please try again."
        return RedirectResponse(url=f"/app?error={msg}")

    org_id = user.active_org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Active Organization not found")

    try:
        # 2. Exchange code for short-lived token
        short_token = await instagram_auth_service.exchange_code_for_token(code)
        if not short_token:
            return RedirectResponse(url="/app?error=Instagram authentication failed.")

        # 3. Upgrade to long-lived token (60 days)
        token_data = await instagram_auth_service.get_long_lived_token(short_token)
        if not token_data:
            return RedirectResponse(url="/app?error=Failed to secure long-term access.")

        # 4. Discover Instagram Business accounts linked to user's Professional Setup
        discovered_accounts = await instagram_auth_service.discover_ig_business_account(token_data["access_token"])
        if not discovered_accounts:
            msg = "No linked Instagram account found. Please ensure your Professional account is correctly configured and try again."
            return RedirectResponse(url=f"/app?error={msg}")

        # 5. Process and store each discovered account
        print(f"DEBUG: Processing {len(discovered_accounts)} accounts for Org ID: {org_id}")
        
        for ig_details in discovered_accounts:
            # Check if account already exists in this org
            acc = db.query(IGAccount).filter(
                IGAccount.org_id == org_id,
                IGAccount.ig_user_id == ig_details["ig_user_id"]
            ).first()

            if not acc:
                print(f"DEBUG: Creating new IGAccount entry for @{ig_details['username']}")
                acc = IGAccount(
                    org_id=org_id,
                    ig_user_id=ig_details["ig_user_id"],
                    name=ig_details["username"] or ig_details["name"] or "Instagram Account"
                )
                db.add(acc)
                db.flush() # Ensure ID is generated
            
            # Update token and metadata
            print(f"DEBUG: Updating access token for @{ig_details['username']}")
            acc.access_token = token_data["access_token"]
            acc.expires_at = token_data["expires_at"]
            acc.fb_page_id = ig_details["fb_page_id"]
            acc.active = True
        
        # Mark user as having connected IG
        user.has_connected_instagram = True
        
        db.commit()
        print(f"DEBUG: Successfully committed all accounts to database for User {user.id}")
        log_event("ig_connect_success", user_id=user.id, count=len(discovered_accounts))
        
        return RedirectResponse(url="/app?success=ig_connected")

    except Exception as e:
        log_event("ig_callback_error", error=str(e))
        traceback.print_exc()
        return RedirectResponse(url="/app?error=ig_callback_exception")

@router.post("/disconnect")
async def instagram_disconnect(
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    """Disconnects the primary Instagram account for the current org."""
    org_id = user.active_org_id
    acc = db.query(IGAccount).filter(IGAccount.org_id == org_id).first()
    
    if acc:
        db.delete(acc)
        
        # Check if user has any other IG accounts in other orgs? 
        # For simplicity, we just reset the flag for the current session/context
        user.has_connected_instagram = False
        
        db.commit()
        log_event("ig_disconnect_success", user_id=user.id)
        return {"ok": True}
    
    return {"ok": False, "error": "No account connected"}
