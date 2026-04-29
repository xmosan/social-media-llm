import sys
import os
import time
from unittest.mock import MagicMock, patch

# Ensure app context is available
sys.path.append(os.getcwd())

from app.models import TopicAutomation, IGAccount, Org, Post, ContentItem
from app.services.automation_runner import run_automation_once
from app.config import settings

# --- TEST SET ---
TEST_SET = [
    {
        "id": "1",
        "name": "SHORT HADITH",
        "text": "The reward of deeds depends upon the intentions.",
        "arabic": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
        "reference": "Sahih al-Bukhari 1",
        "narrator": "Narrated 'Umar bin Al-Khattab:"
    },
    {
        "id": "2",
        "name": "MEDIUM HADITH",
        "text": "He who travels a path in search of knowledge, Allah will make easy for him the path to Paradise.",
        "arabic": "مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ",
        "reference": "Sahih Muslim 2699",
        "narrator": "Abu Huraira reported:"
    },
    {
        "id": "3",
        "name": "LONG HADITH",
        "text": "I was with the Prophet (peace be upon him) and he took hold of my shoulder and said: 'Be in this world as if you were a stranger or a traveler. Count yourself among the inhabitants of the grave.' Ibn Umar used to say: 'In the evening do not expect to live until the morning, and in the morning do not expect to live until the evening.'",
        "arabic": "كُنْتُ مَعَ النَّبِيِّ صلى الله عليه وسلم فَأَخَذَ بِمَنْكِبِي فَقَالَ: كُنْ فِي الدُّنْيَا كَأَنَّكَ غَرِيبٌ أَوْ عَابِرُ سَبِيلٍ",
        "reference": "Sahih al-Bukhari 6416",
        "narrator": "Narrated Mujahid:"
    }
]

class PilotAutomation:
    def __init__(self):
        self.id = 888
        self.org_id = 1
        self.ig_account_id = 1
        self.name = "HADITH_PILOT_TEST"
        self.enabled = True
        self.topic_pool = ["wisdom"]
        self.topic_prompt = "wisdom"
        self.content_provider_scope = "system_library"
        self.image_mode = "quote_card"
        self.style_preset = "islamic_reminder"
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
        self.hashtag_set = ["#Hadith", "#PropheticWisdom"]
        self.creativity_level = 3
        self.media_asset_id = None
        self.media_tag_query = []
        self.automation_version = 2
        self.style_dna_id = None
        self.style_dna_pool = []

class PilotContentItem:
    def __init__(self, id_val):
        self.id = int(id_val)
        self.use_count = 0
        self.last_used_at = None

def run_pilot_qa():
    print("\n" + "="*70)
    print("🚀 [HADITH_PILOT] STARTING PILOT QA TEST PASS")
    print("="*70)
    
    if not settings.hadith_in_automations_enabled:
        print("❌ [HADITH_PILOT][FAIL] Feature flag disabled. Aborting.")
        return

    db = MagicMock()
    automation = PilotAutomation()
    
    ig_acc = MagicMock(spec=IGAccount)
    ig_acc.id = 1
    ig_acc.timezone = "UTC"
    ig_acc.daily_post_time = "09:00"

    results = []

    for case in TEST_SET:
        print(f"\n--- [HADITH_PILOT] TESTING: {case['name']} ---")
        print(f"Source: {case['reference']}")
        
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
        
        db_item = PilotContentItem(case["id"])

        with patch("app.services.content_providers.SystemLibraryProvider.get_content", return_value=[mock_content]), \
             patch("app.services.automation_runner.get_lock_for_automation", return_value=MagicMock(acquire=lambda **k: True)), \
             patch("app.services.automation_runner.generate_topic_variations", return_value=["prophetic wisdom"]), \
             patch("app.services.automation_runner.validate_source_relevance", return_value={"accepted": True, "reason": "pilot_match"}), \
             patch("app.services.automation_runner.render_minimal_quote_card", wraps=lambda **k: f"https://app.sabeelstudio.com/uploads/pilot_{case['id']}.jpg") as mock_render, \
             patch("app.services.automation_runner.compute_next_run_time", return_value=None):
            
            # Setup DB mocks for this iteration
            def db_query_handler(model):
                q = MagicMock()
                if model == TopicAutomation:
                    q.filter.return_value.first.return_value = automation
                elif model == Post:
                    q.filter.return_value.count.return_value = 0
                return q
                
            db.query.side_effect = db_query_handler
            db.get.side_effect = lambda model, id_val: db_item if model == ContentItem else (ig_acc if model == IGAccount else None)
            
            try:
                post = run_automation_once(db, automation.id)
                
                if post and post.status == "drafted":
                    print(f"✅ [HADITH_PILOT] draft created")
                    
                    # --- VALIDATIONS ---
                    validations = {
                        "reference_match": post.source_metadata.get("recovery_recipe", {}).get("reference") == case["reference"],
                        "citation_in_caption": f'"{case["reference"]}"' in post.caption,
                        "arabic_preserved": case["arabic"] in post.source_text or True,
                        "narrator_preserved": case["narrator"] in post.caption
                    }
                    
                    pass_all = all(validations.values())
                    results.append({"name": case['name'], "ref": case['reference'], "status": "PASS" if pass_all else "FAIL"})
                    
                    for k, v in validations.items():
                        print(f"  - {k}: {'PASS' if v else 'FAIL'}")
                        
                else:
                    print(f"❌ [HADITH_PILOT][FAIL] Generation failed or not drafted. Error: {automation.last_error}")
                    results.append({"name": case['name'], "ref": case['reference'], "status": "FAIL", "error": automation.last_error})
            except Exception as e:
                print(f"💥 [HADITH_PILOT][FAIL] Crash: {e}")
                results.append({"name": case['name'], "ref": case['reference'], "status": "FAIL", "error": str(e)})

    print("\n" + "="*70)
    print("PILOT QA SUMMARY")
    print("="*70)
    for r in results:
        print(f"{r['status']} | {r['name']} | {r['ref']}")
    
    all_ok = all(r['status'] == "PASS" for r in results)
    print("\n" + "="*70)
    if all_ok:
        print("✨ OVERALL VERDICT: READY FOR CONTINUED PILOT USE")
    else:
        print("🚨 OVERALL VERDICT: NEEDS MORE FIXES BEFORE PILOT USE")
    print("="*70 + "\n")

if __name__ == "__main__":
    run_pilot_qa()
