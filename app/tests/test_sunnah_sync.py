# Add the project root to sys.path to import app modules
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.db import SessionLocal
from app.services.sources.sunnah import pick_hadith_for_topic

def test_sync(topic="patience"):
    print(f"--- Testing Sunnah.com Sync for topic: {topic} ---")
    db = SessionLocal()
    try:
        item = pick_hadith_for_topic(db, topic)
        if item:
            print("\n✅ SUCCESS: Found/Synced Hadith")
            print(f"Reference: {item.reference}")
            print(f"Text Snippet: {item.content_text[:100]}...")
            print(f"URL: {item.url}")
        else:
            print("\n❌ FAILURE: No Hadith found or synced.")
    except Exception as e:
        print(f"\n💥 CRASH: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "patience"
    test_sync(t)
