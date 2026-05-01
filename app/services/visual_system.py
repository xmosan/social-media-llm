import os
import re
import random
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
    variation_traits: dict = field(default_factory=dict) # NEW: tracks randomized traits for caching


@dataclass
class AnalysisResult:
    """
    Result of analyzing a generated background image.
    Produced by analyze_background() directly from pixel data.

    palette_mode: "light" | "dark" | "warm" | "cool" | "green" | "mixed"
    readability_risk: "low" | "medium" | "high"
    typography_mode: "LIGHT" | "DARK" | "MID_LIGHT" | "MID_DARK"
    """
    overall_brightness: float = 128.0
    center_brightness:  float = 128.0
    edge_brightness:    float = 128.0
    center_detail:      float = 0.0    # 0-1, higher = busier center
    center_contrast:    float = 0.5    # 0-1, higher = more contrast headroom
    readability_score:  float = 0.5    # 0-1, higher = more readable
    is_light:           bool  = False
    zone_a_brightness:  float = 128.0  # reference row (top 8-25%)
    zone_b_brightness:  float = 128.0  # main quote row (30-70%)
    zone_c_brightness:  float = 128.0  # support row (72-88%)
    zone_a_detail:      float = 0.0
    zone_b_detail:      float = 0.0
    zone_c_detail:      float = 0.0
    needs_protection:   bool  = False  # center needs dim layer
    palette_mode:       str   = "dark"  # dominant color character
    readability_risk:   str   = "low"   # low | medium | high
    typography_mode:    str   = "DARK"  # LIGHT | DARK | MID_LIGHT | MID_DARK
    dominant_hue:       str   = "neutral"  # warm | cool | green | neutral


# ─────────────────────────────────────────────────────────────────────────────
# STYLE TOKENS — Named palettes for each typography mode
# ─────────────────────────────────────────────────────────────────────────────

# LIGHT_MODE: bright/parchment backgrounds → dark grounded text

_LIGHT_MODE = {
    "main":       (47,  36,  25),    # #2F2419 — deep warm brown
    "support":    (90,  71,  50),    # #5A4732 — medium warm brown
    "reference":  (140, 106, 47),    # #8C6A2F — bronze/muted gold
    "shadow":     (255, 255, 255, 70),
    "shadow_dx":  -1, "shadow_dy": -1,
    "glow_rgba":  None,
    "orn_color":  (108, 82, 40),
    "sep_color":  (88,  62, 18),
    "ref_alpha":  158,
}

# DARK_MODE: dark/space backgrounds → warm luminous text
_DARK_MODE = {
    "main":       (245, 241, 232),   # #F5F1E8 — warm off-white
    "support":    (221, 214, 200),   # #DDD6C8 — dimmer off-white
    "reference":  (212, 175, 55),    # #D4AF37 — classic sacred gold
    "shadow":     (0,   0,   0,  148),
    "shadow_dx":  2,  "shadow_dy": 2,
    "glow_rgba":  (212, 175, 55, 75),
    "orn_color":  (195, 162, 48),
    "sep_color":  (188, 152, 50),
    "ref_alpha":  205,
}

# MID_LIGHT_MODE: medium-bright → lean dark (sky, golden hour)
_MID_LIGHT_MODE = {
    "main":       (34,  26,  15),    # near-black warm
    "support":    (72,  58,  38),    # medium warm brown
    "reference":  (110, 82,  30),    # muted gold-bronze
    "shadow":     (0,   0,   0,  110),
    "shadow_dx":  1,  "shadow_dy": 1,
    "glow_rgba":  None,
    "orn_color":  (120, 92, 38),
    "sep_color":  (100, 78, 30),
    "ref_alpha":  168,
}

# MID_DARK_MODE: medium-dark → lean light (marble, charcoal, deep forest)
_MID_DARK_MODE = {
    "main":       (248, 244, 236),   # near-white warm
    "support":    (228, 222, 210),   # soft warm grey
    "reference":  (205, 168, 52),    # warm gold medium
    "shadow":     (0,   0,   0,  130),
    "shadow_dx":  2,  "shadow_dy": 2,
    "glow_rgba":  (205, 168, 52, 60),
    "orn_color":  (195, 162, 48),
    "sep_color":  (182, 148, 46),
    "ref_alpha":  192,
}

# Theme-specific accent overrides (applied on top of mode colors for orn/glow)
_THEME_ACCENT_OVERRIDES = {
    "sacred_black":   {"reference": (228, 185, 58),  "glow_rgba": (228, 185, 58, 90),  "orn_color": (210, 168, 42)},
    "marble":         {"reference": (218, 210, 238),  "glow_rgba": (228, 222, 245, 62), "orn_color": (205, 198, 228)},
    "obsidian":       {"reference": (195, 162, 238),  "glow_rgba": (185, 150, 232, 72), "orn_color": (178, 148, 232)},
    "parchment":      {"reference": (140, 106, 47),   "glow_rgba": None,                "orn_color": (108,  82,  40)},
    "velvet":         {"reference": (210, 175, 255),  "glow_rgba": (205, 168, 255, 72), "orn_color": (192, 158, 252)},
    "emerald_forest": {"reference": (138, 218, 165),  "glow_rgba": (110, 202, 148, 58), "orn_color": (95,  192, 138)},
    "cosmic":         {"reference": (185, 208, 255),  "glow_rgba": (172, 198, 255, 74), "orn_color": (158, 188, 252)},
    "celestial":      {"reference": (228, 198, 88),   "glow_rgba": (255, 248, 215, 80), "orn_color": (228, 198, 88)},
    "moonlit":        {"reference": (178, 202, 250),  "glow_rgba": (182, 212, 255, 62), "orn_color": (170, 200, 248)},
    "starry":         {"reference": (188, 205, 255),  "glow_rgba": (200, 218, 255, 68), "orn_color": (188, 205, 252)},
    "desert":         {"reference": (228, 185, 78),   "glow_rgba": (235, 192, 88,  72), "orn_color": (222, 180, 76)},
    "navy":           {"reference": (215, 178, 68),   "glow_rgba": (215, 178, 68,  68), "orn_color": (202, 168, 58)},
    "charcoal":       {"reference": (220, 215, 205),  "glow_rgba": (238, 232, 218, 55), "orn_color": (215, 208, 198)},
}


@dataclass
class TextStyleSpec:
    """Interpreted aesthetic intent for the text overlay."""
    bucket:            str   = "Minimal"
    font_family:       str   = "Sans"
    weight:            str   = "Regular"
    italic:            bool  = False
    uppercase:         bool  = False
    line_spacing:      float = 1.3
    letter_spacing:    int   = 0
    alignment:         str   = "Center"
    v_placement:       str   = "Center"
    horiz_offset:      int   = 0
    ornament_level:    str   = "Minimal"
    accent_color:      str   = "Gold"
    experimental:      bool  = False
    glossy:            bool  = False # NEW: Frosted glass effect
    has_shadow:        bool  = True
    size_ratios:       dict  = field(default_factory=lambda: {"verse": 0.5, "quote": 1.0, "reflection": 0.7})
    layout_mode:       str   = "Stack" # Stack | Editorial | Split

@dataclass
class ZoneStyle:
    """Styling settings for an individual text zone (A, B, or C)."""
    color: tuple
    opacity: float = 1.0
    shadow_fill: tuple = (0, 0, 0, 128)
    shadow_dx: int = 1
    shadow_dy: int = 1
    glow_style: str = "none"
    glossy: bool = False
    # Legacy dim fields kept for signature compatibility but ignored in v8.0
    dim_layer: bool = False
    dim_color: tuple = (0, 0, 0, 0)
    dim_radius: int = 0

@dataclass
class TypographySpec:
    """Final validated spec for the renderer."""
    readability_score: float
    top: ZoneStyle
    main: ZoneStyle
    sub: ZoneStyle
    typography_mode: str = "DARK"
    readability_risk: str = "low"
    has_glow: bool = False
    glow_rgba: tuple = None
    ref_color: tuple = (255, 255, 255)
    quote_color: tuple = (255, 255, 255)
    support_color: tuple = (255, 255, 255)
    glossy: bool = False
    # Atmospheric Halo / Shaping
    halo_radius: int = 0
    halo_opacity: int = 0
    halo_color: tuple = (0, 0, 0, 0)
    top_band_enabled: bool = False
    top_band_alpha: int = 0
    top_band_color: tuple = (0, 0, 0, 0)
    show_reference: bool = True
    sep_color: tuple = (255, 255, 255)
    orn_color: tuple = (255, 255, 255)
    text_style: TextStyleSpec = field(default_factory=TextStyleSpec)


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
    "Composition: subject elements concentrated ONLY at the corners and edges. "
    "The central zone must be a natural light clearing with organic depth-of-field. "
    "Allow background colors to melt into a soft-focus bokeh effect in the center 60%."
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



import random

_STYLE_FAMILIES = {
    "parchment_manuscript": {
        "core": (
            "BACKGROUND PLATE ONLY. STRICT COMPOSITION RULES: "
            "1. The center area (middle 60%) MUST be visually completely clean, soft, and extremely low-detail. "
            "2. The top area must have distinct but minimal texture for readability. "
            "3. All heavy detail, ornaments, frame elements, and textures MUST be pushed strictly toward the outer edges and corners. "
            "4. DO NOT place any patterns, geometry, noise, text, Arabic calligraphy, symbols, or letters anywhere near the center. "
            "Aged parchment manuscript, warm antique tones, elegant Islamic geometric influence."
        ),
        "traits": {
            "lighting": ["warm top-down light", "soft ambient glow", "subtle rim lighting", "faded directional sunbeam"],
            "frame_style": ["subtle corner ornaments", "faded border frame", "centered empty manuscript window", "clean edges with minimal grain"],
            "texture": ["heavy distressed aging", "smooth refined parchment grain", "soft fibrous paper texture", "cracked ancient edges"],
            "ornament": ["faint gold geometry hints", "floral arabesque whispers", "minimal elegant lines", "no ornaments, purely textural"],
            "glow": ["soft center warmth", "even flat illumination", "vignetted dark edges", "faint golden aura"]
        }
    },
    "emerald_forest": {
        "core": (
            "BACKGROUND PLATE ONLY. STRICT COMPOSITION RULES as above. "
            "Deep emerald forest background, atmospheric depth, calm spiritual mood, natural textures."
        ),
        "traits": {
            "scene_type": [
                "upward canopy looking through dense trees toward sky",
                "misty valley with distant mountain/tree silhouettes",
                "close foreground leaves and foliage with soft focus blur",
                "distant silhouette treeline against morning mist",
                "abstract fog and emerald light patterns in deep woodland",
                "ethereal clearing with soft dappled sunlight and moss"
            ],
            "lighting": ["soft diffused light rays", "dappled sunlight filtering down", "mystical twilight glow", "moonlit silver rim light"],
            "fog_density": ["heavy low-hanging mist", "subtle volumetric haze", "clear crisp air", "dense mystical fog around edges"],
            "foliage": ["dense framing trees", "minimal distant silhouettes", "soft out-of-focus foreground leaves", "ancient mossy textures"],
            "highlights": ["faint gold dust particles", "soft jade reflections", "luminous firefly sparks", "deep emerald gradients"]
        }
    },
    "sacred_black": {
        "core": (
            "BACKGROUND PLATE ONLY. STRICT COMPOSITION RULES as above. "
            "Deep matte black surface, fabric or stone inspired, restrained elegance, minimal composition."
        ),
        "traits": {
            "scene_type": ["infinite black void", "minimalist fabric drape", "geometric stone shadow-play", "soft radial pulse of light"],
            "lighting": ["soft gold edge light", "faint silver rim glow", "pure pitch black shadow focus", "subtle warm amber under-lighting"],
            "glow": ["faint radial center glow", "pitch dark center with edge gradients", "soft halo effect", "completely matte flat absorption"],
            "texture": ["subtle fabric weave visibility", "smooth obsidian stone", "dark velvet softness", "slight brushed metal micro-texture"],
            "framing": ["geometric framing minimalism", "invisible soft fade edges", "single thin gold line at bottom", "barely visible top cornice shadow"]
        }
    },
    "luxury_marble": {
        "core": (
            "BACKGROUND PLATE ONLY. STRICT COMPOSITION RULES as above. "
            "Dark charcoal or obsidian stone marble, elegant lighting, premium feel."
        ),
        "traits": {
            "scene_type": ["sweeping organic marble veins", "stratified stone layers", "cracked gold-fill veins", "smooth liquid-stone pooling"],
            "vein_direction": ["organic diagonal sweeping veins", "subtle horizontal stratification", "fractured chaotic gold veins", "minimal smooth pooling patterns"],
            "border": ["dark vignette corners", "gold inlay hints at edge", "clean modern borderless", "classic architectural bevel frame"],
            "reflection": ["high polished specular reflection", "soft matte honing", "wet-stone deep gloss", "diffused frosted surface"],
            "accents": ["heavy gold flake deposits", "platinum silver traces", "pure charcoal monotone", "copper oxidization warmth"],
            "illumination": ["strong top-down spotlight", "soft ambient wash", "dramatic side-lighting", "center-illuminated depth"]
        }
    },
    "celestial_night": {
        "core": (
            "BACKGROUND PLATE ONLY. STRICT COMPOSITION RULES as above. "
            "Deep night palette, peaceful stars, subtle cosmic mood."
        ),
        "traits": {
            "nebula": ["faint blue nebula dust", "warm emerald cosmic clouds", "dark purple void ripples", "no nebula, purely stark night"],
            "stars": ["dense varied starfield", "sparse distant pinpricks", "soft glowing clusters", "minimalist single bright anchor star"],
            "lighting": ["silver moonlight top-down", "dark gradient abyss", "soft turquoise horizon glow", "ethereal halo effect"],
            "haze": ["thick atmospheric optical haze", "crisp vacuum clarity", "soft floating light particles", "gossamer thin cloud wisp"]
        }
    },
    "obsidian_stone": {
        "core": "Deep obsidian volcanic glass surface, near-perfect darkness, restrained elegance.",
        "traits": {
            "scene_type": ["monolithic slab presence", "shattered geometric glass shards", "smooth liquid-like flow patterns", "abstract crystalline depth"],
            "texture": ["highly polished mirror surface", "raw fractured geological edges", "subtle iridescent sheen", "matte volcanic sand texture"],
            "lighting": ["extreme edge rim-light", "soft blue-purple internal glow", "dramatic single-point specular highlight", "minimalist ambient shadow"]
        }
    },
    "royal_velvet": {
        "core": "Rich deep-colored velvet-like matte surface, soft-focus depth, heavy color saturation.",
        "traits": {
            "scene_type": ["cascading fabric folds", "taut structured panel", "soft undulating waves", "abstract macro pile detail"],
            "pile": ["lush heavy velvet pile", "smooth silken sheen", "crushed textured fabric", "faint brushed directional grain"],
            "lighting": ["soft overhead diffuse wash", "deep shadow vignettes", "subtle golden rim highlights", "low-angle tactile illumination"]
        }
    },
    "sacred_desert": {
        "core": "Warm expansive desert environment, golden amber tones, timeless contemplative scale.",
        "traits": {
            "scene_type": ["towering dune ridge silhouettes", "vast open horizon line", "soft undulating sand ripples", "mirage-like heat haze distance"],
            "detail": ["fine wind-swept ripples", "ancient cracked desert floor", "scattered smooth basalt stones", "pure undisturbed sand sheets"],
            "lighting": ["low-angle golden hour sun", "cool blue hour twilight", "harsh midday high-contrast sun", "soft hazy dust-filtered light"]
        }
    },
    "premium_charcoal": {
        "core": "Deep charcoal grey surface, fine grain texture, modern dignified presence.",
        "traits": {
            "scene_type": ["brushed industrial panel", "soft charcoal sketch dust", "solid monolithic stone block", "layered stratified sedimentary grey"],
            "lighting": ["center spotlight glow", "cool horizontal rim light", "soft top-down ambient wash", "dramatic high-contrast shadow-play"]
        }
    }
}

def sanitize_for_dalle(prompt: str) -> str:
    """Removes keywords that reliably trigger calligraphy/mosques/text in DALL-E."""
    forbidden = {
        "islamic", "quran", "koran", "arabic", "muslim", "mosque", "masjid", 
        "script", "allah", "god", "calligraphy", "writing", "lettering", 
        "alphabet", "verses", "text", "glyphs", "symbols", "typography",
        "words", "characters", "sentence", "quote", "heading", "title",
        "label", "inscription", "signature", "watermark", "calligraphic"
    }
    words = re.split(r'(\s+|[,.!?])', prompt)
    safe_words = []
    for w in words:
        if not w: continue
        clean_w = w.lower().strip(",.!? \n\t")
        if clean_w in forbidden:
            continue
        safe_words.append(w)
    
    return "".join(safe_words).strip()

_VARIATION_HISTORY = {}

class VariationEngine:
    @staticmethod
    def generate(theme: str, user_prompt: str) -> dict:
        family_map = {
            "sacred_black": "sacred_black", "parchment": "parchment_manuscript",
            "marble": "premium_charcoal", "emerald_forest": "emerald_forest",
            "obsidian": "obsidian_stone", "velvet": "royal_velvet",
            "desert": "sacred_desert", "navy": "premium_charcoal",
            "charcoal": "premium_charcoal",
            "cosmic": "celestial_night", "dawn_sky": "celestial_night", "moonlit": "celestial_night"
        }
        family_key = family_map.get(theme, "sacred_black")
        if family_key not in _STYLE_FAMILIES: family_key = "sacred_black"

        fam = _STYLE_FAMILIES[family_key]
        traits_available = list(fam["traits"].keys())
        
        num_traits = random.randint(1, 2)
        selected_keys = random.sample(traits_available, num_traits)

        last_chosen = _VARIATION_HISTORY.get(family_key, {})
        chosen_traits_dict = {}
        for k in selected_keys:
            options = fam["traits"][k]
            last_val = last_chosen.get(k)
            valid_options = [o for o in options if o != last_val]
            if not valid_options: valid_options = options
            chosen_traits_dict[k] = random.choice(valid_options)
        
        _VARIATION_HISTORY[family_key] = chosen_traits_dict

        return {
            "family": family_key,
            "core_traits": fam["core"],
            "variation_traits": chosen_traits_dict
        }


# ───────────────────────────────────────────────────────────────────────────────
# PREMIUM SCENE PROMPT TEMPLATES
# Text-stage-first prompts for DALL-E/Gemini background generation.
# The central quiet zone is explicitly mandated before describing the environment.
# ───────────────────────────────────────────────────────────────────────────────

SCENE_PROMPT_TEMPLATES = {
    "sacred_script": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: A photorealistic macro study of premium parchment, fine paper grain, or authentic manuscript textures. "
            "The center MUST be a completely clean, calm, softly lit open space — the text stage. "
            "No clutter or texture in the center zone. Photorealistic 4K studio photography, museum-quality curation, minimalist and elegant. "
            "Believable lighting, no unnatural bloom or glowing objects. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Authentic aged manuscript paper surface, warm ivory tones, naturally non-uniform surface with subtle grain, professional top-down studio lighting.",
            "Smooth refined parchment with very subtle natural fiber texture, clean and minimalist, soft directional light from upper-left.",
            "Thick artisanal cotton paper macro shot, warm top-down lighting creating very subtle shadows on the deckled edges, center completely smooth.",
            "Minimalist clean archival paper surface, elegant restraint, barely visible fine texture, soft vignetted outer edges."
        ]
    },
    "midnight_oasis": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Cinematic, architectural night photography with deep atmospheric tones and realistic shadows. "
            "The center must be perfectly calm and quiet — the text stage. "
            "Photorealistic 4K photography, premium materials and architectural restraint. "
            "Believable lighting, no unnatural bloom or surreal glowing objects. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic dark architectural courtyard at night, bathed in cool silver-blue moonlight entering naturally from upper-left corner.",
            "Deep dark space with soft natural moonlight casting realistic shadows across a minimalist stone texture at the edges.",
            "Crisp, believable astrophotography over a minimalist dark horizon, scattered distant stars at extreme outer edges only, center a pure dark void.",
            "A quiet, realistic desert night, deep midnight blue sky gradient, subtle silhouette of real dunes at the very bottom edge."
        ]
    },
    "desert_glow": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: A high-end landscape editorial of a warm expansive desert environment. "
            "The center must be flooded with natural warm daylight, kept completely clear for text. "
            "Photorealistic 4K photography, real desert topography, natural golden hour lighting, believable atmospheric haze. "
            "1:1 square composition. Absolutely no text, no calligraphy."
        ),
        "variations": [
            "Photorealistic soft undulating sand ripples stretching to a vast open horizon line, natural warm sunlight.",
            "Low-angle golden hour sun casting long cinematic shadows across real smooth basalt stones at the extreme edges.",
            "Realistic high-contrast midday sun, pure undisturbed sand sheets, authentic warm light.",
            "Distant authentic dune ridge silhouettes at the bottom edge, soft natural dust-filtered sunlight above."
        ]
    },
    "luxury_editorial": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: A premium brand-campaign setup with sophisticated, realistic dark materials. "
            "The center must be perfectly calm, smooth, and quiet — the text stage. "
            "Photorealistic 4K studio photography, premium materials (marble, obsidian) and architectural restraint. "
            "Believable lighting, no unnatural bloom or surreal glowing objects. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Deep navy or obsidian stone surface with exquisite realistic gold inlay ornament at the extreme corners.",
            "Minimalist charcoal-black architectural environment with a single restrained studio key-light angled from one side.",
            "Photorealistic dark marble stone slab with natural, subtle veins branching organically only at the extreme edges.",
            "Rich deep-colored velvet fabric macro, soft-focus with authentic color saturation, natural textile drape, heavy vignette."
        ]
    },

    # ── Automation Style DNA Family Scenes ───────────────────────────────────
    # One entry per Style DNA family. 4+ variations ensure a fresh background
    # on every automated post, matching the Studio scene-variation behaviour.

    "sacred_black": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Extremely restrained macro fabric or stone photography. Absolute darkness — deep matte black or obsidian. "
            "The center must be perfectly calm and quiet, held in near-darkness. "
            "Photorealistic 4K photography, focus on tactile reality, minimalist and elegant. "
            "Believable lighting, no unnatural bloom or surreal glowing objects. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Pure matte black void with the faintest warm ambient light catching subtle surface texture at the extreme edges.",
            "Photorealistic obsidian volcanic glass slab, subtle sheen catching a single off-center authentic studio rim light.",
            "Deep velvet black fabric softly draped, natural fabric physics, catching a very faint edge-light at upper corners only.",
            "Smooth matte dark architectural stone slab, barely visible fine grain texture, realistic soft lighting from above.",
            "Realistic geometric shadow-play on monolithic dark stone, single thin metallic line inlay at the lower edge."
        ]
    },
    "emerald_forest": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Realistic nature photography of a deep emerald forest environment. "
            "The center must be an open clearing of soft natural diffused light — the text stage. "
            "Photorealistic 4K botanical detail, authentic woodland depth. "
            "Believable lighting, no unnatural bloom, mystical fog, or surreal glowing objects. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic upward view through dense authentic tree canopy — real leaves framing a soft misty natural sky at the center.",
            "Realistic morning valley with distant tree silhouettes at the horizon, natural morning mist in the center.",
            "Close macro foreground foliage extremely out of focus, center a blurred authentic emerald-green clearing.",
            "Ancient mossy forest floor macro photography, soft natural dappled sunlight filtering down in rays at the extreme edges only.",
            "Authentic twilight behind a dense treeline silhouette — cool natural ambient mood.",
            "Heavy natural low-hanging forest mist, dense dark evergreen foliage framing the edges."
        ]
    },
    "celestial_night": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Crisp, believable astrophotography or high-end architectural night view. "
            "The center must be calm and clear — a soft dark void for text. "
            "Photorealistic 4K photography, realistic infinite depth. "
            "Believable lighting, no unnatural nebula dust, glowing clouds, or optical haze. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Vast authentic deep indigo-black night sky, realistic scattered stars only at outer regions, center a dark clearing.",
            "Clean night sky photography, minimalist single bright anchor star off-center top.",
            "Realistic silver moonlight descending from above, cool natural horizon glow at the very base edge.",
            "Authentic dense starfield at corners fading to pure dark void at center — photorealistic atmospheric depth.",
            "Thin realistic cloud wisps across a deep purple night sky, clean atmospheric clarity, center clear.",
            "Crisp vacuum clarity astrophotography, sparse distant pinprick stars, pure gradient abyss."
        ]
    },
    "parchment_manuscript": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Photorealistic macro study of premium parchment or manuscript paper surface. "
            "The center must be a clean, softly lit manuscript window with minimal texture. "
            "Photorealistic 4K studio photography, premium archival materials, clean and elegant. "
            "Believable lighting, no unnatural bloom or chaotic ancient edges. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Premium aged parchment paper, warm amber-ivory tones, smooth center window, subtle authentic grain.",
            "Smooth refined artisanal paper grain, subtle fibrous texture, natural directional sunlight from upper-left.",
            "Warm top-down studio light on antique paper surface, very subtle and authentic blind deboss patterns at corners only.",
            "Elegant clean border frame of minimal authentic lines, center completely smooth warm ivory, soft vignetted edges.",
            "Warm natural illumination on archival paper, soft amber center warmth, clean dark vignetted outer frame."
        ]
    },
    "luxury_marble": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Photorealistic architectural stone slab — dark charcoal or obsidian marble. "
            "The center must be smooth and calm — the text stage, free of veining. "
            "Photorealistic 4K studio photography, premium materials and architectural restraint. "
            "Believable lighting, no unnatural bloom, glowing cracks, or surreal liquid-stone pooling. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic sweeping organic marble veins of dark charcoal, center naturally clear of heavy veining.",
            "Authentic stone slab with subtle gold inlay branching from corners toward edges, center pure matte stone.",
            "High polished specular obsidian marble slab, strong top-down studio spotlight, natural mineral deposits at edges.",
            "Authentic stratified stone layers of grey and platinum traces, clean architectural surface, clean center.",
            "Realistic minimal veins at extreme corners only, soft matte honed finish at center, natural dark vignette.",
            "Smooth dark monolithic stone surface, subtle natural oxidization warmth at outer regions, soft ambient wash."
        ]
    },
    "sacred_desert": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: A high-end landscape editorial of a vast, warm desert environment. "
            "The center must be flooded with natural cinematic daylight, completely clear for text. "
            "Photorealistic 4K photography, authentic sand textures, timeless scale. "
            "Believable lighting, no unnatural bloom or surreal glowing artifacts. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic towering dune ridge silhouettes at the very bottom edge, soft natural hazy golden light above.",
            "Vast authentic open horizon line with fine wind-swept sand ripples at extreme edges, natural warm center.",
            "Low-angle authentic golden hour sun, long cinematic shadows cast by scattered real basalt stones at corners only.",
            "Cool blue hour desert twilight photography, deep amber-blue gradient sky, undisturbed sand sheets at base edge.",
            "Realistic cracked dry earth at corners, natural heat haze distance, center a pure natural warm sky.",
            "Harsh midday high-contrast natural sun, pure undisturbed sand sheets, bright authentic warmth flooding the center."
        ]
    },

    # ── New Extended Family Scene Templates ───────────────────────────────────

    "royal_velvet": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Photorealistic macro photography of rich, heavy textile drapes. "
            "The center must be a calm, softly-lit focal clearing free of heavy folds. "
            "Photorealistic 4K studio photography, authentic light absorption and drape physics. "
            "Believable lighting, no unnatural bloom or surreal glowing objects. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic cascading deep burgundy velvet fabric folds at edges, center a smooth rich flat surface.",
            "Taut structured deep purple velvet upholstery panel, subtle authentic studio rim highlights at corners only.",
            "Soft realistic undulating indigo-navy fabric waves, faint brushed directional grain, heavy vignette at edges.",
            "Lush heavy velvet pile catching authentic overhead diffuse wash, deep royal blue, smooth center clearing.",
            "Crushed emerald velvet macro photography at outer frame, authentic tactile pile detail, clean center zone.",
            "Low-angle realistic studio illumination on deep wine-red fabric surface, natural shadow vignettes, center calm."
        ]
    },
    "midnight_ink": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: High-contrast, moody architectural minimalism in deep navy or midnight blue. "
            "The center must be perfectly smooth and quiet — a dark serene surface for text. "
            "Photorealistic 4K studio photography, matte premium dark surfaces, architectural restraint. "
            "Believable lighting, no unnatural bloom or gossamer highlights. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic deep navy atmosphere, faint natural tonal gradient from slightly lighter center to rich dark edges.",
            "Midnight blue monolithic architectural surface with barely visible fine grain, single restrained realistic side-light.",
            "Rich authentic navy depth, very faint natural ambient glow from above-center, purely tonal depth.",
            "Dark editorial charcoal-navy matte panel, cool realistic horizontal rim light from one side, strong center calm.",
            "Deep dignified navy surface, subtle authentic micro-sheen, soft center studio spotlight, dark corners.",
            "Layered dark blue-black architectural tonal depth, crisp subtle edge highlight, minimalist absence of detail."
        ]
    },
    "dawn_horizon": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Realistic early morning atmospheric photography of a soft dawn sky. "
            "The center must be filled with natural dawn light, perfectly clear for text. "
            "Photorealistic 4K photography, natural pre-dawn gradients. "
            "Believable lighting, no unnatural volumetric haze or surreal glowing clouds. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Authentic delicate blush pink and gold gradient sky fading from warm top to cool bottom, center natural dawn glow.",
            "Soft amber-rose realistic horizon line at the very base edge, above a vast clean sky, center flooded with natural light.",
            "Thin realistic cloud wisps at outer edges only, warm golden pre-dawn sunlight flooding the center.",
            "Layered authentic pastel dawn sky — coral, gold, and pale blue banding at far edges, center a pure clear sky.",
            "Soft natural morning atmosphere diffusing warm light across the entire frame, detail only at corners.",
            "Real early morning sky with the first hint of deep amber sun at the very base, pale natural center above."
        ]
    },
    "obsidian_stone": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Authentic geological macro photography of volcanic obsidian or deep polished stone. "
            "The center must be held in deep, calm shadow with only the barest presence of light. "
            "Photorealistic 4K studio photography, realistic specular highlights on polished black stone. "
            "Believable lighting, no unnatural bloom or internal blue-purple micro-glows. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic monolithic obsidian slab presence, smooth dark surface, extreme edge studio rim-light only.",
            "Real fractured volcanic glass shards concentrated at the outer corners, center pure dark void.",
            "Highly polished obsidian mirror surface, single realistic specular highlight at one edge, deep center.",
            "Raw authentic geological edges at extreme corners, matte volcanic sand texture, center calm darkness.",
            "Subtle natural sheen at edges of dark stone, soft realistic ambient shadow at center.",
            "Authentic macro photography of dark crystalline depth in stone, near-lightless center."
        ]
    },
    "ocean_depth": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Pristine, realistic underwater photography with natural light caustics and deep teal gradients. "
            "The center must be a calm, luminous aquatic clearing — the text stage. "
            "Photorealistic 4K photography, authentic oceanic depth. "
            "Believable lighting, no unnatural bloom or surreal bioluminescent glow. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic deep teal underwater atmosphere, soft natural diffused light rays descending from above, center calm.",
            "Vast dark authentic oceanic depth at edges, turquoise-teal light pool at center, infinite sense of scale.",
            "Realistic underwater surface — rich blue-green tones, faint natural caustic light patterns at outer regions only.",
            "Cool navy-to-teal natural gradient depth, single column of realistic soft light descending into center clearing.",
            "Dark deep ocean blue at corners, soft natural light radiating from the center.",
            "Serene authentic teal-blue gradient, deep at edges, pale luminous center, minimalist aquatic calm."
        ]
    },
    "warm_copper": {
        "base": (
            "BACKGROUND PLATE for a premium editorial quote card. "
            "Setting: Photorealistic macro photography of hammered or brushed metal surfaces — copper or bronze. "
            "The center must be a calm, warmly lit metallic clearing — smooth and inviting. "
            "Photorealistic 4K studio photography, authentic patina and studio lighting. "
            "Believable lighting, no unnatural bloom or surreal liquid bronze pooling. "
            "1:1 square composition. Absolutely no text, no calligraphy, no letters."
        ),
        "variations": [
            "Photorealistic burnished warm copper surface, soft overhead studio wash, fine metallic grain at edges, smooth center.",
            "Authentic aged bronze patina at outer corners — natural green-gold oxidization, warm amber burnished center clearing.",
            "Real hammered copper texture at extreme edges, warm directional light catching subtle facets, calm center.",
            "Smooth solid bronze surface, warm amber-gold light reflecting from a single realistic side source.",
            "Authentic antique copper surface with deep warm shadows at corners, single overhead warm studio spotlight at center.",
            "Rich photorealistic gold-copper gradient surface, deep bronze at edges, warm burnished amber glow at center."
        ]
    }
}

def compose_scene_prompt(scene_key: str, custom_direction: str = "") -> str:
    """Generates a scene prompt with internal variation and optional user direction."""
    template = SCENE_PROMPT_TEMPLATES.get(scene_key, SCENE_PROMPT_TEMPLATES["sacred_script"])
    base = template["base"]
    variation = random.choice(template["variations"])
    
    prompt = f"{base} Variation: {variation}."
    
    if custom_direction:
        safe_dir = sanitize_for_dalle(custom_direction)
        if safe_dir:
            prompt += f" Custom Refinement: {safe_dir}. (Ensure this refinement does not add any text or letters)."
            
    prompt += " FINAL MANDATE: NO TEXT. NO MESSAGE. ZERO WRITTEN CHARACTERS."
    return prompt

def compose_dalle_prompt(spec: VisualSpec, raw_prompt: str = "") -> str:
    v_data = VariationEngine.generate(spec.theme, raw_prompt)
    
    # Store the traits in the spec for cache key stability
    spec.variation_traits = v_data["variation_traits"]
    
    var_list = [f"{v}" for k, v in v_data["variation_traits"].items()]
    variations_str = ", ".join(var_list)
    
    # Sanitize user input to keep it visual, not semantic
    # Aggressively remove anything that looks like a request for text
    safe_user_input = sanitize_for_dalle(raw_prompt) if raw_prompt else ""
    
    # Architecture C: Leading with User Input + Randomized Traits
    # This ensures user's specific items (e.g. "small waterfall") are given max weight
    # but strictly nested within a "NO TEXT" shell.
    final_prompt = (
        f"{_HARD_CONSTRAINTS} "
        "IMAGE TYPE: PURE BACKGROUND PLATE. "
        f"Visual subject: {safe_user_input if safe_user_input else 'abstract landscape'}. "
        f"Material & Texture: {variations_str}. "
        f"{v_data['core_traits']} "
        f"Atmosphere & Mood: {spec.mood}. "
        f"{_COMPOSITION} "
        "FINAL MANDATE: THE OUTPUT MUST BE A TEXT-FREE IMAGE. "
        "NO TEXT. NO MESSAGE. NO QUOTES. NO LETTERS. NO CALLIGRAPHY. "
        "PURE VISUAL TEXTURE AND ATMOSPHERE ONLY. ZERO WRITTEN CHARACTERS."
    )
    print(f"\n🌪️ AUTO-VARIATION TRIGGERED [{v_data['family']}]: {v_data['variation_traits']}")
    return final_prompt


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

    # 0. Scene detection (highest priority — check before generic theme matching)
    if any(k in p for k in ["arch", "archway", "corridor", "arch stage", "mosque interior", "sacred hall", "light stage"]):
        theme = "arch_stage"
    elif any(k in p for k in ["manuscript", "desk", "scholar study", "candlelit", "ink vessel", "scrolls"]):
        theme = "manuscript"
    elif any(k in p for k in ["luxury panel", "obsidian panel", "navy panel", "editorial panel", "dark panel"]):
        theme = "luxury_panel"
    elif any(k in p for k in ["editorial", "minimal sacred", "magazine", "minimal editorial"]):
        theme = "editorial"
    else:
        # 1. Standard theme detection by keyword priority (highest priority wins)
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
# TEXT STYLE INTERPRETATION
# ─────────────────────────────────────────────────────────────────────────────

def interpret_text_style(raw: str, experimental: bool = False) -> TextStyleSpec:
    """Maps user text-style prompt to a structured TextStyleSpec."""
    p = (raw or "").lower().strip()
    spec = TextStyleSpec(experimental=experimental)
    
    # 1. Bucket Detection
    if any(k in p for k in ["editorial", "magazine", "luxury", "fashion"]):
        spec.bucket = "Editorial"
    elif any(k in p for k in ["manuscript", "sacred", "holy", "scroll", "ancient"]):
        spec.bucket = "Sacred Manuscript"
    elif any(k in p for k in ["bold", "poster", "strong", "impact", "heavy"]):
        spec.bucket = "Modern Bold"
    elif any(k in p for k in ["minimal", "clean", "simple", "quiet", "airy"]):
        spec.bucket = "Minimal"
    elif any(k in p for k in ["classic", "serif", "timeless"]):
        spec.bucket = "Classic Serif"
        
    # 2. Font Category
    if any(k in p for k in ["serif", "classic", "traditional", "manuscript", "elegant"]):
        spec.font_family = "Serif"
    elif any(k in p for k in ["modern", "sans", "clean", "minimal", "bold"]):
        spec.font_family = "Sans"
        
    # 3. Hierarchy & Weight
    if "delicate" in p or "thin" in p:
        spec.weight = "Light"
        spec.letter_spacing = 2
    elif "bold" in p or "heavy" in p or "impact" in p:
        spec.weight = "Bold"
        
    # 4. Alignment & Placement
    if "left" in p:
        spec.alignment = "Left"
    elif "right" in p:
        spec.alignment = "Right"
        
    if "top" in p or "upper" in p or "above" in p:
        spec.v_placement = "Top_Third"
    elif "bottom" in p or "below" in p or "lower" in p:
        spec.v_placement = "Bottom_Third"
        
    if "off-center" in p or "side" in p:
        if spec.alignment == "Center": spec.alignment = "Left"
        spec.horiz_offset = 80
        
    # 5. Accent Colors & Style
    if "gold" in p:
        spec.accent_color = "Gold"
        spec.ornament_level = "Minimal"
    elif "ivory" in p or "warm white" in p:
        spec.accent_color = "Ivory"
        
    if "italic" in p or "cursive" in p or "slanted" in p:
        spec.italic = True
    if "uppercase" in p or "all caps" in p:
        spec.uppercase = True
        
    # 6. Apply Bucket Multipliers
    if spec.bucket == "Editorial":
        spec.size_ratios = {"verse": 0.4, "quote": 1.0, "reflection": 0.6}
        spec.line_spacing = 1.05
        spec.letter_spacing = 12 # Substantial tracking for high-end look
        spec.layout_mode = "Editorial"
    elif spec.bucket == "Modern Bold":
        spec.size_ratios = {"verse": 0.45, "quote": 1.0, "reflection": 0.45}
        spec.weight = "Bold"
        spec.letter_spacing = 6
    elif spec.bucket == "Sacred Manuscript":
        spec.size_ratios = {"verse": 0.8, "quote": 1.0, "reflection": 0.9}
        spec.line_spacing = 1.4
        spec.font_family = "Serif"
        spec.italic = True
        
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
    "Composition: subject elements concentrated ONLY at the corners and edges. "
    "The central zone must be a natural light clearing with organic depth-of-field. "
    "Allow background colors to melt into a soft-focus bokeh effect in the center 60%."
)

# GEMINI SPECIFIC - High-fidelity material constraints
_GEMINI_STRICT_CONSTRAINTS = (
    "A pure material background plate focusing on texture, light, and atmosphere. "
    "Non-textual abstract surface. Cinematic depth. No characters or inscriptions. "
    "The image should be a pristine artistic ground for overlaying spiritual text."
)

_GEMINI_COMPOSITION = (
    "Composition: Intricate material detail and ornamental filigree are restricted ONLY to the outer edges. "
    "The central 60% of the frame must be a clean, atmospheric clearing. "
    "Center must have an organic, creamy bokeh transition avoiding any distinct shapes or lines. "
    "Zero subject matter in the center."
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




# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND ANALYZER
# ─────────────────────────────────────────────────────────────────────────────

def _sample_zone(image, size: tuple,
                 y1f: float, y2f: float,
                 x1f: float = 0.10, x2f: float = 0.90) -> dict:
    """
    Sample brightness, std-dev detail, and dominant hue of a rectangular zone.

    Returns:
        brightness  (float 0-255)
        detail      (float 0-1)  std-dev normalized
        avg_r, avg_g, avg_b  (float)
    """
    W, H = size
    x1, y1 = int(W * x1f), int(H * y1f)
    x2, y2 = int(W * x2f), int(H * y2f)
    crop = image.crop((x1, y1, x2, y2)).resize((48, 48))

    gray = list(crop.convert("L").getdata())
    n    = len(gray)
    brightness = sum(gray) / n if n else 128.0

    mean    = brightness
    std_dev = (sum((p - mean) ** 2 for p in gray) / n) ** 0.5 if n else 0.0
    detail  = min(1.0, std_dev / 52.0)

    rgb   = crop.convert("RGB").getdata()
    avg_r = sum(p[0] for p in rgb) / n if n else 128.0
    avg_g = sum(p[1] for p in rgb) / n if n else 128.0
    avg_b = sum(p[2] for p in rgb) / n if n else 128.0

    return {
        "brightness": brightness,
        "detail":     detail,
        "r": avg_r, "g": avg_g, "b": avg_b,
    }


def _classify_palette(r: float, g: float, b: float,
                       brightness: float) -> tuple:
    """
    Return (palette_mode, dominant_hue) from average RGB and brightness.

    palette_mode: "light" | "dark" | "warm" | "cool" | "green" | "mixed"
    dominant_hue: "warm" | "cool" | "green" | "neutral"
    """
    # Dominant hue based on channel imbalance
    warm_score  = r - (g + b) / 2
    cool_score  = b - (r + g) / 2
    green_score = g - (r + b) / 2

    if green_score > 18:
        dominant_hue = "green"
    elif warm_score > 15:
        dominant_hue = "warm"
    elif cool_score > 12:
        dominant_hue = "cool"
    else:
        dominant_hue = "neutral"

    if brightness > 175:
        palette_mode = "light"
    elif brightness > 135 and dominant_hue == "warm":
        palette_mode = "warm"
    elif brightness < 70:
        palette_mode = "dark"
    elif dominant_hue == "cool":
        palette_mode = "cool"
    elif dominant_hue == "green":
        palette_mode = "green"
    elif brightness > 115:
        palette_mode = "mixed"
    else:
        palette_mode = "dark"

    return palette_mode, dominant_hue


def _readability_risk(center_brightness: float,
                      center_detail: float) -> str:
    """
    Classify readability risk for the center text zone.

    High risk:
      - Detail is high (busy texture behind text)
      - Brightness is in the "grey zone" 85-168 (neither dark nor light enough)
    Medium risk:
      - Moderate detail OR borderline brightness
    Low risk:
      - Very dark or very bright with low detail
    """
    grey_zone   = 75 < center_brightness < 185 # Slightly wider sensitive zone
    very_busy   = center_detail > 0.60         # Relaxed from 0.40
    busy        = center_detail > 0.35         # Relaxed from 0.25
    borderline  = 95 < center_brightness < 155 # Slightly wider borderline

    if very_busy or (grey_zone and busy):
        return "high"
    elif busy or borderline:
        return "medium"
    else:
        return "low"


def _typography_mode(center_brightness: float, palette_mode: str,
                     dominant_hue: str) -> str:
    """
    Choose the base typography mode from center brightness and palette.

    LIGHT     → text must be dark   (bg is bright)
    DARK      → text must be light  (bg is dark / space-like)
    MID_LIGHT → borderline bright   (lean dark text)
    MID_DARK  → borderline dark     (lean light text)
    """
    if center_brightness >= 168:
        return "LIGHT"
    elif center_brightness >= 128:
        # Warm mid-bright (golden hour, dawn sky) → dark text
        if palette_mode in ("light", "warm"):
            return "MID_LIGHT"
        else:
            return "MID_DARK"
    elif center_brightness >= 88:
        # Medium-dark — lean light text
        return "MID_DARK"
    else:
        return "DARK"


def analyze_background(image, size: tuple) -> "AnalysisResult":
    """
    Analyze a rendered background image and return a rich AnalysisResult.

    Zones:
      A (reference row):   top 8-25%  of image height
      B (main quote row):  30-70%
      C (support row):     72-88%

    All sampling uses 48×48 downsamples for speed (<30ms on 1080×1080).
    """
    # Full-image overview
    full  = _sample_zone(image, size, 0.0, 1.0)
    # Center of image (where text lives)
    cen   = _sample_zone(image, size, 0.25, 0.75, 0.20, 0.80)
    edge  = _sample_zone(image, size, 0.0, 0.12)

    # Per text-zone sampling
    zA = _sample_zone(image, size, 0.08, 0.25)
    zB = _sample_zone(image, size, 0.30, 0.70)
    zC = _sample_zone(image, size, 0.72, 0.88)

    # Center contrast headroom — how far from 128 (more = easier to contrast)
    center_contrast = abs(cen["brightness"] - 128.0) / 128.0

    palette_mode, dominant_hue = _classify_palette(
        full["r"], full["g"], full["b"], full["brightness"])

    risk     = _readability_risk(zB["brightness"], zB["detail"])
    typo_mode = _typography_mode(zB["brightness"], palette_mode, dominant_hue)

    # REFORM: Automatic protection is now DISABLED by default.
    # We only trigger it if risk is 'insane' (rare) or user explicitly opts-in.
    needs_protection = (risk == "insane") 

    result = AnalysisResult(
        overall_brightness  = full["brightness"],
        center_brightness   = cen["brightness"],
        edge_brightness     = edge["brightness"],
        center_detail       = zB["detail"],
        center_contrast     = center_contrast,
        readability_score   = max(0.0, center_contrast * 1.5 - zB["detail"] * 0.8),
        is_light            = (full["brightness"] > 145),
        zone_a_brightness   = zA["brightness"],
        zone_b_brightness   = zB["brightness"],
        zone_c_brightness   = zC["brightness"],
        zone_a_detail       = zA["detail"],
        zone_b_detail       = zB["detail"],
        zone_c_detail       = zC["detail"],
        needs_protection    = needs_protection,
        palette_mode        = palette_mode,
        readability_risk    = risk,
        typography_mode     = typo_mode,
        dominant_hue        = dominant_hue,
    )
    print(f"\n📊 [Analyzer]"
          f"  mode={typo_mode}  palette={palette_mode}/{dominant_hue}"
          f"  B-brt={zB['brightness']:.0f}  detail={zB['detail']:.2f}"
          f"  risk={risk}  protect={needs_protection}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TYPOGRAPHY ADAPTATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────


def adapt_typography(analysis: "AnalysisResult",
                     spec: "VisualSpec" = None,
                     text_style: "TextStyleSpec" = None,
                     readability_priority: bool = True) -> "TypographySpec":
    """
    The Readability Engine: Merges background analysis with aesthetic intent.
    Ensures text is legible even if the user requests "Experimental" or difficult styles.
    """
    if text_style is None:
        text_style = TextStyleSpec()
        
    mode_map = {"LIGHT": _LIGHT_MODE, "DARK": _DARK_MODE, "MID_LIGHT": _MID_LIGHT_MODE, "MID_DARK":  _MID_DARK_MODE}
    mode_key = analysis.typography_mode
    M = mode_map.get(mode_key, _DARK_MODE)
    theme = getattr(spec, "theme", "custom") if spec else "custom"
    T_ovr = _THEME_ACCENT_OVERRIDES.get(theme, {})
    
    # Adaptive zone-based text color switching
    def get_color(brt, key):
        # Honor user ivory/white intent if background contrast allows
        if text_style.accent_color == "Ivory" and brt < 180:
            return (245, 241, 232)
        if brt > 145: return _LIGHT_MODE[key]
        if brt < 85:  return _DARK_MODE[key]
        return M[key]
        
    ref_c = get_color(analysis.zone_a_brightness, "reference")
    q_c   = get_color(analysis.zone_b_brightness, "main")
    sub_c = get_color(analysis.zone_c_brightness, "support")
    
    # Force Gold accent if requested and contrast allows (or experimental mode is on)
    if text_style.accent_color == "Gold" and (analysis.zone_b_brightness < 120 or text_style.experimental):
        ref_c = (212, 175, 55)
    
    # Gently blend theme-specific accents only if the background allows it
    if T_ovr.get("reference") and mode_key in ("DARK", "MID_DARK") and analysis.zone_a_brightness < 100:
        ref_c = tuple(T_ovr["reference"])

    orn_c = M["orn_color"]
    sep_c = M["sep_color"]

    baseline_contrast = analysis.center_contrast
    baseline_contrast = analysis.center_contrast
    noise_penalty = min(0.3, analysis.center_detail * 1.5)
    readability_score = max(0.0, min(1.0, baseline_contrast - noise_penalty))

    # READABILITY GUARDRAILS
    # If priority is HIGH or risk is HIGH, we force shadows and dim layers
    force_protection = (readability_priority and analysis.readability_risk != "low")
    if text_style.experimental:
        force_protection = False # Relax for experimental mode

    # --- TOP ZONE (Reference) ---
    top_is_dark = (sum(ref_c[:3]) < 384)
    top_dim = False
    top_dim_color = (0, 0, 0, 0)
    
    # Subtle darkening/brightening ONLY behind text if needed
    if (top_is_dark and analysis.zone_a_brightness < 160) or (force_protection and analysis.zone_a_brightness > 180 and not top_is_dark):
        top_dim = True
        top_dim_color = (255, 255, 255, 45) if top_is_dark else (0, 0, 0, 50)

    top_style = ZoneStyle(
        color=ref_c,
        opacity=1.0,
        shadow_fill=(255, 255, 255, 120) if top_is_dark else (0, 0, 0, 150),
        shadow_dx=0,
        shadow_dy=2,
        dim_layer=False, # Forced NO-BOX
        dim_color=(0, 0, 0, 0),
        dim_radius=0,
        glossy=text_style.glossy
    )

    # --- MAIN ZONE (Quote) ---
    main_is_dark_text = (sum(q_c[:3]) < 384)
    
    main_style = ZoneStyle(
        color=q_c,
        opacity=1.0,
        shadow_fill=(255, 255, 255, 130) if main_is_dark_text else (0, 0, 0, 160),
        shadow_dx=0,
        shadow_dy=2, # Soft vertical offset
        dim_layer=False, # Forced NO-BOX
        dim_color=(0, 0, 0, 0),
        dim_radius=0,
        glossy=text_style.glossy
    )

    # --- SUBTEXT ZONE (Support) ---
    sub_is_dark_text = (sum(sub_c[:3]) < 384)
    sub_dim = False
    sub_dim_color = (0, 0, 0, 0)
    
    if sub_is_dark_text and analysis.zone_c_brightness < 160:
        sub_dim = True
        sub_dim_color = (255, 255, 255, 25)
    elif not sub_is_dark_text and analysis.zone_c_brightness > 70:
        sub_dim = True
        sub_dim_color = (0, 0, 0, 30)

    sub_style = ZoneStyle(
        color=sub_c,
        opacity=0.88,
        shadow_fill=(255, 255, 255, 100) if sub_is_dark_text else (0, 0, 0, 120),
        shadow_dx=0,
        shadow_dy=1,
        dim_layer=False, # Forced NO-BOX
        dim_color=(0, 0, 0, 0),
        dim_radius=0
    )

    # --- CINEMATIC v8.0 ATMOSPHERIC READABILITY ---
    halo_opacity = 0
    halo_radius = 0
    halo_color = (0, 0, 0, 0)
    
    # 1. Main Quote Halo Logic
    risk = analysis.readability_risk
    if risk == "high":
        halo_opacity = 90
        halo_radius = 420
    elif risk == "medium":
        halo_opacity = 60
        halo_radius = 350
    elif risk == "low":
        halo_opacity = 40
        halo_radius = 280
        
    # Halo Color Selection
    if main_is_dark_text:
        halo_color = (255, 255, 255, halo_opacity)
    else:
        halo_color = (0, 0, 0, halo_opacity)

    # 2. Top Band Logic (Atmospheric Protection)
    top_band_enabled = False
    top_band_alpha = 0
    top_band_color = (0, 0, 0, 0)
    
    ref_brightness = sum(ref_c[:3]) / 3
    contrast_diff = abs(analysis.zone_a_brightness - ref_brightness)
    
    if contrast_diff < 50 or risk != "low":
        top_band_enabled = True
        top_band_alpha = 55 if risk == "high" else 35 # Stronger for high risk
        top_band_color = (0, 0, 0, top_band_alpha) if not top_is_dark else (255, 255, 255, top_band_alpha)

    # 3. Typography Hardening (Weight/Spacing/Size)
    if analysis.zone_b_detail > 0.25 or risk != "low":
        text_style.weight = "Bold"
        text_style.letter_spacing += 1
        
    # 4. Reference Guardrail (v8.5 Refinement)
    show_reference = True
    
    # Adaptive Protection Pass
    if contrast_diff < 42 or risk == "high":
        # A. Try Contrast Flip (Dark text on light area, or vice versa)
        better_c = (255, 255, 255) if analysis.zone_a_brightness < 128 else (0, 0, 0)
        new_diff = abs(analysis.zone_a_brightness - (sum(better_c)/3))
        if new_diff > contrast_diff:
            ref_c = better_c
            contrast_diff = new_diff
            
        # B. Increase Opacity & Tracking
        top_style.opacity = 1.0 # Maximize
        top_style.letter_spacing = 1 # Tracking boost
        top_style.shadow_fill = (0, 0, 0, 200) if (sum(ref_c[:3])/3) > 128 else (255, 255, 255, 180)
        
        # C. Force Top Band if not already on
        if not top_band_enabled:
            top_band_enabled = True
            top_band_alpha = 40
            top_band_color = (0, 0, 0, top_band_alpha) if (sum(ref_c[:3])/3) > 128 else (255, 255, 255, top_band_alpha)

    # Final "Last Resort" Hide Check
    # Only hide if it's truly unreadable (low contrast + very high noise)
    # UNLESS top band is NOT enabled (unlikely) or detail is high
    if contrast_diff < 25 and analysis.zone_a_detail > 0.42 and top_band_enabled:
        show_reference = False

    return TypographySpec(
        readability_score=readability_score, top=top_style, main=main_style, sub=sub_style,
        typography_mode=mode_key, readability_risk=risk, 
        ref_color=ref_c, quote_color=q_c, support_color=sub_c, 
        glossy=text_style.glossy,
        sep_color=sep_c, orn_color=orn_c,
        text_style=text_style,
        halo_radius=halo_radius, halo_opacity=halo_opacity, halo_color=halo_color,
        top_band_enabled=top_band_enabled, top_band_alpha=top_band_alpha, top_band_color=top_band_color,
        show_reference=show_reference
    )


def spec_cache_key(spec: VisualSpec, engine: str = "dalle") -> str:
    """Stable 12-char hash of the semantic content, variation, AND engine."""
    v_str = str(sorted(spec.variation_traits.items()))
    # We include engine to prevent engine-mismatch cache hits
    key_str = (f"{engine}|{spec.theme}|{spec.material}|{spec.lighting}|"
               f"{spec.mood}|{spec.ornament_level}|{spec.detail_level}|{v_str}")
    return hashlib.md5(key_str.encode()).hexdigest()[:12]


def load_bg_cache(spec: VisualSpec, cache_dir: str, engine: str = "dalle"):
    """
    Load a background from the semantic spec cache.
    Returns PIL Image or None.
    """
    key  = spec_cache_key(spec, engine=engine)
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


def save_bg_cache(image, spec: VisualSpec, cache_dir: str, engine: str = "dalle") -> None:
    """Persist a generated background to the semantic spec cache."""
    if Image is None:
        return
    try:
        os.makedirs(cache_dir, exist_ok=True)
        key  = spec_cache_key(spec, engine=engine)
        path = os.path.join(cache_dir, f"vsbg_{key}.jpg")
        image.save(path, quality=92)
        print(f"💾 [Cache] Saved vsbg_{key}  (theme={spec.theme})")
    except Exception as e:
        print(f"⚠️  [Cache] Save failed: {e}")

        
def compose_gemini_prompt(spec: VisualSpec, raw_prompt: str = "") -> str:
    """
    Production-hardened prompt composer for Gemini (Imagen 3).
    Stricter than DALL-E version: enforces zero-text and ultra-clean center 
    using explicit negation tokens and mandatory sanitization.
    """
    # 1. Generate variations (Consistent with DALL-E flow)
    v_data = VariationEngine.generate(spec.theme, raw_prompt)
    
    # 2. Mutate spec for cache key stability
    spec.variation_traits = v_data.get("variation_traits", {})
    
    # 3. Prepare visual strings
    var_list = [f"{v}" for k, v in spec.variation_traits.items()]
    variations_str = ", ".join(var_list)
    
    # 4. Sanitize user input (removes semantic/text markers)
    safe_user_input = sanitize_for_dalle(raw_prompt) if raw_prompt else ""
    
    # 5. Assemble stricter Gemini prompt
    final_prompt = (
        f"{_GEMINI_STRICT_CONSTRAINTS} "
        f"A beautiful artistic square background plate representing: {safe_user_input or spec.theme}. "
        f"Material traits: {variations_str}. "
        f"{v_data.get('core_traits', '')} "
        f"Mood: {spec.mood}. "
        f"{_GEMINI_COMPOSITION} "
        f"{_QUALITY}"
    )
    
    print(f"\n🌪️  GEMINI AUTO-VARIATION [{v_data.get('family')}]: {spec.variation_traits}")
    return final_prompt
