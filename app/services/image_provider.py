"""Image API adapters shared by production rendering and the offline comparison runner.

No application, database, scheduler, or credential loading happens on import.
"""

import base64
import binascii
import logging
from dataclasses import dataclass, field
from io import BytesIO

import requests
from openai import OpenAI
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


class ImageGenerationError(RuntimeError):
    """A safe failure description; never includes provider response bodies or keys."""

    def __init__(self, code: str, status: int | None = None):
        self.code = code
        self.status = status
        super().__init__(f"Sabeel Vision could not generate this image ({code}). Please try again.")


@dataclass
class GeneratedImage:
    image: Image.Image
    provider: str
    model: str
    usage: dict = field(default_factory=dict)


def decode_image(encoded: str) -> Image.Image:
    if not isinstance(encoded, str) or not encoded or len(encoded) > 40_000_000:
        raise ImageGenerationError("invalid_image_response")
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(raw)) as image:
            if image.width * image.height > 20_000_000:
                raise ImageGenerationError("image_too_large")
            image.load()
            return image.convert("RGB")
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageGenerationError("invalid_image_response") from None


def generate_openai_image(prompt: str, *, api_key: str, model: str,
                          quality: str = "medium", timeout: float = 120) -> GeneratedImage:
    if not api_key:
        raise ImageGenerationError("provider_not_configured")
    try:
        # Paid image requests are never automatically retried after an uncertain result.
        with OpenAI(api_key=api_key, timeout=timeout, max_retries=0) as client:
            response = client.images.generate(
                model=model, prompt=prompt, size="1024x1024", quality=quality,
                output_format="png", n=1,
            )
    except Exception as exc:
        raise ImageGenerationError("openai_request_failed", getattr(exc, "status_code", None)) from None
    if not response.data or not response.data[0].b64_json:
        raise ImageGenerationError("empty_image_response")
    usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
    return GeneratedImage(decode_image(response.data[0].b64_json), "openai", model, usage)


def generate_google_image(prompt: str, *, api_key: str, model: str,
                          timeout: float = 120) -> GeneratedImage:
    if not api_key:
        raise ImageGenerationError("provider_not_configured")
    try:
        # Use the documented Interactions REST schema: older installed GenAI SDKs
        # do not yet expose output_image. Credentials remain in a header, never a URL.
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"model": model, "input": prompt, "store": False,
                  "response_format": {"type": "image", "aspect_ratio": "1:1", "image_size": "1K"}},
            timeout=(10, timeout),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else None
        raise ImageGenerationError("google_request_failed", status) from None
    except ValueError:
        raise ImageGenerationError("invalid_image_response") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("output_image", {}), dict):
        raise ImageGenerationError("invalid_image_response")
    encoded = (payload.get("output_image") or {}).get("data")
    if not encoded:
        raise ImageGenerationError("empty_image_response")
    return GeneratedImage(decode_image(encoded), "google", model, payload.get("usage") or {})


def configured_image_cache_key() -> str:
    from app.config import settings
    return f"openai:{settings.openai_image_model}:{settings.openai_image_quality}"


def generate_configured_image(prompt: str, *, engine: str = "dalle") -> GeneratedImage:
    """The production path is OpenAI only, including historical saved engine labels.

    Fallback is restricted to explicit model-unavailable/rate-limit/overload errors.
    Timeouts, authentication failures and content refusals never cause a second charge.
    """
    from app.config import settings
    if engine not in {"dalle", "openai", "gemini"}:
        raise ImageGenerationError("unsupported_image_engine")
    primary = settings.openai_image_model
    fallback = settings.openai_image_fallback_model
    try:
        result = generate_openai_image(
            prompt, api_key=settings.openai_api_key, model=primary,
            quality=settings.openai_image_quality, timeout=settings.image_generation_timeout_seconds,
        )
    except ImageGenerationError as exc:
        logger.warning("[VISION] model=%s code=%s status=%s", primary, exc.code, exc.status)
        if exc.status not in {404, 429, 503} or not fallback or fallback == primary:
            raise
        result = generate_openai_image(
            prompt, api_key=settings.openai_api_key, model=fallback,
            quality=settings.openai_image_quality, timeout=settings.image_generation_timeout_seconds,
        )
    logger.info("[VISION] provider=%s model=%s quality=%s", result.provider, result.model, settings.openai_image_quality)
    return result
