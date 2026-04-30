# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
visual_service.py — Phase 1 Service Wrapper

Unified interface for all visual asset generation in Sabeel Studio.
This is a FACADE over the existing, working implementations:
  - services/visual_system.py   (theme engine, VariationEngine, DALL-E prompts)
  - services/image_card.py      (quote card rendering from structured card_message)
  - services/image_renderer.py  (PIL rendering pipeline)

IMPORTANT: This file does NOT change any existing code. It only wraps it.
All existing routes continue to call the underlying services directly.
New routes (Phase 3 Studio API) will call this service.
"""

from __future__ import annotations

import logging
import os
import hashlib
from dataclasses import dataclass, field
from typing import Optional

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
    engine: str = "dalle"         # dalle
    glossy: bool = False
    readability_priority: bool = True
    experimental_mode: bool = False
    text_style_prompt: str = ""

    # Context for DALL-E prompt (used in variation engine)
    topic_hint: Optional[str] = None


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
    except Exception as e:
        logger.error(f"[VisualService] Generation failed: {e}", exc_info=True)
        return VisualResult(url="", error=str(e))


def _generate_quote_card(request: VisualRequest) -> VisualResult:
    """
    Renders a full quote card (background + text overlay) using image_card.py.
    """
    from app.services.image_card import generate_quote_card

    effective_prompt = request.custom_prompt or request.theme
    effective_mode = "custom" if request.custom_prompt else request.mode

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
    )

    prompt_hash = _hash_prompt(effective_prompt or request.theme)
    return VisualResult(
        url=url or "",
        theme=request.theme,
        prompt_hash=prompt_hash,
        generated_by="dalle",
        error=None if url else "generate_quote_card returned empty URL",
    )


def _generate_background_only(request: VisualRequest) -> VisualResult:
    """
    Generates a background image only (no text overlay).
    Uses visual_system.py's interpret_prompt + compose_dalle_prompt pipeline.
    """
    from app.services.visual_system import interpret_prompt, compose_dalle_prompt
    from app.services.llm import generate_ai_image
    from app.config import settings
    import requests as req_lib

    raw = request.custom_prompt or request.theme
    spec = interpret_prompt(raw)
    dalle_prompt = compose_dalle_prompt(spec, raw_prompt=raw)

    prompt_hash = _hash_prompt(dalle_prompt)
    logger.info(f"[VisualService] Generating background | theme={spec.theme} | hash={prompt_hash[:8]}")

    generated_url = generate_ai_image(dalle_prompt)
    if not generated_url:
        return VisualResult(url="", theme=spec.theme, prompt_hash=prompt_hash,
                            error="DALL-E returned no URL")

    # Download and save locally for a stable public URL
    import time
    filename = f"vis_{prompt_hash[:12]}_{int(time.time())}.jpg"
    file_path = os.path.join(settings.uploads_dir, filename)
    try:
        resp = req_lib.get(generated_url, timeout=30)
        if resp.status_code == 200:
            with open(file_path, "wb") as f:
                f.write(resp.content)
            from app.config import build_public_media_url
            public_url = build_public_media_url(filename, local_path=file_path)
            return VisualResult(
                url=public_url,
                theme=spec.theme,
                prompt_hash=prompt_hash,
                generated_by="dalle",
            )
        else:
            return VisualResult(url="", theme=spec.theme, prompt_hash=prompt_hash,
                                error=f"Download failed: HTTP {resp.status_code}")
    except Exception as e:
        return VisualResult(url="", theme=spec.theme, prompt_hash=prompt_hash,
                            error=f"Save failed: {e}")


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
