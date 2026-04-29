import sys
import os
from unittest.mock import MagicMock, patch

# Ensure app context is available
sys.path.append(os.getcwd())

from app.models import TopicAutomation, IGAccount, Org, Post, ContentItem
from app.services.automation_runner import run_automation_once
from app.config import settings

# --- REVIEW SAMPLE SET ---
REVIEW_SET = [
    {
        "id": "1",
        "name": "SHORT (INTENTIONS)",
        "text": "The reward of deeds depends upon the intentions.",
        "arabic": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
        "reference": "Sahih al-Bukhari 1",
        "narrator": "Narrated 'Umar bin Al-Khattab:"
    },
    {
        "id": "2",
        "name": "MEDIUM (KNOWLEDGE)",
        "text": "He who travels a path in search of knowledge, Allah will make easy for him the path to Paradise.",
        "arabic": "مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ",
        "reference": "Sahih Muslim 2699",
        "narrator": "Abu Huraira reported:"
    },
    {
        "id": "3",
        "name": "LONG (WORLDLY LIFE)",
        "text": "I was with the Prophet (peace be upon him) and he took hold of my shoulder and said: 'Be in this world as if you were a stranger or a traveler. Count yourself among the inhabitants of the grave.' Ibn Umar used to say: 'In the evening do not expect to live until the morning, and in the morning do not expect to live until the evening.'",
        "arabic": "كُنْتُ مَعَ النَّبِيِّ صلى الله عليه وسلم فَأَخَذَ بِمَنْكِبِي فَقَالَ: كُنْ فِي الدُّنْيَا كَأَنَّكَ غَرِيبٌ أَوْ عَابِرُ سَبِيلٍ",
        "reference": "Sahih al-Bukhari 6416",
        "narrator": "Narrated Mujahid:"
    },
    {
        "id": "4",
        "name": "SHORT (BROTHERHOOD)",
        "text": "None of you [truly] believes until he loves for his brother what he loves for himself.",
        "arabic": "لاَ يُؤْمِنُ أَحَدُكُمْ حَتَّى يُحِبَّ لأَخِيهِ مَا يُحِبُّ لِنَفْسِهِ",
        "reference": "Sahih al-Bukhari 13",
        "narrator": "Anas reported:"
    },
    {
        "id": "5",
        "name": "MEDIUM (KINDNESS)",
        "text": "Allah is Kind and He loves kindness, and He rewards for kindness what He does not reward for harshness and what He does not reward for anything else.",
        "arabic": "إِنَّ اللَّهَ رَفِيقٌ يُحِبُّ الرِّفْقَ وَيُعْطِي عَلَى الرِّفْقِ مَا لاَ يُعْطِي عَلَى الْعُنْفِ وَمَا لاَ يُعْطِي عَلَى مَا سِوَاهُ",
        "reference": "Sahih Muslim 2594",
        "narrator": "Aisha reported:"
    }
]

class ReviewAutomation:
    def __init__(self, index):
        self.id = 1000 + index
        self.org_id = 1
        self.ig_account_id = 1
        self.name = f"HADITH_REVIEW_AUTO_{index}"
        self.enabled = True
        self.topic_pool = ["wisdom", "guidance", "prophetic_advice"]
        self.topic_prompt = "prophetic advice"
        self.content_provider_scope = "system_library"
        self.image_mode = "quote_card"
        self.style_preset = ["islamic_reminder", "nature_reflection", "parchment_hadith"][index % 3]
        self.approval_mode = "needs_manual_approve"
        self.posting_mode = "scheduled"
        self.tone = "calm"
        self.pillars = []
        self.language = "english"
        self.banned_phrases = []
        self.last_error = None
        self.timezone = "UTC"
        self.post_time_local = "09:00"
        self.content_profile_id = None
        self.hashtag_set = ["#Hadith", "#Wisdom"]
        self.creativity_level = 3
        self.media_asset_id = None
        self.media_tag_query = []
        self.automation_version = 2
        self.style_dna_id = None
        self.style_dna_pool = []

class ReviewContentItem:
    def __init__(self, id_val):
        self.id = int(id_val)
        self.use_count = 0
        self.last_used_at = None

def run_pilot_review():
    print("\n" + "="*70)
    print("🚀 [HADITH_REVIEW] STARTING PILOT REVIEW GENERATION")
    print("="*70)
    
    db = MagicMock()
    results = []

    for i, case in enumerate(REVIEW_SET):
        automation = ReviewAutomation(i)
        
        from app.services.content_providers import UnifiedContent
        mock_content = UnifiedContent(
            type="hadith",
            text=case["text"],
            arabic_text=case["arabic"],
            source="Hadith Library",
            reference=case["reference"],
            topic_tags=["wisdom"],
            verified=True,
            provider="system_library",
            original_id=case["id"],
            meta={"narrator": case["narrator"]}
        )
        
        db_item = ReviewContentItem(case["id"])

        with patch("app.services.content_providers.SystemLibraryProvider.get_content", return_value=[mock_content]), \
             patch("app.services.automation_runner.get_lock_for_automation", return_value=MagicMock(acquire=lambda **k: True)), \
             patch("app.services.automation_runner.generate_topic_variations", return_value=["reminder"]), \
             patch("app.services.automation_runner.validate_source_relevance", return_value={"accepted": True, "reason": "review_match"}), \
             patch("app.services.automation_runner.render_minimal_quote_card", wraps=lambda **k: f"https://app.sabeelstudio.com/uploads/review_{case['id']}.jpg") as mock_render, \
             patch("app.services.automation_runner.compute_next_run_time", return_value=None):
            
            db.query.side_effect = lambda model: MagicMock(filter=lambda *a, **k: MagicMock(first=lambda: automation if model == TopicAutomation else (db_item if model == ContentItem else None), count=lambda: 0))
            db.get.side_effect = lambda model, id_val: db_item if model == ContentItem else MagicMock(id=1, timezone="UTC", daily_post_time="09:00")
            
            try:
                post = run_automation_once(db, automation.id)
                if post:
                    print(f"\n✅ GENERATED: {case['name']}")
                    print(f"Ref: {case['reference']}")
                    print(f"Caption Start: {post.caption[:80]}...")
                    
                    # Log Visual Segments for analysis
                    args, kwargs = mock_render.call_args
                    segments = kwargs.get('segments', [])
                    print(f"Visual Segments: {len(segments)}")
                    for s in segments:
                        print(f"  - [{s.get('size')}] {str(s.get('text'))[:40]}...")
                    
                    results.append({"case": case, "post": post, "segments": segments})
                else:
                    print(f"❌ FAILED: {case['name']}")
            except Exception as e:
                print(f"💥 CRASH: {case['name']} - {e}")

    print("\n" + "="*70)
    print("REVIEW DATA COLLECTED")
    print("="*70 + "\n")

if __name__ == "__main__":
    run_pilot_review()
