"""MFA races, durable attempt limits and migration in a disposable database."""
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

if os.environ.get("SABEEL_ISOLATED_SECURITY_TESTS") != "1" or not os.environ.get("SABEEL_PG_TEST_SOCKET"):
    raise RuntimeError("Use the isolated PostgreSQL runner")

import pyotp
from fastapi import HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import Base, User
from app.security import owner_mfa as mfa
from scripts.migrate_owner_mfa import migrate


class OwnerMFAPostgresChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)

    def setUp(self):
        with engine.begin() as connection:
            names = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
            connection.execute(text("TRUNCATE " + names + " RESTART IDENTITY CASCADE"))
        p = patch.object(settings, "platform_owner_email", "owner@fixture.test")
        p.start(); self.addCleanup(p.stop)
        self.secret = pyotp.random_base32()
        self.codes, hashes = mfa._recovery_codes(1)
        with Session(engine) as db:
            db.add(User(id=1, email="owner@fixture.test", is_active=True, is_superadmin=True,
                        owner_mfa={"enabled_at": mfa.now(), "last_step": -1,
                                   "secret": mfa._cipher().encrypt(self.secret.encode()).decode(),
                                   "recovery_hashes": hashes}))
            db.commit()

    def challenge(self):
        response = Response()
        with Session(engine) as db:
            mfa.issue_challenge(db, db.get(User, 1), response)
        cookie = next(v for v in response.headers.getlist("set-cookie") if v.startswith(mfa.COOKIE + "="))
        return cookie.split(";", 1)[0]

    def request(self, cookie):
        return Request({"type": "http", "method": "POST", "path": mfa.PATH + "/verify",
                        "headers": [(b"cookie", cookie.encode())]})

    def race(self, code):
        cookie, barrier = self.challenge(), threading.Barrier(2)
        def attempt():
            with Session(engine) as db:
                barrier.wait()
                try:
                    return mfa.finish_verification(self.request(cookie), db, Response(), code)["verified"]
                except HTTPException as error:
                    db.rollback()
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(401), 1)

    def test_simultaneous_totp_verification_accepts_exactly_one_request(self):
        self.race(pyotp.TOTP(self.secret).now())
        with Session(engine) as db:
            self.assertNotIn("challenge_hash", mfa.state(db.get(User, 1)))

    def test_simultaneous_recovery_use_consumes_one_code_and_revokes_sessions_once(self):
        self.race(self.codes[0])
        with Session(engine) as db:
            owner = db.get(User, 1)
            self.assertEqual(owner.session_version, 1)
            self.assertEqual(len(mfa.state(owner)["recovery_hashes"]), 9)

    def test_wrong_codes_share_durable_attempt_budget_across_sessions(self):
        cookie = self.challenge()
        # Freeze only the attempt window to avoid a five-minute clock boundary.
        from app.services import usage_limits
        with Session(engine) as db:
            timestamp = db.execute(text("SELECT clock_timestamp()")).scalar_one()
        with patch.object(usage_limits, "_now", return_value=timestamp), \
                patch.object(settings, "auth_identity_attempts", 3):
            for expected in (400, 400, 400, 429):
                with Session(engine) as db:
                    with self.assertRaises(HTTPException) as raised:
                        mfa.finish_verification(self.request(cookie), db, Response(), "invalid-fixture")
                    self.assertEqual(raised.exception.status_code, expected)
        with Session(engine) as db:
            self.assertEqual(db.get(User, 1).session_version, 0)
            self.assertIn("challenge_hash", mfa.state(db.get(User, 1)))

    def test_migration_is_repeatable_preserves_existing_accounts_and_mfa(self):
        with engine.begin() as connection:
            before = connection.execute(text("SELECT owner_mfa::text FROM users WHERE id=1")).scalar_one()
            migrate(connection); migrate(connection)
            self.assertEqual(connection.execute(text("SELECT owner_mfa::text FROM users WHERE id=1")).scalar_one(), before)
            connection.execute(text("INSERT INTO users (id,email) VALUES (2,'legacy@fixture.test')"))
            self.assertIsNone(connection.execute(text("SELECT owner_mfa FROM users WHERE id=2")).scalar_one())
        # Reproduce an older schema; the migration adds only the nullable field.
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users DROP COLUMN owner_mfa"))
            migrate(connection); migrate(connection)
            self.assertEqual(connection.execute(text("SELECT count(*) FROM users")).scalar_one(), 2)
            self.assertEqual(connection.execute(text("SELECT count(*) FROM users WHERE owner_mfa IS NULL")).scalar_one(), 2)
