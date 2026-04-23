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

PROVIDER: sunnah.now (https://api.sunnah.now)
  Auth:    X-API-Key header (from HADITH_API_KEY env var)
  Docs:    https://docs.sunnah.now
  Routes:  /api/early-access/book/{slug}/hadith         (list, paginated)
           /api/early-access/book/{slug}/hadith/{id}    (specific hadith)
           /api/early-access/books                      (list collections)

FALLBACK: fawazahmed0 CDN (no key, CDN-based, no narrator/grade)
  Used ONLY if HADITH_API_KEY is not set.

Startup log:
  [HADITH] provider=sunnah_now   — key present
  [HADITH] provider=fallback_cdn — key missing

sunnah.now response shape (from official docs at docs.sunnah.now):
{
  "id": 1,
  "metadata": {
    "volume": { "id": 1 },
    "chapter": {
      "id": 1,
      "language": {
        "en": { "text": "Chapter title in English" },
        "ar": { "text": "Chapter title in Arabic" }
      }
    }
  },
  "language": {
    "ar": { "text": "Arabic hadith text..." },
    "en": {
      "narrator": "Narrated 'Umar bin Al-Khattab:",
      "text": "I heard Allah's Messenger (ﷺ) saying..."
    }
  }
}
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
    Returns 'sunnah_now' when HADITH_API_KEY is configured,
    'fallback_cdn' otherwise.
    """
    return "sunnah_now" if settings.hadith_api_key else "fallback_cdn"


def _sunnah_now_base() -> str:
    """
    Returns the canonical sunnah.now API base URL.
    HADITH_API_BASE_URL can be bare host or full URL — both are normalized.

    The sunnah.now API host is api.sunnah.now.
    Routes are under /api/early-access/.
    """
    raw = (settings.hadith_api_base_url or "api.sunnah.now").strip().rstrip("/")
    # Strip any scheme the user may have included
    for prefix in ["https://", "http://"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    return f"https://{raw}"


def _cdn_base() -> str:
    return "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"


# Log provider at module-import time (matches startup log contract)
_provider_at_startup = _active_provider()
if _provider_at_startup == "sunnah_now":
    logger.info(f"[HADITH] provider=sunnah_now  base={_sunnah_now_base()}")
else:
    logger.info("[HADITH] provider=fallback_cdn  (no HADITH_API_KEY set)")


# ─────────────────────────────────────────────────────────────────────────────
# COLLECTION REGISTRY
# sunnah.now uses slug-based routing: bukhari, muslim, abudawud, etc.
# Slugs confirmed from docs.sunnah.now /api/books-list.html
# ─────────────────────────────────────────────────────────────────────────────

COLLECTION_REGISTRY = {
    "bukhari": {
        "name": "Sahih al-Bukhari",
        "sunnah_now_slug": "bukhari",
        # fawazahmed0 CDN fallback editions
        "eng_edition": "eng-bukhari",
        "ara_edition": "ara-bukhari",
    },
    "muslim": {
        "name": "Sahih Muslim",
        "sunnah_now_slug": "muslim",
        "eng_edition": "eng-muslim",
        "ara_edition": "ara-muslim",
    },
    "abudawud": {
        "name": "Sunan Abu Dawud",
        "sunnah_now_slug": "abudawud",
        "eng_edition": "eng-abudawud",
        "ara_edition": "ara-abudawud",
    },
    "tirmidhi": {
        "name": "Jami' at-Tirmidhi",
        "sunnah_now_slug": "tirmidhi",
        "eng_edition": "eng-tirmidhi",
        "ara_edition": "ara-tirmidhi",
    },
    "nasai": {
        "name": "Sunan an-Nasa'i",
        "sunnah_now_slug": "nasai",
        "eng_edition": "eng-nasai",
        "ara_edition": "ara-nasai",
    },
    "ibnmajah": {
        "name": "Sunan Ibn Majah",
        "sunnah_now_slug": "ibnmajah",
        "eng_edition": "eng-ibnmajah",
        "ara_edition": "ara-ibnmajah",
    },
}

_CARD_MAX_CHARS = 350
_HTTP_TIMEOUT = 12.0


# ─────────────────────────────────────────────────────────────────────────────
# HTTP HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _sunnah_now_headers() -> dict:
    """
    Returns auth headers for sunnah.now API.
    Auth: X-API-Key header (per docs.sunnah.now/guide/authentication.html)
    Key value is NEVER logged.
    """
    return {
        "X-API-Key": settings.hadith_api_key or "",
        "Accept": "application/json",
    }


def _get_json(url: str, headers: Optional[dict] = None) -> Optional[dict | list]:
    """Fetches JSON from a URL. Returns dict or list depending on endpoint. Fails gracefully."""
    try:
        response = httpx.get(url, headers=headers or {}, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        logger.warning(f"[HADITH] Timeout: {url}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"[HADITH] HTTP {e.response.status_code}: {url}")
        return None
    except Exception as e:
        logger.error(f"[HADITH] Error fetching {url}: {e}")
        return None


def _safe_excerpt(text: str, max_chars: int = _CARD_MAX_CHARS) -> tuple[str, bool]:
    """
    Returns (text_for_card, was_excerpted).
    Excerpts at the last sentence boundary. Never alters meaning.
    Full text preserved in translation_text field.
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
# SUNNAH.NOW PROVIDER (PRIMARY)
# ─────────────────────────────────────────────────────────────────────────────

def _sunnah_now_get_hadith_by_reference(collection_key: str, hadith_number: int) -> Optional[dict]:
    """
    Fetches a single hadith from sunnah.now.

    Endpoint (from docs.sunnah.now/api/hadith-specific.html):
      GET https://api.sunnah.now/api/early-access/book/{slug}/hadith/{id}
      Header: X-API-Key: <token>

    Response:
      {
        "id": 1,
        "metadata": { "chapter": { "language": { "en": { "text": "..." }, "ar": { "text": "..." } } } },
        "language": {
          "ar": { "text": "Arabic text..." },
          "en": { "narrator": "Narrated ...", "text": "English text..." }
        }
      }
    """
    col = COLLECTION_REGISTRY.get(collection_key)
    if not col:
        logger.warning(f"[HADITH][sunnah_now] Unknown collection key: '{collection_key}'")
        return None

    slug = col["sunnah_now_slug"]
    base = _sunnah_now_base()
    url = f"{base}/api/early-access/book/{slug}/hadith/{hadith_number}"

    logger.info(f"[HADITH][sunnah_now] GET {url}")
    data = _get_json(url, headers=_sunnah_now_headers())
    if not data or not isinstance(data, dict):
        return None

    return _normalize_sunnah_now_hadith(data, collection_key)


def _sunnah_now_search_hadith(query: str, collection_key: Optional[str], limit: int) -> list[dict]:
    """
    Searches hadiths via sunnah.now by paginating through books and filtering locally.

    Endpoint (from docs.sunnah.now/api/book-hadiths.html):
      GET https://api.sunnah.now/api/early-access/book/{slug}/hadith?page={n}&pageSize=50
      Header: X-API-Key: <token>

    sunnah.now does not have a server-side text search endpoint in v0.1.0.
    We scan up to 3 pages (150 hadiths) per collection for keyword matches.
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
        slug = col["sunnah_now_slug"]

        for page in range(1, 4):  # 3 pages × 50 = 150 hadiths per collection
            if len(results) >= limit:
                break

            url = f"{base}/api/early-access/book/{slug}/hadith?page={page}&pageSize=50"
            logger.info(f"[HADITH][sunnah_now] Scanning {col['name']} page {page}")
            data = _get_json(url, headers=_sunnah_now_headers())

            if not data or not isinstance(data, list):
                break  # no more pages or error

            for h in data:
                if len(results) >= limit:
                    break

                # Match against English text
                en_lang = (h.get("language") or {}).get("en") or {}
                text = (en_lang.get("text") or "").lower()

                if query_lower in text:
                    normalized = _normalize_sunnah_now_hadith(h, col_key)
                    if normalized and validate_hadith_item(normalized):
                        results.append(normalized)

            if len(data) < 50:
                break  # last page reached

    logger.info(f"[HADITH][sunnah_now] Search '{query}' → {len(results)} results")
    return results[:limit]


def _normalize_sunnah_now_hadith(h: dict, collection_key: str) -> Optional[dict]:
    """
    Normalizes a sunnah.now hadith response object into the internal schema.

    sunnah.now response structure (from docs.sunnah.now/api/hadith-specific.html):
    {
      "id": 1,
      "metadata": {
        "chapter": { "language": { "en": { "text": "..." }, "ar": { "text": "..." } } }
      },
      "language": {
        "ar": { "text": "..." },
        "en": { "narrator": "Narrated 'Umar bin Al-Khattab:", "text": "..." }
      }
    }

    SAFETY RULES:
    - narrator: taken from language.en.narrator (sunnah.now provides this) — not fabricated
    - grade: NOT provided by sunnah.now v0.1.0 API — set to None, never guessed
    - All text fields taken verbatim from API
    """
    if not h or not isinstance(h, dict):
        return None

    col_meta = COLLECTION_REGISTRY.get(collection_key, {})
    collection_name = col_meta.get("name", collection_key)

    lang = h.get("language") or {}
    en_lang = lang.get("en") or {}
    ar_lang = lang.get("ar") or {}

    # English translation text — from language.en.text
    translation_text = (en_lang.get("text") or "").strip() or None

    # Arabic text — from language.ar.text
    arabic_text = (ar_lang.get("text") or "").strip() or None

    # Narrator — from language.en.narrator (sunnah.now provides this field)
    narrator_raw = (en_lang.get("narrator") or "").strip() or None

    # Hadith ID (sunnah.now uses "id" as the hadith number)
    h_num = h.get("id")

    # Reference string
    reference = f"{collection_name} {h_num}" if h_num is not None else collection_name

    # Chapter title — from metadata.chapter.language.en.text
    chapter_title = None
    try:
        chapter_title = (
            (h.get("metadata") or {})
            .get("chapter", {})
            .get("language", {})
            .get("en", {})
            .get("text") or None
        )
        if chapter_title:
            chapter_title = chapter_title.strip() or None
    except (AttributeError, TypeError):
        pass

    # Grade — sunnah.now v0.1.0 does not provide grade per-hadith
    grade = None  # never guessed, set to None explicitly

    card_text, was_excerpted = _safe_excerpt(translation_text or arabic_text or "")

    return {
        "source_type": "hadith",
        "collection": collection_name,
        "collection_key": collection_key,
        "book": collection_name,
        "chapter": chapter_title,
        "hadith_number": h_num,
        "reference": reference,
        "arabic_text": arabic_text,
        "translation_text": translation_text,
        "card_text": card_text,
        "was_excerpted": was_excerpted,
        "narrator": narrator_raw,   # From API — sunnah.now provides narrator in en.narrator
        "grade": grade,             # None — not provided by sunnah.now v0.1.0
        "topics": [],
        "api_source": "sunnah.now/api/early-access",
    }


def _sunnah_now_get_collections() -> list[dict]:
    """
    Fetches the live list of available books from sunnah.now.
    Endpoint: GET /api/early-access/books
    Response: [{ "collection": "Sahih al-Bukhari", "slug": "bukhari" }]
    Falls back to the static registry if the API is unavailable.
    """
    base = _sunnah_now_base()
    url = f"{base}/api/early-access/books"
    data = _get_json(url, headers=_sunnah_now_headers())
    if data and isinstance(data, list):
        return [{"key": b.get("slug"), "name": b.get("collection")} for b in data if b.get("slug")]
    # Fallback to static registry
    logger.warning("[HADITH][sunnah_now] Could not fetch live books — returning static registry")
    return [{"key": k, "name": v["name"]} for k, v in COLLECTION_REGISTRY.items()]


# ─────────────────────────────────────────────────────────────────────────────
# FAWAZAHMED0 CDN FALLBACK (only when no HADITH_API_KEY is configured)
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
        data = _get_json(f"{base}/editions/{col['eng_edition']}.min.json")
        if not data:
            continue
        for h in data.get("hadiths", []):
            if len(results) >= limit:
                break
            if query_lower in (h.get("text") or "").lower():
                normalized = _normalize_cdn_hadith(
                    {"hadiths": [h], "metadata": data.get("metadata", {})},
                    None, col_key, h.get("hadithnumber"), single_hadith=h,
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
        "narrator": None,   # fawazahmed0 CDN does not provide narrator
        "grade": None,      # fawazahmed0 CDN does not provide grade
        "topics": [],
        "api_source": "fawazahmed0/hadith-api@1",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — provider-agnostic entrypoints
# ─────────────────────────────────────────────────────────────────────────────

def get_supported_collections() -> list[dict]:
    """
    Returns the list of supported Hadith collections.
    When sunnah.now is active, fetches live list and falls back to static registry.
    """
    provider = _active_provider()
    if provider == "sunnah_now":
        return _sunnah_now_get_collections()
    return [{"key": k, "name": v["name"]} for k, v in COLLECTION_REGISTRY.items()]


def get_hadith_by_reference(collection_key: str, hadith_number: int) -> Optional[dict]:
    """
    Fetches an exact hadith by collection key and hadith number.

    Uses sunnah.now (primary) if HADITH_API_KEY is set.
    Falls back to fawazahmed0 CDN if no key is configured.

    SAFETY: Returns only what the API provides. No fields are fabricated.
    """
    provider = _active_provider()
    logger.info(f"[HADITH] get_hadith_by_reference provider={provider} {collection_key}#{hadith_number}")

    if provider == "sunnah_now":
        result = _sunnah_now_get_hadith_by_reference(collection_key, hadith_number)
        if result:
            return result
        logger.warning(f"[HADITH] sunnah_now failed for {collection_key}#{hadith_number} — not falling back to CDN (key mode)")
        return None
    else:
        return _cdn_get_hadith_by_reference(collection_key, hadith_number)


def search_hadith(query: str, collection_key: Optional[str] = None, limit: int = 10) -> list[dict]:
    """
    Searches Hadith text for the given query string.

    Uses sunnah.now (primary) if HADITH_API_KEY is set.
    Falls back to fawazahmed0 CDN if no key is configured.

    SAFETY: Returns only real hadiths. No fabricated results.
    """
    if not query or not query.strip():
        return []

    provider = _active_provider()
    logger.info(f"[HADITH] search_hadith provider={provider} query='{query}'")

    if provider == "sunnah_now":
        return _sunnah_now_search_hadith(query, collection_key, limit)
    else:
        return _cdn_search_hadith(query, collection_key, limit)


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION — provider-independent
# ─────────────────────────────────────────────────────────────────────────────

def validate_hadith_item(item: Optional[dict]) -> bool:
    """
    Safety gate: validates minimum quality requirements before a Hadith is
    used in a quote card or post.

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
