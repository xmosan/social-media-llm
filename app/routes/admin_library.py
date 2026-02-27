from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from app.db import get_db
from app.models import ContentSource, ContentItem, User, OrgMember
from app.schemas import (
    ContentSourceOut, ContentSourceCreate, ContentSourceUpdate,
    ContentItemOut, ContentItemCreate, ContentItemUpdate
)
from app.security.auth import require_user
from app.security.rbac import get_current_org_id, require_superadmin

router = APIRouter(prefix="/api/admin/library", tags=["admin_library"])

def check_library_admin_access(user: User, org_id: int, db: Session):
    """Checks if the user is an admin for the given org or a superadmin."""
    if user.is_superadmin:
        return True
    
    membership = db.query(OrgMember).filter(
        OrgMember.user_id == user.id,
        OrgMember.org_id == org_id,
        OrgMember.role.in_(["admin", "owner"])
    ).first()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this organization."
        )
    return True

# --- SOURCES ---

@router.get("/sources", response_model=List[ContentSourceOut])
def list_sources(
    scope: str = Query("org", enum=["global", "org", "all"]),
    query: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    org_id: int = Depends(get_current_org_id)
):
    q = db.query(ContentSource)
    
    if scope == "global":
        q = q.filter(ContentSource.org_id == None)
    elif scope == "org":
        q = q.filter(ContentSource.org_id == org_id)
    else: # all
        q = q.filter(or_(ContentSource.org_id == org_id, ContentSource.org_id == None))
        
    if query:
        q = q.filter(ContentSource.name.ilike(f"%{query}%"))
        
    return q.all()

@router.post("/sources", response_model=ContentSourceOut)
def create_source(
    data: ContentSourceCreate,
    request: Request,
    is_global: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    try:
        if is_global:
            require_superadmin(user)
            target_org_id = None
        else:
            # Note: using the top-level import
            org_id = get_current_org_id(request, user, request.headers.get("X-Org-Id"), db)
            check_library_admin_access(user, org_id, db)
            target_org_id = org_id
            
        source = ContentSource(
            org_id=target_org_id,
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
    except Exception as e:
        import traceback
        print(f"ERROR in create_source: {e}")
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/sources/{id}", response_model=ContentSourceOut)
def update_source(
    id: int,
    data: ContentSourceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    org_id: int = Depends(get_current_org_id)
):
    source = db.query(ContentSource).filter(ContentSource.id == id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    if source.org_id is None:
        require_superadmin(user)
    else:
        if source.org_id != org_id:
            raise HTTPException(status_code=403, detail="Cross-org access denied")
        check_library_admin_access(user, org_id, db)
        
    for field, value in data.dict(exclude_unset=True).items():
        setattr(source, field, value)
        
    db.commit()
    db.refresh(source)
    return source

@router.delete("/sources/{id}")
def delete_source(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    org_id: int = Depends(get_current_org_id)
):
    source = db.query(ContentSource).filter(ContentSource.id == id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    if source.org_id is None:
        require_superadmin(user)
    else:
        if source.org_id != org_id:
            raise HTTPException(status_code=403, detail="Cross-org access denied")
        check_library_admin_access(user, org_id, db)
        
    db.delete(source)
    db.commit()
    return {"ok": True}

# --- ENTRIES ---

@router.get("/entries", response_model=List[ContentItemOut])
def list_entries(
    source_id: Optional[int] = None,
    item_type: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    q = db.query(ContentItem)
    
    # Filter by org or global
    q = q.filter(or_(ContentItem.org_id == org_id, ContentItem.org_id == None))
    
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
def create_entry(
    data: ContentItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    org_id: int = Depends(get_current_org_id)
):
    source = db.query(ContentSource).filter(ContentSource.id == data.source_id).first()
    if not source:
        raise HTTPException(status_code=400, detail="Invalid source_id")
    
    if source.org_id is None:
        require_superadmin(user)
        target_org_id = None
    else:
        if source.org_id != org_id:
            raise HTTPException(status_code=403, detail="Access denied to this source")
        check_library_admin_access(user, org_id, db)
        target_org_id = org_id

    # Type-specific validation
    validate_entry_meta(data.item_type, data.text, data.arabic_text, data.meta)

    item = ContentItem(
        org_id=target_org_id,
        source_id=data.source_id,
        item_type=data.item_type,
        title=data.title,
        text=data.text,
        arabic_text=data.arabic_text,
        translation=data.translation,
        url=data.url,
        meta=data.meta,
        tags=data.tags
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@router.patch("/entries/{id}", response_model=ContentItemOut)
def update_entry(
    id: int,
    data: ContentItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    org_id: int = Depends(get_current_org_id)
):
    item = db.query(ContentItem).filter(ContentItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Entry not found")
        
    if item.org_id is None:
        require_superadmin(user)
    else:
        if item.org_id != org_id:
            raise HTTPException(status_code=403, detail="Cross-org access denied")
        check_library_admin_access(user, org_id, db)

    update_data = data.dict(exclude_unset=True)
    
    # If type or meta or text changes, re-validate
    new_type = update_data.get("item_type", item.item_type)
    new_text = update_data.get("text", item.text)
    new_ar = update_data.get("arabic_text", item.arabic_text)
    new_meta = update_data.get("meta", item.meta)
    
    if any(k in update_data for k in ["item_type", "text", "arabic_text", "meta"]):
        validate_entry_meta(new_type, new_text, new_ar, new_meta)

    for field, value in update_data.items():
        setattr(item, field, value)
        
    db.commit()
    db.refresh(item)
    return item

@router.delete("/entries/{id}")
def delete_entry(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    org_id: int = Depends(get_current_org_id)
):
    item = db.query(ContentItem).filter(ContentItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Entry not found")
        
    if item.org_id is None:
        require_superadmin(user)
    else:
        if item.org_id != org_id:
            raise HTTPException(status_code=403, detail="Cross-org access denied")
        check_library_admin_access(user, org_id, db)
        
    db.delete(item)
    db.commit()
    return {"ok": True}

def validate_entry_meta(item_type: str, text: str, arabic_text: Optional[str], meta: dict):
    if item_type == "quran":
        if not meta.get("surah_number") or not meta.get("verse_start"):
            raise HTTPException(status_code=400, detail="surah_number and verse_start are required for Quran entries.")
        if not text and not arabic_text:
            raise HTTPException(status_code=400, detail="Arabic text or English translation is required for Quran entries.")
            
    elif item_type == "hadith":
        if not meta.get("collection") or not meta.get("hadith_number"):
            raise HTTPException(status_code=400, detail="collection and hadith_number are required for Hadith entries.")
        if not text and not arabic_text:
            raise HTTPException(status_code=400, detail="Hadith text (Arabic or English) is required.")
            
    elif item_type in ["book", "article"]:
        if not meta.get("title") and not meta.get("url"):
             raise HTTPException(status_code=400, detail="Title or URL is required for books/articles.")
        if not text:
             raise HTTPException(status_code=400, detail="Excerpt text is required for books/articles.")
