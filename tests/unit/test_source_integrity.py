"""Synthetic fixture text only: no scripture supplied from model memory."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_security import DatabaseCase
from test_ownership import sqlite_fixture_jsonb
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import settings
from app.db import get_db
from app.models import ContentItem, ContentSource, IGAccount, Org, Post, User
from app.routes import studio, posts
from app.security.auth import get_current_user
from app.security.rbac import get_current_org_id
from app.services import source_caption, quran_caption_service, hadith_caption_service, quote_message_service, automation_runner
from app.services.quran_serialization import normalize_quran_verse
from app.services.source_grounding import resolve_selected_source

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = {"id": 1, "reference": "Qur'an 2:3", "arabic_text": "نص اختباري غير قرآني",
           "translation_text": "Synthetic fixture [clarification];1 with annotation (2). 3"}


def load_isolated_service(name):
    spec = importlib.util.spec_from_file_location("isolated_" + name, ROOT / "app/services" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CaptionIntegrityTests(unittest.TestCase):
    def test_quran_ai_output_cannot_replace_source_fields(self):
        result = {"reference": "Wrong reference", "translation_text": "Rewritten fixture", "arabic_text": "wrong",
                  "reflection": "A separate test reflection."}
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))])
        with patch.object(settings, "openai_api_key", "fake-key"), patch.object(source_caption, "generate_text", return_value=result):
            caption = quran_caption_service.generate_ai_caption_from_quran(FIXTURE)
        self.assertTrue(caption.startswith("\n\n".join(FIXTURE[k] for k in ("reference", "arabic_text", "translation_text"))))
        self.assertIn("Reflection: A separate test reflection.", caption)
        self.assertNotIn("Rewritten fixture", caption)
        self.assertNotIn("Wrong reference", caption)

    def test_missing_provider_or_provider_failure_keeps_only_exact_source(self):
        expected = "\n\n".join(FIXTURE[k] for k in ("reference", "arabic_text", "translation_text"))
        with patch.object(settings, "openai_api_key", None):
            self.assertEqual(quran_caption_service.generate_ai_caption_from_quran(FIXTURE), expected)
        with patch.object(settings, "openai_api_key", "fake-key"), patch.object(source_caption, "generate_text", side_effect=source_caption.TextGenerationError("provider_error")):
            self.assertEqual(quran_caption_service.generate_ai_caption_from_quran(FIXTURE), expected)

    def test_missing_source_data_fails_instead_of_substituting_scripture(self):
        for field in ("reference", "translation_text"):
            payload = {**FIXTURE, field: None}
            with self.assertRaises(ValueError):
                quran_caption_service.generate_ai_caption_from_quran(payload)
            with self.assertRaises(ValueError):
                hadith_caption_service.generate_hadith_caption(payload)

    def test_hadith_caption_keeps_full_source_and_actual_narrator(self):
        payload = {**FIXTURE, "reference": "Synthetic Hadith reference", "translation_text": "Fixture text. " * 100,
                   "narrator": "Returned fixture narrator", "grade": None}
        with patch.object(settings, "openai_api_key", None):
            caption = hadith_caption_service.generate_hadith_caption(payload)
        self.assertIn(payload["translation_text"], caption)
        self.assertIn("Narrator: Returned fixture narrator", caption)
        self.assertNotIn("Reflection:", caption)

    def test_quote_card_locks_reference_and_does_not_attribute_ai_to_narrator(self):
        with patch("app.services.llm.generate_card_framing_from_source", return_value={"eyebrow": "Model theme", "supporting_text": "Test reflection"}):
            card = quote_message_service.build_quran_quote_message(FIXTURE, "calm", "wisdom")
            hadith = quote_message_service.build_hadith_quote_message({**FIXTURE, "narrator": "Actual narrator", "grade": None}, "calm", "wisdom")
        self.assertEqual(card["eyebrow"], FIXTURE["reference"])
        self.assertEqual(card["headline"], FIXTURE["translation_text"])
        self.assertEqual(hadith["supporting_text"], "Test reflection")
        self.assertEqual(hadith["hadith_narrator"], "Actual narrator")
        self.assertIsNone(hadith["hadith_grade"])

    def test_normalization_preserves_arabic_and_does_not_invent_translator(self):
        item = {"title": "Surah 2, Verse 3", "arabic_text": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ " + FIXTURE["arabic_text"],
                "text": FIXTURE["translation_text"]}
        normalized = normalize_quran_verse(item)
        self.assertEqual(normalized["arabic_text"], item["arabic_text"])
        self.assertEqual(normalized["translation_text"], item["text"])
        self.assertIsNone(normalized["translator"])
        for invalid in ({"text": "Fixture"}, {"title": "Surah 999, Verse 1", "text": "Fixture"}, {"title": "Surah 2, Verse 3"}):
            with self.assertRaises(ValueError):
                normalize_quran_verse(invalid)

    def test_automation_cleaning_preserves_brackets_and_numbers(self):
        self.assertEqual(automation_runner.clean_translation_for_card(FIXTURE["translation_text"]), FIXTURE["translation_text"])

    def test_topic_search_cannot_fall_back_to_a_different_verse(self):
        engine = load_isolated_service("caption_engine")
        with patch.object(engine, "fetch_quran_verse", return_value=None), self.assertRaises(ValueError):
            engine.generate_islamic_caption("wisdom", "No matching fixture")

    def test_hadith_missing_credentials_do_not_switch_provider(self):
        service = load_isolated_service("hadith_service")
        with patch.object(settings, "hadith_api_key", None), patch.object(service, "_get_json") as request:
            self.assertEqual(service._active_provider(), "sunnah_now")
            with self.assertRaises(ValueError):
                service.get_hadith_by_reference("bukhari", 1)
            with self.assertRaises(ValueError):
                service.search_hadith("test")
            request.assert_not_called()


class SourceRouteTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount, ContentSource, ContentItem, Post):
            model.__table__.create(self.engine)
        self.db.add(Org(id=1, name="Fixture"))
        self.db.add(User(id=1, email="test@example.test", is_active=True, active_org_id=1))
        self.db.add(IGAccount(id=1, org_id=1, name="Fixture", ig_user_id="fixture", access_token="fake-token", active=True))
        self.db.add(ContentSource(id=1, org_id=None, name="Fixture", source_type="quran_foundation"))
        self.db.add(ContentItem(id=1, org_id=None, source_id=1, item_type="quran", title="Surah 2, Verse 3",
                                text=FIXTURE["translation_text"], arabic_text=FIXTURE["arabic_text"], meta={"surah_number": 2, "verse_number": 3}))
        self.db.commit()
        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)
        app.dependency_overrides[get_current_org_id] = lambda: 1
        app.include_router(studio.router)
        app.include_router(posts.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_modified_source_and_conflicting_reference_rejected_before_ai(self):
        with patch.object(studio, "build_quote_card_message") as build:
            for changes in ({"translation_text": "Changed fixture"}, {"reference": "Qur'an 2:4"}, {"id": 999}):
                result = self.client.post("/api/studio/generate-card-message", json={"source_type": "quran", "source_payload": {**FIXTURE, **changes}})
                self.assertIn(result.status_code, (403, 422))
            build.assert_not_called()

    def test_source_card_caption_save_and_reopen_preserve_same_record(self):
        with patch("app.services.llm.generate_card_framing_from_source", return_value={"supporting_text": "Test reflection"}), patch.object(settings, "openai_api_key", None):
            result = self.client.post("/api/studio/generate-card-message", json={"source_type": "quran", "source_payload": FIXTURE})
            self.assertEqual(result.status_code, 200, result.text)
            card = result.json()["card_message"]
            caption = self.client.post("/api/studio/generate-caption", json={"source_type": "quran", "source_payload": FIXTURE})
            self.assertEqual(caption.status_code, 200, caption.text)
            saved = self.client.post("/api/studio/create-post", json={"ig_account_id": 1, "source_type": "quran", "source_metadata": FIXTURE,
                "source_reference": FIXTURE["reference"], "card_message": card, "caption": caption.json()["caption"],
                "visual_design": {"family": "quiet_photography", "layout": "bilingual", "background_token": "signed-fixture"}})
            self.assertEqual(saved.status_code, 200, saved.text)
        reopened = self.client.get(f'/api/studio/post/{saved.json()["id"]}').json()
        self.assertEqual(reopened["source_text"], FIXTURE["translation_text"])
        self.assertEqual(reopened["card_message"]["headline"], FIXTURE["translation_text"])
        self.assertEqual(reopened["source_metadata"]["id"], 1)
        self.assertIn(FIXTURE["translation_text"], reopened["caption"])
        self.assertEqual(reopened["flags"]["visual_design"], {"family": "quiet_photography", "layout": "bilingual", "background_token": "signed-fixture"})

    def test_modified_card_cannot_be_saved_as_canonical_scripture(self):
        result = self.client.post("/api/studio/create-post", json={"ig_account_id": 1, "source_type": "quran", "source_metadata": FIXTURE,
            "card_message": {"headline": "Changed fixture", "eyebrow": FIXTURE["reference"]}})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.db.query(Post).count(), 0)

    def test_hadith_is_resolved_from_exact_provider_identity_and_metadata(self):
        payload = {"collection_key": "bukhari", "hadith_number": 7, "reference": "Synthetic reference"}
        canonical = {**payload, "translation_text": "Returned fixture", "arabic_text": None, "narrator": None, "grade": None}
        with patch("app.services.hadith_service.get_hadith_by_reference", return_value=canonical) as provider:
            self.assertEqual(resolve_selected_source(self.db, 1, "hadith", payload), canonical)
            provider.assert_called_once_with("bukhari", 7)
            with self.assertRaises(ValueError):
                resolve_selected_source(self.db, 1, "hadith", {**payload, "grade": "fabricated"})
        with patch("app.services.hadith_service.get_hadith_by_reference", return_value=None), self.assertRaises(ValueError):
            resolve_selected_source(self.db, 1, "hadith", payload)

    def save_fixture(self):
        response = self.client.post("/api/studio/create-post", json={"ig_account_id": 1, "source_type": "quran", "source_metadata": FIXTURE,
            "caption": "Saved social copy", "card_message": {"headline": FIXTURE["translation_text"], "eyebrow": FIXTURE["reference"], "arabic_text": FIXTURE["arabic_text"]}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_saved_source_fields_cannot_drift_but_social_copy_can_change(self):
        id_ = self.save_fixture()
        for changes in ({"source_text": "Changed"}, {"source_reference": "Qur'an 2:4"}, {"source_foundation": None},
                        {"card_message": {"headline": "Rewritten fixture"}}, {"library_item_id": 2}):
            self.assertEqual(self.client.patch(f"/posts/{id_}", json=changes).status_code, 422)
        changed = self.client.patch(f"/posts/{id_}", json={"caption": "Updated social copy"})
        self.assertEqual(changed.status_code, 200, changed.text)
        reopened = self.client.get(f"/api/studio/post/{id_}").json()
        self.assertEqual(reopened["caption"], "Updated social copy")
        self.assertEqual(reopened["caption_message"], {"caption": "Updated social copy"})
        self.assertEqual(reopened["source_text"], FIXTURE["translation_text"])

    def test_refine_and_regenerate_keep_exact_source_out_of_generic_writer(self):
        id_ = self.save_fixture()
        with patch.object(settings, "openai_api_key", None), patch.object(posts, "generate_draft") as generic:
            refined = self.client.post(f"/posts/{id_}/refine", json={"style": "shorter", "current_caption": "Invented source"})
            generated = self.client.post(f"/posts/{id_}/generate")
            regenerated = self.client.post(f"/posts/{id_}/regenerate-caption")
            for response in (refined, generated, regenerated):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn(FIXTURE["translation_text"], response.json()["caption"])
                self.assertNotIn("Invented source", response.json()["caption"])
            generic.assert_not_called()

    def test_malformed_card_and_unverified_legacy_intake_fail_before_media(self):
        self.assertEqual(self.client.post("/api/studio/create-post", json={"ig_account_id": 1, "source_type": "quran", "source_metadata": FIXTURE, "card_message": ["bad"]}).status_code, 422)
        with patch.object(posts, "generate_ai_image") as image:
            response = self.client.post("/posts/intake", data={"ig_account_id": 1, "source_type": "quran", "source_text": "Unverified", "use_ai_image": "true"})
            self.assertEqual(response.status_code, 422, response.text)
            image.assert_not_called()

    def test_automation_uses_one_source_shared_card_and_persistent_rotation(self):
        from app.models import TopicAutomation, ContentUsage
        from app.services import content_providers, rotation_engine
        for model in (TopicAutomation, ContentUsage):
            model.__table__.create(self.engine)
        self.db.get(ContentItem, 1).topics = ["wisdom"]
        auto = TopicAutomation(id=1, org_id=1, ig_account_id=1, name="Fixture", topic_prompt="wisdom", topic_pool=["wisdom", "patience"],
                               pillars=["reflection"], image_mode="quote_card", enabled=True, approval_mode="needs_manual_approve", content_provider_scope="system_library")
        self.db.add(auto)
        self.db.commit()
        service = load_isolated_service("automation_service")
        with patch.dict(sys.modules, {"app.services.automation_service": service}), patch.object(settings, "openai_api_key", None), \
             patch.object(rotation_engine, "pick_topic", return_value="wisdom"), \
             patch.object(automation_runner, "generate_topic_variations", return_value=["wisdom"]), \
             patch.object(automation_runner, "validate_source_relevance", return_value={"accepted": True, "reason": "Synthetic fixture"}), \
             patch.object(automation_runner, "resolve_media_url", return_value="https://example.test/background.jpg"), \
             patch("app.services.image_card.generate_quote_card", create=True, return_value="https://res.cloudinary.com/test/image/upload/fixture.jpg") as render, \
             patch("app.services.llm.generate_card_framing_from_source", return_value={"eyebrow": "Wrong model reference", "supporting_text": "Test reflection"}):
            saved = automation_runner.run_automation_once(self.db, 1)
        self.assertIsNotNone(saved, auto.last_error)
        self.assertEqual(saved.status, "drafted")
        self.assertEqual(saved.source_reference, FIXTURE["reference"])
        self.assertEqual(saved.card_message["headline"], FIXTURE["translation_text"])
        self.assertEqual(saved.card_message["eyebrow"], FIXTURE["reference"])
        self.assertEqual(saved.source_text, FIXTURE["translation_text"])
        self.assertIn(FIXTURE["translation_text"], saved.caption)
        self.assertEqual(saved.used_content_item_ids, ["1"])
        render.assert_called_once()
        self.db.expire_all()
        self.assertEqual(rotation_engine.latest_rotation(1, self.db)["rotation_pillar"], "reflection")
        self.assertEqual(rotation_engine.pick_topic(["wisdom", "patience"], 1, self.db), "patience")
