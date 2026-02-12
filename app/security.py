from fastapi import Header, HTTPException
from app.config import settings

def require_api_key(x_api_key: str | None = Header(default=None)):
    if not settings.admin_api_key:
        # If you forgot to set it, fail closed in production
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY not configured")
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")