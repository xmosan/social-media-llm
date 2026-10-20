"""Restricted database login, using only the runner's disposable PostgreSQL."""
import os
import subprocess
import unittest

if os.environ.get("SABEEL_ISOLATED_SECURITY_TESTS") != "1" or not os.environ.get("SABEEL_PG_TEST_SOCKET"):
    raise RuntimeError("Use the isolated PostgreSQL runner")

from sqlalchemy import text, create_engine
from app.db import engine
from app.models import Base
from scripts.provision_runtime_database_role import ROLE, inspect_role, provision


class RuntimeDatabaseRoleChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)

    def test_restricted_role_supports_app_writes_and_complete_dump_without_ddl(self):
        with engine.begin() as connection:
            result = provision(connection, password="synthetic-test-password-only-" + "x" * 40)
            self.assertTrue(result["restricted"])
            self.assertFalse(result["runtime_connection_changed"])
            self.assertFalse(provision(connection)["created"])
            # Future administrator-owned migrations receive the same permissions.
            connection.execute(text("CREATE TABLE public.runtime_permission_fixture (id SERIAL PRIMARY KEY, body TEXT)"))
        runtime = create_engine(engine.url.set(username=ROLE))
        try:
            with runtime.begin() as connection:
                connection.execute(text("INSERT INTO runtime_permission_fixture (body) VALUES ('original')"))
                connection.execute(text("UPDATE runtime_permission_fixture SET body='changed'"))
                self.assertEqual(connection.execute(text("SELECT body FROM runtime_permission_fixture")).scalar_one(), "changed")
                connection.execute(text("DELETE FROM runtime_permission_fixture"))
                connection.execute(text("SELECT pg_advisory_xact_lock(731209, 41)"))
            for statement in (
                "CREATE TABLE public.forbidden_table (id int)",
                "ALTER TABLE public.runtime_permission_fixture ADD COLUMN forbidden int",
                "DROP TABLE public.runtime_permission_fixture",
                "TRUNCATE public.runtime_permission_fixture",
                "CREATE ROLE forbidden_role",
                "SET ROLE sabeel_test",
                "SELECT pg_read_file('/etc/passwd')",
            ):
                with self.subTest(statement=statement), self.assertRaises(Exception):
                    with runtime.begin() as connection:
                        connection.execute(text(statement))
            # Actual pg_dump with the restricted identity, not an administrator
            # connection that merely SET ROLEs. Same flags as production backups.
            dump = subprocess.run([
                "pg_dump", "-h", os.environ["SABEEL_PG_TEST_SOCKET"],
                "-U", ROLE, "-d", "sabeel_test", "--no-password", "--clean",
                "--if-exists", "--no-owner", "--no-privileges",
            ], capture_output=True, timeout=30)
            self.assertEqual(dump.returncode, 0, dump.stderr.decode())
            self.assertIn(b"runtime_permission_fixture", dump.stdout)
            self.assertIn(b"CREATE TABLE public.posts", dump.stdout)
        finally:
            runtime.dispose()
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS public.runtime_permission_fixture"))

    def test_invalid_password_rolls_back_role_creation(self):
        # Role-name patch keeps tests independent of ordering.
        from unittest.mock import patch
        with patch("scripts.provision_runtime_database_role.ROLE", "sabeel_rejected_fixture"):
            with self.assertRaises(ValueError):
                with engine.begin() as connection:
                    provision(connection, password="too-short")
            with engine.connect() as connection:
                self.assertFalse(inspect_role(connection)["exists"])

    def test_unknown_existing_role_is_not_modified(self):
        from unittest.mock import patch
        with engine.begin() as connection:
            connection.execute(text("CREATE ROLE sabeel_unmanaged_fixture NOLOGIN"))
        try:
            with patch("scripts.provision_runtime_database_role.ROLE", "sabeel_unmanaged_fixture"):
                with self.assertRaises(ValueError):
                    with engine.begin() as connection:
                        provision(connection, password="x" * 64)
            with engine.connect() as connection:
                self.assertFalse(connection.execute(text(
                    "SELECT rolcanlogin FROM pg_roles WHERE rolname='sabeel_unmanaged_fixture'"
                )).scalar_one())
        finally:
            with engine.begin() as connection:
                connection.execute(text("DROP ROLE sabeel_unmanaged_fixture"))
