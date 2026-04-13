import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal
from app.services.quran_service import get_quran_ayah
from app.services.quran_caption_service import generate_ai_caption_from_quran

def generate_examples():
    db = SessionLocal()
    examples = [
        (70, 5, "reflective"),
        (94, 5, "direct"),
        (2, 153, "poetic")
    ]
    
    print("✨ LOADING QURAN-CONNECTED CONTENT EXAMPLES ✨\n")
    print("="*60)
    
    try:
        for surah, ayah_num, style in examples:
            ayah = get_quran_ayah(db, surah, ayah_num)
            if not ayah:
                print(f"❌ Ayah {surah}:{ayah_num} not found. Ensure DB is synced.")
                continue
            
            print(f"📖 SOURCE: {ayah.title}")
            print(f"📜 VERSE: {ayah.text}")
            print(f"🎭 STYLE: {style.upper()}")
            print("-" * 30)
            
            caption = generate_ai_caption_from_quran(ayah, style=style)
            print("AI GROUNDED CAPTION:")
            print(caption)
            print("\n" + "="*60 + "\n")
            
    finally:
        db.close()

if __name__ == "__main__":
    generate_examples()
