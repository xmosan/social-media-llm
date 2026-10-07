"""Real PostgreSQL transactions; every external provider is mocked."""

import importlib.util
import os
from pathlib import Path
import sys
import threading
import unittest
import ast
import gzip
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

if os.environ.get("SABEEL_ISOLATED_SECURITY_TESTS") != "1" or not os.environ.get("SABEEL_PG_TEST_SOCKET"):
    raise RuntimeError("Use tests/run_postgres_checks.py; never supply production credentials")

from sqlalchemy import text, inspect, create_engine
from sqlalchemy.orm import Session
from app.db import engine
from app.config import settings
from app.models import Base, Org, IGAccount, Post, TopicAutomation, ContentSource, ContentItem
from app.services import post_service, publisher, automation_runner

ROOT = Path(__file__).resolve().parents[2]
CDN = "https://res.cloudinary.com/fixture/image/upload/fixture.jpg"


class PostgresChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database == "sabeel_test"
        assert engine.url.query["host"] == os.environ["SABEEL_PG_TEST_SOCKET"]
        Base.metadata.create_all(engine)

    def setUp(self):
        with engine.begin() as connection:
            names = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
            connection.execute(text("TRUNCATE " + names + " RESTART IDENTITY CASCADE"))
        self.db = Session(engine, expire_on_commit=False)
        self.addCleanup(self.db.close)
        self.db.add(Org(id=1, name="Test workspace"))
        self.db.flush()
        self.db.add(IGAccount(id=1, org_id=1, name="Fixture", active=True, ig_user_id="123", access_token="fake-test-token"))
        self.db.commit()

    def post(self):
        post = Post(org_id=1, ig_account_id=1, status="drafted", caption="Fixture", media_url=CDN)
        self.db.add(post)
        self.db.commit()
        return post.id

    def test_schema_readiness_detects_missing_column_without_migrating(self):
        tree = ast.parse((ROOT / "app/db.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "validate_database_schema")
        namespace = {"engine": engine, "inspect": inspect}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "isolated_schema_check", "exec"), namespace)
        namespace["validate_database_schema"]()
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE posts RENAME COLUMN caption TO fixture_missing_caption"))
        try:
            with self.assertRaisesRegex(RuntimeError, "posts.caption"):
                namespace["validate_database_schema"]()
            self.assertNotIn("caption", {column["name"] for column in inspect(engine).get_columns("posts")})
        finally:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE posts RENAME COLUMN fixture_missing_caption TO caption"))
        namespace["validate_database_schema"]()

    def test_real_dump_restore_preserves_saved_source_and_publication_state(self):
        from app.services import backups
        post_id = self.post()
        post = self.db.get(Post, post_id)
        post.source_metadata = {"translation_text": "Synthetic fixture [1]", "arabic_text": "نص اختباري", "grade": None}
        post.flags = {"publication": {"creation_id": "12345", "outcome": "unknown"}}
        post.status = "publish_unknown"
        self.db.commit()
        with tempfile.TemporaryDirectory() as directory, patch.object(backups, "BACKUPS_DIR", directory), patch.object(settings, "database_url", engine.url.render_as_string(hide_password=False)), patch.object(settings, "backup_storage_type", "local"):
            result = backups.backup_postgres_database()
            self.assertEqual(result["status"], "success", result)
            dump = gzip.decompress((Path(directory) / result["file"]).read_bytes())
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("CREATE DATABASE sabeel_restore"))
        restore_engine = create_engine(engine.url.set(database="sabeel_restore"))
        try:
            response = subprocess.run(["psql", "-X", "--set", "ON_ERROR_STOP=1", "-h", os.environ["SABEEL_PG_TEST_SOCKET"], "-U", "sabeel_test", "-d", "sabeel_restore"], input=dump, capture_output=True, timeout=30)
            self.assertEqual(response.returncode, 0, response.stderr.decode()[:800])
            with Session(restore_engine) as restored:
                recovered = restored.get(Post, post_id)
                self.assertEqual(recovered.source_metadata, post.source_metadata)
                self.assertEqual(recovered.flags, post.flags)
                self.assertEqual(recovered.status, "publish_unknown")
                self.assertEqual(restored.get(IGAccount, recovered.ig_account_id).org_id, 1)
                self.assertEqual(restored.query(Post).count(), 1)
        finally:
            restore_engine.dispose()
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text("DROP DATABASE sabeel_restore"))

    def test_two_database_connections_publish_one_saved_post_once(self):
        id_ = self.post()
        sending, release = threading.Event(), threading.Event()
        def provider(**kwargs):
            kwargs["on_container_created"]("12345")
            sending.set()
            self.assertTrue(release.wait(5))
            return {"ok": True, "remote_id": "67890", "creation_id": "12345"}
        def first():
            with Session(engine) as db:
                return post_service.publish_post(db, id_, 1).ok
        with patch.object(publisher, "publish_to_instagram", side_effect=provider) as send, ThreadPoolExecutor(2) as pool:
            future = pool.submit(first)
            try:
                self.assertTrue(sending.wait(5))
                with Session(engine) as other:
                    self.assertEqual(post_service.publish_post(other, id_, 1).status_code, 409)
                    with self.assertRaises(Exception) as blocked:
                        post_service.get_mutable_post(other, id_, 1)
                    self.assertEqual(blocked.exception.status_code, 409)
            finally:
                release.set()
            self.assertTrue(future.result(5))
            send.assert_called_once()
        self.db.expire_all()
        self.assertEqual(self.db.get(Post, id_).flags["publication"]["remote_id"], "67890")

    def test_edit_lock_serializes_before_publisher_reads_caption(self):
        id_ = self.post()
        locked = post_service.get_mutable_post(self.db, id_, 1)
        locked.caption = "Latest committed caption"
        entered = threading.Event()
        def worker():
            with Session(engine) as db:
                entered.set()
                return post_service.publish_post(db, id_, 1).ok
        with patch.object(publisher, "publish_to_instagram", return_value={"ok": True, "remote_id": "67890"}) as send, ThreadPoolExecutor(1) as pool:
            future = pool.submit(worker)
            self.assertTrue(entered.wait(5))
            self.assertFalse(future.done())
            self.db.commit()
            self.assertTrue(future.result(5))
            self.assertEqual(send.call_args.kwargs["caption"], "Latest committed caption")

    def automation_fixture(self):
        self.db.add(ContentSource(id=1, org_id=None, name="Test library", source_type="quran_foundation"))
        self.db.flush()
        self.db.add(ContentItem(id=1, source_id=1, org_id=None, item_type="quran", title="Surah 2, Verse 3",
                                text="Synthetic fixture, not scripture", arabic_text="نص اختباري غير قرآني", topics=["wisdom"], meta={"surah_number": 2, "verse_number": 3}))
        self.db.add(TopicAutomation(id=1, org_id=1, ig_account_id=1, name="Fixture", topic_prompt="wisdom", enabled=True,
                                    image_mode="quote_card", approval_mode="needs_manual_approve", content_provider_scope="system_library"))
        self.db.commit()
        stack = ExitStack()
        self.addCleanup(stack.close)
        spec = importlib.util.spec_from_file_location("pg_automation_service", ROOT / "app/services/automation_service.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        stack.enter_context(patch.dict(sys.modules, {"app.services.automation_service": module}))
        stack.enter_context(patch.object(settings, "openai_api_key", None))
        stack.enter_context(patch.object(automation_runner, "get_lock_for_automation", side_effect=lambda _: threading.Lock()))
        stack.enter_context(patch.object(automation_runner, "validate_source_relevance", return_value={"accepted": True, "reason": "Fixture"}))
        stack.enter_context(patch("app.services.image_card.generate_quote_card", create=True, return_value=CDN))
        stack.enter_context(patch("app.services.llm.generate_card_framing_from_source", return_value={"supporting_text": "Fixture reflection"}))

    def test_hadith_manual_approval_round_trip_and_shared_publication(self):
        from app.routes import posts
        self.automation_fixture()
        canonical = {"source_type": "hadith", "collection_key": "bukhari", "hadith_number": 7,
                     "collection": "Fixture collection", "reference": "Fixture collection 7",
                     "translation_text": "Synthetic Hadith fixture, not a religious quotation.",
                     "card_text": "Synthetic Hadith fixture, not a religious quotation.",
                     "arabic_text": "نص اختباري", "narrator": "Returned narrator", "grade": None,
                     "provider_metadata": {"chapter": {"id": 9}}}
        item = self.db.get(ContentItem, 1)
        item.item_type = "hadith"
        item.title = canonical["reference"]
        item.text = canonical["translation_text"]
        item.arabic_text = canonical["arabic_text"]
        item.meta = canonical
        self.db.commit()
        with patch.object(settings, "hadith_in_automations_enabled", True), \
             patch("app.services.hadith_service.get_hadith_by_reference", return_value=canonical), \
             patch.object(automation_runner, "generate_topic_variations", return_value=["wisdom"]), \
             patch.object(publisher, "publish_to_instagram", return_value={"ok": True, "remote_id": "fixture-remote"}) as send:
            draft = automation_runner.run_automation_once(self.db, 1, force_publish=True)
            self.assertIsNotNone(draft)
            self.assertEqual(draft.status, "drafted")
            self.assertIsNone(draft.scheduled_time)
            send.assert_not_called()
            id_ = draft.id
            self.db.expire_all()
            recovered = self.db.get(Post, id_)
            self.assertEqual(recovered.source_metadata["provider_metadata"], canonical["provider_metadata"])
            self.assertEqual(recovered.card_message["headline"], canonical["card_text"])
            scheduled = datetime(2026, 12, 1, 17, tzinfo=timezone.utc)
            approved = posts.approve_post(id_, posts.ApproveIn(scheduled_time=scheduled), db=self.db, org_id=1)
            self.assertEqual(approved.status, "scheduled")
            self.assertEqual(approved.scheduled_time, scheduled)
            send.assert_not_called()
            hashtags = " ".join(approved.hashtags or [])
            caption = approved.caption + ("\n\n" + hashtags if hashtags else "")
            result = post_service.publish_post(self.db, id_, 1)
            self.assertTrue(result.ok, result.error)
            self.assertEqual(send.call_args.kwargs["caption"], caption)
            self.assertIn(canonical["translation_text"], caption)
            self.assertIn(canonical["arabic_text"], caption)
            self.assertEqual(result.post.id, id_)
            self.assertTrue(post_service.publish_post(self.db, id_, 1).ok)
            send.assert_called_once()

    def test_database_lock_blocks_overlapping_automation_workers(self):
        self.automation_fixture()
        started, release = threading.Event(), threading.Event()
        def variation(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(5))
            return ["wisdom"]
        def first():
            with Session(engine) as db:
                return automation_runner.run_automation_once(db, 1) is not None
        with patch.object(automation_runner, "generate_topic_variations", side_effect=variation), ThreadPoolExecutor(2) as pool:
            future = pool.submit(first)
            try:
                self.assertTrue(started.wait(5))
                with Session(engine) as other:
                    self.assertIsNone(automation_runner.run_automation_once(other, 1))
            finally:
                release.set()
            self.assertTrue(future.result(5))
        self.assertEqual(self.db.query(Post).count(), 1)

    def test_same_scheduled_occurrence_returns_saved_post_without_generation(self):
        self.automation_fixture()
        self.db.get(TopicAutomation, 1).approval_mode = "auto_approve"
        self.db.commit()
        occurrence = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
        with patch.object(automation_runner, "generate_topic_variations", return_value=["wisdom"]) as generate:
            first = automation_runner.run_automation_once(self.db, 1, scheduled_for=occurrence)
            self.assertIsNotNone(first)
            self.assertEqual(first.status, "scheduled")
            self.assertEqual(first.scheduled_time, occurrence)
            id_ = first.id
            second = automation_runner.run_automation_once(self.db, 1, scheduled_for=occurrence)
            self.assertEqual(second.id, id_)
            generate.assert_called_once()
        self.assertEqual(self.db.query(Post).count(), 1)

    def test_rollback_releases_database_automation_lock(self):
        with Session(engine) as first, Session(engine) as second:
            statement = text("SELECT pg_try_advisory_xact_lock(731204, 1)")
            self.assertTrue(first.execute(statement).scalar())
            self.assertFalse(second.execute(statement).scalar())
            first.rollback()
            self.assertTrue(second.execute(statement).scalar())


    def test_creator_preset_setup_is_concurrent_idempotent_and_preserves_existing_data(self):
        from app.models import StyleDNA
        from app.services.card_typography import DESIGN_FAMILIES
        spec = importlib.util.spec_from_file_location("pg_creator_presets", ROOT / "app/services/automation_service.py")
        module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
        existing = StyleDNA(name="Existing creator style", family="sacred_black", atmosphere="quiet", ornament_level="none", tone_style="calm", variation_pool=[], locked_traits={}, is_system_preset=True)
        self.db.add(existing); self.db.commit()
        existing_id = existing.id
        post_id = self.post()
        def seed():
            with Session(engine) as session:
                return module.seed_style_dna(session, families=DESIGN_FAMILIES)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: seed(), range(2)))
        self.assertEqual(sorted(results), [0, 3])
        self.assertEqual(seed(), 0)
        rows = self.db.query(StyleDNA).all()
        self.assertEqual(len(rows), 4)
        self.assertEqual({row.family for row in rows if row.id != existing_id}, DESIGN_FAMILIES)
        self.db.expire_all()
        self.assertEqual(self.db.get(StyleDNA, existing_id).family, 'sacred_black')
        self.assertEqual(self.db.get(Post, post_id).media_url, CDN)
        visible = module.list_system_presets(self.db)
        self.assertEqual(sum(p['family'] in DESIGN_FAMILIES for p in visible), 3)
