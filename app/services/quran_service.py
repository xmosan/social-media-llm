# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from app.models import ContentItem, ContentSource

logger = logging.getLogger(__name__)

def get_quran_source(db: Session):
    """Retrieves the global Quran Foundation source."""
    source = db.query(ContentSource).filter(
        ContentSource.source_type == "quran_foundation",
        ContentSource.org_id == None
    ).first()
    if not source:
        logger.error("❌ [QuranService] Global Quran Foundation source missing. DB might not be synced.")
    return source

def get_quran_ayah(db: Session, surah: int, ayah: int) -> Optional[ContentItem]:
    """
    Retrieves a specific ayah by surah and ayah number.
    Reference: Surah {surah}, Verse {ayah}
    """
    title = f"Surah {surah}, Verse {ayah}"
    item = db.query(ContentItem).filter(
        ContentItem.item_type == "quran",
        ContentItem.title == title
    ).first()
    
    if not item:
        logger.warning(f"⚠️ [QuranService] Ayah not found: {title}")
    return item

def search_quran(db: Session, query: str, limit: int = 15) -> List[ContentItem]:
    """
    Searches for verses by keyword in English text or within topic slugs.
    """
    # Clean query
    query = query.strip()
    if not query:
        return []

    # Search in text or topic slugs
    results = db.query(ContentItem).filter(
        ContentItem.item_type == "quran",
        or_(
            ContentItem.text.ilike(f"%{query}%"),
            ContentItem.topics_slugs.contains([query.lower()])
        )
    ).limit(limit).all()
    
    logger.info(f"🔎 [QuranService] Search for '{query}' returned {len(results)} results.")
    return results

def get_quran_ayahs_by_theme(db: Session, theme: str, limit: int = 10) -> List[ContentItem]:
    """
    Alias for search but explicitly targeting theme slugs.
    """
    results = db.query(ContentItem).filter(
        ContentItem.item_type == "quran",
        ContentItem.topics_slugs.contains([theme.lower()])
    ).limit(limit).all()
    
    # Fallback to general search if theme slug has no matches
    if not results:
        return search_quran(db, theme, limit)
    
    return results

def get_verse_by_reference(db: Session, reference: str) -> Optional[ContentItem]:
    """
    Parses a reference like '70:5' or 'Surah 70:5' and returns the verse.
    """
    import re
    # Match patterns like 70:5 or 70.5
    match = re.search(r"(\d+)[:.](\d+)", reference)
    if match:
        surah = int(match.group(1))
        ayah = int(match.group(2))
        return get_quran_ayah(db, surah, ayah)
    return None
