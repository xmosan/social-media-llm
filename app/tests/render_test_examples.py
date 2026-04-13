import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal
from app.services.quran_service import get_quran_ayah
from app.services.quran_caption_service import generate_ai_caption_from_quran
from app.services.image_renderer import render_minimal_quote_card
from app.config import settings

def generate_visual_examples():
    db = SessionLocal()
    output_dir = os.path.abspath(settings.uploads_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    examples = [
        (94, 5, "quran", "reflective"),
        (2, 153, "fajr_horizon", "poetic"),
    ]
    
    print("🎨 GENERATING CINEMATIC VISUAL EXAMPLES 🎨\n")
    
    rendered_paths = []
    
    try:
        for surah, ayah_num, style_key, tone in examples:
            ayah = get_quran_ayah(db, surah, ayah_num)
            if not ayah:
                print(f"❌ Ayah {surah}:{ayah_num} not found.")
                continue
            
            print(f"🔄 Processing {ayah.title} with style '{style_key}'...")
            
            # 1. Generate Grounded Caption (3 segments separated by \n\n)
            caption = generate_ai_caption_from_quran(ayah, style=tone)
            
            # 2. Parse into segments for the renderer
            # The renderer expects a list of dictionaries with 'text' and 'size'
            clean_segments = [p.strip() for p in caption.split("\n\n") if p.strip()]
            
            # Mapping sizes as used in image_card.py
            # 36, 68, 48
            sizes = [36, 68, 48]
            segments_for_render = []
            for i, text in enumerate(clean_segments[:3]):
                is_ar = any("\u0600" <= c <= "\u06FF" for c in text)
                segments_for_render.append({
                    "text": text,
                    "size": sizes[i],
                    "is_arabic": is_ar
                })
            
            # 3. Render
            render_url = render_minimal_quote_card(
                segments=segments_for_render,
                output_dir=output_dir,
                style=style_key,
                mode="preset"
            )
            
            # Convert URL to local path for embedding
            filename = render_url.split("/")[-1]
            local_path = os.path.join(output_dir, filename)
            rendered_paths.append((ayah.title, render_url, local_path))
            print(f"✅ Rendered: {render_url}")
            
    finally:
        db.close()
    
    return rendered_paths

if __name__ == "__main__":
    paths = generate_visual_examples()
    print("\n--- SUMMARY ---")
    for title, url, local in paths:
        print(f"{title}|{url}|{local}")
