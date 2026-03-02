# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from app.db import get_db
from app.models import ContentSource, ContentItem, User
from app.schemas import (
    ContentSourceOut, ContentSourceCreate, ContentSourceUpdate,
    ContentItemOut, ContentItemCreate, ContentItemUpdate
)
from app.security.rbac import require_superadmin
from app.services.library_service import validate_entry_meta

router = APIRouter(prefix="/api/admin/library/global", tags=["admin_global_library"])

# --- GLOBAL SOURCES ---

@router.get("/sources", response_model=List[ContentSourceOut])
def list_global_sources(
    query: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Lists all global library sources (org_id IS NULL)."""
    q = db.query(ContentSource).filter(ContentSource.org_id == None)
    if query:
        q = q.filter(ContentSource.name.ilike(f"%{query}%"))
    return q.all()

@router.post("/sources", response_model=ContentSourceOut)
def create_global_source(
    data: ContentSourceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Creates a new global source."""
    source = ContentSource(
        org_id=None,
        name=data.name,
        source_type=data.source_type,
        category=data.category,
        description=data.description,
        enabled=data.enabled
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source

@router.patch("/sources/{id}", response_model=ContentSourceOut)
def update_global_source(
    id: int,
    data: ContentSourceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Updates a global source."""
    source = db.query(ContentSource).filter(ContentSource.id == id, ContentSource.org_id == None).first()
    if not source:
        raise HTTPException(status_code=404, detail="Global source not found")
        
    for field, value in data.dict(exclude_unset=True).items():
        setattr(source, field, value)
        
    db.commit()
    db.refresh(source)
    return source

@router.delete("/sources/{id}")
def delete_global_source(
    id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Deletes a global source."""
    source = db.query(ContentSource).filter(ContentSource.id == id, ContentSource.org_id == None).first()
    if not source:
        raise HTTPException(status_code=404, detail="Global source not found")
        
    db.delete(source)
    db.commit()
    return {"ok": True}

# --- GLOBAL ENTRIES ---

@router.get("/entries", response_model=List[ContentItemOut])
def list_global_entries(
    source_id: Optional[int] = None,
    item_type: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Lists entries in the global library."""
    q = db.query(ContentItem).filter(ContentItem.org_id == None)
    
    if source_id:
        q = q.filter(ContentItem.source_id == source_id)
    if item_type:
        q = q.filter(ContentItem.item_type == item_type)
    if query:
        q = q.filter(or_(
            ContentItem.title.ilike(f"%{query}%"),
            ContentItem.text.ilike(f"%{query}%"),
            ContentItem.arabic_text.ilike(f"%{query}%")
        ))
        
    return q.order_by(ContentItem.created_at.desc()).offset(offset).limit(limit).all()

@router.post("/entries", response_model=ContentItemOut)
def create_global_entry(
    data: ContentItemCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Creates a new global entry (using the unified service for auto-source creation)."""
    from app.services.library_service import create_library_entry
    return create_library_entry(db, None, data)

@router.patch("/entries/{id}", response_model=ContentItemOut)
def update_global_entry(
    id: int,
    data: ContentItemUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Updates a global entry."""
    item = db.query(ContentItem).filter(ContentItem.id == id, ContentItem.org_id == None).first()
    if not item:
        raise HTTPException(status_code=404, detail="Global entry not found")
        
    update_data = data.dict(exclude_unset=True)
    
    if any(k in update_data for k in ["item_type", "text", "arabic_text", "meta"]):
        new_type = update_data.get("item_type", item.item_type)
        new_text = update_data.get("text", item.text)
        new_ar = update_data.get("arabic_text", item.arabic_text)
        new_meta = update_data.get("meta", item.meta)
        validate_entry_meta(new_type, new_text, new_ar, new_meta)

    for field, value in update_data.items():
        setattr(item, field, value)
        
    db.commit()
    db.refresh(item)
    return item

@router.delete("/entries/{id}")
def delete_global_entry(
    id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin)
):
    """Deletes a global entry."""
    item = db.query(ContentItem).filter(ContentItem.id == id, ContentItem.org_id == None).first()
    if not item:
        raise HTTPException(status_code=404, detail="Global entry not found")
        
    db.delete(item)
    db.commit()
    return {"ok": True}
