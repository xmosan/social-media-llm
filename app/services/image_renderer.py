import os
import time
import textwrap
import math
import random
import json
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from openai import OpenAI
from app.config import settings

def get_openai_client():
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)

# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD STYLE INTERPRETER — works 100% without any external API
# ══════════════════════════════════════════════════════════════════════════════

def interpret_visual_prompt(prompt: str) -> dict:
    """
    Converts natural-language visual description to a complete design config.
    Pure keyword matching — zero network calls. Always returns a valid config.
    """
    p = prompt.lower()
    print(f"🔍 [StyleInterpreter] Input: '{prompt}'")

    # ── Background ───────────────────────────────────────────────────────────
    bg_start, bg_end = [18, 18, 18], [4, 4, 4]  # default: near-black

    if any(k in p for k in ["marble", "stone", "slate", "granite"]):
        bg_start, bg_end = [42, 40, 46], [18, 16, 22]
    elif any(k in p for k in ["black", "obsidian", "onyx", "charcoal"]):
        bg_start, bg_end = [20, 20, 20], [2, 2, 2]
    elif any(k in p for k in ["emerald", "jade"]):
        bg_start, bg_end = [0, 68, 35], [0, 24, 14]
    elif any(k in p for k in ["forest", "deep green", "dark green"]):
        bg_start, bg_end = [5, 40, 20], [0, 14, 7]
    elif any(k in p for k in ["green"]):
        bg_start, bg_end = [0, 52, 26], [0, 18, 10]
    elif any(k in p for k in ["navy", "deep blue", "midnight blue", "indigo"]):
        bg_start, bg_end = [10, 18, 65], [3, 6, 28]
    elif any(k in p for k in ["sapphire", "cobalt", "royal blue"]):
        bg_start, bg_end = [12, 24, 100], [4, 8, 42]
    elif any(k in p for k in ["moonlit", "moonlight", "moon"]):
        bg_start, bg_end = [12, 16, 52], [4, 6, 24]
    elif any(k in p for k in ["burgundy", "crimson", "deep red", "wine", "maroon"]):
        bg_start, bg_end = [65, 10, 14], [28, 4, 6]
    elif any(k in p for k in ["violet", "purple", "plum", "amethyst"]):
        bg_start, bg_end = [42, 12, 88], [18, 4, 38]
    elif any(k in p for k in ["parchment", "cream", "paper", "manuscript", "beige", "aged", "antique"]):
        bg_start, bg_end = [248, 240, 218], [232, 224, 200]
    elif any(k in p for k in ["celestial", "night sky", "starry sky", "cosmic"]):
        bg_start, bg_end = [14, 24, 72], [3, 6, 22]
    elif any(k in p for k in ["desert", "sand", "dune", "amber", "golden hour", "warm"]):
        bg_start, bg_end = [55, 32, 6], [22, 14, 2]
    elif any(k in p for k in ["rose", "blush", "dusty rose"]):
        bg_start, bg_end = [80, 30, 40], [35, 12, 20]

    # Is it a light background (parchment family)?
    is_light_bg = bg_start[0] > 180

    # ── Pattern ───────────────────────────────────────────────────────────────
    pattern_type = "none"
    pattern_rgba = [255, 255, 255, 0]

    if any(k in p for k in ["star", "starry", "celestial", "cosmic", "galaxy", "night sky", "moon"]):
        pattern_type = "starry"
    elif any(k in p for k in ["geometry", "islamic", "pattern", "geometric", "arabesque"]):
        pattern_type = "islamic"
        pattern_rgba = [200, 162, 45, 30]
    elif any(k in p for k in ["parchment", "paper", "aged", "manuscript", "texture", "grain"]):
        pattern_type = "paper"

    # ── Border ────────────────────────────────────────────────────────────────
    border = "none"
    if any(k in p for k in ["gold", "golden", "border", "frame", "corner", "trim", "ornament", "edge"]):
        border = "gold"

    # ── Glow ─────────────────────────────────────────────────────────────────
    if is_light_bg:
        glow_rgba = [0, 0, 0, 0]  # no glow on light backgrounds
    elif any(k in p for k in ["no glow", "minimal", "clean", "simple"]):
        glow_rgba = [0, 0, 0, 0]
    elif any(k in p for k in ["glow", "halo", "aura", "light", "shining", "luminous"]):
        glow_rgba = [255, 255, 200, 100]
    elif any(k in p for k in ["moon", "moonlit", "silver", "cool"]):
        glow_rgba = [180, 200, 255, 70]
    elif any(k in p for k in ["blue", "navy", "sapphire", "indigo", "cobalt"]):
        glow_rgba = [140, 170, 255, 65]
    elif any(k in p for k in ["purple", "violet", "plum"]):
        glow_rgba = [180, 120, 255, 65]
    elif any(k in p for k in ["green", "emerald", "forest"]):
        glow_rgba = [100, 220, 140, 55]
    elif any(k in p for k in ["gold", "amber", "warm", "desert"]):
        glow_rgba = [255, 200, 80, 60]
    else:
        glow_rgba = [255, 245, 220, 50]  # default warm glow

    # ── Vignette ─────────────────────────────────────────────────────────────
    if is_light_bg:
        vignette = 0.08
    elif any(k in p for k in ["dramatic", "intense", "dark", "deep", "moody"]):
        vignette = 0.88
    elif any(k in p for k in ["soft", "gentle", "peaceful", "calm", "light"]):
        vignette = 0.45
    else:
        vignette = 0.70

    config = {
        "bg_start_rgb":      bg_start,
        "bg_end_rgb":        bg_end,
        "gradient_type":     "none" if is_light_bg else "radial",
        "pattern_type":      pattern_type,
        "pattern_color_rgba": pattern_rgba,
        "vignette":          vignette,
        "border":            border,
        "glow_color_rgba":   glow_rgba,
        "is_light_bg":       is_light_bg,
    }
    print(f"✅ [StyleInterpreter] Config: {config}")
    return config


def analyze_style_prompt(visual_prompt: str, base_style: str) -> dict | None:
    """
    Converts a visual prompt to design config.
    ALWAYS returns a config if prompt is non-empty.
    Uses keyword interpreter first (instant), optionally enhanced by OpenAI.
    """
    if not visual_prompt or not visual_prompt.strip():
        print("⚠️  [StyleAnalyzer] No visual_prompt — using preset mode")
        return None

    # Step 1: keyword interpretation (immediate, reliable)
    config = interpret_visual_prompt(visual_prompt)

    # Step 2: try to enhance with OpenAI if available
    client = get_openai_client()
    if not client:
        print("📌 [StyleAnalyzer] No OpenAI key — keyword config only")
        return config

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """You are a luxury design engine.
Translate the user's visual description into a JSON color config.
Be LITERAL with keywords: marble=dark grey, emerald=deep green, gold=add border.
Dark backgrounds unless user says parchment/cream/paper/light.
Return ONLY valid JSON matching this schema:
{"bg_start_rgb":[r,g,b],"bg_end_rgb":[r,g,b],"gradient_type":"radial"|"none",
"pattern_type":"islamic"|"starry"|"paper"|"none","pattern_color_rgba":[r,g,b,a],
"vignette":0.0-1.0,"border":"gold"|"none","glow_color_rgba":[r,g,b,a]}"""},
                {"role": "user", "content": f"Visual: {visual_prompt}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            timeout=8
        )
        ai_config = json.loads(response.choices[0].message.content)
        # Merge AI config over keyword config (AI is more nuanced)
        config.update(ai_config)
        print(f"🤖 [StyleAnalyzer] AI enhanced config: {config}")
    except Exception as e:
        print(f"⚠️  [StyleAnalyzer] OpenAI failed ({e}) — using keyword config only")

    return config


# ══════════════════════════════════════════════════════════════════════════════
# DRAWING PRIMITIVES
# ══════════════════════════════════════════════════════════════════════════════

def render_quote_card(background_local_path: str, quote: str, reference: str, output_dir: str) -> str:
    """
    Renders a 1080x1080 quote card by overlaying text on a background image.
    """
    try:
        bg = Image.open(background_local_path).convert("RGB")
    except Exception as e:
        print(f"[RENDER] Failed to open background: {e}")
        raise

    target_size = (1080, 1080)
    bg_ratio = bg.width / bg.height
    target_ratio = target_size[0] / target_size[1]
    if bg_ratio > target_ratio:
        new_h = target_size[1]
        new_w = int(new_h * bg_ratio)
    else:
        new_w = target_size[0]
        new_h = int(new_w / bg_ratio)
    bg = bg.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_size[0]) // 2
    top  = (new_h - target_size[1]) // 2
    bg   = bg.crop((left, top, left + target_size[0], top + target_size[1]))

    draw = ImageDraw.Draw(bg)
    base_dir  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    font_path = os.path.join(base_dir, "assets", "fonts", "Inter.ttf")
    try:
        ref_font   = ImageFont.truetype(font_path, 36)
        quote_font = ImageFont.truetype(font_path, 72)
    except:
        ref_font   = ImageFont.load_default()
        quote_font = ImageFont.load_default()

    W, H = target_size
    overlay = Image.new("RGBA", target_size, (0, 0, 0, 120))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)

    ref_lines = textwrap.wrap(reference, width=45)
    for i, line in enumerate(ref_lines[:2]):
        draw.text((W // 2, 120 + i * 44), line, font=ref_font, fill=(212, 175, 55, 180), anchor="mt")

    quote_lines = textwrap.wrap(quote, width=22)
    total_h = sum(quote_font.getbbox(l)[3] for l in quote_lines) + (len(quote_lines) - 1) * 20
    y = (H - total_h) // 2
    for line in quote_lines:
        draw.text((W // 2, y), line, font=quote_font, fill=(255, 255, 255), anchor="mt")
        y += quote_font.getbbox(line)[3] + 20

    filename  = f"qcard_{int(time.time() * 1000)}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    bg.save(final_path, quality=95)
    return f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"


def draw_starry_noise(draw, size, density=0.0006):
    w, h = size
    count = int(w * h * density)
    for _ in range(count):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        b = random.randint(180, 255)
        a = random.randint(80, 200)
        draw.point((x, y), fill=(b, b, b, a))

def draw_paper_texture(draw, size):
    w, h = size
    for _ in range(6000):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        v = random.randint(0, 20)
        draw.point((x, y), fill=(v, v, v, 18))

def apply_film_noise(size):
    noise = Image.new("RGBA", (size[0] // 4, size[1] // 4), (0, 0, 0, 0))
    nd    = ImageDraw.Draw(noise)
    for _ in range(500):
        x = random.randint(0, noise.width - 1)
        y = random.randint(0, noise.height - 1)
        v = random.randint(0, 20)
        nd.point((x, y), fill=(v, v, v, 25))
    return noise.resize(size, Image.BILINEAR)

def draw_gold_border(draw, size, border_width=30):
    """Draws an elegant layered gold frame with corner accent dots."""
    w, h     = size
    gold     = (200, 162, 42)
    gold_dim = (148, 118, 30)
    m        = border_width
    draw.rectangle([m, m, w - m, h - m], outline=gold, width=3)
    draw.rectangle([m + 12, m + 12, w - m - 12, h - m - 12], outline=gold_dim, width=1)
    dot_r = 5
    for cx, cy in [(m + 3, m + 3), (w - m - 3, m + 3), (m + 3, h - m - 3), (w - m - 3, h - m - 3)]:
        draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=gold)

def draw_text_highlight(draw, bbox, bg_color):
    padding = 25
    draw.rounded_rectangle(
        [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding],
        radius=15, fill=bg_color
    )

def draw_radial_gradient(draw, size, color_start, color_end):
    width, height = size
    center_x, center_y = width / 2, height / 2
    max_dist = math.sqrt(center_x ** 2 + center_y ** 2)
    steps = 50
    for i in range(steps, 0, -1):
        ratio   = i / steps
        radius  = max_dist * ratio
        c_ratio = 1 - ratio
        r = int(color_start[0] * (1 - c_ratio) + color_end[0] * c_ratio)
        g = int(color_start[1] * (1 - c_ratio) + color_end[1] * c_ratio)
        b = int(color_start[2] * (1 - c_ratio) + color_end[2] * c_ratio)
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            fill=(r, g, b)
        )

def draw_islamic_pattern(draw, size, color):
    """Large, elegant sparse Islamic geometric ornaments at corners and center."""
    w, h = size
    if len(color) == 4:
        r, g, b, a = color
        blend = a / 255.0
        col   = tuple(int(c * blend) for c in (r, g, b))
    else:
        col = color

    positions = [
        (w // 2, h // 2), (180, 180), (w - 180, 180),
        (180, h - 180),   (w - 180, h - 180),
    ]
    sizes  = [260, 110, 110, 110, 110]

    for (cx, cy), s in zip(positions, sizes):
        draw.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], outline=col, width=2)
        sq = int(s * 0.68)
        draw.rectangle([cx - sq, cy - sq, cx + sq, cy + sq], outline=col, width=1)
        dot = int(s * 0.14)
        draw.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], outline=col, width=1)

def apply_vignette(image, intensity=0.6):
    width, height = image.size
    overlay  = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw     = ImageDraw.Draw(overlay)
    center_x, center_y = width / 2, height / 2
    max_dist = math.sqrt(center_x ** 2 + center_y ** 2)
    steps    = 32
    for i in range(steps):
        dist_ratio = i / steps
        alpha  = int((dist_ratio ** 2.5) * 255 * intensity)
        radius = max_dist * (1 - dist_ratio)
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            fill=(0, 0, 0, alpha)
        )
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

def apply_cinematic_layers(image, glow_color=None):
    """Premium film grain + center glow + corner blooms."""
    w, h = image.size

    # 1. Film Grain
    grain = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd    = ImageDraw.Draw(grain)
    for _ in range(3200):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        b = random.randint(210, 255)
        gd.point((x, y), fill=(b, b, b, 9))

    # 2. Center glow
    cx_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cx_layer)
    cx, cy = w // 2, h // 2
    gc = tuple(glow_color[:3]) + (12,) if glow_color else (255, 245, 220, 12)
    cd.ellipse([cx - 480, cy - 480, cx + 480, cy + 480], fill=gc)
    cx_layer = cx_layer.filter(ImageFilter.GaussianBlur(185))

    # 3. Corner bloom
    bloom = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd    = ImageDraw.Draw(bloom)
    bd.ellipse([-260, -260, 440, 440], fill=(255, 215, 160, 15))
    bd.ellipse([w - 440, h - 440, w + 260, h + 260], fill=(160, 210, 255, 12))
    bloom = bloom.filter(ImageFilter.GaussianBlur(120))

    res = image.convert("RGBA")
    res = Image.alpha_composite(res, cx_layer)
    res = Image.alpha_composite(res, grain)
    res = Image.alpha_composite(res, bloom)
    return res.convert("RGB")


def get_font_for_char(char, primary_font, primary_size):
    if char == '\ufdfa' or '\u0600' <= char <= '\u06ff' or '\ufb50' <= char <= '\ufdff':
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        fallback  = os.path.join(base_dir, "assets", "fonts", "Amiri-Regular.ttf")
        return ImageFont.truetype(fallback, primary_size)
    return primary_font


# ══════════════════════════════════════════════════════════════════════════════
# PRESET STYLE DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

PRESET_BACKGROUNDS = {
    "quran": {
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (0, 60, 30), (0, 10, 5)),
            draw_islamic_pattern(draw, ts, (190, 152, 42, 28)),
        ),
        "base_color": (0, 10, 5),
        "post_vignette": 0.72,
        "border": True,
        "border_width": 32,
        "glow": (170, 225, 175, 52),
    },
    "fajr": {
        "base_color": (5, 8, 28),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (14, 22, 72), (3, 5, 20)),
            draw_starry_noise(draw, ts, density=0.0005),
        ),
        "post_vignette": 0.52,
        "border": False,
        "glow": (120, 160, 255, 62),
    },
    "scholar": {
        "base_color": (245, 240, 225),
        "build": lambda bg, draw, ts: draw_paper_texture(draw, ts),
        "post_vignette": 0.06,
        "border": False,
        "glow": None,
    },
    "madinah": {
        "base_color": (14, 8, 2),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (50, 27, 5), (12, 7, 1)),
            draw_islamic_pattern(draw, ts, (196, 154, 62, 36)),
        ),
        "post_vignette": 0.62,
        "border": True,
        "border_width": 28,
        "glow": (222, 182, 82, 48),
    },
    "kaaba": {
        "base_color": (0, 0, 0),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (14, 14, 14), (0, 0, 0)),
            draw_islamic_pattern(draw, ts, (178, 148, 50, 16)),
        ),
        "post_vignette": 0.38,
        "border": True,
        "border_width": 24,
        "glow": (200, 164, 44, 38),
    },
    "laylulqadr": {
        "base_color": (8, 0, 22),
        "build": lambda bg, draw, ts: (
            draw_radial_gradient(draw, ts, (36, 10, 84), (6, 0, 22)),
            draw_starry_noise(draw, ts, density=0.0007),
        ),
        "post_vignette": 0.48,
        "border": False,
        "glow": (165, 105, 255, 68),
    },
}

# Text palettes per preset
PRESET_TEXT = {
    "quran":      [(212, 175, 55), (255, 255, 255), (195, 215, 195)],
    "fajr":       [(140, 170, 245), (230, 238, 255), (170, 195, 240)],
    "scholar":    [(45, 42, 38), (22, 20, 18), (68, 62, 55)],
    "madinah":    [(212, 165, 60), (255, 242, 210), (200, 175, 130)],
    "kaaba":      [(180, 148, 50), (255, 255, 255), (185, 185, 185)],
    "laylulqadr": [(180, 145, 235), (238, 230, 255), (195, 175, 240)],
}

# White-text palette for custom dark backgrounds
CUSTOM_TEXT_LIGHT = [(212, 175, 55), (255, 255, 255), (210, 210, 210)]  # gold ref + white quote + grey support
CUSTOM_TEXT_DARK  = [(60, 50, 38), (28, 24, 20), (75, 68, 58)]  # dark ink for parchment


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def render_minimal_quote_card(
    segments: list,
    output_dir: str,
    style: str = "quran",
    visual_prompt: str = None,
    mode: str = "preset"           # "preset" | "custom"
) -> str:
    """
    Designer Engine v5.0 — Strict Dual-Mode Pipeline.

    Modes:
      preset  → uses PRESET_BACKGROUNDS[style] for bg, PRESET_TEXT[style] for colors
      custom  → uses visual_prompt to generate bg via interpret_visual_prompt()
                 font colors are white-hierarchy (good on any dark bg)
    """
    target_size = (1080, 1080)
    W, H = target_size
    base_dir  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print(f"\n{'='*60}")
    print(f"🎨 [Renderer] mode={mode} | style={style}")
    print(f"📝 [Renderer] visual_prompt={repr(visual_prompt)}")
    print(f"📦 [Renderer] segments={len(segments)}")
    print(f"{'='*60}")

    # ── STEP 1: Resolve text colors per segment ───────────────────────────────
    # Determine color palette before building background
    if mode == "custom":
        overrides = analyze_style_prompt(visual_prompt or "", style)
        is_light  = overrides.get("is_light_bg", False) if overrides else False
        palette   = CUSTOM_TEXT_DARK if is_light else CUSTOM_TEXT_LIGHT
        print(f"🖌️  [Renderer] custom mode — palette={'dark-ink' if is_light else 'white-light'}")
    else:
        # Preset mode
        overrides = None
        palette   = PRESET_TEXT.get(style, PRESET_TEXT["quran"])
        print(f"🖌️  [Renderer] preset mode — palette from '{style}'")

    # ── STEP 2: Font selection ────────────────────────────────────────────────
    use_serif = (style in ("scholar", "madinah") and mode == "preset")
    font_file = "Amiri-Regular.ttf" if use_serif else "Inter.ttf"
    font_path = os.path.join(base_dir, "assets", "fonts", font_file)
    print(f"🔤 [Renderer] font={font_file}")

    # ── STEP 3: Background construction ──────────────────────────────────────
    glow_rgba = None

    if mode == "custom" and overrides:
        # ── CUSTOM BACKGROUND ──────────────────────────────────────────────
        bg_start   = tuple(overrides.get("bg_start_rgb", [18, 18, 18]))
        bg_end     = tuple(overrides.get("bg_end_rgb",   [4,  4,  4]))
        v_intensity = overrides.get("vignette", 0.65)
        border_type = overrides.get("border", "none")
        p_type      = overrides.get("pattern_type", "none")
        p_rgba      = tuple(overrides.get("pattern_color_rgba", [255, 255, 255, 0]))
        g_type      = overrides.get("gradient_type", "radial")
        glow_rgba   = tuple(overrides.get("glow_color_rgba", [255, 245, 220, 50]))

        print(f"🎨 [Renderer] Custom bg: start={bg_start} end={bg_end} border={border_type} pattern={p_type}")

        bg   = Image.new("RGB", target_size, bg_end)
        draw = ImageDraw.Draw(bg)
        if g_type == "radial":
            draw_radial_gradient(draw, target_size, bg_start, bg_end)
        if p_type == "islamic":
            draw_islamic_pattern(draw, target_size, p_rgba)
        elif p_type == "starry":
            draw_starry_noise(draw, target_size)
        elif p_type == "paper":
            draw_paper_texture(draw, target_size)
        bg = apply_vignette(bg, intensity=v_intensity)
        if border_type == "gold":
            draw = ImageDraw.Draw(bg)
            draw_gold_border(draw, target_size)

    elif mode == "preset" or (mode == "custom" and not overrides):
        # ── PRESET BACKGROUND ─────────────────────────────────────────────
        effective = style if style in PRESET_BACKGROUNDS else "quran"
        print(f"🎨 [Renderer] Preset bg: '{effective}'")
        spec = PRESET_BACKGROUNDS[effective]
        bg   = Image.new("RGB", target_size, spec["base_color"])
        draw = ImageDraw.Draw(bg)
        spec["build"](bg, draw, target_size)
        bg   = apply_vignette(bg, intensity=spec["post_vignette"])
        if spec.get("border"):
            draw = ImageDraw.Draw(bg)
            draw_gold_border(draw, target_size, border_width=spec.get("border_width", 30))
        glow_rgba = spec.get("glow")

    else:
        bg = Image.new("RGB", target_size, (10, 10, 10))

    draw = ImageDraw.Draw(bg)

    # ── STEP 4: Zone layout ───────────────────────────────────────────────────
    v_pad_min    = 80
    zone_ref_w   = int(W * 0.72)
    zone_quote_w = int(W * 0.80)
    zone_supp_w  = int(W * 0.74)
    ls_ref       = 18
    ls_quote     = 28
    ls_supp      = 20
    gap_ref_to_quote  = 52
    gap_quote_to_supp = 42

    zone_constraints = [
        (zone_ref_w,   ls_ref,   0),
        (zone_quote_w, ls_quote, 1),
        (zone_supp_w,  ls_supp,  2),
    ]

    # ── STEP 5: Pre-calculation pass ─────────────────────────────────────────
    zone_data = []

    for i, seg in enumerate(segments):
        if i >= len(zone_constraints):
            break
        z_width, z_ls, _ = zone_constraints[i]

        color = palette[i] if i < len(palette) else palette[-1]

        # Override segment color with resolved palette
        seg = dict(seg)
        seg["color"] = color

        try:
            curr_font = ImageFont.truetype(font_path, seg["size"])
        except:
            curr_font = ImageFont.load_default()

        avg_char_w = seg["size"] * 0.54
        wrap_chars = max(10, int(z_width / avg_char_w))

        raw_lines = textwrap.wrap(seg["text"], width=wrap_chars)
        if i == 0 and len(raw_lines) > 2:
            raw_lines = raw_lines[:2]
            raw_lines[-1] = raw_lines[-1].rstrip() + "…"

        line_data = []
        block_h   = 0
        for line in raw_lines:
            bbox = draw.textbbox((0, 0), line, font=curr_font)
            lh   = bbox[3] - bbox[1]
            lw   = bbox[2] - bbox[0]
            line_data.append({"text": line, "h": lh, "w": lw})
            block_h += lh + z_ls
        if block_h > 0:
            block_h -= z_ls

        zone_data.append({
            "font":    curr_font,
            "lines":   line_data,
            "block_h": block_h,
            "color":   color,
            "ls":      z_ls,
            "width":   z_width,
        })
        print(f"   Zone {i}: {len(line_data)} lines, block_h={block_h}px, font_size={seg['size']}")

    # ── STEP 6: Optical centering ─────────────────────────────────────────────
    total_h = 0
    for idx, zd in enumerate(zone_data):
        total_h += zd["block_h"]
        if idx == 0 and len(zone_data) > 1:
            total_h += gap_ref_to_quote
        elif idx == 1 and len(zone_data) > 2:
            total_h += gap_quote_to_supp

    optical_offset = int(H * 0.03)
    start_y = (H // 2) - (total_h // 2) - optical_offset
    start_y = max(v_pad_min, start_y)
    print(f"📐 [Renderer] total_h={total_h}px start_y={start_y}px")

    # ── STEP 7: Glow layer under Zone B ──────────────────────────────────────
    bg_rgba = bg.convert("RGBA")

    for i, zd in enumerate(zone_data):
        if i == 1 and glow_rgba:
            glow_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_layer)
            ty_g = start_y + zone_data[0]["block_h"] + gap_ref_to_quote if len(zone_data) > 1 else start_y
            cx   = W // 2
            for ln in zd["lines"]:
                gd.text((cx, ty_g), ln["text"], font=zd["font"], fill=glow_rgba, anchor="mt")
                ty_g += ln["h"] + zd["ls"]
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(30))
            bg_rgba = Image.alpha_composite(bg_rgba, glow_layer)
            break

    # ── STEP 8: Drawing pass ──────────────────────────────────────────────────
    draw_rgba = ImageDraw.Draw(bg_rgba)
    center_x  = W // 2
    y         = start_y

    for i, zd in enumerate(zone_data):
        ty = y
        for ln in zd["lines"]:
            col = zd["color"]

            if i == 0:  # Zone A — Reference (slightly transparent)
                rgba_col = (col[0], col[1], col[2], 178)
                draw_rgba.text((center_x, ty), ln["text"], font=zd["font"], fill=rgba_col, anchor="mt")

            elif i == 1:  # Zone B — Main Quote + shadow
                draw_rgba.text((center_x + 2, ty + 2), ln["text"], font=zd["font"], fill=(0, 0, 0, 85), anchor="mt")
                draw_rgba.text((center_x, ty),     ln["text"], font=zd["font"], fill=col, anchor="mt")

            else:  # Zone C — Supporting
                rgba_col = (col[0], col[1], col[2], 215)
                draw_rgba.text((center_x, ty), ln["text"], font=zd["font"], fill=rgba_col, anchor="mt")

            ty += ln["h"] + zd["ls"]

        y = ty - zd["ls"]
        if i == 0:
            y += gap_ref_to_quote
        elif i == 1:
            y += gap_quote_to_supp

    # ── STEP 9: Cinematic post-processing ─────────────────────────────────────
    final_img = apply_cinematic_layers(bg_rgba, glow_color=list(glow_rgba) if glow_rgba else None)

    filename   = f"qcard_{int(time.time() * 1000)}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    final_img.save(final_path, quality=95)

    print(f"✅ [Renderer] Saved: {filename} (mode={mode}, style={style}, prompt={'YES' if visual_prompt else 'NO'})")
    print(f"{'='*60}\n")

    return f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
