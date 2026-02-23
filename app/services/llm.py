from typing import Any
import json
from openai import OpenAI
from app.config import settings

def get_client():
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Please set it in your environment or .env file.")
    return OpenAI(api_key=settings.openai_api_key)

def generate_draft(source_text: str, media_hint: str | None = None) -> dict[str, Any]:
    """Generates a caption draft from raw source text."""
    client = get_client()
    
    prompt = f"""
    Generate a social media caption and alt text for the following content.
    Content: {source_text}
    Media Hint: {media_hint or 'Standard image'}
    
    Return JSON format:
    {{
        "caption": "The main caption text",
        "hashtags": ["list", "of", "relevant", "hashtags"],
        "alt_text": "Accessibility alt text"
    }}
    """
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
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
    creativity_level: int = 3
) -> dict[str, Any]:
    """Generates a caption based on a topic and various style parameters using OpenAI."""
    client = get_client()
    
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

    prompt = f"""
    Topic: {topic}
    Style: {style_content}
    Tone: {tone_content}
    Language: {lang_content}
    {banned_prompt}

    Generate a high-quality Instagram/Facebook caption, alt text, and relevant hashtags.
    
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
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # Final check on hashtags if they come back as strings or other types
    if not isinstance(result.get("hashtags"), list):
        result["hashtags"] = []

    return result

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
            prompt=f"Generate a highly realistic nature photograph or elegant Islamic calligraphy representing this concept: {prompt_text[:500]}. Do not include any English text or random letters. Ensure the image is beautiful, serene, and has cinematic lighting.",
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        print(f"[LLM] Error generating AI image: {e}")
        return None