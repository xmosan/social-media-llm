"""Workspace checks shared by request handlers and background execution."""

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import ContentItem, ContentProfile, IGAccount, MediaAsset, StyleDNA


def resource_id(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise HTTPException(status_code=422, detail="Invalid resource ID")
    try:
        parsed = int(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid resource ID")
    if not 0 < parsed <= 2_147_483_647:
        raise HTTPException(status_code=422, detail="Invalid resource ID")
    return parsed


def require_account(db: Session, org_id: int, account_id, *, active: bool = False) -> IGAccount:
    account = db.query(IGAccount).filter(
        IGAccount.id == resource_id(account_id), IGAccount.org_id == org_id,
    ).first()
    if account is None:
        raise HTTPException(status_code=403, detail="Instagram account is not in your workspace")
    if active and (not account.active or not account.ig_user_id or not account.access_token):
        raise HTTPException(status_code=422, detail="Instagram account is inactive or disconnected. Reconnect it in Settings.")
    from app.security.tester_access import require_workspace_access
    require_workspace_access(db, org_id)
    return account


def require_media(db: Session, org_id: int, asset_id) -> MediaAsset:
    asset = db.query(MediaAsset).filter(
        MediaAsset.id == resource_id(asset_id), MediaAsset.org_id == org_id,
    ).first()
    if asset is None:
        raise HTTPException(status_code=403, detail="Media asset is not in your workspace")
    if asset.ig_account_id is not None:
        require_account(db, org_id, asset.ig_account_id)
    return asset


def require_content_item(db: Session, org_id: int, item_id, *, user_id: int | None = None) -> ContentItem:
    item = db.query(ContentItem).filter(
        ContentItem.id == resource_id(item_id),
        or_(ContentItem.org_id == org_id, ContentItem.org_id.is_(None)),
        or_(ContentItem.owner_user_id.is_(None), ContentItem.owner_user_id == user_id)
        if user_id is not None else ContentItem.owner_user_id.is_(None),
    ).first()
    if item is None:
        raise HTTPException(status_code=403, detail="Content item is not available to this workspace")
    return item


def validate_automation_links(db: Session, org_id: int, values: dict) -> None:
    """Validate before assigning any part of a create/update request."""
    if values.get("ig_account_id") is not None:
        require_account(db, org_id, values["ig_account_id"], active=True)
    if values.get("media_asset_id") is not None:
        require_media(db, org_id, values["media_asset_id"])
    if values.get("content_profile_id") is not None:
        profile = db.query(ContentProfile).filter(
            ContentProfile.id == resource_id(values["content_profile_id"]), ContentProfile.org_id == org_id,
        ).first()
        if profile is None:
            raise HTTPException(status_code=403, detail="Content profile is not in your workspace")
    style_ids = list(values.get("style_dna_pool") or [])
    if values.get("style_dna_id") is not None:
        style_ids.append(values["style_dna_id"])
    for style_id in set(style_ids):
        style = db.query(StyleDNA).filter(
            StyleDNA.id == resource_id(style_id),
            or_(StyleDNA.org_id == org_id,
                (StyleDNA.org_id.is_(None) & StyleDNA.is_system_preset.is_(True))),
        ).first()
        if style is None:
            raise HTTPException(status_code=403, detail="Visual style is not available to this workspace")
