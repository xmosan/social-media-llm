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
    preflight_error = None
    
    try:
        # 1. Basic Protocol Check
        if not media_url.startswith("https://"):
            log_event("ig_media_preflight_fail", reason="not_https", url=media_url)
            return {"ok": False, "error": {"message": "Generated image is not publicly reachable yet (HTTPS required)."}}
            
        # 2. Local Loopback Trust (Railway/Hairpin NAT bypass)
        if "/uploads/" in media_url:
            import os
            local_filename = media_url.split("/uploads/")[-1]
            local_path = os.path.join(settings.uploads_dir, local_filename)
            
            should_bypass = False
            if not os.path.exists(local_path):
                # WAIT-AND-HUNT: Micro-latency protection for ephemeral disk sync
                found_asset = False
                print(f"⚠️ [MEDIA_PREFLIGHT] Missing asset on first look: {local_path}")
                
                for attempt in range(3):
                    print(f"🔍 [MEDIA_PREFLIGHT] Hunt Attempt {attempt+1}: {local_filename} not found. Waiting 500ms...")
                    time.sleep(0.5)
                    
                    if os.path.exists(local_path):
                        print(f"🎯 [MEDIA_PREFLIGHT] Asset synchronized successfully at {local_path}!")
                        found_asset = True
                        break
                    
                    print(f"   - Deep scan for fingerprint: {local_filename} in /app")
                    import glob
                    candidates = glob.glob(f"/app/**/{local_filename}", recursive=True)
                    if candidates:
                        local_path = candidates[0]
                        print(f"🎯 [MEDIA_PREFLIGHT] FOUND MISPLACED FILE at {local_path}. Correcting path...")
                        found_asset = True
                        break
                
                if not found_asset:
                    print(f"❌ [MEDIA_PREFLIGHT] STALE DETECTED: File {local_filename} is missing from ephemeral storage.")
                    return {"ok": False, "error": "MEDIA_STALE_OR_MISSING"}

            if os.path.exists(local_path):
                # Deep Verify Magic Bytes Locally
                try:
                    with open(local_path, "rb") as f:
                        header = f.read(8).hex()
                        if header.startswith("ffd8") or header.startswith("89504e47"):
                            print(f"✅ [IG_PUBLISH] Loopback Trust: Valid magic bytes found at {local_path}")
                            log_event("ig_media_preflight_loopback_trust_verified", path=local_path)
                            should_bypass = True
                        else:
                            print(f"⚠️ [IG_PUBLISH] Loopback Fail: Invalid magic bytes ({header[:8]}...) at {local_path}")
                            log_event("ig_media_preflight_fail", reason="invalid_local_magic_bytes", header=header)
                            preflight_error = "Generated image file is corrupted or invalid."
                except Exception as e:
                    print(f"❌ [IG_PUBLISH] Loopback Error: Could not read {local_path}: {e}")
                    log_event("ig_media_preflight_local_read_error", error=str(e))
            else:
                print(f"❌ [IG_PUBLISH] Loopback Fail: File NOT FOUND at {local_path}")
                log_event("ig_media_preflight_local_not_found", path=local_path)

        # 3. Network Ping (If not already trusted via local check)
        if not should_bypass and not preflight_error:
            preflight_opts = {
                "timeout": 8,
                "headers": {"User-Agent": "facebookexternalhit/1.1"} # Simulate Meta crawler
            }
            try:
                preflight = requests.get(media_url, stream=True, **preflight_opts)
                if preflight.status_code < 400:
                    content_type = preflight.headers.get("Content-Type", "")
                    # Deep Verify Magic Bytes via Network
                    header = preflight.raw.read(8).hex()
                    
                    if header.startswith("ffd8") or header.startswith("89504e47"):
                        log_event("ig_media_preflight_network_success", status=preflight.status_code)
                    else:
                        log_event("ig_media_preflight_fail", reason="invalid_network_magic_bytes", header=header, content_type=content_type)
                        preflight_error = "Generated image is not a valid public media file (found non-image content)."
                else:
                    log_event("ig_media_preflight_fail", reason="network_error", status=preflight.status_code)
                    preflight_error = f"Generated image is unreachable (Server returned {preflight.status_code})."
            except Exception as net_err:
                log_event("ig_media_preflight_network_error", error=str(net_err))
                preflight_error = "Generated image is unreachable due to a network timeout."

    except Exception as e:
        log_event("ig_media_preflight_exception", error=str(e))
        preflight_error = f"Media validation failed: {str(e)}"

    # BLOCKED: Only proceed if preflight cleared or bypassed
    if preflight_error and not should_bypass:
        return {"ok": False, "error": {"message": preflight_error}}

    # Step 1: create media container
    log_event("ig_media_create_start", ig_user_id=ig_user_id)
    
    # RETRY SHIELD: Meta's crawler sometimes fails to fetch immediately (especially in ephemeral/cloud environments)
    # We attempt up to 2 times with a slight delay.
    max_attempts = 2
    last_j1 = {}
    
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            import time
            time.sleep(3) # Wait for crawler/DNS/filesystem stabilization
            log_event("ig_media_create_retry", attempt=attempt)

        r1 = requests.post(
            f"{GRAPH_URL}/{ig_user_id}/media",
            data={
                "image_url": media_url,
                "caption": caption,
                "access_token": access_token,
            },
            timeout=30,
        )
        last_j1 = r1.json()
        
        if "id" in last_j1:
            break
            
        # If we failed, check if it's a fetch error that warrants a retry
        error_obj = last_j1.get("error", {})
        error_msg = error_obj.get("message", "").lower()
        if "could not fetch" not in error_msg and "fetch" not in error_msg:
            # If it's a different error (e.g. token expired), don't bother retrying
            break

    if "id" not in last_j1:
        error_obj = last_j1.get("error", {})
        log_event("ig_media_create_fail", ig_user_id=ig_user_id, meta_error_code=error_obj.get("code"), fbtrace_id=error_obj.get("fbtrace_id"))
        
        err_msg = "Instagram could not fetch the generated image. Please regenerate the visual and try again."
        
        # Log the raw JSON so developers can still see it in the logs
        print(f"[IG_PUBLISH][MEDIA_FAIL] Meta JSON: {last_j1}")
            
        return {"ok": False, "error": {"step": "media_create", "message": err_msg}}

    creation_id = last_j1["id"]
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