# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from app.models import ContentItem, ContentSource
from app.services.quran_serialization import normalize_quran_verse

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

def normalize_reference_input(text: str) -> str:
    """
    Normalizes user input to a clean reference string.
    Removes common labels like 'Surah', 'Verse', 'Ayah', 'Quran', and extra spaces.
    Example: "Surah 70:5" -> "70:5"
    """
    if not text:
        return ""
    text = text.strip()
    # Remove common prefixes/labels case-insensitively
    labels = ["surah", "verse", "ayah", "quran", "qur'an"]
    import re
    for label in labels:
        text = re.sub(rf"^{label}\s+", "", text, flags=re.IGNORECASE)
    return text.strip()

def parse_quran_reference(ref: str) -> tuple[int, int]:
    """
    Accept only formats like: "70:5", "2:286", "112:1"
    Returns (surah, ayah)
    """
    ref = normalize_reference_input(ref)
    
    if ":" not in ref:
        raise ValueError(f"Invalid reference format: '{ref}'. Expected format 'surah:ayah' (e.g., 70:5)")
    
    parts = ref.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid reference format: '{ref}'. Multiple colons found.")
    
    try:
        surah = int(parts[0].strip())
        ayah = int(parts[1].strip())
    except ValueError:
        raise ValueError(f"Invalid reference format: '{ref}'. Surah and Ayah must be integers.")
    
    if surah <= 0 or ayah <= 0:
        raise ValueError(f"Invalid reference values: '{ref}'. Numbers must be greater than zero.")
        
    return surah, ayah

def get_quran_ayah_exact(surah: int, ayah: int, db: Session) -> dict:
    """
    Return the exact ayah record and matching translation.
    No fuzzy logic. No theme matching. No random fallback.
    """
    item = get_quran_ayah(db, surah, ayah)
    
    if not item:
        logger.error(f"❌ [QURAN][ERROR] Verse not found: {surah}:{ayah}")
        raise ValueError(f"Verse not found: {surah}:{ayah}")
    
    # Extract translator from meta if available
    translator = item.meta.get("translation_id", "Unknown")
    if translator == "131":
        translator = "Sahih International"
    
    payload = normalize_quran_verse(item)
    
    if not payload["translation_text"]:
        logger.error(f"❌ [QURAN][ERROR] Translation missing for: {surah}:{ayah}")
        raise ValueError(f"Translation missing for: {surah}:{ayah}")
        
    logger.info(f"✅ [QURAN] Exact verse fetch success: {surah}:{ayah}")
    return payload

def resolve_quran_input(user_input: str, db: Session) -> dict:
    """
    If the input looks like a direct reference, use exact lookup only.
    If it does not, route to search mode.
    """
    user_input = user_input.strip()
    logger.info(f"📡 [QURAN] Raw input received: {user_input}")
    
    # Check if it matches reference pattern (basic check before parsing)
    # Pattern: Digit(s) followed by colon then Digit(s)
    import re
    normalized = normalize_reference_input(user_input)
    if re.match(r"^\d+:\d+$", normalized):
        logger.info(f"🎯 [QURAN] Normalized reference: {normalized}")
        try:
            surah, ayah = parse_quran_reference(normalized)
            return get_quran_ayah_exact(surah, ayah, db)
        except ValueError as e:
            logger.error(f"❌ [QURAN][ERROR] Invalid reference input: {user_input} - {e}")
            raise e
    
    # Otherwise, it's a search
    logger.info(f"🔎 [QURAN] Route to keyword search path: '{user_input}'")
    results = search_quran(db, user_input)
    # Formatting for return
    return [normalize_quran_verse(r) for r in results]

def build_quran_quote_payload(user_input: str, db: Session) -> dict:
    """
    Build the exact payload used by the quote renderer.
    """
    try:
        data = resolve_quran_input(user_input, db)
        
        # If it returned a list (search results), we take the first match or fail
        # But for direct lookup, it returns a dict.
        if isinstance(data, list):
            if not data:
                raise ValueError(f"No results found for search: '{user_input}'")
            # In search mode, we might want to let user select, 
            # but for build_payload (e.g. from studio), we need the exact item.
            # If resolve_quran_input was called with a direct reference, it returns the dict.
            # If search, we take the first.
            item_data = data[0]
            # Convert search result format back to exact format if needed
            # Actually, let's just use the item_id to get exact if it came from search
            item = db.query(ContentItem).filter(ContentItem.id == item_data["id"]).first()
            surah = item.meta.get("surah_number")
            ayah = item.meta.get("verse_number")
            exact_data = get_quran_ayah_exact(surah, ayah, db)
        else:
            exact_data = data
            
        payload = {
            "source_type": "quran",
            "source_reference": exact_data["reference"],
            "source_metadata": exact_data,
            "top_line": exact_data["reference"],
            "main_text": exact_data["translation_text"],
            "sub_text": "",
            "arabic_text": exact_data["arabic_text"]
        }
        logger.info(f"✅ [QURAN] Quote payload built: {payload['top_line']}")
        return payload

    except Exception as e:
        logger.error(f"❌ [QURAN][ERROR] Failed to build quote payload: {e}")
        raise e

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

def get_verse_by_id(db: Session, item_id: int) -> Optional[dict]:
    """Retrieves normalized verse by integer ID."""
    item = db.query(ContentItem).filter(ContentItem.id == item_id, ContentItem.item_type == "quran").first()
    return normalize_quran_verse(item) if item else None


def get_surah_list():
    """Returns a list of all 114 surahs with metadata from the static map."""
    from app.services.quran_serialization import SURAH_MAP
    surahs = []
    for num, info in sorted(SURAH_MAP.items()):
        surahs.append({
            "number": num,
            "name_en": info["en"],
            "name_ar": info["ar"],
            "total_verses": info["verses"],
            "revelation_place": info["type"]
        })
    return surahs

def get_surah_verses(db: Session, surah_num: int) -> List[dict]:
    """Retrieves all normalized verses for a specific surah."""
    # We filter by title pattern "Surah {num}, Verse %" and sort by parsed verse number
    # This is safer than meta filtering if JSON support is inconsistent.
    title_prefix = f"Surah {surah_num}, Verse "
    results = db.query(ContentItem).filter(
        ContentItem.item_type == "quran",
        ContentItem.title.ilike(f"{title_prefix}%")
    ).all()
    
    # Sort manually by ayah number safely
    def sort_key(item):
        try:
            return int(item.title.split("Verse ")[-1])
        except:
            return 0
            
    sorted_results = sorted(results, key=sort_key)
    return [normalize_quran_verse(r) for r in sorted_results]

def get_quran_ayahs_by_theme(db: Session, theme: str, limit: int = 5) -> List[ContentItem]:
    """
    Retrieves verses matching a specific theme/topic slug.
    Used by the Caption Engine for grounded generation.
    """
    theme = theme.lower().strip()
    results = db.query(ContentItem).filter(
        ContentItem.item_type == "quran",
        ContentItem.topics_slugs.contains([theme])
    ).limit(limit).all()
    return results

def get_verse_by_reference(db: Session, reference: str) -> Optional[ContentItem]:
    """
    Parses a reference like '70:5' and returns the raw ContentItem object.
    Used by Caption Engine and other services expecting the SQLAlchemy model.
    """
    try:
        surah, ayah = parse_quran_reference(reference)
        return get_quran_ayah(db, surah, ayah)
    except Exception:
        return None
