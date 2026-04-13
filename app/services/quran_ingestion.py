from sqlalchemy.orm import Session
from sqlalchemy import text
from app.quran_foundation import get_surah_verses
from app.models import ContentSource, ContentItem
from app.services.library_service import generate_topics_slugs
import logging
import datetime

logger = logging.getLogger(__name__)

def sync_surah_to_library(db: Session, chapter_id: int, translation_id: str = "131") -> int:
    """
    Synchronizes an entire Surah (chapter) from Quran Foundation into the Global Library.
    Returns the number of new verses added.
    """
    # 1. Get or create the Global QF Source
    source = db.query(ContentSource).filter(
        ContentSource.source_type == "quran_foundation",
        ContentSource.org_id == None 
    ).first()
    
    if not source:
        logger.info("Creating Global Quran Foundation Source...")
        source = ContentSource(
            name="Quran Foundation (QDC)",
            source_type="quran_foundation",
            category="Scripture",
            description="Automated sync from Quran Foundation API",
            org_id=None,
            enabled=True
        )
        db.add(source)
        db.flush()

    # 2. Fetch Verses via the QF Service
    print(f"📡 Ingesting Surah {chapter_id} verses...")
    verses = get_surah_verses(chapter_id, translation_id)
    if not verses:
        logger.warning(f"No verses returned for chapter {chapter_id}")
        return 0

    # 3. Process and Ingest Verses
    new_count = 0
    for v in verses:
        verse_key = v.get("verse_key")
        
        # Use a simple text filter for JSON metadata to find duplicates
        # Correctly check for existing verse in this source
        existing = db.query(ContentItem).filter(
            ContentItem.source_id == source.id,
            ContentItem.title == f"Surah {chapter_id}, Verse {v.get('verse_number')}"
        ).first()
        
        if existing:
            continue
            
        # Extract English translation
        translations = v.get("translations", [])
        english_text = translations[0].get("text", "") if translations else ""
        
        # Build Item
        item = ContentItem(
            org_id=None,
            source_id=source.id,
            item_type="quran",
            title=f"Surah {chapter_id}, Verse {v.get('verse_number')}",
            text=english_text,
            arabic_text=v.get("text_uthmani"),
            translation="Sahih International",
            meta={
                "surah_number": chapter_id,
                "verse_number": v.get("verse_number"),
                "verse_key": verse_key,
                "translation_id": translation_id,
                "ingested_at": datetime.datetime.now().isoformat()
            },
            tags=["quran", f"surah_{chapter_id}"],
            topic="Quran",
            topics=[f"Surah {chapter_id}"],
            topics_slugs=generate_topics_slugs("Quran", [f"Surah {chapter_id}"], "Scripture")
        )
        db.add(item)
        new_count += 1
        
    db.commit()
    logger.info(f"Successfully synced {new_count} new verses from Surah {chapter_id}")
    return new_count
