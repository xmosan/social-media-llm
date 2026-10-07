"""Restart-safe source/topic history and fail-closed visual generation."""
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

from test_security import DatabaseCase
from test_source_integrity import load_isolated_service
from app.models import ContentItem, ContentUsage, ContentSource, Post, Org, IGAccount
from app.services import rotation_engine, post_service, publisher
from app.services.visual_system import compose_scene_prompt, SCENE_PROMPT_TEMPLATES


class RotationChecks(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (ContentSource, ContentItem, ContentUsage, Post, IGAccount):
            model.__table__.create(self.engine)
        self.db.add(Org(id=1, name="Fixture"))
        self.db.add(IGAccount(id=1, org_id=1, name="Fixture", active=True, ig_user_id="123", access_token="fake"))
        self.db.add(ContentSource(id=1, name="Fixture", source_type="quran_foundation"))
        for id_, verse in ((1, 3), (2, 3), (3, 4)):
            self.db.add(ContentItem(id=id_, source_id=1, item_type="quran", text="Synthetic source fixture", arabic_text="نص اختباري", meta={"surah_number": 2, "verse_number": verse}))
        self.db.commit()

    def test_source_identity_survives_translation_rows_and_session_reload(self):
        self.db.add(ContentUsage(org_id=1, ig_account_id=1, automation_id=1, content_item_id=1, used_at=datetime.now(timezone.utc)))
        self.db.commit()
        self.db.expire_all()
        ranked = rotation_engine.rank_source_items(self.db.query(ContentItem).all(), self.db, 1)
        self.assertEqual(ranked[0].id, 3)
        self.assertEqual(rotation_engine.source_identity(ranked[1]), rotation_engine.source_identity(ranked[2]))

    def test_exhausted_source_pool_uses_least_recent_and_logs(self):
        now = datetime.now(timezone.utc)
        for id_, days in ((1, 1), (3, 3)):
            self.db.add(ContentUsage(org_id=1, ig_account_id=1, automation_id=1, content_item_id=id_, used_at=now - timedelta(days=days)))
        self.db.commit()
        with self.assertLogs(rotation_engine.logger, level="INFO") as messages:
            ranked = rotation_engine.rank_source_items(self.db.query(ContentItem).all(), self.db, 1)
        self.assertEqual(ranked[0].id, 3)
        self.assertIn("exhausted", " ".join(messages.output))

    def test_topic_matching_ignores_case_and_whitespace(self):
        self.db.add(Post(org_id=1, ig_account_id=1, automation_id=1, flags={"rotation_topic": " Wisdom ", "rotation_used_at": datetime.now(timezone.utc).isoformat()}))
        self.db.commit()
        self.assertEqual(rotation_engine.pick_topic(["wisdom", "patience"], 1, self.db), "patience")

    def test_exact_duplicate_is_blocked_on_manual_publish_and_fixed_media_is_allowed(self):
        prior = Post(org_id=1, ig_account_id=1, automation_id=1, caption="Caption fixture", card_message={"supporting_text": "Reflection fixture"}, media_url="https://res.cloudinary.com/test/image/upload/first.jpg", source_metadata={"visual_generation": {"background_sha256": "same"}})
        post = Post(org_id=1, ig_account_id=1, automation_id=1, status="drafted", visual_mode="quote_card", caption="caption  fixture", card_message={"supporting_text": "reflection fixture"}, media_url="https://res.cloudinary.com/test/image/upload/second.jpg", source_metadata={"visual_generation": {"background_sha256": "same"}})
        self.db.add_all([prior, post])
        self.db.commit()
        self.assertEqual(rotation_engine.repetition_issues(self.db, post), ["duplicate_caption", "duplicate_reflection", "duplicate_visual"])
        with patch.object(publisher, "publish_to_instagram") as send:
            self.assertEqual(post_service.publish_post(self.db, post.id, 1).status_code, 422)
            send.assert_not_called()
        post.caption = "Corrected copy"
        post.card_message = {"supporting_text": "New reflection"}
        post.visual_mode = "library_fixed"
        self.assertEqual(rotation_engine.repetition_issues(self.db, post), [])

    def test_old_history_and_other_automations_do_not_block_copy(self):
        post = Post(org_id=1, ig_account_id=1, automation_id=1, caption="Fixture")
        self.db.add_all([Post(org_id=1, ig_account_id=1, automation_id=1, caption="Fixture", created_at=datetime.now(timezone.utc) - timedelta(days=31)),
                         Post(org_id=1, ig_account_id=1, automation_id=2, caption="Fixture"), post])
        self.db.commit()
        self.assertEqual(rotation_engine.repetition_issues(self.db, post), [])


class VisualFailureChecks(unittest.TestCase):
    def test_scene_variations_use_saved_history_then_least_recent(self):
        history = {}
        first = None
        for index in range(len(SCENE_PROMPT_TEMPLATES["sacred_black"]["variations"])):
            metadata = {}
            prompt = compose_scene_prompt("sacred_black", history=history, metadata=metadata)
            self.assertFalse(metadata["variation_exhausted"])
            self.assertNotIn(metadata["prompt_signature"], history)
            if index == 0:
                first = prompt
            history[metadata["prompt_signature"]] = f"2030-01-{index+1:02d}"
        metadata = {}
        self.assertEqual(compose_scene_prompt("sacred_black", history=history, metadata=metadata), first)
        self.assertTrue(metadata["variation_exhausted"])

    def test_requested_ai_visual_failure_does_not_render_a_fallback(self):
        renderer = load_isolated_service("image_renderer")
        with tempfile.TemporaryDirectory() as output, patch.object(renderer, "_VS_OK", True), patch.object(renderer, "generate_background", return_value=None):
            for mode in ("scene", "custom"):
                with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "Sabeel Vision"):
                    renderer.render_minimal_quote_card([{"text": "Synthetic test card", "size": 48}], output, style="sacred_black", mode=mode, visual_prompt="Test scene")
            self.assertEqual(list(__import__("pathlib").Path(output).iterdir()), [])
