"""Require durable Cloudinary media before handing a post to Instagram."""

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit
from app.config import settings


def is_durable_media_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname == "res.cloudinary.com"
                and not parsed.username and not parsed.password and parsed.port in (None, 443)
                and "/image/upload/" in parsed.path)
    except (TypeError, ValueError):
        return False


def prepare_publish_media(url: str) -> str:
    if is_durable_media_url(url):
        return url
    try:
        parsed = urlsplit(url or "")
        allowed_hosts = {host for host in (urlsplit(settings.public_base_url).hostname, os.getenv("RAILWAY_PUBLIC_DOMAIN")) if host}
        if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
                or parsed.hostname not in allowed_hosts or not parsed.path.startswith("/uploads/")):
            raise ValueError("Publishable media must be hosted on Cloudinary. Upload the image again.")
        directory = Path(settings.uploads_dir).resolve()
        file = (directory / unquote(parsed.path[len("/uploads/"):])).resolve()
        if file.parent != directory or not file.is_file():
            raise ValueError("The saved image is unavailable. Regenerate it and review the new visual before publishing.")
        from app.services.cloudinary_service import upload_to_cloudinary
        cdn_url = upload_to_cloudinary(str(file))
        if not is_durable_media_url(cdn_url):
            raise ValueError("Could not store the image on Cloudinary. Publishing was stopped.")
        return cdn_url
    except (TypeError, OSError) as error:
        raise ValueError("The saved image could not be prepared for publishing") from error
