# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.


from app.services.source_caption import compose_source_caption
from app.services.quran_serialization import normalize_quran_verse


def generate_ai_caption_from_quran(item_or_payload, style: str = "reflective") -> str:
    """Keep the source immutable; generate only a separately labeled reflection."""
    if isinstance(item_or_payload, dict):
        payload = dict(item_or_payload)
        payload["reference"] = payload.get("reference") or payload.get("source_reference")
        payload["translation_text"] = payload.get("translation_text") or payload.get("main_text")
    else:
        payload = normalize_quran_verse(item_or_payload)
    return compose_source_caption(payload, "quran", style)
