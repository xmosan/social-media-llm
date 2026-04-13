ISLAMIC_CAPTION_PROMPT = """
You are an expert Islamic content creator who writes viral, high-impact reminders for Instagram. 
Your goal is to produce captions that feel human, grounded, and deeply reflective—never generic or AI-written.

STRICT RULES:
1. MAX 50 WORDS TOTAL.
2. NO generic motivational speaker language, "spiritual jargon", or "AI poetic" filler.
3. NO hashtags, emojis, or bold text.
4. NO over-explaining.
5. AVOID PHRASES: "in moments of", "true strength", "let your heart", "embrace the journey", "may we always", "find your way", "connection to", "remember that", "source of".
6. TRANSLATION STYLE: Rewrite the verse to use clean, Sahih-style English (e.g., "Indeed, with hardship comes ease.") Regardless of the input text, normalize it to feel natural and authoritative.

OUTPUT STRUCTURE (STRICT):
Line 1: Qur’an or Hadith (Clean translation + Reference)
Line 2: Deep realization/reflection (1 sentence)
Line 3: Sharp, impactful takeaway (1 sentence)

TONE GUIDELINES:
- Use simple, direct sentences.
- The closing line MUST hit hard. It should feel like a sudden perspective shift or a realization of truth.
- {tone_description}

STYLE EXAMPLES:
"So be patient with a beautiful patience." (Qur’an 70:5)
Real patience is staying quiet when you have every right to complain.
Allah knows the words you choose not to say.

"Indeed, with hardship comes ease." (Qur’an 94:5)
Ease isn't what comes after the struggle—it is what Allah carries you through.
The hardship was the preparation for the relief.

--------------------------------------------------

INPUT:
Intention: {intention}
Topic: {topic}
Tone: {tone}

VERIFIED SOURCE:
{source_text}
Reference: {reference}

--------------------------------------------------

TASK:
Generate a short Islamic reminder following ALL rules above. 
Do not use "reflection" or "takeaway" labels.
Keep it sharp, human, and impactful.
Only output the final caption.
"""




import requests
import re
import html
from openai import OpenAI
from app.config import settings
from app.db import SessionLocal
from app.models import ContentItem
from app.services.library_service import generate_topics_slugs
from app.services.quran_service import search_quran, get_quran_ayahs_by_theme
from app.services.quran_caption_service import generate_ai_caption_from_quran


# -------------------------------
# Prompt Builder
# -------------------------------
def build_caption_prompt(intention, topic, tone, tone_description, source_text, reference):
    return ISLAMIC_CAPTION_PROMPT.format(
        intention=intention,
        topic=topic,
        tone=tone,
        tone_description=tone_description,
        source_text=source_text,
        reference=reference
    )


# -------------------------------
# Quran Fetch
# -------------------------------
def fetch_quran_verse(topic: str):
    """
    Retrieves a relevant verse from the local Quran Foundation database.
    Prioritizes theme/slug matches, then falls back to keyword searching.
    """
    db = SessionLocal()
    try:
        # 1. Search existing themes in local DB
        results = get_quran_ayahs_by_theme(db, topic, limit=1)
        if results:
            item = results[0]
            print(f"📖 [CaptionEngine] Local Foundation match found for '{topic}': {item.title}")
            return {
                "item": item,
                "text": item.text,
                "arabic": item.arabic_text,
                "reference": item.title
            }
        
        # 2. General keyword search in local DB
        results = search_quran(db, topic, limit=1)
        if results:
            item = results[0]
            print(f"🔎 [CaptionEngine] Keyword match found for '{topic}': {item.title}")
            return {
                "item": item,
                "text": item.text,
                "arabic": item.arabic_text,
                "reference": item.title
            }

        return None
    except Exception as e:
        print(f"⚠️ [CaptionEngine] Local Foundation search error: {e}")
        return None
    finally:
        db.close()


# -------------------------------
# OpenAI Client
# -------------------------------
def get_openai_client():
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


# -------------------------------
# Caption Generator
# -------------------------------
def generate_islamic_caption(intention, topic, tone="calm"):
    print(f"👉 Phase 3 Generating caption for: {topic} (Tone: {tone})")

    client = get_openai_client()
    if not client:
        return "Error: OpenAI API Key is missing."

    # 1. Map tone to instructions
    tone_map = {
        "calm": "TONE: Grounded and reflective. Avoid airy-fairy language. Use weight and silence.",
        "direct": "TONE: Strong and uncompromising. A firm reminder that highlights the binary nature of truth.",
        "poetic": "TONE: Lyrical and deep. Use metaphors that resonate with the soul's longing for its Creator.",
        "scholarly": "TONE: Precise and heavy. Focus on the depth of the legacy and the weight of the tradition."
    }
    tone_instruction = tone_map.get(tone, "TONE: Sincere and grounded.")

    # 2. Fetch Verse (Unified Local Foundation Search)
    verse = fetch_quran_verse(topic)
    
    if verse and "item" in verse:
        # HIGH-FIDELITY GROUNDED GENERATION
        # We delegate to the new caption service for unified quality
        print(f"🔗 [CaptionEngine] Delegating grounded generation for '{topic}' to Quran Service.")
        return generate_ai_caption_from_quran(verse["item"], style=tone)

    # 3. Fallback (If no verse found)
    # -------------------------------
    source_translation = "Indeed, with every hardship comes ease."
    reference = "Qur'an 94:5"

    # Build Prompt
    prompt = build_caption_prompt(
        intention,
        topic,
        tone,
        tone_instruction,
        source_translation,
        reference
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            timeout=30
        )

        content = response.choices[0].message.content.strip() if response.choices else ""
        
        # 4. Final Cleanup & Enforcement
        content = content.replace("**", "").replace("_", "")
        # Remove labels
        content = re.sub(r"^(Line \d:|Source:|Reflection:|Takeaway:|Insight:|Translation:)\s*", "", content, flags=re.MULTILINE | re.IGNORECASE)
        
        # Hard Force 3-Line Structure with Double Newlines
        raw_lines = [l.strip() for l in content.split("\n") if l.strip()]
        
        # If AI merged lines, or used single newlines, we fix it
        final_lines = []
        if len(raw_lines) >= 3:
            final_lines = raw_lines[:3]
        else:
            # Fallback if structure broke
            final_lines = raw_lines + [""] * (3 - len(raw_lines))

        return "\n\n".join(final_lines)

    except Exception as e:
        print("❌ OpenAI error:", e)
        return "Indeed, with every hardship comes ease. (94:5)\n\nTrust that Allah sees your struggle.\n\nHe has not forgotten you."
        
    