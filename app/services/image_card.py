# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
from app.config import settings
from app.services.card_typography import contains_arabic
from app.services.image_renderer import render_minimal_quote_card, PRESET_TEXT, CUSTOM_TEXT_LIGHT, CUSTOM_TEXT_DARK

# Base font sizes per zone (reference, quote, support)
ZONE_SIZES = {
    "quran":      (36, 68, 48),
    "fajr":       (34, 64, 46),
    "scholar":    (32, 60, 44),
    "madinah":    (36, 68, 48),
    "kaaba":      (36, 70, 50),
    "laylulqadr": (34, 64, 46),
    "custom":     (36, 68, 48),  # default — overridden by palette in renderer
    # Hadith: slightly smaller base sizes — Hadith text often longer than Quran ayahs
    "hadith":     (34, 60, 42),
}


def is_arabic_segment(text: str) -> bool:
    """Detects if a string contains Arabic characters."""
    return contains_arabic(text)

def generate_quote_card(
    caption: str = None,
    style: str = "quran",
    visual_prompt: str = None,
    mode: str = "preset",
    text_style_prompt: str = "",
    readability_priority: bool = True,
    experimental_mode: bool = False,
    engine: str = "dalle",
    glossy: bool = False,
    card_message: dict = None,
    visual_history: dict = None,
    render_metadata: dict = None,
    layout: str = "english_first",
    background_image=None,
    background_sink=None,
    post_format: str = "feed_4_5",
    allow_sequence: bool = False,
    brand_kit: dict = None,
) -> str:
    """
    Parses an Islamic caption and renders a premium quote card.
    Supports Dual-Language (Arabic + English) detection and layout.
    """
    import re
    if brand_kit is not None:
        from app.services.brand_kit import normalize_brand
        brand_kit = normalize_brand(brand_kit)

    print(f"\n🖼️  [ImageCard] mode={mode} | style={style}")
    
    # ── Determine effective mode ──────────────────────────────────────────────
    if style == "custom":
        mode = "custom"

    # ── Determine zone sizes ──────────────────────────────────────────────────
    # Use 'hadith' sizes when card_message signals a Hadith source
    is_hadith = bool(
        card_message and (
            card_message.get("hadith_collection")
            or card_message.get("hadith_narrator")
            or card_message.get("was_excerpted") is not None
        )
    )
    key = "hadith" if is_hadith else (style if style in ZONE_SIZES else "quran")
    sizes = list(ZONE_SIZES[key])  # mutable copy

    # If this hadith was excerpted (long text truncated at sentence boundary),
    # reduce the headline zone size by ~10% so the excerpt fits comfortably
    if is_hadith and card_message and card_message.get("was_excerpted"):
        sizes[1] = max(44, int(sizes[1] * 0.90))
        print(f"📏 [ImageCard] was_excerpted=True — headline size reduced to {sizes[1]}")

    # ── Parse caption into logical zones ──────────────────────────────────────
    segments = []

    if card_message:
        print(f"📦 [ImageCard] Using structured card_message")
        # Map structured message to zones
        # 1. Eyebrow
        if card_message.get("eyebrow"):
            segments.append({
                "text": card_message["eyebrow"],
                "role": "reference",
                "size": sizes[0],
                "is_arabic": is_arabic_segment(card_message["eyebrow"]),
                "color": (255, 255, 255)
            })
        
        # 1.5 Arabic Text (Specific to Quranic content or if provided in payload)
        if card_message.get("arabic_text"):
            from app.services.source_display import display_range, narration_boundary
            start, end = display_range(card_message)
            boundary = narration_boundary(card_message, "arabic_text")
            segments.append({
                "text": card_message["arabic_text"][start:end],
                "role": "source_arabic",
                "narration_end": max(0, boundary-start) if boundary is not None else None,
                "label": (card_message.get("arabic_display") or {}).get("label"),
                "size": sizes[1],
                "is_arabic": True,
                "color": (255, 255, 255)
            })

        # 2. Headline (The Quote/Verse)
        if card_message.get("headline"):
            from app.services.source_display import narration_boundary
            segments.append({
                "text": card_message["headline"],
                "role": "source_translation",
                "narration_end": narration_boundary(card_message, "headline"),
                "label": "Translation excerpt" if is_hadith and card_message.get("was_excerpted") else None,
                "size": sizes[1] if not card_message.get("arabic_text") else sizes[2],
                "is_arabic": is_arabic_segment(card_message["headline"]),
                "color": (255, 255, 255)
            })
        
        # 3. Supporting Text (Reference/Explanation)
        if card_message.get("supporting_text"):
             segments.append({
                "text": card_message["supporting_text"],
                "role": "reflection",
                "size": sizes[2],
                "is_arabic": is_arabic_segment(card_message["supporting_text"]),
                "color": (255, 255, 255)
            })
    else:
        # Fallback to legacy caption parsing
        print(f"📝 [ImageCard] Fallback to caption parsing: caption[:120]={repr(caption[:120]) if caption else 'None'}")
        if not caption:
             return ""

        clean  = re.sub(r"\*\*|__?|~~", "", caption).strip()
        clean  = re.sub(r"^(Line \d:|Source:|Reflection:|Takeaway:|Insight:|Translation:)\s*",
                        "", clean, flags=re.MULTILINE | re.IGNORECASE)

        # Split on double newlines for zones
        raw_zones = [p.strip() for p in clean.split("\n\n") if p.strip()]
        if len(raw_zones) < 2:
            raw_zones = [p.strip() for p in clean.split("\n") if p.strip()]

        for i, text in enumerate(raw_zones):
            if not text: continue
            segments.append({
                "text":  text,
                "size":  sizes[min(i, 2)],
                "is_arabic": is_arabic_segment(text),
                "color": (255, 255, 255)
            })

    print(f"📦 [ImageCard] Final Segments: {len(segments)}")

    # One canonical renderer for both single cards and complete sequences.
    from app.services.card_typography import DESIGN_FAMILIES, plan_sequence
    from app.services.media_sequence import card_digest
    if allow_sequence and card_message and card_message.get("was_excerpted"):
        from app.services.card_typography import CardTypographyError
        raise CardTypographyError("This legacy card uses an excerpt. Rebuild its card message from the full source before creating a sequence.")
    if allow_sequence and render_metadata is None:
        raise ValueError("Sequence generation requires a manifest destination")
    pages = plan_sequence(segments, family=style, layout=layout, post_format=post_format, brand_kit=brand_kit) if allow_sequence and style in DESIGN_FAMILIES else [{"segments": segments, "slices": [], "label": "Complete source"}]
    from app.services.vision_families import SCENE_FAMILIES
    scene_bounds = None
    if style in SCENE_FAMILIES:
        from app.services.card_typography import layout_card
        # Preflight every page before a paid request, and compose one reusable
        # background for their combined reading area, not just the first page.
        scene_bounds = [block["bounds"] for page in pages for block in
            layout_card(page["segments"], family=style, layout=layout, post_format=post_format, brand_kit=brand_kit)[1]]
    if card_message and card_message.get("arabic_display"):
        from app.services.source_display import display_range
        start, _ = display_range(card_message)
        for page in pages:
            if len(pages) == 1:
                page["label"] = "Source with Arabic chain excerpt"
            for part in page["slices"]:
                if part["role"] == "source_arabic":
                    part["start"] += start
                    part["end"] += start
    retained = background_image
    def keep_photo(image):
        nonlocal retained
        retained = image
        if background_sink:
            background_sink(image)
    rendered = []
    for i, page in enumerate(pages):
        metadata = {}
        url = render_minimal_quote_card(
            page["segments"], settings.uploads_dir, style=style,
            visual_prompt=visual_prompt, mode=mode, text_style_prompt=text_style_prompt,
            readability_priority=readability_priority, experimental_mode=experimental_mode,
            engine=engine, glossy=glossy, visual_history=visual_history,
            render_metadata=metadata, layout=layout, background_image=retained,
            background_sink=keep_photo, post_format=post_format,
            brand_kit=brand_kit,
            **({"scene_bounds": scene_bounds} if scene_bounds is not None else {}),
        )
        rendered.append({"index": i, "url": url, "label": page["label"], "slices": page["slices"],
                         "quality": metadata.get("quality", {}),
                         "width": 1080, "height": 1920 if post_format == "story_9_16" else 1350})
        if render_metadata is not None and i == 0:
            render_metadata.update(metadata)
    if allow_sequence:
        actual_format = "story_9_16" if post_format == "story_9_16" else "carousel_4_5" if len(rendered)>1 else "feed_4_5"
        render_metadata["media_manifest"] = {"version": 1, "format": actual_format,
                                            "card_digest": card_digest(card_message), "pages": rendered,
                                            **({"brand_kit": brand_kit} if brand_kit is not None else {})}
    return rendered[0]["url"]



def create_quote_card(text: str, attribution: str, outfile_path: str):
    """Legacy single-image generation (kept for compatibility)."""
    from PIL import Image, ImageDraw, ImageFont
    size = (1080, 1080)
    img  = Image.new("RGB", size, (20, 25, 20))
    draw = ImageDraw.Draw(img)
    draw.text((size[0] // 2, size[1] // 2), text, fill=(255, 255, 255), anchor="mm")
    img.save(outfile_path, quality=95)
