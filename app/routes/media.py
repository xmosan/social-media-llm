import os, shutil
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..db import get_db
from ..config import settings
from ..models import MediaAsset
from ..schemas import MediaAssetOut, MediaAssetCreate
from ..security import require_api_key
from datetime import datetime, timezone

router = APIRouter(prefix="/media-assets", tags=["media"])

def _utcnow():
    return datetime.now(timezone.utc)

def _ensure_uploads_dir():
    os.makedirs(settings.uploads_dir, exist_ok=True)

@router.get("", response_model=list[MediaAssetOut])
def list_media(
    ig_account_id: int | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
):
    stmt = select(MediaAsset).where(MediaAsset.org_id == org_id).order_by(MediaAsset.created_at.desc())
    
    if ig_account_id:
        stmt = stmt.where(MediaAsset.ig_account_id == ig_account_id)
    
    # Simple tag filtering
    assets = db.execute(stmt).scalars().all()
    if tag:
        assets = [a for a in assets if tag in (a.tags or [])]
    
    return assets

@router.post("", response_model=MediaAssetOut)
def upload_media_asset(
    image: UploadFile = File(...),
    ig_account_id: int | None = Form(None),
    tags: str = Form("[]"), # JSON string
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
):
    import json
    _ensure_uploads_dir()
    
    filename = f"lib_{int(_utcnow().timestamp())}_{image.filename}"
    local_path = os.path.join(settings.uploads_dir, filename)

    with open(local_path, "wb") as f:
        shutil.copyfileobj(image.file, f)

    public_url = f"{settings.public_base_url}/uploads/{filename}"
    
    try:
        tags_list = json.loads(tags)
    except:
        tags_list = []

    new_asset = MediaAsset(
        org_id=org_id,
        ig_account_id=ig_account_id,
        url=public_url,
        storage_path=local_path,
        tags=tags_list
    )
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    return new_asset

@router.delete("/{asset_id}")
def delete_media_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key),
):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.org_id == org_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.storage_path and os.path.exists(asset.storage_path):
        try:
            os.remove(asset.storage_path)
        except Exception as e:
            print(f"Error removing file: {e}")

    db.delete(asset)
    db.commit()
    return {"ok": True}
