# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.models import ContentSource, ContentItem
from app.schemas import ContentItemCreate

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

def create_library_entry(db: Session, org_id: int, data: ContentItemCreate):
    # 1. Handle Source Creation if needed
    source_id = data.source_id
    if not source_id and data.source_name:
        # Check if source already exists for this org with same name
        existing_source = db.query(ContentSource).filter(
            ContentSource.org_id == org_id,
            func.lower(ContentSource.name) == func.lower(data.source_name)
        ).first()
        
        if existing_source:
            source_id = existing_source.id
        else:
            new_source = ContentSource(
                org_id=org_id,
                name=data.source_name,
                category=data.source_category or "Manual Library",
                source_type="manual_library"
            )
            db.add(new_source)
            db.flush()
            source_id = new_source.id
    
    if not source_id:
        raise HTTPException(status_code=400, detail="Either source_id or source_name is required.")

    # 2. Validate Source Ownership
    source = db.query(ContentSource).filter(ContentSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=400, detail="Invalid source_id")
    
    if source.org_id is not None and source.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied to this source")

    # 3. Validate Meta
    validate_entry_meta(data.item_type, data.text, data.arabic_text, data.meta)

    # 4. Create Item
    item = ContentItem(
        org_id=org_id,
        source_id=source_id,
        item_type=data.item_type,
        title=data.title,
        text=data.text,
        arabic_text=data.arabic_text,
        translation=data.translation,
        url=data.url,
        meta=data.meta,
        tags=data.tags,
        topics=data.topics
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
