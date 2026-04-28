# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
hadith_caption_service.py — Grounded Hadith Caption Generator

Mirrors quran_caption_service.py in structure and discipline.

STRICT RULES:
- Uses exact reference and text from verified sunnah.now API response.
- The AI reflection is NEVER presented as the Hadith itself.
- narrator is cited only when the API returned it (never fabricated).
- grade is never mentioned (sunnah.now returns null for now).
- Caption cites the exact same reference that appears on the quote card.
"""

import logging
import re
from typing import Optional, Dict, Any
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)


HADITH_GROUNDED_PROMPT = """\
You are an expert Islamic content creator. Write a 3-line Instagram caption STRICTLY GROUNDED in the verified Hadith below.

VERIFIED HADITH SOURCE:
Reference: {reference}
{narrator_line}Translation: {translation_text}

STRICT RULES:
1. MAX 60 WORDS TOTAL for your entire output.
2. Line 1 MUST be the exact reference and a clean, natural English rendering of the Hadith text (or a meaningful excerpt if long). Do NOT alter its meaning.
3. Line 2 is a short, grounded reflection — a human realization that flows from this Hadith. NOT an AI summary. NOT a generic reminder.
4. Line 3 is a sharp, impactful closing (1 sentence). It must feel like a sudden shift in perspective.
5. NO hashtags, emojis, or bold text.
6. NO "spiritual jargon", "AI poetic" filler, or generic motivational phrases.
7. DO NOT present your reflection (Lines 2-3) as the Hadith itself.
8. The reflection may reference the Prophet ﷺ or the narrator naturally if it adds weight.
9. AVOID PHRASES: "true strength", "let your heart", "embrace the journey", "remember that", "source of", "in moments of".

OUTPUT STRUCTURE (STRICT — 3 lines separated by blank lines):
Line 1: "{reference}" + clean translation of the Hadith (or key excerpt)
Line 2: Deep realization (1 sentence)
Line 3: Sharp takeaway (1 sentence)

TONE: {tone_hint}

TASK: Generate the 3-line caption. Output only the caption — no labels, no preamble.
"""


TONE_MAP = {
    "calm":      "Grounded and reflective. Use weight and silence. Avoid airy language.",
    "direct":    "Strong and uncompromising. A firm, clear reminder of the truth.",
    "poetic":    "Lyrical but weighted. Use metaphors that resonate with the soul's longing.",
    "scholarly": "Precise and authoritative. Emphasize the depth of the prophetic tradition.",
}


def generate_hadith_caption(
    hadith_payload: Dict[str, Any],
    tone: str = "calm",
    intent: Optional[str] = None,
) -> str:
    """
    Generates an AI caption strictly grounded in the provided Hadith metadata.

    hadith_payload must contain:
        - reference (str)  — exact reference from API
        - translation_text (str) — full text from API
    Optionally:
        - narrator (str)  — taken verbatim from API
        - card_text (str) — safe excerpt (used if translation_text is very long)

    Returns a 3-line caption string (lines separated by double newlines).
    On failure, returns a clean fallback that still cites the reference.
    """
    reference = (hadith_payload.get("reference") or "").strip()
    # Prefer full translation_text for caption grounding; card_text is only for the card
    translation_text = (
        hadith_payload.get("translation_text")
        or hadith_payload.get("card_text")
        or ""
    ).strip()
    narrator_raw = (hadith_payload.get("narrator") or "").strip()

    if not reference:
        logger.error("[HadithCaption] Missing reference — cannot generate grounded caption")
        return _fallback_caption(reference, translation_text)

    if not translation_text:
        logger.error(f"[HadithCaption] Missing translation text for: {reference}")
        return _fallback_caption(reference, translation_text)

    if not settings.openai_api_key:
        logger.error("[HadithCaption] No OpenAI API key — returning fallback")
        return _fallback_caption(reference, translation_text)

    # If the translation is very long, use the first 400 chars for caption grounding
    # (the full text is preserved in post metadata; this is just for the LLM prompt)
    grounding_text = translation_text if len(translation_text) <= 450 else translation_text[:450].rsplit(" ", 1)[0] + "…"

    narrator_line = f"Narrator: {narrator_raw}\n" if narrator_raw else ""
    tone_hint = TONE_MAP.get(tone, TONE_MAP["calm"])

    prompt = HADITH_GROUNDED_PROMPT.format(
        reference=reference,
        narrator_line=narrator_line,
        translation_text=grounding_text,
        tone_hint=tone_hint,
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.65,
            timeout=30,
        )
        content = response.choices[0].message.content.strip() if response.choices else ""

        # Clean up any accidental markdown formatting
        content = content.replace("**", "").replace("__", "").replace("_", "")
        # Strip any label prefixes the model might add
        content = re.sub(
            r"^(Line \d:|Source:|Reflection:|Takeaway:|Insight:|Translation:|Caption:)\s*",
            "", content, flags=re.MULTILINE | re.IGNORECASE
        )

        raw_lines = [l.strip() for l in content.split("\n") if l.strip()]
        if len(raw_lines) >= 3:
            return "\n\n".join(raw_lines[:3])
        elif raw_lines:
            return "\n\n".join(raw_lines)

        logger.warning(f"[HadithCaption] LLM returned empty content for {reference}")
        return _fallback_caption(reference, translation_text)

    except Exception as e:
        logger.error(f"[HadithCaption] LLM error for {reference}: {e}")
        return _fallback_caption(reference, translation_text)


def _fallback_caption(reference: str, translation_text: str) -> str:
    """
    Clean fallback that still cites the exact reference.
    Never fabricates narrator or grade.
    """
    ref_line = f'"{reference}"' if reference else "Prophetic Hadith"
    # Use first 120 chars of translation if available
    excerpt = ""
    if translation_text:
        excerpt = translation_text[:120].rsplit(" ", 1)[0]
        if len(translation_text) > 120:
            excerpt += "…"

    if excerpt:
        return f"{ref_line} — {excerpt}\n\nThe Prophet ﷺ left us no room for ambiguity.\n\nAct on what you know."
    return f"{ref_line}\n\nThe Prophet ﷺ left us no room for ambiguity.\n\nAct on what you know."
