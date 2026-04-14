
import os
import sys
from PIL import Image, ImageDraw

# Add working directory to path for app imports
sys.path.append(os.getcwd())

from app.services.image_renderer import render_minimal_quote_card
from app.config import settings

def render_full_examples():
    output_dir = os.path.join(os.getcwd(), "renders/test")
    os.makedirs(output_dir, exist_ok=True)

    # I have these backgrounds from the earlier step
    dalle_bg_path = "/Users/hamoodi/.gemini/antigravity/brain/d483a2d7-5452-46e8-876d-8a094c971568/quran_card_dalle_example_1776173944813.png"
    gemini_bg_path = "/Users/hamoodi/.gemini/antigravity/brain/d483a2d7-5452-46e8-876d-8a094c971568/quran_card_gemini_example_1776173968911.png"

    # Define segments for both (Reference, Quote, Support)
    segments_dalle = [
        {"text": "Qur'an 70:5", "size": 36, "is_arabic": False},
        {"text": "فَاصْبِرْ صَبْرًا جَمِيلًا", "size": 68, "is_arabic": True},
        {"text": "So be patient with gracious patience.", "size": 48, "is_arabic": False}
    ]

    segments_gemini = [
        {"text": "Qur'an 94:5", "size": 36, "is_arabic": False},
        {"text": "فَإِنَّ مَعَ الْعُسْرِ يُسْرًا", "size": 68, "is_arabic": True},
        {"text": "For indeed, with hardship [will be] ease.", "size": 48, "is_arabic": False}
    ]

    # Unfortunately, render_minimal_quote_card generates the background inside. 
    # I will monkeypatch generate_background to return my existing images.
    import app.services.image_renderer as ir
    
    orig_gen = ir.generate_background
    
    # Render DALL-E Full Example
    ir.generate_background = lambda *args, **kwargs: Image.open(dalle_bg_path).convert("RGB")
    url_dalle = render_minimal_quote_card(
        segments_dalle,
        output_dir,
        style="quran",
        visual_prompt="Sacred Black theme",
        mode="custom",
        engine="dalle"
    )
    print(f"DALL-E Full: {url_dalle}")

    # Render Gemini Full Example
    ir.generate_background = lambda *args, **kwargs: Image.open(gemini_bg_path).convert("RGB")
    url_gemini = render_minimal_quote_card(
        segments_gemini,
        output_dir,
        style="quran",
        visual_prompt="Celestial Cinematic theme",
        mode="custom",
        engine="gemini"
    )
    print(f"Gemini Full: {url_gemini}")
    
    # Restore
    ir.generate_background = orig_gen

if __name__ == "__main__":
    render_full_examples()
