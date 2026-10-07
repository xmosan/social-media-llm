# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from typing import Dict, Any
from app.services.text_provider import generate_text, Relevance, TextGenerationError

def validate_source_relevance(topic: str, content_text: str, reference: str = "") -> Dict[str, Any]:
    """
    Uses LLM to verify if a candidate piece of content is semantically relevant to a topic.
    Rejects unverifiable matches, including provider outages.
    """
    # Optimization: If topic is very short, expand it slightly for the auditor
    audit_topic = topic
    if len(topic) < 15:
        audit_topic = f"{topic} (including related concepts of spiritual wisdom, practice, and character)"

    prompt = f"""
    You are a Content Integrity Auditor for Sabeel Studio, a premium Islamic platform.
    
    TOPIC: {audit_topic}
    CONTENT (Reference: {reference}):
    "{content_text}"
    
    TASK:
    Audit this candidate verse/text for a social media post about the provided topic.
    
    STRICT REJECTION RULES:
    1. REJECT (accepted: false) if the text is about a specific historical event or story (e.g.Lot, Pharaoh, People of the City) that does NOT clearly illustrate the topic's attribute.
    2. REJECT if the connection is forced or weak.
    3. REJECT if the text is primarily about punishment, hellfire, or negative outcomes, unless the topic is specifically about 'Warning' or 'Consequences'.
    4. REJECT if the text is irrelevant (e.g. topic is 'Patience' but text is 15:67 "And the people of the city came rejoicing").
    
    STRICT ACCEPTANCE RULES:
    1. ACCEPT only if a reader would immediately see the connection without needing a complex explanation.
    2. Judge only the supplied text. Do not rely on remembered wording or metadata for the reference.

    JSON OUTPUT:
    {{
        "accepted": true/false,
        "confidence": "high" | "medium" | "low",
        "reason": "short explanation of the semantic link or lack thereof"
    }}
    """

    try:
        result = generate_text(prompt, schema=Relevance, utility=True)
        # FORCE REJECTION if confidence is low to stay safe
        if result.get("confidence") == "low":
            result["accepted"] = False
            result["reason"] = f"Low confidence match: {result.get('reason')}"
            
        print(f"🛡️ [RELEVANCE_GATE] topic='{topic}' ref='{reference}' -> {result['accepted']} ({result['confidence']})")
        return result
    except TextGenerationError:
        return {"accepted": False, "confidence": "low", "reason": "relevance_check_unavailable"}
