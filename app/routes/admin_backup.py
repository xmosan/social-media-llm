from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
import os
import json
import gzip
import shutil
from datetime import datetime
from typing import Optional
from sqlalchemy import inspect, text

from app.db import engine, SessionLocal
from app.models import User, Base
from app.security.rbac import require_superadmin

router = APIRouter(prefix="/admin", tags=["Admin Backup"])

# Backup directory (Project Root /backups)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

def verify_admin_key(admin_key: Optional[str] = Query(None)):
    secret = os.getenv("ADMIN_SECRET_KEY")
    if secret and admin_key != secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret key")
    return True

@router.get("/backup-db")
def create_postgres_backup(
    admin: User = Depends(require_superadmin),
    _key: bool = Depends(verify_admin_key)
):
    """
    Creates a portable JSON-based backup of the entire PostgreSQL database.
    This works without pg_dump being installed in the environment.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"pg_backup_{timestamp}.json.gz"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    db_dump = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "engine": "postgresql",
            "version": "1.0-portable"
        },
        "tables": {}
    }
    
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        db = SessionLocal()
        try:
            for table_name in table_names:
                # Use text() for raw SQL query per table
                result = db.execute(text(f"SELECT * FROM {table_name}"))
                # Convert rows to serializable dicts
                columns = result.keys()
                rows = [dict(zip(columns, row)) for row in result]
                
                # Handle non-serializable types (datetime)
                for row in rows:
                    for k, v in row.items():
                        if isinstance(v, datetime):
                            row[k] = v.isoformat()
                
                db_dump["tables"][table_name] = rows
                
            # Serialized and compress
            json_str = json.dumps(db_dump, indent=2)
            with gzip.open(backup_path, 'wt', encoding='utf-8') as f:
                f.write(json_str)
            
            # STEP 2: ADMIN BACKUP VALIDATION
            file_size = os.path.getsize(backup_path)
            
            # Integrity Check: Test decompression and structure
            with gzip.open(backup_path, 'rt', encoding='utf-8') as f:
                test_load = json.load(f)
                if not test_load.get("tables") or len(test_load["tables"]) == 0:
                    raise ValueError("Integrity Failure: Backup manifest contains no tables.")
            
            if file_size < 10240: # 10KB check
                 print(f"⚠️ Warning: Backup size unusually small ({file_size} bytes)")
            
            print(f"📦 Backup created: {backup_filename} ({file_size} bytes)")
            # Log structured
            import logging
            logging.getLogger("social-media-llm").info(f"[BACKUP] Created: {backup_filename}")
                
        finally:
            db.close()
            
    except Exception as e:
        if os.path.exists(backup_path):
            os.remove(backup_path)
        print(f"❌ [BACKUP] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Postgres Matrix Export failed: {str(e)}")

    # Retention Policy: 10 files
    try:
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".json.gz")],
            key=lambda x: os.path.getmtime(os.path.join(BACKUP_DIR, x)),
            reverse=True
        )
        if len(backups) > 10:
            for old_backup in backups[10:]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
    except Exception as e:
        print(f"⚠️ [Backup] Retention cleanup failed: {e}")

    return {
        "status": "success",
        "message": "PostgreSQL Portable Backup manifest created.",
        "backup_file": backup_filename,
        "location": backup_path,
        "tables_synced": list(db_dump["tables"].keys())
    }

@router.get("/download-backup")
def download_latest_backup(
    admin: User = Depends(require_superadmin),
    _key: bool = Depends(verify_admin_key)
):
    if not os.path.exists(BACKUP_DIR):
        raise HTTPException(status_code=404, detail="No backups available")

    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".json.gz")],
        reverse=True
    )

    if not backups:
        raise HTTPException(status_code=404, detail="No backup files found")

    latest_backup = backups[0]
    backup_path = os.path.join(BACKUP_DIR, latest_backup)

    return FileResponse(
        backup_path,
        filename=latest_backup,
        media_type="application/gzip"
    )
