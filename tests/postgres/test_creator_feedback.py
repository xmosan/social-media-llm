"""Actual PostgreSQL feedback persistence and private access boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading
import unittest
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine, get_db
from app.models import Base, User, Org, OrgMember, InboundMessage
from app.routes import creator_feedback as feedback
from app.security.auth import create_access_token

ORIGIN = "https://app.sabeelstudio.com"


class CreatorFeedbackChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database == "sabeel_test" and engine.url.query["host"].startswith("/tmp/sabeel-pg-test-")
        Base.metadata.create_all(engine)

    def setUp(self):
        with engine.begin() as c:
            c.execute(text('TRUNCATE ' + ', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables) + ' RESTART IDENTITY CASCADE'))
        self.db = Session(engine, expire_on_commit=False); self.addCleanup(self.db.close)
        self.db.add_all([Org(id=1, name="One"), Org(id=2, name="Two")]); self.db.flush()
        self.db.add_all([User(id=1, email="admin@fixture.test", is_superadmin=True, active_org_id=1),
                         User(id=2, email="creator@fixture.test", name="Fixture", active_org_id=2)])
        self.db.flush(); self.db.add(OrgMember(org_id=2, user_id=2, role="owner")); self.db.commit()
        app = FastAPI(); app.include_router(feedback.router); app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app, base_url=ORIGIN); self.addCleanup(self.client.close)
        self.creator = {"Authorization": "Bearer " + create_access_token({"sub": "2"}), "Origin": ORIGIN}
        self.admin = {"Authorization": "Bearer " + create_access_token({"sub": "1"})}
        self.payload = {"request_id": str(uuid4()), "device": "iPhone Safari", "task": "save", "outcome": "completed",
                        "confidence": "after_edits", "notes": 'Synthetic <script>alert("x")</script> feedback'}

    def test_saved_feedback_retries_once_is_account_bound_and_escaped_in_admin(self):
        first = self.client.post("/api/creator-feedback", json=self.payload, headers=self.creator)
        again = self.client.post("/api/creator-feedback", json=self.payload, headers=self.creator)
        self.assertEqual(first.status_code, 200, first.text); self.assertEqual(again.json(), first.json())
        self.assertEqual(self.db.query(InboundMessage).count(), 1)
        self.assertEqual(self.db.query(InboundMessage).one().email, "creator@fixture.test")
        inbox = self.client.get("/admin/feedback", headers=self.admin)
        self.assertIn("&lt;script&gt;", inbox.text); self.assertNotIn('<script>alert', inbox.text)
        self.assertEqual(inbox.headers["cache-control"], "no-store")
        changed = dict(self.payload, notes="Changed answers")
        self.assertEqual(self.client.post("/api/creator-feedback", json=changed, headers=self.creator).status_code, 409)

    def test_anonymous_creator_foreign_origin_scope_and_spoofed_identity_are_denied(self):
        self.assertEqual(self.client.get("/app/feedback").status_code, 401)
        self.assertEqual(self.client.get("/admin/feedback").status_code, 401)
        self.assertEqual(self.client.get("/admin/feedback", headers=self.creator).status_code, 403)
        self.assertEqual(self.client.post("/api/creator-feedback", json=self.payload, headers={"Origin": ORIGIN}).status_code, 401)
        for headers in (dict(self.creator, Origin="https://foreign.example"), dict(self.creator, **{"X-Org-Id": "1"})):
            self.assertEqual(self.client.post("/api/creator-feedback", json=self.payload, headers=headers).status_code, 403)
        for payload in (dict(self.payload, email="spoof@example.test"), dict(self.payload, notes="x"*3001), dict(self.payload, task="anything")):
            response = self.client.post("/api/creator-feedback", json=payload, headers=self.creator)
            self.assertEqual(response.status_code, 422); self.assertNotIn("spoof@example", response.text)
        self.assertEqual(self.db.query(InboundMessage).count(), 0)

    def test_expired_workspace_is_denied_and_previous_feedback_is_retained(self):
        self.client.post("/api/creator-feedback", json=self.payload, headers=self.creator)
        self.db.get(Org, 2).tester_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); self.db.commit()
        self.assertEqual(self.client.get("/app/feedback", headers=self.creator).status_code, 403)
        self.assertEqual(self.client.post("/api/creator-feedback", json=self.payload, headers=self.creator).status_code, 403)
        self.assertEqual(self.db.query(InboundMessage).count(), 1)

    def test_concurrent_retry_and_limit_use_one_transaction(self):
        barrier = threading.Barrier(2)
        payload = feedback.FeedbackPayload(**self.payload)
        def submit(_):
            with Session(engine) as db:
                user = db.get(User, 2); barrier.wait(timeout=10)
                return feedback.save_feedback(db, user, payload)
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(submit, range(2)))
        self.assertEqual(results[0], results[1]); self.assertEqual(self.db.query(InboundMessage).count(), 1)
        for _ in range(19):
            response = self.client.post("/api/creator-feedback", json=dict(self.payload, request_id=str(uuid4())), headers=self.creator)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/creator-feedback", json=dict(self.payload, request_id=str(uuid4())), headers=self.creator).status_code, 429)
        self.assertEqual(self.client.post("/api/creator-feedback", json=self.payload, headers=self.creator).status_code, 200)
        self.assertEqual(self.db.query(InboundMessage).count(), 20)
