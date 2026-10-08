"""Sabeel card renderer: measured feed layouts, shared quality gate, legacy backgrounds.

New defaults use restrained editorial, photography and paper families. Existing
scene/gallery choices remain compatible and pass through the same text gate.
"""

import os
import time
import textwrap
import math
import random
import json
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from app.services.card_typography import CardTypographyError, layout_card, paint_card_text, display_text
from app.services.text_provider import generate_text, Glow, TextGenerationError
from app.config import settings
from app.services.image_provider import generate_configured_image, configured_image_cache_key

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _ARABIC_OK = True
except ImportError:
    _ARABIC_OK = False
    print("⚠️ arabic-reshaper or python-bidi not found. Arabic rendering will be degraded.")

# ── Visual System Layer ───────────────────────────────────────────────────────
# Pre-declare as safe defaults so NameError is impossible if import fails
_VS_OK = False
vs_interpret = vs_compose = vs_analyze = vs_adapt = vs_load_cache = vs_save_cache = None

try:
    from app.services.visual_system import (
        interpret_prompt      as vs_interpret,
        interpret_text_style  as vs_interpret_text,
        compose_dalle_prompt  as vs_compose,
        compose_gemini_prompt as vs_compose_gemini,
        analyze_background    as vs_analyze,
        adapt_typography      as vs_adapt,
        load_bg_cache         as vs_load_cache,
        save_bg_cache         as vs_save_cache,
    )
    _VS_OK = True
    print("✅ visual_system loaded OK")
except Exception as _vs_err:
    print(f"⚠️  visual_system unavailable: {_vs_err}")
    vs_compose_gemini = None
    _VS_OK = False



# ─────────────────────────────────────────────────────────────────────────────
# OPENAI
# ─────────────────────────────────────────────────────────────────────────────

# ── Arabic Support ────────────────────────────────────────────────────────────
ARABIC_FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "fonts", "Amiri-Regular.ttf")

def is_arabic_text(text: str) -> bool:
    """Detects if a string contains Arabic characters, including core, supplement, extended, and presentation forms."""
    if not text: return False
    # Check for any Arabic character in the standard blocks
    return any(
        "\u0600" <= c <= "\u06FF" or  # Arabic
        "\u0750" <= c <= "\u077F" or  # Arabic Supplement
        "\u08A0" <= c <= "\u08FF" or  # Arabic Extended-A
        "\uFB50" <= c <= "\uFDFF" or  # Arabic Presentation Forms-A
        "\uFE70" <= c <= "\uFEFF"     # Arabic Presentation Forms-B
        for c in text
    )

def reshape_arabic(text: str) -> str:
    """Compatibility wrapper; direction is inferred from the logical paragraph."""
    if is_arabic_text(text) and not _ARABIC_OK:
        raise ValueError("Arabic shaping support is required to render source text")
    return display_text(text)

# v8.0 CINEMATIC SETTINGS
SHOW_READABILITY_MASKS = False

def draw_radial_halo(image: Image.Image, center: tuple, radius: int, color: tuple, opacity: int):
    """
    Creates a soft atmospheric radial halo (blurred ellipse) behind the text.
    """
    if opacity <= 0 or radius <= 0:
        return image
        
    w, h = image.size
    # Blur on the full canvas. A cropped halo tile leaves a visible rectangular
    # seam because its blurred edge still has nonzero opacity when pasted.
    halo_mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(halo_mask)
    
    # Draw radial gradient via multiple concentric circles or a single blurred ellipse
    # A blurred ellipse is much smoother for cinematic effects
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    halo_mask = halo_mask.filter(ImageFilter.GaussianBlur(radius / 2.5))
    
    # Apply requested alpha/opacity
    halo_mask = Image.eval(halo_mask, lambda x: int(x * (opacity / 255.0)))
    
    halo_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    halo_color = (int(color[0]), int(color[1]), int(color[2]), 255)
    
    # Paste the blurred halo at the center
    # center is (cx, cy)
    halo_layer.paste(halo_color, (0, 0), halo_mask)
    
    if SHOW_READABILITY_MASKS:
        # Debug: Magenta border for mask visualization
        draw_debug = ImageDraw.Draw(halo_layer)
        draw_debug.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(255, 0, 255, 180), width=2)

    return Image.alpha_composite(image.convert("RGBA"), halo_layer).convert("RGB")


def draw_top_gradient_band(image: Image.Image, color: tuple, alpha: int, height_percent: float = 0.20):
    """
    Creates a soft horizontal gradient band at the top of the image (light shaping).
    """
    w, h = image.size
    band_h = int(h * height_percent)
    
    # Create vertical gradient mask
    band_mask = Image.new("L", (w, band_h), 0)
    for y in range(band_h):
        # Linear falloff from top to bottom
        v = int(255 * (1.0 - (y / float(band_h))**1.5))
        for x in range(w):
            band_mask.putpixel((x, y), v)
            
    band_mask = Image.eval(band_mask, lambda x: int(x * (alpha / 255.0)))
    
    band_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    band_color = (int(color[0]), int(color[1]), int(color[2]), 255)
    band_layer.paste(band_color, (0, 0), band_mask)
    
    if SHOW_READABILITY_MASKS:
        draw_debug = ImageDraw.Draw(band_layer)
        draw_debug.rectangle((0, 0, w, band_h), outline=(0, 255, 255, 180), width=2)
        
    return Image.alpha_composite(image.convert("RGBA"), band_layer).convert("RGB")

def draw_bottom_gradient_band(image: Image.Image, color: tuple, alpha: int, height_percent: float = 0.35):
    """
    Creates a soft horizontal gradient band at the bottom of the image for text legibility.
    """
    w, h = image.size
    band_h = int(h * height_percent)
    start_y = h - band_h
    
    # Create vertical gradient mask
    band_mask = Image.new("L", (w, band_h), 0)
    for y in range(band_h):
        # Quadratic falloff from bottom to top
        v = int(255 * ((y / float(band_h))**1.8))
        for x in range(w):
            band_mask.putpixel((x, y), v)
            
    band_mask = Image.eval(band_mask, lambda x: int(x * (alpha / 255.0)))
    
    band_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    band_color = (int(color[0]), int(color[1]), int(color[2]), 255)
    band_layer.paste(band_color, (0, start_y), band_mask)
    
    if SHOW_READABILITY_MASKS:
        draw_debug = ImageDraw.Draw(band_layer)
        draw_debug.rectangle((0, start_y, w, h), outline=(0, 255, 0, 180), width=2)
        
    return Image.alpha_composite(image.convert("RGBA"), band_layer).convert("RGB")

# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION EXTRACTORS
# ─────────────────────────────────────────────────────────────────────────────

def _extract_intensity(p: str) -> float:
    """Effect strength. Floor is 0.65 so 'subtle X' modifiers on individual
    elements don't collapse the whole card to invisible.
    subtle/minimal = 0.65  balanced = 0.80  dramatic = 1.0
    """
    if any(k in p for k in ["dramatic", "bold", "intense", "powerful",
                              "vivid", "rich", "strong", "heavy", "deep"]):
        return 1.0
    if any(k in p for k in ["subtle", "soft", "gentle", "light",
                              "quiet", "faint", "delicate", "minimal"]):
        return 0.65   # floor — keeps ALL effects clearly visible
    return 0.80


def _extract_material(p: str) -> str:
    if "obsidian" in p:                           return "obsidian"
    if any(k in p for k in ["marble", "stone", "granite", "slate"]): return "marble"
    if any(k in p for k in ["velvet", "silk", "satin"]):             return "velvet"
    if "parchment" in p or "papyrus" in p or "vellum" in p:          return "parchment"
    if "manuscript" in p:                                              return "manuscript"
    if "paper" in p or "aged paper" in p:                             return "paper"
    return "none"


def _extract_atmosphere(p: str) -> str:
    if any(k in p for k in ["celestial", "heavenly", "divine light"]): return "celestial"
    if any(k in p for k in ["moonlit", "moonlight", "lunar", "moon"]): return "moonlit"
    if any(k in p for k in ["sacred", "holy", "sanctified"]):          return "sacred"
    if any(k in p for k in ["ancient", "timeless", "classical"]):      return "ancient"
    if any(k in p for k in ["cinematic", "filmic"]):                   return "cinematic"
    if any(k in p for k in ["spiritual", "transcendent", "mystical"]): return "spiritual"
    if any(k in p for k in ["peaceful", "serene", "calm", "tranquil"]): return "peaceful"
    if any(k in p for k in ["dramatic", "epic"]):                      return "dramatic"
    return "none"


def _extract_border(p: str) -> str:
    if any(k in p for k in ["corner line", "corner lines", "corner ornament",
                              "corner accent", "corner filigree", "corner gold",
                              "gold corner", "golden corner"]):
        return "corner_filigree"
    if any(k in p for k in ["manuscript border", "manuscript frame",
                              "double line", "double frame", "manuscript edge"]):
        return "manuscript"
    if any(k in p for k in ["full border", "surrounding border", "complete frame"]):
        return "gold_block"
    if any(k in p for k in ["gold", "golden", "border", "frame", "corner",
                              "ornament", "gilded", "filigree"]):
        return "corner_filigree"
    return "none"


def balanced_text_wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw_tmp: ImageDraw.Draw, letter_spacing: int = 0) -> list[str]:
    """
    Split text into lines that fit within max_width, targeting balanced widths.
    Accounts for letter_spacing (tracking) in width calculations.
    Ensures NO text is lost.
    """
    words = text.strip().split()
    if not words: return []
    
    # Calculate widths for all words with tracking
    def get_word_w(w):
        w_raw = draw_tmp.textbbox((0, 0), w, font=font)[2]
        return w_raw + len(w) * letter_spacing

    space_w = draw_tmp.textbbox((0, 0), " ", font=font)[2] + letter_spacing
    
    lines = []
    curr_line = []
    curr_w = 0
    
    for word in words:
        word_w = get_word_w(word)
        # If adding this word exceeds max_width, start a new line
        if curr_line and (curr_w + space_w + word_w > max_width):
            lines.append(" ".join(curr_line))
            curr_line = [word]
            curr_w = word_w
        else:
            if curr_line:
                curr_w += space_w
            curr_line.append(word)
            curr_w += word_w
            
    if curr_line:
        lines.append(" ".join(curr_line))
        
    return lines

def fit_text_to_zone(
    text: str, 
    font_path: str, 
    max_w: int, 
    max_h: int, 
    start_size: int, 
    draw_tmp: ImageDraw.Draw,
    min_size: int = 24,
    base_ls: int = 0,
    base_tracking: int = 0,
    is_arabic: bool = False
):
    """
    Iteratively fits text into a budget using size, tracking, and leading adjustments.
    Returns: (list[str], ImageFont.FreeTypeFont, block_h, final_ls, final_tracking)
    """
    # MEASUREMENT PREPARATION (v3 Absolute Fix)
    # We use a temporary reshaped string for width measurement only.
    # We DO NOT modify the original 'text' variable because we want to 
    # return logical (un-reversed) lines to the final render loop.
    meas_text = text
    if is_arabic:
        if not _ARABIC_OK or not os.path.isfile(ARABIC_FONT_PATH):
            raise ValueError("Arabic font and shaping support are required to render source text")
        font_path = ARABIC_FONT_PATH
        # Apply transformation for correct measurement only
        meas_text = reshape_arabic(text)
    
    curr_size = start_size
    curr_tracking = base_tracking # extra per-zone boost
    curr_ls = 0 # line spacing adjustment
    
    # Long Quote detection (v9.0)
    is_long = len(text) > 100
    if is_long:
        print(f"📡 [QURAN_CARD] long verse layout adjusted (len={len(text)})")
        curr_size = int(start_size * 0.85)

    if is_arabic:
        # Enforce zero tracking for Arabic - it breaks ligatures
        base_tracking = 0
        curr_tracking = 0

    iterations = 0
    max_iterations = 25
    
    while iterations < max_iterations:
        iterations += 1
        try:
            fnt = ImageFont.truetype(font_path, curr_size, layout_engine=ImageFont.Layout.RAQM)
        except OSError:
            if is_arabic:
                raise ValueError("The Arabic source font could not be loaded") from None
            fnt = ImageFont.load_default()
            
        # 1. Wrap
        total_tracking = base_ls + curr_tracking
        # We wrap on the ORIGINAL text (not the reshaped one) so we get logical lines.
        # But wait - wrapping on non-reshaped Arabic can miscalculate lengths slightly.
        # We wrap on the meas_text but we must be careful.
        # BEST: Wrap on logical text, but measure using the font that will draw reshaped.
        lines = balanced_text_wrap(text, fnt, max_w, draw_tmp, letter_spacing=total_tracking)
        
        # 2. Measure
        block_h = 0
        line_metrics = []
        for line in lines:
            # Measure the RESHAPED version of the line for accuracy
            meas_line = reshape_arabic(line) if is_arabic else line
            bbox = draw_tmp.textbbox((0, 0), meas_line, font=fnt)
            lh = bbox[3] - bbox[1]
            lw = (bbox[2] - bbox[0]) + len(meas_line) * total_tracking
            line_metrics.append({"h": lh, "w": lw})
            
        # Base line spacing (1.3x font size or custom)
        zd_ls = int(curr_size * (0.45 + curr_ls))
        block_h = sum(m["h"] for m in line_metrics) + (len(lines)-1) * zd_ls
        
        # 3. Check Fit
        if block_h <= max_h and all(m["w"] <= max_w for m in line_metrics):
            return lines, fnt, block_h, zd_ls, total_tracking
            
        # 4. Decimate (Priority Order)
        if curr_tracking > 0:
            curr_tracking -= 1
        elif curr_size > min_size:
            curr_size -= 2
        elif curr_ls > -0.15:
            curr_ls -= 0.05
        else:
            # Absolute limit reached
            break
            
    # Final fallback if we never perfectly fit
    raise ValueError("Text does not fit the card without clipping")


def _extract_palette(p: str):
    """
    Returns (bg_start, bg_end, is_light, accent_rgb) — all plain ints.

    Priority:
      1. LIGHT materials/moods (parchment, white)   → light bg
      2. DARK MATERIAL keywords (obsidian, charcoal, marble, black) → dark bg
         These must check BEFORE generic color words like 'emerald' or 'celestial'
         so compound prompts like 'charcoal marble with emerald aura' get the
         correct dark grey base, not a green one.
      3. COLOR/ATMOSPHERE keywords (emerald, navy, celestial, etc)
      4. Default: premium near-black
    """
    # ── 1. Light materials ──────────────────────────────────────────────────
    if any(k in p for k in ["parchment", "papyrus", "vellum", "ivory", "cream"]):
        return [248, 238, 212], [230, 218, 190], True,  [130, 92, 38]
    if any(k in p for k in ["tan", "warm paper", "aged paper"]):
        return [242, 230, 208], [224, 212, 188], True,  [125, 90, 40]
    if any(k in p for k in ["white", "pearl"]):
        return [245, 244, 240], [228, 226, 220], True,  [120, 100, 58]

    # ── 2. Dark material keywords (checked FIRST before color words) ────────
    if "obsidian" in p or "onyx" in p:
        return [14, 10, 18],   [3, 2, 6],        False, [160, 125, 225]
    if "charcoal" in p:
        return [38, 36, 42],   [15, 13, 18],     False, [205, 198, 218]
    if any(k in p for k in ["marble", "stone", "granite"]):
        return [44, 41, 50],   [17, 15, 21],     False, [212, 205, 225]
    if any(k in p for k in ["slate", "gunmetal"]):
        return [36, 40, 45],   [12, 14, 18],     False, [178, 185, 202]
    if any(k in p for k in ["jet black", "pitch black", "pure black"]):
        return [22, 20, 25],   [2, 2, 4],         False, [200, 195, 215]
    if "velvet" in p:
        return [28, 10, 52],   [8, 3, 22],       False, [190, 145, 255]

    # ── 3. Color / atmosphere keywords ─────────────────────────────────────
    if any(k in p for k in ["emerald", "jade"]):
        return [0, 72, 38],    [0, 24, 14],      False, [115, 222, 148]
    if any(k in p for k in ["forest", "deep green", "dark green"]):
        return [6, 44, 22],    [0, 15, 8],       False, [128, 205, 138]
    if "green" in p:
        return [0, 56, 28],    [0, 18, 10],      False, [148, 212, 155]
    if any(k in p for k in ["navy", "deep blue", "midnight blue", "midnight"]):
        return [10, 18, 66],   [3, 5, 27],       False, [138, 172, 250]
    if any(k in p for k in ["sapphire", "cobalt", "royal blue"]):
        return [12, 24, 106],  [4, 8, 44],       False, [158, 188, 255]
    if any(k in p for k in ["moonlit", "moonlight", "lunar", "moon"]):
        return [16, 20, 60],   [4, 6, 23],       False, [178, 202, 255]
    if any(k in p for k in ["night sky", "night", "nighttime"]):
        return [8, 12, 38],    [2, 4, 14],       False, [158, 182, 245]
    if any(k in p for k in ["celestial", "cosmic", "galaxy"]):
        return [14, 22, 75],   [3, 5, 24],       False, [198, 212, 255]
    if any(k in p for k in ["black", "dark"]):
        return [22, 20, 25],   [2, 2, 4],         False, [200, 195, 215]
    if any(k in p for k in ["burgundy", "crimson", "wine", "maroon"]):
        return [66, 10, 15],   [28, 3, 5],       False, [222, 138, 138]
    if any(k in p for k in ["violet", "purple", "plum", "amethyst"]):
        return [44, 12, 90],   [17, 3, 36],      False, [202, 155, 255]
    if any(k in p for k in ["desert", "amber", "warm gold"]):
        return [56, 32, 5],    [22, 13, 2],      False, [222, 182, 88]

    # ── 4. Default ──────────────────────────────────────────────────────────
    return [22, 20, 26], [5, 4, 8], False, [200, 195, 215]



def _extract_glow(p: str, accent: list, is_light: bool, intensity: float) -> list:
    if is_light:
        return [0, 0, 0, 0]
    if any(k in p for k in ["no glow", "matte", "flat"]):
        return [0, 0, 0, 0]
    strong = min(255, int(118 * intensity))
    base   = min(255, int(75 * intensity))
    if any(k in p for k in ["golden glow", "warm glow", "gold glow",
                              "celestial glow", "divine light", "celestial light",
                              "amber glow"]):
        return [255, 215, 90, strong]
    if any(k in p for k in ["emerald aura", "green aura", "emerald glow"]):
        return [72, 220, 128, strong]
    if any(k in p for k in ["silver glow", "cool glow", "moonlit glow",
                              "silver light"]):
        return [198, 214, 255, strong]
    if any(k in p for k in ["glow", "aura", "halo", "radiant", "luminous",
                              "shining", "light"]):
        return [accent[0], accent[1], accent[2], strong]
    if any(k in p for k in ["moon", "moonlit", "lunar", "silver", "cool"]):
        return [192, 212, 255, base]
    if any(k in p for k in ["emerald", "forest", "green"]):
        return [88, 218, 135, base]
    if any(k in p for k in ["gold", "golden"]):
        return [255, 208, 75, base]
    if any(k in p for k in ["purple", "violet", "amethyst"]):
        return [185, 130, 255, base]
    if any(k in p for k in ["blue", "sapphire", "navy"]):
        return [145, 178, 255, base]
    return [255, 245, 218, min(255, int(58 * intensity))]


def _extract_pattern(p: str, material: str, atmosphere: str,
                     intensity: float, accent: list) -> tuple:
    alpha = min(255, int(32 * intensity))
    if any(k in p for k in ["islamic pattern", "arabesque", "geometric pattern",
                              "islamic geometry", "geometric border", "islamic border"]):
        col = [int(accent[0] * 0.85), int(accent[1] * 0.85),
               int(accent[2] * 0.85), alpha]
        return "islamic", col
    if material in ("parchment", "manuscript", "paper") or "aged" in p:
        return "paper", [255, 255, 255, 0]
    if any(k in p for k in ["star", "starry", "stars", "constellation",
                              "star field"]):
        return "starry", [255, 255, 255, 0]
    if atmosphere in ("moonlit", "celestial") and "star" in p:
        return "starry", [255, 255, 255, 0]
    if atmosphere == "sacred":
        col = [int(accent[0] * 0.58), int(accent[1] * 0.58),
               int(accent[2] * 0.58), min(255, int(26 * intensity))]
        return "islamic", col
    return "none", [255, 255, 255, 0]


def interpret_visual_prompt(prompt: str) -> dict:
    """
    Multi-dimensional visual prompt interpreter v2.1.
    All RGB values are guaranteed to be plain Python ints.
    """
    p = prompt.lower().strip()
    print(f"\n🔍 [Interpreter] '{prompt[:80]}'")

    intensity  = _extract_intensity(p)
    material   = _extract_material(p)
    atmosphere = _extract_atmosphere(p)
    border     = _extract_border(p)
    bg_start, bg_end, is_light, accent = _extract_palette(p)
    glow_rgba  = _extract_glow(p, accent, is_light, intensity)
    pattern_type, pattern_rgba = _extract_pattern(p, material, atmosphere,
                                                   intensity, accent)

    gradient_type = "none" if is_light else "radial"

    if is_light:                                     vignette = 0.08
    elif atmosphere in ("dramatic", "cinematic"):    vignette = min(0.95, round(0.85 * intensity, 3))
    elif atmosphere in ("celestial", "sacred"):      vignette = min(0.82, round(0.66 * intensity, 3))
    elif material == "velvet":                        vignette = min(0.92, round(0.88 * intensity, 3))
    else:                                            vignette = min(0.88, round(0.72 * intensity, 3))

    config = {
        "bg_start_rgb":       [int(v) for v in bg_start],
        "bg_end_rgb":         [int(v) for v in bg_end],
        "glow_color_rgba":    [int(v) for v in glow_rgba],
        "pattern_color_rgba": [int(v) for v in pattern_rgba],
        "accent_rgb":         [int(v) for v in accent],
        "gradient_type":      gradient_type,
        "pattern_type":       pattern_type,
        "vignette":           float(vignette),
        "border_style":       border,
        "material":           material,
        "atmosphere":         atmosphere,
        "intensity":          float(intensity),
        "is_light_bg":        is_light,
    }

    print(f"   mat={material}  atm={atmosphere}  bdr={border}  "
          f"int={intensity:.2f}  light={is_light}")
    return config


# ─────────────────────────────────────────────────────────────────────────────
# AI STYLE ANALYZER
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_config(cfg: dict) -> dict:
    """Cast all RGB array values to int — guard against OpenAI float returns."""
    out = dict(cfg)
    for key in ("bg_start_rgb", "bg_end_rgb", "glow_color_rgba",
                "pattern_color_rgba", "accent_rgb"):
        if key in out and isinstance(out[key], (list, tuple)):
            out[key] = [int(round(float(v))) for v in out[key]]
    if "vignette" in out:
        out["vignette"] = float(out["vignette"])
    return out


def analyze_style_prompt(visual_prompt: str, base_style: str) -> Optional[dict]:
    """
    Returns a full design config for a visual prompt.
    Keyword interpreter is SOLE authority on bg_start_rgb, bg_end_rgb, and all
    structural fields (material, atmosphere, border_style). This prevents
    OpenAI from confusing modifier words (e.g. 'emerald AURA') with base
    material/palette keywords and assigning the wrong background color.

    OpenAI may only optionally refine glow_color_rgba.
    """
    if not visual_prompt or not visual_prompt.strip():
        return None

    # Primary: always use keyword config for bg + structure
    config = interpret_visual_prompt(visual_prompt)

    # Optional: AI may only update glow color (not bg)
    if not settings.openai_api_key:
        return config

    try:
        ai = generate_text(
            f"Visual: {visual_prompt}", utility=True, schema=Glow, timeout=6,
            instructions="Choose only a glow_color_rgba: four integers 0-255, alpha 60-120. Keep the glow understated and natural.",
        )
        # Only update glow — NEVER touch bg_start_rgb or bg_end_rgb
        if "glow_color_rgba" in ai:
            config["glow_color_rgba"] = ai["glow_color_rgba"]
            print(f"🤖 [StyleAnalyzer] AI glow: {ai['glow_color_rgba']}")
    except TextGenerationError:
        print("[StyleAnalyzer] AI glow unavailable; retaining keyword colors")

    return config


import urllib.request
import io as _io
import hashlib


# ── Fast-path keywords: single clear themes PIL handles well without DALL-E ──
# Prompts that consist ONLY of these common themes skip DALL-E entirely.
_PIL_FAST_PATH_WORDS = {
    "parchment", "manuscript", "marble", "charcoal", "obsidian", "onyx",
    "velvet", "emerald", "forest", "moonlit", "celestial", "starry",
    "night", "navy", "kaaba", "sacred", "fajr",
}

# ── Material/atmosphere → richer DALL-E background language ─────────────────
_BG_EXPANSIONS = {
    "parchment":   "aged parchment surface, warm antique ivory tones, subtle grain and time-worn texture",
    "manuscript":  "old manuscript environment, aged vellum surface, warm amber tones, scholarly antique feel",
    "marble":      "realistic stone marble texture with natural sinuous veins, polished depth, cool grey tones",
    "charcoal":    "deep charcoal grey surface, fine grain, subtle tonal variation, modern dark aesthetic",
    "obsidian":    "deep obsidian black stone, light absorption, faint iridescent edge glow, volcanic depth",
    "onyx":        "polished onyx black stone, high contrast depth, subtle specular highlights",
    "velvet":      "rich velvet-like matte surface, deep color saturation, smooth soft-focus depth",
    "emerald":     "deep emerald green atmospheric scene, lush organic tones, gem-like depth",
    "forest":      "deep forest atmosphere, mist between dark trees, organic green ambiance",
    "moonlit":     "moonlit scene, silver cool light from above, serene nocturnal atmosphere",
    "celestial":   "celestial atmosphere, radiant cosmic light, deep spiritual heavenly ambiance",
    "starry":      "star field in deep space, scattered stars of varying brightness, velvet black void",
    "night":       "quiet night scene, deep dark tones, subtle ambient light, peaceful nocturnal mood",
    "sacred":      "sacred spiritual atmosphere, warm ambient glow, peaceful and reverent mood",
    "navy":        "deep navy blue atmosphere, dignified and calm, rich oceanic depth",
    "cosmic":      "cosmic nebula atmospheric scene, deep space, radiant distant light sources",
}


def _is_fast_path(prompt: str) -> bool:
    """
    Returns True if the prompt is a simple common-theme description that our
    PIL pipeline handles well without needing DALL-E (saves time and cost).
    A prompt qualifies when ALL identified keywords are standard fast-path
    words AND the description is not unusually detailed (>= 60 chars).
    """
    p     = prompt.lower().strip()
    words = set(p.replace(",", " ").replace(".", " ").split())
    fast  = _PIL_FAST_PATH_WORDS
    # Count matched fast-path words and non-stop words total
    matched  = sum(1 for kw in fast if kw in p)
    # Use DALL-E when prompt has unique/compound descriptions
    if matched == 0:
        return False
    # Short simple prompts (only 1-2 concepts) → PIL
    if len(p) <= 52 and matched >= 1:
        return True
    return False


def _build_bg_prompt(visual_prompt: str) -> str:
    """
    Converts a user's visual description into a background-plate DALL-E prompt.

    KEY RULE: the words 'Islamic', 'Arabic', 'Qur\'an', 'mosque', and
    'quote card' must NEVER appear in the DALL-E prompt.  DALL-E's
    training strongly links those words to Arabic calligraphy and will
    render script regardless of later negative constraints.

    Instead we describe a 'pure abstract material texture plate for
    photo compositing' — neutral art-direction that keeps DALL-E
    focused on material, light, and atmosphere.

    The NO-CALLIGRAPHY directive is placed as the very first tokens
    so it receives maximum positional weight.
    """
    p = visual_prompt.lower()

    # Expand known material/atmosphere keywords into richer visual language
    expanded = visual_prompt
    for kw, expansion in _BG_EXPANSIONS.items():
        if kw in p:
            if expansion.split(",")[0] not in visual_prompt.lower():
                expanded = f"{expanded}, {expansion}"
            break

    # Composition: keep center clear so overlaid text is always readable
    composition = (
        "Composition rule: richly detailed texture, lighting, and ornament "
        "concentrated at edges and corners only. "
        "The central 50% of the image must be calm, smooth, and unoccupied "
        "for digital text to be placed on top."
    )

    # Anti-script directive — placed FIRST for maximum attention weight
    # Uses ALL CAPS and multiple synonyms to reinforce through DALL-E's tokenizer
    no_script = (
        "NO CALLIGRAPHY. NO SCRIPT. NO LETTERS. NO TEXT OF ANY KIND. "
        "This image must contain zero writing, zero lettering, "
        "zero glyphs, zero characters, zero text in any language. "
        "No brush-stroke calligraphy, no decorative script, "
        "no pseudo-letters, no symbol-like shapes resembling writing. "
        "Only pure material texture, abstract light, and geometric ornament."
    )

    return (
        f"{no_script} "
        "Pure abstract material texture plate for digital photo compositing. "
        f"{expanded}. "
        f"{composition} "
        "Cinematic photorealistic quality, premium fine digital art, "
        "deep atmospheric lighting suited to the material, "
        "subtle abstract geometric shapes at corners and edges only, "
        "no representational imagery, no figures, no faces, no readable marks. "
        "Square format 1:1. 4K ultra-detail, tasteful and dignified."
    )

def _load_bg_cache(prompt_key: str, cache_dir: str) -> Optional[Image.Image]:
    """Load a previously saved background from the file cache."""
    h     = hashlib.md5(prompt_key.lower().strip().encode()).hexdigest()[:14]
    path  = os.path.join(cache_dir, f"bgcache_{h}.jpg")
    if os.path.exists(path):
        try:
            img = Image.open(path).convert("RGB")
            print(f"⚡ [BG Cache] HIT {h} — skipping DALL-E")
            return img
        except Exception:
            pass
    return None


def _save_bg_cache(img: Image.Image, prompt_key: str, cache_dir: str) -> None:
    """Persist a generated background to the file cache."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        h    = hashlib.md5(prompt_key.lower().strip().encode()).hexdigest()[:14]
        path = os.path.join(cache_dir, f"bgcache_{h}.jpg")
        img.save(path, quality=92)
        print(f"💾 [BG Cache] Saved {h}")
    except Exception as e:
        print(f"⚠️  [BG Cache] Could not save ({e})")


def _detect_center_brightness(image_rgb, size) -> float:
    """
    Returns average pixel brightness (0-255) of the center 50% of the image.
    Used to choose white vs dark text when overlaying on a DALL-E background.
    """
    W, H     = size
    px, py   = W // 4, H // 4
    center   = image_rgb.crop((px, py, W - px, H - py))
    gray     = center.convert("L")
    pixels   = list(gray.getdata())
    return sum(pixels) / len(pixels) if pixels else 128.0


def generate_background(
    visual_prompt: str,
    target_size: tuple = (1080, 1080),
    cache_dir: Optional[str] = None,
    engine: str = "dalle",
    vs_spec=None,
    render_metadata: dict = None,
    provider_size: str = "1024x1024",
) -> Optional[Image.Image]:
    """Shared Sabeel Vision background path for Studio and automations."""
    if engine not in {"dalle", "openai", "gemini"}:
        raise ValueError("The selected visual engine is unavailable. Use Sabeel Vision.")
    cache_key = configured_image_cache_key() + "_" + provider_size
    if cache_dir and vs_spec and vs_load_cache:
        cached = vs_load_cache(vs_spec, cache_dir, engine=cache_key)
        if cached is not None:
            if render_metadata is not None:
                render_metadata.update(image_provider="openai", image_model=settings.openai_image_model,
                                       image_quality=settings.openai_image_quality, image_cached=True)
            return ImageOps.fit(cached, target_size, method=Image.Resampling.LANCZOS)

    # Scene prompts are already composed; do not reinterpret them as abstract textures.
    prompt = vs_compose(vs_spec, raw_prompt=visual_prompt) if vs_spec and vs_compose else visual_prompt
    prompt += " Background only. No text, letters, calligraphy, symbols or logos. Leave clear space for separately rendered typography."
    result = generate_configured_image(prompt, engine=engine, size=provider_size)
    image = ImageOps.fit(result.image, target_size, method=Image.Resampling.LANCZOS)
    if render_metadata is not None:
        render_metadata.update(image_provider=result.provider, image_model=result.model,
                               image_quality=settings.openai_image_quality, image_cached=False)
    # A fallback result must not masquerade as the selected primary in its cache.
    if cache_dir and vs_spec and vs_save_cache and result.model == settings.openai_image_model:
        vs_save_cache(image, vs_spec, cache_dir, engine=cache_key)
    return image


def generate_background_gemini(visual_prompt: str, target_size: tuple = (1080, 1080),
                               cache_dir: Optional[str] = None, vs_spec=None) -> Optional[Image.Image]:
    """Compatibility alias: production generation now uses OpenAI only."""
    return generate_background(visual_prompt, target_size, cache_dir, engine="openai", vs_spec=vs_spec)


def generate_dalle_background(visual_prompt: str, target_size: tuple = (1080, 1080),
                              cache_dir: Optional[str] = None,
                              dalle_prompt_override: Optional[str] = None) -> Optional[Image.Image]:
    """Legacy entry point using the current shared image API."""
    if _is_fast_path(visual_prompt):
        return None
    prompt = dalle_prompt_override or _build_bg_prompt(visual_prompt)
    result = generate_configured_image(prompt)
    return result.image.resize(target_size, Image.Resampling.LANCZOS)


# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVES — BACKGROUNDS
# ─────────────────────────────────────────────────────────────────────────────

def draw_radial_gradient(draw, size, color_start, color_end):
    """Smooth radial gradient. Extra steps + post-blur to prevent banding."""
    W, H  = size
    cx, cy = W // 2, H // 2
    md    = int(math.sqrt(cx * cx + cy * cy)) + 1
    steps = 80   # more steps = smoother color transition
    for i in range(steps, 0, -1):
        t  = i / steps
        r2 = int(md * t)
        u  = 1 - t
        r  = int(round(color_start[0] * t + color_end[0] * u))
        g  = int(round(color_start[1] * t + color_end[1] * u))
        b  = int(round(color_start[2] * t + color_end[2] * u))
        draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(r, g, b))


def draw_starry_noise(draw, size, density=0.0006, seed=None):
    if seed is not None:
        random.seed(seed)
    W, H  = size
    count = int(W * H * density)
    for _ in range(count):
        x = random.randint(0, W - 1)
        y = random.randint(0, H - 1)
        b = random.randint(170, 255)
        draw.point((x, y), fill=(b, b, b))
    if seed is not None:
        random.seed()


def draw_paper_texture(draw, size, base_color=(238, 228, 205)):
    """Warm paper grain on an RGB draw context."""
    W, H = size
    r0, g0, b0 = base_color
    for _ in range(10000):
        x = random.randint(0, W - 1)
        y = random.randint(0, H - 1)
        d = random.randint(-14, 14)
        v = max(0, min(255, r0 + d))
        draw.point((x, y), fill=(v, max(0, v - 8), max(0, v - 20)))


def draw_gold_border(draw, size, border_width=30):
    W, H     = size
    gold     = (200, 162, 42)
    gold_dim = (148, 118, 30)
    m        = border_width
    draw.rectangle([m, m, W - m, H - m], outline=gold, width=3)
    draw.rectangle([m + 12, m + 12, W - m - 12, H - m - 12],
                   outline=gold_dim, width=1)
    d = 5
    for px, py in [(m + 3, m + 3), (W - m - 3, m + 3),
                   (m + 3, H - m - 3), (W - m - 3, H - m - 3)]:
        draw.ellipse([px - d, py - d, px + d, py + d], fill=gold)


def draw_corner_filigree(draw, size, color, length=80, thickness=1):
    W, H = size
    m    = 30
    c    = tuple(int(v) for v in color[:3])
    for cx, cy, hd, vd in [(m, m, 1, 1), (W-m, m, -1, 1),
                            (m, H-m, 1, -1), (W-m, H-m, -1, -1)]:
        draw.line([(cx, cy), (cx + hd * length, cy)], fill=c, width=thickness)
        draw.line([(cx, cy), (cx, cy + vd * length)], fill=c, width=thickness)
        n = length // 4
        draw.line([(cx + hd * n, cy), (cx + hd * n, cy + vd * n)],
                  fill=c, width=thickness)
        draw.line([(cx, cy + vd * n), (cx + hd * n, cy + vd * n)],
                  fill=c, width=thickness)
        d = 5
        draw.polygon([(cx, cy-d), (cx+d, cy), (cx, cy+d), (cx-d, cy)], fill=c)


def draw_manuscript_frame(draw, size, color, margin=30):
    W, H = size
    c    = tuple(int(v) for v in color[:3])
    m, g = margin, 10
    draw.rectangle([m, m, W - m, H - m], outline=c, width=1)
    draw.rectangle([m+g, m+g, W-m-g, H-m-g], outline=c, width=1)
    sq = 4
    for px, py in [(m, m), (W-m, m), (m, H-m), (W-m, H-m)]:
        draw.rectangle([px-sq, py-sq, px+sq, py+sq], fill=c)


def draw_islamic_pattern(draw, size, color):
    W, H = size
    if len(color) == 4:
        r, g, b, a = (int(v) for v in color)
        blend = a / 255.0
        col   = (int(r * blend), int(g * blend), int(b * blend))
    else:
        col = tuple(int(v) for v in color[:3])
    positions = [(W//2, H//2), (180, 180), (W-180, 180),
                 (180, H-180), (W-180, H-180)]
    sizes     = [260, 110, 110, 110, 110]
    for (px, py), s in zip(positions, sizes):
        draw.polygon([(px, py-s), (px+s, py), (px, py+s), (px-s, py)],
                     outline=col, width=2)
        sq = int(s * 0.68)
        draw.rectangle([px-sq, py-sq, px+sq, py+sq], outline=col, width=1)
        dot = int(s * 0.14)
        draw.ellipse([px-dot, py-dot, px+dot, py+dot], outline=col, width=1)


# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL RENDERING
# ─────────────────────────────────────────────────────────────────────────────

def apply_marble_depth(image_rgb, size, bg_start, intensity=0.72) -> Image.Image:
    """
    Realistic marble: primary + secondary sinusoidal veins + polish highlight.
    """
    W, H   = size
    layer  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld     = ImageDraw.Draw(layer)

    # Vein color: significantly lighter than background so veins are visible
    vc  = (min(255, bg_start[0] + 75), min(255, bg_start[1] + 70), min(255, bg_start[2] + 80))
    vc2 = (min(255, bg_start[0] + 48), min(255, bg_start[1] + 45), min(255, bg_start[2] + 52))

    # Minimum alpha 85 — veins must be clearly visible regardless of intensity
    primary_a   = max(85,  min(255, int(90 * intensity)))
    secondary_a = max(45,  min(255, int(50 * intensity)))

    random.seed(7331)
    # Primary veins
    for _ in range(max(4, int(8 * intensity))):
        sx    = random.randint(-120, W + 120)
        sy    = random.randint(-60,  H + 60)
        angle = random.uniform(8, 70) * math.pi / 180
        lng   = random.randint(350, 950)
        amp   = random.uniform(10, 32)
        freq  = random.uniform(0.006, 0.020)
        prev  = None
        for j in range(lng):
            x = int(sx + j * math.cos(angle) + amp * math.sin(freq * j * 5.0))
            y = int(sy + j * math.sin(angle) + amp * math.cos(freq * j * 3.2))
            if 0 <= x < W and 0 <= y < H:
                ld.point((x, y), fill=vc + (primary_a,))
                if prev:
                    ld.line([prev, (x, y)], fill=vc + (primary_a - 15,), width=1)
                prev = (x, y)
            else:
                prev = None

    # Secondary veins (lighter, shorter)
    for _ in range(max(2, int(5 * intensity))):
        sx    = random.randint(0, W)
        sy    = random.randint(0, H)
        angle = random.uniform(15, 80) * math.pi / 180
        lng   = random.randint(100, 320)
        amp   = random.uniform(4, 15)
        freq  = random.uniform(0.015, 0.045)
        for j in range(lng):
            x = int(sx + j * math.cos(angle) + amp * math.sin(freq * j * 4.0))
            y = int(sy + j * math.sin(angle) + amp * math.cos(freq * j * 3.5))
            if 0 <= x < W and 0 <= y < H:
                ld.point((x, y), fill=vc2 + (secondary_a,))
    random.seed()

    layer = layer.filter(ImageFilter.GaussianBlur(0.9))
    result = Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")

    # Polish highlight: subtle white diagonal streak
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hy = int(H * 0.26)
    hw = int(W * 0.55)
    for dy in range(4):
        a = max(0, int(24 * intensity) - dy * 7)
        hd.line([(W//2 - hw//2, hy + dy), (W//2 + hw//2, hy + dy)],
                fill=(255, 255, 255, a), width=1)
    hl = hl.filter(ImageFilter.GaussianBlur(9))
    return Image.alpha_composite(result.convert("RGBA"), hl).convert("RGB")


def apply_parchment_depth(image_rgb, size, intensity=0.72) -> Image.Image:
    """
    Parchment aging: uneven tone patches + corner aging + manuscript lines.
    """
    W, H   = size
    layer  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld     = ImageDraw.Draw(layer)

    # Uneven tone patches (warm aging spots)
    random.seed(4242)
    for _ in range(10):
        px = random.randint(-80, W + 80)
        py = random.randint(-80, H + 80)
        pr = random.randint(70, 200)
        d  = random.randint(-10, 20)
        a  = random.randint(8, 24)
        col = (max(0, 160 + d), max(0, 125 + d), max(0, 75 + d), a)
        ld.ellipse([px - pr, py - pr, px + pr, py + pr], fill=col)

    # Corner aging: darker warm tint at corners
    ca = min(255, int(35 * intensity))
    corner_specs = [
        (-60, -60, 340, 340),
        (W - 340, -60, W + 60, 340),
        (-60, H - 340, 340, H + 60),
        (W - 340, H - 340, W + 60, H + 60),
    ]
    for x0, y0, x1, y1 in corner_specs:
        ld.ellipse([x0, y0, x1, y1], fill=(90, 60, 28, ca))
    random.seed()

    layer  = layer.filter(ImageFilter.GaussianBlur(42))
    result = Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")

    # Manuscript horizontal lines (very faint ruled lines)
    draw = ImageDraw.Draw(result)
    lc   = (165, 130, 82)
    for y in range(90, H - 90, 38):
        draw.line([(55, y), (W - 55, y)], fill=lc, width=1)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# LIGHTING SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def apply_light_source(image_rgb, size, position, color,
                       radius, intensity=0.72) -> Image.Image:
    """
    Focused emotional light source — guides the eye, creates depth.
    """
    W, H   = size
    cx, cy = int(position[0]), int(position[1])
    layer  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld     = ImageDraw.Draw(layer)
    c      = tuple(int(v) for v in color[:3])

    for r_frac, a_frac in [(0.18, 70), (0.40, 42), (0.68, 20), (1.00, 9)]:
        r = int(radius * r_frac)
        a = min(255, int(a_frac * intensity))
        ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c + (a,))

    layer = layer.filter(ImageFilter.GaussianBlur(int(radius * 0.32)))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


# ─────────────────────────────────────────────────────────────────────────────
# ATMOSPHERE EFFECTS
# ─────────────────────────────────────────────────────────────────────────────

def apply_celestial_atmosphere(image_rgb, size, glow_color, intensity=0.72):
    W, H   = size
    cx, cy = W // 2, H // 2
    gc     = tuple(int(v) for v in glow_color[:3])
    layer  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld     = ImageDraw.Draw(layer)
    for r_frac, base_a in [(0.12, 82), (0.28, 52), (0.48, 26), (0.66, 12)]:
        r = int(W * r_frac)
        a = min(255, int(base_a * intensity))
        ld.ellipse([cx-r, cy-r, cx+r, cy+r], fill=gc + (a,))
    layer = layer.filter(ImageFilter.GaussianBlur(55))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


def apply_moonlit_atmosphere(image_rgb, size, intensity=0.72):
    W, H   = size
    cx     = W // 2
    layer  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld     = ImageDraw.Draw(layer)
    mc     = (185, 205, 255)
    for x0, y0, x1, y1, a_base in [
        (cx-320, -95, cx+320, 320, 50),
        (cx-155, -48, cx+155, 200, 34),
        (cx-70,  -22, cx+70,   92, 20),
    ]:
        a = min(255, int(a_base * intensity))
        ld.ellipse([x0, y0, x1, y1], fill=mc + (a,))
    # Stars (top half, deterministic)
    random.seed(42)
    for _ in range(int(160 * intensity)):
        sx = random.randint(0, W)
        sy = random.randint(0, H // 2)
        b  = random.randint(165, 255)
        a  = random.randint(90, 195)
        ld.point((sx, sy), fill=(b, b, min(255, b + 28), a))
    random.seed()
    layer = layer.filter(ImageFilter.GaussianBlur(6))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


def apply_spiritual_atmosphere(image_rgb, size, accent, intensity=0.72):
    W, H   = size
    cx, cy = W // 2, H // 2
    ac     = tuple(int(v) for v in accent[:3])
    layer  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld     = ImageDraw.Draw(layer)
    for r_frac, base_a in [(0.22, 58), (0.42, 28)]:
        r = int(W * r_frac)
        a = min(255, int(base_a * intensity))
        ld.ellipse([cx-r, cy-r, cx+r, cy+r], fill=ac + (a,))
    layer = layer.filter(ImageFilter.GaussianBlur(72))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


def apply_vignette(image, intensity=0.65):
    W, H   = image.size
    cx, cy = W // 2, H // 2
    md     = int(math.sqrt(cx*cx + cy*cy)) + 1
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)
    steps   = 38
    for i in range(steps):
        t  = i / steps
        r  = int(md * (1 - t))
        a  = int((t ** 2.3) * 255 * intensity)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(0, 0, 0, a))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def apply_text_halo(text_layer, radius=12, halo_color=(255, 255, 255, 255)):
    """
    Builds a soft cinematic halo from the rendered text glyphs' alpha channel.
    The halo follows the actual letter shapes, providing organic readability protection.
    """
    if radius <= 0:
        return None
        
    # 1. Extract the alpha mask from the text layer
    alpha = text_layer.split()[-1]
    
    # 2. Blur the alpha mask to create the 'glow' shape
    halo_alpha = alpha.filter(ImageFilter.GaussianBlur(radius))
    
    # 3. Create a solid color layer and apply the blurred alpha
    halo = Image.new("RGBA", text_layer.size, halo_color)
    halo.putalpha(halo_alpha)
    
    return halo


def draw_glow(
    draw: ImageDraw.ImageDraw,
    pos: tuple,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple,
    radius: float,
    anchor: str = "mt",
    tracking: int = 0,
    is_arabic: bool = False
):
    """Draws a soft glow effect behind text by rendering it with slight offsets."""
    # Force single-unit rendering for Arabic to prevent backwards/broken text
    active_tracking = 0 if (is_arabic or is_arabic_text(text)) else tracking
    
    # Simple multi-pass glow
    for dx, dy in [(-1,-1), (1,-1), (-1,1), (1,1), (0,-1.5), (0,1.5), (-1.5,0), (1.5,0)]:
        off_pos = (pos[0] + dx * radius * 0.4, pos[1] + dy * radius * 0.4)
        draw_text_advanced(draw, off_pos, text, font, color, anchor=anchor, letter_spacing=active_tracking, is_arabic=is_arabic)

def draw_text_advanced(
    draw: ImageDraw.ImageDraw,
    pos: tuple,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    anchor: str = "mt",
    letter_spacing: int = 0,
    shadow_fill: tuple = None,
    shadow_offset: tuple = (0, 0),
    stroke_width: int = 0,
    stroke_fill: tuple = None,
    is_arabic: bool = False
):
    """
    Advanced text drawing with support for tracking (letter_spacing), 
    shadows, and secondary effects.
    """
    # RTL / Arabic Protection: FORCE Fast Path
    # Letter spacing DRAWN character-by-character breaks Arabic ligatures 
    # and reverses the reading direction even after BIDI reshaping.
    if letter_spacing == 0 or is_arabic or is_arabic_text(text):
        # Standard fast path
        if shadow_fill and shadow_offset != (0, 0):
            draw.text((pos[0] + shadow_offset[0], pos[1] + shadow_offset[1]), text, font=font, fill=shadow_fill, anchor=anchor)
        draw.text(pos, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)
        return

    # Tracking path: Draw character by character
    chars = list(text)
    char_widths = [draw.textbbox((0, 0), c, font=font)[2] - draw.textbbox((0, 0), c, font=font)[0] for c in chars]
    total_w = sum(char_widths) + (len(chars) - 1) * letter_spacing
    
    # Adjust starting X based on anchor
    x, y = pos
    if anchor.startswith("m"): # middle
        x -= total_w // 2
    elif anchor.startswith("r"): # right
        x -= total_w
    
    curr_x = x
    for i, char in enumerate(chars):
        if shadow_fill and shadow_offset != (0, 0):
            draw.text((curr_x + shadow_offset[0], y + shadow_offset[1]), char, font=font, fill=shadow_fill)
        draw.text((curr_x, y), char, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
        curr_x += char_widths[i] + letter_spacing


def apply_cinematic_layers(image, glow_color=None):
    W, H   = image.size
    img    = image.convert("RGBA")

    # Film grain
    grain = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd    = ImageDraw.Draw(grain)
    for _ in range(4200):
        x = random.randint(0, W - 1)
        y = random.randint(0, H - 1)
        b = random.randint(200, 255)
        gd.point((x, y), fill=(b, b, b, 8))

    # Center warmth
    cx_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cx_layer)
    cx, cy = W // 2, H // 2
    gc = (tuple(int(v) for v in glow_color[:3]) + (10,)
          if glow_color else (255, 245, 210, 10))
    cd.ellipse([cx - 470, cy - 470, cx + 470, cy + 470], fill=gc)
    cx_layer = cx_layer.filter(ImageFilter.GaussianBlur(195))

    # Corner bloom
    bloom = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bloom)
    bd.ellipse([-290, -290, 480, 480],   fill=(255, 218, 158, 12))
    bd.ellipse([W-480, H-480, W+290, H+290], fill=(148, 205, 255, 10))
    bloom = bloom.filter(ImageFilter.GaussianBlur(130))

    img = Image.alpha_composite(img, cx_layer)
    img = Image.alpha_composite(img, grain)
    img = Image.alpha_composite(img, bloom)
    return img.convert("RGB")


# ─────────────────────────────────────────────────────────────────────────────
# TEXT ORNAMENTS
# ─────────────────────────────────────────────────────────────────────────────

def draw_top_ornament(draw, cx, y, color):
    """Tiny four-pointed star ornament — placed above reference text."""
    c = tuple(int(v) for v in color[:3])
    d = 4
    draw.polygon([(cx, y-d), (cx+d, y), (cx, y+d), (cx-d, y)], fill=c)
    t = 2
    for dx, dy in [(0, -(d+7)), (d+7, 0), (0, d+7), (-(d+7), 0)]:
        draw.ellipse([cx+dx-t, y+dy-t, cx+dx+t, y+dy+t], fill=c)


def draw_zone_separator(draw, cx, y, color):
    """Thin elegant divider with centered diamond — between reference and quote."""
    c    = tuple(int(v) for v in color[:3])
    half = 120
    draw.line([(cx - half, y), (cx - 14, y)], fill=c, width=1)
    draw.line([(cx + 14,   y), (cx + half, y)], fill=c, width=1)
    d = 4
    draw.polygon([(cx, y-d), (cx+d, y), (cx, y+d), (cx-d, y)], fill=c)


# ─────────────────────────────────────────────────────────────────────────────
# PRESET DEFINITIONS  (strongly differentiated identities)
# ─────────────────────────────────────────────────────────────────────────────

PRESET_CONFIGS = {
    "quran": {
        "base": (0, 8, 4),
        "bg_start": (0, 62, 32), "bg_end": (0, 8, 4),
        "pattern": "islamic",   "pattern_col": (190, 152, 42, 32),
        "vignette": 0.72,
        "border": "gold_block", "border_w": 32,
        "light_pos": "center",  "light_col": (200, 170, 60),  "light_r": 420,
        "glow": (170, 225, 175, 55),
        "atmosphere": None,
    },
    "fajr": {
        "base": (4, 6, 26),
        "bg_start": (14, 22, 72), "bg_end": (3, 5, 20),
        "pattern": "starry",     "pattern_density": 0.0006,
        "vignette": 0.55,
        "border": "none",
        "light_pos": (540, 680), "light_col": (255, 200, 100), "light_r": 320,
        "glow": (120, 160, 255, 65),
        "atmosphere": "fajr_horizon",
    },
    "scholar": {
        "base": (246, 240, 225),
        "bg_start": (246, 240, 225), "bg_end": (246, 240, 225),
        "pattern": "paper",
        "vignette": 0.07,
        "border": "none",
        "light_pos": (235, 235), "light_col": (255, 225, 150), "light_r": 380,
        "glow": None,
        "atmosphere": "parchment",
    },
    "madinah": {
        "base": (14, 8, 2),
        "bg_start": (55, 28, 5), "bg_end": (12, 6, 1),
        "pattern": "islamic",   "pattern_col": (210, 162, 65, 42),
        "vignette": 0.65,
        "border": "gold_block", "border_w": 28,
        "light_pos": "center",  "light_col": (255, 195, 75),  "light_r": 450,
        "glow": (225, 185, 82, 52),
        "atmosphere": None,
    },
    "kaaba": {
        "bg_start": (14, 12, 14), "bg_end": (0, 0, 0),
        "pattern": "islamic",    "pattern_col": (175, 148, 50, 14),
        "vignette": 0.32,
        "border": "corner_filigree",
        "light_pos": "center",  "light_col": (195, 162, 42),  "light_r": 260,
        "glow": (200, 162, 42, 35),
        "atmosphere": None,
    },
    "laylulqadr": {
        "base": (6, 0, 20),
        "bg_start": (40, 10, 90), "bg_end": (5, 0, 20),
        "pattern": "starry",    "pattern_density": 0.0009,
        "vignette": 0.50,
        "border": "none",
        "light_pos": "center",  "light_col": (165, 105, 255), "light_r": 400,
        "glow": (165, 105, 255, 72),
        "atmosphere": "celestial",
    },
    "midnight": {
        "base": (5, 8, 22),
        "bg_start": (12, 16, 44), "bg_end": (2, 3, 10),
        "pattern": "starry", "pattern_density": 0.0007,
        "vignette": 0.85,
        "border": "none",
        "light_pos": "center", "light_col": (138, 172, 250), "light_r": 450,
        "glow": (138, 172, 250, 45),
        "atmosphere": "celestial",
    },
    "desert": {
        "base": (26, 16, 5),
        "bg_start": (56, 32, 5), "bg_end": (16, 8, 2),
        "pattern": "paper",
        "vignette": 0.70,
        "border": "corner_filigree",
        "light_pos": "center", "light_col": (255, 195, 75), "light_r": 500,
        "glow": (255, 195, 75, 40),
        "atmosphere": "warm gold",
    },
    "minimal": {
        "base": (12, 12, 14),
        "bg_start": (22, 20, 25), "bg_end": (2, 2, 4),
        "pattern": "none",
        "vignette": 0.85,
        "border": "none",
        "light_pos": "center", "light_col": (200, 195, 215), "light_r": 350,
        "glow": (200, 195, 215, 15),
        "atmosphere": "none",
    },

    # ── PREMIUM SCENE-BASED PRESETS ─────────────────────────────────────────────
    # These presets are designed text-stage-first: the composition centers around
    # a deliberately calm, clear central region where the Arabic quote sits.

    "arch_stage": {
        # Grand symmetrical archway — warm amber corridor, open center stage
        "base": (8, 5, 2),
        "bg_start": (42, 22, 6), "bg_end": (8, 4, 1),
        "pattern": "islamic", "pattern_col": (185, 142, 45, 18),
        "vignette": 0.78,
        "border": "gold_block", "border_w": 20,
        "light_pos": "center", "light_col": (255, 200, 90), "light_r": 580,
        "glow": (220, 175, 65, 70),
        "atmosphere": "arch_veil",   # NEW: draws deep side curtains for text stage
        "scene": True,
    },
    "manuscript": {
        # Candlelit scholar's desk — warm parchment intimacy, quiet center
        "base": (28, 18, 8),
        "bg_start": (62, 38, 14), "bg_end": (22, 12, 4),
        "pattern": "paper",
        "vignette": 0.82,
        "border": "corner_filigree",
        "light_pos": (360, 300), "light_col": (255, 185, 80), "light_r": 340,
        "glow": (230, 175, 70, 60),
        "atmosphere": "parchment",
        "scene": True,
    },
    "luxury_panel": {
        # Deep navy/obsidian — ornate gold corners, dark editorial panel
        "base": (4, 5, 18),
        "bg_start": (10, 12, 42), "bg_end": (2, 2, 10),
        "pattern": "none",
        "vignette": 0.90,
        "border": "gold_block", "border_w": 36,
        "light_pos": "center", "light_col": (180, 162, 255), "light_r": 300,
        "glow": (195, 170, 255, 55),
        "atmosphere": "arch_veil",
        "scene": True,
    },
    "editorial": {
        # Minimal sacred editorial — pure, clean, restrained, premium magazine feel
        "base": (6, 6, 8),
        "bg_start": (15, 14, 18), "bg_end": (3, 3, 5),
        "pattern": "none",
        "vignette": 0.92,
        "border": "none",
        "light_pos": (220, 180), "light_col": (218, 200, 255), "light_r": 280,
        "glow": (218, 200, 255, 30),
        "atmosphere": "none",
        "scene": True,
    },
}

PRESET_TEXT = {
    "quran":       [(212, 175, 55),  (255, 255, 255),  (190, 215, 192)],
    "fajr":        [(138, 170, 248), (228, 238, 255),  (168, 195, 240)],
    "scholar":     [(88, 75, 55),    (28, 22, 16),     (95, 82, 62)],
    "madinah":     [(215, 168, 62),  (255, 242, 210),  (202, 178, 132)],
    "kaaba":       [(180, 148, 50),  (255, 255, 255),  (185, 185, 185)],
    "laylulqadr":  [(180, 145, 238), (238, 230, 255),  (195, 175, 242)],
    "midnight_oasis": [(138, 172, 250), (255, 255, 255),  (170, 190, 240)],
    "desert_glow": [(255, 195, 75),  (255, 255, 255),  (220, 200, 160)],
    "minimal":     [(160, 160, 160), (255, 255, 255),  (140, 140, 140)],
    # Scene presets — warm gold reference, cream quote, soft warm support
    "sacred_script": [(222, 178, 58),  (255, 248, 228),  (215, 195, 158)],
    "luxury_editorial": [(200, 175, 255), (245, 242, 255),  (190, 170, 235)],
}

CUSTOM_TEXT_DARK  = [(212, 175, 55), (255, 255, 255), (210, 210, 210)]
CUSTOM_TEXT_LIGHT = [(95, 78, 48),   (28, 22, 16),   (88, 75, 58)]


def _build_adaptive_palette(
    bg_image: "Image.Image",
    size: tuple,
    shadow_boost: int = 0,
) -> list:
    """
    Builds a 3-element text palette by independently sampling the average
    brightness of each text zone in the rendered background image.
    """
    W, H = size

    def zone_brightness(y1f: float, y2f: float,
                        x1f: float = 0.12, x2f: float = 0.88) -> float:
        x1, y1, x2, y2 = int(W*x1f), int(H*y1f), int(W*x2f), int(H*y2f)
        crop   = bg_image.crop((x1, y1, x2, y2))
        pixels = list(crop.convert("L").getdata())
        return sum(pixels) / len(pixels) if pixels else 128.0

    bA = zone_brightness(0.08, 0.25)   # reference row
    bB = zone_brightness(0.30, 0.70)   # main quote row
    bC = zone_brightness(0.72, 0.88)   # support row

    def pick_text(brightness: float, accent: bool = False):
        if brightness < 100:
            return (220, 178, 58) if accent else (255, 255, 255)
        elif brightness < 155:
            return (210, 168, 52) if accent else (248, 248, 245)
        elif brightness < 200:
            return (60, 40, 8)   if accent else (22, 18, 12)
        else:
            return (50, 30, 5)   if accent else (12, 10, 8)

    ref_c     = pick_text(bA, accent=True)
    quote_c   = pick_text(bB, accent=False)
    support_c = pick_text(bC, accent=False)

    return [ref_c, quote_c, support_c]


def render_minimal_quote_card(
    segments:      list,
    output_dir:    str,
    style:         str = "quran",
    visual_prompt: str = None,
    mode:          str = "preset",
    text_style_prompt: Optional[str] = None,
    readability_priority: bool = True,
    experimental_mode: bool = False,
    engine: str = "dalle",
    glossy: bool = False,
    visual_history: dict = None,
    render_metadata: dict = None,
    layout: str = "english_first",
    background_image=None,
    background_sink=None,
    post_format="feed_4_5",
    brand_kit=None,
    scene_bounds=None,
) -> str:
    """
    Render every source block with measured typography, or fail without clipping.
    """
    # Preflight all source blocks before any paid image-provider call.
    from app.services.vision_families import DESIGN_FAMILIES, SCENE_FAMILIES, scene_prompt
    family = style if style in DESIGN_FAMILIES else "legacy"
    target_size, text_blocks = layout_card(segments, family=family, layout=layout, post_format=post_format, brand_kit=brand_kit)
    from app.services.brand_kit import PALETTES
    brand_palette = PALETTES[brand_kit["palette"]] if brand_kit is not None else None
    W, H = target_size
    cx, cy = W // 2, H // 2
    base_dir    = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print(f"\n{'═'*64}")
    print(f"🎨 [v9.0] mode={mode}  style={style}  engine={engine}")
    print(f"📝 prompt={repr((visual_prompt or '')[:65])}")
    print(f"📦 segments={len(segments)}")
    print(f"{'═'*64}")

    # 1. Background Generation / Setup
    bg = None
    vs_spec = None
    typo_spec = None
    dalle_bg = None
    
    if mode == "custom" and (not visual_prompt or not visual_prompt.strip()):
        raise ValueError("A visual direction is required for a custom background")

    # Scene mode: if style is a known scene preset, route to scene pipeline
    _SCENE_KEYS = {
        # Studio / scheduled-post scene presets
        "sacred_script", "midnight_oasis", "desert_glow", "luxury_editorial",
        # Automation Style DNA families — each has SCENE_PROMPT_TEMPLATES entry
        "sacred_black", "emerald_forest", "celestial_night",
        "parchment_manuscript", "luxury_marble", "sacred_desert",
        # New extended families
        "royal_velvet", "midnight_ink", "dawn_horizon",
        "obsidian_stone", "ocean_depth", "warm_copper",
    }
    if mode == "scene" or (style in _SCENE_KEYS and mode not in {"custom"}):
        mode = "scene"

    if family in SCENE_FAMILIES:
        mode = "designed"
        raw_photo = background_image
        if raw_photo is None:
            prompt, recipe = scene_prompt(family, target_size, scene_bounds or [b["bounds"] for b in text_blocks],
                                          direction=visual_prompt, history=visual_history)
            if render_metadata is not None:
                render_metadata.update(recipe)
            raw_photo = generate_background(prompt, target_size, engine=engine, render_metadata=render_metadata,
                provider_size="1152x2048" if post_format == "story_9_16" else "1088x1360")
        if raw_photo is None:
            raise ValueError("Sabeel Vision could not generate this background")
        bg = ImageOps.fit(raw_photo.convert("RGB"), target_size, method=Image.Resampling.LANCZOS)
        if render_metadata is not None:
            render_metadata["background_reused"] = background_image is not None
    elif family in {"editorial", "minimal_paper"}:
        mode = "designed"
        bg = Image.new("RGB", target_size, brand_palette["paper"] if brand_palette else (248, 246, 239) if family == "minimal_paper" else (244, 246, 243))
        if family == "minimal_paper":
            # Subtle material variation, never decorative marks or pseudo-script.
            grain = Image.effect_noise(target_size, 9).convert("RGB")
            bg = Image.blend(bg, grain, .025)
    elif family == "quiet_photography":
        mode = "designed"
        raw_photo = background_image
        if raw_photo is None:
            prompt = ("Quiet editorial photograph, credible natural light, real materials and restrained composition. "
                      "No text, lettering, calligraphy, symbols, decorative borders, gold filigree, glow or fantasy. "
                      "No people. Detail should remain convincing when cropped to a wide photograph. "
                      + (visual_prompt or "Soft daylight across a pale stone courtyard and olive-tree shadows."))
            raw_photo = generate_background(prompt, (1080, 1080), cache_dir=None, engine=engine,
                                            render_metadata=render_metadata)
        if raw_photo is None:
            raise ValueError("Sabeel Vision could not generate the photograph")
        bg = Image.new("RGB", target_size, brand_palette["paper"] if brand_palette else (247, 246, 242))
        photo_height = text_blocks[0]["photo_height"]
        photo = ImageOps.fit(raw_photo.convert("RGB"), (W, photo_height), method=Image.Resampling.LANCZOS)
        bg.paste(photo, (0, H-photo_height))
        if render_metadata is not None:
            render_metadata["background_reused"] = background_image is not None
            render_metadata["background_sha256"] = hashlib.sha256(raw_photo.convert("RGB").tobytes()).hexdigest()

    if mode == "gallery":
        # Load the user-selected premium background from the app's static directory
        try:
            # Robust pathing: find the static/img/gallery folder relative to the app root
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if os.path.basename(style) != style:
                raise ValueError("Invalid gallery image")
            bg_path = os.path.join(app_root, "static", "img", "gallery", style)
            bg = Image.open(bg_path).convert("RGB")
            if bg.size != target_size:
                bg = ImageOps.fit(bg, target_size, method=Image.Resampling.LANCZOS)
            # bg = apply_vignette(bg, intensity=0.42)
        except Exception as e:
            print(f"⚠️ [Gallery Mode] Could not load {style}: {e}")
            bg = None
            raise ValueError("The selected gallery image is unavailable")

    if mode == "custom":
        if _VS_OK:
            vs_spec = vs_interpret(visual_prompt)
            dalle_bg = generate_background(visual_prompt, target_size, cache_dir=None if render_metadata is not None else output_dir, engine=engine, vs_spec=vs_spec, render_metadata=render_metadata)
        
        if dalle_bg is None:
            raise ValueError("Sabeel Vision could not generate the requested background")
        else:
            bg = dalle_bg
            # Analyze background to detect if it's too bright/busy
            center_b = _detect_center_brightness(bg, target_size)
            if center_b > 180:
                # Add a subtle dark wash to ensure white text pops or switch to dark text
                # We'll stick to a subtle wash to preserve the aesthetic
                # bg = apply_vignette(bg, intensity=0.45)
                pass
            else:
                # bg = apply_vignette(bg, intensity=0.38)
                pass

    if mode == "scene":
        # SCENE MODE: text-stage-first composition with dynamic variation
        scene_key = style if style in _SCENE_KEYS else "sacred_script"
        
        if engine in ("dalle", "openai", "gemini") and _VS_OK:
            from app.services.visual_system import compose_scene_prompt
            scene_prompt = compose_scene_prompt(scene_key, custom_direction=visual_prompt, history=visual_history, metadata=render_metadata)
            dalle_bg = generate_background(scene_prompt, target_size, cache_dir=output_dir, engine=engine, vs_spec=None, render_metadata=render_metadata)
            if dalle_bg:
                bg = dalle_bg
                # bg = apply_vignette(bg, intensity=0.42)
        
        if bg is None:
            raise ValueError("Sabeel Vision could not generate the requested scene")

    if mode == "preset":
        key = style if style in PRESET_CONFIGS else "quran"
        cfg = PRESET_CONFIGS[key]
        bg = Image.new("RGB", target_size, cfg["bg_start"])
        draw = ImageDraw.Draw(bg)
        if cfg["bg_start"] != cfg["bg_end"]:
            draw_radial_gradient(draw, target_size, cfg["bg_start"], cfg["bg_end"])
        
        pat = cfg.get("pattern")
        if pat == "islamic": draw_islamic_pattern(draw, target_size, cfg.get("pattern_col", (190, 150, 40, 30)))
        elif pat == "paper": draw_paper_texture(draw, target_size, cfg["base"])
        elif pat == "starry": draw_starry_noise(draw, target_size, cfg.get("pattern_density", 0.0006))
            
        l_pos = cfg.get("light_pos")
        pos = (W // 2, H // 2) if l_pos == "center" else l_pos if isinstance(l_pos, tuple) else None
        if pos and cfg.get("light_col"):
            bg = apply_light_source(bg, target_size, pos, cfg["light_col"], cfg.get("light_r", 300))
            
        atm = cfg.get("atmosphere")
        if atm == "fajr_horizon":
            horizon = Image.new("RGBA", target_size, (0, 0, 0, 0))
            hd = ImageDraw.Draw(horizon)
            hd.rectangle([0, H//2+100, W, H], fill=(10, 15, 45, 120))
            bg = Image.alpha_composite(bg.convert("RGBA"), horizon.filter(ImageFilter.GaussianBlur(80))).convert("RGB")
        elif atm == "parchment":
            bg = apply_parchment_depth(bg, target_size, intensity=0.6)
        elif atm == "celestial":
            celestial = Image.new("RGBA", target_size, (0, 0, 0, 0))
            cd = ImageDraw.Draw(celestial)
            cd.ellipse([W//2-300, H//2-300, W//2+300, H//2+300], fill=(160, 100, 255, 30))
            bg = Image.alpha_composite(bg.convert("RGBA"), celestial.filter(ImageFilter.GaussianBlur(140))).convert("RGB")
        elif atm == "arch_veil":
            # Scene-Based Arch Veil: deep soft side curtains that frame the center stage
            # Left curtain — deep gradient from left edge toward center
            arch = Image.new("RGBA", target_size, (0, 0, 0, 0))
            ad = ImageDraw.Draw(arch)
            curtain_w = int(W * 0.38)
            for x in range(curtain_w):
                fade = int(200 * (1 - (x / curtain_w)) ** 1.8)
                ad.line([(x, 0), (x, H)], fill=(0, 0, 0, fade))
            # Right curtain — mirror
            for x in range(curtain_w):
                rx = W - 1 - x
                fade = int(200 * (1 - (x / curtain_w)) ** 1.8)
                ad.line([(rx, 0), (rx, H)], fill=(0, 0, 0, fade))
            arch = arch.filter(ImageFilter.GaussianBlur(32))
            bg = Image.alpha_composite(bg.convert("RGBA"), arch).convert("RGB")
            
        v = cfg.get("vignette", 0)
        # if v > 0: bg = apply_vignette(bg, intensity=v)
            
        bdr = cfg.get("border")
        draw = ImageDraw.Draw(bg)
        if bdr == "gold_block": draw_gold_border(draw, target_size, cfg.get("border_w", 30))
        elif bdr == "corner_filigree": draw_corner_filigree(draw, target_size, (200, 162, 42), length=80)
            
        palette = PRESET_TEXT.get(key, PRESET_TEXT["quran"])
        glow_rgba = cfg.get("glow")

    if render_metadata is not None:
        render_metadata.setdefault("background_sha256", hashlib.sha256(bg.convert("RGB").tobytes()).hexdigest())
        if mode == "custom" and vs_spec is not None:
            import json
            render_metadata["prompt_signature"] = hashlib.sha256(json.dumps({"prompt": visual_prompt, "traits": vs_spec.variation_traits}, sort_keys=True).encode()).hexdigest()

    # The shared final quality gate checks the actual glyph footprints. Legacy
    # gallery/scene choices remain usable, but no extra glow is added to them.
    quality = {}
    # Save the reusable original before contrast validation. A rejected layout
    # must not force another paid generation merely to try a different layout.
    if family in SCENE_FAMILIES or family == "quiet_photography":
        if background_sink and background_image is None:
            background_sink(raw_photo)
    final_img = paint_card_text(bg, text_blocks, quality=quality, brand_kit=brand_kit,
                               wash_limit=.2 if family in SCENE_FAMILIES else 1,
                               strong_ink=family in SCENE_FAMILIES)
    if render_metadata is not None:
        render_metadata["quality"] = quality
        render_metadata["card_layout"] = {
            "width": W, "height": H, "family": family, "layout": layout,
            "blocks": [{"role": b["role"], "font_size": b["size"],
                        "line_count": len(b["lines"]), "bounds": list(b["bounds"])} for b in text_blocks],
        }

    from uuid import uuid4
    filename = f"qcard_{uuid4().hex}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    
    # Force JPEG format to ensure Magic Bytes match the extension for Meta's crawler
    print(f"!!! [RENDERER] WRITING TO: {final_path}")
    final_img.save(final_path, format="JPEG", quality=95)
    if family in SCENE_FAMILIES:
        from app.services.card_typography import check_encoded_contrast
        try:
            while True:
                try:
                    with Image.open(final_path) as encoded:
                        check_encoded_contrast(encoded, bg, text_blocks, quality)
                    break
                except CardTypographyError:
                    # JPEG can reduce contrast at thin glyph edges. Try the
                    # next bounded repair on the SAME original photograph.
                    next_wash = next((n for n in (.1, .2) if n > quality["wash_opacity"]), None)
                    if next_wash is None:
                        raise
                    final_img = paint_card_text(bg, text_blocks, quality=quality, brand_kit=brand_kit,
                                                wash_limit=.2, strong_ink=True, minimum_wash=next_wash)
                    final_img.save(final_path, format="JPEG", quality=95)
        except Exception:
            os.remove(final_path)
            raise
    
    # ZERO-TRUST VERIFICATION
    if os.path.exists(final_path):
         print(f"✅ [RENDERER] SAVE VERIFIED: {final_path}")
    else:
         print(f"❌ [RENDERER] CRITICAL SAVE FAILURE: File missing immediately after save() at {final_path}")
    
    from app.config import build_public_media_url
    return build_public_media_url(filename, local_path=final_path)
def render_quote_card(background_local_path: Optional[str], quote: str,
                      reference: str, output_dir: str) -> str:
    """Legacy image-overlay render with procedural fallback."""
    W, H = 1080, 1080
    
    # 1. Attempt to load specified background
    bg = None
    if background_local_path and os.path.exists(background_local_path):
        try:
            bg = Image.open(background_local_path).convert("RGB")
            r = bg.width / bg.height
            nw, nh = (int(H * r), H) if r > 1 else (W, int(W / r))
            bg = bg.resize((nw, nh), Image.LANCZOS)
            bg = bg.crop(((nw - W) // 2, (nh - H) // 2,
                           (nw - W) // 2 + W, (nh - H) // 2 + H))
        except Exception as e:
            print(f"⚠️ Failed to load background {background_local_path}: {e}")
            bg = None

    # 2. Procedural Fallback if no bg loaded
    if bg is None:
        print("🎨 [Renderer] Generating procedural spiritual background...")
        bg = Image.new("RGB", (W, H), (14, 10, 18)) # Obsidian base
        draw_inner = ImageDraw.Draw(bg)
        # Vertical gradient: Deep Charcoal to Obsidian
        for y in range(H):
            r = int(14 + (24 - 14) * (1 - y/H))
            g = int(10 + (20 - 10) * (1 - y/H))
            b = int(18 + (28 - 18) * (1 - y/H))
            draw_inner.line([(0, y), (W, y)], fill=(r, g, b))
        
        # Add subtle noise or grain for premium feel
        noise = Image.effect_noise((W, H), 12).convert("L")
        noise_ov = Image.new("RGBA", (W, H), (255, 255, 255, 10))
        bg.paste(noise_ov, (0, 0), noise)

    base_dir  = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fp = os.path.join(base_dir, "assets", "fonts", "Inter.ttf")
    try:
        fs, fl = ImageFont.truetype(fp, 36), ImageFont.truetype(fp, 72)
    except Exception:
        fs = fl = ImageFont.load_default()
    # ov = Image.new("RGBA", (W, H), (0, 0, 0, 120))
    # bg = Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(bg)
    for i, l in enumerate(textwrap.wrap(reference, 44)[:2]):
        draw.text((W//2, 120 + i*44), l, font=fs, fill=(212, 175, 55), anchor="mt")
    y = H // 2
    for l in textwrap.wrap(quote, 22):
        draw.text((W//2, y), l, font=fl, fill=(255, 255, 255), anchor="mt")
        y += 80
    os.makedirs(output_dir, exist_ok=True)
    
    fn = f"qcard_{int(time.time()*1000)}.jpg"
    fp2 = os.path.join(output_dir, fn)
    
    # Ensure explicit JPEG format
    print(f"!!! [RENDERER] WRITING TO: {fp2}")
    bg.save(fp2, format="JPEG", quality=95)
    
    # ZERO-TRUST VERIFICATION
    if os.path.exists(fp2):
         print(f"✅ [RENDERER] SAVE VERIFIED: {fp2}")
    else:
         print(f"❌ [RENDERER] CRITICAL SAVE FAILURE: File missing immediately after save() at {fp2}")
    
    from app.config import build_public_media_url
    return build_public_media_url(fn, local_path=fp2)
