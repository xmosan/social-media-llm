import sys
import os
from unittest.mock import MagicMock, patch

# Ensure app context is available
sys.path.append(os.getcwd())

from app.models import TopicAutomation, IGAccount, Org, Post, ContentItem
from app.services.automation_runner import run_automation_once
from app.config import settings

# --- INTERNAL TEST CONFIG ---
TEST_HADITH = {
    "id": "1",
    "text": "The reward of deeds depends upon the intentions.",
    "arabic_text": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
    "reference": "Sahih al-Bukhari 1",
    "narrator": "Narrated 'Umar bin Al-Khattab:"
}

class SimpleAutomation:
    def __init__(self):
        self.id = 777
        self.org_id = 999
        self.ig_account_id = 999
        self.name = "INTERNAL_HADITH_TEST"
        self.enabled = True
        self.topic_pool = ["intentions"]
        self.topic_prompt = "intentions"
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

class SimpleContentItem:
    def __init__(self):
        self.id = 1
        self.use_count = 0

def run_internal_verification():
    print("\n" + "="*60)
    print("🚀 [HADITH_AUTOMATION] INTERNAL TEST RUN STARTED")
    print("="*60)
    
    if not settings.hadith_in_automations_enabled:
        print("❌ [HADITH_AUTOMATION][FAIL] Feature flag not enabled!")
        return
    
    print("✅ [HADITH_AUTOMATION] feature flag enabled")

    db = MagicMock()
    automation = SimpleAutomation()
    ig_acc = MagicMock(spec=IGAccount)
    ig_acc.id = 999
    ig_acc.timezone = "UTC"
    ig_acc.daily_post_time = "09:00"
    
    db_item = SimpleContentItem()

    from app.services.content_providers import UnifiedContent
    mock_content = UnifiedContent(
        type="hadith",
        text=TEST_HADITH["text"],
        arabic_text=TEST_HADITH["arabic_text"],
        source="Sahih al-Bukhari",
        reference=TEST_HADITH["reference"],
        topic_tags=["intentions"],
        verified=True,
        provider="system_library",
        original_id=TEST_HADITH["id"],
        meta={"narrator": TEST_HADITH["narrator"]}
    )

    with patch("app.services.content_providers.SystemLibraryProvider.get_content", return_value=[mock_content]), \
         patch("app.services.automation_runner.get_lock_for_automation", return_value=MagicMock(acquire=lambda **k: True)), \
         patch("app.services.automation_runner.generate_topic_variations", return_value=["deeds and intentions"]), \
         patch("app.services.automation_runner.validate_source_relevance", return_value={"accepted": True, "reason": "exact_match"}), \
         patch("app.services.automation_runner.render_minimal_quote_card", wraps=lambda **k: f"https://app.sabeelstudio.com/uploads/internal_test.jpg") as mock_render, \
         patch("app.services.automation_runner.compute_next_run_time", return_value=None):
        
        # Fixed Query Mock
        def db_query_handler(model):
            mock_q = MagicMock()
            if model == TopicAutomation:
                mock_q.filter.return_value.first.return_value = automation
            elif model == Post:
                mock_q.filter.return_value.count.return_value = 0
            elif model == ContentItem:
                mock_q.filter.return_value.first.return_value = db_item
            return mock_q
            
        db.query.side_effect = db_query_handler
        db.get.return_value = ig_acc
        
        print(f"📡 [HADITH_AUTOMATION] trigger runner for automation {automation.id}")
        post = run_automation_once(db, automation.id)
        
        if not post:
            print(f"❌ [HADITH_AUTOMATION][FAIL] Post generation failed. Error: {automation.last_error}")
            return

        print("✅ [HADITH_AUTOMATION] post created")
        
        # Validation Gates
        if post.status != "drafted":
            print(f"❌ [HADITH_AUTOMATION][FAIL] status mismatch: {post.status}")
            return
        print("✅ [HADITH_AUTOMATION] draft created")

        recipe = post.source_metadata.get("recovery_recipe", {})
        if recipe.get("reference") != TEST_HADITH["reference"]:
            print(f"❌ [HADITH_AUTOMATION][FAIL] reference mismatch")
            return
        
        if f'"{TEST_HADITH["reference"]}"' not in post.caption:
            print(f"❌ [HADITH_AUTOMATION][FAIL] caption citation missing")
            return

        print("\n" + "="*60)
        print("✨ [HADITH_AUTOMATION] INTERNAL VERIFICATION SUCCESSFUL")
        print(f"Reference: {TEST_HADITH['reference']}")
        print(f"Draft URL: {post.media_url}")
        print("="*60 + "\n")

if __name__ == "__main__":
    run_internal_verification()
