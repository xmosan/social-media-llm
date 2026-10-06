"""Disposable PostgreSQL integration tests. Accepts binaries, never a database URL.

python -B tests/run_postgres_checks.py /path/to/postgres/bin
Creates a private Unix socket, disables TCP, and always stops its own server.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

if sys.argv[1:2] == ["--worker"]:
    if os.environ.get("SABEEL_ISOLATED_SECURITY_TESTS") != "1":
        raise SystemExit("Use the parent runner")
    from run_security_checks import run_worker
    raise SystemExit(run_worker("postgres", os.environ["SABEEL_PG_TEST_SOCKET"]))

if len(sys.argv) != 2:
    raise SystemExit("Supply a PostgreSQL bin directory (not a database URL)")
binary = Path(sys.argv[1]).resolve()
for executable in ("initdb", "pg_ctl", "createdb", "pg_dump", "psql"):
    if not (binary / executable).is_file():
        raise SystemExit("PostgreSQL test binaries are incomplete")

with tempfile.TemporaryDirectory(prefix="sabeel-pg-test-", dir="/tmp") as directory:
    root = Path(directory)
    data = root / "data"
    started = False
    env = {"PATH": str(binary) + os.pathsep + os.defpath, "SABEEL_ISOLATED_SECURITY_TESTS": "1",
           "SECRET_KEY": "isolated-test-key-not-for-production-0001", "ADMIN_API_KEY": "isolated-admin-key",
           "SABEEL_PG_TEST_SOCKET": str(root)}
    try:
        subprocess.run([str(binary / "initdb"), "-D", str(data), "-U", "sabeel_test", "-A", "trust", "--no-locale", "-E", "UTF8"], env=env, check=True, capture_output=True)
        subprocess.run([str(binary / "pg_ctl"), "-D", str(data), "-l", str(root / "server.log"), "-o", f"-k {root} -c listen_addresses=''", "-w", "start"], env=env, check=True, capture_output=True)
        started = True
        subprocess.run([str(binary / "createdb"), "-h", str(root), "-U", "sabeel_test", "sabeel_test"], env=env, check=True, capture_output=True)
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker"], cwd=root, env=env)
    finally:
        if started:
            subprocess.run([str(binary / "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop"], env=env, check=True, capture_output=True)
    raise SystemExit(result.returncode)
