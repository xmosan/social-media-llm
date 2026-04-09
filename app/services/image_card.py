# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
from app.config import settings
from .image_renderer import render_minimal_quote_card

def generate_quote_card(caption: str, style: str = "classic", visual_prompt: str = None) -> str:
    """
    Parses an Islamic caption and generates an upgraded quote card image.
    Supports styles: 'classic', 'modern', 'premium', etc.
    Influenced by optional visual_prompt.
    """
    # 1. Clean and Split
    clean_caption = caption.replace("**", "").replace("_", "")
    parts = [p.strip() for p in clean_caption.split("\n\n") if p.strip()]
    
    # Clean individual part formatting artifacts
    cleaned_parts = []
    for i, part in enumerate(parts):
        p = part.strip()
        if i == 0:
            # Reference line: strip surrounding quotes
            p = p.strip('"').strip("'").strip("\u201c").strip("\u201d").strip()
        cleaned_parts.append(p)
    parts = cleaned_parts
    
    segments = []
    
    # Text color & size hierarchy per style
    if style == "quran":
        base_size = 46
        styles = [
            {"size": base_size,            "color": (212, 175, 55)},   # gold reference
            {"size": int(base_size * 1.8), "color": (255, 255, 255)},  # white quote
            {"size": int(base_size * 1.25),"color": (195, 215, 195)},  # soft sage support
        ]
    elif style == "fajr":
        base_size = 44
        styles = [
            {"size": base_size,            "color": (140, 170, 245)},  # soft blue reference
            {"size": int(base_size * 1.85),"color": (230, 238, 255)},  # near-white quote
            {"size": int(base_size * 1.3), "color": (170, 195, 240)},  # pale blue support
        ]
    elif style == "madinah":
        base_size = 46
        styles = [
            {"size": base_size,            "color": (212, 165, 60)},   # amber gold reference
            {"size": int(base_size * 1.8), "color": (255, 242, 210)},  # warm cream quote
            {"size": int(base_size * 1.25),"color": (200, 175, 130)},  # sandy support
        ]
    elif style == "kaaba":
        base_size = 46
        styles = [
            {"size": base_size,            "color": (180, 148, 50)},   # muted gold reference
            {"size": int(base_size * 1.85),"color": (255, 255, 255)},  # pure white quote
            {"size": int(base_size * 1.25),"color": (185, 185, 185)},  # silver support
        ]
    elif style == "laylulqadr":
        base_size = 44
        styles = [
            {"size": base_size,            "color": (180, 145, 235)},  # lavender reference
            {"size": int(base_size * 1.85),"color": (238, 230, 255)},  # near-white purple quote
            {"size": int(base_size * 1.3), "color": (195, 175, 240)},  # soft violet support
        ]
    elif style == "scholar":

        base_size = 42
        styles = [
            {"size": base_size, "color": (40, 40, 40)},
            {"size": int(base_size * 1.85), "color": (20, 20, 20)},
            {"size": int(base_size * 1.4), "color": (60, 60, 60)},
        ]
    elif style == "ethereal":
        base_size = 44
        styles = [
            {"size": base_size, "color": (100, 100, 110)},
            {"size": int(base_size * 1.9), "color": (40, 40, 50)},
            {"size": int(base_size * 1.5), "color": (120, 120, 130)},
        ]
    elif style == "celestial":
        base_size = 48
        styles = [
            {"size": base_size, "color": (212, 175, 55)},
            {"size": int(base_size * 1.8), "color": (255, 255, 255)},
            {"size": int(base_size * 1.3), "color": (200, 210, 255)},
        ]
    elif style == "modern":
        base_size = 38
        styles = [
            {"size": base_size, "color": (220, 220, 220)},
            {"size": base_size * 2, "color": (255, 255, 255)},
            {"size": int(base_size * 1.5), "color": (240, 240, 240)},
        ]
    else: # classic
        base_size = 36
        styles = [
            {"size": base_size, "color": (212, 175, 55)},
            {"size": base_size * 2, "color": (255, 255, 255)},
            {"size": int(base_size * 1.5), "color": (230, 230, 230)},
        ]
    
    for i, text in enumerate(parts):
        if i >= len(styles): break
        segments.append({
            "text": text,
            "size": styles[i]["size"],
            "color": styles[i]["color"]
        })

    # 2. Render with Style & Prompt
    output_dir = settings.uploads_dir
    public_url = render_minimal_quote_card(segments, output_dir, style=style, visual_prompt=visual_prompt)
    
    return public_url


def create_quote_card(text: str, attribution: str, outfile_path: str):
    """
    Legacy helper: Creates a simple 1080x1080 quote card.
    """
    # Canvas Settings
    width, height = 1080, 1080
    bg_color = (30, 30, 30) # Dark grey
    text_color = (255, 255, 255) # White
    attr_color = (200, 200, 200) # Light grey
    
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # Font Loading
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    
    font_main = None
    font_attr = None
    for p in font_paths:
        if os.path.exists(p):
            try:
                font_main = ImageFont.truetype(p, 60)
                font_attr = ImageFont.truetype(p, 40)
                break
            except:
                continue
    
    if font_main is None:
        font_main = ImageFont.load_default()
        font_attr = ImageFont.load_default()

    # Text Wrapping
    lines = textwrap.wrap(text, width=35)
    
    # Vertical Centering
    line_spacing = 15
    try:
        line_heights = [draw.textbbox((0, 0), line, font=font_main)[3] - draw.textbbox((0, 0), line, font=font_main)[1] for line in lines]
    except:
        line_heights = [60 for _ in lines]
        
    total_text_height = sum(line_heights) + (len(lines) - 1) * line_spacing
    y = (height - total_text_height) // 2 - 50
    
    # Drawing
    for i, line in enumerate(lines):
        try:
            w = draw.textbbox((0, 0), line, font=font_main)[2]
        except:
            w = len(line) * 30
            
        x = (width - w) // 2
        draw.text((x, y), line, font=font_main, fill=text_color)
        y += line_heights[i] + line_spacing
        
    # Attribution
    if attribution:
        y += 40
        attr_text = f"— {attribution}"
        try:
            w_attr = draw.textbbox((0, 0), attr_text, font=font_attr)[2]
        except:
            w_attr = len(attr_text) * 20
            
        x_attr = (width - w_attr) // 2
        draw.text((x_attr, y), attr_text, font=font_attr, fill=attr_color)
        
    # Save
    img.save(outfile_path, "JPEG", quality=90)
    print(f"[DEBUG] Legacy quote card saved to {outfile_path}")
