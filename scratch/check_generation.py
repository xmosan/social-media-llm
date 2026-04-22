import os
import sys
import time

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.image_renderer import render_quote_card
from app.config import settings

def test_render():
    # Simulate a "sabr" quote card from the growth plan
    quote_text = "Verily, with hardship comes ease."
    reference = "Quran 94:5"
    output_dir = settings.uploads_dir
    
    print(f"🎨 Generating test quote card in {output_dir}...")
    
    # We pass None for bg_path to trigger the procedural background
    url = render_quote_card(None, quote_text, reference, output_dir)
    
    print(f"✅ Generated URL: {url}")
    
    # Let's check the local file path
    filename = url.split("/")[-1]
    local_path = os.path.join(output_dir, filename)
    
    if os.path.exists(local_path):
        print(f"📦 File physically exists at: {local_path}")
        print(f"📏 File size: {os.path.getsize(local_path)} bytes")
    else:
        print(f"❌ ERROR: File not found at {local_path}")

if __name__ == "__main__":
    test_render()
