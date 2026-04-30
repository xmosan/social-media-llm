# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
Cloudinary CDN Service
======================
Uploads local image files to Cloudinary so they are reachable by Instagram's crawler.

Instagram requires a publicly accessible HTTPS URL to fetch images for media_create.
Railway's ephemeral filesystem is NOT reliably reachable by Meta's crawler.
Cloudinary solves this by providing a permanent CDN URL for every uploaded asset.

Usage:
    from app.services.cloudinary_service import upload_to_cloudinary
    public_url = upload_to_cloudinary(local_path)   # None if Cloudinary not configured

Configuration (Railway environment variables):
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

If any of these are unset, all functions return None and the system falls back
to the local URL (existing behaviour — no breakage).
"""

import os
import logging

logger = logging.getLogger(__name__)

_cloudinary_configured = False


def _ensure_configured() -> bool:
    """Lazily configure Cloudinary on first use. Returns True if configured."""
    global _cloudinary_configured

    if _cloudinary_configured:
        return True

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        return False

    try:
        import cloudinary
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        _cloudinary_configured = True
        logger.info("[CLOUDINARY] SDK configured successfully")
        return True
    except ImportError:
        logger.warning("[CLOUDINARY] cloudinary package not installed")
        return False
    except Exception as e:
        logger.error(f"[CLOUDINARY] Configuration error: {e}")
        return False


def upload_to_cloudinary(local_path: str, public_id: str | None = None) -> str | None:
    """
    Upload a local image file to Cloudinary and return its secure CDN URL.

    Args:
        local_path: Absolute path to the local image file.
        public_id: Optional Cloudinary public_id (for deduplication). If None,
                   Cloudinary auto-generates one from the filename.

    Returns:
        The secure HTTPS CDN URL (e.g. https://res.cloudinary.com/…/image/upload/…)
        or None if Cloudinary is not configured or the upload fails.
    """
    if not os.path.exists(local_path):
        logger.warning(f"[CLOUDINARY] File not found, cannot upload: {local_path}")
        return None

    if not _ensure_configured():
        logger.debug("[CLOUDINARY] Not configured, skipping CDN upload")
        return None

    try:
        import cloudinary.uploader

        # Derive a stable public_id from the filename if not provided
        if not public_id:
            basename = os.path.basename(local_path)
            name_only = os.path.splitext(basename)[0]
            public_id = f"sabeel/{name_only}"

        logger.info(f"[CLOUDINARY] Uploading {local_path} as {public_id}...")
        result = cloudinary.uploader.upload(
            local_path,
            public_id=public_id,
            folder="sabeel_posts",
            overwrite=True,
            resource_type="image",
            quality="auto:best",
            fetch_format="auto"
        )

        secure_url = result.get("secure_url")
        if secure_url:
            logger.info(f"[CLOUDINARY] Upload success → {secure_url}")
            print(f"✅ [CLOUDINARY] CDN URL: {secure_url}")
            return secure_url

        logger.error(f"[CLOUDINARY] Upload returned no secure_url: {result}")
        return None

    except Exception as e:
        logger.error(f"[CLOUDINARY] Upload failed for {local_path}: {e}")
        print(f"❌ [CLOUDINARY] Upload failed: {e}")
        return None


def is_cloudinary_configured() -> bool:
    """Returns True if Cloudinary credentials are available."""
    return _ensure_configured()
