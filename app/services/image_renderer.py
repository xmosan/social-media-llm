"""
Sabeel Studio — Image Renderer v7.0  "Spiritual Depth"

Custom pipeline (5 layers):
  1. Base gradient         — material-matched palette, rich dark grounds
  2. Material texture      — marble veins, parchment aging, obsidian depth
  3. Light source          — every card has a focused, emotional light point
  4. Vignette + atmosphere — grain, mist, depth particles
  5. Ornaments / border    — corner filigree, manuscript frame, gold block
Then:
  6. Text (3-zone)         — reference honored, quote prominent, support quiet
  7. Cinematic post        — grain, bloom, warmth
"""

import os
import time
import textwrap
import math
import random
import json
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from openai import OpenAI
from app.config import settings
from google import genai
from google.genai import types
import base64
import io as _io

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

def get_openai_client() -> Optional[OpenAI]:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)

# v8.0 CINEMATIC SETTINGS
SHOW_READABILITY_MASKS = False

def draw_radial_halo(image: Image.Image, center: tuple, radius: int, color: tuple, opacity: int):
    """
    Creates a soft atmospheric radial halo (blurred ellipse) behind the text.
    """
    if opacity <= 0 or radius <= 0:
        return image
        
    w, h = image.size
    halo_mask = Image.new("L", (radius * 2, radius * 2), 0)
    draw = ImageDraw.Draw(halo_mask)
    
    # Draw radial gradient via multiple concentric circles or a single blurred ellipse
    # A blurred ellipse is much smoother for cinematic effects
    draw.ellipse((0, 0, radius * 2, radius * 2), fill=255)
    halo_mask = halo_mask.filter(ImageFilter.GaussianBlur(radius // 2.5))
    
    # Apply requested alpha/opacity
    halo_mask = Image.eval(halo_mask, lambda x: int(x * (opacity / 255.0)))
    
    halo_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    halo_color = (int(color[0]), int(color[1]), int(color[2]), 255)
    
    # Paste the blurred halo at the center
    # center is (cx, cy)
    cx, cy = center
    halo_layer.paste(halo_color, (int(cx - radius), int(cy - radius)), halo_mask)
    
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

def get_gemini_client():
    if not settings.gemini_api_key:
        return None
    # Using the modern GenAI Python SDK
    return genai.Client(api_key=settings.gemini_api_key)


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
    Split text into 2-4 lines that are roughly equal in pixel width.
    Accounts for letter_spacing (tracking) in width calculations.
    """
    words = text.strip().split()
    if not words: return []
    
    # Measure total width to estimate line count
    raw_w = draw_tmp.textbbox((0, 0), text, font=font)[2]
    total_w = raw_w + (len(text) - 1) * letter_spacing
    n_lines = max(1, math.ceil(total_w / max_width))
    
    # For small snippets, don't force multiple lines unless necessary
    if n_lines == 1 and total_w < max_width:
        return [text]

    # Target width per line
    target_w = total_w / n_lines
    
    lines = []
    current_line = []
    current_w = 0
    
    for word in words:
        # Measure word including the trailing space
        w_text = word + " "
        w_raw = draw_tmp.textbbox((0, 0), w_text, font=font)[2]
        word_w = w_raw + len(w_text) * letter_spacing
        
        # Threshold (1.15x) to allow some lines to be slightly wider to keep balance.
        if current_w + word_w > target_w * 1.15 and current_line:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_w = word_w
        else:
            current_line.append(word)
            current_w += word_w
            
    if current_line:
        lines.append(" ".join(current_line))
        
    return lines


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
    client = get_openai_client()
    if not client:
        return config

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a glow color engine for Islamic quote cards. "
                    "Return ONLY a JSON object with ONE key: "
                    '{"glow_color_rgba":[r,g,b,a]} where all values are integers 0-255. '
                    "Choose a glow color that fits the mood: "
                    "golden glow = warm gold, emerald aura = soft green, "
                    "celestial = cool pale blue-white, moonlit = silver-blue. "
                    "Alpha between 60 and 120."
                )},
                {"role": "user", "content": f"Visual: {visual_prompt}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.3, timeout=6
        )
        ai = _normalize_config(json.loads(r.choices[0].message.content))
        # Only update glow — NEVER touch bg_start_rgb or bg_end_rgb
        if "glow_color_rgba" in ai:
            config["glow_color_rgba"] = ai["glow_color_rgba"]
            print(f"🤖 [StyleAnalyzer] AI glow: {ai['glow_color_rgba']}")
    except Exception as e:
        print(f"⚠️  [StyleAnalyzer] AI skipped ({e})")

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
    vs_spec = None
) -> Optional[Image.Image]:
    """
    Unified entry point for background generation.
    Checks cache first, then switches between DALL-E and Gemini.
    """
    # 1. Attempt Cache Load (Semantic Match)
    if cache_dir and vs_spec and vs_load_cache:
        img = vs_load_cache(vs_spec, cache_dir, engine=engine)
        if img: return img

    # 2. Generate Fresh if Cache Miss
    if engine == "gemini":
        img = generate_background_gemini(
            visual_prompt, target_size, cache_dir, vs_spec=vs_spec)
        if img:
            return img
        
        # 3. RECOVERY MODE: If Gemini fails, don't show green—try DALL-E
        print("🔄 [Gemini] Generation failed — attempting DALL-E Recovery...")
        # We fall through to the DALL-E logic below
    
    # Default: DALL-E
    client = get_openai_client()
    if not client:
        print("📌 [DALL-E] No OpenAI key — PIL fallback")
        return None

    dalle_prompt = vs_compose(vs_spec, raw_prompt=visual_prompt) if vs_spec and vs_compose else _build_bg_prompt(visual_prompt)
    print(f"\n🎨 [DALL-E] Generating background plate...")
    
    response = client.images.generate(
        model="dall-e-3",
        prompt=dalle_prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    img_url = response.data[0].url
    import requests
    img_data = requests.get(img_url).content
    img = Image.open(_io.BytesIO(img_data)).convert("RGB")
    
    if img.size != target_size:
        img = img.resize(target_size, Image.LANCZOS)
        
    print("✅ [DALL-E] Background plate ready")
    
    if cache_dir and vs_spec and vs_save_cache:
            vs_save_cache(img, vs_spec, cache_dir, engine="dalle")
        
    return img


def generate_background_gemini(
    visual_prompt: str,
    target_size: tuple = (1080, 1080),
    cache_dir: Optional[str] = None,
    vs_spec = None
) -> Optional[Image.Image]:
    """
    Gemini (Imagen 3) implementation for background plate generation.
    """
    client = get_gemini_client()
    if not client:
        print("📌 [Gemini] No Google API key — falling back")
        return None

    # Compose the stricter Gemini prompt
    if vs_spec and vs_compose_gemini:
        prompt = vs_compose_gemini(vs_spec, raw_prompt=visual_prompt)
    else:
        prompt = f"A professional background plate: {visual_prompt}. No text, no calligraphy."

    models_to_try = [
        'imagen-4.0-generate-001',
        'imagen-4.0-fast-generate-001'
    ]

    last_err = None
    for model_name in models_to_try:
        print(f"\n💎 [Gemini] Manifesting background (model={model_name})...")
        try:
            response = client.models.generate_images(
                model=model_name,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio='1:1',
                    output_mime_type='image/jpeg'
                )
            )
            
            if not response.generated_images:
                print(f"⚠️  [Gemini] No images returned for {model_name}")
                continue
                
            img_raw = response.generated_images[0].image.image_bytes
            img = Image.open(_io.BytesIO(img_raw)).convert("RGB")
            
            if img.size != target_size:
                img = img.resize(target_size, Image.LANCZOS)
                
            print(f"✅ [Gemini] {model_name} generated successfully")
            
            if cache_dir and vs_spec and vs_save_cache:
                vs_save_cache(img, vs_spec, cache_dir, engine="gemini")
                
            return img

        except Exception as e:
            last_err = e
            print(f"❌ [Gemini] {model_name} failed: {e}")
            continue

    print(f"💀 [Gemini] Exhausted all models. Final error: {last_err}")
    return None


def generate_dalle_background(
    visual_prompt: str,
    target_size: tuple = (1080, 1080),
    cache_dir: Optional[str] = None,
    dalle_prompt_override: Optional[str] = None,
) -> Optional[Image.Image]:
    """
    Three-tier background generation for custom mode:

    Tier 1 — File cache    : Same prompt → instant load, zero DALL-E cost.
    Tier 2 — PIL fast-path : Simple single-theme prompts → rich PIL rendering.
    Tier 3 — DALL-E 3      : Complex/unique prompts → photo-realistic bg plate.

    The DALL-E prompt is pre-processed by _build_bg_prompt() to:
    - Frame the output explicitly as a background plate (NOT a finished card)
    - Expand vague material keywords to richer visual descriptors
    - Add composition guidance (clear uncluttered center)
    - Apply five-clause constraint preventing any Arabic/text from appearing

    Returns an RGB PIL Image at target_size, or None on total failure.
    """
    # ── Tier 1: (Removed - handled by caller vs_load_cache for variation awareness) ──

    # ── Tier 2: PIL fast-path ─────────────────────────────────────────────────
    if _is_fast_path(visual_prompt):
        print(f"⚡ [BG] Fast-path PIL for: '{visual_prompt[:55]}'")
        return None   # signals caller to use PIL pipeline (already implemented)

    # ── Tier 3: DALL-E 3 ─────────────────────────────────────────────────────
    client = get_openai_client()
    if not client:
        print("📌 [DALL-E] No OpenAI key — PIL fallback")
        return None

    dalle_prompt = dalle_prompt_override or _build_bg_prompt(visual_prompt)
    print(f"\n🎨 [DALL-E] Generating background plate...")
    print(f"   User: '{visual_prompt[:70]}'")
    print(f"   Sent: {dalle_prompt[:110]}...")

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=dalle_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        img_url = response.data[0].url
        with urllib.request.urlopen(img_url, timeout=38) as resp:
            img_data = resp.read()
        img = Image.open(_io.BytesIO(img_data)).convert("RGB")
        if img.size != target_size:
            img = img.resize(target_size, Image.LANCZOS)
        print("✅ [DALL-E] Background plate ready")

        # Save to cache for next time
        if cache_dir:
            _save_bg_cache(img, visual_prompt, cache_dir)

        return img
    except Exception as e:
        print(f"⚠️  [DALL-E] Failed ({type(e).__name__}: {e}) — PIL fallback")
        return None


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
    stroke_fill: tuple = None
):
    """
    Advanced text drawing with support for tracking (letter_spacing), 
    shadows, and secondary effects.
    """
    if letter_spacing == 0:
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
        "base": (0, 0, 0),
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
}

PRESET_TEXT = {
    "quran":      [(212, 175, 55), (255, 255, 255), (190, 215, 192)],
    "fajr":       [(138, 170, 248), (228, 238, 255), (168, 195, 240)],
    "scholar":    [(88, 75, 55),   (28, 22, 16),    (95, 82, 62)],
    "madinah":    [(215, 168, 62), (255, 242, 210), (202, 178, 132)],
    "kaaba":      [(180, 148, 50), (255, 255, 255), (185, 185, 185)],
    "laylulqadr": [(180, 145, 238), (238, 230, 255), (195, 175, 242)],
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

    Returns [reference_rgb, quote_rgb, support_rgb].

    Zone layout (fractions of 1080x1080):
      Zone A (reference / top ornament): rows 8–25%
      Zone B (main quote):               rows 30–70%
      Zone C (support / bottom):         rows 72–88%
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
        """Return RGB that maximally contrasts with the sampled brightness."""
        if brightness < 100:
            # Very dark bg: bright white or warm gold for accent
            return (220, 178, 58) if accent else (255, 255, 255)
        elif brightness < 155:
            # Medium-dark: off-white or slightly muted gold
            return (210, 168, 52) if accent else (248, 248, 245)
        elif brightness < 200:
            # Medium-light: dark brown-gold or near-black
            return (60, 40, 8)   if accent else (22, 18, 12)
        else:
            # Very light: deep mahogany or near-black
            return (50, 30, 5)   if accent else (12, 10, 8)

    ref_c     = pick_text(bA, accent=True)
    quote_c   = pick_text(bB, accent=False)
    support_c = pick_text(bC, accent=False)

    print(f"   🎨 Adaptive palette:  "
          f"A-brt={bA:.0f} ref={ref_c}  "
          f"B-brt={bB:.0f} qte={quote_c}  "
          f"C-brt={bC:.0f} sup={support_c}")

    return [ref_c, quote_c, support_c]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER ENGINE v7.0
# ─────────────────────────────────────────────────────────────────────────────

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
    glossy: bool = False
) -> str:
    """
    Sabeel Designer Engine v7.0 — Spiritual Depth Renderer.
    """
    W, H = 1080, 1080
    target_size = (W, H)
    cx, cy = W // 2, H // 2
    base_dir    = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print(f"\n{'═'*64}")
    print(f"🎨 [v7.0] mode={mode}  style={style}  engine={engine}")
    print(f"📝 prompt={repr((visual_prompt or '')[:65])}")
    print(f"📦 segments={len(segments)}")
    print(f"{'═'*64}")

    # Initial default font
    font_file = "Inter.ttf"
    font_path = os.path.join(base_dir, "assets", "fonts", font_file)

    # ── MODE: CUSTOM ──────────────────────────────────────────────────────────
    if mode == "custom" and (not visual_prompt or not visual_prompt.strip()):
        mode = "preset"; style = "quran"

    typo_spec = None   # will be populated by visual system if available

    if mode == "custom":
        # Interpret prompt → VisualSpec, compose safe DALL-E prompt
        vs_spec = None
        if _VS_OK:
            vs_spec      = vs_interpret(visual_prompt)
            # Logic moved to centralized generate_background switcher
            dalle_bg = generate_background(
                visual_prompt, target_size, 
                cache_dir=output_dir,
                engine=engine,
                vs_spec=vs_spec
            )

        kw_ov     = interpret_visual_prompt(visual_prompt or "")
        glow_rgba = tuple(int(v) for v in kw_ov.get("glow_color_rgba",
                                                      [255, 245, 220, 60]))

        if dalle_bg is None:
            mode = "preset"
        else:
            bg = dalle_bg

            # Gentle vignette (preserves DALL-E detail)
            bg   = apply_vignette(bg, intensity=0.38)
            draw = ImageDraw.Draw(bg)

    # ── VISUAL SYSTEM INTEGRATION ─────────────────────────────────────────────
    # This block interprets aesthetic intent and adapts typography to the background.
    if _VS_OK:
        # Avoid double interpretation if already done for custom mode
        if typo_spec is None:
            # 1. Interpret user text-style intent
            text_style = vs_interpret_text(text_style_prompt, experimental=experimental_mode)
            
            # 2. Analyze background (requires bg to be initialized)
            # If in custom mode, bg is the DALL-E image. 
            # If in preset mode, bg is generated below.
            # So we move this analysis to AFTER bg is finalized.
            pass 
    else:
        typo_spec = None
        # Ornaments driven by spec.ornament_level
        gold_c    = (205, 165, 45)
        orn_level = getattr(vs_spec, "ornament_level", "corner") if vs_spec else "corner"
        if orn_level == "ornate":
            draw_manuscript_frame(draw, target_size, tuple(max(0, v - 20) for v in gold_c))
            draw_corner_filigree(draw, target_size, gold_c, length=90)
        elif orn_level in ("corner", "moderate"):
            draw_corner_filigree(draw, target_size, gold_c, length=82)
        elif orn_level == "minimal":
            draw_corner_filigree(draw, target_size, gold_c, length=48)

    if mode == "preset":
        # ── MODE: PRESET ──────────────────────────────────────────────────────
        key = style if style in PRESET_CONFIGS else "quran"
        cfg = PRESET_CONFIGS[key]
        
        bg = Image.new("RGB", target_size, cfg["bg_start"])
        draw = ImageDraw.Draw(bg)
        if cfg["bg_start"] != cfg["bg_end"]:
            draw_radial_gradient(draw, target_size, cfg["bg_start"], cfg["bg_end"])
        
        pat = cfg.get("pattern")
        if pat == "islamic":
            draw_islamic_pattern(draw, target_size, cfg.get("pattern_col", (190, 150, 40, 30)))
        elif pat == "paper":
            draw_paper_texture(draw, target_size, cfg["base"])
        elif pat == "starry":
            draw_starry_noise(draw, target_size, cfg.get("pattern_density", 0.0006))
            
        l_pos = cfg.get("light_pos")
        pos = None
        if l_pos == "center":
            pos = (W // 2, H // 2)
        elif isinstance(l_pos, tuple):
            pos = l_pos
            
        if pos and cfg.get("light_col"):
            bg = apply_light_source(bg, target_size, pos, cfg["light_col"], cfg.get("light_r", 300))
            draw = ImageDraw.Draw(bg)
            
        atm = cfg.get("atmosphere")
        if atm == "fajr_horizon":
            horizon = Image.new("RGBA", target_size, (0, 0, 0, 0))
            hd = ImageDraw.Draw(horizon)
            hd.rectangle([0, H//2+100, W, H], fill=(10, 15, 45, 120))
            horizon = horizon.filter(ImageFilter.GaussianBlur(80))
            bg = Image.alpha_composite(bg.convert("RGBA"), horizon).convert("RGB")
            draw = ImageDraw.Draw(bg)
        elif atm == "parchment":
            bg = apply_parchment_depth(bg, target_size, intensity=0.6)
            draw = ImageDraw.Draw(bg)
        elif atm == "celestial":
            celestial = Image.new("RGBA", target_size, (0, 0, 0, 0))
            cd = ImageDraw.Draw(celestial)
            cd.ellipse([W//2-300, H//2-300, W//2+300, H//2+300], fill=(160, 100, 255, 30))
            celestial = celestial.filter(ImageFilter.GaussianBlur(140))
            bg = Image.alpha_composite(bg.convert("RGBA"), celestial).convert("RGB")
            draw = ImageDraw.Draw(bg)
            
        v = cfg.get("vignette", 0)
        if v > 0:
            bg = apply_vignette(bg, intensity=v)
            draw = ImageDraw.Draw(bg)
            
        bdr = cfg.get("border")
        if bdr == "gold_block":
            draw_gold_border(draw, target_size, cfg.get("border_w", 30))
        elif bdr == "corner_filigree":
            draw_corner_filigree(draw, target_size, (200, 162, 42), length=80)
            
        palette = PRESET_TEXT.get(key, PRESET_TEXT["quran"])
        glow_rgba = cfg.get("glow")

    # ── FINAL TYPOGRAPHY ADAPTATION ──────────────────────────────────────────
    # Run analysis and adaptation now that 'bg' is definitively ready (custom or preset)
    if _VS_OK and typo_spec is None:
        text_style = vs_interpret_text(text_style_prompt, experimental=experimental_mode)
        analysis   = vs_analyze(bg, target_size)
        typo_spec  = vs_adapt(analysis, vs_spec if mode == "custom" else None, 
                              text_style=text_style, readability_priority=readability_priority)
        
        print(f"   🎨 [Adapt] mode={typo_spec.typography_mode} risk={typo_spec.readability_risk}")

    if typo_spec is None:
        # Fallback to simple adaptive palette if visual_system failed or isn't used
        palette = _build_adaptive_palette(bg, target_size)
    # Generous zones: Reference (A) | Main Quote (B) | Supporting (C)
    v_pad   = 120  # Increased for breathing room
    zone_ws = [int(W * 0.70), int(W * 0.82), int(W * 0.74)]
    zone_ls = [22, 34, 24]
    gap_ab  = 74   # refined gap: Reference → Quote
    gap_bc  = 74   # refined gap: Quote → Supporting

    draw_tmp = ImageDraw.Draw(bg)
    zone_data = []

    for i, seg in enumerate(segments):
        if i >= 3:
            break
        z_w, z_ls = zone_ws[i], zone_ls[i]
        if typo_spec:
            style_idx = [typo_spec.top, typo_spec.main, typo_spec.sub][i]
            col = style_idx.color
        else:
            col = palette[i] if palette and i < len(palette) else (255,255,255)
        
        # ── PREMIUM HIERARCHY OVERRIDES ──────────────────────────────────────
        if mode == "custom":
            # Default sizes: 34 (Ref), 74 (Quote), 42 (Support)
            base_sizes = [34, 74, 42]
            
        # ── DYNAMIC FONT SELECTION ──────────────────────────────────────────
        # Build path based on family, weight, and italic intent
        family = "Sans"
        if typo_spec and typo_spec.text_style:
            family = typo_spec.text_style.font_family
            ts = typo_spec.text_style
            
            # Map logical families to assets
            f_base = "Amiri" if family == "Serif" else "Inter"
            
            # Form specific variant name (e.g., Inter-Bold.ttf)
            variant = f_base
            if ts.weight == "Bold": variant += "-Bold"
            elif ts.weight == "Light": variant += "-Light"
            if ts.italic: variant += "-Italic"
            
            # Fallback to Regular if specific variant doesn't exist
            font_path = os.path.join(base_dir, "assets", "fonts", f"{variant}.ttf")
            if not os.path.exists(font_path):
                # Try adding -Regular if it's missing (Amiri uses -Regular.ttf)
                if not os.path.exists(os.path.join(base_dir, "assets", "fonts", f"{f_base}-Regular.ttf")):
                    font_path = os.path.join(base_dir, "assets", "fonts", f"{f_base}.ttf")
                else:
                    font_path = os.path.join(base_dir, "assets", "fonts", f"{f_base}-Regular.ttf")

        try:
            fnt = ImageFont.truetype(font_path, int(seg["size"]))
        except Exception:
            fnt = ImageFont.load_default()

        # Handle text wrap width using the exact font metrics
        # For Zone A, we want wider tracking (simulated by spaces if needed, but
        # PIL handles kerning natively mostly. We will draw custom spacing later, 
        # but for bounding box width we account for expanded characters).
        avg_cw = seg["size"] * (0.64 if i == 0 else 0.50)
        max_chars = max(10, int(z_w / max(1, avg_cw)))
        
        seg_text = str(seg["text"])
        if typo_spec and typo_spec.text_style:
            if typo_spec.text_style.uppercase or (mode == "custom" and i == 0):
                seg_text = seg_text.upper()
        elif mode == "custom" and i == 0:
            seg_text = seg_text.upper() 

        if mode == "custom" and i == 0:
            # Manually inject tracking spaces between letters for Zone A
            seg_text = " ".join(list(seg_text)).replace("   ", "  ")
            
        # Use our intelligent balanced wrapper instead of textwrap
        ls_val = typo_spec.text_style.letter_spacing if typo_spec and typo_spec.text_style else 0
        raw = balanced_text_wrap(seg_text, fnt, z_w, draw_tmp, letter_spacing=ls_val)
        
        if i == 0 and len(raw) > 2:
            raw = raw[:2]; raw[-1] = raw[-1].rstrip() + "…"
            
        # Refine Zone C opacity (make it softer natively)
        if mode == "custom" and i == 2:
            # Drop the alpha of Zone C by ~25%
            col = (col[0], col[1], col[2], 190)

        block_h = 0
        lines   = []
        for line in raw:
            bbox = draw_tmp.textbbox((0, 0), line, font=fnt)
            lh   = bbox[3] - bbox[1]
            lw   = bbox[2] - bbox[0]
            lines.append({"text": line, "h": lh, "w": lw})
            block_h += lh + z_ls
        if block_h > 0:
            block_h -= z_ls

        zone_data.append({"font": fnt, "lines": lines,
                          "block_h": block_h, "color": col, "ls": z_ls})
        print(f"   Zone {i}: {len(lines)} lines  h={block_h}px  size={seg['size']}")

    # Optical centering and Vertical Placement logic
    total_h = sum(zd["block_h"] for zd in zone_data)
    if len(zone_data) > 1: total_h += gap_ab
    if len(zone_data) > 2: total_h += gap_bc
    
    # Default: Center vertically
    start_y = (H // 2) - (total_h // 2) - int(H * 0.03)
    
    # User-defined placement
    if typo_spec and typo_spec.text_style:
        vp = typo_spec.text_style.v_placement
        if vp == "Top_Third":
            start_y = int(H * 0.18)
        elif vp == "Bottom_Third":
            start_y = int(H * 0.82) - total_h
            
    start_y = max(v_pad, start_y)
    print(f"📐 total_h={total_h}  start_y={start_y}")

    # Ornament / glow colors — driven by TypographySpec theme when available
    if typo_spec is not None:
        g_rgba  = typo_spec.glow_rgba
        orn_col = list(typo_spec.orn_color)
        sep_col = tuple(typo_spec.orn_color)
    else:
        g_rgba  = glow_rgba
        orn_col = list(g_rgba[:3]) if g_rgba else [200, 162, 42]
        sep_col = (min(255, int(orn_col[0] * 0.9)),
                   min(255, int(orn_col[1] * 0.9)),
                   min(255, int(orn_col[2] * 0.75)))

    # ── LAYOUT RESOLVER ──────────────────────────────────────────────────────
    # Determine (cx, y, anchor) for each zone based on LayoutMode
    layout_params = []
    
    if typo_spec and typo_spec.text_style.layout_mode == "Editorial":
        ts = typo_spec.text_style
        # Zone 0: Top-Right (always, for balance)
        layout_params.append({
            "cx": int(W * 0.90), "y": int(H * 0.08), "anchor": "rt"
        })
        # Zone 1: Main Quote (User defined placement + side focus)
        q_cx = int(W * 0.10) if ts.alignment != "Right" else int(W * 0.90)
        q_y = start_y
        layout_params.append({
            "cx": q_cx, "y": q_y, "anchor": "lt" if ts.alignment != "Right" else "rt"
        })
        # Zone 2: Support (Opposite of quote or bottom center)
        layout_params.append({
            "cx": int(W * 0.90) if ts.alignment != "Right" else int(W * 0.10),
            "y": H - int(H * 0.10) - zone_data[2]["block_h"],
            "anchor": "rb" if ts.alignment != "Right" else "lb"
        })
    else:
        # Default: Stacked Vertical Layout
        curr_y = start_y
        for i, zd in enumerate(zone_data):
            # Alignment logic
            z_cx = W // 2
            z_anchor = "mt"
            if typo_spec and typo_spec.text_style:
                ts = typo_spec.text_style
                if ts.alignment == "Left":
                    z_cx = int(W * 0.12) + ts.horiz_offset
                    z_anchor = "lt"
                elif ts.alignment == "Right":
                    z_cx = int(W * 0.88) - ts.horiz_offset
                    z_anchor = "rt"
            
            layout_params.append({"cx": z_cx, "y": curr_y, "anchor": z_anchor})
            gap = gap_ab if i == 0 else gap_bc
            curr_y += zd["block_h"] + gap

    # ── ATMOSPHERIC READABILITY PASS (v8.0) ──────────────────────────────────
    
    if typo_spec:
        # A. Top Gradient Band (Light Shaping)
        if getattr(typo_spec, "top_band_enabled", False):
            bg = draw_top_gradient_band(
                bg, 
                typo_spec.top_band_color[:3], 
                typo_spec.top_band_alpha,
                height_percent=0.20
            )
            
        # B. Radial Halo (Main Quote Pool)
        if getattr(typo_spec, "halo_radius", 0) > 0:
            # We target the center of the main quote zone (Zone 1)
            main_lp = layout_params[1]
            main_zd = zone_data[1]
            halo_center = (main_lp["cx"], main_lp["y"] + main_zd["block_h"] // 2)
            bg = draw_radial_halo(
                bg, 
                halo_center, 
                typo_spec.halo_radius, 
                typo_spec.halo_color[:3], 
                typo_spec.halo_opacity
            )

    bg_rgba = bg.convert("RGBA")

    # ── DRAWING PASS ─────────────────────────────────────────────────────────

    draw_out = ImageDraw.Draw(bg_rgba)
            
    y = start_y
    
    for i, zd in enumerate(zone_data):
        lp = layout_params[i]
        cx, z_y, anchor = lp["cx"], lp["y"], lp["anchor"]
        
        if typo_spec:
            z_style = [typo_spec.top, typo_spec.main, typo_spec.sub][i]
            col = z_style.color
            opacity = z_style.opacity
            
            # Cinematic Soft Shadow Upgrade:
            # We use the shadow from the spec but soften it for premium feel
            shd_fill = list(z_style.shadow_fill)
            shd_fill[3] = int(shd_fill[3] * 0.7) # Reduce alpha for softness
            shd_fill = tuple(shd_fill)
            
            shd_dx = z_style.shadow_dx
            shd_dy = z_style.shadow_dy
            dim_layer = z_style.dim_layer
            dim_color = z_style.dim_color
            dim_rad = z_style.dim_radius
        else:
            col = zd["color"]
            opacity = 1.0
            shd_fill = (0,0,0,130) if (col[0]+col[1]+col[2])>440 else (255,255,255,100)
            shd_dx, shd_dy = (2,2) if shd_fill[0]==0 else (-1,-1)
            dim_layer = False
            
        fc = (int(col[0]), int(col[1]), int(col[2]), int(255 * opacity))
        
        # Determine strict bounds of current zone for local protection veil
        ty = z_y
        ty_end = ty + zd["block_h"]
        if i == 0: ty_end += gap_ab // 2
        elif i == 1: ty_end += gap_bc // 2
        
        # 1) Protection Layer — REPLACED BY v8.0 ATMOSPHERIC PASS
        # (Old rectangular logic removed as requested)
            
        # --- CINEMATIC TEXT RENDERING (HALO SYSTEM) ---
        # 1. Prepare Zone-Specific Layers
        zone_mask_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
        zone_draw = ImageDraw.Draw(zone_mask_layer)
        
        # 2. Determine Cinematic Treatment
        risk = getattr(typo_spec, "readability_risk", "low")
        radius = 8  # Default Glyph-Halo (v7.5) preserved as secondary reinforcement
        if risk == "high": radius = 14
        elif risk == "medium": radius = 10
        
        # Determine Glyph-Halo Tint
        is_dark_bg = (sum(col[:3]) > 400) # Text is light -> BG is likely dark
        if is_dark_bg:
            h_col = (255, 252, 240, 140 if risk == "high" else 100)
        else:
            h_col = (0, 0, 0, 110 if risk == "high" else 70)
            
        l_spacing = typo_spec.text_style.letter_spacing if typo_spec else 0
        
        # 3. Render Zone Contents (Top/Main/Sub)
        ty = z_y
        
        if i == 0:
            # Check Guardrail for Reference Line (v8.0/v8.5)
            if not getattr(typo_spec, "show_reference", True):
                continue
            
            # Zone-specific letter spacing (already includes base + boost)
            lp_spacing = l_spacing + getattr(z_style, "letter_spacing", 0)
                
            if typo_spec and typo_spec.has_glow:
                draw_top_ornament(zone_draw, cx, ty - 22, typo_spec.orn_color)
                
            # Font Adaptation (v8.5): Slightly smaller for high risk
            z_font = zd["font"]
            if risk == "high":
                try:
                    z_font = ImageFont.truetype(z_font.path, int(z_font.size * 0.92))
                except: pass
                
            for ln in zd["lines"]:
                draw_text_advanced(zone_draw, (cx, ty), ln["text"], font=z_font, fill=fc, anchor=anchor, letter_spacing=lp_spacing)
                ty += ln["h"] + zd["ls"]
            if typo_spec and typo_spec.text_style.layout_mode == "Stack":
                draw_zone_separator(zone_draw, cx, ty + zd["ls"] // 2, typo_spec.orn_color)
            y = ty - zd["ls"] + gap_ab
        elif i == 1:
            # Font Hardening (v8.0): Heavier weight/spacing handled by visual_system
            # Size boost applied here locally
            z_font = zd["font"]
            lp_spacing = l_spacing + getattr(z_style, "letter_spacing", 0)
            
            if risk != "low":
                boost = 1.06 if risk == "medium" else 1.08
                new_size = int(z_font.size * boost)
                try:
                    z_font = ImageFont.truetype(z_font.path, new_size)
                except:
                    pass
            
            for ln in zd["lines"]:
                sw = 1 if typo_spec and typo_spec.text_style.weight == "Bold" else 0
                draw_text_advanced(zone_draw, (cx, ty), ln["text"], font=z_font, fill=fc, anchor=anchor, letter_spacing=lp_spacing, stroke_width=sw, stroke_fill=fc)
                ty += ln["h"] + zd["ls"]
            y = ty - zd["ls"] + gap_bc
        else:
            # Zone-specific letter spacing
            lp_spacing = l_spacing + getattr(z_style, "letter_spacing", 0)
            
            for ln in zd["lines"]:
                draw_text_advanced(zone_draw, (cx, ty), ln["text"], font=zd["font"], fill=fc, anchor=anchor, letter_spacing=lp_spacing)
                ty += ln["h"] + zd["ls"]
            y = ty - zd["ls"]

        # 4. Generate Cinematic Effects Layers
        halo_layer = apply_text_halo(zone_mask_layer, radius=radius, halo_color=h_col)
        
        # Soft Cinematic Shadow Layer
        shd_radius = 4 if risk == "high" else 2
        shadow_mask = zone_mask_layer.split()[-1].filter(ImageFilter.GaussianBlur(shd_radius))
        shadow_layer = Image.new("RGBA", target_size, shd_fill)
        shadow_layer.putalpha(shadow_mask)
        
        # 5. Final Composite Pass (Halo -> Shadow -> Text)
        if halo_layer:
            bg_rgba = Image.alpha_composite(bg_rgba, halo_layer)
        
        # Apply shadow with vertical offset (dy=2)
        shadow_final = Image.new("RGBA", target_size, (0,0,0,0))
        shadow_final.paste(shadow_layer, (0, 2)) # dy=2
        bg_rgba = Image.alpha_composite(bg_rgba, shadow_final)
        
        # Final Text Overlay
        bg_rgba = Image.alpha_composite(bg_rgba, zone_mask_layer)
        
        draw_out = ImageDraw.Draw(bg_rgba)

    # ── CINEMATIC POST ────────────────────────────────────────────────────────
    glow_list  = list(g_rgba) if g_rgba else None
    final_img  = apply_cinematic_layers(bg_rgba, glow_color=glow_list)

    filename   = f"qcard_{int(time.time() * 1000)}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    final_img.save(final_path, quality=95)

    print(f"✅ [v7.0] {filename}  (mode={mode} style={style})")
    print(f"{'═'*64}\n")
    
    # Avoid crashing on missing public_base_url by handling cases where it's not set
    base_url = settings.public_base_url.rstrip('/') if settings.public_base_url else ""
    return f"{base_url}/uploads/{filename}"


def render_quote_card(background_local_path: str, quote: str,
                      reference: str, output_dir: str) -> str:
    """Legacy image-overlay render (kept for compatibility)."""
    bg = Image.open(background_local_path).convert("RGB")
    W, H = 1080, 1080
    r = bg.width / bg.height
    nw, nh = (int(H * r), H) if r > 1 else (W, int(W / r))
    bg = bg.resize((nw, nh), Image.LANCZOS)
    bg = bg.crop(((nw - W) // 2, (nh - H) // 2,
                   (nw - W) // 2 + W, (nh - H) // 2 + H))
    base_dir  = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fp = os.path.join(base_dir, "assets", "fonts", "Inter.ttf")
    try:
        fs, fl = ImageFont.truetype(fp, 36), ImageFont.truetype(fp, 72)
    except Exception:
        fs = fl = ImageFont.load_default()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 120))
    bg = Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(bg)
    for i, l in enumerate(textwrap.wrap(reference, 44)[:2]):
        draw.text((W//2, 120 + i*44), l, font=fs, fill=(212, 175, 55), anchor="mt")
    y = H // 2
    for l in textwrap.wrap(quote, 22):
        draw.text((W//2, y), l, font=fl, fill=(255, 255, 255), anchor="mt")
        y += 80
    fn = f"qcard_{int(time.time()*1000)}.jpg"
    fp2 = os.path.join(output_dir, fn)
    os.makedirs(output_dir, exist_ok=True)
    bg.save(fp2, quality=95)
    return f"{settings.public_base_url.rstrip('/')}/uploads/{fn}"

def draw_soft_protection_glow(base_img, target_size, center, zone_box, blend_color=(0,0,0,128)):
    """
    Subtle contrast boost (ATMOSPHERIC BLOOM).
    No blur, no smudge—just preserves the texture while making text pop.
    """
    if not base_img: return base_img
    
    # We ignore the 'blend_color' alpha and force a much tighter/subtler alpha (5-10%)
    # to avoid the "weird box" reported by the user.
    r, g, b, _ = blend_color
    subtle_color = (r, g, b, 25) # 10% opacity
    
    x1, y1, x2, y2 = zone_box
    mask_region = Image.new("RGBA", (x2-x1, y2-y1), subtle_color)
    
    # Smooth edges for the non-destructive layer
    clean_box = Image.new("RGBA", target_size, (0,0,0,0))
    clean_box.paste(mask_region, (x1, y1))
    
    return Image.alpha_composite(base_img.convert("RGBA"), clean_box).convert("RGB")

def apply_glass_morphism(base_img, target_size, center, zone_box, blend_color=(0,0,0,128), intensity=40):
    """
    Applies a premium frosted glass (Glassmorphism) effect to a specific zone.
    Refracted blur, frosted highlight, and subtle alpha blending.
    """
    if not base_img: return base_img
    
    # Gaussian Blur depth
    blur_radius = intensity // 2
    
    # 1. Extract the region to be frosted
    # Padding to ensure blur doesn't have hard edges
    x1, y1, x2, y2 = zone_box
    pad = 20
    crop_box = (max(0, x1-pad), max(0, y1-pad), min(target_size[0], x2+pad), min(target_size[1], y2+pad))
    
    region = base_img.crop(crop_box)
    
    # 2. Apply atmospheric blur
    blurred = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    
    # 3. Apply frosted tint
    overlay = Image.new("RGBA", blurred.size, blend_color)
    frosted = Image.alpha_composite(blurred.convert("RGBA"), overlay)
    
    # 4. Create mask for the actual zone (rounded rectangle)
    mask = Image.new("L", blurred.size, 0)
    m_draw = ImageDraw.Draw(mask)
    # Local coordinates for the mask
    lx1, ly1 = pad, pad
    lx2, ly2 = (x2-x1) + pad, (y2-y1) + pad
    m_draw.rounded_rectangle([lx1, ly1, lx2, ly2], radius=15, fill=255)
    
    # 5. Composite back onto main image
    final_region = Image.composite(frosted, blurred.convert("RGBA"), mask)
    
    # Paste back
    base_img.paste(final_region.convert("RGB"), crop_box)
    
    return base_img
