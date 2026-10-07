ISLAMIC_CAPTION_PROMPT = """
You are an expert Islamic content creator who writes viral, high-impact reminders for Instagram. 
Your goal is to produce captions that feel human, grounded, and deeply reflective—never generic or AI-written.

STRICT RULES:
1. MAX 50 WORDS TOTAL.
2. NO generic motivational speaker language, "spiritual jargon", or "AI poetic" filler.
3. NO hashtags, emojis, or bold text.
4. NO over-explaining.
5. AVOID PHRASES: "in moments of", "true strength", "let your heart", "embrace the journey", "may we always", "find your way", "connection to", "remember that", "source of".
6. Preserve the supplied source wording exactly. Never rewrite scripture or its translation.

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
from app.config import settings
from app.db import SessionLocal
from app.models import ContentItem
from app.services.library_service import generate_topics_slugs
from app.services.quran_service import search_quran, get_quran_ayahs_by_theme, get_verse_by_reference
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
        # 1. Try direct reference matching (e.g. "70:5", "Surah 70:5")
        item = get_verse_by_reference(db, topic)
        if item:
            print(f"🎯 [CaptionEngine] Direct reference match found for '{topic}': {item.title}")
            return {
                "item": item,
                "text": item.text,
                "arabic": item.arabic_text,
                "reference": item.title
            }

        # 2. Search existing themes in local DB
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
# Caption Generator
# -------------------------------
def generate_islamic_caption(intention, topic, tone="calm"):
    print(f"👉 Phase 3 Generating caption for: {topic} (Tone: {tone})")

    # 2. Fetch Verse (Unified Local Foundation Search)
    verse = fetch_quran_verse(topic)
    
    if verse and "item" in verse:
        # HIGH-FIDELITY GROUNDED GENERATION
        # We delegate to the new caption service for unified quality
        print(f"🔗 [CaptionEngine] Delegating grounded generation for '{topic}' to Quran Service.")
        return generate_ai_caption_from_quran(verse["item"], style=tone)

    raise ValueError("No verified source was found. Select a source from the library before generating a caption.")
