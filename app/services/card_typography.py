"""Measured card typography. Logical source text is never rewritten or truncated."""
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont, features

class CardTypographyError(ValueError):
    """A safe, actionable card validation error for the Studio UI."""


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
        raise CardTypographyError("Arabic text shaping is unavailable; the card was not generated")
    path = (arabic_path or ARABIC_FONT) if contains_arabic(text) else (ARABIC_FONT if serif else LATIN_FONT)
    try:
        return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)
    except OSError:
        raise CardTypographyError("The required card font is unavailable; no substitute was used") from None


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
        start = len(lines)
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
        # Avoid a stranded final Arabic word while preserving logical order and
        # every source character. Only line breaks change, never source text.
        if direction == "rtl" and len(lines)-start >= 2:
            previous, last = lines[-2]["text"].split(), lines[-1]["text"].split()
            while len(previous) > 1 and measure(" ".join(last), font, direction)["width"] < width*.45:
                trial = [previous[-1], *last]
                if (measure(" ".join(trial), font, direction)["width"] > width or
                        measure(" ".join(previous[:-1]), font, direction)["width"] < width*.45):
                    break
                last, previous = trial, previous[:-1]
            lines[-2:] = [measure(" ".join(words), font, direction) for words in (previous, last)]
    return lines


DESIGN_FAMILIES = {"editorial", "quiet_photography", "minimal_paper"}
FEED_LAYOUTS = {"english_first", "bilingual"}


def layout_card(segments, *, serif=False, family="editorial", layout="english_first"):
    """Measured 4:5 feed compositions. Never shrink source text below the floor.

    Long sources need a sequence (not implemented by this single-card renderer).
    All incoming blocks survive reordering, including legacy untyped blocks.
    """
    if layout not in FEED_LAYOUTS:
        raise CardTypographyError("Choose an English-first or bilingual layout")
    segments = [dict(s) for s in segments if str(s.get("text", "")).strip()]
    if not segments:
        raise CardTypographyError("Card text is required")
    for i, seg in enumerate(segments):
        seg.setdefault("role", "reference" if i == 0 and len(segments) > 1 else "source")
    order = ["source_translation", "source_arabic", "source", "reflection", "reference"]
    if layout == "bilingual":
        order[:2] = ["source_arabic", "source_translation"]
    segments.sort(key=lambda s: order.index(s["role"]) if s["role"] in order else 3)
    width, height, margin = 1080, 1350, 88
    short = all(len(s["text"]) <= (80 if s["role"] == "source_arabic" else 100) for s in segments)
    # A photograph occupies a separate, full-width area, never a box behind text.
    photo_height = (430 if short else 280) if family == "quiet_photography" else 0
    available_bottom = height - (photo_height + 64 if photo_height else margin)
    for scale in (1, .92, .84):
        blocks = []
        fits = True
        for seg in segments:
            text, role = str(seg["text"]), seg["role"]
            base, minimum = {"reference": (38, 36), "source_arabic": (82 if short else 68, 56),
                             "reflection": (46, 42)}.get(role, (104 if short else 80, 52))
            size = max(minimum, round(base * scale))
            font = load_font(text, size, serif=serif or family == "minimal_paper")
            lines = wrap(text, font, width - 2 * margin)
            leading = round(size * (.36 if contains_arabic(text) else .30))
            block_height = sum(line["height"] for line in lines) + max(0, len(lines)-1) * leading
            label = None
            label_text = "Reflection" if role == "reflection" else seg.get("label")
            if label_text:
                label_font = load_font(label_text, 34)
                label = {**measure(label_text, label_font), "font": label_font}
                block_height += label["height"] + 18
            fits &= all(line["width"] <= width - 2 * margin for line in lines)
            blocks.append({"role": role, "lines": lines, "font": font, "leading": leading,
                           "height": block_height, "label": label, "size": size,
                           "alignment": "Right" if role == "source_arabic" else "Left",
                           "photo_height": photo_height})
        gap = 72 if short else 38
        references = [b for b in blocks if b["role"] == "reference"]
        body = [b for b in blocks if b["role"] != "reference"]
        footer_height = sum(b["height"] for b in references) + max(0, len(references)-1)*gap
        body_bottom = available_bottom - (footer_height + 64 if references else 0)
        total = sum(b["height"] for b in body) + max(0, len(body)-1)*gap
        if fits and total <= body_bottom - margin:
            # Short cards use deliberate negative space; reference anchors the
            # footer. Medium sources get the full reading column.
            y = margin + min(240 if short else 120, max(0, (body_bottom-margin-total)//(2 if short else 3)))
            for block in body:
                block["y"] = y
                block["bounds"] = (margin, y, width-margin, y+block["height"])
                y += block["height"] + gap
            y = available_bottom-footer_height
            for block in references:
                block["y"] = y
                block["bounds"] = (margin, y, width-margin, y+block["height"])
                y += block["height"] + gap
            return (width, height), body + references
    raise CardTypographyError("This source and reflection are too long for a readable feed card. Choose a shorter complete source or remove the optional reflection. Nothing has been shortened or hidden; long sources need a multi-card sequence.")


def _ink_mask(size, block, alignment):
    mask = Image.new("L", size)
    draw = ImageDraw.Draw(mask)
    left, top, right, _ = block["bounds"]
    y = top
    for line in ([block["label"]] if block["label"] else []) + block["lines"]:
        align = block.get("alignment", alignment)
        if line is block["label"]:
            align = "Left"
        x = left if align == "Left" else right-line["width"] if align == "Right" else (left+right-line["width"])/2
        draw.text((x-line["bbox"][0], y-line["bbox"][1]), line["display"],
                  font=line.get("font", block["font"]), fill=255, direction=line["direction"])
        y += line["height"] + (18 if line is block["label"] else block["leading"])
    return mask


_LINEAR = tuple(v/255/12.92 if v/255 <= .04045 else ((v/255+.055)/1.055)**2.4 for v in range(256))


def _luminance(rgb):
    return .2126*_LINEAR[rgb[0]] + .7152*_LINEAR[rgb[1]] + .0722*_LINEAR[rgb[2]]


def _contrast_at_ink(background, mask, color):
    box = mask.getbbox()
    if box is None:
        raise CardTypographyError("The card contains text that could not be rendered")
    fg = _luminance(color)
    values = [(max(fg, _luminance(rgb))+.05)/(min(fg, _luminance(rgb))+.05)
              for alpha, rgb in zip(mask.crop(box).getdata(), background.crop(box).getdata()) if alpha >= 240]
    if not values:
        raise CardTypographyError("The card text could not be checked for readability")
    return min(values)


def paint_card_text(background, blocks, *, alignment="Left", quality=None):
    """Check the actual opaque glyph footprint, repair globally, then paint.

    No average-brightness proxy and no shadows/panels behind lettering. A 4.8:1
    floor leaves margin above 4.5:1 for JPEG encoding. This is an automated check,
    not certification or a substitute for visual/source review.
    """
    background = background.convert("RGB")
    masks = [_ink_mask(background.size, b, alignment) for b in blocks]
    dark, light = (25, 43, 39), (255, 253, 247)
    repaired = False
    for amount in (0, .35, .60, .80, 1):
        candidate = background if amount == 0 else Image.blend(background, Image.new("RGB", background.size, (248, 246, 239)), amount)
        choices = []
        for mask in masks:
            scores = [(_contrast_at_ink(candidate, mask, color), color) for color in (dark, light)]
            choices.append(max(scores, key=lambda pair: pair[0]))
        if all(score >= 4.8 for score, _ in choices):
            repaired = amount > 0
            break
    else:
        raise CardTypographyError("This composition failed its readability check. Try a quieter background.")
    final = candidate.copy()
    for block, (_, color) in zip(blocks, choices):
        if block["role"] == "reference":
            left, top, right, _ = block["bounds"]
            ImageDraw.Draw(final).line((left, top-26, right, top-26), fill=color, width=2)
    for mask, (_, color) in zip(masks, choices):
        final.paste(color, (0, 0), mask)
    if quality is not None:
        quality.update({"status": "passed", "check": "opaque_glyph_contrast", "minimum_required": 4.8,
                        "background_repaired": repaired, "wash_opacity": amount,
                        "blocks": [{"role": b["role"], "minimum_contrast": round(score, 3),
                                    "font_size": b["size"], "font_at_390px": round(b["size"]*390/1080, 1)}
                                   for b, (score, _) in zip(blocks, choices)],
                        "review_required": True})
    return final
