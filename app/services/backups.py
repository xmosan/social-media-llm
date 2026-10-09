# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import subprocess
import gzip
import shutil
import glob
import tempfile
import hashlib
import threading
from uuid import uuid4
from sqlalchemy.engine import make_url
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from datetime import datetime, timezone
import logging
from ..config import settings

try:
    import boto3
    from botocore.config import Config
    _BOTO3_AVAILABLE = True
except ImportError:
    boto3 = None
    _BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)

BACKUPS_DIR = os.path.join(os.getcwd(), "backups")
MAX_RETAINED_BACKUPS = 14
MAX_BACKUP_AGE_HOURS = 26
_backup_lock = threading.Lock()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_backup_status(*, now=None):
    """Read durable snapshot metadata. Freshness is not proof of restoration."""
    if settings.backup_storage_type.lower() != "s3":
        return {"status": "not_configured", "restore_verified": False}
    try:
        client = _get_s3_client()
        if client is None:
            return {"status": "not_configured", "restore_verified": False}
        pages = client.get_paginator("list_objects_v2").paginate(
            Bucket=settings.s3_bucket_name, Prefix="database_backups/backup_")
        latest = max((obj for page in pages for obj in page.get("Contents", [])
                      if obj["Key"].endswith(".sql.gz")),
                     key=lambda obj: obj["LastModified"], default=None)
        if latest is None:
            return {"status": "missing", "restore_verified": False}
        head = client.head_object(Bucket=settings.s3_bucket_name, Key=latest["Key"])
        modified = head["LastModified"]
        age = ((now or datetime.now(timezone.utc)) - modified).total_seconds() / 3600
        size = head["ContentLength"]
        return {"status": "invalid" if size <= 0 or age < -0.1 else (
                    "fresh" if age <= MAX_BACKUP_AGE_HOURS else "stale"),
                "latest_at": modified.isoformat(), "age_hours": round(age, 2),
                "size_bytes": size, "checksum_recorded": bool(head.get("Metadata", {}).get("sha256")),
                "restore_verified": False}
    except Exception:
        logger.error("backup_storage_unavailable")
        return {"status": "unavailable", "restore_verified": False}


def scheduled_database_backup():
    """Make scheduler failure reporting reflect the actual durable result."""
    result = backup_postgres_database()
    if result.get("status") != "success" or not result.get("durable"):
        logger.error("backup_job_failed", extra={"event": "backup_job_failed"})
        raise RuntimeError("Durable database backup failed; inspect backup storage configuration")
    logger.info("backup_job_succeeded", extra={"event": "backup_job_succeeded"})
    return result


def ensure_recent_backup():
    """Catch a missed daily snapshot after a restart; do not dump every hour."""
    status = remote_backup_status()
    logger.log(logging.INFO if status["status"] == "fresh" else logging.WARNING,
               "backup_freshness", extra={"event": "backup_freshness", **status})
    if status["status"] == "fresh":
        return status
    if status["status"] in {"missing", "stale", "invalid"}:
        return scheduled_database_backup()
    raise RuntimeError("Durable backup freshness could not be checked")

def _ensure_backup_dir():
    os.makedirs(BACKUPS_DIR, mode=0o700, exist_ok=True)
    os.chmod(BACKUPS_DIR, 0o700)

def _get_s3_client():
    if not _BOTO3_AVAILABLE or not boto3:
        logger.debug("[BACKUP] boto3 not installed — S3 backup unavailable.")
        return None
    if not settings.s3_access_key or not settings.s3_secret_key or not settings.s3_bucket_name:
        return None
    # Keep compatibility with older installs that put an endpoint in S3_REGION.
    legacy_endpoint = settings.s3_region if (settings.s3_region or "").startswith(("https://", "http://")) else None
    endpoint = settings.s3_endpoint_url or legacy_endpoint
    region = None if legacy_endpoint else settings.s3_region
    
    return boto3.client(
        's3',
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=region,
        endpoint_url=endpoint,
        config=Config(signature_version="s3v4", s3={"addressing_style": settings.s3_addressing_style},
                      connect_timeout=10, read_timeout=60, retries={"max_attempts": 3, "mode": "standard"}),
    )

def _s3_upload(file_path: str, object_name: str):
    try:
        s3 = _get_s3_client()
        if not s3:
            return False
        checksum = file_sha256(file_path)
        s3.upload_file(file_path, settings.s3_bucket_name, object_name,
                       ExtraArgs={"Metadata": {"sha256": checksum}})
        stored = s3.head_object(Bucket=settings.s3_bucket_name, Key=object_name)
        return (stored.get("ContentLength") == os.path.getsize(file_path)
                and stored.get("Metadata", {}).get("sha256") == checksum)
    except Exception:
        logger.error("S3 backup upload failed")
        return False

def _s3_cleanup_old_backups():
    try:
        s3 = _get_s3_client()
        if not s3:
            return
        pages = s3.get_paginator("list_objects_v2").paginate(Bucket=settings.s3_bucket_name, Prefix="database_backups/")
        objects = sorted((obj for page in pages for obj in page.get("Contents", [])
                          if obj["Key"].startswith("database_backups/backup_") and obj["Key"].endswith(".sql.gz")),
                         key=lambda x: x["LastModified"], reverse=True)
        to_delete = objects[MAX_RETAINED_BACKUPS:]
        
        # S3 DeleteObjects accepts at most 1,000 keys per request.
        for offset in range(0, len(to_delete), 1000):
            delete_keys = [{'Key': obj['Key']} for obj in to_delete[offset:offset + 1000]]
            response = s3.delete_objects(
                Bucket=settings.s3_bucket_name,
                Delete={'Objects': delete_keys}
            )
            if response.get("Errors"):
                logger.error("backup_retention_failed", extra={"event": "backup_retention_failed"})
    except Exception:
        logger.error("backup_retention_failed", extra={"event": "backup_retention_failed"})

def _local_cleanup_old_backups():
    files = glob.glob(os.path.join(BACKUPS_DIR, "backup_*.sql.gz"))
    files.sort(key=os.path.getmtime, reverse=True)
    
    for f in files[MAX_RETAINED_BACKUPS:]:
        try:
            os.remove(f)
        except Exception as e:
            logger.error(f"Local cleanup failed for {f}: {e}")

def backup_postgres_database() -> dict:
    """A real pg_dump snapshot; report remote upload failure and local durability."""
    if not _backup_lock.acquire(blocking=False):
        return {"status": "error", "detail": "A database backup is already running", "durable": False}
    try:
        return _backup_postgres_database()
    finally:
        _backup_lock.release()


def _backup_postgres_database() -> dict:
    local_path = None
    try:
        url = make_url(settings.database_url)
        if url.get_backend_name() not in {"postgres", "postgresql"}:
            raise ValueError("PostgreSQL is required for backups")
        storage = settings.backup_storage_type.lower()
        if storage not in {"local", "s3"}:
            raise ValueError("Unsupported backup storage type")
        # libpq handles escaped passwords and SSL/query parameters. Passwords
        # stay in the child environment, never command arguments or error logs.
        connection = conninfo_to_dict(url.set(drivername="postgresql").render_as_string(hide_password=False))
        password = connection.pop("password", None)
        env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        if password is not None:
            env["PGPASSWORD"] = password
        env["PGCONNECT_TIMEOUT"] = "10"
        dsn = make_conninfo(**connection)
        _ensure_backup_dir()
        timestamp = datetime.now(timezone.utc).strftime("%Y_%m_%d_%H%M%S")
        filename = f"backup_{timestamp}_{uuid4().hex}.sql.gz"
        local_path = os.path.join(BACKUPS_DIR, filename)
        with tempfile.TemporaryFile(dir=BACKUPS_DIR) as raw:
            result = subprocess.run(
                ["pg_dump", "--dbname", dsn, "--no-password", "--clean", "--if-exists", "--no-owner", "--no-privileges"],
                env=env, stdout=raw, stderr=subprocess.PIPE, timeout=300, check=False,
            )
            if result.returncode != 0 or raw.tell() == 0:
                raise RuntimeError("pg_dump failed; check database access and pg_dump version")
            raw.seek(0)
            # Create with private permissions before any database bytes are written.
            with open(local_path, "xb", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
                with gzip.GzipFile(fileobj=output, mode="wb") as compressed:
                    shutil.copyfileobj(raw, compressed)
        if storage == "s3":
            if not _s3_upload(local_path, f"database_backups/{filename}"):
                logger.error("Database snapshot created locally but remote backup upload failed")
                return {"status": "error", "detail": "Remote backup upload failed; local copy retained", "file": filename, "durable": False}
            _s3_cleanup_old_backups()
        _local_cleanup_old_backups()
        result = {"status": "success", "file": filename, "type": "postgres", "storage": storage, "durable": storage == "s3"}
        if storage == "local":
            result["warning"] = "Local backups require a persistent volume or an external copy to survive deployment"
            logger.warning(result["warning"])
        return result
    except Exception as error:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
        logger.error("Database backup failed (%s)", type(error).__name__)
        return {"status": "error", "detail": "Database backup failed; check PostgreSQL, pg_dump and storage configuration", "durable": False}
