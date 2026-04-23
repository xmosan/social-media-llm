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

PROVIDER SELECTION (auto, based on env vars):
  Primary:  sunnah.com API (https://api.sunnah.com/v1)
            Requires: HADITH_API_KEY
            Auth:     X-API-Key header
  Fallback: fawazahmed0 CDN (no key needed, CDN-based, no real search)
            Used ONLY if HADITH_API_KEY is not set.

Log at startup:
  [HADITH] provider=sunnah_now  (key present)
  [HADITH] provider=fallback_cdn (key missing)
"""

import logging
import httpx
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def _active_provider() -> str:
    """
    Returns the provider mode string based on current config.
    'sunnah_now'   → use sunnah.com API with key
    'fallback_cdn' → use fawazahmed0 CDN
    """
    return "sunnah_now" if settings.hadith_api_key else "fallback_cdn"


def _sunnah_now_base() -> str:
    """
    Returns the canonicalized sunnah.com API base URL.
    Handles cases where the env value is missing scheme or /v1.

    HADITH_API_BASE_URL can be:
      api.sunnah.com          → https://api.sunnah.com/v1
      api.sunnah.now          → https://api.sunnah.com/v1  (alias corrected)
      https://api.sunnah.com  → https://api.sunnah.com/v1
    """
    raw = (settings.hadith_api_base_url or "api.sunnah.com").strip().rstrip("/")
    # Normalise: strip any existing scheme
    for prefix in ["https://", "http://"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    # The actual sunnah.com API host is always api.sunnah.com
    # If user has set api.sunnah.now or similar, redirect to the correct host
    if "sunnah" in raw and "sunnah.com" not in raw:
        logger.warning(
            f"[HADITH] HADITH_API_BASE_URL='{raw}' does not look like the sunnah.com API host. "
            "Correcting to 'api.sunnah.com'. Update HADITH_API_BASE_URL=api.sunnah.com in .env."
        )
        raw = "api.sunnah.com"
    # Ensure /v1 suffix
    base = f"https://{raw}"
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _cdn_base() -> str:
    return "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"


# Log provider at module load time
_provider = _active_provider()
if _provider == "sunnah_now":
    logger.info("[HADITH] provider=sunnah_now (api.sunnah.com, key configured)")
else:
    logger.info("[HADITH] provider=fallback_cdn (fawazahmed0, no key set)")


# ─────────────────────────────────────────────────────────────────────────────
# COLLECTION REGISTRY
# Maps Sabeel collection keys → sunnah.com collectionName slugs and display names.
# Also retains fawazahmed0 edition names for CDN fallback mode.
# ─────────────────────────────────────────────────────────────────────────────

COLLECTION_REGISTRY = {
    "bukhari": {
        "name": "Sahih al-Bukhari",
        "sunnah_slug": "bukhari",          # used in api.sunnah.com paths
        "eng_edition": "eng-bukhari",      # fawazahmed0 CDN fallback
        "ara_edition": "ara-bukhari",
    },
    "muslim": {
        "name": "Sahih Muslim",
        "sunnah_slug": "muslim",
        "eng_edition": "eng-muslim",
        "ara_edition": "ara-muslim",
    },
    "abudawud": {
        "name": "Sunan Abu Dawud",
        "sunnah_slug": "abudawud",
        "eng_edition": "eng-abudawud",
        "ara_edition": "ara-abudawud",
    },
    "tirmidhi": {
        "name": "Jami' at-Tirmidhi",
        "sunnah_slug": "tirmidhi",
        "eng_edition": "eng-tirmidhi",
        "ara_edition": "ara-tirmidhi",
    },
    "nasai": {
        "name": "Sunan an-Nasa'i",
        "sunnah_slug": "nasai",
        "eng_edition": "eng-nasai",
        "ara_edition": "ara-nasai",
    },
    "ibnmajah": {
        "name": "Sunan Ibn Majah",
        "sunnah_slug": "ibnmajah",
        "eng_edition": "eng-ibnmajah",
        "ara_edition": "ara-ibnmajah",
    },
}

# Maximum card text length before excerpting
_CARD_MAX_CHARS = 350

# HTTP timeout (sunnah.com is a real API — lower than CDN)
_HTTP_TIMEOUT = 12.0


# ─────────────────────────────────────────────────────────────────────────────
# HTTP HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _sunnah_headers() -> dict:
    """Returns auth headers for sunnah.com API. Never logs the key value."""
    return {
        "X-API-Key": settings.hadith_api_key or "",
        "Accept": "application/json",
    }


def _get_json(url: str, headers: Optional[dict] = None) -> Optional[dict]:
    """Fetches JSON from a URL with graceful error handling."""
    try:
        response = httpx.get(url, headers=headers or {}, timeout=_HTTP_TIMEOUT, follow_redirects=True)
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

    truncated = text[:max_chars]
    for sentinel in [". ", "! ", "? "]:
        pos = truncated.rfind(sentinel)
        if pos > max_chars // 2:
            excerpt = truncated[:pos + 1].strip()
            logger.info(f"[HADITH_CARD] long hadith excerpted (original={len(text)}, card={len(excerpt)})")
            return excerpt, True

    pos = truncated.rfind(" ")
    excerpt = (truncated[:pos] + "…").strip() if pos > 0 else truncated
    logger.info(f"[HADITH_CARD] long hadith excerpted (original={len(text)}, card={len(excerpt)})")
    return excerpt, True


# ─────────────────────────────────────────────────────────────────────────────
# SUNNAH.COM PROVIDER (PRIMARY)
# ─────────────────────────────────────────────────────────────────────────────

def _sunnah_get_hadith_by_reference(collection_key: str, hadith_number: int) -> Optional[dict]:
    """
    Fetches a single hadith from api.sunnah.com using X-API-Key auth.
    Endpoint: GET /v1/collections/{slug}/hadiths/{hadithNumber}

    Response shape (sunnah.com v1):
    {
      "hadith": [{
        "collection": "bukhari",
        "bookNumber": "1",
        "chapterId": "1.00",
        "hadithNumber": "1",
        "hadith": [{
          "lang": "en",
          "chapterNumber": "1",
          "chapterTitle": "...",
          "urn": 123,
          "body": "...",
          "grades": [{"graded_by": "...", "grade": "Sahih"}]
        }, {
          "lang": "ar",
          "body": "..."
        }]
      }]
    }
    """
    col = COLLECTION_REGISTRY.get(collection_key)
    if not col:
        logger.warning(f"[HADITH][sunnah_now] Unknown collection key: '{collection_key}'")
        return None

    slug = col["sunnah_slug"]
    base = _sunnah_now_base()
    url = f"{base}/collections/{slug}/hadiths/{hadith_number}"

    logger.info(f"[HADITH][sunnah_now] GET {url}")
    data = _get_json(url, headers=_sunnah_headers())
    if not data:
        return None

    return _normalize_sunnah_response(data, collection_key, hadith_number)


def _sunnah_search_hadith(query: str, collection_key: Optional[str], limit: int) -> list[dict]:
    """
    Searches hadiths via api.sunnah.com by fetching collection pages and filtering.
    Endpoint: GET /v1/collections/{slug}/hadiths?limit=50&page=1

    sunnah.com does NOT have a text-search endpoint — we paginate and filter locally.
    We scan up to 3 pages (150 hadiths) per collection for speed.
    """
    query_lower = query.lower().strip()
    results = []
    base = _sunnah_now_base()

    collections_to_search = (
        [collection_key] if collection_key and collection_key in COLLECTION_REGISTRY
        else list(COLLECTION_REGISTRY.keys())
    )

    for col_key in collections_to_search:
        if len(results) >= limit:
            break

        col = COLLECTION_REGISTRY[col_key]
        slug = col["sunnah_slug"]

        for page in range(1, 4):  # scan up to 3 pages × 50 hadiths = 150 per collection
            if len(results) >= limit:
                break

            url = f"{base}/collections/{slug}/hadiths?limit=50&page={page}"
            logger.info(f"[HADITH][sunnah_now] scanning {col['name']} page {page}")
            data = _get_json(url, headers=_sunnah_headers())
            if not data:
                break

            hadiths = data.get("data", [])
            if not hadiths:
                break  # no more pages

            for h_wrapper in hadiths:
                if len(results) >= limit:
                    break
                # Each wrapper has a "hadith" list with lang variants
                lang_variants = h_wrapper.get("hadith", [])
                en_variant = next((v for v in lang_variants if v.get("lang") == "en"), None)
                if not en_variant:
                    continue
                body = en_variant.get("body", "") or ""
                if query_lower in body.lower():
                    normalized = _normalize_sunnah_hadith(h_wrapper, col_key)
                    if normalized and validate_hadith_item(normalized):
                        results.append(normalized)

    logger.info(f"[HADITH][sunnah_now] Search '{query}' → {len(results)} results")
    return results[:limit]


def _normalize_sunnah_response(data: dict, collection_key: str, hadith_number: int) -> Optional[dict]:
    """Normalizes a single-hadith response from the sunnah.com API."""
    hadiths = data.get("hadith", [])
    if not hadiths:
        logger.warning(f"[HADITH][sunnah_now] Empty hadith list in response for {collection_key}#{hadith_number}")
        return None
    return _normalize_sunnah_hadith(hadiths[0] if isinstance(hadiths[0], dict) and "hadith" in hadiths[0]
                                    else {"hadith": hadiths, "hadithNumber": str(hadith_number)},
                                    collection_key)


def _normalize_sunnah_hadith(h_wrapper: dict, collection_key: str) -> Optional[dict]:
    """
    Converts a single sunnah.com hadith wrapper object to the normalized schema.

    SAFETY RULES:
    - grade: only set if the API provides it in the 'grades' field
    - narrator: not provided by sunnah.com API at this level → None
    - chapter/book: taken directly from API fields
    """
    col_meta = COLLECTION_REGISTRY.get(collection_key, {})
    collection_name = col_meta.get("name", collection_key)

    lang_variants = h_wrapper.get("hadith", [])
    if not lang_variants:
        return None

    en_variant = next((v for v in lang_variants if v.get("lang") == "en"), None)
    ar_variant = next((v for v in lang_variants if v.get("lang") == "ar"), None)

    translation_text = (en_variant.get("body", "") or "").strip() if en_variant else None
    if not translation_text:
        translation_text = None

    arabic_text = (ar_variant.get("body", "") or "").strip() if ar_variant else None
    if not arabic_text:
        arabic_text = None

    # Hadith number from wrapper
    h_num_raw = h_wrapper.get("hadithNumber") or h_wrapper.get("hadith_number")
    h_num = int(h_num_raw) if h_num_raw and str(h_num_raw).isdigit() else h_num_raw

    # Reference string — consistent format
    reference = f"{collection_name} {h_num}" if h_num else collection_name

    # Grade — ONLY from API 'grades' field; never guessed
    grade = None
    grades_list = (en_variant or {}).get("grades", []) if en_variant else []
    if grades_list:
        # Take the first grade entry's 'grade' value if present
        first_grade = grades_list[0].get("grade") if grades_list else None
        grade = first_grade if first_grade else None  # still None if empty string

    # Narrator — sunnah.com v1 API does not expose narrator per-hadith at this endpoint
    narrator = None

    # Chapter info
    chapter_title = (en_variant or {}).get("chapterTitle") if en_variant else None
    book_number = h_wrapper.get("bookNumber")

    card_text, was_excerpted = _safe_excerpt(translation_text or arabic_text or "")

    return {
        "source_type": "hadith",
        "collection": collection_name,
        "collection_key": collection_key,
        "book": book_number or collection_name,
        "chapter": chapter_title or None,
        "hadith_number": h_num,
        "reference": reference,
        "arabic_text": arabic_text,
        "translation_text": translation_text,
        "card_text": card_text,
        "was_excerpted": was_excerpted,
        "narrator": narrator,       # None — not provided by sunnah.com v1 per-hadith
        "grade": grade,             # From API only — None if not provided
        "topics": [],
        "api_source": "sunnah.com/v1",
    }


# ─────────────────────────────────────────────────────────────────────────────
# FAWAZAHMED0 CDN FALLBACK (used only when no API key is set)
# ─────────────────────────────────────────────────────────────────────────────

def _cdn_get_hadith_by_reference(collection_key: str, hadith_number: int) -> Optional[dict]:
    col = COLLECTION_REGISTRY.get(collection_key)
    if not col:
        return None

    base = _cdn_base()
    eng_url = f"{base}/editions/{col['eng_edition']}/{hadith_number}.json"
    ara_url = f"{base}/editions/{col['ara_edition']}/{hadith_number}.json"

    logger.info(f"[HADITH][fallback_cdn] Fetching {col['name']} #{hadith_number}")
    eng_data = _get_json(eng_url)
    ara_data = _get_json(ara_url)

    if not eng_data and not ara_data:
        return None

    return _normalize_cdn_hadith(eng_data, ara_data, collection_key, hadith_number)


def _cdn_search_hadith(query: str, collection_key: Optional[str], limit: int) -> list[dict]:
    query_lower = query.lower().strip()
    results = []
    base = _cdn_base()

    collections_to_search = (
        [collection_key] if collection_key and collection_key in COLLECTION_REGISTRY
        else list(COLLECTION_REGISTRY.keys())
    )

    for col_key in collections_to_search:
        if len(results) >= limit:
            break

        col = COLLECTION_REGISTRY[col_key]
        edition_url = f"{base}/editions/{col['eng_edition']}.min.json"
        data = _get_json(edition_url)

        if not data:
            logger.warning(f"[HADITH][fallback_cdn] Could not fetch collection: {col_key}")
            continue

        hadiths = data.get("hadiths", [])
        logger.info(f"[HADITH][fallback_cdn] Scanning {len(hadiths)} in {col['name']} for '{query}'")

        for h in hadiths:
            if len(results) >= limit:
                break
            text = h.get("text", "") or ""
            if query_lower in text.lower():
                normalized = _normalize_cdn_hadith(
                    {"hadiths": [h], "metadata": data.get("metadata", {})},
                    None, col_key, h.get("hadithnumber"),
                    single_hadith=h,
                )
                if normalized and validate_hadith_item(normalized):
                    results.append(normalized)

    return results[:limit]


def _normalize_cdn_hadith(
    eng_data: Optional[dict],
    ara_data: Optional[dict],
    collection_key: str,
    hadith_number,
    single_hadith: Optional[dict] = None,
) -> Optional[dict]:
    col_meta = COLLECTION_REGISTRY.get(collection_key, {})
    collection_name = col_meta.get("name", collection_key)

    if single_hadith:
        eng_hadith = single_hadith
    elif eng_data:
        hadiths = eng_data.get("hadiths", [])
        eng_hadith = hadiths[0] if hadiths else None
    else:
        eng_hadith = None

    if not eng_hadith and not ara_data:
        return None

    arabic_text = None
    if ara_data:
        ara_hadiths = ara_data.get("hadiths", [])
        if ara_hadiths:
            arabic_text = (ara_hadiths[0].get("text") or "").strip() or None

    translation_text = (eng_hadith.get("text") or "").strip() if eng_hadith else None
    if not translation_text:
        translation_text = None

    h_num = (eng_hadith.get("hadithnumber") if eng_hadith else None) or hadith_number
    reference = f"{collection_name} {h_num}" if h_num else collection_name

    metadata = eng_data.get("metadata", {}) if eng_data else {}
    book_name = metadata.get("name") or collection_name

    card_text, was_excerpted = _safe_excerpt(translation_text or arabic_text or "")

    return {
        "source_type": "hadith",
        "collection": collection_name,
        "collection_key": collection_key,
        "book": book_name,
        "chapter": None,
        "hadith_number": h_num,
        "reference": reference,
        "arabic_text": arabic_text,
        "translation_text": translation_text,
        "card_text": card_text,
        "was_excerpted": was_excerpted,
        "narrator": None,   # Not provided by CDN
        "grade": None,      # Not provided by CDN
        "topics": [],
        "api_source": "fawazahmed0/hadith-api@1",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — provider-agnostic entrypoints
# ─────────────────────────────────────────────────────────────────────────────

def get_supported_collections() -> list[dict]:
    """
    Returns the list of supported Hadith collections.
    Static registry — no API call needed.
    """
    return [{"key": k, "name": v["name"]} for k, v in COLLECTION_REGISTRY.items()]


def get_hadith_by_reference(collection_key: str, hadith_number: int) -> Optional[dict]:
    """
    Fetches an exact hadith by collection key and hadith number.

    Uses sunnah.com API (primary) if HADITH_API_KEY is set.
    Falls back to fawazahmed0 CDN otherwise.

    SAFETY: Returns only what the API provides. No fields are fabricated.
    """
    provider = _active_provider()
    logger.info(f"[HADITH] get_hadith_by_reference provider={provider} collection={collection_key} #{hadith_number}")

    if provider == "sunnah_now":
        result = _sunnah_get_hadith_by_reference(collection_key, hadith_number)
        if result:
            return result
        logger.warning(f"[HADITH] sunnah_now failed for {collection_key}#{hadith_number} — no CDN fallback in key mode")
        return None
    else:
        return _cdn_get_hadith_by_reference(collection_key, hadith_number)


def search_hadith(query: str, collection_key: Optional[str] = None, limit: int = 10) -> list[dict]:
    """
    Searches Hadith text for the given query string.

    Uses sunnah.com API (primary) if HADITH_API_KEY is set.
    Falls back to fawazahmed0 CDN otherwise.

    SAFETY: Returns only real hadiths. No fabricated results.
    """
    if not query or not query.strip():
        return []

    provider = _active_provider()
    logger.info(f"[HADITH] search_hadith provider={provider} query='{query}' collection={collection_key}")

    if provider == "sunnah_now":
        return _sunnah_search_hadith(query, collection_key, limit)
    else:
        return _cdn_search_hadith(query, collection_key, limit)


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION — provider-independent
# ─────────────────────────────────────────────────────────────────────────────

def validate_hadith_item(item: Optional[dict]) -> bool:
    """
    Safety gate: validates minimum quality requirements before a Hadith is used
    in a quote card or post.

    NEVER passes items with fabricated fields.
    """
    if not item:
        logger.warning("[HADITH] validate_hadith_item: item is None")
        return False

    if item.get("source_type") != "hadith":
        logger.warning(f"[HADITH] Validation failed: wrong source_type '{item.get('source_type')}'")
        return False

    if not item.get("reference"):
        logger.warning("[HADITH] Validation failed: missing reference")
        return False

    if not item.get("translation_text") and not item.get("arabic_text"):
        logger.warning(f"[HADITH] Validation failed: no text for {item.get('reference')}")
        return False

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
