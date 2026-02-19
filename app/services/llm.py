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
    banned_phrases: list[str] | None = None
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
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a professional social media manager specializing in high-engagement content."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # Final check on hashtags if they come back as strings or other types
    if not isinstance(result.get("hashtags"), list):
        result["hashtags"] = []

    return result