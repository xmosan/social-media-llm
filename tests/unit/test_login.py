"""Login privacy and session recovery, using only disposable accounts."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_security import DatabaseCase
from app.db import get_db
from app.models import Org, OrgMember, User
from app.routes import auth
from app.security.auth import get_password_hash


class LoginTests(DatabaseCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "isolated-login-fixture-password"
        cls.password_hash = get_password_hash(cls.password)

    def setUp(self):
        super().setUp()
        throttle = patch.object(auth, "check_auth_attempt")
        throttle.start(); self.addCleanup(throttle.stop)
        self.db.add(Org(id=1, name="Fixture workspace"))
        self.db.add_all([
            User(id=1, email="member@example.test", password_hash=self.password_hash, is_active=True),
            User(id=2, email="disabled@example.test", password_hash=self.password_hash, is_active=False),
            User(id=3, email="oauth@example.test", password_hash=None, is_active=True),
            User(id=4, email="malformed@example.test", password_hash="invalid-hash", is_active=True),
        ])
        self.db.add(OrgMember(org_id=1, user_id=1))
        self.db.commit()
        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(auth.router)
        self.client = TestClient(app, base_url="https://testserver")
        self.addCleanup(self.client.close)

    def submit(self, username, password):
        return self.client.post("/auth/login", data={"username": username, "password": password})

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Incorrect email or password"})
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertNotIn("set-cookie", response.headers)

    def test_unknown_account_and_bad_password_do_not_disclose_accounts(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output), patch.object(auth, "create_user_access_token") as issue:
            self.assert_rejected(self.submit("missing@example.test", self.password))
            self.assert_rejected(self.submit("member@example.test", "wrong-password"))
        self.assertEqual(output.getvalue(), "")
        issue.assert_not_called()

    def test_disabled_passwordless_and_malformed_accounts_fail_without_a_session(self):
        with patch.object(auth, "create_user_access_token") as issue:
            for email in ("disabled@example.test", "oauth@example.test", "malformed@example.test"):
                with self.subTest(email=email):
                    self.assert_rejected(self.submit(email, self.password))
        issue.assert_not_called()
        self.assertIsNone(self.db.get(User, 2).active_org_id)

    def test_login_preserves_normalization_workspace_and_secure_cookie(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            response = self.submit(" MEMBER@Example.test ", self.password)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(output.getvalue(), "")
        for attribute in ("HttpOnly", "Secure", "SameSite=lax"):
            self.assertIn(attribute, response.headers["set-cookie"])
        self.assertEqual(self.db.get(User, 1).active_org_id, 1)
        profile = self.client.get("/auth/me")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["id"], 1)

    def test_signing_in_replaces_a_stale_session(self):
        self.client.cookies.set("access_token", "expired-session-fixture", domain="testserver.local", path="/")
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.submit("member@example.test", self.password).status_code, 200)
        self.assertEqual(self.client.get("/auth/me").status_code, 200)

    def test_logout_clears_legacy_google_domain_and_current_host_cookies(self):
        response=self.client.post('/auth/logout')
        cookies=response.headers.get_list('set-cookie')
        self.assertEqual(len(cookies),2)
        self.assertTrue(any('Domain=app.sabeelstudio.com' in value for value in cookies))
        self.assertTrue(any('Domain=' not in value for value in cookies))
        self.assertTrue(all('Max-Age=0' in value for value in cookies))
