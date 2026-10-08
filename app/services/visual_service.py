# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""Shared visual facade for Studio, measured cards and durable background reuse."""

from __future__ import annotations

import logging
import os
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from app.services.card_typography import CardTypographyError
from app.services.vision_families import DESIGN_FAMILIES, REUSABLE_FAMILIES, recipe_binding

logger = logging.getLogger(__name__)


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
    layout: str = "english_first"
    background_token: Optional[str] = None
    owner_id: Optional[int] = None
    post_format: str = "feed_4_5"
    brand_kit: Optional[dict] = None


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
                                             family=request.style, post_format=request.post_format)



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
            brand_kit=brand,
        )
    except CardTypographyError as error:
        # Only a raw-background receipt survives a failed composition. Never
        # return partial pages or a publishable manifest from this branch.
        return VisualResult(url="", error=str(error), error_status=422,
            design={"version": 1, "family": request.style, "layout": request.layout,
                    "brand_kit": brand, "direction": request.custom_prompt or "",
                    "background_token": background_token if request.style in REUSABLE_FAMILIES else None,
                    "recipe": recipe_binding(request.style, request.post_format),
                    "quality": {"status": "rejected", "review_required": True}})

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
                "recipe": recipe_binding(request.style, request.post_format),
                "direction": request.custom_prompt or "", "quality": generation_metadata.get("quality", {}),
                "media_manifest": manifest,
                "background_reused": generation_metadata.get("background_reused", False)},
    )


def store_background(image, owner_id, prompt="", *, family="quiet_photography", post_format="feed_4_5"):
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
                                       "recipe": recipe_binding(family, post_format)})


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


def _load_background(token, request):
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
                or data.get("recipe") != recipe_binding(request.style, request.post_format)
                or not is_durable_media_url(data.get("url"))):
            raise ValueError("Invalid receipt")
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
                return photo.convert("RGB")
    except (BadData, ValueError, TypeError, OSError, requests.RequestException):
        raise CardTypographyError("The saved photograph could not be reused. Choose a new photograph and try again.") from None
