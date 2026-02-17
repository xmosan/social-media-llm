import requests
from datetime import datetime, timezone
from app.config import settings

GRAPH_URL = "https://graph.facebook.com/v24.0"

def publish_to_instagram(*, caption: str, media_url: str) -> dict:
    if not settings.ig_user_id or not settings.ig_access_token:
        return {"ok": False, "error": "Missing IG_USER_ID or IG_ACCESS_TOKEN in .env"}

    # Step 1: create media container
    r1 = requests.post(
        f"{GRAPH_URL}/{settings.ig_user_id}/media",
        data={
            "image_url": media_url,
            "caption": caption,
            "access_token": settings.ig_access_token,
        },
        timeout=30,
    )
    j1 = r1.json()
    if "id" not in j1:
        return {"ok": False, "error": {"step": "media", "response": j1}}

    creation_id = j1["id"]

    # Step 2: publish container
  import time

# Try publishing up to 10 times (media sometimes takes a few seconds)
for attempt in range(10):
    r2 = requests.post(
        f"{GRAPH_URL}/{settings.ig_user_id}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": settings.ig_access_token,
        },
        timeout=30,
    )

    j2 = r2.json()

    # Success
    if r2.status_code < 400 and "id" in j2:
        return {
            "ok": True,
            "platform": "instagram",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "remote_id": j2["id"],
        }

    # Media not ready yet → retry
    error = j2.get("error", {})
    if error.get("code") == 9007:
        print(f"media_publish not ready, retrying... attempt={attempt+1}", j2)
        time.sleep(4)
        continue

    # Any other error → fail immediately
    return {"ok": False, "error": {"step": "media_publish", "meta_error": j2}}

# If loop exits → it never became ready
return {
    "ok": False,
    "error": {
        "step": "media_publish",
        "message": "Media never became ready after retries"
    },
}


    j2 = r2.json()

    if r2.status_code >= 400:
        return {"ok": False, "error": {"step": "media_publish", "meta_error": j2}}

    if "id" not in j2:
        return {"ok": False, "error": {"step": "media_publish", "meta_error": j2}}

    return {
        "ok": True,
        "platform": "instagram",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "remote_id": j2["id"],
    }