import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import SessionLocal
from app.services.quran_service import resolve_quran_input

def test_search():
    db = SessionLocal()
    try:
        # Test reference lookup
        print("--- Testing Reference Lookup: 70:5 ---")
        res = resolve_quran_input("70:5", db)
        print(f"Reference: {res.get('reference')}")
        print(f"Translation: {res.get('translation_text')}")
        print(f"Arabic: {res.get('arabic_text')}")
        
        # Test search lookup
        print("\n--- Testing Keyword Search: Patience ---")
        results = resolve_quran_input("Patience", db)
        for i, r in enumerate(results[:3]):
            print(f"Result {i+1}: {r.get('reference')}")
            print(f"  Translation: {r.get('translation_text')[:50]}...")
            print(f"  Arabic: {r.get('arabic_text')}")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_search()
