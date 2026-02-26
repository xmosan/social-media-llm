import os
import time
import textwrap
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

    # 7. Save and Return Public URL
    filename = f"card_{int(time.time())}.jpg"
    final_path = os.path.join(output_dir, filename)
    bg.save(final_path, "JPEG", quality=90)
    
    public_url = f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
    return public_url
