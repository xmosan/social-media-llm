from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
import requests
import os
import magic # if available, otherwise manual checks
from app.config import settings
from app.logging_setup import log_event
from app.models import User
from app.security.auth import get_current_user

router = APIRouter(prefix="/api/admin/diag", tags=["admin-diag"])

@router.get("/media-diagnostic")
def media_diagnostic(
    url: str = Query(..., description="The full URL to check"),
    current_user: User = Depends(get_current_user)
):
    """
    Simulates a Meta crawler fetch to verify image reachability and integrity.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    results = {
        "url": url,
        "absolute": url.startswith("https://"),
        "timestamp": str(os.times()),
        "diagnostics": {}
    }

    log_event("media_diag_start", url=url)

    try:
        # Pre-check: is it a local-mapped URL?
        if "/uploads/" in url:
            filename = url.split("/uploads/")[-1]
            abs_path = os.path.join(settings.uploads_dir, filename)
            results["diagnostics"]["local_file_found"] = os.path.exists(abs_path)
            if results["diagnostics"]["local_file_found"]:
                results["diagnostics"]["local_path"] = abs_path
                results["diagnostics"]["local_size"] = os.path.getsize(abs_path)

        # Meta Simulation
        headers = {"User-Agent": "facebookexternalhit/1.1"}
        resp = requests.get(url, headers=headers, timeout=10, stream=True)
        
        results["status_code"] = resp.status_code
        results["content_type"] = resp.headers.get("Content-Type", "None")
        results["content_length"] = resp.headers.get("Content-Length", 0)
        
        if resp.status_code == 200:
            # Read first 8 bytes for magic number check
            first_bytes = resp.raw.read(8)
            hex_sig = first_bytes.hex()
            results["magic_bytes"] = hex_sig
            
            is_jpeg = hex_sig.startswith("ffd8ff")
            is_png = hex_sig.startswith("89504e47")
            
            results["is_valid_image"] = is_jpeg or is_png
            results["format"] = "JPEG" if is_jpeg else ("PNG" if is_png else "Unknown")
            
            if "text/html" in results["content_type"].lower():
                results["is_html_error"] = True
                results["is_valid_image"] = False

        log_event("media_diag_success", url=url, status=resp.status_code, valid=results.get("is_valid_image"))

    except Exception as e:
        results["error"] = str(e)
        log_event("media_diag_error", url=url, error=str(e))

    return results
