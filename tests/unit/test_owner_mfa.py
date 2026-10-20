"""Owner verification uses disposable accounts; no real credential or provider."""
import json
import time
from unittest.mock import patch, AsyncMock

import jwt
import pyotp
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from app.config import settings
from app.db import get_db
from app.models import User
from app.routes import auth, auth_google, owner_security
from app.security import owner_mfa as mfa
from app.security.auth import create_user_access_token, get_password_hash, require_user
from app.security.http_boundary import HTTPBoundaryMiddleware
from app.security.rbac import require_superadmin
from test_security import DatabaseCase

ORIGIN = "https://app.sabeelstudio.com"


class OwnerMFATests(DatabaseCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "isolated-owner-fixture-password"
        cls.password_hash = get_password_hash(cls.password)

    def setUp(self):
        super().setUp()
        for target, name, value in ((settings, "platform_owner_email", "owner@fixture.test"),):
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)
        for target in (auth, mfa):
            p = patch.object(target, "check_auth_attempt"); p.start(); self.addCleanup(p.stop)
        self.owner = User(id=1, email="owner@fixture.test", password_hash=self.password_hash,
                          is_active=True, is_superadmin=True)
        self.db.add_all([self.owner, User(id=2, email="creator@fixture.test",
                         password_hash=self.password_hash, is_active=True)])
        self.db.commit()
        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: self.db
        for router in (auth.router, owner_security.router, auth_google.router):
            app.include_router(router)
        @app.get("/private")
        def private(user=Depends(require_user)):
            return {"id": user.id}
        @app.post("/admin/action")
        def admin_action(user=Depends(require_superadmin)):
            return {"ok": True}
        app.add_middleware(HTTPBoundaryMiddleware, public_url=ORIGIN)
        self.client = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
        self.addCleanup(self.client.close)
        self.old_token = create_user_access_token(self.owner)

    def login(self, email="owner@fixture.test"):
        return self.client.post("/auth/login", data={"username": email, "password": self.password})

    def enrolled(self):
        self.secret = pyotp.random_base32()
        codes, hashes = mfa._recovery_codes(self.owner.id)
        self.owner.owner_mfa = {"enabled_at": mfa.now(), "secret": mfa._cipher().encrypt(self.secret.encode()).decode(),
                                "last_step": -1, "recovery_hashes": hashes}
        self.db.commit()
        return codes

    def verify(self, code):
        return self.client.post(mfa.PATH + "/verify", json={"code": code})

    def set_access(self, age=0):
        token = create_user_access_token(self.owner, extra={"mfa": "totp", "mfa_at": mfa.now() - age})
        self.client.cookies.clear()
        self.client.cookies.set("access_token", token, domain="app.sabeelstudio.com", path="/")
        return token

    def test_password_login_is_only_a_short_lived_challenge_for_owner(self):
        r = self.login()
        self.assertTrue(r.json()["mfa_required"])
        self.assertNotIn("access_token", r.json())
        self.assertEqual(self.client.get("/private").status_code, 401)
        token = self.client.cookies.get(mfa.COOKIE)
        self.assertEqual(self.client.get("/private", headers={"Authorization": "Bearer " + token}).status_code, 401)
        data = jwt.decode(token, settings.secret_key, algorithms=["HS256"], audience="sabeel-owner-challenge")
        self.assertEqual(data["exp"] - data["iat"], 300)
        self.assertIn("HttpOnly", r.headers["set-cookie"])
        self.assertIn("SameSite=strict", r.headers["set-cookie"])

    def test_complete_enrollment_encrypts_secret_and_revokes_old_sessions(self):
        self.login()
        setup = self.client.post(mfa.PATH + "/enroll", json={})
        self.assertEqual(setup.status_code, 200, setup.text)
        secret = setup.json()["setup_key"]
        self.assertNotIn(secret, json.dumps(self.owner.owner_mfa))
        r = self.verify(pyotp.TOTP(secret).now())
        self.assertEqual(r.status_code, 200, r.text)
        codes = r.json()["recovery_codes"]
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        self.assertNotIn(secret, json.dumps(self.owner.owner_mfa))
        self.assertTrue(all(code not in json.dumps(self.owner.owner_mfa) for code in codes))
        self.assertTrue(mfa.enabled(self.owner))
        self.assertEqual(self.client.get("/private").status_code, 200)
        self.assertEqual(self.client.post("/admin/action").status_code, 200)
        self.assertEqual(self.client.get(mfa.PATH + "/status").json()["mode"], "manage")
        token = self.client.cookies.get("access_token")
        claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        self.assertEqual(claims["exp"] - claims["iat"], 8 * 3600)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/private", headers={"Authorization": "Bearer " + self.old_token}).status_code, 401)

    def test_old_full_session_cannot_start_enrollment(self):
        self.client.cookies.set("access_token", self.old_token)
        self.assertEqual(self.client.post(mfa.PATH + "/enroll", json={}).status_code, 401)
        self.assertEqual(self.client.post(mfa.PATH + "/reauth", json={}).status_code, 401)

    def test_wrong_and_malformed_codes_never_authenticate_or_echo_values(self):
        self.enrolled(); self.login()
        for code in ("not-a-code", "١٢٣٤٥٦", "x" * 80):
            r = self.verify(code)
            self.assertIn(r.status_code, (400, 422))
            self.assertNotIn(code, r.text)
            self.assertEqual(self.client.get("/private").status_code, 401)
        self.assertEqual(self.verify(pyotp.TOTP(self.secret).now()).status_code, 200)

    def test_challenge_is_one_use_and_totp_cannot_be_replayed(self):
        self.enrolled(); self.login()
        challenge = self.client.cookies.get(mfa.COOKIE)
        code = pyotp.TOTP(self.secret).now()
        self.assertEqual(self.verify(code).status_code, 200)
        self.client.cookies.set(mfa.COOKIE, challenge, domain="app.sabeelstudio.com", path=mfa.PATH)
        self.assertEqual(self.verify(code).status_code, 401)
        self.login()
        self.assertEqual(self.verify(code).status_code, 400)

    def test_new_signin_invalidates_the_previous_challenge(self):
        self.enrolled(); self.login()
        old = self.client.cookies.get(mfa.COOKIE)
        self.login()
        self.client.cookies.set(mfa.COOKIE, old, domain="app.sabeelstudio.com", path=mfa.PATH)
        self.assertEqual(self.verify(pyotp.TOTP(self.secret).now()).status_code, 401)

    def test_expired_challenge_and_revoked_account_are_rejected(self):
        self.enrolled(); self.login()
        value = mfa.state(self.owner); value["challenge_expires"] = mfa.now() - 1
        self.owner.owner_mfa = value; self.db.commit()
        self.assertEqual(self.verify(pyotp.TOTP(self.secret).now()).status_code, 401)
        self.login()
        self.owner.is_active = False; self.db.commit()
        self.assertEqual(self.verify(pyotp.TOTP(self.secret).now()).status_code, 401)

    def test_recovery_is_single_use_and_revokes_other_sessions(self):
        codes = self.enrolled()
        other = self.set_access()
        self.login()
        r = self.verify(codes[0])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(mfa.state(self.owner)["recovery_hashes"]), 9)
        self.assertEqual(self.client.get("/private").status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/private", headers={"Authorization": "Bearer " + other}).status_code, 401)
        self.login()
        self.assertEqual(self.verify(codes[0]).status_code, 400)

    def test_mfa_cannot_be_bypassed_with_password_only_signed_tokens(self):
        self.enrolled()
        self.client.cookies.set("access_token", create_user_access_token(self.owner))
        self.assertEqual(self.client.get("/private").status_code, 401)
        self.assertEqual(self.client.post("/admin/action").status_code, 401)

    def test_recent_proof_required_for_admin_changes_and_reauth_restores_it(self):
        self.enrolled(); self.set_access(age=901)
        self.assertEqual(self.client.get("/private").status_code, 200)
        denied = self.client.post("/admin/action")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.headers["x-sabeel-owner-verification"], mfa.PATH)
        self.assertEqual(self.client.post(mfa.PATH + "/reauth", json={}).status_code, 200)
        self.assertEqual(self.verify(pyotp.TOTP(self.secret).now()).status_code, 200)
        self.assertEqual(self.client.post("/admin/action").status_code, 200)

    def test_revoking_sessions_does_not_extend_second_factor_freshness(self):
        self.enrolled(); self.set_access(age=800)
        r = self.client.post(mfa.PATH + "/revoke-sessions", json={})
        self.assertEqual(r.status_code, 200, r.text)
        claims = jwt.decode(self.client.cookies.get("access_token"), settings.secret_key, algorithms=["HS256"])
        self.assertGreaterEqual(mfa.now() - claims["mfa_at"], 800)

    def test_recovery_rotation_requires_a_new_totp_and_invalidates_old_codes(self):
        codes = self.enrolled(); self.set_access()
        self.assertEqual(self.client.post(mfa.PATH + "/recovery", json={"code": codes[0]}).status_code, 400)
        r = self.client.post(mfa.PATH + "/recovery", json={"code": pyotp.TOTP(self.secret).now()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["recovery_codes"]), 10)
        self.login()
        self.assertEqual(self.verify(codes[0]).status_code, 400)

    def test_creator_login_and_profile_are_unchanged(self):
        r = self.login("creator@fixture.test")
        self.assertIn("access_token", r.json())
        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        self.assertNotIn("owner_mfa", self.client.get("/auth/me").text)
        self.assertEqual(self.client.post("/admin/action").status_code, 403)
        self.assertEqual(self.client.post(mfa.PATH + "/reauth", json={}).status_code, 401)

    def test_second_factor_cookie_still_requires_same_origin(self):
        self.enrolled(); self.login()
        for origin in ("https://evil.example", ""):
            r = self.client.post(mfa.PATH + "/verify", json={"code": pyotp.TOTP(self.secret).now()},
                                 headers={"Origin": origin})
            self.assertEqual(r.status_code, 403)

    def test_google_signin_issues_challenge_without_owner_access(self):
        self.enrolled()
        with patch("app.main.is_prod", True, create=True), patch.object(
                auth_google.oauth.google, "authorize_access_token", AsyncMock(return_value={
                    "userinfo": {"sub": "fixture-google", "email": self.owner.email, "email_verified": True}
                })), patch("app.services.usage_limits.check_auth_attempt"):
            r = self.client.get("/auth/google/callback", follow_redirects=False)
        self.assertEqual(r.status_code, 303, r.text)
        self.assertEqual(r.headers["location"], mfa.PATH)
        self.assertEqual(self.client.get("/private").status_code, 401)
        self.assertEqual(self.verify(pyotp.TOTP(self.secret).now()).status_code, 200)

    def test_verification_page_has_strict_policy_and_no_inline_script(self):
        r = self.client.get(mfa.PATH)
        self.assertEqual(r.status_code, 200)
        self.assertIn("script-src 'self'", r.headers["content-security-policy"])
        self.assertNotIn("unsafe-inline", r.headers["content-security-policy"])
        self.assertNotIn("<script>", r.text)
        self.assertEqual(r.headers["cache-control"], "no-store")
