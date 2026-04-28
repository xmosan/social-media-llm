# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def build_quote_card_message(source_type: str, source_payload: Dict[str, Any], tone: str = "calm", intent: str = "wisdom", custom_prompt: str = "") -> Dict[str, Any]:
    """
    Orchestrator for building the structured content that appears ON THE CARD.
    """
    logger.info(f"[QUOTE_MESSAGE] Building card message for source_type: {source_type}")
    
    if source_type == "quran":
        return build_quran_quote_message(source_payload, tone, intent, custom_prompt)
    elif source_type == "hadith":
        return build_hadith_quote_message(source_payload, tone, intent, custom_prompt)
    elif source_type == "manual":
        return build_manual_quote_message(source_payload, tone, intent)
    else:
        # Fallback for library or other types
        return {
            "eyebrow": source_payload.get("reference", ""),
            "headline": source_payload.get("text", "Inspired by Divine Wisdom"),
            "supporting_text": ""
        }

def build_quran_quote_message(ayah_record: Dict[str, Any], tone: str, intent: str, custom_prompt: str = "") -> Dict[str, Any]:
    """
    Safely generates framing text for the Quran quote card using the LLM, while
    locking the primary headline to the exact translation text.
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

    from .llm import generate_card_framing_from_source
    framing = generate_card_framing_from_source(
        source_text=translation, 
        intent=intent, 
        tone=tone, 
        custom_prompt=custom_prompt,
        source_type="quran",
        reference=reference
    )

    message = {
        "eyebrow": framing.get("eyebrow", reference),
        "headline": translation,
        "supporting_text": framing.get("supporting_text", ""),
        "arabic_text": ayah_record.get("arabic_text", "")
    }
    
    logger.info("[QUOTE_MESSAGE] Card message built successfully")
    return message


def build_hadith_quote_message(hadith_record: Dict[str, Any], tone: str, intent: str, custom_prompt: str = "") -> Dict[str, Any]:
    """
    Safely generates framing text for the Hadith quote card using the LLM, while
    locking the primary headline to the safe excerpt / translation.
    """
    reference = hadith_record.get("reference") or hadith_record.get("collection", "")
    collection = hadith_record.get("collection", "")

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

    narrator_raw = (hadith_record.get("narrator") or "").strip()

    from .llm import generate_card_framing_from_source
    framing = generate_card_framing_from_source(
        source_text=card_text, 
        intent=intent, 
        tone=tone, 
        custom_prompt=custom_prompt,
        source_type="hadith",
        reference=reference
    )
    
    # Append narrator to supporting text if present
    supporting = framing.get("supporting_text", "")
    if narrator_raw:
        supporting = f"Narrated {narrator_raw}: " + supporting if supporting else narrator_raw

    logger.info(
        f"[QUOTE_MESSAGE] Hadith resolved: {reference} | "
        f"has_arabic={bool(arabic_text)} | has_en={bool(card_text)} | "
        f"was_excerpted={was_excerpted} | narrator={'yes' if narrator_raw else 'no'}"
    )

    return {
        "eyebrow": framing.get("eyebrow", reference),
        "arabic_text": arabic_text,
        "headline": card_text,
        "supporting_text": supporting,
        "was_excerpted": was_excerpted,
        "hadith_narrator": narrator_raw or None,
        "hadith_collection": collection,
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
