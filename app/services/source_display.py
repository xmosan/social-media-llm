"""Explicit display excerpts; the canonical source always remains complete.

No chain parser or LLM selects narrators. Each optional boundary is pinned to an
exact source revision and reference. This first editorial option starts at Umar
and retains his report of the Prophet's words in full. It is not a claim of
qualified scholarly validation; creators must review it in context.
"""
import hashlib

BUKHARI_ONE = "e71c0c2136abd43aa7513403c094a72eacd7daa77c17b94b401e3905cb568b61"


def narration_boundary(card, field):
    """Exact provider-text boundary before the quoted speech, never a parser.

    Typography can subordinate the chain without editing or removing it. A new
    source revision must be inspected before receiving this treatment.
    """
    pins = {
        "arabic_text": (BUKHARI_ONE, 429),
        "headline": ("58a1cf29609a701e2fcf8c9bc8013ad01ca823aeeb342d111ad2bdb586a85dcf", 38),
    }
    text = card.get(field) or ""
    pin = pins.get(field)
    if (card.get("eyebrow") == "Sahih al-Bukhari 1" and pin
            and hashlib.sha256(text.encode()).hexdigest() == pin[0]):
        return pin[1]
    return None


def arabic_display_options(card):
    text = card.get("arabic_text") or ""
    if (card.get("eyebrow") == "Sahih al-Bukhari 1" and
            hashlib.sha256(text.encode()).hexdigest() == BUKHARI_ONE):
        return [{"id": "bukhari-1-umar", "start": 286, "end": len(text), "source_sha256": BUKHARI_ONE,
                 "label": "Arabic excerpt"}]
    return []


def display_range(card):
    if not isinstance(card, dict):
        raise ValueError("Choose a valid source card")
    text = (card or {}).get("arabic_text") or ""
    chosen = (card or {}).get("arabic_display")
    if chosen is None:
        return 0, len(text)
    if chosen not in arabic_display_options(card):
        raise ValueError("This Arabic excerpt is not available for the exact selected source. Use the full narration.")
    return chosen["start"], chosen["end"]


def validate_source_display(card, source_type):
    if card is not None and not isinstance(card, dict):
        raise ValueError("Choose a valid source card")
    if card and card.get("arabic_display") is not None and source_type != "hadith":
        raise ValueError("Qur'an Arabic must be displayed in full")
    display_range(card or {})
