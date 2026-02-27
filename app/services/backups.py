# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import subprocess
import gzip
import shutil
import glob
from datetime import datetime
import boto3
import logging
from ..config import settings

logger = logging.getLogger(__name__)

BACKUPS_DIR = os.path.join(os.getcwd(), "backups")
MAX_RETENTION_DAYS = 14

def _ensure_backup_dir():
    os.makedirs(BACKUPS_DIR, exist_ok=True)

def _get_s3_client():
    if not settings.s3_access_key or not settings.s3_secret_key or not settings.s3_bucket_name:
        return None
    endpoint = settings.s3_region if settings.s3_region and "http" in settings.s3_region else None
    region = settings.s3_region if settings.s3_region and "http" not in settings.s3_region else None
    
    return boto3.client(
        's3',
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=region,
        endpoint_url=endpoint
    )

def _s3_upload(file_path: str, object_name: str):
    s3 = _get_s3_client()
    if not s3:
        return False
    try:
        s3.upload_file(file_path, settings.s3_bucket_name, object_name)
        return True
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return False

def _s3_cleanup_old_backups():
    s3 = _get_s3_client()
    if not s3:
        return
    try:
        response = s3.list_objects_v2(Bucket=settings.s3_bucket_name, Prefix="database_backups/")
        if 'Contents' not in response:
            return
            
        objects = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
        to_delete = objects[MAX_RETENTION_DAYS:]
        
        if to_delete:
            delete_keys = [{'Key': obj['Key']} for obj in to_delete]
            s3.delete_objects(
                Bucket=settings.s3_bucket_name,
                Delete={'Objects': delete_keys}
            )
    except Exception as e:
        logger.error(f"S3 cleanup failed: {e}")

def _local_cleanup_old_backups():
    files = glob.glob(os.path.join(BACKUPS_DIR, "backup_*.sql.gz"))
    files.sort(key=os.path.getmtime, reverse=True)
    
    for f in files[MAX_RETENTION_DAYS:]:
        try:
            os.remove(f)
        except Exception as e:
            logger.error(f"Local cleanup failed for {f}: {e}")

def backup_postgres_database() -> dict:
    _ensure_backup_dir()
    
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M")
    filename = f"backup_{timestamp}.sql.gz"
    local_path = os.path.join(BACKUPS_DIR, filename)
    raw_path = os.path.join(BACKUPS_DIR, f"backup_{timestamp}.sql")
    
    db_url = settings.database_url
    
    success = False
    error_msg = None
    
    if db_url.startswith("postgres"):
        try:
            env = os.environ.copy()
            # Suppress pg_dump password prompt / utilize connection string
            result = subprocess.run(["pg_dump", db_url, "-f", raw_path, "--clean", "--if-exists", "--no-owner"], capture_output=True, text=True)
            if result.returncode != 0:
                error_msg = f"pg_dump failed: {result.stderr}"
                logger.error(error_msg)
            else:
                success = True
        except FileNotFoundError:
            # Fallback if pg_dump is not installed
            error_msg = "pg_dump not found in system executable path. A psycopg2-based export fallback could be implemented here, but pg_dump is explicitly required for Schema compatibility."
            logger.error(error_msg)
    else:
        # SQLite or other (local dev fallback)
        success = True
        with open(raw_path, 'w') as f:
            f.write("-- SQLite unsupported by routine pg_dump backup script. Use proper DB for prod.")
        
    if success:
        try:
            # Compress to .sql.gz
            with open(raw_path, 'rb') as f_in:
                with gzip.open(local_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            if os.path.exists(raw_path):
                os.remove(raw_path)  # Clean up raw sql
            
            # S3 Upload
            if settings.backup_storage_type.lower() == "s3":
                s3_key = f"database_backups/{filename}"
                _s3_upload(local_path, s3_key)
                _s3_cleanup_old_backups()
                
            # Local cleanup
            _local_cleanup_old_backups()
            
            return {"status": "success", "file": filename, "type": "postgres" if db_url.startswith("postgres") else "mock"}
            
        except Exception as e:
            success = False
            error_msg = f"Compression or upload failed: {str(e)}"
            logger.error(error_msg)
            if os.path.exists(raw_path):
                os.remove(raw_path)
            
    return {"status": "error", "detail": error_msg}
