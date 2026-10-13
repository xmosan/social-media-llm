"""Optional presentation metadata; never part of canonical scripture strings."""
import re


def normalize_ornaments(value):
    if not isinstance(value, dict) or set(value) - {"brackets", "verse_number"}:
        raise ValueError("Choose valid Qur’an styling options")
    if any(type(v) is not bool for v in value.values()):
        raise ValueError("Qur’an styling options must be on or off")
    result = {key: value.get(key, False) for key in ("brackets", "verse_number")}
    return result if any(result.values()) else {}


def card_ornaments(card, brand):
    """Only complete, identified Qur’an cards receive decorations.

    Studio validates this card against its canonical library record before
    rendering. Automations build it from their resolved source record. The
    reference is mandatory and remains visible in every rendered page.
    """
    options = (brand or {}).get("quran_ornaments") or {}
    if not options or not card:
        return None
    if not isinstance(card, dict) or not isinstance(card.get("eyebrow", ""), str):
        raise ValueError("Choose a verified Qur’an source before adding ornaments")
    if card.get("hadith_collection") or "was_excerpted" in card:
        return None
    match = re.fullmatch(r"Qur[’']?an ([1-9][0-9]{0,2}):([1-9][0-9]{0,2})", card.get("eyebrow") or "", re.I)
    if not match:
        return None
    surah, ayah = map(int, match.groups())
    from app.services.quran_serialization import SURAH_MAP
    if surah not in SURAH_MAP or not 1 <= ayah <= SURAH_MAP[surah]["verses"]:
        raise ValueError("Choose a verified Qur’an verse before adding ornaments")
    text = card.get("arabic_text") or ""
    if not text or card.get("arabic_display") or card.get("source_complete") is False:
        raise ValueError("Qur’an ornaments require the complete Arabic verse")
    # Provider punctuation stays intact. Avoid adding a second copy of marks
    # already present in the source; these controls never remove source glyphs.
    brackets = options.get("brackets", False) and not any(c in text for c in "\ufd3e\ufd3f")
    number = ayah if options.get("verse_number", False) and "\u06dd" not in text else None
    return {"opening": brackets, "closing": brackets, "verse_number": number}
