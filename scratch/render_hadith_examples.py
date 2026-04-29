import sys
import os

# Ensure the app context is available
sys.path.append(os.getcwd())

from app.services.quote_message_service import build_hadith_quote_message
from app.services.image_card import generate_quote_card

# Test Data
examples = [
    {
        "name": "short_minimalist",
        "style": "islamic_minimalist",
        "data": {
            "reference": "Sahih al-Bukhari 1",
            "collection": "bukhari",
            "arabic_text": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
            "translation_text": "The reward of deeds depends upon the intentions.",
            "narrator": "Narrated 'Umar bin Al-Khattab:"
        }
    },
    {
        "name": "medium_kaaba",
        "style": "kaaba",
        "data": {
            "reference": "Sahih Muslim 2699",
            "collection": "muslim",
            "arabic_text": "مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ",
            "translation_text": "He who travels a path in search of knowledge, Allah will make easy for him the path to Paradise.",
            "narrator": "Abu Huraira reported:"
        }
    },
    {
        "name": "long_scholar",
        "style": "scholar",
        "data": {
            "reference": "Sahih al-Bukhari 6416",
            "collection": "bukhari",
            "arabic_text": "كُنْتُ مَعَ النَّبِيِّ صلى الله عليه وسلم فَأَخَذَ بِمَنْكِبِي فَقَالَ: كُنْ فِي الدُّنْيَا كَأَنَّكَ غَرِيبٌ أَوْ عَابِرُ سَبِيلٍ",
            "translation_text": "Be in this world as if you were a stranger or a traveler.",
            "narrator": "Narrated Mujahid:",
            "was_excerpted": True
        }
    }
]

def render_examples():
    results = []
    for ex in examples:
        print(f"Rendering {ex['name']} with style {ex['style']}...")
        message = build_hadith_quote_message(ex['data'], tone="calm", intent="wisdom")
        result_path = generate_quote_card(card_message=message, style=ex['style'])
        if os.path.exists(result_path):
            # The result_path is absolute, but generate_quote_card might return a URL-like string in some modes.
            # In local mode, it returns the local file path.
            print(f"Saved: {result_path}")
            results.append({"name": ex['name'], "path": result_path})
        else:
            # Handle the case where it returns a URL or something else
            print(f"Result (possibly URL): {result_path}")
            results.append({"name": ex['name'], "path": result_path})
    return results

if __name__ == "__main__":
    render_examples()
