"""Adversarial requests use disposable records; no live providers or user data."""
import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import UploadFile

from app.db import get_db
from app.models import ContentSource, ContentItem, Org, OrgMember, User
from app.routes import library
from app.security.auth import create_access_token
from app.security.http_boundary import HTTPBoundaryMiddleware
from app.security.public_fetch import fetch_public_document
from app.security.uploads import save_image_upload
from test_ownership import sqlite_fixture_jsonb
from test_security import DatabaseCase


class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        self.calls = []
        @app.api_route("/action", methods=["GET", "POST", "PATCH", "DELETE"])
        @app.post("/posts/preview_render")
        async def action(request: Request):
            self.calls.append(await request.body())
            return {"ok": True}
        app.add_middleware(HTTPBoundaryMiddleware, public_url="https://app.example.test", body_limit=64, upload_limit=128)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_browser_mutations_reject_cross_origin_and_null_origin(self):
        for supplied in ("https://evil.test", "null", "https://app.example.test.evil.test",
                         "http://app.example.test", "https://app.example.test:444",
                         "https://app.example.test/evil", "https://app.example.test?bad=1"):
            for method in ("post", "patch", "delete"):
                response = getattr(self.client, method)("/action", headers={"Origin": supplied})
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])

    def test_cookie_origin_required_and_explicit_bearer_client_preserved(self):
        self.client.cookies.set("access_token", "fixture")
        self.assertEqual(self.client.post("/action").status_code, 403)
        self.assertEqual(self.client.post("/action", headers={"Origin": "https://app.example.test"}).status_code, 200)
        self.assertEqual(self.client.post("/action", headers={"Referer": "https://app.example.test/app"}).status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/action", headers={"Authorization": "Bearer fixture"}).status_code, 200)
        self.assertEqual(self.client.get("/action", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 200)

    def test_cache_headers_and_large_body_preflight(self):
        response = self.client.post("/action", content=b"x" * 65)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.calls, [])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_legacy_preview_keeps_the_bounded_image_upload_allowance(self):
        self.assertEqual(self.client.post("/posts/preview_render", content=b"x" * 65).status_code, 200)
        self.assertEqual(self.client.post("/posts/preview_render", content=b"x" * 129).status_code, 413)
        self.assertEqual(len(self.calls), 1)

    def test_chunked_body_without_content_length_stops_before_handler(self):
        called, output = [], []
        async def app(scope, receive, send):
            called.append(True)
        messages = iter([{"type": "http.request", "body": b"a" * 40, "more_body": True},
                         {"type": "http.request", "body": b"b" * 40, "more_body": False}])
        async def receive():
            return next(messages)
        async def send(value):
            output.append(value)
        middleware = HTTPBoundaryMiddleware(app, "https://app.example.test", body_limit=64)
        asyncio.run(middleware({"type": "http", "method": "POST", "path": "/action",
                               "headers": []}, receive, send))
        self.assertEqual(output[0]["status"], 413)
        self.assertEqual(called, [])


class SourceFetchTests(unittest.TestCase):
    def test_private_addresses_and_unsafe_urls_never_reach_transport(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fd00::1",
                        "::ffff:127.0.0.1", "64:ff9b::7f00:1", "2002:7f00:1::", "224.0.0.1"):
            with patch("socket.getaddrinfo", return_value=[(None, None, None, None, (address, 443))]), \
                 patch("urllib3.HTTPSConnectionPool") as pool:
                with self.assertRaises(ValueError):
                    fetch_public_document("https://source.example.test/")
                pool.assert_not_called()
        for url in ("file:///etc/passwd", "http://example.test", "https://user:pass@example.test",
                    "https://example.test:8443", "https://example.test\\@127.0.0.1", "https://example.test/\n"):
            with patch("socket.getaddrinfo") as dns:
                with self.assertRaises(ValueError):
                    fetch_public_document(url)
                dns.assert_not_called()

    def test_public_connection_is_pinned_and_redirects_and_oversize_are_rejected(self):
        for status, chunks, success in ((200, [b"safe text"], True), (302, [], False), (200, [b"x" * 30], False)):
            response = Mock(status=status, headers={"Content-Type": "text/plain"})
            response.stream.return_value = iter(chunks)
            pool = Mock()
            pool.__enter__ = Mock(return_value=pool)
            pool.__exit__ = Mock(return_value=False)
            pool.urlopen.return_value = response
            with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]) as dns, \
                 patch("urllib3.HTTPSConnectionPool", return_value=pool) as factory:
                if success:
                    self.assertEqual(fetch_public_document("https://source.example.test/article", maximum=20), b"safe text")
                else:
                    with self.assertRaises(ValueError):
                        fetch_public_document("https://source.example.test/article", maximum=20)
                self.assertEqual(dns.call_count, 1)
                self.assertEqual(factory.call_args.args[0], "93.184.216.34")
                self.assertEqual(factory.call_args.kwargs["assert_hostname"], "source.example.test")
                self.assertEqual(factory.call_args.kwargs["cert_reqs"], "CERT_REQUIRED")
                self.assertFalse(pool.urlopen.call_args.kwargs["redirect"])
                response.close.assert_called_once()


class UploadTests(unittest.TestCase):
    def test_disguised_image_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            upload = UploadFile(io.BytesIO(b"<script>alert(1)</script>"), filename="test.jpg")
            with self.assertRaises(HTTPException):
                save_image_upload(upload, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_real_pixels_preserved_but_trailing_payload_and_filename_are_discarded(self):
        image = io.BytesIO()
        Image.new("RGB", (64, 64), (20, 90, 50)).save(image, "PNG")
        payload = image.getvalue() + b"<script>private metadata</script>"
        with tempfile.TemporaryDirectory() as directory:
            name, file = save_image_upload(UploadFile(io.BytesIO(payload), filename="../../escape.png"), directory)
            self.assertEqual(Path(file).parent, Path(directory))
            self.assertTrue(name.endswith(".jpg"))
            self.assertNotIn(b"private metadata", Path(file).read_bytes())
            with Image.open(file) as result:
                self.assertEqual(result.size, (64, 64))
                self.assertEqual(result.format, "JPEG")


class SharedLibraryTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (ContentSource, ContentItem):
            model.__table__.create(self.engine)
        self.db.add_all([Org(id=1, name="Own"), Org(id=2, name="Other"),
                         User(id=1, email="reader@example.test", active_org_id=1)])
        self.db.flush()
        self.db.add(OrgMember(org_id=1, user_id=1))
        self.db.add(ContentSource(id=1, name="Fixture", source_type="manual_library"))
        self.db.flush()
        for id_, org, owner in ((1, None, None), (2, 1, 1), (3, 2, None), (4, 1, 99)):
            self.db.add(ContentItem(id=id_, org_id=org, owner_user_id=owner, source_id=1,
                                    item_type="note", title="Fixture", meta={"reference": "Fixture"},
                                    text="Exact original source"))
        self.db.commit()
        app = FastAPI()
        app.include_router(library.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app, headers={"Authorization": "Bearer " + create_access_token({"sub": "1"})})
        self.addCleanup(self.client.close)

    def test_global_foreign_and_other_creator_sources_cannot_be_changed_or_deleted(self):
        for id_ in (1, 3, 4):
            self.assertEqual(self.client.patch(f"/api/library/entries/{id_}", json={"text": "Forged"}).status_code, 403)
            self.assertEqual(self.client.delete(f"/api/library/entries/{id_}").status_code, 403)
            self.assertEqual(self.db.get(ContentItem, id_).text, "Exact original source")

    def test_owned_edit_and_global_clone_still_work(self):
        response = self.client.patch("/api/library/entries/2", json={"title": "My note"})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post("/api/library/entries/1/clone")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["org_id"], 1)
        self.assertEqual(response.json()["owner_user_id"], 1)
        self.assertEqual(self.db.get(ContentItem, 1).text, "Exact original source")

    def test_private_entries_and_stale_workspace_are_not_readable(self):
        response = self.client.get("/api/library/entries")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({r["id"] for r in response.json()}, {1, 2})
        for id_ in (3, 4):
            self.assertEqual(self.client.get(f"/api/library/entries/{id_}").status_code, 403)
        self.db.query(OrgMember).delete()
        self.db.commit()
        self.assertEqual(self.client.get("/api/library/entries").status_code, 403)


class ConnectionCredentialTests(DatabaseCase):
    def test_new_tokens_are_encrypted_at_rest_and_legacy_rows_still_read(self):
        from sqlalchemy import text
        from app.models import IGAccount
        from app.security.connection_tokens import PREFIX, open_token
        IGAccount.__table__.create(self.engine)
        self.db.add(Org(id=1, name="Fixture"))
        self.db.add(IGAccount(id=1, org_id=1, name="Fixture", ig_user_id="1", access_token="synthetic-only"))
        self.db.commit()
        stored = self.db.execute(text("SELECT access_token FROM ig_accounts WHERE id=1")).scalar_one()
        self.assertTrue(stored.startswith(PREFIX))
        self.assertNotIn("synthetic-only", stored)
        self.assertEqual(open_token(stored), "synthetic-only")
        self.db.expire_all()
        self.assertEqual(self.db.get(IGAccount, 1).access_token, "synthetic-only")
        self.db.execute(text("UPDATE ig_accounts SET access_token='legacy-fixture' WHERE id=1"))
        self.db.commit(); self.db.expire_all()
        self.assertEqual(self.db.get(IGAccount, 1).access_token, "legacy-fixture")
        self.db.get(IGAccount, 1).access_token = ""
        self.db.commit()
        self.assertEqual(self.db.query(IGAccount).filter(IGAccount.access_token != "").count(), 0)

    def test_tampered_envelope_and_wrong_key_never_return_credentials(self):
        from app.config import settings
        from app.security.connection_tokens import open_token, seal_token, PREFIX
        value = seal_token("synthetic-credential")
        self.assertEqual(seal_token(value), value)
        with patch.object(settings, "secret_key", "different-test-key"):
            with self.assertRaises(ValueError):
                open_token(value)
        with self.assertRaises(ValueError):
            open_token(PREFIX + "invalid")

    def test_nested_logs_and_embedded_credentials_are_redacted(self):
        from app.logging_setup import redact_log_value
        value = redact_log_value({"nested": {"access_token": ["do-not-log"]},
                                  "message": "GET https://service.test/?access_token=hidden&x=1 Bearer private",
                                  "url": "postgresql://user:password@host/db"})
        serialized = json.dumps(value)
        for secret in ("do-not-log", "hidden", "private", "user:password"):
            self.assertNotIn(secret, serialized)
