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


def generate_quote_card(
    caption: str,
    style: str = "quran",
    visual_prompt: str = None,
    mode: str = "preset",
    text_style_prompt: str = "",
    readability_priority: bool = True,
    experimental_mode: bool = False
) -> str:
    """
    Parses an Islamic caption and renders a premium quote card.

    Args:
        caption:       The full multi-part caption (newline-separated).
        style:         Preset style key (quran/fajr/scholar/madinah/kaaba/laylulqadr)
                       or 'custom' for visual-prompt-driven mode.
        visual_prompt: User's description of the desired visual atmosphere.
        mode:          'preset' | 'custom'

    Returns:
        Public URL of the generated image.
    """
    import re

    print(f"\n🖼️  [ImageCard] mode={mode} | style={style}")
    print(f"📝 [ImageCard] visual_prompt={repr(visual_prompt)}")
    print(f"📄 [ImageCard] caption[:80]={repr(caption[:80])}")

    # ── Determine effective mode ──────────────────────────────────────────────
    # Normalize: if style is 'custom', enforce custom mode
    if style == "custom":
        mode = "custom"

    # ── Parse caption into 3 zones ────────────────────────────────────────────
    clean  = re.sub(r"\*\*|__?|~~", "", caption).strip()
    # Remove label prefixes AI sometimes adds
    clean  = re.sub(r"^(Line \d:|Source:|Reflection:|Takeaway:|Insight:|Translation:)\s*",
                    "", clean, flags=re.MULTILINE | re.IGNORECASE)

    # Split on double newlines
    parts  = [p.strip() for p in clean.split("\n\n") if p.strip()]

    # Fallback: single newlines if < 2 parts found
    if len(parts) < 2:
        parts = [p.strip() for p in clean.split("\n") if p.strip()]

    # Guard: ensure exactly 3 parts (pad or trim)
    while len(parts) < 3:
        parts.append("")
    parts = parts[:3]

    # Clean Zone A (reference): strip surrounding quotes
    ref = parts[0]
    ref = ref.strip('"').strip("'").strip("\u201c").strip("\u201d").strip()
    parts[0] = ref

    print(f"📦 [ImageCard] Parts: {[p[:40] for p in parts]}")

    # ── Font sizes ────────────────────────────────────────────────────────────
    key   = style if style in ZONE_SIZES else "quran"
    sizes = ZONE_SIZES[key]

    # ── Build segments (size only — colors resolved inside renderer) ──────────
    segments = []
    for i, text in enumerate(parts):
        if not text:
            continue
        segments.append({
            "text":  text,
            "size":  sizes[i],
            "color": (255, 255, 255),  # placeholder — renderer applies palette
        })

    print(f"📦 [ImageCard] Segments: {len(segments)}")

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
        experimental_mode=experimental_mode
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
