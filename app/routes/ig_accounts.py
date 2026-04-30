# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import IGAccount
from ..security.rbac import get_current_org_id
from ..security.auth import require_user
from ..schemas import IGAccountOut, AccountCreate, AccountUpdate
import httpx
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/ig-accounts", tags=["ig-accounts"])

# --- SEAMLESS UX DISCOVERY API ---
accounts_router = APIRouter(prefix="/accounts", tags=["accounts"])

@accounts_router.get("/available")
async def get_available_accounts(request: Request, user = Depends(require_user)):
    """Fetch discovered accounts from session storage."""
    return request.session.get("discovered_accounts", [])

@accounts_router.get("/connected")
async def get_connected_accounts(db: Session = Depends(get_db), user = Depends(require_user)):
    """Fetch IDs of accounts already connected to the current org."""
    if not user.active_org_id:
        return []
    accounts = db.query(IGAccount.ig_user_id).filter(IGAccount.org_id == user.active_org_id).all()
    return [a[0] for a in accounts]

class SelectionPayload(BaseModel):
    ig_user_id: str
    page_id: str

@accounts_router.post("/select")
async def select_accounts(
    payload: list[SelectionPayload],
    request: Request,
    db: Session = Depends(get_db),
    user = Depends(require_user)
):
    """Persist a list of discovery selections to the database."""
    accounts = request.session.get("discovered_accounts", [])
    token = request.session.get("temp_ig_token")
    
    if not token or not accounts:
        raise HTTPException(status_code=401, detail="Meta session expired. Please reconnect.")
        
    org_id = user.active_org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No active organization found.")

    # Mark existing active accounts as inactive if we're adding new ones
    db.query(IGAccount).filter(IGAccount.org_id == org_id).update({"active": False})
    
    for item in payload:
        selected = next((a for a in accounts if a["ig_user_id"] == item.ig_user_id), None)
        if not selected:
            continue

        # Upsert
        acc = db.query(IGAccount).filter(
            IGAccount.org_id == org_id,
            IGAccount.ig_user_id == selected["ig_user_id"]
        ).first()
        
        if not acc:
            acc = IGAccount(
                org_id=org_id,
                ig_user_id=selected["ig_user_id"],
                username=selected.get("username"),
                name=selected.get("name") or selected["username"] or "Instagram Account",
                profile_picture_url=selected.get("profile_picture_url")
            )
            db.add(acc)
        
        acc.access_token = token
        acc.username = selected.get("username")
        acc.fb_page_id = selected["fb_page_id"]
        acc.profile_picture_url = selected.get("profile_picture_url")
        acc.expires_at = datetime.now(timezone.utc) + timedelta(days=60)
        acc.active = True # Last one in loop will be the final active one
    
    user.has_connected_instagram = True
    db.commit()
    
    # Cleanup session
    request.session.pop("discovered_accounts", None)
    request.session.pop("temp_ig_token", None)
    
    return {"ok": True, "message": "Accounts connected successfully"}


@router.get("", response_model=list[IGAccountOut])
def list_accounts(
    request: Request,
    db: Session = Depends(get_db),
    user = Depends(require_user)
):
    """List all IG accounts for the organization (or all for superadmin)."""
    org_id_header = request.headers.get("X-Org-Id")
    
    if user.is_superadmin and not org_id_header:
        return db.query(IGAccount).all()
        
    org_id = get_current_org_id(request=request, user=user, org_id=org_id_header, db=db)
    return db.query(IGAccount).filter(IGAccount.org_id == org_id).all()

@router.post("", response_model=IGAccountOut)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Add a new IG account to the organization (Legacy Manual - Restricted)."""
    # Prohibit manual creation now that OAuth is implemented
    raise HTTPException(
        status_code=400, 
        detail="Manual account creation is disabled. Please use the 'Connect Instagram' button on the dashboard to link via Meta OAuth."
    )

@router.patch("/{account_id}", response_model=IGAccountOut)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Update an IG account's settings."""
    acc = db.query(IGAccount).filter(
        IGAccount.id == account_id,
        IGAccount.org_id == org_id
    ).first()
    
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # We only allow updating basic settings, NOT tokens/IDs manually
    data = payload.dict(exclude_unset=True)
    restricted_fields = ["ig_user_id", "access_token"]
    for k, v in data.items():
        if k not in restricted_fields:
            setattr(acc, k, v)
    
    db.commit()
    db.refresh(acc)
    return acc

@router.post("/{account_id}/toggle", response_model=IGAccountOut)
def toggle_account(
    account_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Enable/Disable an IG account."""
    acc = db.query(IGAccount).filter(
        IGAccount.id == account_id,
        IGAccount.org_id == org_id
    ).first()
    
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    acc.active = not acc.active
    db.commit()
    db.refresh(acc)
    return acc

@router.get("/meta-options", response_model=dict)
async def get_meta_account_options(
    request: Request,
    user = Depends(require_user)
):
    """Fetch available IG accounts from Meta using the temporary token cookie."""
    token = request.cookies.get("temp_ig_token")
    if not token:
        raise HTTPException(status_code=401, detail="Meta session expired. Please try connecting again.")
    
    from app.services.instagram_auth import instagram_auth_service
    accounts = await instagram_auth_service.discover_ig_business_account(token)
    return {"accounts": accounts}

class ConnectPayload(BaseModel):
    ig_user_id: str

@router.post("/set-active/{account_id}", response_model=IGAccountOut)
def set_active_account(
    account_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Sets a specific account as the 'active' one for the organization."""
    # 1. Unset all current active for this org
    db.query(IGAccount).filter(IGAccount.org_id == org_id).update({"active": False})
    
    # 2. Set target as active
    acc = db.query(IGAccount).filter(
        IGAccount.id == account_id,
        IGAccount.org_id == org_id
    ).first()
    
    if not acc:
        db.rollback()
        raise HTTPException(status_code=404, detail="Account not found")
        
    acc.active = True
    db.commit()
    db.refresh(acc)
    return acc

@router.get("/me", response_model=list[IGAccountOut])
def get_my_accounts(
    db: Session = Depends(get_db),
    user = Depends(require_user)
):
    """List all IG accounts for the current user's active organization."""
    org_id = user.active_org_id
    if not org_id:
        return []
    # Order by active DESC so active shows first
    return db.query(IGAccount).filter(IGAccount.org_id == org_id).order_by(IGAccount.active.desc()).all()

@router.get("/active", response_model=IGAccountOut)
def get_active_account(
    db: Session = Depends(get_db),
    user = Depends(require_user)
):
    """Get the currently active account for the organization."""
    org_id = user.active_org_id
    acc = db.query(IGAccount).filter(IGAccount.org_id == org_id, IGAccount.active == True).first()
    if not acc:
        # Fallback to the first one found if none marked active
        acc = db.query(IGAccount).filter(IGAccount.org_id == org_id).first()
        if acc:
            acc.active = True
            db.commit()
            db.refresh(acc)
    
    if not acc:
        raise HTTPException(status_code=404, detail="No active account found")
    return acc

@router.post("/connect", response_model=IGAccountOut)
async def connect_meta_account(
    payload: ConnectPayload,
    request: Request,
    db: Session = Depends(get_db),
    user = Depends(require_user)
):
    """Persist the selected IG account to the database."""
    token = request.cookies.get("temp_ig_token")
    if not token:
        raise HTTPException(status_code=401, detail="Meta session expired.")
    
    org_id = user.active_org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Active Organization not found")

    from app.services.instagram_auth import instagram_auth_service
    # Re-discover to get full details (safe and ensures data integrity)
    all_discovery = await instagram_auth_service.discover_ig_business_account(token)
    selected = next((a for a in all_discovery if a["ig_user_id"] == payload.ig_user_id), None)
    
    if not selected:
        raise HTTPException(status_code=404, detail="Selected account not found in your Meta profile")

    # Set all others to inactive if we are connecting a new one
    db.query(IGAccount).filter(IGAccount.org_id == org_id).update({"active": False})

    # Check if exists
    acc = db.query(IGAccount).filter(
        IGAccount.org_id == org_id,
        IGAccount.ig_user_id == selected["ig_user_id"]
    ).first()

    if not acc:
        acc = IGAccount(
            org_id=org_id,
            ig_user_id=selected["ig_user_id"],
            username=selected.get("username"),
            name=selected.get("name") or selected["username"] or "Instagram Account",
            profile_picture_url=selected.get("profile_picture_url")
        )
        db.add(acc)
    
    # Update latest token and metadata
    acc.access_token = token
    acc.username = selected.get("username")
    acc.fb_page_id = selected["fb_page_id"]
    acc.profile_picture_url = selected.get("profile_picture_url")
    acc.expires_at = datetime.now(timezone.utc) + timedelta(days=60) # Standard Meta LLT
    acc.active = True
    
    user.has_connected_instagram = True
    db.commit()
    db.refresh(acc)
    
    return acc

@router.get("/{account_id}/health")
async def check_account_health(
    account_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Verifies if the stored Meta access token is still valid."""
    acc = db.query(IGAccount).filter(IGAccount.id == account_id, IGAccount.org_id == org_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    if not acc.access_token:
        return {"healthy": False, "detail": "No token stored"}

    from .instagram_auth import GRAPH_URL
    async with httpx.AsyncClient() as client:
        try:
            # Simple check against /me
            resp = await client.get(
                f"{GRAPH_URL}/{acc.ig_user_id}", 
                params={"fields": "id,username", "access_token": acc.access_token},
                timeout=10
            )
            if resp.status_code == 200:
                return {"healthy": True, "username": resp.json().get("username")}
            
            err_data = resp.json()
            err_msg = err_data.get("error", {}).get("message", "Token rejected by Meta")
            return {"healthy": False, "detail": err_msg}
        except Exception as e:
            return {"healthy": False, "detail": str(e)}

@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Remove an IG account."""
    acc = db.query(IGAccount).filter(
        IGAccount.id == account_id,
        IGAccount.org_id == org_id
    ).first()
    
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Optional: ensure no scheduled posts are left? 
    # For now just delete.
    db.delete(acc)
    db.commit()
    return {"ok": True}
