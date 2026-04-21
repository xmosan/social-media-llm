# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from typing import Any
import json
from openai import OpenAI
from app.config import settings

def get_client():
    """Returns a live OpenAI client, or None if key is not configured."""
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)

def generate_draft(
    source_text: str,
    intent: str | None = None,
    audience: str | None = None,
    source_foundation: str | None = None,
    emotion: str | None = None,
    depth: str | None = None,
    post_format: str | None = None,
    visual_style: str | None = None,
    hook_style: str | None = None,
    strictness: str = "balanced"
) -> dict[str, Any]:
    """
    Structured generator for high-integrity Islamic content.
    Respects strictness guidelines and intent parameters.
    """
    client = get_client()
    if not client:
        # Mock logic for UI testing environments
        return {
            "hook": "Seeking the Path of Sabr",
            "caption": "Patience is not just waiting; it is how we behave while we wait for Allah's decree. This reflection explores the depth of spiritual endurance.",
            "source": "Qur'an 2:153",
            "hashtags": ["Islam", "Sabr", "Faith"],
            "tone_notes": "Gentle, reassuring, and spiritually grounded.",
            "alt_text": "Minimalistic calligraphy on a serene background."
        }
    
    # 1. Construct Strictness Directives
    strict_clause = ""
    if strictness == "strict":
        strict_clause = """
        STRICT MODE ACTIVE: 
        - DO NOT add creative analogies or modern slang.
        - DO NOT paraphrase sacred texts loosely. 
        - Use traditional, scholarly, and literal language.
        - If a source is provided, use it exactly.
        - If no clear source or reference exists, state 'General Reflection' and DO NOT fabricate a Hadith number.
        """
    elif strictness == "balanced":
        strict_clause = """
        BALANCED MODE:
        - Harmonize traditional wisdom with contemporary understanding.
        - Maintain spiritual depth while making it accessible.
        - Use inspired reflections to connect the source to daily life.
        """
    else: # creative
        strict_clause = """
        CREATIVE MODE:
        - Use storytelling, metaphors, and modern applications.
        - Focus on the emotional and psychological impact.
        - Feel free to expand on the message for maximum inspiration.
        """

    # 2. Build the Global Prompt
    prompt = f"""
    ROLE: You are an expert Islamic Content Designer specializing in authentic and engaging social media education.

    INPUT PARAMETERS:
    - Intent: {intent or 'Daily Reminder'}
    - Target Audience: {audience or 'General Muslims'}
    - Source Foundation: {source_foundation or 'General'}
    - Core Seed/Message: {source_text}
    - Emotion: {emotion or 'Spiritual'}
    - Intellectual Depth: {depth or 'Moderate'}
    - Post Format: {post_format or 'Feed Post'}
    - Hook Style: {hook_style or 'Inspirational'}
    
    {strict_clause}

    TASK: Generate a high-integrity social media post.
    
    CONSTRAINTS:
    1. Hook: A powerful first line (max 90 chars).
    2. Caption: The primary body text. High conversion, respectful, and meaningful.
    3. Source: Proper attribution (e.g., 'Sahih Bukhari #123' or 'Surah Al-Baqarah 2:153').
    4. Tone/Notes: A brief note for the creator on the intended delivery tone.
    5. Alt Text: Descriptive text for accessibility.

    OUTPUT FORMAT: Strictly JSON.
    {{
        "hook": "text",
        "caption": "text",
        "source": "text",
        "hashtags": ["list", "of", "relevant", "hashtags"],
        "tone_notes": "text",
        "alt_text": "text"
    }}
    """
    
    response = client.chat.completions.create(
        model="gpt-4", # Use GPT-4 for intelligence tasks if possible
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

def generate_topic_caption(
    topic: str,
    style: str = "islamic_reminder",
    tone: str = "medium",
    language: str = "english",
    banned_phrases: list[str] | None = None,
    content_profile_prompt: str | None = None,
    creativity_level: int = 3,
    extra_context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Generates a caption based on a topic and various style parameters using OpenAI."""
    client = get_client()
    if not client:
        # Return a structured failure dict rather than crashing — runner's guardrails handle it
        return {
            "caption": "",
            "hashtags": [],
            "alt_text": "",
            "validation_failed": True,
            "fail_reason": "llm_client_unavailable"
        }
    
    style_content = {
        "islamic_reminder": "an Islamic reminder style with wisdom and spiritual depth",
        "educational": "an educational and informative tone",
        "motivational": "a high-energy motivational and encouraging tone"
    }.get(style, "a professional and engaging tone")

    tone_content = {
        "short": "keep it under 150 characters",
        "medium": "standard length, about 2-3 paragraphs",
        "long": "detailed and immersive, about 5-6 paragraphs"
    }.get(tone, "balanced length")

    lang_content = "English" if language == "english" else "a mix of English and Arabic phrases (like SubhanAllah, Alhamdulillah, etc.)"

    banned_prompt = f"Avoid these specific words/phrases: {', '.join(banned_phrases)}" if banned_phrases else ""

    # Grounding Context Logic
    grounding_prompt = ""
    special_instructions = []
    
    if extra_context:
        mode = extra_context.get("mode")
        
        if mode == "auto_library" and extra_context.get("sources"):
            sources = extra_context["sources"]
            sources_text = "\n".join([
                f"- Excerpt: {s['chunk_text']}\n  Source: {s['doc_title']}\n  URL: {s.get('url') or 'N/A'}\n  Page: {s.get('chunk_metadata', {}).get('page') or 'N/A'}"
                for s in sources
            ])
            grounding_prompt = f"\nLIBRARY SOURCES (Source of Truth):\n{sources_text}\n"
            special_instructions.append("Use ONE short excerpt (max 1-2 sentences) from the provided library sources verbatim.")
            special_instructions.append("Cite the source title and URL/Page clearly at the end of the caption or reflection.")
            special_instructions.append("Do NOT fabricate quotes or information not present in the sources.")
            
        elif mode == "manual_seed" and extra_context.get("manual_seed"):
            grounding_prompt = f"\nMANUAL SEED CONTENT:\n{extra_context['manual_seed']}\n"
            special_instructions.append("The caption must be grounded in and reflect the provided manual seed content.")
        
        elif mode == "grounded_library" and extra_context.get("snippet"):
            s = extra_context["snippet"]
            item_type = s.get("item_type", "reference")
            grounding_prompt = f"\nGROUNDED LIBRARY SNIPPET (Source of Truth):\nType: {item_type}\nText: {s['text']}\nReference: {s.get('reference') or 'N/A'}\nSource: {s.get('source') or 'N/A'}\n"
            
            if item_type in ['quran', 'hadith']:
                special_instructions.append("You MUST quote the provided text VERBATIM (word-for-word) at the start of the caption.")
                special_instructions.append(f"You MUST include the reference exactly as provided: {s.get('reference') or ''}")
                special_instructions.append("Do NOT summarize the sacred text. Quote it exactly.")
            else:
                special_instructions.append("Summarize the snippet OR quote exactly ONE short sentence from it.")
                special_instructions.append(f"You MUST include the reference exactly as provided: {s.get('reference') or ''}")

            special_instructions.append("STRICT: Do NOT fabricate hadith. Do NOT fabricate references.")
            special_instructions.append("STRICT: Do NOT add generic filler like 'Enhance your daily reminder' or 'AUTO:'.")
            if not s.get("text"):
                special_instructions.append("IMPORTANT: No valid snippet was found. Generate a generic Islamic reflection without any specific quotes or references.")
        
        # Backward compatibility or additional instructions
        if extra_context.get("instructions"):
            if isinstance(extra_context["instructions"], list):
                special_instructions.extend(extra_context["instructions"])
            else:
                special_instructions.append(extra_context["instructions"])

    extra_instructions_str = ""
    if special_instructions:
        extra_instructions_str = "\nSPECIAL INSTRUCTIONS:\n" + "\n".join([f"- {instr}" for instr in special_instructions])

    prompt = f"""
    Topic/Concept: {topic}
    Style Preference: {style_content}
    Desired Tone: {tone_content}
    Primary Language: {lang_content}
    {banned_prompt}
    {grounding_prompt}
    {extra_instructions_str}

    Task: Generate a professional social media caption, hashtags, and alt text for an Islamic reminder.
    
    CRITICAL RULES:
    1. DO NOT include generic filler like "Enhance your daily reminder", "Welcome to our page", or "Here is your caption".
    2. Write a unique, meaningful caption specifically about the topic/concept provided.
    3. If GROUNDING CONTENT (snippet) is provided, you MUST start the caption by quoting the provided verse/text verbatim (or the key sentence if long), followed immediately by the reference.
    4. CITE SOURCES STRICTLY: If citing the Qur'an or Hadith, use the provided reference EXACTLY. NEVER make up a reference.
    5. NO meta-talk. No "Certainly", no "Here is your caption".
    6. DO NOT return the topic or the automation name as the caption itself.
    
    Return JSON:
    {{
        "caption": "the caption text",
        "hashtags": ["hashtag1", "hashtag2"],
        "alt_text": "description for screen readers"
    }}
    """

    print(f"[DEBUG] Prompting LLM for topic: {topic}")
    
    system_msg = content_profile_prompt if content_profile_prompt else "You are a professional social media manager specializing in high-engagement content."
    system_msg += f" Creativity Level: {creativity_level}/5."
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
    except Exception as e:
        print(f"[LLM] OpenAI API call failed: {e}")
        raise RuntimeError(f"LLM Generation failed: {str(e)}")
    
    result = json.loads(response.choices[0].message.content)
    caption = result.get("caption", "").strip()
    
    # STRICT VALIDATION
    is_invalid = False
    fail_reason = None
    
    if not caption:
        is_invalid = True
        fail_reason = "empty_caption"
    elif caption.lower() == topic.lower():
        is_invalid = True
        fail_reason = "caption_equals_topic"
    elif caption.startswith("AUTO:"):
        is_invalid = True
        fail_reason = "caption_starts_with_auto"
    elif "enhance your daily reminder" in caption.lower():
        is_invalid = True
        fail_reason = "contains_generic_filler"
    elif len(caption) < 20:
        is_invalid = True
        fail_reason = "caption_too_short"

    if is_invalid:
        print(f"[LLM] Validation failed: {fail_reason}. Raw output: {caption}")
        # According to requirement D.2:
        # mark post.status = "failed", set flags.reason = "invalid_generated_caption"
        # Since this function returns a dict to the runner, we add these flags.
        result["validation_failed"] = True
        result["fail_reason"] = fail_reason
    
    # Final check on hashtags if they come back as strings or other types
    if not isinstance(result.get("hashtags"), list):
        result["hashtags"] = []

    return result

def generate_topic_variations(topic: str, count: int = 5) -> list[str]:
    """Generates X sub-angles or variations for a given topic to provide variety."""
    from app.services.caption_engine import get_openai_client as get_real_client
    client = get_real_client()
    
    # Structural determinisic fallback generator
    def get_fallback():
        return [
            f"The Wisdom of {topic}",
            f"Reflections on {topic}",
            f"Understanding {topic}",
            f"The Spiritual Depth of {topic}",
            topic
        ][:count]

    if not client:
        print("[LLM][WARN] topic variation generator unavailable, using fallback")
        return get_fallback()

    prompt = f"Given the topic '{topic}', generate {count} diverse sub-angles or specific perspectives for a social media post. Return as a JSON list of strings."
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        # Search for any list in the object
        for v in data.values():
            if isinstance(v, list) and len(v) > 0:
                return v[:count]
        return get_fallback()
    except Exception as e:
        print(f"[LLM][ERROR] Topic variation client unavailable: {str(e)}")
        print("[LLM][FALLBACK] Using deterministic topic variation fallback")
        return get_fallback()

def generate_caption_from_content_item(
    content_item: Any, # Use Any because of circular import risk with models
    style: str = "islamic_reminder",
    tone: str = "medium",
    language: str = "english",
    banned_phrases: list[str] | None = None,
    include_arabic: bool = False,
    extra_hashtag_set: list[str] | None = None,
    content_profile_prompt: str | None = None,
    creativity_level: int = 3
) -> dict[str, Any]:
    """
    Asks LLM to generate a reflection and hashtags for a specific DB content item.
    Enforces verbatim text usage by constructing the final caption on server side.
    """
    client = get_client()
    
    # 1. Prepare Content Snippet for LLM
    text_to_show = content_item.text_en
    if include_arabic and content_item.text_ar:
        text_to_show = f"{content_item.text_ar}\n\n{text_to_show}"
        
    prompt = f"""
    Content Item (verbatim): {text_to_show}
    Topic: {content_item.topics[0] if content_item.topics else "general"}
    Source: {content_item.source_name or "Unknown"} ({content_item.reference or "No ref"})
    Style: {style}
    Tone: {tone}
    Language: {language}
    {f"Banned phrases (AVOID): {', '.join(banned_phrases)}" if banned_phrases else ""}

    Your Task:
    1. Write a 1-2 sentence meaningful reflection about this specific piece of content. 
    2. Do NOT change the content text above. Just reflect on it.
    3. Suggest relevant hashtags.
    4. Provide an alt-text description for the content.

    Return JSON format:
    {{
        "reflection": "Your 1-2 sentence reflection here",
        "hashtags": ["hashtag1", "hashtag2"],
        "alt_text": "description for screen readers"
    }}
    """
    
    system_msg = content_profile_prompt if content_profile_prompt else "You are a professional social media manager. You write brief, powerful reflections for authentic narrations and quotes."
    system_msg += f" Creativity Level: {creativity_level}/5."
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # 2. Server-side Assembly (Enforce Verbatim)
    # We do NOT let the LLM provide the "caption" field to avoid edits to the hadith text.
    reflection = result.get("reflection", "").strip()
    
    final_caption = f'"{text_to_show}"'
    if reflection:
        final_caption += f"\n\n{reflection}"
        
    # Append attribution
    attribution = ""
    if content_item.source_name:
        attribution = content_item.source_name
        if content_item.reference:
            attribution += f" ({content_item.reference})"
    
    if attribution:
        final_caption += f"\n\n— {attribution}"
        
    if content_item.url:
        final_caption += f"\nSource: {content_item.url}"
        
    # Merge hashtags
    suggested_hashtags = result.get("hashtags", [])
    if not isinstance(suggested_hashtags, list):
        suggested_hashtags = []
        
    all_hashtags = suggested_hashtags
    if extra_hashtag_set:
        # Avoid duplicates
        all_hashtags = list(set(all_hashtags + extra_hashtag_set))

    return {
        "caption": final_caption,
        "hashtags": all_hashtags,
        "alt_text": result.get("alt_text", "Image describing religious content"),
        "reflection": reflection # Original for debugging
    }

def generate_ai_image(prompt_text: str) -> str | None:
    """Generates an image using DALL-E 3 based on the prompt."""
    client = get_client()
    try:
        print(f"[LLM] Requesting DALL-E 3 image for concept: {prompt_text[:50]}...")
        response = client.images.generate(
            model="dall-e-3",
            prompt=f"A professional, premium, and minimalistic image representing this concept: {prompt_text[:500]}. NO text, NO letters, NO words, NO calligraphy. The image should be text-free, artistic, and suitable for social media. Ensure cinematic lighting and a serene atmosphere.",
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        print(f"[LLM] Error generating AI image: {e}")
        return None

def refine_caption(text: str, refinement_type: str) -> str:
    """Refines an existing caption based on a specific goal."""
    client = get_client()
    
    prompts = {
        "emotional": "Rewrite this Islamic social media post to be more emotionally resonant, heart-felt, and spiritually moving. Maintain sincerity and avoid exaggeration.",
        "shorter": "Make this post significantly shorter and more concise (max 2-3 sentences) while keeping the core spiritual message intact.",
        "ayah": "Find a relevant and authentic Quran ayah (verse) in English that complements this message. Add it at the beginning with proper citation (Surah:Verse).",
        "hadith": "Find a relevant and authentic Hadith in English that supports this message. Add it with proper citation.",
        "clarity": "Improve the clarity, flow, and professional tone of this post. Use bullet points if helpful for legibility."
    }
    
    directive = prompts.get(refinement_type, "Improve this social media post.")
    
    if not client:
        # Mock responses for UX testing
        if refinement_type == "shorter":
            return "Trusting Allah's plan is the essence of Sabr. Even in silence, He is working for your good."
        elif refinement_type == "emotional":
            return "Let your heart find rest in the remembrance of the Most Merciful. Every tear and every prayer is seen by Him. ❤️"
        return text + f"\n\n[Refined for {refinement_type.upper()}: This is a mock response because the OpenAI client is currently disabled in this environment.]"

    prompt = f"{directive}\n\nOriginal Text: {text}\n\nRefined Text:"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional social media editor specializing in Islamic content."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] Refinement failed: {e}")
        return text # Return original if failed
def generate_card_message_from_topic(topic: str, tone: str = "calm", intent: str = "wisdom") -> dict[str, Any]:
    """
    Generates structured content specifically for a visual quote card based on a topic.
    """
    client = get_client()
    if not client:
        return {
            "eyebrow": "Timeless Wisdom",
            "headline": f"Reflecting on {topic}",
            "supporting_text": "May your heart find peace in remembrance."
        }

    prompt = f"""
    Topic: {topic}
    Tone: {tone}
    Intent: {intent}

    Task: Generate a deep, soul-stirring 3-part structured message for a premium Islamic visual quote card.
    
    IMPORTANT: Do NOT repeat the topic as the headline unless it is part of a larger contemplative phrase. Focus on the spiritual depth, the wisdom behind it, and the emotional resonance.

    Card Structure:
    1. Eyebrow: A very short (1-3 words) context or category (e.g., 'DIVINE MERCY', 'TRUE PATIENCE', 'INNER PEACE').
    2. Headline: A powerful, original spiritual realization or wisdom (max 15 words). MUST be punchy and visually striking. Do NOT just say "{topic}". Instead, express the ESSENCE of {topic}. 
    3. Supporting Text: A deep, 1-sentence reflection to ground the headline in daily practice or heart-work.

    Format: JSON only.
    {{
        "eyebrow": "string",
        "headline": "string",
        "supporting_text": "string"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a master of spiritual typography and minimalist Islamic content design."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[LLM] Card message generation failed: {e}")
        return {
            "eyebrow": topic.upper(),
            "headline": f"The Essence of {topic}",
            "supporting_text": "Searching for deeper meaning in the path of the righteous."
        }
