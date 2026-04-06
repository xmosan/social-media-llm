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

router = APIRouter(prefix="/auth/instagram", tags=["auth"])

@router.get("/login")
async def instagram_login(
    request: Request,
    user: User = Depends(require_user)
):
    """Redirects the user to the Meta OAuth consent screen."""
    if not instagram_auth_service.client_id:
        log_event("ig_auth_config_missing", user_id=user.id)
        raise HTTPException(status_code=400, detail="Instagram connection is not configured properly (Missing App ID)")

    auth_url = instagram_auth_service.get_auth_url()
    
    # 3. DEBUG LOGGING: Print full URL (sanitized) to help identify App ID issues
    print(f"DEBUG: Constructing Meta OAuth URL for User {user.id}")
    print(f"DEBUG: URL: {auth_url}")
    
    log_event("ig_auth_redirect", user_id=user.id)
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def instagram_callback(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    """Handles the Meta OAuth callback."""
    org_id = user.active_org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Active Organization not found")

    try:
        # 1. Exchange code for short-lived token
        short_token = await instagram_auth_service.exchange_code_for_token(code)
        if not short_token:
            return RedirectResponse(url="/app?error=ig_auth_failed")

        # 2. Upgrade to long-lived token (60 days)
        token_data = await instagram_auth_service.get_long_lived_token(short_token)
        if not token_data:
            return RedirectResponse(url="/app?error=ig_token_upgrade_failed")

        # 3. Discover Instagram Business account linked to user's FB Pages
        ig_details = await instagram_auth_service.discover_ig_business_account(token_data["access_token"])
        if not ig_details:
            return RedirectResponse(url="/app?error=ig_account_not_found")

        # 4. Check if account already exists in this org, otherwise create
        acc = db.query(IGAccount).filter(
            IGAccount.org_id == org_id,
            IGAccount.ig_user_id == ig_details["ig_user_id"]
        ).first()

        if not acc:
            acc = IGAccount(
                org_id=org_id,
                ig_user_id=ig_details["ig_user_id"],
                name=ig_details["username"] or ig_details["name"] or "Instagram Account"
            )
            db.add(acc)
            db.flush()

        # Update token and metadata
        acc.access_token = token_data["access_token"]
        acc.expires_at = token_data["expires_at"]
        acc.fb_page_id = ig_details["fb_page_id"]
        acc.active = True
        
        # Mark user as having connected IG
        user.has_connected_instagram = True
        
        db.commit()
        log_event("ig_connect_success", user_id=user.id, ig_user_id=acc.ig_user_id)
        
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
