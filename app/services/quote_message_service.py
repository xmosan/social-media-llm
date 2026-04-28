# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def build_quote_card_message(source_type: str, source_payload: Dict[str, Any], tone: str = "calm", intent: str = "wisdom") -> Dict[str, Any]:
    """
    Orchestrator for building the structured content that appears ON THE CARD.
    """
    logger.info(f"[QUOTE_MESSAGE] Building card message for source_type: {source_type}")
    
    if source_type == "quran":
        return build_quran_quote_message(source_payload, tone, intent)
    elif source_type == "hadith":
        return build_hadith_quote_message(source_payload, tone, intent)
    elif source_type == "manual":
        return build_manual_quote_message(source_payload, tone, intent)
    else:
        # Fallback for library or other types
        return {
            "eyebrow": source_payload.get("reference", ""),
            "headline": source_payload.get("text", "Inspired by Divine Wisdom"),
            "supporting_text": ""
        }

def build_quran_quote_message(ayah_record: Dict[str, Any], tone: str, intent: str) -> Dict[str, Any]:
    """
    Strict literal logic for Quran card text.
    Uses exact DB translation and reference.
    """
    reference = ayah_record.get("reference") or ayah_record.get("verse_key")
    translation = ayah_record.get("translation_text") or ayah_record.get("text")
    
    if not reference or not translation:
        logger.error("[QUOTE_MESSAGE] Quran verse resolution failed: missing ref or translation")
        raise ValueError("Selected Quran verse is incomplete or invalid.")

    # Format eyebrow as "Qur'an {ref}"
    if not reference.lower().startswith("qur"):
        reference = f"Qur'an {reference}"

    logger.info(f"[QUOTE_MESSAGE] Quran verse resolved: {reference}")

    message = {
        "eyebrow": reference,
        "headline": translation,
        "supporting_text": "",
        "arabic_text": ayah_record.get("arabic_text", "")
    }
    
    logger.info("[QUOTE_MESSAGE] Card message built successfully")
    return message


def build_hadith_quote_message(hadith_record: Dict[str, Any], tone: str, intent: str) -> Dict[str, Any]:
    """
    Strict literal logic for Hadith card text.

    SAFETY CONTRACT:
    - reference, arabic_text, and translation_text come ONLY from the verified API response.
    - narrator is set only if the API returned it — never fabricated.
    - grade is never set here; it is not fabricated.
    - card_text is the safe excerpt produced by hadith_service._safe_excerpt().
      If card_text is absent, falls back to translation_text (full text).
    - Full translation_text is always preserved in metadata for caption and post storage.
    """
    reference = hadith_record.get("reference") or hadith_record.get("collection", "")
    collection = hadith_record.get("collection", "")

    # card_text is the safe excerpt from hadith_service (sentence-boundary truncated)
    # translation_text is always the full text
    card_text = (hadith_record.get("card_text") or hadith_record.get("translation_text") or "").strip()
    translation_text = (hadith_record.get("translation_text") or card_text).strip()
    arabic_text = (hadith_record.get("arabic_text") or "").strip()
    was_excerpted = bool(hadith_record.get("was_excerpted", False))

    if not reference:
        logger.error("[QUOTE_MESSAGE] Hadith resolution failed: missing reference")
        raise ValueError("Selected Hadith is missing a reference. Please choose another Hadith.")

    if not card_text and not arabic_text:
        logger.error(f"[QUOTE_MESSAGE] Hadith has no text content: {reference}")
        raise ValueError("Selected Hadith has no text content. Please choose another Hadith.")

    # Narrator — taken verbatim from API; never fabricated
    narrator_raw = (hadith_record.get("narrator") or "").strip()
    supporting_text = narrator_raw if narrator_raw else ""

    # Log for traceability
    logger.info(
        f"[QUOTE_MESSAGE] Hadith resolved: {reference} | "
        f"has_arabic={bool(arabic_text)} | has_en={bool(card_text)} | "
        f"was_excerpted={was_excerpted} | narrator={'yes' if narrator_raw else 'no'}"
    )

    return {
        # Eyebrow: exact reference (e.g. "Sahih al-Bukhari 1")
        "eyebrow": reference,
        # Arabic zone — full Arabic text; image_card renders it RTL via Amiri font
        "arabic_text": arabic_text,
        # Headline: safe excerpt (sentence-boundary truncated if long)
        "headline": card_text,
        # Supporting text: narrator if provided by API, else empty string
        "supporting_text": supporting_text,
        # Structural metadata — passed through to image_card for layout decisions
        "was_excerpted": was_excerpted,
        "hadith_narrator": narrator_raw or None,   # explicit field, never fabricated
        "hadith_collection": collection,
        # Full text always preserved for post storage and caption grounding
        "full_translation_text": translation_text,
    }


def build_manual_quote_message(payload: Dict[str, Any], tone: str = "calm", intent: str = "wisdom") -> Dict[str, Any]:
    # Check if this is a "topic" that needs expansion
    topic = payload.get("topic") or payload.get("reference")
    
    # If we have a specific headline already, use it (custom input)
    if payload.get("headline") or payload.get("text"):
        return {
            "eyebrow": payload.get("eyebrow", ""),
            "headline": payload.get("headline", payload.get("text", "")),
            "supporting_text": payload.get("supporting_text", "")
        }
    
    # Otherwise, if we only have a topic, use LLM to expand it
    if topic:
        from .llm import generate_card_message_from_topic
        logger.info(f"[QUOTE_MESSAGE] Expanding topic '{topic}' via LLM")
        return generate_card_message_from_topic(topic, tone, intent)

    return {
        "eyebrow": "",
        "headline": "Inspired by Divine Wisdom",
        "supporting_text": ""
    }
