import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.services.sources.sunnah import pick_hadith_for_topic
from app.models import Base, engine

def test_fetch():
    print("Starting Hadith Fetch Test...")
    
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        topic = "gratitude"
        print(f"Testing fetch for topic: {topic}")
        hadith = pick_hadith_for_topic(db, topic)
        
        if hadith:
            print(f"SUCCESS: Found hadith for '{topic}'")
            print(f"Reference: {hadith.reference}")
            print(f"Text Preview: {hadith.content_text[:100]}...")
        else:
            print(f"FAILURE: No hadith found for '{topic}'")
            
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_fetch()
