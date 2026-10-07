"""Ordered, source-bound media manifests and portable source-preserving exports.

Stored in Post.flags; media_url remains the cover for legacy list views. No schema
rewrite is required. Only server-rendered, organization-bound manifests are saved.
"""
import hashlib
import io
import json
import zipfile

from itsdangerous import URLSafeSerializer, BadSignature
from app.config import settings
from app.services.publish_media import is_durable_media_url

FORMATS = {"feed_4_5", "carousel_4_5", "story_9_16"}
ROLE_FIELDS = {"source_translation": "headline", "source_arabic": "arabic_text", "reflection": "supporting_text"}


def card_digest(card):
    # JSON.parse/stringify changes integral floats (13.0 -> 13). Measurements
    # cross that browser boundary before a draft save, so hash their numeric
    # value rather than Python's int/float spelling. Source strings stay exact.
    return _raw_digest(_canonical_numbers(card or {}))


def _canonical_numbers(value):
    if isinstance(value, dict):
        return {k: _canonical_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical_numbers(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _raw_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _signer():
    return URLSafeSerializer(settings.secret_key, salt="sabeel-media-sequence-v1")


def seal_manifest(manifest, owner_id):
    body = {k: v for k, v in manifest.items() if k != "receipt"}
    return {**body, "receipt": _signer().dumps({"owner": owner_id, "digest": card_digest(body)})}


def validate_manifest(manifest, card, owner_id):
    if not isinstance(manifest, dict):
        raise ValueError("Generate and review the complete sequence first")
    try:
        receipt = _signer().loads(manifest.get("receipt") or "")
    except BadSignature:
        raise ValueError("This visual sequence could not be verified. Generate it again.") from None
    body = {k: v for k, v in manifest.items() if k != "receipt"}
    # Retain verification of already stored pre-normalization manifests.
    if (not isinstance(receipt, dict) or set(receipt) != {"owner", "digest"}
            or receipt["owner"] != owner_id or receipt["digest"] not in {card_digest(body), _raw_digest(body)}):
        raise ValueError("The visual sequence changed or belongs to another workspace")
    if manifest.get("card_digest") not in {card_digest(card), _raw_digest(card or {})}:
        raise ValueError("Apply your latest source and reflection changes before saving")
    pages, fmt = manifest.get("pages"), manifest.get("format")
    if (manifest.get("version") != 1 or fmt not in FORMATS or not isinstance(pages, list)
            or not 1 <= len(pages) <= 10 or (fmt == "feed_4_5" and len(pages) != 1)
            or (fmt == "carousel_4_5" and len(pages) < 2)):
        raise ValueError("This sequence has an invalid format or page count")
    for i, page in enumerate(pages):
        if (page.get("index") != i or not is_durable_media_url(page.get("url"))
                or page.get("width") != 1080 or page.get("height") != (1920 if fmt == "story_9_16" else 1350)
                or page.get("quality", {}).get("status") != "passed"):
            raise ValueError("Every page needs a durable image and a passed readability check")
    # Complete contiguous coverage, without omissions, overlaps, or reordering.
    # Legacy single-card callers have no ranges; only accept that for one page.
    if any(p.get("slices") for p in pages) or len(pages)>1:
        for role, field in ROLE_FIELDS.items():
            text, cursor = (card or {}).get(field) or "", 0
            for page in pages:
                for part in page.get("slices", []):
                    if part.get("role") == role:
                        if (part.get("start") != cursor or type(part.get("end")) is not int
                                or not cursor < part["end"] <= len(text)):
                            raise ValueError("The sequence does not preserve the complete source in order")
                        cursor = part["end"]
            if cursor != len(text):
                raise ValueError("The sequence is missing source or reflection text")
    return manifest


def saved_manifest(post):
    manifest = (post.flags or {}).get("media_manifest")
    if manifest is None:
        if post.post_format in {"carousel_4_5", "story_9_16"}:
            raise ValueError("This post has no verified sequence. Rebuild its visual in Studio.")
        return None
    validate_manifest(manifest, post.card_message, post.org_id)
    if post.post_format != manifest["format"] or post.media_url != manifest["pages"][0]["url"]:
        raise ValueError("The saved format or cover does not match the reviewed sequence")
    return manifest


def require_sequence_review(post, manifest):
    if manifest and (post.flags or {}).get("reviewed_manifest") != card_digest(manifest):
        raise ValueError("Open this draft in Studio, review every page, and confirm the visual before sharing")


def download_image(url):
    """Bounded CDN-only fetch; never follow redirects into arbitrary hosts."""
    import requests
    if not is_durable_media_url(url):
        raise ValueError("The saved media is not on the canonical CDN")
    try:
        with requests.get(url, stream=True, timeout=(5, 20), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError("A sequence image is unavailable; nothing was exported or published")
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>8*1024*1024:
                    raise ValueError("A sequence image exceeds the supported size")
        if not data.startswith(b"\xff\xd8"):
            raise ValueError("Sequence media must be a JPEG image")
        return bytes(data)
    except requests.RequestException:
        raise ValueError("A sequence image could not be downloaded. Please try again.") from None


def export_post(post):
    manifest = saved_manifest(post)
    pages = manifest["pages"] if manifest else [{"url": post.media_url}]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        for i, page in enumerate(pages):
            bundle.writestr(f"{i+1:02d}.jpg", download_image(page["url"]))
        # Internal render recipes and background receipts are not provenance.
        source_metadata = {k:v for k,v in (post.source_metadata or {}).items()
                           if k not in {"visual_generation", "recovery_recipe"}}
        bundle.writestr("source.json", json.dumps({"source_type": post.source_type,
            "source_reference": post.source_reference, "source_metadata": source_metadata,
            "card_message": post.card_message, "format": post.post_format,
            "pages": [{k:v for k,v in p.items() if k != "url"} for p in pages]}, ensure_ascii=False, indent=2))
        bundle.writestr("caption.txt", post.caption or "")
        bundle.writestr("README.txt", "Publish every numbered image in order. Together they preserve the full source.\n"
                         "Review the source, context, Arabic and reflection before sharing.\n"
                         "Story captions are separate notes and are not sent as Instagram Story text.\n")
    archive.seek(0)
    return archive
