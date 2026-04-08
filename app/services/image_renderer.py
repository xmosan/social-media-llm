# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import time
import textwrap
import math
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from app.config import settings

def render_quote_card(background_local_path: str, quote: str, reference: str, output_dir: str) -> str:
    """
    Renders a 1080x1080 quote card by overlaying text on a background image.
    """
    # 1. Load Background
    try:
        bg = Image.open(background_local_path).convert("RGB")
    except Exception as e:
        print(f"[RENDER] Failed to open background: {e}")
        raise

    # 2. Resize and Center Crop to 1080x1080
    target_size = (1080, 1080)
    bg_ratio = bg.width / bg.height
    target_ratio = target_size[0] / target_size[1]

    if bg_ratio > target_ratio:
        # Background is wider - crop sides
        new_width = int(target_ratio * bg.height)
        offset = (bg.width - new_width) // 2
        bg = bg.crop((offset, 0, offset + new_width, bg.height))
    else:
        # Background is taller - crop top/bottom
        new_height = int(bg.width / target_ratio)
        offset = (bg.height - new_height) // 2
        bg = bg.crop((0, offset, bg.width, offset + new_height))

    bg = bg.resize(target_size, Image.Resampling.LANCZOS)

    # 3. Apply Subtle Dark Gradient/Overlay for readability
    overlay = Image.new("RGBA", target_size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    
    # Simple bottom-heavy gradient
    for i in range(1080):
        # Starts getting darker from 40% down
        if i > 400:
            alpha = int(((i - 400) / 680) * 160) # Max alpha 160
            draw_overlay.line([(0, i), (1080, i)], fill=(0, 0, 0, alpha))
            
    bg.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(bg)

    # 4. Font Loading
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    font_inter_path = os.path.join(base_dir, "assets", "fonts", "Inter.ttf")
    font_amiri_path = os.path.join(base_dir, "assets", "fonts", "Amiri-Regular.ttf")

    # Use Inter for English, Amiri if Arabic detected (simplified: use Inter for all if Amiri missing)
    try:
        font_main = ImageFont.truetype(font_inter_path, 48)
        font_ref = ImageFont.truetype(font_inter_path, 32)
    except:
        font_main = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    # 5. Text Wrapping & Truncation (Guardrail)
    if len(quote) > 240:
        quote = quote[:237] + "..."

    # Wrap text to fit with margins (100px on each side)
    wrapped_lines = textwrap.wrap(quote, width=35) # Approx 35 chars for 48px font

    # Calculate total height of text block
    line_spacing = 15
    line_heights = []
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font_main)
        line_heights.append(bbox[3] - bbox[1])
    
    text_block_height = sum(line_heights) + (len(wrapped_lines) - 1) * line_spacing
    ref_bbox = draw.textbbox((0, 0), reference, font=font_ref)
    ref_height = ref_bbox[3] - ref_bbox[1]
    
    total_height = text_block_height + 60 + ref_height # 60px gap between quote and ref

    # Start drawing from middle-bottom area
    y = (1080 - total_height) // 2 + 50 # Slightly lower than center

    # 6. Draw Text with Shadow (Readability)
    def draw_text_with_shadow(draw_obj, pos, text, font, color, shadow_color=(0, 0, 0, 180)):
        x, y = pos
        # Draw shadow
        draw_obj.text((x + 2, y + 2), text, font=font, fill=shadow_color)
        # Draw main text
        draw_obj.text((x, y), text, font=font, fill=color)

    for i, line in enumerate(wrapped_lines):
        line_w = draw.textbbox((0, 0), line, font=font_main)[2]
        line_x = (1080 - line_w) // 2
        draw_text_with_shadow(draw, (line_x, y), line, font_main, (255, 255, 255))
        y += line_heights[i] + line_spacing

    # Draw Reference
    y += 40
    ref_w = draw.textbbox((0, 0), reference, font=font_ref)[2]
    ref_x = (1080 - ref_w) // 2
    draw_text_with_shadow(draw, (ref_x, y), reference, font_ref, (200, 200, 200))

import random

def draw_paper_texture(draw, size, color=(245, 245, 235)):
    """Generates a procedural handmade paper/parchment texture."""
    # Base color
    draw.rectangle([0, 0, size[0], size[1]], fill=color)
    # Add subtle grain/noise
    for _ in range(25000):
        x, y = random.randint(0, size[0]-1), random.randint(0, size[1]-1)
        alpha = random.randint(5, 15)
        draw.point((x, y), fill=(0, 0, 0, alpha))
    # Add some fiber-like strokes
    for _ in range(150):
        x1, y1 = random.randint(0, size[0]-1), random.randint(0, size[1]-1)
        length = random.randint(2, 8)
        angle = random.uniform(0, math.pi * 2)
        x2, y2 = x1 + math.cos(angle) * length, y1 + math.sin(angle) * length
        draw.line([x1, y1, x2, y2], fill=(0, 0, 0, random.randint(3, 8)), width=1)

def draw_starry_noise(draw, size, density=0.0005):
    """Adds subtle white speckles to simulate a night sky."""
    num_stars = int(size[0] * size[1] * density)
    for _ in range(num_stars):
        x, y = random.randint(0, size[0]-1), random.randint(0, size[1]-1)
        # Varying star size and brightness
        s_size = random.choice([1, 1, 1, 2])
        alpha = random.randint(80, 255)
        if s_size == 1:
            draw.point((x, y), fill=(255, 255, 255, alpha))
        else:
            draw.rectangle([x, y, x+1, y+1], fill=(255, 255, 255, alpha))

def draw_textured_background(draw, size, base_color):
    """Draws a base color plus subtle procedural noise for a 'dark paper/parchment' texture."""
    width, height = size
    draw.rectangle([0, 0, width, height], fill=base_color)
    for _ in range(40000):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        grain = random.randint(-12, 12)
        r = max(0, min(255, base_color[0] + grain))
        g = max(0, min(255, base_color[1] + grain))
        b = max(0, min(255, base_color[2] + grain))
        draw.point((x, y), fill=(r, g, b))

def draw_gold_border(draw, size, border_width=30):
    """Draws a frame around the card in Gold with a subtle inner edge."""
    gold_color = (190, 150, 40) # Aged gold
    w, h = size
    # Outer frame
    draw.rectangle([border_width, border_width, w - border_width, h - border_width], 
                   outline=gold_color, width=3)
    # Inner rim
    draw.rectangle([border_width + 10, border_width + 10, w - border_width - 10, h - border_width - 10], 
                   outline=gold_color, width=1)

def draw_text_highlight(draw, bbox, bg_color):
    """Draws a rounded rectangle background behind a text bbox."""
    padding = 25
    draw.rounded_rectangle([bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding], 
                           radius=15, fill=bg_color)

def draw_radial_gradient(draw, size, color_start, color_end):
    """Draws a smooth radial gradient."""
    width, height = size
    center_x, center_y = width / 2, height / 2
    max_dist = math.sqrt(center_x**2 + center_y**2)
    for radius in range(int(max_dist), 0, -4):
        ratio = min(1, radius / (max_dist * 0.9))
        r = int(color_start[0] * (1 - ratio) + color_end[0] * ratio)
        g = int(color_start[1] * (1 - ratio) + color_end[1] * ratio)
        b = int(color_start[2] * (1 - ratio) + color_end[2] * ratio)
        draw.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(r, g, b))

def draw_islamic_pattern(draw, size, color):
    """Draws a visible but subtle Rub el Hizb tile pattern."""
    w, h = size
    step = 140
    for y in range(0, h + step, step):
        for x in range(0, w + step, step):
            s = 25
            draw.polygon([(x-s, y-s), (x+s, y-s), (x+s, y+s), (x-s, y+s)], outline=color, width=1)
            s_diag = int(s * 1.414)
            draw.polygon([(x-s_diag, y), (x, y-s_diag), (x+s_diag, y), (x, y+s_diag)], outline=color, width=1)

def apply_vignette(image, intensity=0.6):
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    center_x, center_y = width / 2, height / 2
    max_dist = math.sqrt(center_x**2 + center_y**2)
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
            alpha = int((dist / max_dist) ** 2.5 * 255 * intensity)
            draw.rectangle([x, y, x+4, y+4], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

def draw_text_with_shadow(draw, position, text, font, fill, shadow_fill=(0, 0, 0, 100), offset=(3, 3)):
    """Draws text with character-level fallback support for Islamic symbols."""
    x, y = position
    # Shadow first
    draw_text_with_fallback(draw, (x + offset[0], y + offset[1]), text, font, fill=shadow_fill)
    # Main text
    draw_text_with_fallback(draw, (x, y), text, font, fill=fill)

def get_font_for_char(char, primary_font, primary_size):
    """Returns the primary font or fallback (Amiri) if the symbol is Arabic."""
    # Specifically catch common Islamic symbols and the Arabic unicode range
    # ﷺ is U+FDFA
    if char == '\ufdfa' or '\u0600' <= char <= '\u06ff' or '\ufb50' <= char <= '\ufdff':
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        fallback_path = os.path.join(base_dir, "assets", "fonts", "Amiri-Regular.ttf")
        return ImageFont.truetype(fallback_path, primary_size)
    return primary_font

def draw_text_with_fallback(draw, position, text, font, fill):
    """Simple character-level fallback drawing."""
    x, y = position
    size = font.size if hasattr(font, 'size') else 40
    for char in text:
        f = get_font_for_char(char, font, size)
        draw.text((x, y), char, font=f, fill=fill)
        # Calculate width
        bbox = draw.textbbox((0, 0), char, font=f)
        x += bbox[2] - bbox[0]

def draw_text_spaced(draw, position, text, font, fill, spacing=2):
    """Draws text with custom letter spacing and font fallback."""
    x, y = position
    size = font.size if hasattr(font, 'size') else 40
    for char in text:
        f = get_font_for_char(char, font, size)
        draw.text((x, y), char, font=f, fill=fill)
        # Advance x by character width + spacing
        bbox = draw.textbbox((0, 0), char, font=f)
        char_w = bbox[2] - bbox[0]
        x += char_w + spacing

def render_minimal_quote_card(segments: list, output_dir: str, style: str = "classic") -> str:
    """
    Final Designer Engine: 3 Emotionally Powerful styles.
    """
    target_size = (1080, 1080)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Selection of Font based on style
    font_file = "Inter.ttf"
    if style in ["classic", "scholar", "ethereal"]:
        font_file = "Amiri-Regular.ttf"
    font_path = os.path.join(base_dir, "assets", "fonts", font_file)

    # 1. Background Logic
    if style == "classic":
        bg = Image.new("RGB", target_size, (15, 20, 15))
        draw = ImageDraw.Draw(bg)
        draw_textured_background(draw, target_size, (12, 18, 12))
        draw_islamic_pattern(draw, target_size, (180, 140, 50, 45)) # Visible gold
        bg = apply_vignette(bg, intensity=0.45)
        # Apply border after vignette to keep gold sharp
        draw = ImageDraw.Draw(bg)
        draw_gold_border(draw, target_size, border_width=40)
    elif style == "modern":
        bg = Image.new("RGB", target_size, (5, 5, 5))
        draw = ImageDraw.Draw(bg)
        draw_radial_gradient(draw, target_size, (15, 45, 15), (2, 5, 2))
    elif style == "premium":
        bg = Image.new("RGB", target_size, (0, 0, 0))
        draw = ImageDraw.Draw(bg)
        # Deep green cinematic center (#0F2A1D)
        draw_radial_gradient(draw, target_size, (15, 42, 29), (0, 0, 0))
        bg = apply_vignette(bg, intensity=0.9)
    elif style == "ethereal":
        bg = Image.new("RGB", target_size, (255, 255, 255))
        draw = ImageDraw.Draw(bg)
        # Soft warmth for peace
        draw_radial_gradient(draw, target_size, (255, 255, 255), (245, 245, 235))
        bg = apply_vignette(bg, intensity=0.1) # Very subtle
    elif style == "scholar":
        bg = Image.new("RGB", target_size, (245, 245, 235))
        draw = ImageDraw.Draw(bg)
        draw_paper_texture(draw, target_size)
    elif style == "celestial":
        bg = Image.new("RGB", target_size, (0, 0, 0))
        draw = ImageDraw.Draw(bg)
        # Deep spiritual midnight
        draw_radial_gradient(draw, target_size, (10, 25, 60), (0, 0, 0))
        draw_starry_noise(draw, target_size, density=0.0006)
        bg = apply_vignette(bg, intensity=0.4)
    
    draw = ImageDraw.Draw(bg)

    # 2. Text Calculation
    padding = 180 if style in ["modern", "ethereal"] else 100
    line_spacing = 40 if style in ["premium", "celestial"] else 30
    segment_spacing = 120 if style in ["premium", "celestial"] else 110
    
    prepared_segments = []
    total_height = 0

    for i, seg in enumerate(segments):
        try:
            curr_font = ImageFont.truetype(font_path, seg["size"])
        except:
            curr_font = ImageFont.load_default()

        wrap_max = 1080 - 2 * padding
        wrapped_lines = textwrap.wrap(seg["text"], width=int(wrap_max / (seg["size"] * 0.5)))
        
        line_data = []
        seg_h = 0
        for line in wrapped_lines:
            bbox = draw.textbbox((0, 0), line, font=curr_font)
            h = bbox[3] - bbox[1]
            line_data.append({"line": line, "height": h, "width": bbox[2] - bbox[0], "bbox": bbox})
            seg_h += h + line_spacing
        
        seg_h -= line_spacing
        prepared_segments.append({
            "font": curr_font,
            "lines": line_data,
            "height": seg_h,
            "color": seg["color"],
            "glow": i == 1 and (style in ["modern", "premium", "celestial"])
        })
        total_height += seg_h + (segment_spacing if i < len(segments)-1 else 0)

    # 3. Y Starting Position
    y = (1080 - total_height) // 2
    # Removed premium offset for Perfect Center Alignment

    # 4. Draw Content
    bg_rgba = bg.convert("RGBA")
    
    for i, seg in enumerate(prepared_segments):
        # 1. Soft Glow Layer (Behind Text)
        if seg.get("glow"):
            glow_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_layer)
            ty = y
            
            # Select Glow profile
            if style == "premium":
                g_col = (255, 255, 255, 80) # Subtle white halo
                g_blur = 35 
            elif style == "celestial":
                g_col = (255, 255, 255, 100) # Bright celestial halo
                g_blur = 40
            else: # modern
                g_col = (20, 100, 20, 150) # Subtle green
                g_blur = 18
                
            for ln in seg["lines"]:
                tx = (1080 - ln["width"]) // 2
                draw_text_with_fallback(gd, (tx, ty), ln["line"], seg["font"], fill=g_col)
                ty += ln["height"] + line_spacing
                
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(g_blur))
            bg_rgba = Image.alpha_composite(bg_rgba, glow_layer)

        # 2. Cinematic Text Drawing
        draw_rgba = ImageDraw.Draw(bg_rgba)
        ty = y
        for ln in seg["lines"]:
            tx = (1080 - ln["width"]) // 2
            
            # Application of Cinematic Effects
            if i == 0 and style in ["premium", "celestial"]:
                # Letter-spaced reference with 70% opacity and fallback support
                ref_color = (seg["color"][0], seg["color"][1], seg["color"][2], 180)
                draw_text_spaced(draw_rgba, (tx, ty), ln["line"], seg["font"], fill=ref_color, spacing=4)
            elif i == 1 and style in ["premium", "celestial"]:
                # Shadowed hero text with semi-bold simulation and fallback support
                shadow_col = (0, 0, 0, 150) if style == "premium" else (0, 5, 20, 180)
                draw_text_with_shadow(draw_rgba, (tx, ty), ln["line"], seg["font"], fill=seg["color"], shadow_fill=shadow_col)
            else:
                # Standard drawing for Scholar, Ethereal, and others
                draw_text_with_fallback(draw_rgba, (tx, ty), ln["line"], seg["font"], fill=seg["color"])
                
            ty += ln["height"] + line_spacing
            
        # Adjust spacing for cinematic grouping (Tighter reference)
        current_spacing = segment_spacing
        if i == 0 and style in ["premium", "celestial"]:
            current_spacing = int(segment_spacing * 0.65) # 35% reduction
            
        y = ty + (current_spacing if i < len(prepared_segments)-1 else 0)

    # 5. Save Final Cinematic Image
    final_img = bg_rgba.convert("RGB")
    filename = f"quote_v7_{style}_{int(time.time() * 1000)}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    final_img.save(final_path, quality=95)
    
    return f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
