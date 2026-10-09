"""Restore an S3 snapshot into a private, disposable PostgreSQL cluster.

No application import, production DB connection, scheduler or public listener.
Only aggregate validation is retained; the private snapshot and cluster are removed.
Run only with approval to download production data onto this machine.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def run(binary, args, env, **kwargs):
    result = subprocess.run([str(binary / args[0]), *args[1:]], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=300, **kwargs)
    if result.returncode:
        # SQL errors can contain private rows. Never print stderr.
        raise RuntimeError(f"{args[0]} failed; private output withheld")
    return result.stdout


def restore_and_check(snapshot, binary):
    """Accept a dump file, never a database URL. Always stop our own cluster."""
    binary = Path(binary).resolve()
    for name in ("initdb", "pg_ctl", "createdb", "psql"):
        if not (binary / name).is_file():
            raise ValueError("PostgreSQL binaries are incomplete")
    with tempfile.TemporaryDirectory(prefix="sabeel-restore-", dir="/tmp") as directory:
        root = Path(directory)
        os.chmod(root, 0o700)
        env = {"PATH": str(binary) + os.pathsep + os.defpath}
        started = False
        try:
            run(binary, ["initdb", "-D", str(root / "data"), "-U", "postgres", "-A", "trust", "--no-locale", "-E", "UTF8"], env)
            run(binary, ["pg_ctl", "-D", str(root / "data"), "-l", str(root / "server.log"), "-o", f"-k {root} -c listen_addresses=''", "-w", "start"], env)
            started = True
            run(binary, ["createdb", "-h", str(root), "-U", "postgres", "restore_check"], env)
            command = ["psql", "-X", "--set", "ON_ERROR_STOP=1", "-h", str(root), "-U", "postgres", "-d", "restore_check"]
            # Decompression verifies the gzip trailer before SQL is executed.
            with tempfile.TemporaryFile(dir=root) as sql:
                with gzip.open(snapshot, "rb") as compressed:
                    shutil.copyfileobj(compressed, sql)
                sql.seek(0)
                run(binary, command, env, stdin=sql)
            query = """
                SELECT json_build_object(
                    'posts', (SELECT count(*) FROM posts),
                    'sources', (SELECT count(*) FROM content_items),
                    'accounts', (SELECT count(*) FROM ig_accounts),
                    'workspaces', (SELECT count(*) FROM orgs),
                    'orphan_or_mismatched_post_accounts', (SELECT count(*) FROM posts p
                        LEFT JOIN ig_accounts a ON a.id=p.ig_account_id
                        WHERE p.ig_account_id IS NOT NULL AND (a.id IS NULL OR a.org_id<>p.org_id)),
                    'orphan_post_workspaces', (SELECT count(*) FROM posts p
                        LEFT JOIN orgs o ON o.id=p.org_id WHERE o.id IS NULL),
                    'unvalidated_constraints', (SELECT count(*) FROM pg_constraint c
                        JOIN pg_namespace n ON n.oid=c.connamespace
                        WHERE n.nspname='public' AND NOT c.convalidated),
                    'invalid_indexes', (SELECT count(*) FROM pg_index WHERE NOT indisvalid)
                );
            """
            counts = json.loads(run(binary, command + ["-At", "-c", query], env))
            if any(counts[k] for k in ("orphan_or_mismatched_post_accounts", "orphan_post_workspaces", "unvalidated_constraints", "invalid_indexes")):
                raise RuntimeError("Restored database failed integrity checks")
            return counts
        finally:
            # Also stop a server that started just before pg_ctl timed out.
            if started or (root / "data/postmaster.pid").exists():
                run(binary, ["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"], env)


def download_snapshot(config, directory):
    import boto3
    from botocore.config import Config
    required = ("S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET_NAME", "S3_ENDPOINT_URL")
    if not all(config.get(key) for key in required):
        raise ValueError("Required S3 connection settings are missing")
    if not config["S3_ENDPOINT_URL"].startswith("https://"):
        raise ValueError("Backup storage must use HTTPS")
    client = boto3.client("s3", aws_access_key_id=config["S3_ACCESS_KEY"],
                          aws_secret_access_key=config["S3_SECRET_KEY"],
                          endpoint_url=config["S3_ENDPOINT_URL"], region_name=config.get("S3_REGION") or "auto",
                          config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=60,
                                        retries={"max_attempts": 2},
                                        s3={"addressing_style": config.get("S3_ADDRESSING_STYLE") or "auto"}))
    bucket = config["S3_BUCKET_NAME"]
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="database_backups/backup_")
    latest = max((obj for page in pages for obj in page.get("Contents", []) if obj["Key"].endswith(".sql.gz")),
                 key=lambda obj: obj["LastModified"], default=None)
    if latest is None:
        raise RuntimeError("No PostgreSQL snapshots found")
    # One GET binds the returned metadata/checksum to the downloaded bytes.
    response = client.get_object(Bucket=bucket, Key=latest["Key"])
    snapshot = Path(directory) / "snapshot.sql.gz"
    digest = hashlib.sha256()
    size = 0
    try:
        with open(snapshot, "xb", opener=lambda p, f: os.open(p, f, 0o600)) as output:
            for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024):
                size += len(chunk)
                if size > 1024 ** 3:
                    raise RuntimeError("Snapshot exceeds the restore drill size limit")
                digest.update(chunk)
                output.write(chunk)
    finally:
        response["Body"].close()
    expected = response.get("Metadata", {}).get("sha256")
    if size == 0 or size != response["ContentLength"] or (expected and expected != digest.hexdigest()):
        raise RuntimeError("Backup size or checksum mismatch")
    return snapshot, {"snapshot_at": response["LastModified"].isoformat(), "size_bytes": size,
                      "sha256": digest.hexdigest(), "checksum_verified": bool(expected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.env_file.is_symlink() or args.env_file.stat().st_mode & 0o077:
        raise SystemExit("Credential file must be a private regular file (chmod 600)")
    from dotenv import dotenv_values
    config = dotenv_values(args.env_file, interpolate=False)
    # Do not overwrite an existing report or accidentally overwrite credentials.
    with open(args.report, "x", opener=lambda p, f: os.open(p, f, 0o600)) as report:
        result = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "failed"}
        started_at = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="sabeel-snapshot-", dir="/tmp") as directory:
                snapshot, evidence = download_snapshot(config, directory)
                result.update(evidence)
                result["counts"] = restore_and_check(snapshot, args.pg_bin)
            result.update(status="passed", private_copy_removed=True, application_started=False)
        except Exception as error:
            result["error_type"] = type(error).__name__
            # No exception text: provider/SQL errors may contain credentials/data.
        result["elapsed_seconds"] = round(time.monotonic() - started_at, 2)
        json.dump(result, report, indent=2)
    print(json.dumps({"status": result["status"], "report": str(args.report)}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
