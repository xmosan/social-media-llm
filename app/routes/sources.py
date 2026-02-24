from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.security import require_api_key
from app.models import ContentSource, ContentItem
from app.services.content_sources import import_manual_items, import_from_rss, import_from_url_list

router = APIRouter(prefix="/sources", tags=["sources"])

# NOTE: In a real production app, we would get this from the API Key or Session
def get_org_id():
    return 1

@router.post("")
def create_source(payload: dict, db: Session = Depends(get_db), _auth: str = Depends(require_api_key)):
    org_id = get_org_id()
    source_type = payload.get("source_type")
    name = payload.get("name")
    config = payload.get("config") or {}

    if source_type not in ("manual_library", "rss", "url_list", "sunnah"):
        raise HTTPException(400, "Invalid source_type")

    src = ContentSource(
        org_id=org_id, 
        source_type=source_type, 
        name=name, 
        config=config, 
        enabled=True
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return {"id": src.id, "name": src.name, "source_type": src.source_type}

@router.get("")
def list_sources(db: Session = Depends(get_db), _auth: str = Depends(require_api_key)):
    org_id = get_org_id()
    sources = db.execute(
        select(ContentSource).where(ContentSource.org_id == org_id).order_by(ContentSource.id.desc())
    ).scalars().all()
    return [{"id": s.id, "name": s.name, "source_type": s.source_type, "enabled": s.enabled} for s in sources]

@router.post("/{source_id}/import")
def import_source(source_id: int, payload: dict, db: Session = Depends(get_db), _auth: str = Depends(require_api_key)):
    org_id = get_org_id()
    src = db.execute(
        select(ContentSource).where(ContentSource.id == source_id, ContentSource.org_id == org_id)
    ).scalar_one_or_none()
    
    if not src:
        raise HTTPException(404, "Source not found")

    if src.source_type == "manual_library":
        texts = payload.get("texts") or []
        n = import_manual_items(db, org_id=org_id, source_id=src.id, texts=texts)
        return {"imported": n}

    if src.source_type == "rss":
        n = import_from_rss(db, org_id=org_id, source=src)
        return {"imported": n}

    if src.source_type == "url_list":
        n = import_from_url_list(db, org_id=org_id, source=src)
        return {"imported": n}

    return {"imported": 0, "note": "Importer not implemented for this source type yet"}

@router.get("/{source_id}/items")
def list_items(source_id: int, db: Session = Depends(get_db), _auth: str = Depends(require_api_key)):
    org_id = get_org_id()
    items = db.execute(
        select(ContentItem).where(
            ContentItem.org_id == org_id, 
            ContentItem.source_id == source_id
        ).order_by(ContentItem.id.desc()).limit(200)
    ).scalars().all()
    
    return [
        {
            "id": it.id, 
            "title": it.title, 
            "text": it.text[:200], 
            "url": it.url, 
            "use_count": it.use_count,
            "last_used_at": it.last_used_at
        } for it in items
    ]

@router.delete("/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db), _auth: str = Depends(require_api_key)):
    org_id = get_org_id()
    src = db.execute(
        select(ContentSource).where(ContentSource.id == source_id, ContentSource.org_id == org_id)
    ).scalar_one_or_none()
    
    if not src:
        raise HTTPException(404, "Source not found")
    
    db.delete(src)
    db.commit()
    return {"ok": True}
