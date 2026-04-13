import requests
import time
from typing import Any, Optional
from app.config import settings

# --- Configuration ---
# Quran Foundation API (QDC) Base URLs
QF_AUTH_BASES = {
    "prod": "https://oauth2.quran.foundation", 
    "dev":  "https://prelive-oauth2.quran.foundation", 
}

QF_CONTENT_BASES = {
    "prod": "https://apis.quran.foundation/content/api/v4",
    "dev":  "https://apis.quran.foundation/content/api/v4",
}

AUTH_BASE = QF_AUTH_BASES.get(settings.qf_env, QF_AUTH_BASES["prod"])
CONTENT_BASE = QF_CONTENT_BASES.get(settings.qf_env, QF_CONTENT_BASES["prod"])

# Token Cache to avoid redundant auth calls
_TOKEN_CACHE = {
    "token": None,
    "expires_at": 0
}

def get_access_token() -> Optional[str]:
    """
    Authenticates with the Quran Foundation API using Client Credentials flow.
    Caches the token until it expires.
    """
    global _TOKEN_CACHE
    
    # Return cached token if still valid (with 60s buffer)
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > time.time() + 60:
        return _TOKEN_CACHE["token"]

    if not settings.qf_client_id or not settings.qf_client_secret:
        print("⚠️  [QF] Missing QF_CLIENT_ID or QF_CLIENT_SECRET in .env")
        return None

    print(f"🔑 [QF] Fetching new access token from {AUTH_BASE}...")
    auth_url = f"{AUTH_BASE.rstrip('/')}/oauth2/token" 
    try:
        # Use Basic Auth for the token request as per OIDC standards
        response = requests.post(
            auth_url,
            auth=(settings.qf_client_id, settings.qf_client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": "content"
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        _TOKEN_CACHE["token"] = data["access_token"]
        _TOKEN_CACHE["expires_at"] = time.time() + data.get("expires_in", 3600)
        
        return _TOKEN_CACHE["token"]
    except Exception as e:
        print(f"❌ [QF] Authentication failed: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"   Response: {e.response.text}")
        return None

def qf_get(path: str, params: dict = None) -> dict:
    """
    Wrapper for authenticated GET requests to the Quran Foundation API.
    """
    url = f"{CONTENT_BASE.rstrip('/')}/{path.lstrip('/')}"
    
    # Add token if available
    token = get_access_token()
    if not token:
        print("❌ [QF] No access token available for request.")
        return {}

    headers = {
        "Accept": "application/json",
        "x-auth-token": token,
        "x-client-id": settings.qf_client_id or ""
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ [QF] Request to {path} failed: {e}")
        return {}

def get_translations_catalog() -> list:
    """
    Returns the list of available translations and their numeric IDs.
    """
    data = qf_get("/resources/translations")
    return data.get("translations", [])

def get_surah_verses(chapter_number: int, translation_ids: str = "131") -> list:
    """
    Fetches all verses for a specific chapter (Surah), handling pagination.
    Default translation: Sahih International (ID 131).
    """
    all_verses = []
    current_page = 1
    
    while True:
        params = {
            "language": "en",
            "translations": translation_ids,
            "fields": "text_uthmani,chapter_id",
            "per_page": 50,
            "page": current_page
        }
        data = qf_get(f"/verses/by_chapter/{chapter_number}", params=params)
        verses = data.get("verses", [])
        if not verses:
            break
            
        all_verses.extend(verses)
        
        pagination = data.get("pagination", {})
        if not pagination.get("next_page"):
            break
            
        current_page += 1
        
    return all_verses

def get_verse_by_key(verse_key: str, translation_ids: str = "131") -> dict:
    """
    Fetches a specific verse by key (e.g. '70:5').
    """
    params = {
        "language": "en",
        "translations": translation_ids,
        "fields": "text_uthmani,chapter_id"
    }
    data = qf_get(f"/verses/by_key/{verse_key}", params=params)
    return data.get("verse", {})

# --- Example Usage (Protected) ---
if __name__ == "__main__":
    # Fix: Define local variables to avoid NameError
    chapter_number = 70
    translation_ids = "131" # Sahih International
    
    print(f"📖 [QF Test] Fetching Verse by Key 70:5...")
    v = get_verse_by_key("70:5", translation_ids)
    if v:
        print(f"✅ Verse found: {v.get('text_uthmani')}")
    else:
        print(f"❌ Could not retrieve verse.")