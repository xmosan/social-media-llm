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
        print(f"DEBUG: Exchanging code for token. Code: {code[:10]}...")
        short_token = await instagram_auth_service.exchange_code_for_token(code)
        if not short_token:
            print("DEBUG: Exchange failed - no short_token returned")
            return RedirectResponse(url="/app?error=Instagram authentication failed.")

        # 3. Upgrade to long-lived token (60 days)
        print("DEBUG: Upgrading to long-lived token...")
        token_data = await instagram_auth_service.get_long_lived_token(short_token)
        if not token_data:
            print("DEBUG: Upgrade failed - no token_data returned")
            return RedirectResponse(url="/app?error=Failed to secure long-term access.")

        # --- MULTI-ACCOUNT HANDLING (TASK 6) ---
        # Perform discovery immediately to see if we can skip the selection UI
        accounts = await instagram_auth_service.discover_ig_business_account(token_data["access_token"])
        
        if not accounts:
            log_event("ig_callback_no_accounts", user_id=user.id)
            return RedirectResponse(url="/app?error=No Instagram Business accounts found on your Facebook Pages.")

        if len(accounts) == 1:
            # AUTO-SELECT SINGLE ACCOUNT
            acc_data = accounts[0]
            print(f"DEBUG: Auto-selecting single IG account: {acc_data['username']}")
            
            # Upsert logic
            existing = db.query(IGAccount).filter(IGAccount.org_id == org_id).first()
            if existing:
                existing.name = acc_data["name"]
                existing.ig_user_id = acc_data["ig_user_id"]
                existing.access_token = token_data["access_token"]
                existing.fb_page_id = acc_data["fb_page_id"]
                existing.profile_picture_url = acc_data["profile_picture_url"]
                existing.expires_at = token_data["expires_at"]
            else:
                new_acc = IGAccount(
                    org_id=org_id,
                    name=acc_data["name"],
                    ig_user_id=acc_data["ig_user_id"],
                    access_token=token_data["access_token"],
                    fb_page_id=acc_data["fb_page_id"],
                    profile_picture_url=acc_data["profile_picture_url"],
                    expires_at=token_data["expires_at"]
                )
                db.add(new_acc)
            
            user.has_connected_instagram = True
            db.commit()
            log_event("ig_connect_autoselect", user_id=user.id, ig_id=acc_data["ig_user_id"])
            return RedirectResponse(url="/app?success=Instagram connected successfully!")

        # MULTIPLE ACCOUNTS FOUND -> SHOW SELECTION UI
        print(f"DEBUG: {len(accounts)} accounts discovered. Redirecting to selection UI for User {user.id}")
        response = RedirectResponse(url="/app/select-account")
        response.set_cookie(
            key="temp_ig_token",
            value=token_data["access_token"],
            httponly=True,
            secure=True, 
            samesite="lax",
            max_age=900 
        )
        return response

    except Exception as e:
        print(f"CRITICAL ERROR in ig_callback: {str(e)}")
        log_event("ig_callback_error", error=str(e))
        traceback.print_exc()
        err_msg = f"ig_callback_exception: {type(e).__name__} - {str(e)}"
        return RedirectResponse(url=f"/app?error={err_msg}")

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
