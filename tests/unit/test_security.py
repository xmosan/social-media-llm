from app.config import settings
from unittest.mock import patch
"""Security regression tests with disposable records and mocked external work."""

import ast
import hashlib
import os
from pathlib import Path
import sys
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

# Refuse normal collection before importing app modules or settings.
if os.environ.get("SABEEL_ISOLATED_SECURITY_TESTS") != "1" or "app.db" not in sys.modules:
    raise RuntimeError("Use python -B tests/run_security_checks.py for safe, isolated execution")

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, settings
from app.db import get_db
from app.models import ApiKey, Org, OrgMember, User, WaitlistEntry
from app.security.auth import create_access_token, require_user, verify_password
from app.security.rbac import get_current_org_id, require_superadmin
from app.services.bootstrap import bootstrap_saas
from app.api.routes import waitlist
from app.routes import automations, library, public, studio
from app.services import email, scheduler

ROOT = Path(__file__).resolve().parents[2]
KEY = "isolated-test-signing-key-00000000001"


class SettingsTests(unittest.TestCase):
    def test_missing_or_weak_signing_key_is_rejected_without_echoing_input(self):
        for value in (None, "", "short-private-value", " " * 40):
            with self.subTest(value=value), patch.dict(os.environ, {}, clear=True):
                values = {} if value is None else {"SECRET_KEY": value}
                with self.assertRaises(ValidationError) as caught:
                    Settings(_env_file=None, **values)
                if value and value.strip():
                    self.assertNotIn(value, str(caught.exception))

    def test_legacy_jwt_secret_and_secret_key_precedence(self):
        with patch.dict(os.environ, {"JWT_SECRET": KEY}, clear=True):
            self.assertEqual(Settings(_env_file=None).secret_key, KEY)
            os.environ["SECRET_KEY"] = KEY + "preferred"
            self.assertEqual(Settings(_env_file=None).secret_key, KEY + "preferred")

    def test_bootstrap_disabled_by_default(self):
        self.assertFalse(Settings(_env_file=None).bootstrap_superadmin)

    def test_bootstrap_opt_in_is_read_from_environment(self):
        with patch.dict(os.environ, {"BOOTSTRAP_SUPERADMIN": "true", "SUPERADMIN_EMAIL": "admin@example.test",
                                     "SUPERADMIN_PASSWORD": "long-test-password-only"}):
            self.assertTrue(Settings(_env_file=None).bootstrap_superadmin)

    def test_bootstrap_requires_explicit_credentials(self):
        for overrides in ({}, {"superadmin_email": "admin@example.test"},
                          {"superadmin_email": " ", "superadmin_password": "a-long-test-password"},
                          {"superadmin_email": "admin@example.test", "superadmin_password": "short"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                Settings(_env_file=None, bootstrap_superadmin=True, **overrides)


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        # SQLite is an explicit, in-memory unit-test fixture for these five tables.
        # It does not exercise PostgreSQL migrations or the application's DB module.
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        for model in (Org, User, OrgMember, ApiKey, WaitlistEntry):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)


class BootstrapTests(DatabaseCase):
    def config(self):
        return Settings(_env_file=None, bootstrap_superadmin=True,
                        superadmin_email="Admin@Example.test", superadmin_password="long-test-password-only")

    def test_disabled_bootstrap_does_not_touch_database(self):
        db = Mock()
        bootstrap_saas(db, Settings(_env_file=None))
        self.assertEqual(db.mock_calls, [])

    def test_create_once_without_default_api_key(self):
        config = self.config()
        bootstrap_saas(self.db, config)
        admin = self.db.query(User).one()
        original_hash = admin.password_hash
        self.assertTrue(admin.is_active and admin.is_superadmin)
        self.assertEqual(admin.email, "admin@example.test")
        self.assertTrue(verify_password(config.superadmin_password, original_hash))
        self.assertEqual(self.db.query(OrgMember).one().user_id, admin.id)
        self.assertEqual(self.db.query(ApiKey).count(), 0)
        bootstrap_saas(self.db, config)
        self.assertEqual(self.db.query(User).count(), 1)
        self.assertEqual(self.db.query(Org).count(), 1)
        self.assertEqual(self.db.query(OrgMember).count(), 1)
        self.assertEqual(admin.password_hash, original_hash)

    def test_existing_account_is_not_promoted_reactivated_or_reset(self):
        account = User(email="admin@example.test", password_hash="unchanged", is_active=False, is_superadmin=False)
        self.db.add(account)
        self.db.commit()
        bootstrap_saas(self.db, self.config())
        self.db.refresh(account)
        self.assertFalse(account.is_active)
        self.assertFalse(account.is_superadmin)
        self.assertEqual(account.password_hash, "unchanged")
        self.assertEqual(self.db.query(Org).count(), 0)


class AccessTests(DatabaseCase):
    def setUp(self):
        owner = patch.object(settings, "platform_owner_email", "admin@example.test")
        owner.start(); self.addCleanup(owner.stop)
        super().setUp()
        self.db.add_all([Org(id=1, name="First"), Org(id=2, name="Second"), Org(id=3, name="Empty")])
        self.admin = User(id=1, email="admin@example.test", is_active=True, is_superadmin=True, active_org_id=1)
        self.member = User(id=2, email="member@example.test", is_active=True, is_superadmin=False, active_org_id=1)
        self.disabled = User(id=3, email="disabled@example.test", is_active=False, is_superadmin=False, active_org_id=1)
        self.db.add_all([self.admin, self.member, self.disabled])
        self.db.add_all([OrgMember(org_id=1, user_id=1), OrgMember(org_id=1, user_id=2)])
        for name, org, revoked in [("first-key", 1, None), ("empty-key", 3, None), ("revoked-key", 1, datetime.now(timezone.utc))]:
            self.db.add(ApiKey(org_id=org, name=name, key_hash=hashlib.sha256(name.encode()).hexdigest(), revoked_at=revoked))
        self.db.add(WaitlistEntry(email="synthetic@example.test", source="test", wants_updates=True))
        self.db.commit()

        self.app = FastAPI()
        self.app.dependency_overrides[get_db] = lambda: self.db

        @self.app.get("/whoami")
        def whoami(user=Depends(require_user)):
            return {"id": user.id}

        @self.app.get("/tenant")
        def tenant(org_id=Depends(get_current_org_id)):
            return {"org_id": org_id}

        @self.app.get("/platform")
        def platform(user=Depends(require_superadmin)):
            return {"id": user.id}

        for router in (waitlist.router, studio.router, automations.router, library.router, public.router):
            self.app.include_router(router)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        scheduler.publish_due_posts.reset_mock()
        email.send_email.reset_mock()

    def headers(self, user_id=2):
        return {"Authorization": "Bearer " + create_access_token({"sub": str(user_id)})}

    def test_cookie_and_bearer_login_work(self):
        self.assertEqual(self.client.get("/whoami", headers=self.headers()).json(), {"id": 2})
        self.client.cookies.set("access_token", create_access_token({"sub": "1"}))
        self.assertEqual(self.client.get("/whoami").json(), {"id": 1})

    def test_organization_key_cannot_impersonate_admin_or_user(self):
        for key, org in [("first-key", 1), ("empty-key", 3)]:
            headers = {"X-API-Key": key}
            with self.subTest(key=key):
                self.assertEqual(self.client.get("/tenant", headers=headers).json(), {"org_id": org})
                for path in ("/whoami", "/platform", "/api/waitlist/all"):
                    self.assertEqual(self.client.get(path, headers=headers).status_code, 401)
                self.assertEqual(self.client.get("/tenant", headers={**headers, "X-Org-Id": "2"}).status_code, 403)

    def test_revoked_and_unknown_api_keys_rejected(self):
        for key in ("revoked-key", "unknown-key"):
            self.assertEqual(self.client.get("/tenant", headers={"X-API-Key": key}).status_code, 401)

    def test_retired_default_key_is_rejected_even_if_still_configured(self):
        # Historical public fallback, not a live credential.
        retired_key = "SaaS_Secret_123"
        self.db.add(ApiKey(org_id=1, name="Old default", key_hash=hashlib.sha256(retired_key.encode()).hexdigest()))
        self.db.commit()
        headers = {"X-API-Key": retired_key}
        self.assertEqual(self.client.get("/tenant", headers=headers).status_code, 401)
        with patch.object(settings, "admin_api_key", retired_key):
            self.assertEqual(self.client.get("/platform", headers=headers).status_code, 401)

    def test_shared_admin_key_cannot_impersonate_owner(self):
        headers = {"X-API-Key": settings.admin_api_key}
        self.assertEqual(self.client.get("/platform", headers=headers).status_code, 401)
        self.admin.is_active = False
        self.db.commit()
        self.assertEqual(self.client.get("/platform", headers=headers).status_code, 401)

    def test_expired_malformed_and_disabled_user_tokens_fail_closed(self):
        tokens = ["invalid", create_access_token({"sub": "2"}, timedelta(seconds=-1)), create_access_token({"sub": "3"})]
        for subject in (None, "not-a-number", "0", "-1", "2147483648", "9" * 5000, "٢", 2):
            tokens.append(jwt.encode({"sub": subject, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, settings.secret_key, algorithm="HS256"))
        for token in tokens:
            with self.subTest(token_length=len(token)):
                headers = {"Authorization": "Bearer " + token, "X-API-Key": "first-key"}
                self.assertEqual(self.client.get("/whoami", headers=headers).status_code, 401)
                self.assertEqual(self.client.get("/tenant", headers=headers).status_code, 401)

    def test_foreign_or_stale_active_org_is_rejected(self):
        self.assertEqual(self.client.get("/tenant", headers=self.headers()).json(), {"org_id": 1})
        self.assertEqual(self.client.get("/tenant", headers={**self.headers(), "X-Org-Id": "2"}).status_code, 403)
        self.member.active_org_id = 2
        self.db.commit()
        self.assertEqual(self.client.get("/tenant", headers=self.headers()).status_code, 403)
        self.assertEqual(self.client.get("/tenant", headers={**self.headers(), "X-Org-Id": "1"}).json(), {"org_id": 1})
        self.assertEqual(self.member.active_org_id, 1)

    def test_invalid_org_header_fails_instead_of_silently_falling_back(self):
        for value in ("invalid", "0", "-1", "2147483648"):
            self.assertEqual(self.client.get("/tenant", headers={**self.headers(), "X-Org-Id": value}).status_code, 400)

    def test_membership_fallback_and_explicit_superadmin_scope(self):
        self.member.active_org_id = None
        self.db.commit()
        self.assertEqual(self.client.get("/tenant", headers=self.headers()).json(), {"org_id": 1})
        self.assertEqual(self.client.get("/tenant", headers={**self.headers(1), "X-Org-Id": "2"}).json(), {"org_id": 2})

    def test_waitlist_reads_require_superadmin_and_work_for_admin(self):
        for path in ("/api/waitlist/all", "/api/waitlist/export", "/api/waitlist/stats"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
                self.assertEqual(self.client.get(path, headers=self.headers()).status_code, 403)
                self.assertEqual(self.client.get(path, headers=self.headers(1)).status_code, 200)
        data = self.client.get("/api/waitlist/all", headers=self.headers(1)).json()
        self.assertEqual(data["items"][0]["email"], "synthetic@example.test")

    def test_public_waitlist_join_remains_available_with_email_mocked(self):
        response = self.client.post("/api/waitlist/join", json={"email": "new@example.com", "source": "test"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])
        email.send_email.assert_awaited_once()

    def test_generation_denies_anonymous_and_calls_services_for_member(self):
        from app.services.visual_service import VisualResult
        for path, target, result in [
            ("generate-card-message", "build_quote_card_message", {"headline": "Test card"}),
            ("generate-caption", "generate_islamic_caption", "Test caption"),
            ("generate-visual", "generate_visual", VisualResult(url="https://example.test/test.jpg")),
        ]:
            with self.subTest(path=path), patch.object(studio, target, return_value=result) as provider:
                url = "/api/studio/" + path
                self.assertEqual(self.client.post(url, json={}).status_code, 401)
                provider.assert_not_called()
                self.assertEqual(self.client.post(url, json={}, headers=self.headers()).status_code, 200)
                provider.assert_called_once()

    def test_global_scheduler_requires_admin_and_never_runs_for_other_credentials(self):
        path = "/automations/run-scheduler-now"
        for headers, status in [({}, 401), (self.headers(), 403), ({"X-API-Key": "first-key"}, 401)]:
            self.assertEqual(self.client.post(path, headers=headers).status_code, status)
            scheduler.publish_due_posts.assert_not_called()
        self.assertEqual(self.client.post(path, headers=self.headers(1)).status_code, 200)
        scheduler.publish_due_posts.assert_called_once()

    def test_debug_endpoints_are_not_public_or_member_accessible(self):
        for path in ("/admin", "/api/auth-debug", "/api/debug-automations", "/api/library/hadith/test-public"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
                self.assertEqual(self.client.get(path, headers=self.headers()).status_code, 403)
        self.assertEqual(self.client.get("/api/auth-debug", headers=self.headers(1)).status_code, 200)


class StartupWiringTests(unittest.TestCase):
    """Wiring checks plus a guarded startup rejection; no production startup."""

    def test_missing_signing_key_stops_startup_before_database_import(self):
        code = f"""
import importlib.abc
import sys
from pydantic import ValidationError
sys.path.insert(0, {str(ROOT)!r})
class BlockDatabase(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'app.db':
            raise AssertionError('Database import attempted before signing-key validation')
sys.meta_path.insert(0, BlockDatabase())
try:
    import app.main
except ValidationError:
    assert 'app.db' not in sys.modules
else:
    raise AssertionError('Startup accepted a missing signing key')
"""
        result = subprocess.run([sys.executable, "-B", "-I", "-c", code],
                                env={"PATH": os.defpath}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_generation_aliases_declare_auth_dependency(self):
        tree = ast.parse((ROOT / "app" / "main.py").read_text())
        expected = {"/api/quote-card/build-message", "/api/caption/generate", "/generate-caption", "/generate-quote-card"}
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                        path = decorator.args[0].value
                        if path in expected:
                            dependencies = next(kw.value for kw in decorator.keywords if kw.arg == "dependencies")
                            self.assertIn("Depends(require_user)", ast.unparse(dependencies))
                            seen.add(path)
        self.assertEqual(seen, expected)

    def test_config_validates_before_database_import_and_sessions_use_same_key(self):
        source = (ROOT / "app" / "main.py").read_text()
        self.assertLess(source.index("from .config import settings"), source.index("from .db import"))
        self.assertIn("secret_key=settings.secret_key", source)
        self.assertNotIn("eff_secret_key", source)
