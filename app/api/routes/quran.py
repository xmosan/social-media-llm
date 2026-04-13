# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.quran_service import get_quran_ayah, search_quran, get_verse_by_reference
from app.services.quran_caption_service import generate_ai_caption_from_quran
from app.models import User
from app.security.auth import require_user
from typing import List, Optional

router = APIRouter(prefix="/api/quran", tags=["Quran Foundation"])

@router.get("/ayah/{surah}/{ayah}")
async def api_get_ayah(
    surah: int, 
    ayah: int, 
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    item = get_quran_ayah(db, surah, ayah)
    if not item:
        raise HTTPException(status_code=404, detail=f"Ayah {surah}:{ayah} not found in database.")
    
    return {
        "id": item.id,
        "title": item.title,
        "text": item.text,
        "arabic": item.arabic_text,
        "meta": item.meta
    }

@router.get("/search")
async def api_search_quran(
    q: str = Query(..., min_length=2),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    # Try reference lookup first (e.g. 70:5)
    ref_item = get_verse_by_reference(db, q)
    if ref_item:
        results = [ref_item]
    else:
        results = search_quran(db, q, limit)
        
    return [
        {
            "id": r.id,
            "title": r.title,
            "text": r.text,
            "arabic": r.arabic_text,
            "meta": r.meta
        } for r in results
    ]

@router.post("/generate-caption")
async def api_generate_quran_caption(
    data: dict, 
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    item_id = data.get("item_id")
    style = data.get("style", "reflective")
    
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id (Quran verse ID) is required.")
    
    from app.models import ContentItem
    item = db.query(ContentItem).filter(ContentItem.id == item_id, ContentItem.item_type == "quran").first()
    if not item:
        raise HTTPException(status_code=404, detail="Quran verse not found.")
        
    caption = generate_ai_caption_from_quran(item, style)
    return {
        "caption": caption,
        "reference": item.title,
        "item_id": item.id
    }
