"""
Sabeel Studio — Visual System (Theme extraction & DALL-E orchestration)
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
class TypographySpec:
    """
    Complete text styling specification.
    Produced by adapt_typography(analysis, spec).

    typography_mode drives the base palette:
      LIGHT     → dark grounded text (parchment, bright sky)
      DARK      → warm luminous text (sacred black, deep space)
      MID_LIGHT → lean dark (golden hour, medium-bright)
      MID_DARK  → lean light (marble, charcoal, deep forest)
    """
    ref_color:       tuple = (212, 175, 55)   # Zone A — reference/accent
    quote_color:     tuple = (245, 241, 232)  # Zone B — main quote
    support_color:   tuple = (221, 214, 200)  # Zone C — support
    shadow_fill:     tuple = (0, 0, 0, 148)
    shadow_dx:       int   = 2
    shadow_dy:       int   = 2
    dim_layer:       bool  = False
    dim_color:       tuple = (0, 0, 0, 48)
    dim_radius:      int   = 110
    sep_color:       tuple = (188, 152, 50)
    glow_rgba:       tuple = (212, 175, 55, 70)
    orn_color:       tuple = (195, 162, 48)
    ref_alpha:       int   = 192
    typography_mode: str   = "DARK"
    readability_risk: str  = "low"
    has_glow:        bool  = True


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
    }
}

_VARIATION_HISTORY = {}

class VariationEngine:
    @staticmethod
    def generate(theme: str, user_prompt: str) -> dict:
        family_map = {
            "sacred_black": "sacred_black", "parchment": "parchment_manuscript",
            "marble": "luxury_marble", "emerald_forest": "emerald_forest",
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

def compose_dalle_prompt(spec: VisualSpec, raw_prompt: str = "") -> str:
    v_data = VariationEngine.generate(spec.theme, raw_prompt)
    
    # Store the traits in the spec for cache key stability
    spec.variation_traits = v_data["variation_traits"]
    
    var_list = [f"{k.replace('_', ' ')}: {v}" for k, v in v_data["variation_traits"].items()]
    variations_str = ", ".join(var_list)
    
    # Strategy: Tokens 1-50 are the strongest in DALL-E.
    # We lead with the variation traits to ensure maximum scene diversity.
    final_prompt = (
        f"{_HARD_CONSTRAINTS} "
        f"BACKGROUND PLATE: {variations_str}. "
        f"{v_data['core_traits']} "
        f"Mood: {spec.mood}. "
        f"{_COMPOSITION} "
        f"{_QUALITY}"
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
    grey_zone   = 85 < center_brightness < 168
    very_busy   = center_detail > 0.40
    busy        = center_detail > 0.25
    borderline  = 100 < center_brightness < 148

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

    needs_protection = (risk in ("medium", "high"))

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


@dataclass
class ZoneStyle:
    color: tuple
    opacity: float
    shadow_fill: tuple
    shadow_dx: int
    shadow_dy: int
    glow_style: str
    dim_layer: bool
    dim_color: tuple
    dim_radius: int

@dataclass
class TypographySpec:
    readability_score: float
    top: ZoneStyle
    main: ZoneStyle
    sub: ZoneStyle
    
    typography_mode: str = "DARK"
    readability_risk: str = "low"
    has_glow: bool = False
    glow_rgba: tuple = None
    ref_color: tuple = (255,255,255)
    quote_color: tuple = (255,255,255)
    support_color: tuple = (255,255,255)
    dim_layer: bool = False
    dim_color: tuple = (0,0,0,0)
    dim_radius: int = 0
    sep_color: tuple = (255,255,255)
    orn_color: tuple = (255,255,255)

def adapt_typography(analysis: "AnalysisResult",
                     spec: "VisualSpec" = None) -> "TypographySpec":
    mode_map = {"LIGHT": _LIGHT_MODE, "DARK": _DARK_MODE, "MID_LIGHT": _MID_LIGHT_MODE, "MID_DARK":  _MID_DARK_MODE}
    mode_key = analysis.typography_mode
    M = mode_map.get(mode_key, _DARK_MODE)
    theme = getattr(spec, "theme", "custom") if spec else "custom"
    T_ovr = _THEME_ACCENT_OVERRIDES.get(theme, {})
    
    # Adaptive zone-based text color switching
    def get_color(brt, key):
        if brt > 145: return _LIGHT_MODE[key]
        if brt < 85:  return _DARK_MODE[key]
        return M[key]
        
    ref_c = get_color(analysis.zone_a_brightness, "reference")
    q_c   = get_color(analysis.zone_b_brightness, "main")
    sub_c = get_color(analysis.zone_c_brightness, "support")
    
    # Gently blend theme-specific accents only if the background allows it
    if T_ovr.get("reference") and mode_key in ("DARK", "MID_DARK") and analysis.zone_a_brightness < 100:
        ref_c = tuple(T_ovr["reference"])

    orn_c = M["orn_color"]
    sep_c = M["sep_color"]

    baseline_contrast = analysis.center_contrast
    noise_penalty = min(0.3, analysis.center_detail * 1.5)
    readability_score = max(0.0, min(1.0, baseline_contrast - noise_penalty))

    # --- TOP ZONE (Reference) ---
    top_dim = False
    top_dim_color = (0, 0, 0, 0)
    top_is_dark_text = (sum(ref_c[:3]) < 384)
    # Subtle darkening/brightening ONLY behind text if needed
    if top_is_dark_text and analysis.zone_a_brightness < 160:
        top_dim = True
        top_dim_color = (255, 255, 255, 45) # Increased slightly for presence
    elif not top_is_dark_text and analysis.zone_a_brightness > 80:
        top_dim = True
        top_dim_color = (0, 0, 0, 50)       # Increased slightly for presence

    top_style = ZoneStyle(
        color=ref_c,
        opacity=1.0,
        shadow_fill=(255, 255, 255, 140) if top_is_dark_text else (0, 0, 0, 160),
        shadow_dx=-1 if top_is_dark_text else 1,
        shadow_dy=-1 if top_is_dark_text else 1,
        glow_style="none",
        dim_layer=top_dim,
        dim_color=top_dim_color,
        dim_radius=80  # high blur behind text
    )

    # --- MAIN ZONE (Quote) ---
    main_is_dark_text = (sum(q_c[:3]) < 384)
    main_dim = False
    main_dim_color = (0, 0, 0, 0)
    main_dim_rad = 380
    
    if analysis.readability_risk != 'low':
        main_dim = True
        if main_is_dark_text:
            main_dim_color = (255, 255, 255, 45 if analysis.readability_risk == "high" else 25)
        else:
            main_dim_color = (0, 0, 0, 85 if analysis.readability_risk == "high" else 55)

    main_style = ZoneStyle(
        color=q_c,
        opacity=1.0,
        shadow_fill=(255, 255, 255, 160) if main_is_dark_text else (0, 0, 0, 180),
        shadow_dx=-1 if main_is_dark_text else 1,
        shadow_dy=-1 if main_is_dark_text else 2,
        glow_style="none",
        dim_layer=main_dim,
        dim_color=main_dim_color,
        dim_radius=main_dim_rad
    )

    # --- SUBTEXT ZONE (Support) ---
    sub_is_dark_text = (sum(sub_c[:3]) < 384)
    sub_dim = False
    sub_dim_color = (0, 0, 0, 0)
    
    # Slight clarity boost / micro-darkening
    if sub_is_dark_text and analysis.zone_c_brightness < 160:
        sub_dim = True
        sub_dim_color = (255, 255, 255, 25)
    elif not sub_is_dark_text and analysis.zone_c_brightness > 70:
        sub_dim = True
        sub_dim_color = (0, 0, 0, 30)

    sub_style = ZoneStyle(
        color=sub_c,
        opacity=0.88, # Slightly boosted from 0.82/0.9 to find the sweet spot
        shadow_fill=(255, 255, 255, 120) if sub_is_dark_text else (0, 0, 0, 140),
        shadow_dx=0,
        shadow_dy=1,
        glow_style="none",
        dim_layer=sub_dim,
        dim_color=sub_dim_color,
        dim_radius=120
    )

    return TypographySpec(
        readability_score=readability_score, top=top_style, main=main_style, sub=sub_style,
        typography_mode=mode_key, readability_risk=analysis.readability_risk, has_glow=False,
        glow_rgba=None,
        ref_color=ref_c, quote_color=q_c, support_color=sub_c, 
        dim_layer=main_dim, dim_color=main_dim_color, dim_radius=main_dim_rad,
        sep_color=sep_c, orn_color=orn_c
    )


def spec_cache_key(spec: VisualSpec) -> str:
    """Stable 12-char hash of the semantic content AND random variation of a VisualSpec."""
    # We include variation_traits to ensure randomized generations don't collide in cache
    v_str = str(sorted(spec.variation_traits.items()))
    key_str = (f"{spec.theme}|{spec.material}|{spec.lighting}|"
               f"{spec.mood}|{spec.ornament_level}|{spec.detail_level}|{v_str}")
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