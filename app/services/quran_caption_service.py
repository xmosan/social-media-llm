# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import logging
import re
from openai import OpenAI
from app.config import settings
from app.models import ContentItem

logger = logging.getLogger(__name__)

QURAN_GROUNDED_PROMPT = """
You are an expert Islamic content creator. You are crafting a viral, deeply reflective caption for Instagram that is STRICTLY GROUNDED in a specific Quranic verse.

VERIFIED QURANIC BASELINE:
Reference: {reference}
Arabic: {arabic_text}
Translation: {translation_text}

STRICT RULES:
1. MAX 50 WORDS TOTAL for your reflection.
2. DO NOT change the translation text provided above. Use it exactly.
3. NO hashtags, emojis, or bold text.
4. NO "spiritual jargon" or AI poetic filler.
5. NO mentions of "AI", "LLM", or "models".

OUTPUT STRUCTURE (STRICT):
Line 1: {reference}
Line 2: {translation_text}
Line 3: A deep realization connecting this verse to life + an impactful closing takeaway (2 short sentences).

TONE: {tone_hint}

TASK:
Craft the caption based on the provided verse. Only output the final 3-line structured caption.
"""

def generate_ai_caption_from_quran(item: ContentItem, style: str = "reflective") -> str:
    """
    Generates an AI caption that is strictly grounded in the provided ContentItem (Quran Verse).
    """
    if not settings.openai_api_key:
        logger.error("❌ [QuranCaption] Missing OpenAI API Key.")
        return f"{item.text} ({item.title})\n\nTrust in the wisdom of your Creator.\n\nHe knows what you do not."

    client = OpenAI(api_key=settings.openai_api_key)
    
    tone_map = {
        "reflective": "Grounded and quiet. Focus on the internal shift of the heart.",
        "direct": "Strong and firm. A clear warning or instruction for the soul.",
        "poetic": "Lyrical but weighted. Use metaphors found in nature or archetypes.",
        "scholarly": "Precise and authoritative. Focus on the timeless nature of the truth."
    }
    tone_hint = tone_map.get(style, tone_map["reflective"])

    prompt = QURAN_GROUNDED_PROMPT.format(
        reference=item.title,
        arabic_text=item.arabic_text or "N/A",
        translation_text=item.text,
        tone_hint=tone_hint
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=30
        )

        content = response.choices[0].message.content.strip() if response.choices else ""
        
        # Cleanup any accidental formatting
        content = content.replace("**", "").replace("_", "")
        raw_lines = [l.strip() for l in content.split("\n") if l.strip()]
        
        # Ensure 3-line structure
        if len(raw_lines) >= 3:
            return "\n\n".join(raw_lines[:3])
        return content # Fallback 
        
    except Exception as e:
        logger.error(f"❌ [QuranCaption] LLM Error: {e}")
        return f"{item.text} ({item.title})\n\nAllah is always with the patient.\n\nKeep moving forward."
