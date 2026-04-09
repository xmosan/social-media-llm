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


# ─────────────────────────────────────────────────────────────────────────────
# OPENAI
# ─────────────────────────────────────────────────────────────────────────────

def get_openai_client() -> Optional[OpenAI]:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


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


def generate_dalle_background(
    visual_prompt: str,
    target_size: tuple = (1080, 1080),
    cache_dir: Optional[str] = None,
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
    # ── Tier 1: File cache ────────────────────────────────────────────────────
    if cache_dir:
        cached = _load_bg_cache(visual_prompt, cache_dir)
        if cached is not None:
            if cached.size != target_size:
                cached = cached.resize(target_size, Image.LANCZOS)
            return cached

    # ── Tier 2: PIL fast-path ─────────────────────────────────────────────────
    if _is_fast_path(visual_prompt):
        print(f"⚡ [BG] Fast-path PIL for: '{visual_prompt[:55]}'")
        return None   # signals caller to use PIL pipeline (already implemented)

    # ── Tier 3: DALL-E 3 ─────────────────────────────────────────────────────
    client = get_openai_client()
    if not client:
        print("📌 [DALL-E] No OpenAI key — PIL fallback")
        return None

    dalle_prompt = _build_bg_prompt(visual_prompt)
    print(f"\n🎨 [DALL-E] Background plate (no calligraphy mode)...")
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
) -> str:
    """
    Sabeel Designer Engine v7.0 — Spiritual Depth Renderer.
    """
    W, H = 1080, 1080
    target_size = (W, H)
    base_dir    = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print(f"\n{'═'*64}")
    print(f"🎨 [v7.0] mode={mode}  style={style}")
    print(f"📝 prompt={repr((visual_prompt or '')[:65])}")
    print(f"📦 segments={len(segments)}")
    print(f"{'═'*64}")

    # ── FONT ─────────────────────────────────────────────────────────────────
    use_serif = (style in ("scholar", "madinah") and mode == "preset")
    font_file = "Amiri-Regular.ttf" if use_serif else "Inter.ttf"
    font_path = os.path.join(base_dir, "assets", "fonts", font_file)

    # ── MODE: CUSTOM ──────────────────────────────────────────────────────────
    if mode == "custom":
        overrides = interpret_visual_prompt(visual_prompt or "")
        if not visual_prompt or not visual_prompt.strip():
            mode = "preset"; style = "quran"  # empty prompt fallback

    if mode == "custom":
        # ── Route A: DALL-E Background (primary) ──────────────────────────
        dalle_bg = generate_dalle_background(visual_prompt, target_size,
                                              cache_dir=output_dir)

        if dalle_bg is not None:
            # DALL-E succeeded — use photo-quality background
            bg = dalle_bg

            # Keyword config (for glow, border, intensity — NOT bg color)
            overrides  = interpret_visual_prompt(visual_prompt)
            intensity  = float(overrides.get("intensity", 0.80))
            border_sty = overrides.get("border_style", "none")
            glow_rgba  = tuple(int(v) for v in overrides.get("glow_color_rgba",
                                                              [255, 245, 220, 60]))

            # Readability overlay: soft centre darkening or brightening
            # to make the text zone more uniform before sampling colors
            center_brt = _detect_center_brightness(bg, target_size)
            is_light   = center_brt > 148
            cx, cy   = W // 2, H // 2
            r_layer  = Image.new("RGBA", target_size, (0, 0, 0, 0))
            rd       = ImageDraw.Draw(r_layer)
            if is_light:
                rd.ellipse([cx-380, cy-380, cx+380, cy+380],
                           fill=(255, 255, 255, 50))
            else:
                rd.ellipse([cx-380, cy-380, cx+380, cy+380],
                           fill=(0, 0, 0, 65))
            r_layer = r_layer.filter(ImageFilter.GaussianBlur(110))
            bg = Image.alpha_composite(bg.convert("RGBA"), r_layer).convert("RGB")
            draw = ImageDraw.Draw(bg)

            # Light vignette (frame the subject, don’t crush the DALL-E bg)
            bg   = apply_vignette(bg, intensity=min(0.50, intensity * 0.55))
            draw = ImageDraw.Draw(bg)

            # ━━ Zone-adaptive text palette ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # Sample each text zone of the FINAL background independently.
            # This replaces the single global brightness check and ensures
            # each piece of text contrasts with the exact pixels behind it.
            palette = _build_adaptive_palette(bg, target_size)

            # Border / ornaments on top of DALL-E background
            gold_c = (205, 165, 45)
            if border_sty == "corner_filigree":
                draw_corner_filigree(draw, target_size, gold_c, length=85)
            elif border_sty == "manuscript":
                draw_manuscript_frame(draw, target_size,
                                      tuple(max(0, v - 28) for v in gold_c))
            elif border_sty == "gold_block":
                draw_gold_border(draw, target_size)
            elif any(k in (visual_prompt or "").lower() for k in
                     ["gold", "golden", "border", "corner", "ornament", "frame",
                      "filigree", "gilded"]):
                draw_corner_filigree(draw, target_size, gold_c, length=85)

        else:
            # ── Route B: PIL Fallback ──────────────────────────────────────
            overrides  = overrides  # already computed above
            is_light   = overrides.get("is_light_bg", False)
            palette    = CUSTOM_TEXT_LIGHT if is_light else CUSTOM_TEXT_DARK
            material   = overrides.get("material",   "none")
            atmosphere = overrides.get("atmosphere", "none")
            border_sty = overrides.get("border_style", "none")
            p_type     = overrides.get("pattern_type", "none")
            g_type     = overrides.get("gradient_type", "radial")
            intensity  = float(overrides.get("intensity", 0.80))
            accent     = [int(v) for v in overrides.get("accent_rgb", [200, 196, 216])]
            bg_start   = tuple(int(v) for v in overrides["bg_start_rgb"])
            bg_end     = tuple(int(v) for v in overrides["bg_end_rgb"])
            p_rgba     = tuple(int(v) for v in overrides.get("pattern_color_rgba",
                                                             [255, 255, 255, 0]))
            glow_rgba  = tuple(int(v) for v in overrides.get("glow_color_rgba",
                                                             [255, 245, 220, 50]))
            v_int      = float(overrides.get("vignette", 0.70))

            print(f"🏗️  PIL Fallback:  mat={material}  atm={atmosphere}  bdr={border_sty}")
            print(f"   bg: {bg_start}→{bg_end}  p={p_type}  glow_a={glow_rgba[3]}")

            # Layer 1: Base gradient
            bg   = Image.new("RGB", target_size, bg_end)
            draw = ImageDraw.Draw(bg)
            if g_type == "radial":
                draw_radial_gradient(draw, target_size, bg_start, bg_end)

            # Layer 2: Material texture
            if material == "marble":
                draw_radial_gradient(draw, target_size, bg_start, bg_end)
                bg = apply_marble_depth(bg, target_size, list(bg_start), intensity)
                draw = ImageDraw.Draw(bg)
            elif material in ("parchment", "manuscript", "paper"):
                draw_paper_texture(draw, target_size,
                                   base_color=tuple(int(v) for v in bg_start))
                bg   = apply_parchment_depth(bg, target_size, intensity)
                draw = ImageDraw.Draw(bg)

            # Patterns
            if p_type == "starry":
                draw_starry_noise(draw, target_size,
                                  density=max(0.0003, 0.0006 * intensity))
            elif p_type == "islamic":
                draw_islamic_pattern(draw, target_size, p_rgba)

            # Layer 3: Atmosphere
            glow_list = list(glow_rgba[:3])
            if atmosphere == "celestial":
                bg = apply_celestial_atmosphere(bg, target_size, glow_list, intensity)
            elif atmosphere == "moonlit":
                bg = apply_moonlit_atmosphere(bg, target_size, intensity)
            elif atmosphere in ("spiritual", "peaceful", "sacred"):
                bg = apply_spiritual_atmosphere(bg, target_size, glow_list, intensity * 0.88)
            draw = ImageDraw.Draw(bg)

            # Layer 4: Light source — center by default
            cx_s, cy_s = W // 2, H // 2
            light_col  = tuple(int(v) for v in glow_rgba[:3])
            bg = apply_light_source(bg, target_size, (cx_s, cy_s),
                                    light_col, int(W * 0.48), intensity * 0.65)
            draw = ImageDraw.Draw(bg)

            # Layer 5: Vignette
            bg   = apply_vignette(bg, intensity=v_int)
            draw = ImageDraw.Draw(bg)

            # Layer 6: Border
            gold_c = (min(255, accent[0] // 2 + 148),
                      min(255, int(accent[1] * 0.35 + 128)),
                      max(0,   int(accent[2] * 0.08 + 28)))
            if border_sty == "corner_filigree":
                draw_corner_filigree(draw, target_size, gold_c, length=80)
            elif border_sty == "manuscript":
                draw_manuscript_frame(draw, target_size,
                                      tuple(max(0, v - 28) for v in gold_c))
            elif border_sty == "gold_block":
                draw_gold_border(draw, target_size)

    # ── MODE: PRESET ──────────────────────────────────────────────────────────
    if mode == "preset":
        eff  = style if style in PRESET_CONFIGS else "quran"
        spec = PRESET_CONFIGS[eff]
        palette = PRESET_TEXT.get(eff, PRESET_TEXT["quran"])

        print(f"🏗️  Preset: '{eff}'")

        bg   = Image.new("RGB", target_size, spec["base"])
        draw = ImageDraw.Draw(bg)
        draw_radial_gradient(draw, target_size, spec["bg_start"], spec["bg_end"])

        # Pattern
        pat = spec.get("pattern", "none")
        if pat == "starry":
            draw_starry_noise(draw, target_size,
                              density=spec.get("pattern_density", 0.0006),
                              seed=42)
        elif pat == "paper":
            bg_c = tuple(int(v) for v in spec["bg_start"])
            draw_paper_texture(draw, target_size, base_color=bg_c)
        elif pat == "islamic":
            draw_islamic_pattern(draw, target_size, spec["pattern_col"])

        # Atmosphere (preset-specific)
        atm = spec.get("atmosphere")
        gc  = spec.get("glow")
        glow_rgba = gc

        if atm == "parchment":
            bg   = apply_parchment_depth(bg, target_size, 0.55)
            draw = ImageDraw.Draw(bg)
        elif atm == "celestial" and gc:
            bg   = apply_celestial_atmosphere(bg, target_size, list(gc[:3]), 0.85)
            draw = ImageDraw.Draw(bg)
        elif atm == "fajr_horizon":
            # Warm amber horizon glow at bottom
            hz_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
            hd = ImageDraw.Draw(hz_layer)
            hd.ellipse([100, H - 200, W - 100, H + 180], fill=(255, 180, 60, 22))
            hz_layer = hz_layer.filter(ImageFilter.GaussianBlur(48))
            bg = Image.alpha_composite(bg.convert("RGBA"), hz_layer).convert("RGB")
            draw = ImageDraw.Draw(bg)

        # Light source
        lpos = spec.get("light_pos", "center")
        if lpos == "center":
            lpos = (W // 2, H // 2)
        if lpos:
            lcol = spec.get("light_col", (255, 245, 220))
            lrad = spec.get("light_r", 400)
            bg   = apply_light_source(bg, target_size, lpos,
                                      lcol, lrad, intensity=0.60)
            draw = ImageDraw.Draw(bg)

        # Vignette
        bg   = apply_vignette(bg, intensity=spec["vignette"])
        draw = ImageDraw.Draw(bg)

        # Border
        bsty = spec.get("border", "none")
        if bsty == "gold_block":
            draw_gold_border(draw, target_size,
                             border_width=spec.get("border_w", 30))
        elif bsty == "corner_filigree":
            draw_corner_filigree(draw, target_size, (190, 158, 45), length=75)

        glow_rgba = spec.get("glow")

    # ── TEXT ZONE LAYOUT ─────────────────────────────────────────────────────
    # Generous zones: Reference (A) | Main Quote (B) | Supporting (C)
    v_pad   = 88
    zone_ws = [int(W * 0.68), int(W * 0.80), int(W * 0.72)]
    zone_ls = [18, 30, 20]
    gap_ab  = 68   # generous gap: Reference → Quote (holds separator + breathing)
    gap_bc  = 46   # Quote → Supporting

    draw_tmp = ImageDraw.Draw(bg)
    zone_data = []

    for i, seg in enumerate(segments):
        if i >= 3:
            break
        z_w, z_ls = zone_ws[i], zone_ls[i]
        col        = palette[i] if i < len(palette) else palette[-1]

        try:
            fnt = ImageFont.truetype(font_path, int(seg["size"]))
        except Exception:
            fnt = ImageFont.load_default()

        avg_cw    = seg["size"] * 0.54
        max_chars = max(10, int(z_w / max(1, avg_cw)))
        raw       = textwrap.wrap(str(seg["text"]), width=max_chars)
        if i == 0 and len(raw) > 2:
            raw = raw[:2]; raw[-1] = raw[-1].rstrip() + "…"

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

    # Optical centering
    total_h = sum(zd["block_h"] for zd in zone_data)
    if len(zone_data) > 1: total_h += gap_ab
    if len(zone_data) > 2: total_h += gap_bc
    start_y = max(v_pad, (H // 2) - (total_h // 2) - int(H * 0.03))
    print(f"📐 total_h={total_h}  start_y={start_y}")

    # Ornament colors
    g_rgba     = glow_rgba
    orn_col    = list(g_rgba[:3]) if g_rgba else [200, 162, 42]
    sep_col    = (min(255, int(orn_col[0] * 0.9)),
                  min(255, int(orn_col[1] * 0.9)),
                  min(255, int(orn_col[2] * 0.75)))

    # ── GLOW HALO UNDER ZONE B ────────────────────────────────────────────────
    bg_rgba = bg.convert("RGBA")
    if len(zone_data) > 1 and g_rgba:
        g_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
        gd      = ImageDraw.Draw(g_layer)
        ty_g    = start_y + zone_data[0]["block_h"] + gap_ab
        cx      = W // 2
        gr      = tuple(int(v) for v in g_rgba)
        for ln in zone_data[1]["lines"]:
            gd.text((cx, ty_g), ln["text"], font=zone_data[1]["font"],
                    fill=gr, anchor="mt")
            ty_g += ln["h"] + zone_data[1]["ls"]
        g_layer = g_layer.filter(ImageFilter.GaussianBlur(32))
        bg_rgba = Image.alpha_composite(bg_rgba, g_layer)

    # ── DRAWING PASS ─────────────────────────────────────────────────────────
    draw_out = ImageDraw.Draw(bg_rgba)
    cx       = W // 2
    y        = start_y

    try:
        orn_font = ImageFont.truetype(font_path, 18)
    except Exception:
        orn_font = ImageFont.load_default()

    for i, zd in enumerate(zone_data):
        col = zd["color"]

        # ── Adaptive shadow for this zone ────────────────────────────────────
        # Light text (white/gold) → dark drop-shadow
        # Dark text (black/brown) → subtle white halo
        is_light_text = (col[0] + col[1] + col[2]) > 440
        if is_light_text:
            shadow_fill = (0, 0, 0, 130)           # dark shadow behind light text
            shd_dx, shd_dy = 2, 2
        else:
            shadow_fill = (255, 255, 255, 100)      # soft white halo behind dark text
            shd_dx, shd_dy = -1, -1

        if i == 0:
            # ── Zone A: Reference — honored, calm, elevated ───────────────
            draw_top_ornament(draw_out, cx, y - 22, sep_col)
            # Soft glow layer (optional)
            if g_rgba and len(g_rgba) >= 4:
                soft_ref_col = (int(orn_col[0]), int(orn_col[1]),
                                int(orn_col[2]), min(255, int(g_rgba[3] * 0.30)))
                for ln in zd["lines"]:
                    draw_out.text((cx, y), ln["text"], font=zd["font"],
                                  fill=soft_ref_col, anchor="mt")
                    y += ln["h"] + zd["ls"]
                y = start_y
            # Shadow pass then actual reference text
            ty = start_y
            for ln in zd["lines"]:
                draw_out.text((cx + shd_dx, ty + shd_dy), ln["text"],
                              font=zd["font"], fill=shadow_fill, anchor="mt")
                fc = (int(col[0]), int(col[1]), int(col[2]), 188)
                draw_out.text((cx, ty), ln["text"], font=zd["font"],
                              fill=fc, anchor="mt")
                ty += ln["h"] + zd["ls"]
            y = ty - zd["ls"] + gap_ab
            sep_y = (start_y + zd["block_h"]) + gap_ab // 2
            draw_zone_separator(draw_out, cx, sep_y, sep_col)

        elif i == 1:
            # ── Zone B: Main Quote — prominent, readable ──────────────────
            ty = y
            for ln in zd["lines"]:
                # Shadow pass
                draw_out.text((cx + shd_dx, ty + shd_dy), ln["text"],
                              font=zd["font"], fill=shadow_fill, anchor="mt")
                # Main text
                draw_out.text((cx, ty), ln["text"], font=zd["font"],
                              fill=col, anchor="mt")
                ty += ln["h"] + zd["ls"]
            y = ty - zd["ls"] + gap_bc

        else:
            # ── Zone C: Supporting — quiet, readable ─────────────────────
            ty = y
            for ln in zd["lines"]:
                draw_out.text((cx + shd_dx, ty + shd_dy), ln["text"],
                              font=zd["font"], fill=shadow_fill, anchor="mt")
                fc = (int(col[0]), int(col[1]), int(col[2]), 215)
                draw_out.text((cx, ty), ln["text"], font=zd["font"],
                              fill=fc, anchor="mt")
                ty += ln["h"] + zd["ls"]
            y = ty - zd["ls"]

    # ── CINEMATIC POST ────────────────────────────────────────────────────────
    glow_list  = list(glow_rgba) if glow_rgba else None
    final_img  = apply_cinematic_layers(bg_rgba, glow_color=glow_list)

    filename   = f"qcard_{int(time.time() * 1000)}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    final_img.save(final_path, quality=95)

    print(f"✅ [v7.0] {filename}  (mode={mode} style={style})")
    print(f"{'═'*64}\n")
    return f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"


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
