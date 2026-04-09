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

def analyze_style_prompt(visual_prompt: str, base_style: str):
    """
    Uses AI to convert a natural language visual prompt into a design config.
    """
    if not visual_prompt or not visual_prompt.strip():
        return None

    client = get_openai_client()
    if not client:
        return None

    system_prompt = """
    You are a luxury Islamic quote card design engine. Your ONLY job is to translate a user's visual
    description into a precise JSON color config. You must be LITERAL and CREATIVE with colors.

    COLOR TRANSLATION RULES (follow these exactly):
    - "marble" or "stone" → bg_start: [35, 35, 38], bg_end: [15, 15, 18], gradient: radial
    - "charcoal" → bg_start: [42, 42, 42], bg_end: [18, 18, 18], gradient: radial
    - "deep green" or "forest" → bg_start: [5, 35, 15], bg_end: [0, 10, 5], gradient: radial
    - "emerald" → bg_start: [0, 60, 30], bg_end: [0, 25, 12], gradient: radial
    - "navy" or "deep blue" → bg_start: [5, 10, 50], bg_end: [0, 5, 25], gradient: radial
    - "celestial" or "night sky" → bg_start: [10, 20, 60], bg_end: [0, 0, 15], pattern: starry
    - "parchment" or "manuscript" or "paper" → bg_start: [245, 235, 210], bg_end: [230, 220, 195], pattern: paper
    - "gold" accent → border: gold
    - "glow" or "halo" → glow_color_rgba: [255, 255, 220, 90]
    - Default text color is WHITE unless background is light-colored (parchment/paper)

    ALWAYS infer colors from keywords. NEVER return default green unless explicitly asked.
    Keep it premium. Avoid neon or oversaturated hues.

    JSON SCHEMA (return ONLY this, no extra text):
    {
      "bg_start_rgb": [r, g, b],
      "bg_end_rgb": [r, g, b],
      "gradient_type": "radial" or "none",
      "pattern_type": "islamic", "starry", "paper", or "none",
      "pattern_color_rgba": [r, g, b, a],
      "vignette": 0.0 to 1.0,
      "border": "gold" or "none",
      "glow_color_rgba": [r, g, b, a]
    }
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Visual Prompt: {visual_prompt}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.5
        )
        config = json.loads(response.choices[0].message.content)
        print(f"🎨 AI Design Config: {config}")
        return config
    except Exception as e:
        print(f"❌ Style analysis error: {e}")
        return None

def render_quote_card(background_local_path: str, quote: str, reference: str, output_dir: str) -> str:
    """
    Renders a 1080x1080 quote card by overlaying text on a background image.
    """
    # 1. Load Background
    try:
        bg = Image.open(background_local_path).convert("RGB")
    except Exception as e:
        print(f"[RENDER] Failed to open background: {e}")
        raise

    # 2. Resize and Center Crop to 1080x1080
    target_size = (1080, 1080)
    bg_ratio = bg.width / bg.height
    target_ratio = target_size[0] / target_size[1]

    if bg_ratio > target_ratio:
        # Background is wider - crop sides
        new_width = int(target_ratio * bg.height)
        offset = (bg.width - new_width) // 2
        bg = bg.crop((offset, 0, offset + new_width, bg.height))
    else:
        # Background is taller - crop top/bottom
        new_height = int(bg.width / target_ratio)
        offset = (bg.height - new_height) // 2
        bg = bg.crop((0, offset, bg.width, offset + new_height))

    bg = bg.resize(target_size, Image.Resampling.LANCZOS)

    # 3. Apply Subtle Dark Gradient/Overlay for readability
    overlay = Image.new("RGBA", target_size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    
    # Simple bottom-heavy gradient
    for i in range(1080):
        # Starts getting darker from 40% down
        if i > 400:
            alpha = int(((i - 400) / 680) * 160) # Max alpha 160
            draw_overlay.line([(0, i), (1080, i)], fill=(0, 0, 0, alpha))
            
    bg.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(bg)

    # 4. Font Loading
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    font_inter_path = os.path.join(base_dir, "assets", "fonts", "Inter.ttf")
    font_amiri_path = os.path.join(base_dir, "assets", "fonts", "Amiri-Regular.ttf")

    # Use Inter for English, Amiri if Arabic detected (simplified: use Inter for all if Amiri missing)
    try:
        font_main = ImageFont.truetype(font_inter_path, 48)
        font_ref = ImageFont.truetype(font_inter_path, 32)
    except:
        font_main = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    # 5. Text Wrapping & Truncation (Guardrail)
    if len(quote) > 240:
        quote = quote[:237] + "..."

    # Wrap text to fit with margins (100px on each side)
    wrapped_lines = textwrap.wrap(quote, width=35) # Approx 35 chars for 48px font

    # Calculate total height of text block
    line_spacing = 15
    line_heights = []
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font_main)
        line_heights.append(bbox[3] - bbox[1])
    
    text_block_height = sum(line_heights) + (len(wrapped_lines) - 1) * line_spacing
    ref_bbox = draw.textbbox((0, 0), reference, font=font_ref)
    ref_height = ref_bbox[3] - ref_bbox[1]
    
    total_height = text_block_height + 60 + ref_height # 60px gap between quote and ref

    # Start drawing from middle-bottom area
    y = (1080 - total_height) // 2 + 50 # Slightly lower than center

    # 6. Draw Text with Shadow (Readability)
    def draw_text_with_shadow(draw_obj, pos, text, font, color, shadow_color=(0, 0, 0, 180)):
        x, y = pos
        # Draw shadow
        draw_obj.text((x + 2, y + 2), text, font=font, fill=shadow_color)
        # Draw main text
        draw_obj.text((x, y), text, font=font, fill=color)

    for i, line in enumerate(wrapped_lines):
        line_w = draw.textbbox((0, 0), line, font=font_main)[2]
        line_x = (1080 - line_w) // 2
        draw_text_with_shadow(draw, (line_x, y), line, font_main, (255, 255, 255))
        y += line_heights[i] + line_spacing

    # Draw Reference
    y += 40
    ref_w = draw.textbbox((0, 0), reference, font=font_ref)[2]
    ref_x = (1080 - ref_w) // 2
    draw_text_with_shadow(draw, (ref_x, y), reference, font_ref, (200, 200, 200))

import random

def draw_paper_texture(draw, size, color=(245, 245, 235)):
    """Fast procedural handmade paper/parchment texture."""
    draw.rectangle([0, 0, size[0], size[1]], fill=color)
    # Create a small noise patch and scale it (Fast)
    ns = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    nd = ImageDraw.Draw(ns)
    for _ in range(1500):
        x, y = random.randint(0, 255), random.randint(0, 255)
        nd.point((x, y), fill=(0, 0, 0, random.randint(5, 15)))
    
    return ns.resize(size, Image.BILINEAR)

def draw_starry_noise(draw, size, density=0.0005):
    """Adds subtle white speckles to simulate a night sky."""
    num_stars = int(size[0] * size[1] * density)
    for _ in range(num_stars):
        x, y = random.randint(0, size[0]-1), random.randint(0, size[1]-1)
        # Varying star size and brightness
        s_size = random.choice([1, 1, 1, 2])
        alpha = random.randint(80, 255)
        if s_size == 1:
            draw.point((x, y), fill=(255, 255, 255, alpha))
        else:
            draw.rectangle([x, y, x+1, y+1], fill=(255, 255, 255, alpha))

def draw_textured_background(draw, size, base_color):
    """Fast dark paper/parchment texture using noise patching."""
    draw.rectangle([0, 0, size[0], size[1]], fill=base_color)
    noise = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    nd = ImageDraw.Draw(noise)
    for _ in range(1500):
        x, y = random.randint(0, 127), random.randint(0, 127)
        v = random.randint(0, 20)
        nd.point((x, y), fill=(v, v, v, 25))
    
    return noise.resize(size, Image.BILINEAR)

def draw_gold_border(draw, size, border_width=30):
    """Draws a frame around the card in Gold with a subtle inner edge."""
    gold_color = (190, 150, 40) # Aged gold
    w, h = size
    # Outer frame
    draw.rectangle([border_width, border_width, w - border_width, h - border_width], 
                   outline=gold_color, width=3)
    # Inner rim
    draw.rectangle([border_width + 10, border_width + 10, w - border_width - 10, h - border_width - 10], 
                   outline=gold_color, width=1)

def draw_text_highlight(draw, bbox, bg_color):
    """Draws a rounded rectangle background behind a text bbox."""
    padding = 25
    draw.rounded_rectangle([bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding], 
                           radius=15, fill=bg_color)

def draw_radial_gradient(draw, size, color_start, color_end):
    """Fast smooth radial gradient with optimized steps."""
    width, height = size
    center_x, center_y = width / 2, height / 2
    max_dist = math.sqrt(center_x**2 + center_y**2)
    # Using 45 steps instead of high iterations is much faster
    steps = 45
    for i in range(steps, 0, -1):
        ratio = i / steps
        radius = max_dist * ratio
        c_ratio = 1 - ratio
        r = int(color_start[0] * (1 - c_ratio) + color_end[0] * c_ratio)
        g = int(color_start[1] * (1 - c_ratio) + color_end[1] * c_ratio)
        b = int(color_start[2] * (1 - c_ratio) + color_end[2] * c_ratio)
        draw.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(r, g, b))

def draw_islamic_pattern(draw, size, color):
    """Draws a visible but subtle Rub el Hizb tile pattern."""
    w, h = size
    step = 140
    for y in range(0, h + step, step):
        for x in range(0, w + step, step):
            s = 25
            draw.polygon([(x-s, y-s), (x+s, y-s), (x+s, y+s), (x-s, y+s)], outline=color, width=1)
            s_diag = int(s * 1.414)
            draw.polygon([(x-s_diag, y), (x, y-s_diag), (x+s_diag, y), (x, y+s_diag)], outline=color, width=1)

def apply_vignette(image, intensity=0.6):
    """Fast vignette overlay using gradient mask."""
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    center_x, center_y = width / 2, height / 2
    max_dist = math.sqrt(center_x**2 + center_y**2)
    
    # Fast concentric circles for vignette
    steps = 30
    for i in range(steps):
        dist_ratio = i / steps
        alpha = int((dist_ratio ** 2.5) * 255 * intensity)
        radius = max_dist * (1 - dist_ratio)
        draw.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(0, 0, 0, alpha))
    
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

def apply_cinematic_layers(image):
    """Adds ultra-premium cinematic overlays: grain and optical bloom."""
    w, h = image.size
    
    # 1. Subtle Film Grain Overlay
    grain_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grain_layer)
    for _ in range(4000):
        x, y = random.randint(0, w-1), random.randint(0, h-1)
        r = random.randint(220, 255)
        gd.point((x, y), fill=(r, r, r, 12))
        
    # 2. Corner Light Blooms (Optical Flares)
    bloom_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bloom_layer)
    # Warm warm glow Top-Left
    bd.ellipse([-300, -300, 500, 500], fill=(255, 210, 160, 22)) 
    # Soft cool glow Bottom-Right
    bd.ellipse([w-500, h-500, w+300, h+300], fill=(160, 210, 255, 18))
    
    bloom_layer = bloom_layer.filter(ImageFilter.GaussianBlur(110))
    
    # Composite
    res = image.convert("RGBA")
    res = Image.alpha_composite(res, grain_layer)
    res = Image.alpha_composite(res, bloom_layer)
    return res.convert("RGB")

def draw_text_with_shadow(draw, position, text, font, fill, shadow_fill=(0, 0, 0, 100), offset=(3, 3)):
    """Draws text with character-level fallback support for Islamic symbols."""
    x, y = position
    # Shadow first
    draw_text_with_fallback(draw, (x + offset[0], y + offset[1]), text, font, fill=shadow_fill)
    # Main text
    draw_text_with_fallback(draw, (x, y), text, font, fill=fill)

def get_font_for_char(char, primary_font, primary_size):
    """Returns the primary font or fallback (Amiri) if the symbol is Arabic."""
    # Specifically catch common Islamic symbols and the Arabic unicode range
    # ﷺ is U+FDFA
    if char == '\ufdfa' or '\u0600' <= char <= '\u06ff' or '\ufb50' <= char <= '\ufdff':
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        fallback_path = os.path.join(base_dir, "assets", "fonts", "Amiri-Regular.ttf")
        return ImageFont.truetype(fallback_path, primary_size)
    return primary_font

def draw_text_with_fallback(draw, position, text, font, fill):
    """Simple character-level fallback drawing."""
    x, y = position
    size = font.size if hasattr(font, 'size') else 40
    for char in text:
        f = get_font_for_char(char, font, size)
        draw.text((x, y), char, font=f, fill=fill)
        # Calculate width
        bbox = draw.textbbox((0, 0), char, font=f)
        x += bbox[2] - bbox[0]

def draw_text_spaced(draw, position, text, font, fill, spacing=2):
    """Draws text with custom letter spacing and font fallback."""
    x, y = position
    size = font.size if hasattr(font, 'size') else 40
    for char in text:
        f = get_font_for_char(char, font, size)
        draw.text((x, y), char, font=f, fill=fill)
        # Advance x by character width + spacing
        bbox = draw.textbbox((0, 0), char, font=f)
        char_w = bbox[2] - bbox[0]
        x += char_w + spacing

def render_minimal_quote_card(segments: list, output_dir: str, style: str = "classic", visual_prompt: str = None) -> str:
    """
    Final Designer Engine v4.0 — 3-Zone Optical Centering.
    Zones: [0] Top Reference | [1] Main Quote | [2] Supporting Line
    Supports both preset styles and custom visual prompt overrides.
    """
    target_size = (1080, 1080)
    W, H = target_size
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # ── 1. BACKGROUND CONSTRUCTION ────────────────────────────────────────────
    # Custom mode: ALWAYS call AI analyzer if a prompt is provided
    overrides = None
    if visual_prompt and visual_prompt.strip():
        overrides = analyze_style_prompt(visual_prompt, style)
    
    # Resolve effective style (for font/text decisions)
    effective_style = style if style != "custom" else "premium"

    # Font selection based on style family
    font_file = "Amiri-Regular.ttf" if effective_style in ["classic", "scholar", "ethereal"] else "Inter.ttf"
    font_path = os.path.join(base_dir, "assets", "fonts", font_file)

    glow_rgba = (255, 255, 255, 70)  # default glow

    if overrides:
        # Custom prompt overrides ALL background settings
        bg_start = tuple(overrides.get("bg_start_rgb", [15, 20, 15]))
        bg_end   = tuple(overrides.get("bg_end_rgb",   [5,  10,  5]))
        v_intensity = overrides.get("vignette", 0.5)
        border_type = overrides.get("border", "none")
        p_type      = overrides.get("pattern_type", "none")
        p_rgba      = tuple(overrides.get("pattern_color_rgba", [255, 255, 255, 30]))
        g_type      = overrides.get("gradient_type", "radial")
        glow_rgba   = tuple(overrides.get("glow_color_rgba", [255, 255, 255, 80]))

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
    else:
        # Preset style backgrounds
        if effective_style == "classic":
            bg   = Image.new("RGB", target_size, (15, 20, 15))
            draw = ImageDraw.Draw(bg)
            draw_textured_background(draw, target_size, (12, 18, 12))
            draw_islamic_pattern(draw, target_size, (180, 140, 50, 45))
            bg   = apply_vignette(bg, intensity=0.45)
            draw = ImageDraw.Draw(bg)
            draw_gold_border(draw, target_size, border_width=40)
        elif effective_style == "modern":
            bg   = Image.new("RGB", target_size, (5, 5, 5))
            draw = ImageDraw.Draw(bg)
            draw_radial_gradient(draw, target_size, (15, 45, 15), (2, 5, 2))
            glow_rgba = (20, 200, 80, 90)
        elif effective_style == "premium":
            bg   = Image.new("RGB", target_size, (0, 0, 0))
            draw = ImageDraw.Draw(bg)
            draw_radial_gradient(draw, target_size, (15, 42, 29), (0, 0, 0))
            bg   = apply_vignette(bg, intensity=0.9)
        elif effective_style == "ethereal":
            bg   = Image.new("RGB", target_size, (255, 255, 255))
            draw = ImageDraw.Draw(bg)
            draw_radial_gradient(draw, target_size, (255, 255, 255), (245, 245, 235))
            bg   = apply_vignette(bg, intensity=0.1)
            glow_rgba = (80, 80, 80, 40)
        elif effective_style == "scholar":
            bg   = Image.new("RGB", target_size, (245, 245, 235))
            draw = ImageDraw.Draw(bg)
            draw_paper_texture(draw, target_size)
            glow_rgba = None
        elif effective_style == "celestial":
            bg   = Image.new("RGB", target_size, (0, 0, 0))
            draw = ImageDraw.Draw(bg)
            draw_radial_gradient(draw, target_size, (10, 25, 60), (0, 0, 0))
            draw_starry_noise(draw, target_size, density=0.0006)
            bg   = apply_vignette(bg, intensity=0.4)
            glow_rgba = (180, 200, 255, 80)
        else:
            bg   = Image.new("RGB", target_size, (20, 20, 20))
            draw = ImageDraw.Draw(bg)

    draw = ImageDraw.Draw(bg)

    # ── 2. ZONE DEFINITIONS ────────────────────────────────────────────────────
    # Safe horizontal margins
    h_pad = 130  # left/right margin
    v_pad_min = 120  # minimum top/bottom vertical safe margin

    # Width constraints per zone
    zone_ref_w   = int(W * 0.68)   # Zone A — Reference (narrower, elegant)
    zone_quote_w = int(W * 0.76)   # Zone B — Main Quote (dominant)
    zone_supp_w  = int(W * 0.70)   # Zone C — Supporting Line

    # Line spacing per zone
    ls_ref   = 22
    ls_quote = 34
    ls_supp  = 26

    # Spacing between zones
    gap_ref_to_quote = 70
    gap_quote_to_supp = 60

    # ── 3. PRE-CALCULATION PASS ────────────────────────────────────────────────
    # Measure all zones BEFORE drawing anything
    zone_data = []  # [{font, lines:[{text,h,w}], block_h, color, zone_ls, zone_w}, ...]

    zone_constraints = [
        (zone_ref_w,   ls_ref,   0),   # Zone A
        (zone_quote_w, ls_quote, 1),   # Zone B
        (zone_supp_w,  ls_supp,  2),   # Zone C
    ]

    for i, seg in enumerate(segments):
        if i >= len(zone_constraints):
            break
        z_width, z_ls, _ = zone_constraints[i]

        try:
            curr_font = ImageFont.truetype(font_path, seg["size"])
        except:
            curr_font = ImageFont.load_default()

        # Smart wrap width: chars ≈ zone_width / (font_size * 0.52)
        avg_char_w = seg["size"] * 0.52
        wrap_chars = max(10, int(z_width / avg_char_w))

        # Zone A hard cap: max 2 lines
        raw_lines = textwrap.wrap(seg["text"], width=wrap_chars)
        if i == 0 and len(raw_lines) > 2:
            raw_lines = raw_lines[:2]
            raw_lines[-1] = raw_lines[-1].rstrip() + "…"

        line_data = []
        block_h = 0
        for line in raw_lines:
            bbox = draw.textbbox((0, 0), line, font=curr_font)
            lh = bbox[3] - bbox[1]
            lw = bbox[2] - bbox[0]
            line_data.append({"text": line, "h": lh, "w": lw})
            block_h += lh + z_ls
        if block_h > 0:
            block_h -= z_ls  # remove trailing spacing

        zone_data.append({
            "font":    curr_font,
            "lines":   line_data,
            "block_h": block_h,
            "color":   seg["color"],
            "ls":      z_ls,
            "width":   z_width,
        })

    # ── 4. OPTICAL CENTERING CALCULATION ──────────────────────────────────────
    total_h = 0
    for idx, zd in enumerate(zone_data):
        total_h += zd["block_h"]
        if idx == 0 and len(zone_data) > 1:
            total_h += gap_ref_to_quote
        elif idx == 1 and len(zone_data) > 2:
            total_h += gap_quote_to_supp

    # Optical center: pull content slightly above mathematical center (~5%)
    center_y = H // 2
    optical_offset = int(H * 0.03)  # 3% upward shift for visual balance
    start_y = center_y - (total_h // 2) - optical_offset
    start_y = max(v_pad_min, start_y)  # enforce minimum top margin

    # ── 5. DRAWING PASS ───────────────────────────────────────────────────────
    bg_rgba = bg.convert("RGBA")
    y = start_y

    for i, zd in enumerate(zone_data):
        # === Zone B: Soft Glow Under Main Quote ===
        if i == 1 and glow_rgba:
            glow_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_layer)
            ty = y
            for ln in zd["lines"]:
                tx = (W - ln["w"]) // 2
                draw_text_with_fallback(gd, (tx, ty), ln["text"], zd["font"], fill=glow_rgba)
                ty += ln["h"] + zd["ls"]
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(28))
            bg_rgba = Image.alpha_composite(bg_rgba, glow_layer)

        # === Text Drawing ===
        draw_rgba = ImageDraw.Draw(bg_rgba)
        ty = y
        for ln in zd["lines"]:
            tx = (W - ln["w"]) // 2  # center-align each line

            if i == 0:  # Zone A — Reference
                sc = zd["color"]
                # Elegant spaced reference text, slightly transparent
                ref_alpha_color = (sc[0], sc[1], sc[2], 170)
                draw_text_spaced(draw_rgba, (tx, ty), ln["text"], zd["font"], fill=ref_alpha_color, spacing=3)

            elif i == 1:  # Zone B — Main Quote (hero)
                draw_text_with_shadow(draw_rgba, (tx, ty), ln["text"], zd["font"], fill=zd["color"])

            else:  # Zone C — Supporting
                draw_text_with_fallback(draw_rgba, (tx, ty), ln["text"], zd["font"], fill=zd["color"])

            ty += ln["h"] + zd["ls"]

        y = ty - zd["ls"]  # remove last trailing space

        # Add zone gaps
        if i == 0:
            y += gap_ref_to_quote
        elif i == 1:
            y += gap_quote_to_supp

    # ── 6. CINEMATIC POST-PROCESSING ──────────────────────────────────────────
    final_img = apply_cinematic_layers(bg_rgba)
    filename = f"qcard_{int(time.time() * 1000)}.jpg"
    final_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    final_img.save(final_path, quality=95)
    print(f"✅ Quote card rendered: {filename} (style={style}, prompt={'yes' if visual_prompt else 'no'})")

    return f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
