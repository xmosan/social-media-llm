from sqlalchemy.orm import Session
from sqlalchemy import text
from app.quran_foundation import get_surah_verses
from app.models import ContentSource, ContentItem
from app.services.library_service import generate_topics_slugs
import logging
import datetime
import time

logger = logging.getLogger(__name__)

def sync_surah_to_library(db: Session, chapter_id: int, translation_id: str = "131") -> int:
    """
    Synchronizes an entire Surah (chapter) from Quran Foundation into the Global Library.
    Returns the number of new verses added.
    Optimized with bulk existence checks.
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

    # 3. Optimized: Fetch all existing verses for THIS surah in one go
    existing_titles = {
        item.title for item in db.query(ContentItem.title).filter(
            ContentItem.source_id == source.id,
            ContentItem.title.like(f"Surah {chapter_id}, Verse %")
        ).all()
    }

    # 4. Process and Ingest Verses
    new_count = 0
    for v in verses:
        verse_number = v.get("verse_number")
        title = f"Surah {chapter_id}, Verse {verse_number}"
        
        if title in existing_titles:
            continue
            
        # Extract English translation
        translations = v.get("translations", [])
        english_text = translations[0].get("text", "") if translations else ""
        
        # Build Item
        item = ContentItem(
            org_id=None,
            source_id=source.id,
            item_type="quran",
            title=title,
            text=english_text,
            arabic_text=v.get("text_uthmani"),
            translation="Sahih International",
            meta={
                "surah_number": chapter_id,
                "verse_number": verse_number,
                "verse_key": v.get("verse_key"),
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
    if new_count > 0:
        logger.info(f"Successfully synced {new_count} new verses from Surah {chapter_id}")
    return new_count

def sync_entire_quran(db_factory: callable):
    """
    Background worker to sync all 114 Surahs sequentially.
    """
    total_new = 0
    t0 = time.time()
    logger.info("🚀 STARTING FULL QURAN FOUNDATION SYNC (114 SURAHS)...")
    
    for chapter_id in range(1, 115):
        db = db_factory()
        try:
            count = sync_surah_to_library(db, chapter_id)
            total_new += count
            # Yield slightly to avoid overwhelming the API or DB
            if chapter_id % 10 == 0:
                logger.info(f"Progress: {chapter_id}/114 Surahs processed...")
        except Exception as e:
            logger.error(f"❌ Error syncing Surah {chapter_id}: {e}")
        finally:
            db.close()
            
    duration = time.time() - t0
    logger.info(f"✅ FULL SYNC COMPLETE. Added {total_new} new verses. Total time: {duration:.2f}s")
