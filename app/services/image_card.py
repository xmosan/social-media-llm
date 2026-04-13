# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
from app.config import settings
from .image_renderer import render_minimal_quote_card, PRESET_TEXT, CUSTOM_TEXT_LIGHT, CUSTOM_TEXT_DARK

# Base font sizes per zone (reference, quote, support)
ZONE_SIZES = {
    "quran":      (36, 68, 48),
    "fajr":       (34, 64, 46),
    "scholar":    (32, 60, 44),
    "madinah":    (36, 68, 48),
    "kaaba":      (36, 70, 50),
    "laylulqadr": (34, 64, 46),
    "custom":     (36, 68, 48),  # default — overridden by palette in renderer
}


def is_arabic_segment(text: str) -> bool:
    """Detects if a string contains Arabic characters."""
    return any("\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F" for c in text)

def generate_quote_card(
    caption: str,
    style: str = "quran",
    visual_prompt: str = None,
    mode: str = "preset",
    text_style_prompt: str = "",
    readability_priority: bool = True,
    experimental_mode: bool = False,
    engine: str = "dalle",
    glossy: bool = False
) -> str:
    """
    Parses an Islamic caption and renders a premium quote card.
    Supports Dual-Language (Arabic + English) detection and layout.
    """
    import re

    print(f"\n🖼️  [ImageCard] mode={mode} | style={style}")
    print(f"📝 [ImageCard] caption[:120]={repr(caption[:120])}")

    # ── Determine effective mode ──────────────────────────────────────────────
    if style == "custom":
        mode = "custom"

    # ── Parse caption into logical zones ──────────────────────────────────────
    clean  = re.sub(r"\*\*|__?|~~", "", caption).strip()
    clean  = re.sub(r"^(Line \d:|Source:|Reflection:|Takeaway:|Insight:|Translation:)\s*",
                    "", clean, flags=re.MULTILINE | re.IGNORECASE)

    # Split on double newlines for zones
    raw_zones = [p.strip() for p in clean.split("\n\n") if p.strip()]
    if len(raw_zones) < 2:
        raw_zones = [p.strip() for p in clean.split("\n") if p.strip()]

    # Guard: Pad to at least 3
    while len(raw_zones) < 3:
        raw_zones.append("")

    # ── Dual-Language Processing ──────────────────────────────────────────────
    # Identify if any zone contains Arabic + English or if we have separate 
    # Arabic/English zones that should be paired.
    segments = []
    key   = style if style in ZONE_SIZES else "quran"
    sizes = ZONE_SIZES[key]

    for i, text in enumerate(raw_zones[:3]):
        if not text: continue
        
        # If the segment contains Arabic, we mark it as such for the renderer
        is_ar = is_arabic_segment(text)
        
        # Special Case: If the text contains BOTH Arabic and English (e.g., merged by AI)
        # We might want to split them, but for now we'll let the renderer handle the font switching
        segments.append({
            "text":  text,
            "size":  sizes[i],
            "is_arabic": is_ar,
            "color": (255, 255, 255)
        })

    print(f"📦 [ImageCard] Final Segments: {len(segments)}")

    # ── Render ────────────────────────────────────────────────────────────────
    output_dir = settings.uploads_dir
    url = render_minimal_quote_card(
        segments,
        output_dir,
        style=style,
        visual_prompt=visual_prompt,
        mode=mode,
        text_style_prompt=text_style_prompt,
        readability_priority=readability_priority,
        experimental_mode=experimental_mode,
        engine=engine,
        glossy=glossy
    )
    return url


def create_quote_card(text: str, attribution: str, outfile_path: str):
    """Legacy single-image generation (kept for compatibility)."""
    from PIL import Image, ImageDraw, ImageFont
    size = (1080, 1080)
    img  = Image.new("RGB", size, (20, 25, 20))
    draw = ImageDraw.Draw(img)
    draw.text((size[0] // 2, size[1] // 2), text, fill=(255, 255, 255), anchor="mm")
    img.save(outfile_path, quality=95)
