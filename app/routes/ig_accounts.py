from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import IGAccount
from ..security import require_api_key
from ..schemas import IGAccountOut, AccountCreate, AccountUpdate

router = APIRouter(prefix="/ig-accounts", tags=["ig-accounts"])

@router.get("", response_model=list[IGAccountOut])
def list_accounts(
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key)
):
    """List all IG accounts for the organization."""
    return db.query(IGAccount).filter(IGAccount.org_id == org_id).all()

@router.post("", response_model=IGAccountOut)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key)
):
    """Add a new IG account to the organization."""
    acc = IGAccount(
        org_id=org_id,
        name=payload.name,
        ig_user_id=payload.ig_user_id,
        access_token=payload.access_token,
        timezone=payload.timezone,
        daily_post_time=payload.daily_post_time,
        active=True
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc

@router.patch("/{account_id}", response_model=IGAccountOut)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key)
):
    """Update an IG account's settings."""
    acc = db.query(IGAccount).filter(
        IGAccount.id == account_id,
        IGAccount.org_id == org_id
    ).first()
    
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(acc, k, v)
    
    db.commit()
    db.refresh(acc)
    return acc

@router.post("/{account_id}/toggle", response_model=IGAccountOut)
def toggle_account(
    account_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key)
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

@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key)
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
