# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
import logging
from app.services.text_provider import generate_text, SocialCaption
from typing import Dict, Any

logger = logging.getLogger(__name__)

# SOCIAL CAPTION SYSTEM PROMPT
SOCIAL_CAPTION_PROMPT = """
You are a world-class Instagram & Social Media storyteller. Your task is to craft a HIGH-CONVERTING, soulful social media caption grounded in a specific source.

SOURCE CONTENT:
Type: {source_type}
Reference: {reference}
Text: {source_text}

TONE: {tone_hint}
INTENTION: {intention}
PLATFORM: {platform}

STRICT OUTPUT STRUCTURE (JSON ONLY):
{{
  "hook": "A 1-sentence scroll-stopping opening line (under 15 words)",
  "body": "2-3 short, punchy paragraphs of reflective storytelling or spiritual realization. Use line breaks for readability.",
  "cta": "A clear Call to Action (e.g., 'Share this with someone who needs it', 'Save for your next reflection')",
  "hashtags": ["#islam", "#faith", "#reminder", "..."] 
}}

RULES:
1. DO NOT mention "AI", "algorithm", or "LLM".
2. Keep it authentic. 
3. Only output valid JSON.
"""

def generate_caption_from_source(
    source_type: str, 
    source_payload: Dict[str, Any], 
    tone: str = "calm", 
    intention: str = "wisdom", 
    platform: str = "instagram"
) -> Dict[str, Any]:
    """
    Generates a social media caption (Hook, Body, CTA, Hashtags) decoupled from card text.
    """
    logger.info(f"[CAPTION] Generating caption for {source_type}")

    if source_type in {"quran", "hadith"}:
        from app.services.source_caption import compose_source_caption
        caption = compose_source_caption(source_payload, source_type, tone)
        return {"hook": "", "body": caption, "cta": "", "hashtags": []}
    
    reference = source_payload.get("reference") or source_payload.get("source_reference") or "N/A"
    source_text = source_payload.get("translation_text") or source_payload.get("text") or "N/A"
    
    if source_type == "quran":
        logger.info(f"[CAPTION] Quran source grounded: {reference}")
    
    tone_map = {
        "reflective": "Grounded and quiet. Focus on the internal shift of the heart.",
        "direct": "Strong and firm. A clear warning or instruction for the soul.",
        "poetic": "Lyrical but weighted. Use metaphors found in nature or archetypes.",
        "scholarly": "Precise and authoritative. Focus on the timeless nature of the truth.",
        "calm": "Soft, serene, and peaceful. Aim to soothe the reader's spirit."
    }
    tone_hint = tone_map.get(tone, tone_map["calm"])

    prompt = SOCIAL_CAPTION_PROMPT.format(
        source_type=source_type,
        reference=reference,
        source_text=source_text,
        tone_hint=tone_hint,
        intention=intention,
        platform=platform
    )

    return generate_text(prompt, schema=SocialCaption)
