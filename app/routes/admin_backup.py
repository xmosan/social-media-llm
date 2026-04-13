from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
import shutil
import os
from datetime import datetime
from typing import Optional

from app.db import DEFAULT_DB_PATH
from app.models import User
from app.security.rbac import require_superadmin

router = APIRouter(prefix="/admin", tags=["Admin Backup"])

# We define the backup directory relative to the project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

def verify_admin_key(admin_key: Optional[str] = Query(None)):
    """
    Optional extra security layer checking for a secret key in environment.
    """
    secret = os.getenv("ADMIN_SECRET_KEY")
    if secret and admin_key != secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret key")
    return True

@router.get("/backup-db")
def create_backup(
    admin: User = Depends(require_superadmin),
    _key: bool = Depends(verify_admin_key)
):
    """
    Creates a timestamped backup of the SQLite database.
    Requires Superadmin role AND optional ADMIN_SECRET_KEY if configured.
    """
    if not os.path.exists(DEFAULT_DB_PATH):
        raise HTTPException(status_code=404, detail=f"Database not found at {DEFAULT_DB_PATH}")

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"saas_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    try:
        shutil.copy2(DEFAULT_DB_PATH, backup_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

    # Retention Policy: Keep only the 10 most recent backups
    try:
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
            key=lambda x: os.path.getmtime(os.path.join(BACKUP_DIR, x)),
            reverse=True
        )
        if len(backups) > 10:
            for old_backup in backups[10:]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
    except Exception as e:
        # We don't want to fail the backup if cleanup fails, but we should log it
        print(f"⚠️ [Backup] Retention cleanup failed: {e}")

    return {
        "status": "success",
        "message": "Backup created successfully (10-file retention active)",
        "backup_file": backup_filename,
        "location": backup_path
    }

@router.get("/download-backup")
def download_latest_backup(
    admin: User = Depends(require_superadmin),
    _key: bool = Depends(verify_admin_key)
):
    """
    Downloads the most recent backup file.
    Requires Superadmin role AND optional ADMIN_SECRET_KEY if configured.
    """
    if not os.path.exists(BACKUP_DIR):
        raise HTTPException(status_code=404, detail="No backups available")

    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
        reverse=True
    )

    if not backups:
        raise HTTPException(status_code=404, detail="No backup files found")

    latest_backup = backups[0]
    backup_path = os.path.join(BACKUP_DIR, latest_backup)

    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Latest backup file missing from disk")

    return FileResponse(
        backup_path,
        filename=latest_backup,
        media_type="application/octet-stream"
    )
