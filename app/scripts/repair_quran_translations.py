"""
repair_quran_translations.py
----------------------------
Backfills the 'text' column for all Quran ContentItems that currently have
an empty 'text' (i.e. no English translation stored).

Run from project root:
  .venv/bin/python3 -m app.scripts.repair_quran_translations

The script processes surah by surah, re-fetches from QF API (which now
includes translations), and updates the DB in-place.
"""
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def run_repair():
    import re as _re
    from app.db import SessionLocal
    from app.models import ContentItem
    from app.quran_foundation import get_surah_verses

    def strip_html(text: str) -> str:
        """Remove HTML tags and footnote markers from translation text."""
        text = _re.sub(r'<[^>]+>', '', text)
        return text.strip()

    db = SessionLocal()
    total_updated = 0
    total_skipped = 0
    total_errors = 0

    logger.info("🔧 Starting Quran translation repair...")

    for surah_num in range(1, 115):
        try:
            # Fetch from QF API with translation ID 20 (Sahih International)
            verses = get_surah_verses(surah_num, "20")
            if not verses:
                logger.warning(f"⚠️  Surah {surah_num}: No verses returned from API, skipping.")
                total_skipped += 1
                continue

            surah_updated = 0
            for v in verses:
                verse_num = v.get("verse_number")
                translations = v.get("translations", [])
                raw_text = translations[0].get("text", "").strip() if translations else ""
                english_text = strip_html(raw_text)

                if not english_text:
                    logger.warning(f"  Surah {surah_num}:{verse_num} — no translation in API response")
                    continue

                title = f"Surah {surah_num}, Verse {verse_num}"
                item = db.query(ContentItem).filter(
                    ContentItem.item_type == "quran",
                    ContentItem.title == title
                ).first()

                if item and not item.text:
                    item.text = english_text
                    surah_updated += 1
                    total_updated += 1

            db.commit()
            logger.info(f"✅ Surah {surah_num:3d}: updated {surah_updated}/{len(verses)} verses")

            # Gentle rate-limiting
            time.sleep(0.3)

        except Exception as e:
            logger.error(f"❌ Surah {surah_num}: {e}")
            db.rollback()
            total_errors += 1
            time.sleep(2)

    db.close()
    logger.info(f"\n{'='*50}")
    logger.info(f"Repair complete. Updated: {total_updated} | Skipped: {total_skipped} surahs | Errors: {total_errors}")


if __name__ == "__main__":
    run_repair()
