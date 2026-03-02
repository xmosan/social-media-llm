# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db import get_db
from app.models import SourceDocument, ContentSource, ContentItem
from app.schemas import (
    SourceDocumentOut, SourceDocumentCreate,
    ContentSourceOut, ContentItemOut, ContentItemCreate, ContentItemUpdate
)
from sqlalchemy import or_
from app.security.rbac import get_current_org_id
from app.services.ingestion import ingest_document
from app.services.prebuilt_loader import load_prebuilt_packs
from app.services.library_service import create_library_entry, validate_entry_meta

router = APIRouter(prefix="/library", tags=["library"])

# --- STRUCTURED LIBRARY (Sources & Entries) ---

@router.get("/sources", response_model=List[ContentSourceOut])
def list_library_sources(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Lists all manual library sources for the org (including global)."""
    sources = db.query(ContentSource).filter(
        or_(ContentSource.org_id == org_id, ContentSource.org_id == None)
    ).all()
    return sources

@router.get("/entries", response_model=List[ContentItemOut])
def list_library_entries(
    source_id: Optional[int] = None,
    query: Optional[str] = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Lists entries in the library with filtering."""
    q = db.query(ContentItem).filter(
        or_(ContentItem.org_id == org_id, ContentItem.org_id == None)
    )
    if source_id:
        q = q.filter(ContentItem.source_id == source_id)
    if query:
        q = q.filter(or_(
            ContentItem.text.ilike(f"%{query}%"),
            ContentItem.title.ilike(f"%{query}%"),
            ContentItem.arabic_text.ilike(f"%{query}%")
        ))
    return q.order_by(ContentItem.created_at.desc()).all()

@router.post("/entries", response_model=ContentItemOut)
def add_library_entry(
    data: ContentItemCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Adds a new library entry, optionally creating a source inline."""
    return create_library_entry(db, org_id, data)

@router.patch("/entries/{id}", response_model=ContentItemOut)
def update_library_entry(
    id: int,
    data: ContentItemUpdate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Updates an existing library entry."""
    item = db.query(ContentItem).filter(ContentItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Entry not found")
    if item.org_id is not None and item.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
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
def delete_library_entry(
    id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Deletes a library entry."""
    item = db.query(ContentItem).filter(ContentItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Entry not found")
    if item.org_id is not None and item.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    db.delete(item)
    db.commit()
    return {"status": "success"}

# --- PREBUILT LIBRARY ---

@router.get("/all_prebuilt")
def get_all_prebuilt_items():
    """Returns a flattened list of all prebuilt pack items for the UI drawer."""
    packs = load_prebuilt_packs()
    items = []
    for p in packs:
        for i in p.get("items", []):
            items.append({
                "id": str(i.get("id")),
                "title": f"[{p.get('name', 'Pack')}] {i.get('reference', '')}".strip(),
                "text": i.get("text", ""),
                "source_type": i.get("source") or "prebuilt pack"
            })
    return items

# --- DOCUMENT LIBRARY (Legacy/Unstructured) ---

@router.get("", response_model=List[SourceDocumentOut])
def list_library_documents(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Lists all documents in the organizational library."""
    docs = db.query(SourceDocument).filter(SourceDocument.org_id == org_id).order_by(SourceDocument.created_at.desc()).all()
    return docs

@router.post("/upload", response_model=SourceDocumentOut)
async def upload_document(
    title: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Uploads a PDF or TXT file to the library."""
    content = await file.read()
    filename = file.filename
    source_type = "pdf" if filename.lower().endswith(".pdf") else "text"
    
    doc_title = title or filename
    
    doc = ingest_document(
        db=db,
        org_id=org_id,
        title=doc_title,
        source_type=source_type,
        file_bytes=content if source_type == "pdf" else None,
        content=content.decode("utf-8", errors="ignore") if source_type == "text" else None
    )
    return doc

@router.post("/add_text", response_model=SourceDocumentOut)
def add_text_document(
    data: SourceDocumentCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Adds a text document (pasted) to the library."""
    doc = ingest_document(
        db=db,
        org_id=org_id,
        title=data.title,
        source_type="text",
        content=data.raw_text
    )
    return doc

@router.post("/add_url", response_model=SourceDocumentOut)
def add_url_document(
    data: SourceDocumentCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Adds a URL source to the library."""
    if not data.original_url:
        raise HTTPException(status_code=400, detail="original_url is required for URL source")
    
    doc = ingest_document(
        db=db,
        org_id=org_id,
        title=data.title or data.original_url,
        source_type="url",
        url=data.original_url
    )
    return doc

@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Deletes a document from the library."""
    doc = db.query(SourceDocument).filter(SourceDocument.id == doc_id, SourceDocument.org_id == org_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    return {"status": "success", "message": f"Document {doc_id} deleted"}
