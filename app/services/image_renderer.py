"""
Sabeel Studio — Image Renderer v6.0
Multi-Dimensional Visual Art Direction Engine

Custom mode pipeline:
  1. Base gradient        → material-matched palette
  2. Material overlay     → marble veins / paper grain / obsidian sheen
  3. Atmosphere effect    → celestial glow / moonlit cast / sacred pattern
  4. Vignette             → intensity-driven depth
  5. Border / ornaments   → corner_filigree / manuscript / gold_block
  6. Text (3-zone)        → optical centering, palette-matched colors
  7. Cinematic post       → film grain, corner bloom, center warmth
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
# OPENAI CLIENT
# ─────────────────────────────────────────────────────────────────────────────

def get_openai_client() -> Optional[OpenAI]:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION EXTRACTORS  (pure keyword logic — no network, no floats)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_intensity(p: str) -> float:
    """Effect strength: subtle 0.42 | balanced 0.72 | dramatic 1.0"""
    if any(k in p for k in ["dramatic", "bold", "intense", "powerful", "vivid",
                              "rich", "strong", "heavy", "deep"]):
        return 1.0
    if any(k in p for k in ["subtle", "soft", "gentle", "light", "quiet",
                              "faint", "delicate", "minimal"]):
        return 0.42
    return 0.72


def _extract_material(p: str) -> str:
    """Primary surface/material."""
    if "obsidian" in p:
        return "obsidian"
    if any(k in p for k in ["marble", "stone", "granite", "slate"]):
        return "marble"
    if any(k in p for k in ["velvet", "silk", "satin"]):
        return "velvet"
    if any(k in p for k in ["parchment", "papyrus", "vellum"]):
        return "parchment"
    if any(k in p for k in ["manuscript"]):
        return "manuscript"
    if any(k in p for k in ["paper", "aged paper"]):
        return "paper"
    return "none"


def _extract_atmosphere(p: str) -> str:
    """Mood / lighting atmosphere."""
    if any(k in p for k in ["celestial", "heavenly", "divine light", "cosmic light"]):
        return "celestial"
    if any(k in p for k in ["moonlit", "moonlight", "lunar", "moon sky", "moon night"]):
        return "moonlit"
    if any(k in p for k in ["sacred", "holy", "sanctified"]):
        return "sacred"
    if any(k in p for k in ["ancient", "timeless", "classical", "eternal"]):
        return "ancient"
    if any(k in p for k in ["cinematic", "filmic"]):
        return "cinematic"
    if any(k in p for k in ["spiritual", "transcendent", "mystical"]):
        return "spiritual"
    if any(k in p for k in ["peaceful", "serene", "calm", "tranquil", "meditative"]):
        return "peaceful"
    if any(k in p for k in ["dramatic", "epic"]):
        return "dramatic"
    return "none"


def _extract_border(p: str) -> str:
    """Border / ornament treatment."""
    if any(k in p for k in ["corner line", "corner lines", "corner ornament",
                              "corner accent", "corner filigree", "corner gold",
                              "gold corner", "golden corner"]):
        return "corner_filigree"
    if any(k in p for k in ["manuscript border", "manuscript frame",
                              "manuscript line", "double line", "double frame"]):
        return "manuscript"
    if any(k in p for k in ["full border", "surrounding border", "complete frame"]):
        return "gold_block"
    # Any gold/border mention → refined corner filigree (not thick block)
    if any(k in p for k in ["gold", "golden", "border", "frame", "corner",
                              "ornament", "gilded", "filigree"]):
        return "corner_filigree"
    return "none"


def _extract_palette(p: str):
    """Returns (bg_start, bg_end, is_light, accent_rgb)  — all plain ints."""
    # ── Light backgrounds ──────────────────────────────────────────────────
    if any(k in p for k in ["parchment", "papyrus", "vellum", "ivory", "cream"]):
        return [248, 238, 212], [232, 220, 192], True, [140, 100, 40]
    if any(k in p for k in ["tan", "warm paper", "aged paper"]):
        return [242, 232, 210], [225, 215, 192], True, [130, 95, 42]
    if any(k in p for k in ["white", "pearl", "bright"]):
        return [245, 244, 240], [228, 226, 220], True, [120, 100, 60]

    # ── Dark / rich backgrounds ───────────────────────────────────────────
    if "obsidian" in p or "onyx" in p:
        return [14, 10, 18], [3, 2, 6], False, [165, 130, 225]
    if "charcoal" in p:
        return [38, 36, 42], [16, 14, 20], False, [205, 200, 215]
    if any(k in p for k in ["marble", "stone", "granite"]):
        return [44, 41, 48], [18, 16, 22], False, [210, 205, 220]
    if any(k in p for k in ["slate", "gunmetal"]):
        return [36, 40, 44], [13, 15, 19], False, [180, 186, 202]
    if any(k in p for k in ["black", "jet", "pitch"]):
        return [22, 20, 24], [3, 2, 4], False, [200, 196, 215]
    if any(k in p for k in ["emerald", "jade"]):
        return [0, 70, 36], [0, 25, 14], False, [120, 220, 148]
    if any(k in p for k in ["forest", "deep green", "dark green"]):
        return [6, 44, 21], [0, 16, 8], False, [130, 204, 138]
    if "green" in p:
        return [0, 56, 27], [0, 20, 10], False, [150, 210, 155]
    if any(k in p for k in ["navy", "deep blue", "midnight blue", "midnight"]):
        return [10, 18, 66], [3, 6, 28], False, [140, 172, 248]
    if any(k in p for k in ["sapphire", "cobalt", "royal blue"]):
        return [12, 24, 104], [4, 8, 44], False, [160, 188, 255]
    if any(k in p for k in ["moonlit", "moonlight", "lunar", "moon"]):
        return [16, 20, 60], [4, 6, 24], False, [180, 202, 255]
    if any(k in p for k in ["night sky", "night", "nighttime"]):
        return [8, 12, 38], [2, 4, 14], False, [160, 182, 242]
    if any(k in p for k in ["celestial", "cosmic", "galaxy", "cosmos"]):
        return [14, 22, 74], [3, 6, 24], False, [200, 212, 255]
    if any(k in p for k in ["burgundy", "crimson", "wine", "maroon"]):
        return [66, 10, 15], [28, 4, 6], False, [220, 140, 140]
    if any(k in p for k in ["violet", "purple", "plum", "amethyst"]):
        return [44, 12, 90], [18, 4, 38], False, [202, 156, 255]
    if any(k in p for k in ["desert", "sand", "amber", "warm gold"]):
        return [56, 32, 6], [22, 14, 2], False, [222, 182, 90]
    if any(k in p for k in ["rose", "dusty rose", "blush"]):
        return [82, 30, 42], [36, 12, 20], False, [242, 175, 185]
    if any(k in p for k in ["velvet", "deep velvet"]):
        return [28, 10, 50], [10, 4, 22], False, [192, 148, 255]

    # Default premium near-black
    return [22, 20, 26], [6, 5, 9], False, [200, 196, 216]


def _extract_glow(p: str, accent: list, is_light: bool, intensity: float) -> list:
    """Glow/halo RGBA — all int values."""
    if is_light:
        return [0, 0, 0, 0]
    if any(k in p for k in ["no glow", "matte", "flat", "no light"]):
        return [0, 0, 0, 0]

    base_a = min(255, int(75 * intensity))
    strong_a = min(255, int(115 * intensity))

    if any(k in p for k in ["golden glow", "warm glow", "gold glow",
                              "amber glow", "divine light", "celestial glow",
                              "celestial light"]):
        return [255, 218, 95, strong_a]
    if any(k in p for k in ["emerald aura", "green aura", "emerald glow"]):
        return [80, 220, 130, strong_a]
    if any(k in p for k in ["silver glow", "cool glow", "moonlit glow"]):
        return [200, 215, 255, strong_a]
    if any(k in p for k in ["glow", "aura", "halo", "radiant",
                              "luminous", "shining", "light"]):
        return [accent[0], accent[1], accent[2], strong_a]
    if any(k in p for k in ["moon", "moonlit", "lunar", "silver", "cool"]):
        return [195, 212, 255, base_a]
    if any(k in p for k in ["emerald", "forest", "green"]):
        return [90, 218, 136, base_a]
    if any(k in p for k in ["gold", "golden"]):
        return [255, 210, 78, base_a]
    if any(k in p for k in ["purple", "violet", "amethyst"]):
        return [186, 132, 255, base_a]
    if any(k in p for k in ["blue", "sapphire", "navy", "cobalt"]):
        return [148, 178, 255, base_a]

    return [255, 246, 222, min(255, int(55 * intensity))]


def _extract_pattern(p: str, material: str, atmosphere: str, intensity: float,
                     accent: list) -> tuple:
    """Returns (pattern_type, pattern_rgba)."""
    alpha = min(255, int(30 * intensity))

    if any(k in p for k in ["islamic pattern", "arabesque", "geometric pattern",
                              "islamic geometry", "geometric border"]):
        col = [int(accent[0] * 0.85), int(accent[1] * 0.85), int(accent[2] * 0.85), alpha]
        return "islamic", col
    if material in ("parchment", "manuscript", "paper") or "aged" in p:
        return "paper", [255, 255, 255, 0]
    if any(k in p for k in ["star", "starry", "stars", "constellation"]):
        return "starry", [255, 255, 255, 0]
    if atmosphere in ("moonlit", "celestial") and "star" in p:
        return "starry", [255, 255, 255, 0]
    if atmosphere == "sacred":
        col = [int(accent[0] * 0.6), int(accent[1] * 0.6), int(accent[2] * 0.6),
               min(255, int(28 * intensity))]
        return "islamic", col
    return "none", [255, 255, 255, 0]


def interpret_visual_prompt(prompt: str) -> dict:
    """
    Multi-dimensional visual prompt interpreter v2.0.

    Extracts: intensity | material | atmosphere | border | palette |
              pattern | glow — and composes a rich render config.

    Returns a dict whose RGB values are always plain Python ints.
    """
    p = prompt.lower().strip()
    print(f"\n🔍 [Interpreter] '{prompt[:80]}'")

    intensity  = _extract_intensity(p)
    material   = _extract_material(p)
    atmosphere = _extract_atmosphere(p)
    border     = _extract_border(p)
    bg_start, bg_end, is_light, accent = _extract_palette(p)
    glow_rgba  = _extract_glow(p, accent, is_light, intensity)
    pattern_type, pattern_rgba = _extract_pattern(p, material, atmosphere, intensity, accent)

    # Gradient
    gradient_type = "none" if is_light else "radial"

    # Vignette
    if is_light:
        vignette = 0.08
    elif atmosphere in ("dramatic", "cinematic"):
        vignette = min(0.95, round(0.84 * intensity, 3))
    elif atmosphere in ("celestial", "sacred"):
        vignette = min(0.80, round(0.65 * intensity, 3))
    elif material == "velvet":
        vignette = min(0.92, round(0.88 * intensity, 3))
    else:
        vignette = min(0.88, round(0.70 * intensity, 3))

    config = {
        # Colors (all int lists)
        "bg_start_rgb":       [int(v) for v in bg_start],
        "bg_end_rgb":         [int(v) for v in bg_end],
        "glow_color_rgba":    [int(v) for v in glow_rgba],
        "pattern_color_rgba": [int(v) for v in pattern_rgba],
        "accent_rgb":         [int(v) for v in accent],

        # Structural
        "gradient_type": gradient_type,
        "pattern_type":  pattern_type,
        "vignette":      float(vignette),
        "border_style":  border,
        "material":      material,
        "atmosphere":    atmosphere,
        "intensity":     float(intensity),
        "is_light_bg":   is_light,
    }

    print(f"   material={material}  atmosphere={atmosphere}  border={border}  "
          f"intensity={intensity:.2f}  is_light={is_light}")
    print(f"   bg: {bg_start} → {bg_end}  pattern={pattern_type}  "
          f"glow_a={glow_rgba[3] if len(glow_rgba) > 3 else 0}")
    return config


# ─────────────────────────────────────────────────────────────────────────────
# AI STYLE ANALYZER  (keyword config is primary; AI may augment colors only)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_config(cfg: dict) -> dict:
    """Cast all color component lists to int — guard against OpenAI float values."""
    out = dict(cfg)
    for key in ("bg_start_rgb", "bg_end_rgb", "pattern_color_rgba",
                "glow_color_rgba", "accent_rgb"):
        if key in out and isinstance(out[key], (list, tuple)):
            out[key] = [int(round(float(v))) for v in out[key]]
    if "vignette" in out:
        out["vignette"] = float(out["vignette"])
    return out


def analyze_style_prompt(visual_prompt: str, base_style: str) -> Optional[dict]:
    """
    Returns a full design config for a visual prompt.
    Keyword interpreter is PRIMARY. OpenAI may only refine color fields.
    Structural decisions (material, atmosphere, border_style) are always
    keyword-driven to prevent OpenAI from disrupting the render pipeline.
    """
    if not visual_prompt or not visual_prompt.strip():
        return None

    # Primary: instant keyword config
    config = interpret_visual_prompt(visual_prompt)

    # Optional: OpenAI color refinement
    client = get_openai_client()
    if not client:
        print("📌 [StyleAnalyzer] No OpenAI — keyword config only")
        return config

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a premium design color engine. "
                    "Return ONLY a JSON object with these exact keys "
                    "(all RGB values must be integers 0-255):\n"
                    '{"bg_start_rgb":[r,g,b],"bg_end_rgb":[r,g,b],'
                    '"glow_color_rgba":[r,g,b,a]}\n'
                    "Be literal: marble=dark grey, emerald=deep green, "
                    "obsidian=near-black, parchment=warm tan. "
                    "Dark backgrounds unless user says parchment/cream/ivory. "
                    "Return ONLY JSON, no other text."
                )},
                {"role": "user", "content": f"Visual: {visual_prompt}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            timeout=7
        )
        ai_raw = json.loads(response.choices[0].message.content)
        ai_cfg = _normalize_config(ai_raw)
        # AI may only update color fields — not structure
        for key in ("bg_start_rgb", "bg_end_rgb", "glow_color_rgba"):
            if key in ai_cfg:
                config[key] = ai_cfg[key]
        print(f"🤖 [StyleAnalyzer] AI color update applied")
    except Exception as e:
        print(f"⚠️  [StyleAnalyzer] AI failed ({e}) — keyword config only")

    return config


# ─────────────────────────────────────────────────────────────────────────────
# DRAWING PRIMITIVES
# ─────────────────────────────────────────────────────────────────────────────

def draw_radial_gradient(draw, size, color_start, color_end):
    """Radial gradient from center. All coords and colors are integers."""
    W, H = size
    cx, cy   = W // 2, H // 2
    max_dist = int(math.sqrt(cx * cx + cy * cy)) + 1
    steps    = 60
    for i in range(steps, 0, -1):
        t      = i / steps          # 1.0 at center → 0.0 at edge
        radius = int(max_dist * t)
        u      = 1 - t              # 0 at center → 1 at edge
        r = int(color_start[0] * t + color_end[0] * u)
        g = int(color_start[1] * t + color_end[1] * u)
        b = int(color_start[2] * t + color_end[2] * u)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     fill=(r, g, b))


def draw_starry_noise(draw, size, density=0.0006):
    """Subtle star field — RGB draw context only."""
    W, H  = size
    count = int(W * H * density)
    for _ in range(count):
        x = random.randint(0, W - 1)
        y = random.randint(0, H - 1)
        b = random.randint(180, 255)
        draw.point((x, y), fill=(b, b, b))


def draw_paper_texture(draw, size, color=(230, 222, 200)):
    """Warm paper grain — RGB draw context only."""
    W, H = size
    for _ in range(8000):
        x = random.randint(0, W - 1)
        y = random.randint(0, H - 1)
        v = random.randint(color[0] - 12, color[0] + 12)
        v = max(0, min(255, v))
        draw.point((x, y), fill=(v, max(0, v - 8), max(0, v - 18)))


def draw_marble_veins(image_rgb, size, vein_color, intensity=0.72) -> Image.Image:
    """
    Applies subtle sinusoidal marble veins over an RGB image.
    Returns a new RGB image with the vein layer composited.
    """
    W, H   = size
    layer  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld     = ImageDraw.Draw(layer)
    vc     = tuple(int(v) for v in vein_color[:3])
    n_veins = max(4, int(9 * intensity))
    alpha   = min(255, int(48 * intensity))

    random.seed(7331)
    for _ in range(n_veins):
        sx     = random.randint(-80, W + 80)
        sy     = random.randint(-40, H + 40)
        angle  = random.uniform(10, 80) * math.pi / 180
        length = random.randint(280, 750)
        amp    = random.uniform(6, 22)
        freq   = random.uniform(0.008, 0.025)

        prev = None
        for j in range(length):
            x = int(sx + j * math.cos(angle) + amp * math.sin(freq * j * 4.8))
            y = int(sy + j * math.sin(angle) + amp * math.cos(freq * j * 3.2))
            if 0 <= x < W and 0 <= y < H:
                pt = (x, y)
                ld.point(pt, fill=vc + (alpha,))
                if prev:
                    ld.line([prev, pt], fill=vc + (max(0, alpha - 18),), width=1)
                prev = pt
            else:
                prev = None
    random.seed()

    layer = layer.filter(ImageFilter.GaussianBlur(1))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


def draw_corner_filigree(draw, size, color, length=80, thickness=1):
    """
    Elegant thin corner ornaments — premium alternative to thick border block.
    Each corner has an L-shape with a small diamond accent and inner notch.
    """
    W, H = size
    m    = 30                          # margin from edge
    c    = tuple(int(v) for v in color[:3])

    # (corner_x, corner_y, h_direction, v_direction)
    corners = [
        (m,     m,     +1, +1),   # top-left
        (W - m, m,     -1, +1),   # top-right
        (m,     H - m, +1, -1),   # bottom-left
        (W - m, H - m, -1, -1),   # bottom-right
    ]
    for cx, cy, hd, vd in corners:
        # Primary L-arms
        draw.line([(cx, cy), (cx + hd * length, cy)], fill=c, width=thickness)
        draw.line([(cx, cy), (cx, cy + vd * length)], fill=c, width=thickness)
        # Inner notch detail
        n = length // 4
        draw.line([(cx + hd * n, cy), (cx + hd * n, cy + vd * n)],
                  fill=c, width=thickness)
        draw.line([(cx, cy + vd * n), (cx + hd * n, cy + vd * n)],
                  fill=c, width=thickness)
        # Diamond accent at corner point
        d = 5
        draw.polygon([(cx,     cy - d),
                      (cx + d, cy),
                      (cx,     cy + d),
                      (cx - d, cy)],
                     fill=c)


def draw_manuscript_frame(draw, size, color, margin=30):
    """Double thin-line frame like illuminated manuscripts, with corner blocks."""
    W, H = size
    c    = tuple(int(v) for v in color[:3])
    m, g = margin, 10   # outer margin, gap

    draw.rectangle([m, m, W - m, H - m], outline=c, width=1)
    draw.rectangle([m + g, m + g, W - m - g, H - m - g], outline=c, width=1)
    sq = 4
    for px, py in [(m, m), (W - m, m), (m, H - m), (W - m, H - m)]:
        draw.rectangle([px - sq, py - sq, px + sq, py + sq], fill=c)


def draw_gold_border(draw, size, border_width=30):
    """Full layered gold frame with corner accent dots."""
    W, H      = size
    gold      = (200, 162, 42)
    gold_dim  = (148, 118, 30)
    m         = border_width
    draw.rectangle([m, m, W - m, H - m], outline=gold, width=3)
    draw.rectangle([m + 12, m + 12, W - m - 12, H - m - 12],
                   outline=gold_dim, width=1)
    dot_r = 5
    for px, py in [(m + 3, m + 3), (W - m - 3, m + 3),
                   (m + 3, H - m - 3), (W - m - 3, H - m - 3)]:
        draw.ellipse([px - dot_r, py - dot_r, px + dot_r, py + dot_r], fill=gold)


def draw_islamic_pattern(draw, size, color):
    """Sparse elegant Islamic star-diamond ornaments at corners and center."""
    W, H = size
    if len(color) == 4:
        r, g, b, a = (int(v) for v in color)
        blend = a / 255.0
        col   = (int(r * blend), int(g * blend), int(b * blend))
    else:
        col = tuple(int(v) for v in color[:3])

    positions = [(W // 2, H // 2), (180, 180), (W - 180, 180),
                 (180, H - 180), (W - 180, H - 180)]
    sizes     = [260, 110, 110, 110, 110]

    for (px, py), s in zip(positions, sizes):
        draw.polygon([(px, py - s), (px + s, py),
                      (px, py + s), (px - s, py)], outline=col, width=2)
        sq = int(s * 0.68)
        draw.rectangle([px - sq, py - sq, px + sq, py + sq], outline=col, width=1)
        dot = int(s * 0.14)
        draw.ellipse([px - dot, py - dot, px + dot, py + dot], outline=col, width=1)


def apply_vignette(image, intensity=0.65) -> Image.Image:
    """Smooth radial vignette — all integer coords."""
    W, H     = image.size
    overlay  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw     = ImageDraw.Draw(overlay)
    cx, cy   = W // 2, H // 2
    max_dist = int(math.sqrt(cx * cx + cy * cy)) + 1
    steps    = 36
    for i in range(steps):
        t      = i / steps          # 0 at center → 1 at edge
        radius = int(max_dist * (1 - t))
        alpha  = int((t ** 2.4) * 255 * intensity)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     fill=(0, 0, 0, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


# ─────────────────────────────────────────────────────────────────────────────
# ATMOSPHERE EFFECTS
# ─────────────────────────────────────────────────────────────────────────────

def apply_celestial_atmosphere(image_rgb, size, glow_color, intensity=0.72) -> Image.Image:
    """
    Divine center light radiating outward — bold spiritual warmth.
    Layered radial ellipses from bright core to soft outer diffusion.
    """
    W, H  = size
    cx, cy = W // 2, H // 2
    gc    = tuple(int(v) for v in glow_color[:3])
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld    = ImageDraw.Draw(layer)

    tiers = [
        (int(W * 0.12), int(80 * intensity)),
        (int(W * 0.26), int(52 * intensity)),
        (int(W * 0.44), int(28 * intensity)),
        (int(W * 0.62), int(14 * intensity)),
    ]
    for r, a in tiers:
        a = min(255, a)
        ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=gc + (a,))

    layer = layer.filter(ImageFilter.GaussianBlur(52))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


def apply_moonlit_atmosphere(image_rgb, size, intensity=0.72) -> Image.Image:
    """
    Cool silver light from top-center — moon simulation with soft scatter.
    """
    W, H  = size
    cx    = W // 2
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld    = ImageDraw.Draw(layer)

    moon_c = (185, 205, 255)
    ovals  = [
        (cx - 300, -90,  cx + 300, 310,  int(48 * intensity)),
        (cx - 150, -45,  cx + 150, 195,  int(34 * intensity)),
        (cx -  70, -20,  cx +  70,  90,  int(22 * intensity)),
    ]
    for x0, y0, x1, y1, a in ovals:
        a = min(255, a)
        ld.ellipse([x0, y0, x1, y1], fill=moon_c + (a,))

    # Deterministic soft stars (top half only)
    random.seed(42)
    for _ in range(int(150 * intensity)):
        sx = random.randint(0, W)
        sy = random.randint(0, H // 2)
        b  = random.randint(165, 255)
        a  = random.randint(85, 190)
        ld.point((sx, sy), fill=(b, b, min(255, b + 30), a))
    random.seed()

    layer = layer.filter(ImageFilter.GaussianBlur(7))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


def apply_spiritual_atmosphere(image_rgb, size, accent_color, intensity=0.72) -> Image.Image:
    """Warm diffuse inner glow — calm, meditative, transcendent."""
    W, H  = size
    cx, cy = W // 2, H // 2
    ac    = tuple(int(v) for v in accent_color[:3])
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld    = ImageDraw.Draw(layer)

    tiers = [
        (int(W * 0.20), int(55 * intensity)),
        (int(W * 0.40), int(28 * intensity)),
    ]
    for r, a in tiers:
        a = min(255, a)
        ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ac + (a,))

    layer = layer.filter(ImageFilter.GaussianBlur(70))
    return Image.alpha_composite(image_rgb.convert("RGBA"), layer).convert("RGB")


def apply_cinematic_grade(image_rgb, intensity=0.72) -> Image.Image:
    """Slight cool-teal shadow grade for cinematic atmosphere."""
    W, H  = image_rgb.size
    grade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd    = ImageDraw.Draw(grade)
    # Subtle teal shadow in corners
    a = min(255, int(30 * intensity))
    gd.rectangle([0, 0, W, H], fill=(0, 8, 18, a))
    return Image.alpha_composite(image_rgb.convert("RGBA"), grade).convert("RGB")


def apply_cinematic_layers(image, glow_color=None) -> Image.Image:
    """Premium post-processing: film grain + center warmth + corner bloom."""
    W, H = image.size
    img  = image.convert("RGBA")

    # 1. Film grain
    grain = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd    = ImageDraw.Draw(grain)
    for _ in range(3800):
        x = random.randint(0, W - 1)
        y = random.randint(0, H - 1)
        b = random.randint(200, 255)
        gd.point((x, y), fill=(b, b, b, 8))

    # 2. Center warmth glow
    cx_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd       = ImageDraw.Draw(cx_layer)
    cx, cy   = W // 2, H // 2
    gc       = (tuple(int(v) for v in glow_color[:3]) + (10,)
                if glow_color else (255, 245, 210, 10))
    cd.ellipse([cx - 460, cy - 460, cx + 460, cy + 460], fill=gc)
    cx_layer = cx_layer.filter(ImageFilter.GaussianBlur(190))

    # 3. Corner bloom
    bloom = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd    = ImageDraw.Draw(bloom)
    bd.ellipse([-280, -280, 460, 460],   fill=(255, 220, 160, 13))
    bd.ellipse([W - 460, H - 460, W + 280, H + 280], fill=(150, 205, 255, 11))
    bloom = bloom.filter(ImageFilter.GaussianBlur(125))

    img = Image.alpha_composite(img, cx_layer)
    img = Image.alpha_composite(img, grain)
    img = Image.alpha_composite(img, bloom)
    return img.convert("RGB")


# ─────────────────────────────────────────────────────────────────────────────
# PRESET STYLE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

PRESET_BACKGROUNDS = {
    "quran": {
        "base": (0, 10, 5),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (0, 62, 31), (0, 10, 5)),
            draw_islamic_pattern(draw, ts, (190, 152, 42, 28)),
        ),
        "vignette": 0.72, "border": "gold_block", "border_w": 32,
        "glow": (170, 225, 175, 52),
    },
    "fajr": {
        "base": (5, 8, 28),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (14, 22, 72), (3, 5, 20)),
            draw_starry_noise(draw, ts, density=0.0005),
        ),
        "vignette": 0.52, "border": "none",
        "glow": (120, 160, 255, 62),
    },
    "scholar": {
        "base": (245, 240, 225),
        "build": lambda bg, draw, ts: draw_paper_texture(draw, ts, (240, 230, 210)),
        "vignette": 0.06, "border": "none",
        "glow": None,
    },
    "madinah": {
        "base": (14, 8, 2),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (52, 28, 5), (12, 7, 1)),
            draw_islamic_pattern(draw, ts, (196, 154, 62, 36)),
        ),
        "vignette": 0.62, "border": "gold_block", "border_w": 28,
        "glow": (222, 182, 82, 48),
    },
    "kaaba": {
        "base": (0, 0, 0),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (14, 14, 14), (0, 0, 0)),
            draw_islamic_pattern(draw, ts, (178, 148, 50, 16)),
        ),
        "vignette": 0.38, "border": "gold_block", "border_w": 24,
        "glow": (200, 164, 44, 38),
    },
    "laylulqadr": {
        "base": (8, 0, 22),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (38, 10, 86), (6, 0, 22)),
            draw_starry_noise(draw, ts, density=0.0007),
        ),
        "vignette": 0.48, "border": "none",
        "glow": (165, 105, 255, 68),
    },
}

PRESET_TEXT = {
    "quran":      [(212, 175, 55), (255, 255, 255), (195, 215, 195)],
    "fajr":       [(140, 170, 245), (230, 238, 255), (170, 195, 240)],
    "scholar":    [(45, 42, 38), (22, 20, 18), (68, 62, 55)],
    "madinah":    [(212, 165, 60), (255, 242, 210), (200, 175, 130)],
    "kaaba":      [(180, 148, 50), (255, 255, 255), (185, 185, 185)],
    "laylulqadr": [(180, 145, 235), (238, 230, 255), (195, 175, 240)],
}

CUSTOM_TEXT_LIGHT = [(130, 90, 40),  (28, 24, 18),  (80, 68, 55)]   # dark ink
CUSTOM_TEXT_DARK  = [(212, 175, 55), (255, 255, 255), (210, 210, 210)]  # gold + white


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY RENDER (background-image mode — kept for compatibility)
# ─────────────────────────────────────────────────────────────────────────────

def render_quote_card(background_local_path: str, quote: str,
                      reference: str, output_dir: str) -> str:
    bg = Image.open(background_local_path).convert("RGB")
    W, H = 1080, 1080
    size = (W, H)
    ratio = bg.width / bg.height
    if ratio > 1:
        new_h, new_w = H, int(H * ratio)
    else:
        new_w, new_h = W, int(W / ratio)
    bg = bg.resize((new_w, new_h), Image.LANCZOS)
    left, top = (new_w - W) // 2, (new_h - H) // 2
    bg = bg.crop((left, top, left + W, top + H))

    base_dir  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    font_path = os.path.join(base_dir, "assets", "fonts", "Inter.ttf")
    try:
        font_sm = ImageFont.truetype(font_path, 36)
        font_lg = ImageFont.truetype(font_path, 72)
    except Exception:
        font_sm = font_lg = ImageFont.load_default()

    overlay = Image.new("RGBA", size, (0, 0, 0, 120))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)

    for i, line in enumerate(textwrap.wrap(reference, 44)[:2]):
        draw.text((W // 2, 120 + i * 44), line, font=font_sm,
                  fill=(212, 175, 55), anchor="mt")
    y = H // 2
    for line in textwrap.wrap(quote, 22):
        draw.text((W // 2, y), line, font=font_lg, fill=(255, 255, 255), anchor="mt")
        y += 80

    filename = f"qcard_{int(time.time() * 1000)}.jpg"
    path     = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    bg.save(path, quality=95)
    return f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def render_minimal_quote_card(
    segments:      list,
    output_dir:    str,
    style:         str = "quran",
    visual_prompt: str = None,
    mode:          str = "preset",
) -> str:
    """
    Designer Engine v6.0 — Strict Dual-Mode Pipeline.

    PRESET mode: curated palette + preset background build function.
    CUSTOM mode: 5-layer art-directed pipeline driven by visual_prompt.
    """
    target_size = (1080, 1080)
    W, H        = target_size
    base_dir    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print(f"\n{'═'*62}")
    print(f"🎨 [Renderer v6] mode={mode}  style={style}")
    print(f"📝 prompt={repr((visual_prompt or '')[:70])}")
    print(f"📦 segments={len(segments)}")
    print(f"{'═'*62}")

    # ── 1. RESOLVE OVERRIDES & PALETTE ───────────────────────────────────────
    overrides = None
    if mode == "custom":
        overrides = analyze_style_prompt(visual_prompt or "", style)

    if mode == "custom" and overrides:
        is_light = overrides.get("is_light_bg", False)
        palette  = CUSTOM_TEXT_LIGHT if is_light else CUSTOM_TEXT_DARK
    else:
        is_light = False
        palette  = PRESET_TEXT.get(style, PRESET_TEXT["quran"])

    # ── 2. FONT SELECTION ────────────────────────────────────────────────────
    use_serif = (style in ("scholar", "madinah") and mode == "preset") or \
                ("manuscript" in (overrides or {}).get("material", ""))
    font_file = "Amiri-Regular.ttf" if use_serif else "Inter.ttf"
    font_path = os.path.join(base_dir, "assets", "fonts", font_file)

    # ── 3. BACKGROUND CONSTRUCTION ───────────────────────────────────────────
    glow_rgba = None

    if mode == "custom" and overrides:
        # ── CUSTOM 5-LAYER PIPELINE ──────────────────────────────────────
        material   = overrides.get("material",   "none")
        atmosphere = overrides.get("atmosphere", "none")
        border_sty = overrides.get("border_style", "none")
        p_type     = overrides.get("pattern_type", "none")
        g_type     = overrides.get("gradient_type", "radial")
        intensity  = float(overrides.get("intensity", 0.72))
        accent     = [int(v) for v in overrides.get("accent_rgb", [200, 196, 216])]

        bg_start   = tuple(int(v) for v in overrides["bg_start_rgb"])
        bg_end     = tuple(int(v) for v in overrides["bg_end_rgb"])
        p_rgba     = tuple(int(v) for v in overrides.get("pattern_color_rgba", [255, 255, 255, 0]))
        glow_rgba  = tuple(int(v) for v in overrides.get("glow_color_rgba", [255, 245, 220, 50]))
        v_int      = float(overrides.get("vignette", 0.68))

        print(f"🏗️  [Layer 1] base gradient: {bg_start}→{bg_end}")
        # Layer 1: Base gradient
        bg   = Image.new("RGB", target_size, bg_end)
        draw = ImageDraw.Draw(bg)
        if g_type == "radial":
            draw_radial_gradient(draw, target_size, bg_start, bg_end)

        # Layer 2: Material texture
        print(f"🏗️  [Layer 2] material={material}")
        if material == "marble":
            vein_tone = [min(255, bg_start[0] + 55),
                         min(255, bg_start[1] + 52),
                         min(255, bg_start[2] + 60)]
            bg = draw_marble_veins(bg, target_size, vein_tone, intensity)
            draw = ImageDraw.Draw(bg)
        elif material in ("parchment", "manuscript", "paper"):
            draw_paper_texture(draw, target_size,
                               color=tuple(int(v) for v in bg_start))
        elif material == "velvet":
            pass  # velvet = ultra-smooth, no texture — rely on heavy vignette

        # Apply pattern (stars / paper / islamic)
        if p_type == "starry":
            draw_starry_noise(draw, target_size, density=max(0.0003, 0.0006 * intensity))
        elif p_type == "paper" and material not in ("parchment", "manuscript", "paper"):
            draw_paper_texture(draw, target_size)
        elif p_type == "islamic":
            draw_islamic_pattern(draw, target_size, p_rgba)

        # Layer 3: Atmosphere effects
        print(f"🏗️  [Layer 3] atmosphere={atmosphere}")
        glow_col_list = list(glow_rgba[:3])
        if atmosphere == "celestial":
            bg = apply_celestial_atmosphere(bg, target_size, glow_col_list, intensity)
            draw = ImageDraw.Draw(bg)
        elif atmosphere == "moonlit":
            bg = apply_moonlit_atmosphere(bg, target_size, intensity)
            draw = ImageDraw.Draw(bg)
        elif atmosphere in ("spiritual", "peaceful", "sacred"):
            bg = apply_spiritual_atmosphere(bg, target_size, glow_col_list, intensity * 0.85)
            draw = ImageDraw.Draw(bg)
        elif atmosphere == "cinematic":
            bg = apply_cinematic_grade(bg, intensity)
            draw = ImageDraw.Draw(bg)

        # Layer 4: Vignette
        print(f"🏗️  [Layer 4] vignette={v_int:.2f}")
        bg   = apply_vignette(bg, intensity=v_int)
        draw = ImageDraw.Draw(bg)

        # Layer 5: Border / ornaments
        print(f"🏗️  [Layer 5] border={border_sty}")
        gold_c = (int(accent[0] * 0.9 + 200 * 0.1),
                  int(accent[1] * 0.4 + 155 * 0.6),
                  int(accent[2] * 0.1 + 35 * 0.9))
        if border_sty == "corner_filigree":
            draw_corner_filigree(draw, target_size, gold_c, length=78)
        elif border_sty == "manuscript":
            gold_dim = tuple(max(0, v - 30) for v in gold_c)
            draw_manuscript_frame(draw, target_size, gold_dim)
        elif border_sty == "gold_block":
            draw_gold_border(draw, target_size)

    else:
        # ── PRESET BACKGROUND ────────────────────────────────────────────
        eff  = style if style in PRESET_BACKGROUNDS else "quran"
        spec = PRESET_BACKGROUNDS[eff]
        print(f"🏗️  [Preset] '{eff}'")

        bg   = Image.new("RGB", target_size, spec["base"])
        draw = ImageDraw.Draw(bg)
        spec["build"](bg, draw, target_size)
        bg   = apply_vignette(bg, intensity=spec["vignette"])
        draw = ImageDraw.Draw(bg)

        bsty = spec.get("border", "none")
        if bsty == "gold_block":
            draw_gold_border(draw, target_size,
                             border_width=spec.get("border_w", 30))

        glow_rgba = spec.get("glow")

    # ── 4. PRE-CALCULATE TEXT ZONES ──────────────────────────────────────────
    # Zone constraints: (max_width_px, line_spacing, zone_index)
    v_pad      = 85
    zone_ws    = [int(W * 0.70), int(W * 0.82), int(W * 0.72)]
    zone_ls    = [18, 30, 20]
    gap_ab     = 54   # gap Reference → Quote
    gap_bc     = 44   # gap Quote → Support

    draw = ImageDraw.Draw(bg)   # fresh draw for textbbox measurements
    zone_data = []

    for i, seg in enumerate(segments):
        if i >= 3:
            break
        z_w, z_ls = zone_ws[i], zone_ls[i]
        color      = palette[i] if i < len(palette) else palette[-1]

        try:
            fnt = ImageFont.truetype(font_path, int(seg["size"]))
        except Exception:
            fnt = ImageFont.load_default()

        avg_cw    = seg["size"] * 0.54
        max_chars = max(10, int(z_w / max(1, avg_cw)))
        lines_raw = textwrap.wrap(str(seg["text"]), width=max_chars)
        if i == 0 and len(lines_raw) > 2:  # reference: max 2 lines
            lines_raw = lines_raw[:2]
            lines_raw[-1] = lines_raw[-1].rstrip() + "…"

        block_h = 0
        line_data = []
        for line in lines_raw:
            bbox = draw.textbbox((0, 0), line, font=fnt)
            lh   = bbox[3] - bbox[1]
            lw   = bbox[2] - bbox[0]
            line_data.append({"text": line, "h": lh, "w": lw})
            block_h += lh + z_ls
        if block_h > 0:
            block_h -= z_ls

        zone_data.append({
            "font": fnt, "lines": line_data,
            "block_h": block_h, "color": color, "ls": z_ls,
        })
        print(f"   Zone {i}: {len(line_data)} lines  block_h={block_h}px")

    # ── 5. OPTICAL CENTERING ─────────────────────────────────────────────────
    total_h = sum(zd["block_h"] for zd in zone_data)
    if len(zone_data) > 1:
        total_h += gap_ab
    if len(zone_data) > 2:
        total_h += gap_bc

    optical_shift = int(H * 0.03)
    start_y = max(v_pad, (H // 2) - (total_h // 2) - optical_shift)
    print(f"📐 total_h={total_h}px  start_y={start_y}px")

    # ── 6. GLOW HALO UNDER ZONE B ────────────────────────────────────────────
    bg_rgba = bg.convert("RGBA")
    if len(zone_data) > 1 and glow_rgba:
        g_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
        gd      = ImageDraw.Draw(g_layer)
        ty_g    = start_y + zone_data[0]["block_h"] + gap_ab
        cx      = W // 2
        gr      = tuple(int(v) for v in glow_rgba)
        for ln in zone_data[1]["lines"]:
            gd.text((cx, ty_g), ln["text"],
                    font=zone_data[1]["font"], fill=gr, anchor="mt")
            ty_g += ln["h"] + zone_data[1]["ls"]
        g_layer = g_layer.filter(ImageFilter.GaussianBlur(30))
        bg_rgba = Image.alpha_composite(bg_rgba, g_layer)

    # ── 7. TEXT DRAWING ───────────────────────────────────────────────────────
    draw_out = ImageDraw.Draw(bg_rgba)
    cx       = W // 2
    y        = start_y

    for i, zd in enumerate(zone_data):
        ty  = y
        col = zd["color"]

        for ln in zd["lines"]:
            if i == 0:  # Zone A — Reference (slightly dimmed)
                fc = (int(col[0]), int(col[1]), int(col[2]), 180)
                draw_out.text((cx, ty), ln["text"], font=zd["font"],
                              fill=fc, anchor="mt")
            elif i == 1:  # Zone B — Main Quote (shadow + text)
                draw_out.text((cx + 2, ty + 2), ln["text"], font=zd["font"],
                              fill=(0, 0, 0, 88), anchor="mt")
                draw_out.text((cx, ty), ln["text"], font=zd["font"],
                              fill=col, anchor="mt")
            else:  # Zone C — Supporting line
                fc = (int(col[0]), int(col[1]), int(col[2]), 215)
                draw_out.text((cx, ty), ln["text"], font=zd["font"],
                              fill=fc, anchor="mt")
            ty += ln["h"] + zd["ls"]

        y = ty - zd["ls"]
        if i == 0:
            y += gap_ab
        elif i == 1:
            y += gap_bc

    # ── 8. CINEMATIC POST-PROCESSING ─────────────────────────────────────────
    glow_list = list(glow_rgba) if glow_rgba else None
    final_img = apply_cinematic_layers(bg_rgba, glow_color=glow_list)

    filename   = f"qcard_{int(time.time() * 1000)}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    final_img.save(final_path, quality=95)

    print(f"✅ [Renderer] saved {filename}")
    print(f"{'═'*62}\n")
    return f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
