"""Operational failure checks without importing production startup or its DB."""
import ast
import gzip
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_security import ROOT
from app.config import settings, Settings
from app.services import backups
import app.db as isolated_db
from fastapi.responses import JSONResponse
from sqlalchemy.engine import make_url


def load_functions(path, names, namespace):
    tree = ast.parse((ROOT / "app" / path).read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == len(names)
    for node in functions:
        node.decorator_list = []
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class StartupChecks(unittest.TestCase):
    def context(self):
        return load_functions("main.py", {"on_startup", "on_shutdown", "health_check", "readiness_check"}, {
            "__package__": "app", "app": SimpleNamespace(state=SimpleNamespace()),
            "settings": SimpleNamespace(run_startup_migrations=False, scheduler_enabled=True, openai_api_key=None),
            "log_startup": Mock(), "run_admin_library_migration": Mock(), "run_startup_tasks": Mock(),
            "bootstrap_saas": Mock(), "start_scheduler": Mock(), "SessionLocal": Mock(), "engine": Mock(), "JSONResponse": JSONResponse,
        })

    def test_startup_checks_schema_without_migrations_and_shutdown_stops_jobs(self):
        ctx = self.context()
        with patch.object(isolated_db, "validate_database_schema", create=True) as check:
            ctx["on_startup"]()
            check.assert_called_once()
        ctx["run_admin_library_migration"].assert_not_called()
        ctx["run_startup_tasks"].assert_not_called()
        self.assertTrue(ctx["app"].state.ready)
        scheduler = ctx["app"].state.scheduler
        ctx["on_shutdown"]()
        scheduler.shutdown.assert_called_once_with(wait=True)
        self.assertFalse(ctx["app"].state.ready)

    def test_schema_failure_prevents_bootstrap_and_scheduler(self):
        ctx = self.context()
        with patch.object(isolated_db, "validate_database_schema", side_effect=RuntimeError("Missing schema"), create=True):
            with self.assertRaises(RuntimeError):
                ctx["on_startup"]()
        self.assertFalse(ctx["app"].state.ready)
        ctx["start_scheduler"].assert_not_called()
        ctx["bootstrap_saas"].assert_not_called()

    def test_health_returns_503_without_exposing_database_error(self):
        ctx = self.context()
        ctx["app"].state.ready = True
        ctx["app"].state.scheduler = SimpleNamespace(running=True)
        ctx["engine"].connect.side_effect = RuntimeError("sensitive fixture connection string")
        result = ctx["health_check"]()
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(b"sensitive", result.body)
        ctx["engine"].connect = Mock()
        ctx["engine"].connect.return_value = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        self.assertEqual(ctx["health_check"]().status_code, 200)
        ctx["app"].state.scheduler.running = False
        self.assertEqual(ctx["readiness_check"]().status_code, 503)

    def test_legacy_schema_changes_require_explicit_opt_in(self):
        self.assertFalse(Settings(_env_file=None).run_startup_migrations)
        ctx = self.context()
        ctx["settings"].run_startup_migrations = True
        with patch.object(isolated_db, "validate_database_schema", create=True):
            ctx["on_startup"]()
        ctx["run_admin_library_migration"].assert_called_once()
        ctx["run_startup_tasks"].assert_called_once()

    def test_connection_failure_redacts_credentials_and_enforces_postgres(self):
        from sqlalchemy import text
        engine = Mock()
        engine.connect.side_effect = RuntimeError("fake-secret-pw")
        ctx = load_functions("db.py", {"_create_engine_with_retries"}, {"make_url": make_url, "create_engine": Mock(return_value=engine), "text": text, "time": Mock(), "logger": logging.getLogger("isolated-db-test")})
        for url in ("sqlite:///postgresql.db", "not-a-url-fake-secret-pw"):
            with self.assertRaises(ValueError) as error:
                ctx["_create_engine_with_retries"](url)
            self.assertNotIn("fake-secret", str(error.exception))
        with self.assertRaises(RuntimeError) as error:
            ctx["_create_engine_with_retries"]("postgresql://fixture:fake-secret-pw@localhost/test")
        self.assertNotIn("fake-secret", str(error.exception))
        self.assertTrue(ctx["create_engine"].call_args.kwargs["hide_parameters"])
        engine.dispose.assert_called_once()


class BackupChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for target, name, value in ((backups, "BACKUPS_DIR", self.directory.name),
                                    (settings, "database_url", "postgresql+psycopg://fixture:fake-private-pw@localhost/fixture?sslmode=require"),
                                    (settings, "backup_storage_type", "local")):
            manager = patch.object(target, name, value)
            manager.start()
            self.addCleanup(manager.stop)

    def dump(self, args, **kwargs):
        self.assertNotIn("fake-private-pw", " ".join(args))
        self.assertEqual(kwargs["env"]["PGPASSWORD"], "fake-private-pw")
        self.assertIn("sslmode=require", args[2])
        self.assertEqual(kwargs["timeout"], 300)
        kwargs["stdout"].write(b"-- Synthetic database dump\nSELECT 1;\n")
        return SimpleNamespace(returncode=0)

    def test_backup_has_real_bytes_private_permissions_and_explicit_local_durability(self):
        with patch.object(backups.subprocess, "run", side_effect=self.dump):
            result = backups.backup_postgres_database()
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["durable"])
        file = Path(self.directory.name) / result["file"]
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertIn(b"Synthetic", gzip.decompress(file.read_bytes()))

    def test_remote_upload_failure_is_error_and_never_runs_retention(self):
        with patch.object(settings, "backup_storage_type", "s3"), patch.object(backups.subprocess, "run", side_effect=self.dump), patch.object(backups, "_s3_upload", return_value=False), patch.object(backups, "_s3_cleanup_old_backups") as clean, patch.object(backups, "_local_cleanup_old_backups") as local:
            result = backups.backup_postgres_database()
        self.assertEqual(result["status"], "error")
        self.assertTrue((Path(self.directory.name) / result["file"]).exists())
        clean.assert_not_called()
        local.assert_not_called()

    def test_missing_dump_timeout_and_nonpostgres_never_report_success(self):
        for failure in (FileNotFoundError, subprocess.TimeoutExpired("pg_dump", 300)):
            with patch.object(backups.subprocess, "run", side_effect=failure):
                self.assertEqual(backups.backup_postgres_database()["status"], "error")
        with patch.object(settings, "database_url", "sqlite:///fixture.db"), patch.object(backups.subprocess, "run") as dump:
            self.assertEqual(backups.backup_postgres_database()["status"], "error")
            dump.assert_not_called()
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_admin_backup_routes_share_real_dump_and_return_error_status(self):
        from app.routes import admin_backup, admin
        from fastapi import HTTPException
        with patch.object(backups, "backup_postgres_database", return_value={"status": "error", "detail": "Fixture failure"}) as dump:
            for endpoint in (admin_backup.create_postgres_backup, admin.trigger_manual_backup):
                with self.assertRaises(HTTPException) as error:
                    endpoint()
                self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(dump.call_count, 2)
        result = {"status": "success", "file": "backup_fixture.sql.gz", "durable": False, "storage": "local"}
        with patch.object(backups, "backup_postgres_database", return_value=result):
            self.assertEqual(admin_backup.create_postgres_backup()["backup_file"], result["file"])

    def test_admin_download_returns_real_dump_and_preserves_legacy_export_access(self):
        from app.routes import admin_backup
        legacy = Path(self.directory.name) / "pg_backup_fixture.json.gz"
        legacy.write_bytes(b"fixture")
        self.assertEqual(Path(admin_backup.download_latest_backup().path), legacy)
        legacy.unlink()
        dump = Path(self.directory.name) / "backup_fixture.sql.gz"
        dump.write_bytes(b"fixture")
        response = admin_backup.download_latest_backup()
        self.assertEqual(Path(response.path), dump)
        self.assertEqual(response.headers["cache-control"], "no-store")
