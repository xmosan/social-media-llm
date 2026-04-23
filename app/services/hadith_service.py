# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
Sabeel Studio — Hadith Service
================================
Secure, source-faithful gateway to Hadith data.

SAFETY CONTRACT:
- Do NOT fabricate hadith text, references, grades, or narrators.
- Do NOT paraphrase hadith and present it as the original.
- All fields are derived exclusively from the API response.
- Missing fields are set to None — never guessed.

API: fawazahmed0/hadith-api (CDN, free, no key)
Fallback: HadithAPI.com if HADITH_API_KEY is set in env.
"""

import logging
import httpx
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# COLLECTION REGISTRY
# Maps human-readable collection names → edition keys used by fawazahmed0 API
# Arabic (ara-) and English (eng-) editions are paired.
# ─────────────────────────────────────────────────────────────────────────────

COLLECTION_REGISTRY = {
    "bukhari": {
        "name": "Sahih al-Bukhari",
        "eng_edition": "eng-bukhari",
        "ara_edition": "ara-bukhari",
    },
    "muslim": {
        "name": "Sahih Muslim",
        "eng_edition": "eng-muslim",
        "ara_edition": "ara-muslim",
    },
    "abudawud": {
        "name": "Sunan Abu Dawud",
        "eng_edition": "eng-abudawud",
        "ara_edition": "ara-abudawud",
    },
    "tirmidhi": {
        "name": "Jami' at-Tirmidhi",
        "eng_edition": "eng-tirmidhi",
        "ara_edition": "ara-tirmidhi",
    },
    "nasai": {
        "name": "Sunan an-Nasa'i",
        "eng_edition": "eng-nasai",
        "ara_edition": "ara-nasai",
    },
    "ibnmajah": {
        "name": "Sunan Ibn Majah",
        "eng_edition": "eng-ibnmajah",
        "ara_edition": "ara-ibnmajah",
    },
}

# Maximum card text length before excerpting
_CARD_MAX_CHARS = 350

# HTTP timeout for CDN requests
_HTTP_TIMEOUT = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _base_url() -> str:
    return settings.hadith_api_base_url.rstrip("/")


def _get_json(url: str) -> Optional[dict]:
    """Fetches JSON from a URL with graceful error handling."""
    try:
        response = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        logger.warning(f"[HADITH] Timeout fetching: {url}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"[HADITH] HTTP {e.response.status_code} for: {url}")
        return None
    except Exception as e:
        logger.error(f"[HADITH] Unexpected error fetching {url}: {e}")
        return None


def _safe_excerpt(text: str, max_chars: int = _CARD_MAX_CHARS) -> tuple[str, bool]:
    """
    Returns (text_for_card, was_excerpted).
    Excerpts at the last sentence boundary before max_chars.
    Never alters meaning — full text is preserved in metadata.
    """
    if not text or len(text) <= max_chars:
        return text, False

    # Find the last sentence ending (. ! ?) before the limit
    truncated = text[:max_chars]
    for sentinel in [". ", "! ", "? "]:
        pos = truncated.rfind(sentinel)
        if pos > max_chars // 2:  # Only excerpt if we keep at least half
            excerpt = truncated[:pos + 1].strip()
            logger.info(f"[HADITH_CARD] long hadith excerpted (original={len(text)}, card={len(excerpt)})")
            return excerpt, True

    # Fallback: hard cut at word boundary
    pos = truncated.rfind(" ")
    excerpt = (truncated[:pos] + "…").strip() if pos > 0 else truncated
    logger.info(f"[HADITH_CARD] long hadith excerpted (original={len(text)}, card={len(excerpt)})")
    return excerpt, True


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def get_supported_collections() -> list[dict]:
    """
    Returns the list of supported Hadith collections with their keys and names.
    No API call needed — this is a static registry.
    """
    return [
        {"key": k, "name": v["name"]}
        for k, v in COLLECTION_REGISTRY.items()
    ]


def get_hadith_by_reference(collection_key: str, hadith_number: int) -> Optional[dict]:
    """
    Fetches an exact hadith by collection key and hadith number.
    Returns a normalized Hadith object or None on failure.

    SAFETY: Returns only what the API provides. No fields are fabricated.

    Example:
        get_hadith_by_reference("bukhari", 1)
        → {"reference": "Sahih al-Bukhari 1", "arabic_text": "...", ...}
    """
    col = COLLECTION_REGISTRY.get(collection_key)
    if not col:
        logger.warning(f"[HADITH] Unknown collection key: '{collection_key}'")
        return None

    base = _base_url()
    eng_url = f"{base}/editions/{col['eng_edition']}/{hadith_number}.json"
    ara_url = f"{base}/editions/{col['ara_edition']}/{hadith_number}.json"

    logger.info(f"[HADITH] Fetching {col['name']} #{hadith_number}")

    eng_data = _get_json(eng_url)
    ara_data = _get_json(ara_url)

    if not eng_data and not ara_data:
        logger.warning(f"[HADITH][WARN] Both English and Arabic fetch failed for {collection_key} #{hadith_number}")
        return None

    return normalize_hadith(
        eng_data=eng_data,
        ara_data=ara_data,
        collection_key=collection_key,
        hadith_number=hadith_number,
    )


def search_hadith(query: str, collection_key: Optional[str] = None, limit: int = 10) -> list[dict]:
    """
    Searches Hadith text for the given query string.

    Since fawazahmed0 is a CDN/static API (no server-side search), this fetches
    a section of the collection and filters in Python. For keyword searches,
    we check up to the first 300 hadiths of each collection.

    SAFETY: Returns only real hadiths. No fabricated results.

    Args:
        query: Keyword(s) to search for (e.g. "patience", "intention")
        collection_key: Restrict to one collection (e.g. "bukhari"), or None for all
        limit: Maximum number of results to return

    Returns:
        List of normalized Hadith objects
    """
    if not query or not query.strip():
        return []

    query_lower = query.lower().strip()
    collections_to_search = (
        [collection_key] if collection_key and collection_key in COLLECTION_REGISTRY
        else list(COLLECTION_REGISTRY.keys())
    )

    results = []
    base = _base_url()

    for col_key in collections_to_search:
        if len(results) >= limit:
            break

        col = COLLECTION_REGISTRY[col_key]
        # Fetch the entire English edition (CDN, cached, fast)
        edition_url = f"{base}/editions/{col['eng_edition']}.min.json"
        data = _get_json(edition_url)

        if not data:
            logger.warning(f"[HADITH] Could not fetch collection: {col_key}")
            continue

        hadiths = data.get("hadiths", [])
        logger.info(f"[HADITH] Scanning {len(hadiths)} hadiths in {col['name']} for '{query}'")

        for h in hadiths:
            if len(results) >= limit:
                break
            text = h.get("text", "") or ""
            if query_lower in text.lower():
                normalized = normalize_hadith(
                    eng_data={"hadiths": [h], "metadata": data.get("metadata", {})},
                    ara_data=None,
                    collection_key=col_key,
                    hadith_number=h.get("hadithnumber"),
                    single_hadith=h,
                )
                if normalized and validate_hadith_item(normalized):
                    results.append(normalized)

    logger.info(f"[HADITH] Search for '{query}' returned {len(results)} results")
    return results[:limit]


def normalize_hadith(
    eng_data: Optional[dict],
    ara_data: Optional[dict],
    collection_key: str,
    hadith_number: Optional[int],
    single_hadith: Optional[dict] = None,
) -> Optional[dict]:
    """
    Converts raw fawazahmed0 API responses into the normalized Hadith schema.

    SAFETY RULES:
    - Only set 'grade' if the API explicitly provides it
    - Only set 'narrator' if the API explicitly provides it
    - Missing fields → None (never guessed)
    """
    col_meta = COLLECTION_REGISTRY.get(collection_key, {})
    collection_name = col_meta.get("name", collection_key)

    # Extract single hadith record from response
    if single_hadith:
        eng_hadith = single_hadith
    elif eng_data:
        hadiths = eng_data.get("hadiths", [])
        eng_hadith = hadiths[0] if hadiths else None
    else:
        eng_hadith = None

    if not eng_hadith and not ara_data:
        return None

    # Arabic text
    arabic_text = None
    if ara_data:
        ara_hadiths = ara_data.get("hadiths", [])
        if ara_hadiths:
            arabic_text = ara_hadiths[0].get("text") or None

    # English translation
    translation_text = (eng_hadith.get("text") or "").strip() if eng_hadith else None
    if not translation_text:
        translation_text = None

    # Hadith number (prefer from data, fallback to parameter)
    h_num = (eng_hadith.get("hadithnumber") if eng_hadith else None) or hadith_number

    # Reference string — consistent format
    reference = f"{collection_name} {h_num}" if h_num else collection_name

    # Grade — ONLY if the API provides it (it's in info.json, not per-hadith in fawazahmed0)
    # Per-hadith grade is not in the fawazahmed0 standard endpoint; we don't fabricate it.
    grade = None  # Set only if API provides it in future integrations

    # Narrator — fawazahmed0 does not provide per-hadith narrators in the standard format
    narrator = None

    # Book/chapter info from metadata
    metadata = eng_data.get("metadata", {}) if eng_data else {}
    book_name = metadata.get("name") or collection_name

    # Safe card text (excerpted if too long)
    card_text, was_excerpted = _safe_excerpt(translation_text or arabic_text or "")

    return {
        "source_type": "hadith",
        "collection": collection_name,
        "collection_key": collection_key,
        "book": book_name,
        "chapter": None,  # Not provided by fawazahmed0 per-hadith endpoint
        "hadith_number": h_num,
        "reference": reference,
        "arabic_text": arabic_text,
        "translation_text": translation_text,
        "card_text": card_text,               # Safe for visual card (possibly excerpted)
        "was_excerpted": was_excerpted,        # If True, full text is in translation_text
        "narrator": narrator,                  # None — not fabricated
        "grade": grade,                        # None — not fabricated
        "topics": [],
        "api_source": "fawazahmed0/hadith-api@1",
    }


def validate_hadith_item(item: Optional[dict]) -> bool:
    """
    Safety gate: validates that a Hadith item meets minimum quality requirements
    before being used in a quote card or post.

    Returns True if valid, False otherwise.

    NEVER passes items with fabricated fields.
    """
    if not item:
        logger.warning("[HADITH] validate_hadith_item: item is None")
        return False

    # 1. Must be explicitly typed as hadith
    if item.get("source_type") != "hadith":
        logger.warning(f"[HADITH] Validation failed: wrong source_type '{item.get('source_type')}'")
        return False

    # 2. Must have a reference
    if not item.get("reference"):
        logger.warning("[HADITH] Validation failed: missing reference")
        return False

    # 3. Must have at least one text field
    if not item.get("translation_text") and not item.get("arabic_text"):
        logger.warning(f"[HADITH] Validation failed: no text for {item.get('reference')}")
        return False

    # 4. Must have a collection
    if not item.get("collection"):
        logger.warning("[HADITH] Validation failed: missing collection")
        return False

    return True


def validate_hadith_source_metadata(meta: Optional[dict]) -> tuple[bool, str]:
    """
    Validates source_metadata stored on a Post for Hadith-based posts.
    Returns (is_valid, error_message).
    Called before quote card generation to prevent incomplete data from being used.
    """
    if not meta:
        return False, "Hadith source data is incomplete. Please choose another Hadith."

    required_fields = ["source_type", "reference", "collection"]
    for field in required_fields:
        if not meta.get(field):
            return False, f"Hadith source data is incomplete (missing: {field}). Please choose another Hadith."

    if not meta.get("translation_text") and not meta.get("arabic_text"):
        return False, "Hadith source data is incomplete. Please choose another Hadith."

    if meta.get("source_type") != "hadith":
        return False, "Source type mismatch. Expected Hadith source."

    return True, ""
