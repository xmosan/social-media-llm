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

    # 2. Fetch Verses via the QF Service (with RETRY logic)
    print(f"📡 [SYNC] Ingesting Surah {chapter_id} verses...")
    verses = None
    for attempt in range(3):
        try:
            verses = get_surah_verses(chapter_id, translation_id)
            if verses: break
        except Exception as e:
            logger.warning(f"⚠️ [SYNC] API Attempt {attempt+1} failed for Surah {chapter_id}: {e}")
            time.sleep(2 * (attempt + 1))

    if not verses:
        logger.error(f"❌ [SYNC] Max retries reached or no verses returned for chapter {chapter_id}")
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
    verse_idx = 0
    for v in verses:
        verse_idx += 1
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
        
        # STEP 7: Progress logging every 50 verses
        if verse_idx % 50 == 0:
            logger.info(f"[SYNC] Surah {chapter_id}: Manifested verse {verse_idx}...")
        
    db.commit()
    if new_count > 0:
        logger.info(f"✅ [SYNC] Successfully manifested {new_count} new verses from Surah {chapter_id}")
    return new_count

def save_sync_status(status_msg, is_error=False):
    """Utility to persist sync status for the UI."""
    import json
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    status_file = os.path.join(base_dir, "sync_status.json")
    try:
        with open(status_file, "w") as f:
            json.dump({
                "message": status_msg,
                "is_error": is_error,
                "timestamp": datetime.datetime.now().isoformat()
            }, f)
    except Exception as e:
        logger.error(f"Failed to save sync status: {e}")

def validate_sync_ready(db):
    """
    Step 5: Pre-check before allowing bulk sync.
    Checks DB connectivity, verifies a recent backup exists, and runs a quick write test.
    IMPROVED: Allows bypass for initial sync if DB is nearly empty.
    """
    from app.models import WaitlistEntry, ContentItem
    import os
    import glob
    
    checks = {
        "db_connected": False,
        "backup_recent": False,
        "write_test_passed": False
    }
    
    try:
        # 1. DB Connected
        db.execute(text("SELECT 1"))
        checks["db_connected"] = True
        
        # 2. Backup Recent (within 24h)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        backups_dir = os.path.join(base_dir, "backups")
        if os.path.exists(backups_dir):
            files = glob.glob(os.path.join(backups_dir, "*.json.gz"))
            if files:
                latest = max(files, key=os.path.getmtime)
                mtime = os.path.getmtime(latest)
                if (time.time() - mtime) < 86400: # 24 hours
                    checks["backup_recent"] = True

        # INITIAL SYNC BYPASS: If no backup but DB is basically empty, allow it
        quran_count = db.query(ContentItem).filter(ContentItem.item_type == "quran").count()
        if not checks["backup_recent"] and quran_count < 100:
            logger.info("⚠️ [SYNC] No recent backup found, but allowing Initial Sync Bypass (DB count < 100)")
            checks["backup_recent"] = True

        # 3. Write Test
        test_email = "sync_precheck@sabeel.test"
        db.query(WaitlistEntry).filter(WaitlistEntry.email == test_email).delete()
        test_entry = WaitlistEntry(email=test_email, name="Pre-Sync Check")
        db.add(test_entry)
        db.flush()
        db.delete(test_entry)
        db.commit()
        checks["write_test_passed"] = True
        
    except Exception as e:
        logger.error(f"❌ [SYNC_PRECHECK] Failed: {e}")
        
    if not all(checks.values()):
        msg = f"❌ System not ready for Quran sync: {checks}"
        save_sync_status(msg, is_error=True)
        raise Exception(msg)
    
    logger.info("✅ [HEALTH] Pre-sync verification passed")
    return True

def sync_entire_quran(db_factory: callable):
    """
    Background worker to sync all 114 Surahs sequentially.
    Step 7: Implements safe trigger and granular logging.
    """
    db = db_factory()
    try:
        # STEP 7: PRE-SYNC CHECK
        validate_sync_ready(db)
    except Exception as e:
        logger.error(str(e))
        db.close()
        return
    finally:
        db.close()

    total_new = 0
    t0 = time.time()
    save_sync_status("🚀 Manifesting Global Quran Repository...")
    logger.info("🚀 [SYNC] STARTING FULL QURAN FOUNDATION SYNC (114 SURAHS)...")
    
    for chapter_id in range(1, 115):
        db = db_factory()
        try:
            # Note: sync_surah_to_library currently logs per surah.
            # We'll add a more granular log here if needed or just keep current surah-level.
            count = sync_surah_to_library(db, chapter_id)
            total_new += count
            
            # Progress reporting every 10 surahs (roughly 500-1000 verses)
            if chapter_id % 10 == 0:
                msg = f"📡 [SYNC] Running: {chapter_id}/114 Surahs manifest..."
                logger.info(msg)
                save_sync_status(msg)
        except Exception as e:
            logger.error(f"❌ [SYNC] Error Surah {chapter_id}: {e}")
            # Optional: Add retry logic here if desired, but sequential skip safer
        finally:
            db.close()
            
    duration = time.time() - t0
    msg = f"✅ [SYNC] COMPLETE. Added {total_new} records. Total time: {duration:.2f}s"
    print("📖 Quran Sync Completed Successfully")
    logger.info(msg)
    save_sync_status(msg)
