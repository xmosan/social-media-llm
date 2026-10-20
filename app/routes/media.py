# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..db import get_db
from ..config import settings
from ..models import MediaAsset
from ..schemas import MediaAssetOut, MediaAssetCreate
from ..security.rbac import get_current_org_id
from ..security.ownership import require_account
from ..security.uploads import save_image_upload
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
    org_id: int = Depends(get_current_org_id),
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
    org_id: int = Depends(get_current_org_id),
):
    import json
    if ig_account_id is not None:
        require_account(db, org_id, ig_account_id)
    if image.content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise HTTPException(status_code=400, detail="Use a PNG, JPG, or WEBP image")
    try:
        tags_list = json.loads(tags)
        if (not isinstance(tags_list, list) or len(tags_list) > 30
                or any(not isinstance(t, str) or len(t) > 100 for t in tags_list)):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Use up to 30 short text tags.") from None
    _ensure_uploads_dir()
    filename, local_path = save_image_upload(image, settings.uploads_dir, "lib")
    public_url = f"{settings.public_base_url}/uploads/{filename}"

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
    org_id: int = Depends(get_current_org_id),
):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.org_id == org_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    local = Path(asset.storage_path).resolve() if asset.storage_path else None
    if local and local.is_relative_to(Path(settings.uploads_dir).resolve()) and local.is_file():
        try:
            local.unlink()
        except Exception as e:
            pass  # A failed local cleanup must not expose server paths.

    db.delete(asset)
    db.commit()
    return {"ok": True}
