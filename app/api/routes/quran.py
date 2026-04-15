# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import logging
from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)

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
    
    return normalize_quran_verse(item)

@router.get("/surahs")
async def api_get_surahs(
    user: User = Depends(require_user)
):
    from app.services.quran_service import get_surah_list
    return get_surah_list()

@router.get("/surahs/{number}")
async def api_get_surah_detail(
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    from app.services.quran_service import get_surah_verses, get_surah_list
    from app.services.quran_serialization import SURAH_MAP
    
    if number not in SURAH_MAP:
        raise HTTPException(status_code=404, detail="Surah not found")
        
    meta = SURAH_MAP[number]
    verses = get_surah_verses(db, number)
    
    return {
        "number": number,
        "name_en": meta["en"],
        "name_ar": meta["ar"],
        "total_verses": meta["verses"],
        "revelation_place": meta["type"],
        "verses": verses
    }

@router.get("/search")
async def api_search_quran(
    q: str = Query(..., min_length=2),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    from app.services.quran_service import resolve_quran_input
    
    try:
        data = resolve_quran_input(q, db)
        
        # If it's a direct reference dict, wrap in a list for the UI list view
        if isinstance(data, dict):
            return [data]
        
        # If it's a list (search results), return as is
        return data
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search failure: {e}")
        raise HTTPException(status_code=500, detail="An error occurred during search.")

@router.post("/generate-caption")
async def api_generate_quran_caption(
    data: dict, 
    db: Session = Depends(get_db),
    user: User = Depends(require_user)
):
    item_id = data.get("item_id")
    style = data.get("style", "reflective")
    
    # Robust ID parsing
    try:
        final_item_id = int(item_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid item_id format.")
    
    from app.models import ContentItem
    try:
        item = db.query(ContentItem).filter(ContentItem.id == final_item_id, ContentItem.item_type == "quran").first()
        if not item:
            raise HTTPException(status_code=404, detail="Quran verse not found in Foundation.")
            
        print(f"📡 [GroundedAPI] Generating for: {item.title} (ID: {item.id})")
        caption = generate_ai_caption_from_quran(item, style)
        
        return {
            "caption": caption,
            "reference": item.title,
            "item_id": item.id
        }
    except Exception as e:
        import traceback
        print(f"🔴 [GroundedAPI] CRITICAL FAILURE: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
