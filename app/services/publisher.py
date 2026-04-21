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
            "error": {"message": "Instagram cannot fetch images from localhost. Please ensure your publicly accessible URL is being used (e.g., via ngrok or production hostname)."}
        }

    # PREFLIGHT CHECK: Ensure media URL is reachable and resolves to an image
    log_event("ig_media_preflight_check_start", url=media_url)
    should_bypass = False
    should_bypass_mime = False
    
    try:
        if not media_url.startswith("https://"):
            return {"ok": False, "error": {"message": "Generated image is not publicly reachable yet."}}
            
        preflight_opts = {
            "timeout": 10,
            "headers": {"User-Agent": "facebookexternalhit/1.1"} # Simulate Meta crawler
        }
        
        preflight = requests.head(media_url, **preflight_opts)
        
        # Some CDNs or servers don't respond well to HEAD requests; try GET if HEAD fails
        if preflight.status_code >= 400:
            preflight = requests.get(media_url, stream=True, **preflight_opts)
            if preflight.status_code >= 400:
                log_event("ig_media_preflight_fail", reason="http_error", status=preflight.status_code)
                
                # Cloud environments (Railway, Cloudflare) often block 'Hairpin NAT' loopbacks.
                # If the server is 404ing its own public URL, but the file exists perfectly on disk, trust the disk.
        content_type = preflight.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            # Check local disk if it's HTML or some other type (e.g. 200 OK from index.html)
            if "/uploads/" in media_url:
                import os
                local_filename = media_url.split("/uploads/")[-1]
                local_path = os.path.join(settings.uploads_dir, local_filename)
                if os.path.exists(local_path):
                    log_event("ig_media_preflight_mime_bypass", url=media_url)
                    should_bypass_mime = True
            
            if not should_bypass_mime and not should_bypass:
                log_event("ig_media_preflight_fail", reason="invalid_content_type_no_bypass", content_type=content_type)
                return {
                    "ok": False,
                    "error": {"message": "Generated image is not publicly reachable yet."}
                }
        
        log_event("ig_media_preflight_success", status_code=preflight.status_code, content_type=content_type)
            
    except Exception as e:
        log_event("ig_media_preflight_error", error=str(e))
        
        # Fallback loopback trust for hard network timeouts
        if "/uploads/" in media_url:
            import os
            local_filename = media_url.split("/uploads/")[-1]
            if os.path.exists(os.path.join(settings.uploads_dir, local_filename)):
                pass # Bypass
            else:
                return {"ok": False, "error": {"message": "Generated image is not publicly reachable yet."}}
        else:
            return {
                "ok": False,
                "error": {"message": "Generated image is not publicly reachable yet."}
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
        
        err_msg = "Instagram could not fetch the generated image. Please regenerate the visual and try again."
        
        # Log the raw JSON so developers can still see it in the logs
        print(f"[IG_PUBLISH][MEDIA_FAIL] Meta JSON: {j1}")
            
        return {"ok": False, "error": {"step": "media_create", "message": err_msg}}

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
        error = j2.get("error", {})
        err_msg = error.get("message", "Unknown Meta API error")
        err_code = error.get("code")
        
        # Human-friendly mapping for common Meta errors
        if err_code == 190:
            err_msg = "Instagram account disconnected. Please re-authenticate in Settings."
        elif err_code == 368:
            err_msg = "Meta has temporarily restricted this account from posting (Spam/Safety check)."
        elif err_code == 10:
            err_msg = "Permission error: Ensure Sabeel Studio has 'Permission to Post' in Facebook settings."
            
        log_event("ig_media_publish_fail", ig_user_id=ig_user_id, creation_id=creation_id, meta_error_code=err_code, fbtrace_id=error.get("fbtrace_id"))
        return {"ok": False, "error": {"step": "media_publish", "message": err_msg, "meta_error": j2}}

    log_event("ig_media_publish_timeout", ig_user_id=ig_user_id, creation_id=creation_id, attempts=10)
    return {
        "ok": False,
        "error": {
            "step": "media_publish",
            "message": "Media never became ready after retries"
        },
    }