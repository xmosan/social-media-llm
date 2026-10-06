"""Saved-post lifecycle tests and mocked Instagram HTTP protocol checks."""

import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from test_security import DatabaseCase
from test_ownership import load_scheduler
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import IGAccount, Org, Post
from app.routes import posts, studio
from app.security.auth import get_current_user
from app.security.rbac import get_current_org_id
from app.services import post_service, publisher, publish_media

CDN_URL = "https://res.cloudinary.com/test-cloud/image/upload/test.jpg"


class PublishingTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount, Post):
            model.__table__.create(self.engine)
        self.db.add(Org(id=1, name="Fixture"))
        self.db.add(IGAccount(id=1, org_id=1, name="Fixture", ig_user_id="fixture", access_token="fake-token", active=True))
        self.db.add(Post(id=1, org_id=1, ig_account_id=1, status="drafted", caption="Saved caption", media_url=CDN_URL))
        self.db.commit()
        self.app = FastAPI()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_org_id] = lambda: 1
        self.app.dependency_overrides[get_current_user] = lambda: None
        self.app.include_router(posts.router)
        self.app.include_router(studio.router)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def confirmed(self, **kwargs):
        kwargs["on_container_created"]("container-1")
        self.assertEqual(self.db.get(Post, 1).flags["publication"]["creation_id"], "container-1")
        return {"ok": True, "remote_id": "published-1", "creation_id": "container-1"}

    def test_success_persists_ids_and_repeated_share_does_not_publish_twice(self):
        with patch.object(publisher, "publish_to_instagram", side_effect=self.confirmed) as publish:
            first = self.client.post("/posts/1/publish")
            second = self.client.post("/posts/1/publish")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200)
        publish.assert_called_once()
        saved = self.db.get(Post, 1)
        self.assertEqual(saved.flags["publication"]["remote_id"], "published-1")
        self.assertEqual(saved.status, "published")

    def test_competing_session_cannot_claim_a_post_already_being_sent(self):
        def send(**kwargs):
            with Session(self.engine) as competing:
                result = post_service.publish_post(competing, 1, 1)
                self.assertEqual(result.status_code, 409)
            return self.confirmed(**kwargs)
        with patch.object(publisher, "publish_to_instagram", side_effect=send) as publish:
            self.assertTrue(post_service.publish_post(self.db, 1, 1).ok)
            publish.assert_called_once()

    def test_ambiguous_response_prevents_retry_edit_reschedule_and_delete(self):
        def uncertain(**kwargs):
            kwargs["on_container_created"]("container-unknown")
            return {"ok": False, "outcome": "unknown", "creation_id": "container-unknown", "error": "Unconfirmed"}
        with patch.object(publisher, "publish_to_instagram", side_effect=uncertain) as publish:
            self.assertEqual(self.client.post("/posts/1/publish").status_code, 502)
            self.assertEqual(self.client.post("/posts/1/publish").status_code, 409)
            publish.assert_called_once()
        self.assertEqual(self.db.get(Post, 1).status, "publish_unknown")
        self.assertEqual(self.client.patch("/posts/1", json={"status": "drafted", "flags": {}}).status_code, 409)
        self.assertEqual(self.client.post("/api/studio/schedule-post", json={"post_id": 1, "scheduled_at": "2030-01-01T10:00:00Z"}).status_code, 409)
        self.assertEqual(self.client.delete("/posts/1").status_code, 409)

    def test_exception_after_claim_remains_unresolved(self):
        with patch.object(publisher, "publish_to_instagram", side_effect=RuntimeError("Synthetic failure")):
            result = post_service.publish_post(self.db, 1, 1)
        self.assertFalse(result.ok)
        self.assertEqual(self.db.get(Post, 1).status, "publish_unknown")

    def test_explicit_rejection_is_failed_and_can_be_corrected(self):
        with patch.object(publisher, "publish_to_instagram", return_value={"ok": False, "error": "Rejected"}):
            self.assertFalse(post_service.publish_post(self.db, 1, 1).ok)
        self.assertEqual(self.db.get(Post, 1).status, "failed")
        result = self.client.patch("/posts/1", json={"caption": "Corrected caption"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["caption_message"], {"caption": "Corrected caption"})

    def test_clients_cannot_fabricate_published_state_or_remote_id(self):
        self.assertEqual(self.client.patch("/posts/1", json={"status": "published"}).status_code, 422)
        result = self.client.patch("/posts/1", json={"flags": {"publication": {"remote_id": "fake"}}})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("publication", self.db.get(Post, 1).flags)

    def test_structured_caption_edit_is_the_text_sent_to_instagram(self):
        edited = self.client.patch("/posts/1", json={"caption_message": {"hook": "New hook", "body": "New body"}})
        self.assertEqual(edited.status_code, 200)
        with patch.object(publisher, "publish_to_instagram", side_effect=self.confirmed) as publish:
            self.assertEqual(self.client.post("/posts/1/publish").status_code, 200)
        self.assertEqual(publish.call_args.kwargs["caption"], "New hook\n\nNew body")

    def test_missing_local_image_stops_without_regeneration_or_publish(self):
        self.db.get(Post, 1).media_url = settings.public_base_url + "/uploads/missing-fixture.jpg"
        self.db.commit()
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "uploads_dir", directory), patch.object(publisher, "publish_to_instagram") as publish, patch("app.services.automation_runner.recover_stale_media") as regenerate:
            result = post_service.publish_post(self.db, 1, 1)
            self.assertEqual(result.status_code, 422)
            publish.assert_not_called()
            regenerate.assert_not_called()

    def test_identical_local_image_must_reach_cdn_before_publish(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "uploads_dir", directory):
            path = Path(directory) / "fixture.jpg"
            path.write_bytes(b"fixture-image")
            url = settings.public_base_url + "/uploads/fixture.jpg"
            with patch("app.services.cloudinary_service.upload_to_cloudinary", return_value=CDN_URL) as upload:
                self.assertEqual(publish_media.prepare_publish_media(url), CDN_URL)
                upload.assert_called_once_with(str(path.resolve()))
            with patch("app.services.cloudinary_service.upload_to_cloudinary", return_value=None), self.assertRaises(ValueError):
                publish_media.prepare_publish_media(url)
            with self.assertRaises(ValueError):
                publish_media.prepare_publish_media(settings.public_base_url + "/uploads/%2e%2e/private.jpg")

    def test_scheduled_publish_uses_shared_service_and_saved_caption(self):
        from datetime import datetime, timezone
        post = self.db.get(Post, 1)
        post.status = "scheduled"
        post.scheduled_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        self.db.commit()
        scheduler = load_scheduler()
        with patch.object(publisher, "publish_to_instagram", side_effect=self.confirmed) as publish:
            self.assertEqual(scheduler.publish_due_posts(lambda: self.db), 1)
            self.assertEqual(scheduler.publish_due_posts(lambda: self.db), 0)
            self.assertEqual(publish.call_args.kwargs["caption"], "Saved caption")

    def uncertain_post(self, status="publish_unknown", minutes=15):
        post = self.db.get(Post, 1)
        post.status = status
        post.flags = {"publication": {"creation_id": "12345", "ig_user_id": "fixture", "started_at": (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()}}
        self.db.commit()
        return post

    def test_reconciliation_confirms_published_without_sending_again_or_inventing_id(self):
        self.uncertain_post()
        with patch.object(publisher, "get_container_status", return_value="PUBLISHED") as check, patch.object(publisher, "publish_to_instagram") as publish:
            response = self.client.post("/posts/1/reconcile-publication")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.client.post("/posts/1/publish").status_code, 200)
            self.assertEqual(self.client.post("/posts/1/reconcile-publication").status_code, 200)
            check.assert_called_once_with("12345", "fake-token")
            publish.assert_not_called()
        self.assertIsNone(self.db.get(Post, 1).published_time)
        self.assertNotIn("remote_id", self.db.get(Post, 1).flags["publication"])

    def test_only_terminal_nonpublished_statuses_allow_correction(self):
        for code in ("ERROR", "EXPIRED", "FINISHED", "IN_PROGRESS", None):
            with self.subTest(code=code):
                self.uncertain_post()
                with patch.object(publisher, "get_container_status", return_value=code):
                    result = post_service.reconcile_publication(self.db, 1, 1)
                self.assertEqual(result.ok, code in {"ERROR", "EXPIRED"})
                self.assertEqual(self.db.get(Post, 1).status, "failed" if result.ok else "publish_unknown")

    def test_reconciliation_refuses_wrong_workspace_active_send_and_changed_account(self):
        post = self.uncertain_post(status="publishing", minutes=1)
        with patch.object(publisher, "get_container_status") as check:
            self.assertEqual(post_service.reconcile_publication(self.db, 1, 2).status_code, 404)
            self.assertEqual(post_service.reconcile_publication(self.db, 1, 1).status_code, 409)
            post = self.uncertain_post()
            self.db.get(IGAccount, 1).ig_user_id = "different-account"
            self.db.commit()
            self.assertEqual(post_service.reconcile_publication(self.db, 1, 1).status_code, 409)
            check.assert_not_called()

    def test_schedule_promotes_same_image_before_saving_and_missing_image_keeps_draft(self):
        self.db.get(Post, 1).media_url = settings.public_base_url + "/uploads/test.jpg"
        self.db.commit()
        payload = {"post_id": 1, "scheduled_at": "2030-01-01T10:00:00Z"}
        with patch.object(post_service, "prepare_publish_media", side_effect=ValueError("Missing image")):
            response = self.client.post("/api/studio/schedule-post", json=payload)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.db.get(Post, 1).status, "drafted")
        with patch.object(post_service, "prepare_publish_media", return_value=CDN_URL) as promote:
            self.assertEqual(self.client.post("/api/studio/schedule-post", json=payload).status_code, 200)
            promote.assert_called_once()
            self.db.expire_all()
            self.assertEqual(self.db.get(Post, 1).media_url, CDN_URL)

    def test_scheduling_patch_and_approval_cannot_bypass_media_validation(self):
        with patch.object(post_service, "prepare_publish_media", side_effect=ValueError("Missing image")):
            response = self.client.patch("/posts/1", json={"status": "scheduled", "scheduled_time": "2030-01-01T10:00:00Z"})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.db.get(Post, 1).status, "drafted")
            response = self.client.post("/posts/1/approve", json={"approve_anyway": True})
            self.assertEqual(response.status_code, 422, response.text)

    def test_incomplete_legacy_scripture_post_cannot_reach_publisher(self):
        post = self.db.get(Post, 1)
        post.source_type = "quran"
        self.db.commit()
        with patch.object(publisher, "publish_to_instagram") as send:
            self.assertEqual(post_service.publish_post(self.db, 1, 1).status_code, 422)
            send.assert_not_called()

    def test_snapshot_text_reference_and_card_are_checked_before_publish(self):
        post = self.db.get(Post, 1)
        post.source_type = "quran"
        post.source_metadata = {"reference": "Qur'an 2:3", "translation_text": "Synthetic fixture", "arabic_text": "نص اختباري"}
        post.source_reference = "Qur'an 2:3"
        post.source_text = "Synthetic fixture"
        post.card_message = {"eyebrow": "Qur'an 2:3", "headline": "Wrong source", "arabic_text": "نص اختباري"}
        self.db.commit()
        with patch.object(publisher, "publish_to_instagram") as send:
            self.assertEqual(post_service.publish_post(self.db, 1, 1).status_code, 422)
            send.assert_not_called()
        post.card_message = {**post.card_message, "headline": "Synthetic fixture"}
        self.db.commit()
        with patch.object(publisher, "publish_to_instagram", side_effect=self.confirmed):
            self.assertTrue(post_service.publish_post(self.db, 1, 1).ok)


class InstagramProtocolTests(unittest.TestCase):
    def test_container_status_is_read_only_and_rejects_mismatched_identity(self):
        with patch.object(publisher.requests, "get", return_value=self.response({"id": "123", "status_code": "PUBLISHED"})) as get, patch.object(publisher.requests, "post") as send:
            self.assertEqual(publisher.get_container_status("123", "fake-token"), "PUBLISHED")
            self.assertNotIn("fake-token", get.call_args.args[0])
            send.assert_not_called()
        with patch.object(publisher.requests, "get", return_value=self.response({"id": "999", "status_code": "PUBLISHED"})):
            self.assertIsNone(publisher.get_container_status("123", "fake-token"))
        with patch.object(publisher.requests, "get") as get:
            self.assertIsNone(publisher.get_container_status("../123", "fake-token"))
            get.assert_not_called()

    def preflight(self):
        response = Mock(status_code=200)
        response.raw = io.BytesIO(b"\xff\xd8fixture")
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def response(self, data, status=200):
        return SimpleNamespace(status_code=status, json=lambda: data)

    def invoke(self, callback=None):
        return publisher.publish_to_instagram(caption="Fixture", media_url=CDN_URL, ig_user_id="fixture", access_token="fake-token", on_container_created=callback)

    def test_9007_retries_same_container_without_local_time_error(self):
        responses = [self.response({"id": "container-1"}), self.response({"error": {"code": 9007}}, 400), self.response({"id": "published-1"})]
        with patch.object(publisher.requests, "get", return_value=self.preflight()), patch.object(publisher.requests, "post", side_effect=responses) as request, patch.object(publisher.time, "sleep") as sleep:
            callback = Mock()
            result = self.invoke(callback)
        self.assertTrue(result["ok"])
        callback.assert_called_once_with("container-1")
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args_list[1].kwargs["data"]["creation_id"], request.call_args_list[2].kwargs["data"]["creation_id"])
        sleep.assert_called_once_with(4)

    def test_timeout_after_publish_request_is_not_retried(self):
        with patch.object(publisher.requests, "get", return_value=self.preflight()), patch.object(publisher.requests, "post", side_effect=[self.response({"id": "container-1"}), TimeoutError]) as request:
            result = self.invoke()
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["creation_id"], "container-1")
        self.assertEqual(request.call_count, 2)

    def test_success_http_without_publication_identity_needs_reconciliation(self):
        with patch.object(publisher.requests, "get", return_value=self.preflight()), patch.object(publisher.requests, "post", side_effect=[self.response({"id": "container-1"}), self.response({})]) as request:
            result = self.invoke()
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(request.call_count, 2)

    def test_failure_to_persist_container_prevents_publish_request(self):
        with patch.object(publisher.requests, "get", return_value=self.preflight()), patch.object(publisher.requests, "post", return_value=self.response({"id": "container-1"})) as request:
            with self.assertRaises(RuntimeError):
                self.invoke(Mock(side_effect=RuntimeError))
            self.assertEqual(request.call_count, 1)

    def test_non_durable_urls_rejected_without_network(self):
        with patch.object(publisher.requests, "get") as request:
            result = publisher.publish_to_instagram(caption="Fixture", media_url="https://app.sabeelstudio.com/uploads/x.jpg", ig_user_id="fixture", access_token="fake-token")
        self.assertFalse(result["ok"])
        request.assert_not_called()
