# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import random
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models import ContentSource, ContentItem

logger = logging.getLogger(__name__)

# --- Topic Alias Map (v2 Intelligence) ---
ALIAS_MAP = {
    "sabr": ["patience", "steadfastness", "persevere", "endurance", "patiently"],
    "salah": ["prayer", "pray", "prostrate", "sujud"],
    "shukr": ["gratitude", "grateful", "thankful", "thanks"],
    "tawakkul": ["trust in allah", "dependence", "reliance", "trusting allah"],
    "mercy": ["compassion", "rahmah", "merciful", "kindness"],
    "forgiveness": ["pardon", "forgive", "repentance", "maghfirah"],
    "akhlaq": ["character", "manner", "morals", "behavior"],
    "rizq": ["provision", "sustenance", "blessing"],
}

def expand_topic_keywords(topic: str) -> list[str]:
    """Expands a topic into a list of relevant search keywords using the ALIAS_MAP."""
    if not topic:
        return []
    
    words = [topic.lower().strip()]
    
    # Check for direct matches in the alias map
    for key, aliases in ALIAS_MAP.items():
        if key in words[0] or any(alias in words[0] for alias in aliases):
            words.extend(aliases)
            # Add the key itself if it wasn't there
            if key not in words:
                words.append(key)
    
    # Split the original multi-word topic into individual tokens too
    tokens = [w.strip() for w in words[0].replace(",", " ").split() if len(w.strip()) > 2]
    words.extend(tokens)
    
    # Unique, cleaned list
    return list(set([w.lower() for w in words if w]))

def select_items_for_automation(
    db: Session,
    *,
    org_id: int,
    source_id: int,
    items_per_post: int,
    selection_mode: str,
    last_item_cursor: str | None,
) -> tuple[list[ContentItem], str | None]:
    """
    Selects N items from a source based on the selection mode.
    Returns: (list of ContentItem, new_cursor_string)
    """
    items_per_post = max(1, min(items_per_post or 1, 5))

    # Ensure source belongs to org and is enabled
    src = db.execute(
        select(ContentSource).where(
            ContentSource.id == source_id, 
            ContentSource.org_id == org_id, 
            ContentSource.enabled == True
        )
    ).scalar_one_or_none()
    
    if not src:
        logger.warning(f"Source {source_id} not found or disabled for org {org_id}")
        return ([], last_item_cursor)

    # Fetch all eligible items
    q = select(ContentItem).where(
        ContentItem.org_id == org_id,
        ContentItem.source_id == source_id,
    )

    all_items = db.execute(q).scalars().all()
    if not all_items:
        logger.warning(f"No content items found for source {source_id}")
        return ([], last_item_cursor)

    if selection_mode == "round_robin":
        # Deterministic rotation by ID ordering
        all_items_sorted = sorted(all_items, key=lambda x: x.id)
        start_idx = 0
        if last_item_cursor:
            try:
                cursor_id = int(last_item_cursor)
                for i, it in enumerate(all_items_sorted):
                    if it.id == cursor_id:
                        start_idx = (i + 1) % len(all_items_sorted)
                        break
            except (ValueError, TypeError):
                start_idx = 0
                
        picked = []
        idx = start_idx
        for _ in range(min(items_per_post, len(all_items_sorted))):
            picked.append(all_items_sorted[idx])
            idx = (idx + 1) % len(all_items_sorted)
            
        new_cursor = str(picked[-1].id) if picked else last_item_cursor
        return (picked, new_cursor)

    # Default: random, prefer least-used / not recently used
    # weighting by inverse use_count
    try:
        weights = []
        for it in all_items:
            w = 1.0 / (1.0 + (it.use_count or 0))
            weights.append(w)
        
        # random.choices can pick same item multiple times if k > 1
        # so we pick one by one to ensure uniqueness if possible
        picked = []
        available = list(all_items)
        for _ in range(min(items_per_post, len(available))):
            # Recalculate weights for remaining available items
            current_weights = [1.0 / (1.0 + (it.use_count or 0)) for it in available]
            choice = random.choices(available, weights=current_weights, k=1)[0]
            picked.append(choice)
            available.remove(choice)
            
        return (picked, last_item_cursor)
    except Exception as e:
        logger.error(f"Error in random item selection: {e}")
        return (random.sample(all_items, min(items_per_post, len(all_items))), last_item_cursor)

def mark_items_used(db: Session, items: list[ContentItem]) -> None:
    """Updates last_used_at and use_count for the provided items."""
    now = datetime.now(timezone.utc)
    for it in items:
        it.last_used_at = now
        it.use_count = (it.use_count or 0) + 1
    db.commit()

# ---- Importers ----

def import_manual_items(db: Session, *, org_id: int, source_id: int, texts: list[str]) -> int:
    """Imports raw text items into the database."""
    n = 0
    for t in texts:
        t = (t or "").strip()
        if not t:
            continue
        db.add(ContentItem(org_id=org_id, source_id=source_id, text=t))
        n += 1
    db.commit()
    logger.info(f"Imported {n} manual items for source {source_id}")
    return n

def import_from_rss(db: Session, *, org_id: int, source: ContentSource) -> int:
    """Stub for RSS importing logic."""
    # TODO: Implement RSS parsing (e.g., using feedparser)
    logger.info(f"RSS import triggered for source {source.id} (Not implemented)")
    return 0

def import_from_url_list(db: Session, *, org_id: int, source: ContentSource) -> int:
    """Stub for URL list importing logic."""
    # TODO: Implement URL content extraction (e.g., using newspaper3k or custom scrapers)
    logger.info(f"URL list import triggered for source {source.id} (Not implemented)")
    return 0

def import_from_qf(db: Session, *, chapter_id: int, translation_id: str = "131") -> int:
    """
    Imports verses from Quran Foundation into the global library.
    """
    from app.services.quran_ingestion import sync_surah_to_library
    return sync_surah_to_library(db, chapter_id, translation_id)
