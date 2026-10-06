"""Tenant boundary tests; providers, uploads and scheduler execution are isolated."""

import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

import httpx

from test_security import DatabaseCase
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.config import settings
from app.db import get_db
from app.models import ContentItem, ContentProfile, ContentSource, IGAccount, MediaAsset, Org, Post, StyleDNA, TopicAutomation
from app.routes import automations, ig_accounts, media, posts, studio
from app.security.auth import get_current_user
from app.security.rbac import get_current_org_id
from app.security.ownership import require_content_item, validate_automation_links
from app.services import automation_runner


@compiles(JSONB, "sqlite")
def sqlite_fixture_jsonb(type_, compiler, **kwargs):
    # Only for disposable test tables; no production dialect fallback.
    return "JSON"


def load_scheduler():
    path = Path(__file__).resolve().parents[2] / "app/services/scheduler.py"
    spec = importlib.util.spec_from_file_location("isolated_scheduler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OwnershipTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount, MediaAsset, ContentSource, ContentItem, ContentProfile, StyleDNA, TopicAutomation, Post):
            model.__table__.create(self.engine)
        self.db.add_all([Org(id=1, name="Own"), Org(id=2, name="Foreign")])
        for id_, org, active in [(1, 1, True), (2, 2, True), (3, 1, False)]:
            self.db.add(IGAccount(id=id_, org_id=org, name="Fixture", ig_user_id=f"fixture-{id_}", access_token="fake-test-token", active=active))
        for id_, org, account in [(1, 1, 1), (2, 2, 2), (3, 1, 2)]:
            self.db.add(MediaAsset(id=id_, org_id=org, ig_account_id=account, url=f"https://example.test/{id_}.jpg"))
        self.db.add(ContentSource(id=1, org_id=1, name="Fixture", source_type="manual_library"))
        for id_, org, owner in [(1, 1, None), (2, 2, None), (3, None, None), (4, 1, 7)]:
            self.db.add(ContentItem(id=id_, org_id=org, owner_user_id=owner, source_id=1, text="Fixture"))
        for id_, org in [(1, 1), (2, 2)]:
            self.db.add(ContentProfile(id=id_, org_id=org, name="Fixture"))
        for id_, org, system in [(1, 1, False), (2, 2, False), (3, None, True), (4, None, False)]:
            self.db.add(StyleDNA(id=id_, org_id=org, name="Fixture", family="test", atmosphere="test",
                                 ornament_level="none", tone_style="test", variation_pool=[], locked_traits={}, is_system_preset=system))
        for id_, org, account in [(1, 1, 1), (2, 2, 2), (3, 1, 2), (4, 1, 3)]:
            self.db.add(Post(id=id_, org_id=org, ig_account_id=account, status="drafted", caption="Fixture", media_url="https://example.test/test.jpg"))
        for id_, account in [(1, 1), (2, 2)]:
            self.db.add(TopicAutomation(id=id_, org_id=1, ig_account_id=account, name="Fixture", topic_prompt="Fixture", enabled=True))
        self.db.commit()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        upload_patch = patch.object(settings, "uploads_dir", directory.name)
        upload_patch.start()
        self.addCleanup(upload_patch.stop)
        self.app = FastAPI()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_org_id] = lambda: 1
        self.app.dependency_overrides[get_current_user] = lambda: None
        for router in (studio.router, posts.router, media.router, automations.router, ig_accounts.router):
            self.app.include_router(router)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_account_health_uses_publisher_api_and_header_auth(self):
        from app.services.publisher import GRAPH_URL
        response = httpx.Response(200, json={"id": "fixture-1", "username": "fixture"})
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response)) as check:
            result = self.client.get("/ig-accounts/1/health")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"healthy": True, "status": "connected", "username": "fixture"})
        check.assert_awaited_once_with(f"{GRAPH_URL}/fixture-1", params={"fields": "id,username"},
                                      headers={"Authorization": "Bearer fake-test-token"}, timeout=10, follow_redirects=False)

    def test_account_health_rejects_foreign_or_missing_accounts_before_network(self):
        with patch.object(httpx.AsyncClient, "get", AsyncMock()) as check:
            for id_ in (2, 999):
                self.assertEqual(self.client.get(f"/ig-accounts/{id_}/health").status_code, 404)
            check.assert_not_awaited()

    def test_account_health_missing_token_is_disconnected(self):
        self.db.get(IGAccount, 1).access_token = ""
        self.db.commit()
        with patch.object(httpx.AsyncClient, "get", AsyncMock()) as check:
            result = self.client.get("/ig-accounts/1/health")
            check.assert_not_awaited()
        self.assertFalse(result.json()["healthy"])
        self.assertEqual(result.json()["status"], "disconnected")

    def test_account_health_provider_rejection_does_not_expose_response_or_claim_expiry(self):
        response = httpx.Response(400, json={"error": {"message": "private provider body fake-test-token"}})
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response)):
            result = self.client.get("/ig-accounts/1/health")
        self.assertEqual(result.json()["status"], "needs_attention")
        self.assertNotIn("private provider body", result.text)
        self.assertNotIn("fake-test-token", result.text)
        self.assertNotIn("expired", result.text.lower())

    def test_account_health_outage_malformed_or_wrong_account_is_not_connected(self):
        for response in (httpx.Response(503, json={}), httpx.Response(200, text="not JSON"),
                         httpx.Response(200, json=[]), httpx.Response(200, json={"id": "other", "username": "fixture"})):
            with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response)):
                result = self.client.get("/ig-accounts/1/health")
            self.assertFalse(result.json()["healthy"])
            self.assertEqual(result.json()["status"], "unavailable")
        with patch.object(httpx.AsyncClient, "get", AsyncMock(side_effect=httpx.ConnectError("fake-test-token"))):
            result = self.client.get("/ig-accounts/1/health")
        self.assertEqual(result.json()["status"], "unavailable")
        self.assertNotIn("fake-test-token", result.text)

    def test_studio_rejects_foreign_inactive_and_invalid_accounts(self):
        for account, status in [(2, 403), (3, 422), (999, 403), ("bad", 422)]:
            result = self.client.post("/api/studio/create-post", json={"ig_account_id": account, "caption": "Fixture"})
            self.assertEqual(result.status_code, status, result.text)
        self.assertEqual(self.db.query(Post).count(), 4)

    def test_studio_saves_owned_account_and_reopens(self):
        result = self.client.post("/api/studio/create-post", json={"ig_account_id": 1, "caption": "Saved fixture", "source_type": "manual"})
        self.assertEqual(result.status_code, 200, result.text)
        post = self.client.get(f'/api/studio/post/{result.json()["id"]}').json()
        self.assertEqual((post["org_id"], post["ig_account_id"], post["caption"]), (1, 1, "Saved fixture"))

    def test_studio_invalid_schedule_and_fabricated_published_state_rejected(self):
        for extra in ({"scheduled_at": "invalid"}, {"status": "published"}):
            self.assertEqual(self.client.post("/api/studio/create-post", json={"ig_account_id": 1, **extra}).status_code, 422)

    def test_intake_media_ownership_and_correct_foreign_key(self):
        for asset in (2, 3, 999):
            result = self.client.post("/posts/intake", data={"ig_account_id": 1, "visual_mode": "media_library", "library_item_id": asset})
            self.assertEqual(result.status_code, 403, result.text)
        result = self.client.post("/posts/intake", data={"ig_account_id": 1, "visual_mode": "media_library", "library_item_id": 1})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["media_asset_id"], 1)
        self.assertIsNone(result.json()["library_item_id"])

    def test_preview_does_not_render_or_download_foreign_media(self):
        with patch.object(posts, "render_quote_card") as render, patch.object(posts.requests, "get") as download:
            result = self.client.post("/posts/preview_render", data={"visual_mode": "media_library", "library_item_id": 2})
            self.assertEqual(result.status_code, 403)
            render.assert_not_called()
            download.assert_not_called()

    def test_upload_rejects_foreign_account_before_saving_file(self):
        result = self.client.post("/media-assets", data={"ig_account_id": 2}, files={"image": ("test.jpg", b"fixture", "image/jpeg")})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(list(Path(settings.uploads_dir).iterdir()), [])

    def test_upload_does_not_use_client_filename_as_path(self):
        result = self.client.post("/media-assets", data={"ig_account_id": 1}, files={"image": ("../../escape.jpg", b"fixture", "image/jpeg")})
        self.assertEqual(result.status_code, 200, result.text)
        asset = self.db.get(MediaAsset, result.json()["id"])
        self.assertEqual(Path(asset.storage_path).parent, Path(settings.uploads_dir))
        self.assertNotIn("escape", asset.storage_path)

    def test_post_update_rejects_foreign_media_without_partial_caption_change(self):
        result = self.client.patch("/posts/1", json={"caption": "must not save", "media_asset_id": 2})
        self.assertEqual(result.status_code, 403)
        self.db.refresh(self.db.get(Post, 1))
        self.assertEqual(self.db.get(Post, 1).caption, "Fixture")
        result = self.client.patch("/posts/1", json={"media_asset_id": 1, "media_url": "https://example.test/wrong.jpg"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["media_url"], "https://example.test/1.jpg")

    def test_legacy_cross_workspace_account_cannot_publish_approve_or_schedule(self):
        with patch("app.services.publisher.publish_to_instagram") as publish:
            for path, payload in [("/posts/3/publish", {}), ("/posts/3/approve", {"scheduled_time": "2030-01-01T12:00:00Z"}),
                                  ("/api/studio/schedule-post", {"post_id": 3, "scheduled_at": "2030-01-01T12:00:00Z"})]:
                self.assertEqual(self.client.post(path, json=payload).status_code, 403)
            self.assertEqual(self.client.post("/posts/4/publish").status_code, 422)
            publish.assert_not_called()

    def test_automation_create_and_update_validate_all_linked_resources(self):
        for fields in ({"media_asset_id": 2}, {"content_profile_id": 2}, {"style_dna_id": 2}, {"style_dna_pool": [1, 2]}, {"style_dna_id": 4}):
            result = self.client.post("/automations", json={"ig_account_id": 1, "name": "new", "topic_prompt": "test", **fields})
            self.assertEqual(result.status_code, 403, result.text)
            result = self.client.patch("/automations/1", json={"name": "must not save", **fields})
            self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(self.db.get(TopicAutomation, 1).name, "Fixture")
        validate_automation_links(self.db, 1, {"style_dna_pool": [1, 3], "media_asset_id": 1, "content_profile_id": 1})

    def test_content_access_preserves_global_and_own_personal_items(self):
        for id_ in (1, 3):
            self.assertEqual(require_content_item(self.db, 1, id_).id, id_)
        self.assertEqual(require_content_item(self.db, 1, 4, user_id=7).id, 4)
        for id_, user in [(2, None), (4, None), (4, 8)]:
            with self.assertRaises(HTTPException):
                require_content_item(self.db, 1, id_, user_id=user)

    def test_media_resolver_cannot_read_another_workspaces_asset(self):
        with self.assertRaises(HTTPException):
            automation_runner.resolve_media_url(self.db, 1, 1, "library_fixed", media_asset_id=2)
        self.assertEqual(automation_runner.resolve_media_url(self.db, 1, 1, "library_fixed", media_asset_id=1), "https://example.test/1.jpg")

    def test_background_automation_rejects_legacy_cross_workspace_account_before_generation(self):
        with patch.object(automation_runner, "generate_topic_variations") as generate:
            self.assertIsNone(automation_runner.run_automation_once(self.db, 2))
            generate.assert_not_called()
        self.assertIn("workspace", self.db.get(TopicAutomation, 2).last_error)

    def test_scheduler_rejects_legacy_cross_workspace_account(self):
        from datetime import datetime, timezone
        scheduled = self.db.get(Post, 3)
        scheduled.status = "scheduled"
        scheduled.scheduled_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        self.db.commit()
        scheduler = load_scheduler()
        with patch("app.services.publisher.publish_to_instagram") as publish:
            self.assertEqual(scheduler.publish_due_posts(lambda: self.db), 0)
            publish.assert_not_called()
        self.assertEqual(self.db.get(Post, 3).status, "failed")
