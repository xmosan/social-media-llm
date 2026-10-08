"""One workspace identity, consumed by Studio and automation renderers.

Curated palettes and bundled typefaces keep brand choices measurable. A draft's
snapshot is independent of the current workspace default.
"""
import hashlib
import unicodedata
from app.services.vision_families import DESIGN_FAMILIES

PALETTES = {
    "olive": {"paper": (245, 247, 241), "ink": (29, 48, 39), "accent": (72, 99, 63)},
    "ink": {"paper": (244, 246, 249), "ink": (28, 39, 56), "accent": (68, 89, 120)},
    "clay": {"paper": (251, 245, 238), "ink": (67, 40, 34), "accent": (133, 69, 50)},
    "night": {"paper": (23, 35, 40), "ink": (248, 246, 236), "accent": (167, 191, 172)},
}
DEFAULT_BRAND = {"version": 1, "palette": "olive", "typography": "modern", "signature": "",
                 "series_name": "", "family": "editorial", "composition": "varied"}
AUDIENCES = {"english_muslims": "English-speaking Muslims", "new_muslims": "Muslims new to learning about Islam",
             "curious_readers": "Readers exploring Islam", "arabic_readers": "Arabic-speaking Muslims"}
PURPOSES = {"reminder": "A gentle daily reminder", "learn": "Help readers understand this source",
            "reflect": "Invite personal reflection", "practice": "Encourage a small, relevant action"}


def normalize_brand(value=None):
    if value is None:
        return dict(DEFAULT_BRAND)
    if not isinstance(value, dict) or set(value) - set(DEFAULT_BRAND):
        raise ValueError("Choose a valid brand kit")
    result = {**DEFAULT_BRAND, **value}
    enums = {"palette": PALETTES, "typography": {"modern", "classic"},
             "family": DESIGN_FAMILIES,
             "composition": {"varied", "airy", "anchored"}}
    if type(result["version"]) is not int or result["version"] != 1:
        raise ValueError("This brand kit version is unsupported")
    for key, choices in enums.items():
        if not isinstance(result[key], str) or result[key] not in choices:
            raise ValueError(f"Choose a supported brand {key}")
    for key in ("signature", "series_name"):
        text = result[key]
        if (not isinstance(text, str) or len(text) > 48 or
                any(unicodedata.category(c).startswith("C") or c in "\r\n" for c in text)):
            raise ValueError("Creator signature and series name must each be one line of up to 48 characters")
        result[key] = text.strip()
        if any(not (c.isascii() or "ARABIC" in unicodedata.name(c, "") or "LATIN" in unicodedata.name(c, "")
                    or unicodedata.category(c).startswith("M") or 0x2010 <= ord(c) <= 0x2027) for c in text):
            raise ValueError("Creator signature and series name currently support English and Arabic lettering; remove unsupported symbols")
    return result


def workspace_brand(db, org_id):
    from app.models import Org
    org = db.query(Org).filter(Org.id == org_id).first()
    return normalize_brand(org.brand_kit if org else None)


def composition_for(brand, source_key):
    choice = brand["composition"]
    return choice if choice != "varied" else ("airy" if hashlib.sha256(source_key.encode()).digest()[0] % 2 else "anchored")


def editorial_context(audience="english_muslims", purpose="reminder"):
    if audience not in AUDIENCES or purpose not in PURPOSES:
        raise ValueError("Choose an audience and purpose from the available options")
    return (f"Audience: {AUDIENCES[audience]}. Purpose: {PURPOSES[purpose]}. "
            "Apply this only to optional reflection or social copy. Keep all source text and returned attribution exact. "
            "Do not add religious rulings, invented citations, or claims about a reader's faith.")
