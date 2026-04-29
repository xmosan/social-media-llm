import sys
import os
from unittest.mock import MagicMock, patch

# Ensure app context is available
sys.path.append(os.getcwd())

from app.models import TopicAutomation, ContentItem, IGAccount, Org, Post
from app.services.automation_runner import run_automation_once
from app.config import settings

# --- TEST DATA ---
test_cases = [
    {
        "id": 101,
        "name": "SHORT HADITH",
        "text": "The reward of deeds depends upon the intentions.",
        "reference": "Sahih al-Bukhari 1",
        "arabic": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
        "narrator": "Narrated 'Umar bin Al-Khattab:"
    }
]

def run_qa():
    print("🚀 Initializing Robust Mocked E2E Hadith Automation QA Pass...")
    settings.hadith_in_automations_enabled = True
    
    for case in test_cases:
        print(f"\nTESTING: {case['name']}")
        
        db = MagicMock()
        
        # Mock automation and its relations
        automation = MagicMock(spec=TopicAutomation)
        automation.id = 500
        automation.org_id = 1
        automation.ig_account_id = 1
        automation.enabled = True
        automation.topic_pool = ["qa_test"]
        automation.topic_prompt = "qa_test"
        automation.content_provider_scope = "user_library"
        automation.image_mode = "quote_card"
        automation.style_preset = "islamic_minimalist"
        automation.approval_mode = "needs_manual_approve"
        automation.tone = "calm"
        automation.pillars = []
        automation.language = "english"
        automation.banned_phrases = []
        automation.last_error = None
        automation.timezone = "UTC"
        automation.post_time_local = "09:00"

        ig_acc = MagicMock(spec=IGAccount)
        ig_acc.id = 1
        ig_acc.timezone = "UTC"
        ig_acc.daily_post_time = "09:00"

        from app.services.content_providers import UnifiedContent
        mock_content = UnifiedContent(
            type="hadith",
            text=case["text"],
            arabic_text=case["arabic"],
            source="Test Source",
            reference=case["reference"],
            topic_tags=["qa_test"],
            verified=True,
            provider="user_library",
            original_id=str(case["id"])
        )

        # Build query chain mocks
        # db.query(TopicAutomation).filter(...).first()
        db.query.return_value.filter.return_value.first.return_value = automation
        
        # db.query(Post).filter(...).count()
        # Ensure count() returns 0 for the first run
        query_mock = MagicMock()
        query_mock.filter.return_value.count.return_value = 0
        db.query.side_effect = lambda model: query_mock if model == Post else MagicMock(filter=lambda *a, **k: MagicMock(first=lambda: automation))

        db.get.return_value = ig_acc

        with patch("app.services.content_providers.UserLibraryProvider.get_content", return_value=[mock_content]), \
             patch("app.services.automation_runner.get_lock_for_automation", return_value=MagicMock(acquire=lambda **k: True)), \
             patch("app.services.automation_runner.generate_topic_variations", return_value=["test_had_var"]), \
             patch("app.services.automation_runner.validate_source_relevance", return_value={"accepted": True, "reason": "match"}), \
             patch("app.services.automation_runner.render_minimal_quote_card", return_value="https://app.sabeelstudio.com/uploads/mock.jpg"), \
             patch("app.services.automation_runner.compute_next_run_time", return_value=None):
            
            try:
                post = run_automation_once(db, automation.id)
                if post:
                    print(f"✅ SUCCESS: {case['name']}")
                    print(f"Caption: {post.caption[:100]}...")
                else:
                    print(f"❌ FAILED: {case['name']} - No post returned")
            except Exception as e:
                print(f"💥 ERROR: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    run_qa()
