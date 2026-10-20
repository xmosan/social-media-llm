"""Owner-only checks of canonical public publishing media."""
from fastapi import APIRouter, Depends, Query, HTTPException
import requests
from app.models import User
from app.security.rbac import require_superadmin
from app.services.publish_media import is_durable_media_url
from app.logging_setup import log_event

router = APIRouter(prefix="/api/admin/diag", tags=["admin-diag"])

@router.get("/media-diagnostic")
def media_diagnostic(url: str = Query(..., max_length=2048),
                     current_user: User = Depends(require_superadmin)):
    if not is_durable_media_url(url):
        raise HTTPException(422, "Choose a Cloudinary publishing image from Sabeel.")
    try:
        with requests.get(url, headers={"User-Agent": "facebookexternalhit/1.1"},
                          timeout=(3, 8), stream=True, allow_redirects=False) as response:
            signature = response.raw.read(8) if response.status_code == 200 else b""
            jpeg, png = signature.startswith(b"\xff\xd8\xff"), signature.startswith(b"\x89PNG\r\n\x1a\n")
            return {"status_code": response.status_code,
                    "content_type": response.headers.get("Content-Type", ""),
                    "content_length": response.headers.get("Content-Length", ""),
                    "is_valid_image": jpeg or png,
                    "format": "JPEG" if jpeg else "PNG" if png else "Unknown"}
    except requests.RequestException:
        log_event("media_diag_unavailable", level="warning")
        raise HTTPException(502, "The publishing image could not be reached. Try again shortly.") from None
