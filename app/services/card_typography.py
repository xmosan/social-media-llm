"""Measured card typography. Logical source text is never rewritten or truncated."""
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont, features

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
ARABIC_FONT = FONT_DIR / "Amiri-Regular.ttf"
LATIN_FONT = FONT_DIR / "Inter.ttf"


def contains_arabic(text):
    # Includes presentation forms, notably U+FDFA (the ﷺ honorific).
    return any("ARABIC" in unicodedata.name(char, "") for char in text)


def display_text(text):
    # RAQM receives logical Unicode, with original marks and direction controls.
    # Manual reshaping/reversal would double-shape and misplace Qur'anic marks.
    return text


def load_font(text, size, *, serif=False, arabic_path=None):
    if not features.check_feature("raqm"):
        raise ValueError("Arabic text shaping is unavailable; the card was not generated")
    path = (arabic_path or ARABIC_FONT) if contains_arabic(text) else (ARABIC_FONT if serif else LATIN_FONT)
    try:
        return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)
    except OSError:
        raise ValueError("The required card font is unavailable; no substitute was used") from None


def paragraph_direction(text):
    for char in text:
        bidi = unicodedata.bidirectional(char)
        if bidi in {"R", "AL"}:
            return "rtl"
        if bidi == "L":
            return "ltr"
    return "ltr"


def measure(text, font, direction=None):
    visual = display_text(text)
    direction = direction or paragraph_direction(text)
    box = font.getbbox(visual, direction=direction)
    return {"text": text, "display": visual, "bbox": box,
            "width": box[2] - box[0], "height": box[3] - box[1], "direction": direction}


def wrap(text, font, width):
    """Wrap logical words, measuring exactly the glyphs that will be painted."""
    lines = []
    direction = paragraph_direction(text)
    for paragraph in text.splitlines():
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}" if current else word
            if current and measure(trial, font, direction)["width"] > width:
                lines.append(measure(current, font, direction))
                current = word
            else:
                current = trial
        if current:
            lines.append(measure(current, font, direction))
    return lines


def layout_card(segments, *, serif=False):
    """Fit every block, using portrait before resorting to smaller readable type.

    Fail before background generation if a single card cannot contain the text.
    The caller may ask the user to choose a shorter source or omit reflection;
    the renderer never makes that editorial decision on their behalf.
    """
    segments = [dict(s) for s in segments if str(s.get("text", "")).strip()]
    if not segments:
        raise ValueError("Card text is required")
    width, margin, gap = 1080, 96, 36
    for height, scales in ((1080, (1, .95, .9)), (1350, (1, .95, .9, .85, .8, .75, .7))):
        for scale in scales:
            blocks = []
            fits = True
            for index, seg in enumerate(segments):
                text = str(seg["text"])
                role = seg.get("role", "reference" if index == 0 else "source")
                arabic = contains_arabic(text)
                minimum = 32 if role == "reference" else 34 if role == "reflection" else 42 if seg.get("role") == "source_arabic" else 36
                size = max(minimum, round(int(seg.get("size", 48)) * scale))
                font = load_font(text, size, serif=serif)
                lines = wrap(text, font, width - 2 * margin)
                leading = round(size * (.32 if arabic else .28))
                block_height = sum(line["height"] for line in lines) + max(0, len(lines)-1) * leading
                label = None
                if role == "reflection":
                    label_font = load_font("Reflection", 28)
                    label = {**measure("Reflection", label_font), "font": label_font}
                    block_height += label["height"] + 16
                fits &= all(line["width"] <= width - 2 * margin for line in lines)
                blocks.append({"role": role, "lines": lines, "font": font, "leading": leading,
                               "height": block_height, "label": label, "size": size})
            total = sum(b["height"] for b in blocks) + gap * (len(blocks)-1)
            if fits and total <= height - 2 * margin:
                y = (height - total) // 2
                for block in blocks:
                    block["y"] = y
                    block["bounds"] = (margin, y, width-margin, y+block["height"])
                    y += block["height"] + gap
                return (width, height), blocks
    raise ValueError("This source and reflection are too long for a readable card. Choose a shorter source or remove the optional reflection. Your source text has not been shortened.")


def paint_card_text(background, blocks, *, alignment="Center"):
    """Paint measured ink bounds; effects stay behind the source text."""
    layer = Image.new("RGBA", background.size)
    draw = ImageDraw.Draw(layer)
    for block in blocks:
        left, top, right, bottom = block["bounds"]
        sample = background.crop((left, top, right, bottom)).convert("L").resize((1, 1)).getpixel((0, 0))
        color = (24, 22, 19, 255) if sample > 150 else (255, 251, 239, 255)
        if block["role"] == "reference":
            color = (83, 59, 16, 255) if sample > 150 else (234, 204, 132, 255)
        y = top
        lines = block["lines"]
        if block["label"]:
            lines = [block["label"], *lines]
        for line in lines:
            font = line.get("font", block["font"])
            x = left if alignment == "Left" else right-line["width"] if alignment == "Right" else (background.width-line["width"]) / 2
            # Compensate both bearings. Diacritics are part of the measured ink,
            # not an assumed fixed line-height that might clip them.
            pos = (x-line["bbox"][0], y-line["bbox"][1])
            draw.text(pos, line["display"], font=font, fill=color, direction=line["direction"],
                      stroke_width=1, stroke_fill=(0, 0, 0, 90) if sample <= 150 else (255, 255, 255, 90))
            y += line["height"] + (16 if line is block["label"] else block["leading"])
    return Image.alpha_composite(background.convert("RGBA"), layer).convert("RGB")
