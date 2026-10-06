"""Import and start the real FastAPI app against the disposable PostgreSQL DB."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

if os.environ.get("SABEEL_ISOLATED_SECURITY_TESTS") != "1" or not os.environ.get("SABEEL_PG_TEST_SOCKET"):
    raise RuntimeError("Use tests/run_postgres_checks.py")

from fastapi.testclient import TestClient
from app.config import settings
from app.db import engine
from app.models import Base
from app.services import scheduler

ROOT = Path(__file__).resolve().parents[2]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AppStartupChecks(unittest.TestCase):
    def test_actual_app_startup_health_and_shutdown_without_seeds_or_live_jobs(self):
        assert engine.url.database == "sabeel_test"
        assert engine.url.query["host"] == os.environ["SABEEL_PG_TEST_SOCKET"]
        Base.metadata.create_all(engine)
        url = engine.url.render_as_string(hide_password=False)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DATABASE_URL": url}), patch.object(settings, "uploads_dir", directory), patch.object(settings, "scheduler_enabled", False), patch.object(scheduler, "start_scheduler", Mock(), create=True):
            actual_db = module_at("app.isolated_startup_db", ROOT / "app/db.py")
            try:
                with patch.dict(sys.modules, {"app.db": actual_db}):
                    main = module_at("app.isolated_startup_main", ROOT / "app/main.py")
                    with patch.object(main, "run_admin_library_migration") as migrate, patch.object(main, "run_startup_tasks") as seed, patch.object(main, "start_scheduler") as jobs:
                        with TestClient(main.app) as client:
                            for endpoint in ("/health", "/ready"):
                                response = client.get(endpoint)
                                self.assertEqual(response.status_code, 200, response.text)
                                self.assertEqual(response.json()["database"], "connected")
                                self.assertEqual(response.json()["scheduler"], "disabled")
                            self.assertTrue(main.app.state.ready)
                        self.assertFalse(main.app.state.ready)
                        migrate.assert_not_called()
                        seed.assert_not_called()
                        jobs.assert_not_called()
            finally:
                actual_db.engine.dispose()
