# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import IGAccount
from ..security.rbac import get_current_org_id
from ..security.auth import require_user
from ..schemas import IGAccountOut, AccountCreate, AccountUpdate
import httpx
from pydantic import BaseModel

router = APIRouter(prefix="/ig-accounts", tags=["ig-accounts"])

# --- SEAMLESS UX DISCOVERY API ---
accounts_router = APIRouter(prefix="/accounts", tags=["accounts"])

from app.services import instagram_connection as connection

@accounts_router.get("/available")
async def get_available_accounts(request: Request, db: Session = Depends(get_db),
                                 user = Depends(require_user), org_id: int = Depends(get_current_org_id)):
    _, payload = connection.read_discovery(db, request, user.id, org_id)
    return payload["accounts"]

@accounts_router.get("/connected")
async def get_connected_accounts(db: Session = Depends(get_db), user = Depends(require_user),
                                  org_id: int = Depends(get_current_org_id)):
    return [a[0] for a in db.query(IGAccount.ig_user_id).filter(IGAccount.org_id == org_id).all()]

class SelectionPayload(BaseModel):
    ig_user_id: str
    page_id: str

@accounts_router.post("/select")
async def select_accounts(payload: list[SelectionPayload], request: Request,
                          db: Session = Depends(get_db), user = Depends(require_user),
                          org_id: int = Depends(get_current_org_id)):
    ids = connection.connect_selected(db, request, user, org_id, payload)
    return {"ok": True, "account_ids": ids, "message": "Accounts connected successfully"}


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
async def get_meta_account_options(request: Request, db: Session = Depends(get_db),
                                   user = Depends(require_user), org_id: int = Depends(get_current_org_id)):
    _, payload = connection.read_discovery(db, request, user.id, org_id)
    return {"accounts": payload["accounts"]}

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
    user = Depends(require_user), org_id: int = Depends(get_current_org_id)
):
    """List all IG accounts for the current user's active organization."""
    if not org_id:
        return []
    # Order by active DESC so active shows first
    return db.query(IGAccount).filter(IGAccount.org_id == org_id).order_by(IGAccount.active.desc()).all()

@router.get("/active", response_model=IGAccountOut)
def get_active_account(
    db: Session = Depends(get_db),
    user = Depends(require_user), org_id: int = Depends(get_current_org_id)
):
    """Get the currently active account for the organization."""
    acc = db.query(IGAccount).filter(IGAccount.org_id == org_id, IGAccount.active == True).first()
    if not acc:
        # Return the existing account for reconnect UX; a GET must not reactivate it.
        acc = db.query(IGAccount).filter(IGAccount.org_id == org_id).first()
    
    if not acc:
        raise HTTPException(status_code=404, detail="No active account found")
    return acc

@router.post("/connect", response_model=IGAccountOut)
async def connect_meta_account(payload: ConnectPayload, request: Request,
                               db: Session = Depends(get_db), user = Depends(require_user),
                               org_id: int = Depends(get_current_org_id)):
    _, discovered = connection.read_discovery(db, request, user.id, org_id)
    selected = next((a for a in discovered["accounts"] if a["ig_user_id"] == payload.ig_user_id), None)
    if not selected:
        raise HTTPException(422, "Selected account was not returned by Meta.")
    ids = connection.connect_selected(db, request, user, org_id,
        [SelectionPayload(ig_user_id=selected["ig_user_id"], page_id=selected["fb_page_id"])])
    return db.get(IGAccount, ids[0])

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
        return {"healthy": False, "status": "disconnected", "detail": "Reconnect this Instagram account."}

    # Check the same Graph API version used by the publishing service.
    from app.services.publisher import GRAPH_URL
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{GRAPH_URL}/{acc.ig_user_id}", 
                params={"fields": "id,username"},
                headers={"Authorization": "Bearer " + acc.access_token},
                timeout=10, follow_redirects=False,
            )
            data = resp.json()
        except (httpx.RequestError, ValueError):
            return {"healthy": False, "status": "unavailable", "detail": "Account check is temporarily unavailable."}
        if (resp.status_code == 200 and isinstance(data, dict)
                and str(data.get("id")) == str(acc.ig_user_id) and data.get("username")):
            return {"healthy": True, "status": "connected", "username": data["username"]}
        if resp.status_code in {400, 401, 403}:
            return {"healthy": False, "status": "needs_attention", "detail": "Meta could not verify this account. Check its connection and permissions."}
        return {"healthy": False, "status": "unavailable", "detail": "Account check is temporarily unavailable."}

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
