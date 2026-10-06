# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.


import requests
import time
from datetime import datetime, timezone
from app.logging_setup import log_event
from app.services.publish_media import is_durable_media_url

GRAPH_URL = "https://graph.facebook.com/v24.0"


def get_container_status(creation_id: str, access_token: str) -> str | None:
    """Read the existing container. Never create or publish media during recovery.

    Meta's collection documents GET /{container}?fields=status_code,status:
    https://www.postman.com/meta/instagram/request/munmruq/get-ig-container-status
    """
    import re
    if not re.fullmatch(r"[0-9]{1,64}", str(creation_id)) or not access_token:
        return None
    try:
        response = requests.get(f"{GRAPH_URL}/{creation_id}", params={"fields": "id,status_code"},
                                headers={"Authorization": "Bearer " + access_token}, timeout=15,
                                allow_redirects=False)
        result = response.json()
        if response.status_code != 200 or not isinstance(result, dict) or str(result.get("id")) != str(creation_id):
            return None
        code = result.get("status_code")
        return code if code in {"PUBLISHED", "ERROR", "EXPIRED", "FINISHED", "IN_PROGRESS"} else None
    except Exception:
        return None


def publish_to_instagram(*, caption: str, media_url: str, ig_user_id: str, access_token: str,
                         on_container_created=None) -> dict:
    """Publish one container; report ambiguous delivery instead of blindly retrying."""
    if not ig_user_id or not access_token:
        return {"ok": False, "error": "Instagram account is disconnected"}
    if not is_durable_media_url(media_url):
        return {"ok": False, "error": "Durable Cloudinary media is required"}

    # No local-file bypass: verify the public image Meta will actually fetch.
    try:
        with requests.get(media_url, stream=True, timeout=8, allow_redirects=False) as response:
            if response.status_code != 200:
                return {"ok": False, "error": "The public image is unavailable"}
            header = response.raw.read(8)
            if not (header.startswith(b"\xff\xd8") or header.startswith(b"\x89PNG")):
                return {"ok": False, "error": "The public image is not a supported image file"}
    except Exception:
        return {"ok": False, "error": "The public image could not be verified"}

    creation_id = None
    for attempt in range(2):
        if attempt:
            time.sleep(3)
        try:
            response = requests.post(
                f"{GRAPH_URL}/{ig_user_id}/media",
                data={"image_url": media_url, "caption": caption, "access_token": access_token}, timeout=30,
            )
            result = response.json()
        except Exception:
            return {"ok": False, "error": "Instagram media container creation failed"}
        if response.status_code < 400 and isinstance(result, dict) and result.get("id"):
            creation_id = str(result["id"])
            break
        error = result.get("error", {}) if isinstance(result, dict) else {}
        if "fetch" not in str(error.get("message", "")).lower():
            break
    if not creation_id:
        return {"ok": False, "error": "Instagram could not create the media container"}

    # Persist the container ID before making a request that can publish publicly.
    if on_container_created is not None:
        on_container_created(creation_id)

    for attempt in range(10):
        try:
            response = requests.post(
                f"{GRAPH_URL}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": access_token}, timeout=30,
            )
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Unexpected publish response")
        except Exception:
            return {"ok": False, "outcome": "unknown", "creation_id": creation_id,
                    "error": "Instagram did not confirm the publish outcome. Check Instagram before retrying."}
        if response.status_code < 400 and result.get("id"):
            log_event("ig_media_publish_success", creation_id=creation_id, remote_id=result["id"])
            return {"ok": True, "platform": "instagram", "remote_id": str(result["id"]),
                    "creation_id": creation_id, "published_at": datetime.now(timezone.utc).isoformat()}
        error = result.get("error") or {}
        if error.get("code") == 9007:
            # Meta explicitly reports that this same container is not ready.
            if attempt < 9:
                time.sleep(4)
            continue
        if response.status_code >= 500 or response.status_code < 400:
            return {"ok": False, "outcome": "unknown", "creation_id": creation_id,
                    "error": "Instagram did not confirm the publish outcome. Check Instagram before retrying."}
        messages = {
            190: "Instagram account disconnected. Reconnect it in Settings.",
            368: "Meta has temporarily restricted this account from posting.",
            10: "Instagram publishing permission is missing.",
        }
        return {"ok": False, "creation_id": creation_id,
                "error": messages.get(error.get("code"), "Instagram rejected the publish request")}
    return {"ok": False, "creation_id": creation_id, "error": "Instagram media did not become ready in time"}
