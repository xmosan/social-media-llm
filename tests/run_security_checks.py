"""Run only isolated security checks; never import the production application.

Usage: python -B tests/run_security_checks.py
The parent launches a fresh interpreter with no inherited credentials and a
temporary working directory (so Settings cannot discover the repository .env).
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run_worker(suite_directory="unit", postgres_socket=None):
    import socket
    import types
    import unittest
    from contextlib import ExitStack
    from unittest.mock import AsyncMock, Mock, patch

    sys.path.insert(0, str(ROOT))

    def forbidden(*args, **kwargs):
        raise AssertionError("Production database/startup/network access is forbidden in security tests")

    def stub(name, **attributes):
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        sys.modules[name] = module

    # Stub these before importing routes. Real models, auth, RBAC, configuration,
    # bootstrap and route handlers are tested; provider/scheduler calls are mocks.
    stub("app.db", get_db=forbidden, SessionLocal=forbidden, engine=None)
    if postgres_socket is not None:
        from sqlalchemy import create_engine, URL
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(URL.create("postgresql+psycopg", username="sabeel_test", database="sabeel_test", query={"host": postgres_socket}))
        stub("app.db", get_db=forbidden, SessionLocal=sessionmaker(bind=engine), engine=engine)
    stub("app.main", STARTUP_LOG=[])
    stub("app.services.email", send_email=AsyncMock(return_value=True), send_contact_acknowledgment=AsyncMock(return_value=True))
    stub("app.services.caption_engine", generate_islamic_caption=Mock(return_value="Test caption"))
    stub("app.services.scheduler", reload_automation_jobs=Mock(), publish_due_posts=Mock(return_value=0))
    stub("app.services.automation_service", run_automation=Mock(), get_automation_history=Mock(), list_system_presets=Mock())
    stub("app.services.llm", **{name: Mock() for name in (
        "generate_topic_caption", "generate_caption_from_content_item", "generate_ai_image",
        "generate_topic_variations", "generate_draft", "get_client", "generate_card_framing_from_source",
    )})
    stub("app.services.image_renderer", render_quote_card=Mock(), render_minimal_quote_card=Mock())
    stub("app.services.image_card", create_quote_card=Mock(), generate_quote_card=Mock())
    stub("app.services.ingestion", ingest_document=Mock())
    stub("app.services.prebuilt_loader", load_prebuilt_packs=Mock())
    stub("app.services.library_retrieval", retrieve_relevant_chunks=Mock())
    stub("app.services.library_service", create_library_entry=Mock(), validate_entry_meta=Mock(), generate_topics_slugs=Mock(), suggest_library_topics=Mock())
    stub("app.services.hadith_service", get_hadith_by_reference=Mock(return_value={"reference": "test fixture"}))

    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, "connect", forbidden))
        stack.enter_context(patch.object(socket, "create_connection", forbidden))
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests" / suite_directory))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if postgres_socket is not None:
            engine.dispose()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--isolated-worker"]:
        if os.environ.get("SABEEL_ISOLATED_SECURITY_TESTS") != "1":
            raise SystemExit("Run this script without --isolated-worker")
        raise SystemExit(run_worker())

    with tempfile.TemporaryDirectory(prefix="sabeel-security-tests-") as directory:
        result = subprocess.run(
            [sys.executable, "-B", "-I", str(Path(__file__).resolve()), "--isolated-worker"],
            cwd=directory,
            env={
                "PATH": os.defpath,
                "SABEEL_ISOLATED_SECURITY_TESTS": "1",
                "SECRET_KEY": "isolated-test-key-not-for-production-0001",
                "ADMIN_API_KEY": "isolated-admin-key",
            },
            check=False,
        )
    raise SystemExit(result.returncode)
