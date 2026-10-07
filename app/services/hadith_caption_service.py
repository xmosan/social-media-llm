# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.


from typing import Any, Optional
from app.services.source_caption import compose_source_caption


def generate_hadith_caption(hadith_payload: dict[str, Any], tone: str = "calm", intent: Optional[str] = None, *, editorial_context: str = "") -> str:
    """Preserve the full translation and returned narrator separately from reflection."""
    return compose_source_caption(hadith_payload, "hadith", tone, editorial_context=editorial_context)
