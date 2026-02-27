# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
from app.config import settings

def create_quote_card(text: str, attribution: str, outfile_path: str):
    """
    Creates a simple 1080x1080 quote card.
    """
    # 1. Canvas Settings
    width, height = 1080, 1080
    bg_color = (30, 30, 30) # Dark grey
    text_color = (255, 255, 255) # White
    attr_color = (200, 200, 200) # Light grey
    
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # 2. Font Loading
    # On macOS, common fonts are in /System/Library/Fonts or /Library/Fonts
    # We'll try to find a nice sans-serif. Fallback to default if not found.
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", # Linux
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

    # 3. Text Wrapping
    # Assume ~30 characters per line at 60px font
    lines = textwrap.wrap(text, width=35)
    
    # 4. Vertical Centering
    # Calculate total height
    line_spacing = 15
    # draw.textbbox is preferred in newer Pillow
    try:
        line_heights = [draw.textbbox((0, 0), line, font=font_main)[3] - draw.textbbox((0, 0), line, font=font_main)[1] for line in lines]
    except:
        line_heights = [60 for _ in lines] # Fallback
        
    total_text_height = sum(line_heights) + (len(lines) - 1) * line_spacing
    
    y = (height - total_text_height) // 2 - 50 # Slightly above center
    
    # 5. Drawing
    for i, line in enumerate(lines):
        # Center horizontally
        try:
            w = draw.textbbox((0, 0), line, font=font_main)[2]
        except:
            w = len(line) * 30 # Rough estimate
            
        x = (width - w) // 2
        draw.text((x, y), line, font=font_main, fill=text_color)
        y += line_heights[i] + line_spacing
        
    # 6. Attribution
    if attribution:
        y += 40 # Padding
        attr_text = f"— {attribution}"
        try:
            w_attr = draw.textbbox((0, 0), attr_text, font=font_attr)[2]
        except:
            w_attr = len(attr_text) * 20
            
        x_attr = (width - w_attr) // 2
        draw.text((x_attr, y), attr_text, font=font_attr, fill=attr_color)
        
    # 7. Save
    img.save(outfile_path, "JPEG", quality=90)
    print(f"[DEBUG] Quote card saved to {outfile_path}")
