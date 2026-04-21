# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import json
from typing import Dict, Any
from app.services.llm import get_client

def validate_source_relevance(topic: str, content_text: str, reference: str = "") -> Dict[str, Any]:
    """
    Uses LLM to verify if a candidate piece of content is semantically relevant to a topic.
    Returns a structured validation result.
    """
    client = get_client()
    if not client:
        # Fallback to permissive if AI is offline to avoid blocking automation
        return {"accepted": True, "confidence": "low", "reason": "ai_offline_permissive"}

    prompt = f"""
    You are a Content Integrity Auditor for an Islamic social media platform.
    
    TOPIC: {topic}
    CONTENT (Reference: {reference}):
    "{content_text}"
    
    TASK:
    Determine if this content is HIGHLY RELEVANT and APPROPRIATE to use for a social media post about the provided topic.
    
    CRITICAL RULES:
    1. REJECT if the text is about a completely different subject (e.g., topic is 'Patience' but text is about 'Satan' or 'Hellfire' without constructive context).
    2. REJECT if the text is negative, harsh, or strictly about punishment, unless the topic specifically asks for it (e.g. 'Warning against Arrogance').
    3. ACCEPT if the text clearly supports, illustrates, or provides wisdom regarding the topic.
    
    JSON OUTPUT FORMAT:
    {{
        "accepted": true/false,
        "confidence": "high" | "medium" | "low",
        "reason": "short explanation"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        print(f"[RELEVANCE] topic='{topic}' ref='{reference}' result={result['accepted']} reason='{result['reason']}'")
        return result
    except Exception as e:
        print(f"[RELEVANCE] Error in AI relevance gate: {e}")
        return {"accepted": True, "confidence": "low", "reason": f"error: {str(e)}"}
