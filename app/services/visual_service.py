# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""Shared visual facade for Studio, measured cards and durable background reuse."""

from __future__ import annotations

from app.services.usage_limits import UsageLimitError
import logging
import os
import hashlib
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional
from app.services.card_typography import CardTypographyError
from app.services.vision_families import DESIGN_FAMILIES, REUSABLE_FAMILIES, recipe_binding

logger = logging.getLogger(__name__)

# Short-lived, bounded decoded-photo cache for editing. Receipts are validated
# on EVERY access; cache entries never confer ownership or publishing approval.
_preview_photos = OrderedDict()
_preview_lock = threading.Lock()
_preview_slots = threading.BoundedSemaphore(2)
_PREVIEW_BYTES = 48 * 1024 * 1024


def preview_visual(request: VisualRequest, page_index=0):
    """Same compositor, one page, no image provider, upload, save or manifest."""
    from tempfile import TemporaryDirectory
    from app.services.image_card import generate_quote_card
    from app.services.brand_kit import normalize_brand
    if request.style not in DESIGN_FAMILIES:
        raise CardTypographyError("Choose a current visual style to preview edits")
    card = request.card_message
    if not isinstance(card, dict) or not (card.get("headline") or card.get("arabic_text")):
        raise CardTypographyError("Choose a source before previewing its design")
    if len(str(card)) > 32000 or type(page_index) is not int or not 0 <= page_index < 20:
        raise CardTypographyError("This preview is too large or its page is unavailable")
    if request.style in REUSABLE_FAMILIES and not request.background_token:
        raise CardTypographyError("Create a background once, then preview design edits with that photograph")
    if not _preview_slots.acquire(blocking=False):
        raise PreviewBusyError("The preview is busy. Try again in a moment; your changes are kept.")
    started = time.perf_counter()
    try:
        request.brand_kit = normalize_brand(request.brand_kit)
        photo = _load_background(request.background_token, request, use_cache=True) if request.style in REUSABLE_FAMILIES else None
        loaded = time.perf_counter()
        metadata = {}
        with TemporaryDirectory(prefix="sabeel-preview-") as directory:
            image = generate_quote_card(style=request.style, card_message=card,
                layout=request.layout, post_format=request.post_format,
                brand_kit=request.brand_kit, background_image=photo,
                visual_prompt=request.custom_prompt, allow_sequence=True,
                render_metadata=metadata, preview_page=page_index, output_dir=directory)
        finished = time.perf_counter()
        return {"preview_only": True, "image_data": image, **metadata,
                "timings_ms": {"background": round((loaded-started)*1000),
                               "render": round((finished-loaded)*1000),
                               "total": round((finished-started)*1000)}}
    finally:
        _preview_slots.release()


class PreviewBusyError(ValueError):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# INPUT MODELS
# These dataclasses define the clean interface for visual generation requests.
# They are framework-agnostic (not Pydantic) so they can be used from anywhere.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VisualRequest:
    """
    A structured request for visual generation.
    Replaces ad-hoc string passing across the codebase.
    """
    # Visual theme / atmosphere
    theme: str = "sacred_black"
    atmosphere: str = "contemplative"
    ornament_level: str = "corner"

    # Raw user prompt (optional — used if theme is 'custom')
    custom_prompt: Optional[str] = None

    # Quote card content (from quote_message_service output)
    card_message: Optional[dict] = None

    # Generation config
    style: str = "quran"          # quran | fajr | scholar | custom
    mode: str = "preset"          # preset | custom
    engine: str = "openai"        # Historical dalle/gemini labels remain compatible.
    glossy: bool = False
    readability_priority: bool = True
    experimental_mode: bool = False
    text_style_prompt: str = ""

    # Context for DALL-E prompt (used in variation engine)
    topic_hint: Optional[str] = None
    layout: str = "bilingual"
    background_token: Optional[str] = None
    owner_id: Optional[int] = None
    post_format: str = "feed_4_5"
    brand_kit: Optional[dict] = None
    visual_history: Optional[dict] = None


@dataclass
class VisualResult:
    """
    The result of a visual generation request.
    """
    url: str                         # Public-accessible URL
    theme: str = "custom"
    prompt_hash: str = ""            # SHA256 of the effective DALL-E prompt (for caching)
    generated_by: str = "dalle"      # dalle | pil_renderer | cached
    error: Optional[str] = None
    error_status: int = 500
    design: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.url) and self.error is None


# ─────────────────────────────────────────────────────────────────────────────
# CORE SERVICE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def assess_visual_fit(card_message, *, layout="bilingual", post_format="feed_4_5", brand_kit=None):
    """Measure available styles without generating, uploading or approving media."""
    from app.services.image_card import structured_card_segments
    from app.services.card_typography import plan_sequence, layout_card
    from app.services.brand_kit import normalize_brand
    from app.services.quran_ornaments import card_ornaments
    from app.services.vision_families import SCENE_FAMILIES
    if not isinstance(card_message, dict) or not (card_message.get("headline") or card_message.get("arabic_text")):
        raise ValueError("Choose a source before checking styles")
    fields = ("eyebrow", "headline", "arabic_text", "supporting_text")
    if any(not isinstance(card_message.get(key, ""), str) for key in fields):
        raise ValueError("Source and reflection must be text")
    if sum(len(card_message.get(key, "")) for key in fields) > 24000:
        raise ValueError("This complete source exceeds the current sequence limit")
    if card_message.get("was_excerpted"):
        raise ValueError("Rebuild this legacy card from its full source before checking styles")
    if layout not in {"bilingual", "english_first"} or post_format not in {"feed_4_5", "story_9_16"}:
        raise ValueError("Choose a supported format and reading order")
    brand = normalize_brand(brand_kit)
    segments = structured_card_segments(card_message, ornaments=card_ornaments(card_message, brand))
    result = []
    for family in [*SCENE_FAMILIES, "editorial", "quiet_photography", "minimal_paper"]:
        try:
            pages = plan_sequence(segments, family=family, layout=layout, post_format=post_format, brand_kit=brand)
            for page in pages:
                layout_card(page["segments"], family=family, layout=layout, post_format=post_format, brand_kit=brand)
            result.append({"family": family, "available": True, "pages": len(pages)})
        except CardTypographyError as error:
            result.append({"family": family, "available": False, "reason": str(error)})
    return {"families": result}


def generate_visual(request: VisualRequest) -> VisualResult:
    """
    Main entry point for visual generation.

    Routing logic:
    1. If card_message is provided → render a quote card via image_card.generate_quote_card()
    2. If mode == 'custom' and custom_prompt → use visual_system to compose DALL-E prompt
    3. Otherwise → use theme preset via visual_system

    Returns a VisualResult with a public URL.
    """
    try:
        if request.card_message:
            return _generate_quote_card(request)
        else:
            return _generate_background_only(request)
    except CardTypographyError as e:
        logger.warning("[VisualService] Card validation: %s", str(e))
        return VisualResult(url="", error=str(e), error_status=422)
    except UsageLimitError:
        raise
    except Exception as e:
        from app.services.image_provider import ImageGenerationError
        logger.error("[VisualService] Generation failed (%s)", type(e).__name__)
        error = str(e) if isinstance(e, ImageGenerationError) else "Sabeel Vision could not finish this image. Please try again."
        return VisualResult(url="", error=error)


def _generate_quote_card(request: VisualRequest) -> VisualResult:
    """
    Renders a full quote card (background + text overlay) using image_card.py.
    """
    from app.services.image_card import generate_quote_card
    from app.services.brand_kit import normalize_brand
    from app.services.source_display import display_range
    try:
        brand = normalize_brand(request.brand_kit) if request.brand_kit is not None else None
        display_range(request.card_message)
    except ValueError as error:
        raise CardTypographyError(str(error)) from None

    effective_prompt = request.custom_prompt or (None if request.style in DESIGN_FAMILIES else request.theme)
    effective_mode = "custom" if request.custom_prompt else request.mode
    generation_metadata = {}
    background_image = None
    background_token = request.background_token
    if background_token and request.style in REUSABLE_FAMILIES:
        background_image = _load_background(background_token, request)

    def retain_background(image):
        nonlocal background_token
        background_token = store_background(image, request.owner_id, request.custom_prompt or "",
                                             family=request.style, post_format=request.post_format,
                                             visual_identity=(brand or {}).get("visual_identity", ""),
                                             paper_finish=(brand or {}).get("paper_finish"))



    try:
        url = generate_quote_card(
            style=request.style,
            visual_prompt=effective_prompt,
            mode=effective_mode,
            text_style_prompt=request.text_style_prompt,
            readability_priority=request.readability_priority,
            experimental_mode=request.experimental_mode,
            engine=request.engine,
            glossy=request.glossy,
            card_message=request.card_message,
            render_metadata=generation_metadata,
            layout=request.layout, background_image=background_image,
            background_sink=retain_background if request.style in REUSABLE_FAMILIES else None,
            post_format=request.post_format, allow_sequence=True,
            brand_kit=brand, visual_history=request.visual_history,
        )
    except CardTypographyError as error:
        # Only a raw-background receipt survives a failed composition. Never
        # return partial pages or a publishable manifest from this branch.
        return VisualResult(url="", error=str(error), error_status=422,
            design={"version": 1, "family": request.style, "layout": request.layout,
                    "brand_kit": brand, "direction": request.custom_prompt or "",
                    "background_token": background_token if request.style in REUSABLE_FAMILIES else None,
                    "recipe": recipe_binding(request.style, request.post_format, (brand or {}).get("paper_finish")),
                    "quality": {"status": "rejected", "review_required": True}})

    # Keep the signed composition identity through free re-layouts so saved
    # drafts remain part of account-wide variation history.
    signature = generation_metadata.get("prompt_signature")
    if background_token:
        from itsdangerous import BadData
        try:
            receipt = _background_signer().loads(background_token)
            if signature:
                receipt["prompt_signature"] = signature
                background_token = _background_signer().dumps(receipt)
            else:
                signature = receipt.get("prompt_signature")
        except BadData:
            # Invalid production receipts are rejected by _load_background.
            # A renderer without a signed receipt simply has no scene history.
            pass

    from app.services.media_sequence import seal_manifest, validate_manifest
    manifest = seal_manifest(generation_metadata["media_manifest"], request.owner_id)
    validate_manifest(manifest, request.card_message, request.owner_id)

    prompt_hash = _hash_prompt(effective_prompt or request.theme)
    return VisualResult(
        url=url or "",
        theme=request.theme,
        prompt_hash=prompt_hash,
        generated_by=generation_metadata.get("image_model", "pil_renderer"),
        error=None if url else "generate_quote_card returned empty URL",
        design={"version": 1, "family": request.style, "layout": request.layout,
                "brand_kit": brand,
                "background_token": background_token if request.style in REUSABLE_FAMILIES else None,
                "recipe": recipe_binding(request.style, request.post_format, (brand or {}).get("paper_finish")),
                "direction": request.custom_prompt or "", "quality": generation_metadata.get("quality", {}),
                "media_manifest": manifest,
                "background_reused": generation_metadata.get("background_reused", False),
                "prompt_signature": signature},
    )


def store_background(image, owner_id, prompt="", *, family="quiet_photography", post_format="feed_4_5", visual_identity="", paper_finish=None):
    """Persist one raw photograph for Studio and automation draft re-layout."""
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from uuid import uuid4
    from app.services.cloudinary_service import upload_to_cloudinary
    from app.services.publish_media import is_durable_media_url
    with TemporaryDirectory(prefix="sabeel-background-") as directory:
        path = Path(directory) / f"background_{uuid4().hex}.jpg"
        image.convert("RGB").save(path, "JPEG", quality=97)
        url = upload_to_cloudinary(str(path))
    if not is_durable_media_url(url):
        raise CardTypographyError("The photograph could not be saved for reuse. Please try again.")
    return _background_signer().dumps({"url": url, "owner": owner_id, "prompt": _hash_prompt(prompt),
                                       "recipe": recipe_binding(family, post_format, paper_finish), "identity": _hash_prompt(visual_identity) if visual_identity else ""})


def _generate_background_only(request: VisualRequest) -> VisualResult:
    """
    Generates a background image only (no text overlay).
    Uses visual_system.py's interpret_prompt + compose_dalle_prompt pipeline.
    """
    from app.services.visual_system import interpret_prompt, compose_dalle_prompt
    from app.services.llm import generate_ai_image

    raw = request.custom_prompt or request.theme
    spec = interpret_prompt(raw)
    dalle_prompt = compose_dalle_prompt(spec, raw_prompt=raw)

    prompt_hash = _hash_prompt(dalle_prompt)
    logger.info(f"[VisualService] Generating background | theme={spec.theme} | hash={prompt_hash[:8]}")

    generated_url = generate_ai_image(dalle_prompt)
    if not generated_url:
        return VisualResult(url="", theme=spec.theme, prompt_hash=prompt_hash,
                            error="Sabeel Vision could not generate this background")

    # The shared image service already stores a real JPEG on Cloudinary.
    return VisualResult(url=generated_url, theme=spec.theme, prompt_hash=prompt_hash,
                        generated_by="openai")


def get_available_themes() -> list[dict]:
    """
    Returns the list of available visual themes from visual_system.py.
    Used by the Studio UI to populate the theme picker.
    """
    from app.services.visual_system import _THEME_KEYWORDS, _PALETTES, _MOOD

    themes = []
    for theme_name, keywords, priority in sorted(_THEME_KEYWORDS, key=lambda x: -x[2]):
        if theme_name == "custom":
            continue
        palette = _PALETTES.get(theme_name, {})
        themes.append({
            "key": theme_name,
            "label": theme_name.replace("_", " ").title(),
            "is_dark": not palette[2] if len(palette) > 2 else True,
            "mood": _MOOD.get(theme_name, "contemplative"),
            "keywords": keywords[:3],
        })
    return themes


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _hash_prompt(prompt: str) -> str:
    """SHA256 hash of a prompt string, used for deduplication and caching."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _background_signer():
    from itsdangerous import URLSafeSerializer
    from app.config import settings
    return URLSafeSerializer(settings.secret_key, salt="sabeel-visual-background-v1")


def _load_background(token, request, *, use_cache=False):
    """Only server-issued, same-organization Cloudinary photographs can be reused.

    Receipts deliberately survive refresh/deploy; they contain no credentials.
    No redirects or arbitrary URL fetching. Layout and source are independent.
    """
    import io
    import requests
    from PIL import Image
    from itsdangerous import BadData
    from app.services.publish_media import is_durable_media_url
    try:
        data = _background_signer().loads(token)
        if (not isinstance(data, dict) or data.get("owner") != request.owner_id
                or data.get("prompt") != _hash_prompt(request.custom_prompt or "")
                or data.get("recipe") != recipe_binding(request.style, request.post_format, (request.brand_kit or {}).get("paper_finish"))
                or data.get("identity", "") != (_hash_prompt(request.brand_kit["visual_identity"]) if (request.brand_kit or {}).get("visual_identity") else "")
                or not is_durable_media_url(data.get("url"))):
            raise ValueError("Invalid receipt")
        cache_key = (request.owner_id, data["url"])
        if use_cache:
            with _preview_lock:
                for key, (expires, _) in list(_preview_photos.items()):
                    if expires <= time.monotonic():
                        del _preview_photos[key]
                cached = _preview_photos.get(cache_key)
                if cached:
                    _preview_photos.move_to_end(cache_key)
                    return cached[1].copy()
        with requests.get(data["url"], timeout=(5, 20), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ValueError("Unavailable image")
            buffer = io.BytesIO()
            for chunk in response.iter_content(65536):
                buffer.write(chunk)
                if buffer.tell() > 20 * 1024 * 1024:
                    raise ValueError("Oversize image")
            buffer.seek(0)
            with Image.open(buffer) as photo:
                if photo.width * photo.height > 16_000_000:
                    raise ValueError("Oversize image")
                decoded = photo.convert("RGB")
        if use_cache and decoded.width * decoded.height * 3 <= _PREVIEW_BYTES:
            with _preview_lock:
                _preview_photos[cache_key] = (time.monotonic()+300, decoded.copy())
                while sum(img.width*img.height*3 for _, img in _preview_photos.values()) > _PREVIEW_BYTES:
                    _preview_photos.popitem(last=False)
        return decoded
    except (BadData, ValueError, TypeError, OSError, requests.RequestException):
        raise CardTypographyError("The saved photograph could not be reused. Choose a new photograph and try again.") from None
