# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import requests
import time
from datetime import datetime, timezone
from app.config import settings
from app.logging_setup import log_event

GRAPH_URL = "https://graph.facebook.com/v24.0"

def publish_to_instagram(*, caption: str, media_url: str, ig_user_id: str, access_token: str) -> dict:
    if not ig_user_id or not access_token:
        return {"ok": False, "error": "Missing ig_user_id or access_token"}

    if "localhost" in media_url or "127.0.0.1" in media_url:
        return {
            "ok": False, 
            "error": "Instagram cannot fetch images from 'localhost'. You must use a public HTTPS URL (e.g., via ngrok or production deployment) for the BASE_URL."
        }

    # Step 1: create media container
    log_event("ig_media_create_start", ig_user_id=ig_user_id)
    r1 = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={
            "image_url": media_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    j1 = r1.json()
    if "id" not in j1:
        error_obj = j1.get("error", {})
        log_event("ig_media_create_fail", ig_user_id=ig_user_id, meta_error_code=error_obj.get("code"), fbtrace_id=error_obj.get("fbtrace_id"))
        return {"ok": False, "error": {"step": "media", "response": j1}}

    creation_id = j1["id"]
    log_event("ig_media_create_success", ig_user_id=ig_user_id, creation_id=creation_id)

    log_event("ig_media_publish_start", ig_user_id=ig_user_id, creation_id=creation_id)
    # Step 2: publish container
    for attempt in range(10):
        r2 = requests.post(
            f"{GRAPH_URL}/{ig_user_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": access_token,
            },
            timeout=30,
        )

        j2 = r2.json()

        # Success
        if r2.status_code < 400 and "id" in j2:
            log_event("ig_media_publish_success", ig_user_id=ig_user_id, creation_id=creation_id, attempts=attempt+1, remote_id=j2["id"])
            return {
                "ok": True,
                "platform": "instagram",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "remote_id": j2["id"],
            }

        # Media not ready yet → retry
        error = j2.get("error", {})
        if error.get("code") == 9007:
            if attempt == 0:
                log_event("ig_media_publish_retry", ig_user_id=ig_user_id, creation_id=creation_id, fbtrace_id=error.get("fbtrace_id"))
            time.sleep(4)
            continue

        # Any other error → fail immediately
        log_event("ig_media_publish_fail", ig_user_id=ig_user_id, creation_id=creation_id, meta_error_code=error.get("code"), fbtrace_id=error.get("fbtrace_id"))
        return {"ok": False, "error": {"step": "media_publish", "meta_error": j2}}

    log_event("ig_media_publish_timeout", ig_user_id=ig_user_id, creation_id=creation_id, attempts=10)
    return {
        "ok": False,
        "error": {
            "step": "media_publish",
            "message": "Media never became ready after retries"
        },
    }