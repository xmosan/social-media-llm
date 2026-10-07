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
                         on_container_created=None, media_urls=None, story=False, verify_media=True) -> dict:
    """Publish one container; report ambiguous delivery instead of blindly retrying."""
    if not ig_user_id or not access_token:
        return {"ok": False, "error": "Instagram account is disconnected"}
    if not is_durable_media_url(media_url):
        return {"ok": False, "error": "Durable Cloudinary media is required"}

    # No local-file bypass: verify the public image Meta will actually fetch.
    try:
        if media_urls:
            verify_sequence_images(media_urls, story=False)
        if verify_media:
            verify_single_image(media_url)
    except Exception:
        return {"ok": False, "error": "The public image could not be verified"}

    children = []
    if media_urls:
        if not 2 <= len(media_urls) <= 10:
            return {"ok": False, "error": "A carousel requires 2–10 images"}
        for url in media_urls:
            child = create_container(ig_user_id, access_token, {"image_url": url, "is_carousel_item": "true"})
            if not child or not wait_until_ready(child, access_token):
                return {"ok": False, "error": "Instagram could not prepare every carousel page. Nothing was published."}
            children.append(child)
    media_data = ({"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption} if children else
                  {"image_url": media_url, **({"media_type": "STORIES"} if story else {"caption": caption})})
    creation_id = create_container(ig_user_id, access_token, media_data)
    if not creation_id:
        return {"ok": False, "error": ("Instagram could not prepare this Story. This connection requires a Business account with publishing permission. Export the sequence to share it manually."
                                      if story else "Instagram could not create the media container")}

    # Persist the container ID before making a request that can publish publicly.
    if on_container_created is not None:
        on_container_created(creation_id)

    return publish_container(creation_id, ig_user_id, access_token)


def verify_single_image(media_url):
    with requests.get(media_url, stream=True, timeout=8, allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError("The public image is unavailable")
        header = response.raw.read(8)
        if not (header.startswith(b"\xff\xd8") or header.startswith(b"\x89PNG")):
            raise ValueError("The public image is not a supported image file")


def verify_sequence_images(urls, *, story):
    import io
    from PIL import Image
    from app.services.media_sequence import download_image
    if not 1 <= len(urls) <= 10:
        raise ValueError("Sequences support up to ten images")
    for url in urls:
        image = Image.open(io.BytesIO(download_image(url)))
        if image.size != (1080, 1920 if story else 1350):
            raise ValueError("A sequence image has the wrong dimensions")
        image.verify()


def create_container(ig_user_id, access_token, media_data):
    for attempt in range(2):
        if attempt:
            time.sleep(3)
        try:
            response = requests.post(f"{GRAPH_URL}/{ig_user_id}/media",
                data={**media_data, "access_token": access_token}, timeout=30, allow_redirects=False)
            result = response.json()
        except Exception:
            return None
        if response.status_code < 400 and isinstance(result, dict) and result.get("id"):
            return str(result["id"])
        error = result.get("error", {}) if isinstance(result, dict) else {}
        if "fetch" not in str(error.get("message", "")).lower():
            break
    return None


def wait_until_ready(creation_id, access_token):
    for attempt in range(8):
        status = get_container_status(creation_id, access_token)
        if status == "FINISHED":
            return True
        if status != "IN_PROGRESS":
            return False
        if attempt < 7:
            time.sleep(2)
    return False


def publish_container(creation_id, ig_user_id, access_token):
    for attempt in range(10):
        try:
            response = requests.post(
                f"{GRAPH_URL}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": access_token}, timeout=30, allow_redirects=False,
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


def validate_story_account(ig_user_id, access_token):
    """Verify live identity using fields supported by Facebook Login.

    This API does not expose account_type (verified against the live connection).
    Meta enforces Business eligibility when creating the STORIES container,
    before media_publish. Do not infer eligibility from a successful profile read.
    Meta's official collection documents the Business-only restriction:
    https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
    """
    try:
        response = requests.get(f"{GRAPH_URL}/{ig_user_id}", params={"fields": "id"},
            headers={"Authorization": "Bearer " + access_token}, timeout=15, allow_redirects=False)
        data = response.json()
        if response.status_code != 200 or not isinstance(data, dict) or str(data.get("id")) != str(ig_user_id):
            raise ValueError("Could not verify the connected Instagram account. Reconnect Instagram or export the sequence.")
    except requests.RequestException:
        raise ValueError("Could not verify the connected Instagram account. Please try again or export.") from None


def publish_story_sequence(*, media_urls, ig_user_id, access_token, frames, on_progress):
    """Each Story is a separate public action. Commit progress before proceeding.

    A partial sequence is never represented as one atomic publication. Unknown
    delivery stops the sequence and requires read-only reconciliation first.
    """
    from copy import deepcopy
    frames = deepcopy(frames)
    try:
        verify_sequence_images(media_urls, story=True)
    except Exception:
        return {"ok": False, "error": "Every Story image must be available before publishing", "frames": frames}
    for i, url in enumerate(media_urls):
        if frames[i].get("state") == "published":
            continue
        if frames[i].get("state") in {"publishing", "unknown"}:
            return {"ok": False, "outcome": "unknown", "frames": frames, "error": "Reconcile the pending Story frame before continuing"}
        def record(creation_id):
            frames[i] = {"index": i, "creation_id": creation_id, "state": "publishing"}
            on_progress(deepcopy(frames))
        result = publish_to_instagram(caption="", media_url=url, ig_user_id=ig_user_id,
            access_token=access_token, on_container_created=record, story=True, verify_media=False)
        frames[i] = {**frames[i], "index": i, "state": "published" if result.get("ok") and result.get("remote_id") else
                     "unknown" if result.get("outcome") == "unknown" or result.get("ok") else "failed"}
        for key in ("creation_id", "remote_id"):
            if result.get(key):
                frames[i][key] = result[key]
        on_progress(deepcopy(frames))
        if frames[i]["state"] != "published":
            return {**result, "ok": False, "frames": frames}
    return {"ok": True, "frames": frames}
