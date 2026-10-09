"""Real PostgreSQL transactions; every external provider is mocked."""

import importlib.util
import os
from pathlib import Path
import sys
import threading
import unittest
import ast
import gzip
import shutil
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

    def test_new_creator_registration_login_and_workspace_are_isolated(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.db import get_db
        from app.models import User, OrgMember
        from app.routes import auth
        # setUp inserts an explicit ID; let normal registration use the next one.
        self.db.execute(text("SELECT setval(pg_get_serial_sequence('orgs','id'), (SELECT MAX(id) FROM orgs))"))
        self.db.commit()
        application = FastAPI()
        application.dependency_overrides[get_db] = lambda: self.db
        application.include_router(auth.router)
        with patch.object(settings, 'signup_enabled', True), TestClient(application, base_url='https://testserver') as client:
            created = client.post('/auth/register', json={
                'email': 'creator@example.com', 'name': 'Isolated Creator',
                'password': 'disposable-creator-test-password',
            })
            self.assertEqual(created.status_code, 200)
            for flag in ('HttpOnly', 'Secure', 'SameSite=lax'):
                self.assertIn(flag, created.headers['set-cookie'])
            profile = client.get('/auth/me')
            self.assertEqual(profile.status_code, 200)
            user = self.db.get(User, profile.json()['id'])
            self.assertFalse(user.is_superadmin)
            self.assertNotEqual(user.active_org_id, 1)
            membership = self.db.query(OrgMember).filter_by(user_id=user.id).one()
            self.assertEqual(membership.org_id, user.active_org_id)
            self.assertEqual(membership.role, 'owner')
            self.assertEqual(self.db.query(IGAccount).filter_by(org_id=user.active_org_id).count(), 0)
            client.post('/auth/logout')
            self.assertEqual(client.get('/auth/me').status_code, 401)
            login = client.post('/auth/login', data={'username': 'CREATOR@example.com', 'password': 'disposable-creator-test-password'})
            self.assertEqual(login.status_code, 200)
            self.assertEqual(client.get('/auth/me').json()['id'], user.id)

    def test_quran_annotation_repair_preview_apply_and_guarded_rollback(self):
        import json
        from types import SimpleNamespace
        spec=importlib.util.spec_from_file_location('quran_annotation_repair',ROOT/'scripts/repair_quran_annotations.py')
        repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)
        self.db.add(ContentSource(id=1,org_id=None,name='Provider fixture',source_type='quran_foundation'))
        self.db.flush()
        old={'verse_key':'2:3','translation_id':'131'}
        self.db.add(ContentItem(id=1,source_id=1,item_type='quran',title='Surah 2, Verse 3',text='Synthetic body.1',arabic_text='نص',meta=old))
        self.db.commit()
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'DATABASE_URL':engine.url.render_as_string(hide_password=False)}):
            root=Path(d);t=root/'translations.json';a=root/'arabic.json';backup=root/'rollback.json'
            t.write_text(json.dumps({'translations':[{'verse_key':'2:3','resource_id':20,'text':'Synthetic body.<sup foot_note=9>1</sup>','foot_notes':{'9':'Exact note'}}],'meta':{'translation_name':'Returned name'}}))
            a.write_text(json.dumps({'verses':[{'verse_key':'2:3','text_uthmani':'نص'}]}))
            args=SimpleNamespace(translations=str(t),arabic=str(a),backup=str(backup),rollback=None,apply=False)
            repair.run(args);self.db.expire_all()
            self.assertEqual(self.db.get(ContentItem,1).text,'Synthetic body.1');self.assertFalse(backup.exists());self.db.rollback()
            args.apply=True;repair.run(args);self.db.expire_all()
            self.assertEqual(self.db.get(ContentItem,1).text,'Synthetic body.')
            self.assertEqual(backup.stat().st_mode & 0o777,0o600)
            self.db.rollback()
            # Refuse to overwrite the only rollback copy.
            with self.assertRaises(FileExistsError):repair.run(args)
            args.rollback=str(backup);args.apply=False;repair.run(args)
            args.apply=True;repair.run(args);self.db.expire_all()
            self.assertEqual(self.db.get(ContentItem,1).text,'Synthetic body.1')
            self.assertEqual(self.db.get(ContentItem,1).meta,old);self.db.rollback()
            with self.assertRaises(ValueError):repair.run(args)

    def test_brand_migration_is_additive_and_repeatable_on_existing_workspaces(self):
        spec=importlib.util.spec_from_file_location('brand_migration', ROOT/'scripts/migrate_brand_kit.py')
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        self.db.close()
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE orgs DROP COLUMN brand_kit'))  # Disposable fixture only.
            migration.migrate(connection);migration.migrate(connection)
        with Session(engine) as db:
            org=db.get(Org,1)
            self.assertEqual(org.name,'Test workspace');self.assertIsNone(org.brand_kit)
            self.assertEqual(db.query(IGAccount).count(),1)

    def test_simultaneous_brand_edits_accept_one_revision_and_reject_the_stale_one(self):
        from app.routes.studio import save_brand_kit
        from app.services.brand_kit import normalize_brand
        from app.services.media_sequence import card_digest
        from fastapi import HTTPException
        revision=card_digest(normalize_brand());barrier=threading.Barrier(2)
        def save(palette):
            with Session(engine) as db:
                loaded = db.get(Org,1)  # Authorization may already have loaded this row.
                barrier.wait(timeout=10)
                try:
                    save_brand_kit({'brand_kit':normalize_brand({'palette':palette}),'revision':revision},db,1)
                    return 200
                except HTTPException as error:
                    db.rollback();return error.status_code
        with ThreadPoolExecutor(2) as pool:statuses=list(pool.map(save,['clay','night']))
        self.assertEqual(sorted(statuses),[200,409])
        self.db.expire_all();self.assertIn(self.db.get(Org,1).brand_kit['palette'],{'clay','night'})

    def test_concurrent_studio_recovery_key_creates_one_ordered_draft(self):
        from app.routes.studio import studio_create_post
        from app.services.media_sequence import seal_manifest, card_digest
        card = {"eyebrow":"Fixture", "headline":"Exact synthetic text", "arabic_text":""}
        pages = [{"index":i,"url":CDN+str(i),"width":1080,"height":1350,"quality":{"status":"passed"},
                  "slices":[{"role":"source_translation","start":i*10,"end":10 if i==0 else len(card["headline"])}]} for i in range(2)]
        manifest=seal_manifest({"version":1,"format":"carousel_4_5","card_digest":card_digest(card),"pages":pages},1)
        payload={"ig_account_id":1,"draft_key":"11111111-1111-4111-8111-111111111111","card_message":card,
                 "visual_design":{"media_manifest":manifest},"media_url":pages[0]["url"],"caption":"Separate caption"}
        barrier=threading.Barrier(2)
        def save():
            with Session(engine) as db:
                barrier.wait(timeout=10)
                return studio_create_post(payload,db,1,None).id
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(lambda _:save(),range(2)))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(self.db.query(Post).count(),1)
        self.db.expire_all()
        post=self.db.get(Post,ids[0])
        self.assertEqual(post.flags['media_manifest'],manifest)
        self.assertEqual(post.card_message,card)

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
            snapshot = Path(directory) / result["file"]
            dump = gzip.decompress(snapshot.read_bytes())
            from scripts.verify_backup_restore import restore_and_check
            counts = restore_and_check(snapshot, Path(shutil.which("psql")).parent)
            self.assertEqual(counts["posts"], 1)
            self.assertEqual(counts["orphan_or_mismatched_post_accounts"], 0)
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

    def test_automation_budget_denial_stops_without_a_partial_post_or_more_ai_calls(self):
        from app.services.usage_limits import UsageLimitError
        self.automation_fixture()
        with patch.object(automation_runner, 'generate_topic_variations', side_effect=UsageLimitError('Preview allowance reached')), \
             patch.object(automation_runner, 'validate_source_relevance') as relevance:
            with self.assertRaises(UsageLimitError):
                automation_runner.run_automation_once(self.db, 1)
        relevance.assert_not_called()
        self.assertEqual(self.db.query(Post).count(), 0)
        self.db.expire_all()
        self.assertIn('Preview allowance reached', self.db.get(TopicAutomation, 1).last_error)

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

    def test_automation_uses_workspace_brand_and_freezes_it_in_reviewable_draft(self):
        from app.services.brand_kit import normalize_brand
        from app.services.media_sequence import card_digest, validate_manifest
        self.automation_fixture()
        kit=normalize_brand({'palette':'clay','signature':'@fixture','series_name':'Learning together','visual_identity':'Coastal dusk, muted blue, no buildings.'})
        self.db.get(Org,1).brand_kit=kit
        self.db.get(TopicAutomation,1).approval_mode='auto_approve'
        self.db.commit()
        def render(**kw):
            self.assertEqual(kw['brand_kit'],kit)
            card=kw['card_message']
            kw['render_metadata'].update({'quality':{'review_required':True},'media_manifest':{
                'version':1,'format':'feed_4_5','card_digest':card_digest(card),'brand_kit':kw['brand_kit'],
                'pages':[{'index':0,'url':CDN,'width':1080,'height':1350,'quality':{'status':'passed'},
                          'slices':[{'role':role,'start':0,'end':len(card[field])}
                              for role,field in [('source_translation','headline'),('source_arabic','arabic_text'),('reflection','supporting_text')]
                              if card.get(field)]}]}})
            return CDN
        with patch('app.services.image_card.generate_quote_card',side_effect=render),patch.object(automation_runner,'generate_topic_variations',return_value=['wisdom']):
            draft=automation_runner.run_automation_once(self.db,1)
        self.assertIsNotNone(draft);self.assertEqual(draft.status,'drafted')
        self.assertIsNone(draft.scheduled_time)
        self.assertEqual(draft.flags['visual_design']['brand_kit'],kit)
        validate_manifest(draft.flags['media_manifest'],draft.card_message,1)
        self.db.get(Org,1).brand_kit=normalize_brand({'palette':'night'});self.db.commit();self.db.expire_all()
        self.assertEqual(self.db.get(Post,draft.id).flags['media_manifest']['brand_kit'],kit)

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
        self.assertEqual(sorted(results), [0, 7])
        self.assertEqual(seed(), 0)
        rows = self.db.query(StyleDNA).all()
        self.assertEqual(len(rows), 8)
        self.assertEqual({row.family for row in rows if row.id != existing_id}, DESIGN_FAMILIES)
        self.db.expire_all()
        self.assertEqual(self.db.get(StyleDNA, existing_id).family, 'sacred_black')
        self.assertEqual(self.db.get(Post, post_id).media_url, CDN)
        visible = module.list_system_presets(self.db)
        self.assertEqual(sum(p['family'] in DESIGN_FAMILIES for p in visible), 7)

    def test_existing_nature_preset_keeps_its_id_and_does_not_gain_a_duplicate(self):
        from app.models import StyleDNA
        spec = importlib.util.spec_from_file_location("pg_vision_presets", ROOT / "app/services/automation_service.py")
        module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
        old = StyleDNA(name="Emerald Calm", family="emerald_forest", atmosphere="quiet", ornament_level="none", tone_style="calm", variation_pool=[], locked_traits={}, is_system_preset=True)
        self.db.add(old); self.db.commit(); old_id=old.id
        self.assertEqual(module.seed_style_dna(self.db, families={'emerald_forest'}), 0)
        self.assertEqual(self.db.query(StyleDNA).filter(StyleDNA.family=='emerald_forest').count(), 1)
        self.db.expire_all()
        self.assertEqual(self.db.get(StyleDNA,old_id).name,'Emerald Calm')
        visible=next(p for p in module.list_system_presets(self.db) if p['id']==old_id)
        self.assertEqual(visible['label'],'Quiet Nature')
        self.assertEqual(visible['scene_key'],'emerald_forest')
