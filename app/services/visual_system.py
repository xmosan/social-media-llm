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
class ZoneStyle:
    color: tuple
    opacity: float
    shadow_fill: tuple
    shadow_dx: int
    shadow_dy: int
    glow_style: str  # "none", "subtle", "strong"
    dim_layer: bool
    dim_color: tuple
    dim_radius: int

@dataclass
class TypographySpec:
    """
    Complete text styling specification separated strictly by layout zones.
    Output of adapt_typography(analysis, spec).
    """
    readability_score: float
    top: ZoneStyle    # Reference line
    main: ZoneStyle   # Main Quote
    sub: ZoneStyle    # Support/Reflection
    
    # Global fallbacks to remain theoretically compatible
    typography_mode: str = "DARK"
    readability_risk: str = "low"
    has_glow: bool = False
    ref_color: tuple = (255,255,255)
    quote_color: tuple = (255,255,255)
    support_color: tuple = (255,255,255)
    dim_layer: bool = False
    dim_color: tuple = (0,0,0,0)
    dim_radius: int = 0
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


def adapt_typography(analysis: "AnalysisResult",
                     spec: "VisualSpec" = None) -> "TypographySpec":
    """
    Build independent Typography styling per text zone based on background analysis.
    """
    mode_map = {
        "LIGHT":     _LIGHT_MODE,
        "DARK":      _DARK_MODE,
        "MID_LIGHT": _MID_LIGHT_MODE,
        "MID_DARK":  _MID_DARK_MODE,
    }
    mode_key = analysis.typography_mode
    M = mode_map.get(mode_key, _DARK_MODE)
    theme = getattr(spec, "theme", "custom") if spec else "custom"

    # Theme overrides
    T_ovr = _THEME_ACCENT_OVERRIDES.get(theme, {})
    ref_c = tuple(T_ovr.get("reference", M["reference"]))
    q_c = tuple(M["main"])
    sub_c = tuple(M["support"])
    sh_fill = tuple(M["shadow"])
    sh_dx = M.get("shadow_dx", 2)
    sh_dy = M.get("shadow_dy", 2)

    # Calculate global readability score
    baseline_contrast = analysis.center_contrast
    noise_penalty = min(0.3, analysis.center_detail * 1.5)
    readability_score = max(0.0, min(1.0, baseline_contrast - noise_penalty))

    top_noise = max(0, analysis.zone_a_brightness - 120) / 135.0 if mode_key == "LIGHT" else max(0, 135 - analysis.zone_a_brightness) / 135.0
    
    # ── TOP ZONE (Reference) ──
    top_dim = analysis.zone_a_brightness > 130 and mode_key == "LIGHT" or analysis.zone_a_brightness < 90 and mode_key == "DARK"
    top_glow = "strong" if theme in ["cosmic", "sacred_black"] else "subtle" if theme in ["celestial", "moonlit"] else "none"
    top_style = ZoneStyle(
        color=ref_c,
        opacity=1.0,
        shadow_fill=sh_fill,
        shadow_dx=sh_dx,
        shadow_dy=sh_dy,
        glow_style=top_glow,
        dim_layer=top_dim,
        dim_color=(0,0,0,135) if mode_key in ["LIGHT", "MID_LIGHT"] else (0,0,0,165),
        dim_radius=55
    )

    # ── MAIN ZONE (Quote) ──
    main_dim = analysis.readability_risk in ["medium", "high"]
    dm_r = {"low": 0, "medium": 320, "high": 420}.get(analysis.readability_risk, 200)
    dm_c = (0,0,0,45) if mode_key in ["LIGHT", "MID_LIGHT"] else (0,0,0,140)
    if mode_key == "LIGHT" and analysis.readability_risk == "high":
        dm_c = (0,0,0,120)
    elif mode_key == "DARK" and analysis.readability_risk == "high":
        dm_c = (0,0,0,180)

    main_style = ZoneStyle(
        color=q_c,
        opacity=1.0,
        shadow_fill=sh_fill,
        shadow_dx=sh_dx + (1 if analysis.readability_risk == "high" else 0),
        shadow_dy=sh_dy + (1 if analysis.readability_risk == "high" else 0),
        glow_style="subtle" if T_ovr.get("glow_rgba") and mode_key == "DARK" else "none",
        dim_layer=main_dim,
        dim_color=dm_c,
        dim_radius=dm_r
    )

    # ── SUB ZONE (Support) ──
    sub_dim = analysis.zone_c_brightness > 140 if mode_key == "LIGHT" else analysis.zone_c_brightness < 70
    sub_style = ZoneStyle(
        color=sub_c,
        opacity=0.82,
        shadow_fill=sh_fill,
        shadow_dx=max(1, sh_dx - 1),
        shadow_dy=max(1, sh_dy - 1),
        glow_style="none",
        dim_layer=sub_dim,
        dim_color=(0,0,0,85),
        dim_radius=110
    )

    return TypographySpec(
        readability_score=readability_score,
        top=top_style,
        main=main_style,
        sub=sub_style,
        typography_mode=mode_key,
        readability_risk=analysis.readability_risk,
        has_glow=(T_ovr.get("glow_rgba") is not None),
        ref_color=ref_c,
        quote_color=q_c,
        support_color=sub_c,
        dim_layer=main_dim,
        dim_color=dm_c,
        dim_radius=dm_r
    )

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
