import asyncio
import os
import sys

# Add app to path
sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.models import QuranVerse

async def check():
    db = SessionLocal()
    verse = db.query(QuranVerse).filter(QuranVerse.surah_number == 1, QuranVerse.ayah_number == 1).first()
    if verse:
        print(f"ID: {verse.id}")
        print(f"Verse Key: {verse.verse_key}")
        print(f"Arabic Raw: {repr(verse.arabic_text)}")
        
        # Test Reshaping
        from app.services.image_renderer import reshape_arabic
        reshaped = reshape_arabic(verse.arabic_text)
        print(f"Reshaped: {repr(reshaped)}")
    else:
        print("Verse 1:1 not found")
    db.close()

if __name__ == "__main__":
    asyncio.run(check())
