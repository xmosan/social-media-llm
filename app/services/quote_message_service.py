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
    elif source_type == "manual":
        return build_manual_quote_message(source_payload)
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

    # For now, literal translation is the headline.
    # In the future, we can add 'supporting_text' grounded reflection if needed.
    
    message = {
        "eyebrow": reference,
        "headline": translation,
        "supporting_text": ""
    }
    
    logger.info("[QUOTE_MESSAGE] Card message built successfully")
    return message

def build_manual_quote_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "eyebrow": payload.get("eyebrow", ""),
        "headline": payload.get("headline", payload.get("text", "")),
        "supporting_text": payload.get("supporting_text", "")
    }
