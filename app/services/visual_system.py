"""
visual_system.py — Sabeel Studio Visual System Layer v1.0

Architecture:
  Raw user description
       ↓  interpret_prompt()
  VisualSpec  (structured, semantic, keyword-matched)
       ↓  compose_dalle_prompt()
  DALL-E background prompt  (always text-free, policy-enforced)
       ↓  (DALL-E call lives in image_renderer.py)
  Raw background image
       ↓  analyze_background()
  AnalysisResult  (brightness, detail, readability per zone)
       ↓  adapt_typography()
  TypographySpec  (text colors, shadows, dim layer)
       ↓  (text rendering in image_renderer.py)
  Final quote card

Islamic Trust Rule — enforced at every prompt composition step:
  DALL-E must NEVER be used as the source of Qur'an text, hadith text,
  Arabic calligraphy, or verse references.  The words 'Islamic', 'Arabic',
  'Qur'an', 'mosque', and 'quote card' are forbidden from DALL-E prompts
  because they reliably trigger calligraphy in DALL-E's output.
  All sacred text comes exclusively from the verified app overlay only.
"""

from __future__ import annotations
import os
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

try:
    from PIL import Image, ImageFilter
except ImportError:
    Image = None


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VisualSpec:
    """
    Structured representation of a visual card background request.
    Produced by interpret_prompt() from raw user text.
    Theme and all fields are determined by keyword matching — no AI needed.
    """
    theme:          str   = "custom"
    material:       str   = "none"
    lighting:       str   = "radial"
    mood:           str   = "contemplative"
    bg_start:       tuple = (22, 20, 26)
    bg_end:         tuple = (5, 4, 8)
    is_light_bg:    bool  = False
    accent:         tuple = (200, 195, 215)
    ornament_level: str   = "corner"   # none | minimal | corner | moderate | ornate
    detail_level:   str   = "medium"   # sparse | medium | rich
    center_clarity: str   = "clear"    # clear | moderate | textured


@dataclass
class AnalysisResult:
    """
    Result of analyzing a generated background image.
    Produced by analyze_background() directly from pixel data.
    """
    overall_brightness: float = 128.0
    center_brightness:  float = 128.0
    edge_brightness:    float = 128.0
    center_detail:      float = 0.0    # 0-1, higher = busier center
    readability_score:  float = 0.5    # 0-1, higher = more readable
    is_light:           bool  = False
    zone_a_brightness:  float = 128.0  # reference row (top 8-25%)
    zone_b_brightness:  float = 128.0  # main quote row (30-70%)
    zone_c_brightness:  float = 128.0  # support row (72-88%)
    needs_protection:   bool  = False  # center needs dim layer


@dataclass
class TypographySpec:
    """
    Typography choices derived from background analysis + VisualSpec theme.
    Produced by adapt_typography() from an AnalysisResult (+ optional spec).
    """
    ref_color:     tuple = (220, 178, 58)   # Zone A — reference/accent
    quote_color:   tuple = (252, 252, 250)  # Zone B — main quote
    support_color: tuple = (228, 226, 222)  # Zone C — support
    shadow_fill:   tuple = (0, 0, 0, 130)
    shadow_dx:     int   = 2
    shadow_dy:     int   = 2
    dim_layer:     bool  = False
    dim_color:     tuple = (0, 0, 0, 55)
    dim_radius:    int   = 90
    sep_color:     tuple = (188, 152, 50)   # zone separator ornament
    # Theme-aware extras — drive the glow halo color and orn_col in renderer
    glow_rgba:     tuple = (210, 175, 62, 65)  # halo behind Zone B (RGBA)
    orn_color:     tuple = (195, 162, 48)       # separator/ornament RGB
    ref_alpha:     int   = 185                  # Zone A text opacity (0–255)


# ─────────────────────────────────────────────────────────────────────────────
# THEME CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────

# (theme_name, trigger_keywords, priority) — higher priority wins on conflict
_THEME_KEYWORDS: List[tuple] = [
    # Sacred / Kaaba-inspired
    ("sacred_black",    ["kaaba", "kiswah", "cloth", "sacred black", "holy cloth",
                         "sacred fabric", "black cloth", "kaba"],              10),
    # Material — checked before color/atmosphere words
    ("marble",          ["marble", "granite"],                                   9),
    ("obsidian",        ["obsidian", "onyx", "volcanic glass"],                  9),
    ("parchment",       ["parchment", "papyrus", "manuscript", "vellum",
                         "aged paper", "scroll"],                                9),
    ("velvet",          ["velvet", "velvet ribbon", "plush fabric"],             8),
    # Atmosphere
    ("emerald_forest",  ["emerald forest", "forest emerald", "emerald woodland",
                         "forest", "woodland", "lush green", "jungle"],          7),
    ("cosmic",          ["cosmic", "galaxy", "nebula", "deep space"],            6),
    ("celestial",       ["celestial", "heavenly", "divine light",
                         "sacred light", "radiant sky"],                          5),
    ("moonlit",         ["moonlit", "moonlight", "lunar", "silver moon"],        5),
    ("starry",          ["starry", "star field", "stars", "night sky",
                         "midnight sky", "star-filled"],                          5),
    ("desert",          ["desert", "dune", "golden sand", "warm sand", "amber"], 4),
    ("navy",            ["navy", "deep blue", "sapphire", "midnight blue"],      4),
    ("charcoal",        ["charcoal", "dark grey", "deep grey", "gunmetal"],      4),
    # Fallback
    ("custom",          [],                                                       0),
]

# Background color per theme: (bg_start, bg_end, is_light, accent)
_PALETTES = {
    "sacred_black":   ([8, 6, 10],     [2, 2, 4],      False, [180, 148, 42]),
    "marble":         ([44, 41, 50],   [18, 16, 22],   False, [210, 205, 225]),
    "obsidian":       ([14, 10, 18],   [3, 2, 6],      False, [160, 125, 225]),
    "parchment":      ([248, 238, 210],[228, 218, 188], True,  [120, 90, 38]),
    "velvet":         ([28, 12, 55],   [8, 4, 24],     False, [195, 148, 255]),
    "emerald_forest": ([12, 48, 28],   [4, 18, 10],    False, [120, 210, 148]),
    "cosmic":         ([10, 12, 52],   [2, 4, 20],     False, [175, 198, 255]),
    "celestial":      ([14, 22, 75],   [3, 5, 24],     False, [198, 212, 255]),
    "moonlit":        ([18, 22, 62],   [6, 8, 26],     False, [175, 200, 250]),
    "starry":         ([8, 10, 32],    [2, 3, 12],     False, [195, 210, 255]),
    "desert":         ([56, 34, 8],    [24, 14, 3],    False, [220, 180, 88]),
    "navy":           ([10, 18, 66],   [3, 5, 27],     False, [138, 172, 250]),
    "charcoal":       ([38, 36, 42],   [15, 13, 18],   False, [205, 195, 218]),
    "custom":         ([22, 20, 26],   [5, 4, 8],      False, [200, 195, 215]),
}

_LIGHTING = {
    "sacred_black":   "minimal",
    "marble":         "center_soft",
    "obsidian":       "edge_only",
    "parchment":      "overhead",
    "velvet":         "center_soft",
    "emerald_forest": "overhead",
    "cosmic":         "radial",
    "celestial":      "radial",
    "moonlit":        "corner_top",
    "starry":         "radial",
    "desert":         "overhead",
    "navy":           "center_soft",
    "charcoal":       "center_soft",
    "custom":         "radial",
}

_ORNAMENT = {
    "sacred_black":   "minimal",
    "marble":         "corner",
    "obsidian":       "corner",
    "parchment":      "moderate",
    "velvet":         "corner",
    "emerald_forest": "minimal",
    "cosmic":         "none",
    "celestial":      "minimal",
    "moonlit":        "minimal",
    "starry":         "none",
    "desert":         "corner",
    "navy":           "corner",
    "charcoal":       "corner",
    "custom":         "corner",
}

_MOOD = {
    "sacred_black":   "sacred",
    "marble":         "contemplative",
    "obsidian":       "majestic",
    "parchment":      "peaceful",
    "velvet":         "majestic",
    "emerald_forest": "peaceful",
    "cosmic":         "celestial",
    "celestial":      "celestial",
    "moonlit":        "contemplative",
    "starry":         "celestial",
    "desert":         "contemplative",
    "navy":           "majestic",
    "charcoal":       "contemplative",
    "custom":         "contemplative",
}


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND POLICY ENGINE
# Policy = theme-specific DALL-E prompt clause (what to render)
# These describe ONLY what the image should look like visually.
# They never mention 'Islamic', 'Arabic', 'Qur'an', 'mosque', or 'quote card'.
# ─────────────────────────────────────────────────────────────────────────────

_POLICIES = {
    "sacred_black": (
        "Deep matte black surface with very subtle fabric-like weave texture, "
        "like dense woven cloth in near-total darkness. "
        "Profound silence and power — almost no detail, purely tonal. "
        "One extremely faint, thin gold geometric line at a single corner only. "
        "Center completely empty and dark. No pattern, no noise. "
        "Absolute sacred stillness."
    ),
    "marble": (
        "Dark sophisticated marble stone surface with clearly visible sinuous "
        "natural veins branching organically. "
        "Veins concentrated toward edges and corners, center zone smooth and calm. "
        "Polished surface with subtle specular highlight at center. "
        "Very thin delicate geometric gold filigree lines at corners only. "
        "Cinematic lighting from slightly above center."
    ),
    "obsidian": (
        "Deep obsidian volcanic glass surface, near-perfect darkness. "
        "Subtle iridescent light reflection visible only at extreme edges. "
        "Faint blue-purple edge glow suggesting depth and mystery. "
        "Absolutely no pattern, no veins — pure geological darkness. "
        "Center held in deep shadow, no detail."
    ),
    "parchment": (
        "Aged manuscript parchment surface, warm ivory-amber tones, "
        "naturally non-uniform surface with subtle grain. "
        "Slightly darker at corners and edges suggesting age. "
        "Center smooth and uniformly warm, lighter than edges. "
        "Thin elegant gold geometric border lines at outer edge only. "
        "Warm overhead amber light illuminating the surface."
    ),
    "velvet": (
        "Rich deep-colored velvet-like matte surface, "
        "smooth soft-focus with deep color saturation. "
        "Heavy vignette from center outward — edges darker. "
        "Minimal surface detail, tactile cloth quality. "
        "Very slight light reflection at center only."
    ),
    "emerald_forest": (
        "Deep emerald-green forest atmosphere, dense dark tree canopy above. "
        "Soft shafts of light piercing from above through mist. "
        "Dark organic green textures concentrated at edges. "
        "Center region bathed in diffused soft green light — clear and usable. "
        "No defined leaf or tree objects, purely atmospheric depth and mist. "
        "Serene, still, contemplative natural mood."
    ),
    "cosmic": (
        "Vast deep space atmosphere, scattered distant stars at outer regions only. "
        "Rich indigo-black void with very soft nebula haze at edges. "
        "Calm, not chaotic — absolutely no bright star clusters in center. "
        "Center region intentionally dark and serene. "
        "Infinite atmospheric depth. Contemplative scale."
    ),
    "celestial": (
        "Radiant warm light descending from above-center, "
        "divine light source creating soft circular glow. "
        "Light diffuses and falls off gently toward edges. "
        "Deep background color behind the light source. "
        "Center region gently illuminated but not overexposed. "
        "Peaceful, heavenly, lifting mood."
    ),
    "moonlit": (
        "Moonlit nocturnal scene bathed in cool silver-blue ambient light "
        "entering from upper-left corner. "
        "Deep dark background with soft moonlight casting atmosphere. "
        "Center visible in calm ambient moonlight. "
        "Serene, quiet, reflective nocturnal mood."
    ),
    "starry": (
        "Soft star field background, stars of varying brightness. "
        "Stars concentrated at outer regions — fewer near center intentionally. "
        "Deep dark void background. Calm, not chaotic, not a busy nebula. "
        "Center region darker and cleaner for readability. "
        "Atmospheric depth, no foreground objects."
    ),
    "desert": (
        "Warm expansive desert environment with rich golden amber tones. "
        "Subtle dune textures visible at bottom edge only. "
        "Open warm sky above, light source high and warm. "
        "Center flooded with ethereal warm desert light. "
        "Timeless, vast, contemplative atmosphere."
    ),
    "navy": (
        "Deep dignified navy blue atmosphere, rich oceanic depth. "
        "Subtle tonal variation from slightly lighter center to darker edges. "
        "Very faint warm glow from above-center — not a spotlight, just a presence. "
        "No patterns, purely tonal depth."
    ),
    "charcoal": (
        "Deep charcoal grey surface with very fine grain texture throughout. "
        "Slight tonal variation — not flat, has dimensional depth. "
        "Slightly lighter at center, naturally darker at edges. "
        "Clean, modern, dignified material presence."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT INTERPRETER
# ─────────────────────────────────────────────────────────────────────────────

def interpret_prompt(raw: str) -> VisualSpec:
    """
    Convert a raw user description into a structured VisualSpec.
    Uses exclusively keyword matching — no AI, no network calls.
    This ensures deterministic, safe, consistent interpretation.

    Examples:
      "emerald forest"                      → theme=emerald_forest
      "warm parchment with gold geometry"   → theme=parchment, ornament=moderate
      "charcoal marble with celestial glow" → theme=marble, lighting=center_soft
      "sacred Kaaba-inspired cloth"         → theme=sacred_black
    """
    p = raw.lower().strip()

    # 1. Detect theme by keyword priority (highest priority wins)
    theme = "custom"
    for t_name, keywords, _ in sorted(_THEME_KEYWORDS, key=lambda x: -x[2]):
        if any(kw in p for kw in keywords):
            theme = t_name
            break

    # 2. Get base palette from theme
    palette_entry = _PALETTES.get(theme, _PALETTES["custom"])
    bg_start, bg_end, is_light, accent = palette_entry

    # 3. For custom/mixed themes, refine palette from compound keywords
    #    (e.g. "charcoal marble" → charcoal wins as the darker material)
    if theme == "custom":
        if "charcoal" in p:
            bg_start, bg_end = [38, 36, 42], [15, 13, 18]
        elif "emerald" in p or "jade" in p:
            bg_start, bg_end, is_light, accent = [0, 72, 38], [0, 24, 14], False, [115, 222, 148]
        elif "navy" in p or "midnight blue" in p:
            bg_start, bg_end = [10, 18, 66], [3, 5, 27]
        elif "dark" in p or "black" in p:
            bg_start, bg_end = [18, 16, 22], [4, 4, 6]

    # 4. Detect material (may override theme material)
    material = "none"
    if any(k in p for k in ["marble", "granite", "stone"]): material = "marble"
    elif any(k in p for k in ["parchment", "papyrus", "paper", "vellum", "manuscript"]): material = "parchment"
    elif any(k in p for k in ["velvet", "silk", "cloth", "fabric"]): material = "fabric"
    elif any(k in p for k in ["obsidian", "onyx"]): material = "stone"
    elif any(k in p for k in ["forest", "woodland", "leaf", "leaves"]): material = "organic"

    # 5. Detect lighting (prompt overrides theme default)
    lighting = _LIGHTING.get(theme, "radial")
    if any(k in p for k in ["center light", "center glow", "light center"]): lighting = "center_soft"
    if any(k in p for k in ["overhead", "from above", "top light"]):          lighting = "overhead"
    if any(k in p for k in ["corner light", "corner glow"]):                   lighting = "corner"
    if "dramatic" in p:                                                         lighting = "dramatic"
    if any(k in p for k in ["minimal light", "dark only", "no light"]):        lighting = "minimal"

    # 6. Detect mood (prompt overrides theme default)
    mood = _MOOD.get(theme, "contemplative")
    if any(k in p for k in ["peaceful", "calm", "serene", "tranquil"]):        mood = "peaceful"
    if any(k in p for k in ["majestic", "epic", "powerful", "striking"]):      mood = "majestic"
    if any(k in p for k in ["sacred", "holy", "divine", "reverent"]):          mood = "sacred"
    if any(k in p for k in ["celestial", "heavenly", "cosmic"]):               mood = "celestial"

    # 7. Detect ornament level
    ornament = _ORNAMENT.get(theme, "corner")
    if any(k in p for k in ["ornate", "detailed border", "arabesque",
                              "filigree", "intricate"]):                         ornament = "ornate"
    if any(k in p for k in ["minimal ornament", "clean", "spare", "simple"]):  ornament = "minimal"
    if any(k in p for k in ["no border", "borderless", "no ornament"]):        ornament = "none"
    if "gold" in p or "golden" in p:
        # Gold keyword implies at least corner treatment
        if ornament == "none": ornament = "minimal"

    # 8. Detect detail level
    detail = "medium"
    if any(k in p for k in ["minimal", "sparse", "bare", "very clean"]):       detail = "sparse"
    if any(k in p for k in ["rich", "luxurious", "detailed", "ornate",
                              "elaborate"]):                                      detail = "rich"

    # 9. Center clarity
    center = "clear"
    if any(k in p for k in ["all over", "full texture", "full detail"]):       center = "textured"
    if "moderate" in p:                                                          center = "moderate"

    spec = VisualSpec(
        theme=theme,
        material=material,
        lighting=lighting,
        mood=mood,
        bg_start=tuple(int(v) for v in bg_start),
        bg_end=tuple(int(v) for v in bg_end),
        is_light_bg=is_light,
        accent=tuple(int(v) for v in accent),
        ornament_level=ornament,
        detail_level=detail,
        center_clarity=center,
    )
    print(f"\n🔍 [VisualSpec] theme={theme}  mat={material}  light={lighting}  "
          f"mood={mood}  orn={ornament}  light_bg={is_light}")
    return spec


# ─────────────────────────────────────────────────────────────────────────────
# DALL-E PROMPT COMPOSER
# ─────────────────────────────────────────────────────────────────────────────

# Hard constraints — ALWAYS first in the prompt for maximum token-weight.
# Uses ALL-CAPS and plain English synonyms, never 'Arabic' or 'Islamic'
# (those words reliably trigger calligraphy in DALL-E regardless of negation).
_HARD_CONSTRAINTS = (
    "NO CALLIGRAPHY. NO SCRIPT. NO LETTERS. NO TEXT. NO WRITING OF ANY KIND. "
    "Zero glyphs, zero characters, zero lettering, zero symbols, zero inscriptions. "
    "No brush-stroke patterns resembling written language. "
    "No decorative elements that resemble alphabet characters. "
    "Only pure texture, atmosphere, light, and abstract geometric ornament."
)

# Composition rule — maintains center clarity for text overlay
_COMPOSITION = (
    "Composition discipline: all fine detail, texture richness, and ornamental "
    "elements are pushed to the outer 25% of the image (edges and corners). "
    "The central 50% must be intentionally calm, smooth, and unoccupied — "
    "a pristine open plate for digital text compositing."
)

_QUALITY = (
    "Premium photorealistic quality. "
    "Cinematic 4K detail. "
    "Fine digital art. "
    "Square format 1:1."
)

_LIGHTING_CLAUSES = {
    "radial":       "Soft light radiating gently from center, fading toward edges.",
    "overhead":     "Warm atmospheric light descending naturally from above.",
    "center_soft":  "Very gentle soft-focus glow at center, edges darker and richer.",
    "corner":       "Directional ambient light entering from upper-right corner.",
    "corner_top":   "Cool silvery light from upper-left corner.",
    "edge_only":    "Light exists only at extreme edges — center held in deep shadow.",
    "minimal":      "Nearly lightless — only the barest textural hint in near-darkness.",
    "dramatic":     "Strong directional light, marked contrast between light and shadow.",
}


def compose_dalle_prompt(spec: VisualSpec, raw_prompt: str = "") -> str:
    """
    Converts a VisualSpec into a safe, structured DALL-E background prompt.

    Token order strategy (DALL-E weights first tokens most heavily):
      1. Hard constraints     — NO CALLIGRAPHY / NO TEXT (must dominate)
      2. Frame descriptor     — 'Abstract texture background plate'
      3. Theme policy         — what specifically to render
      4. Lighting clause      — direction and quality of light
      5. Composition rule     — center must stay clear
      6. Quality directives   — premium, photorealistic, cinematic

    Nothing in this prompt may reference: Islamic, Arabic, mosque, Qur'an,
    calligraphy, quote card, or any religious text system.
    """
    policy = _POLICIES.get(spec.theme)
    if not policy:
        # For custom/unknown themes, describe the raw material directly
        policy = (
            f"{raw_prompt}. "
            "Premium material texture and atmospheric depth. "
            "Subtle geometric ornament at edges and corners only."
        )

    lighting_clause = _LIGHTING_CLAUSES.get(spec.lighting,
                                            "Soft diffused ambient lighting.")

    return (
        f"{_HARD_CONSTRAINTS} "
        "Abstract texture background plate for digital photo compositing. "
        f"{policy} "
        f"Lighting: {lighting_clause} "
        f"{_COMPOSITION} "
        f"{_QUALITY}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND ANALYZER
# ─────────────────────────────────────────────────────────────────────────────

def _zone_brightness(image, size: tuple,
                     y1f: float, y2f: float,
                     x1f: float = 0.10, x2f: float = 0.90) -> float:
    """Average grayscale brightness of a rectangular image zone (0-255)."""
    W, H = size
    x1, y1 = int(W * x1f), int(H * y1f)
    x2, y2 = int(W * x2f), int(H * y2f)
    # Downsample significantly before computing — avoids O(n) over a megapixel
    crop = image.crop((x1, y1, x2, y2)).resize((32, 32))
    pixels = list(crop.convert("L").getdata())
    return sum(pixels) / len(pixels) if pixels else 128.0


def _detail_score(image, size: tuple,
                  y1f: float, y2f: float,
                  x1f: float = 0.15, x2f: float = 0.85) -> float:
    """
    Detail complexity score 0-1 for a zone. Uses std-dev of brightness.
    0 = perfectly flat/smooth.  1 = highly detailed / complex.
    """
    W, H = size
    x1, y1 = int(W * x1f), int(H * y1f)
    x2, y2 = int(W * x2f), int(H * y2f)
    # 48×48 downsample is enough to capture std-dev without megapixel cost
    crop = image.crop((x1, y1, x2, y2)).resize((48, 48))
    pixels = list(crop.convert("L").getdata())
    n = len(pixels)
    if n == 0:
        return 0.0
    mean = sum(pixels) / n
    variance = sum((px - mean) ** 2 for px in pixels) / n
    std_dev = variance ** 0.5
    # Normalize: std≈10 → flat (0.18),  std≈55 → very detailed (1.0)
    return min(1.0, std_dev / 55.0)


def analyze_background(image, size: tuple) -> AnalysisResult:
    """
    Analyze a rendered background image and return an AnalysisResult.

    All sampling uses small downsampled crops for speed.
    A 1080×1080 image is analyzed in < 50ms with this approach.

    Center detail > 0.35 or medium-brightness center → needs_protection = True,
    meaning a soft dim/brighten layer should be applied before text is drawn.
    """
    # Overall + zone brightnesses
    overall    = _zone_brightness(image, size, 0.0, 1.0)
    center_brt = _zone_brightness(image, size, 0.25, 0.75, 0.25, 0.75)
    edge_brt   = _zone_brightness(image, size, 0.0, 0.15)   # top strip

    zone_a = _zone_brightness(image, size, 0.08, 0.25)
    zone_b = _zone_brightness(image, size, 0.30, 0.70)
    zone_c = _zone_brightness(image, size, 0.72, 0.88)

    # Detail score of main quote zone
    center_detail = _detail_score(image, size, 0.30, 0.70)

    # Readability: low detail + clear brightness contrast = good readability
    brightness_contrast = abs(center_brt - 128) / 128.0
    readability = max(0.0, min(1.0, brightness_contrast * 1.4 - center_detail * 0.6))

    # Protection needed if center is busy OR mid-brightness (worst for readability)
    needs_protection = (
        center_detail > 0.32
        or (80 < center_brt < 172 and center_detail > 0.18)
    )

    result = AnalysisResult(
        overall_brightness=overall,
        center_brightness=center_brt,
        edge_brightness=edge_brt,
        center_detail=center_detail,
        readability_score=readability,
        is_light=(overall > 145),
        zone_a_brightness=zone_a,
        zone_b_brightness=zone_b,
        zone_c_brightness=zone_c,
        needs_protection=needs_protection,
    )
    print(f"\n📊 [Analyzer] overall={overall:.0f}  center={center_brt:.0f}  "
          f"detail={center_detail:.2f}  readable={readability:.2f}  "
          f"protect={needs_protection}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TYPOGRAPHY ADAPTATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────


# Per-theme text style presets — defines the glow halo, ornament color, and
# reference-line opacity for each visual theme. These create VISIBLE differences
# in how text looks across sacred_black vs parchment vs cosmic vs emerald etc.
_THEME_TEXT = {
    "sacred_black":   {"glow_rgba": (225, 182, 55, 95),  "orn_color": (210, 168, 42), "ref_alpha": 215},
    "marble":         {"glow_rgba": (228, 222, 248, 65),  "orn_color": (205, 198, 228), "ref_alpha": 190},
    "obsidian":       {"glow_rgba": (185, 152, 238, 78),  "orn_color": (178, 148, 232), "ref_alpha": 195},
    "parchment":      {"glow_rgba": (158, 124, 72, 32),   "orn_color": (108, 82, 40),   "ref_alpha": 160},
    "velvet":         {"glow_rgba": (205, 168, 255, 74),  "orn_color": (192, 158, 252), "ref_alpha": 192},
    "emerald_forest": {"glow_rgba": (108, 202, 148, 60),  "orn_color": (95, 192, 138),  "ref_alpha": 178},
    "cosmic":         {"glow_rgba": (172, 198, 255, 76),  "orn_color": (158, 188, 252), "ref_alpha": 192},
    "celestial":      {"glow_rgba": (255, 248, 215, 82),  "orn_color": (228, 198, 88),  "ref_alpha": 205},
    "moonlit":        {"glow_rgba": (182, 212, 255, 64),  "orn_color": (170, 200, 248), "ref_alpha": 180},
    "starry":         {"glow_rgba": (202, 218, 255, 70),  "orn_color": (188, 205, 252), "ref_alpha": 185},
    "desert":         {"glow_rgba": (235, 192, 88, 74),   "orn_color": (222, 180, 76),  "ref_alpha": 198},
    "navy":           {"glow_rgba": (215, 178, 68, 70),   "orn_color": (202, 168, 58),  "ref_alpha": 192},
    "charcoal":       {"glow_rgba": (238, 232, 218, 58),  "orn_color": (215, 208, 198), "ref_alpha": 182},
    "custom":         {"glow_rgba": (215, 178, 64, 68),   "orn_color": (198, 165, 50),  "ref_alpha": 182},
}

def _pick_text(brightness: float, accent: bool = False,
               theme: str = "custom") -> tuple:
    """
    Returns an RGB tuple that contrasts with the given background brightness.
    Also accounts for theme to produce warm/cool variants that feel on-brand.

    accent=True  → accent/reference line (gold on dark, mahogany on light)
    accent=False → body text

    Brightness ranges (0-255):
      <  90  → very dark       → white / warm gold accent
      90-145 → medium dark     → off-white / gold accent
     145-185 → medium bright   → dark brown / amber accent
      > 185  → very light      → near-black / deep mahogany
    """
    if brightness < 90:
        if accent:
            # Theme-tinted gold accent on very dark bg
            if theme in ("sacred_black", "desert", "celestial", "navy"):
                return (228, 185, 58)
            elif theme in ("marble", "charcoal", "obsidian"):
                return (218, 210, 235)   # platinum-silver
            elif theme in ("emerald_forest",):
                return (138, 218, 165)   # jade
            elif theme in ("cosmic", "moonlit", "starry"):
                return (185, 208, 255)   # stellar silver-blue
            elif theme == "velvet":
                return (210, 175, 255)   # soft violet
            return (225, 182, 58)        # default warm gold
        return (255, 255, 255)           # pure white body

    elif brightness < 145:
        if accent:
            if theme in ("sacred_black", "desert", "navy", "celestial"):
                return (218, 178, 52)
            elif theme in ("marble", "charcoal"):
                return (210, 205, 228)
            elif theme in ("emerald_forest",):
                return (128, 208, 158)
            elif theme in ("cosmic", "moonlit", "starry"):
                return (178, 200, 252)
            return (215, 172, 50)
        return (248, 248, 245)           # off-white body

    elif brightness < 185:
        # Medium-bright — dark text needed, but tinted to the theme
        if accent:
            if theme == "parchment":
                return (88, 62, 22)      # deep amber mahogany
            elif theme in ("desert",):
                return (95, 58, 12)
            elif theme in ("celestial", "moonlit"):
                return (42, 48, 95)      # deep indigo
            elif theme in ("emerald_forest",):
                return (18, 75, 42)      # deep forest green
            return (62, 42, 10)          # default dark amber
        # Body text: dark but tinted warm/cool per theme
        if theme == "parchment":
            return (28, 22, 12)          # warm near-black
        elif theme in ("marble", "charcoal"):
            return (18, 16, 22)          # cold near-black
        elif theme in ("celestial", "moonlit"):
            return (22, 20, 42)          # deep blue-black
        elif theme in ("emerald_forest",):
            return (12, 28, 18)          # forest dark
        return (22, 18, 12)              # neutral near-black

    else:
        # Very bright (parchment, bright sky)
        if accent:
            if theme == "parchment":
                return (75, 50, 12)      # rich mahogany
            elif theme in ("desert", "celestial"):
                return (85, 55, 8)
            return (52, 32, 6)
        if theme == "parchment":
            return (18, 14, 8)           # warm black on parchment
        return (12, 10, 8)               # neutral near-black


def adapt_typography(analysis: AnalysisResult, spec: 'VisualSpec' = None) -> TypographySpec:
    """
    Produce a TypographySpec from a background AnalysisResult.

    Rules:
    - Each zone gets its own color independently sampled → true zone adaptation
    - Gold accent avoided when Zone A is golden/medium-bright (would clash)
    - Dim layer activated when center is busy / mid-brightness
    - Shadow direction based on whether text is light or dark
    - Separator uses gold on dark, mahogany on light
    """
    theme_str  = getattr(spec, 'theme', 'custom') if spec else 'custom'
    ref_c      = _pick_text(analysis.zone_a_brightness, accent=True,  theme=theme_str)
    quote_c    = _pick_text(analysis.zone_b_brightness, accent=False, theme=theme_str)
    support_c  = _pick_text(analysis.zone_c_brightness, accent=False, theme=theme_str)

    # If accent color would clash with a medium-light bg, deepen it
    if 145 < analysis.zone_a_brightness < 195:
        ref_c = _pick_text(analysis.zone_a_brightness, accent=True, theme=theme_str)

    # Shadow: dark offset for light text, white halo for dark text
    is_light_text = (quote_c[0] + quote_c[1] + quote_c[2]) > 440
    if is_light_text:
        shadow_fill = (0, 0, 0, 140)
        shd_dx, shd_dy = 2, 2
    else:
        shadow_fill = (255, 255, 255, 100)
        shd_dx, shd_dy = -1, -1

    # Dim/protect layer
    # For dark bg (light text): darken center slightly to help white text pop.
    # For light bg (dark text): also darken slightly so dark text pops against
    #   a uniform, controlled tone rather than busy texture.
    dim_layer = analysis.needs_protection
    if analysis.is_light:
        dim_color = (0, 0, 0, 38)   # gentle darkening on bright bg for dark text
    else:
        dim_color = (0, 0, 0, 58)   # stronger darkening on dark bg for light text

    # Zone separator ornament color — theme-tinted
    if analysis.is_light:
        sep_color = (88, 62, 18)  # dark mahogany on light bgs
    else:
        # Use orn_color from t_style but as a 3-tuple
        sep_color = (188, 152, 50)  # will be overridden by orn_color below

    # Theme-aware glow + ornament colors
    theme_key  = getattr(spec, "theme", "custom") if spec else "custom"
    t_style    = _THEME_TEXT.get(theme_key, _THEME_TEXT["custom"])
    glow_rgba  = t_style["glow_rgba"]
    orn_color  = t_style["orn_color"]
    ref_alpha  = t_style["ref_alpha"]

    typo = TypographySpec(
        ref_color=ref_c,
        quote_color=quote_c,
        support_color=support_c,
        shadow_fill=shadow_fill,
        shadow_dx=shd_dx,
        shadow_dy=shd_dy,
        dim_layer=dim_layer,
        dim_color=dim_color,
        dim_radius=90,
        sep_color=sep_color,
        glow_rgba=glow_rgba,
        orn_color=orn_color,
        ref_alpha=ref_alpha,
    )
    print(f"✏️  [Typography] theme={theme_key}  ref={ref_c}  quote={quote_c}  "
          f"glow={glow_rgba[:3]}α={glow_rgba[3]}  dim={dim_layer}")
    return typo


# ─────────────────────────────────────────────────────────────────────────────
# CACHE MANAGER
# Cache key is based on: theme + material + lighting + mood + ornament_level
# This means semantically identical prompts (same theme, different wording)
# will naturally share cached backgrounds.
# ─────────────────────────────────────────────────────────────────────────────

def spec_cache_key(spec: VisualSpec) -> str:
    """Stable 12-char hash of the semantic content of a VisualSpec."""
    key_str = (f"{spec.theme}|{spec.material}|{spec.lighting}|"
               f"{spec.mood}|{spec.ornament_level}|{spec.detail_level}")
    return hashlib.md5(key_str.encode()).hexdigest()[:12]


def load_bg_cache(spec: VisualSpec, cache_dir: str):
    """
    Load a background from the semantic spec cache.
    Returns PIL Image or None.
    """
    key  = spec_cache_key(spec)
    path = os.path.join(cache_dir, f"vsbg_{key}.jpg")
    if os.path.exists(path):
        try:
            if Image is None:
                return None
            img = Image.open(path).convert("RGB")
            print(f"⚡ [Cache] Spec HIT vsbg_{key}  (theme={spec.theme})")
            return img
        except Exception:
            pass
    return None


def save_bg_cache(image, spec: VisualSpec, cache_dir: str) -> None:
    """Persist a generated background to the semantic spec cache."""
    if Image is None:
        return
    try:
        os.makedirs(cache_dir, exist_ok=True)
        key  = spec_cache_key(spec)
        path = os.path.join(cache_dir, f"vsbg_{key}.jpg")
        image.save(path, quality=92)
        print(f"💾 [Cache] Saved vsbg_{key}  (theme={spec.theme})")
    except Exception as e:
        print(f"⚠️  [Cache] Save failed: {e}")
