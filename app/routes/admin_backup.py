"""Administrator backup endpoints share the tested PostgreSQL dump service."""
from pathlib import Path
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from app.models import User
from app.security.rbac import require_superadmin
from app.services import backups

router = APIRouter(prefix="/admin", tags=["Admin Backup"])


def verify_admin_key(admin_key: Optional[str] = Query(None)):
    secret = os.getenv("ADMIN_SECRET_KEY")
    if secret and admin_key != secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret key")
    return True


@router.post("/backup-db")
@router.get("/backup-db")  # Existing admin client compatibility.
def create_postgres_backup(admin: User = Depends(require_superadmin), _key: bool = Depends(verify_admin_key)):
    result = backups.backup_postgres_database()
    if result["status"] != "success":
        raise HTTPException(status_code=503, detail=result["detail"])
    return {**result, "backup_file": result["file"], "message": "PostgreSQL dump created; see storage and durability status"}


@router.get("/download-backup")
def download_latest_backup(admin: User = Depends(require_superadmin), _key: bool = Depends(verify_admin_key)):
    directory = Path(backups.BACKUPS_DIR)
    files = [file for file in directory.glob("*.gz") if file.is_file() and not file.is_symlink()
             and ((file.name.startswith("backup_") and file.name.endswith(".sql.gz"))
                  or (file.name.startswith("pg_backup_") and file.name.endswith(".json.gz")))]
    if not files:
        raise HTTPException(status_code=404, detail="No backup files found")
    latest = max(files, key=lambda file: file.stat().st_mtime)
    return FileResponse(latest, filename=latest.name, media_type="application/gzip", headers={"Cache-Control": "no-store"})
