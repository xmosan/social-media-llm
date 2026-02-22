import os
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .db import engine, SessionLocal
from .models import Base, Org, ApiKey, IGAccount
from .security import hash_api_key, require_api_key
from .routes import posts, admin, orgs, ig_accounts, automations, library, media
from .services.scheduler import start_scheduler
from .config import settings

app = FastAPI(title="Social Media LLM - Multi-tenant SaaS")
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    print(f"GLOBAL ERROR: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}", "type": type(exc).__name__},
    )

@app.get("/debug-env")
def debug_env():
    return {
        "openai_api_key_set": bool(settings.openai_api_key),
        "openai_api_key_len": len(settings.openai_api_key) if settings.openai_api_key else 0,
        "database_url_scheme": settings.database_url.split(":")[0] if settings.database_url else None
    }

# Serve uploads
os.makedirs(settings.uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")

# Include Routers
app.include_router(posts.router)
app.include_router(admin.router)
app.include_router(orgs.router)
app.include_router(ig_accounts.router)
app.include_router(automations.router)
app.include_router(library.router)
app.include_router(media.router)

def bootstrap_saas():
    """Seed initial Org and API Key for development/first run."""
    print("DIAGNOSTIC: Bootstrapping SaaS...")
    db = SessionLocal()
    try:
        # 1. Check if any Org exists
        if db.query(Org).first():
            return

        print("Bootstrap: Seeding initial multi-tenant data...")
        
        # 2. Create Default Org
        org = Org(name="Default Workspace")
        db.add(org)
        db.flush() # get ID

        # 3. Create initial API Key
        raw_key = os.getenv("INITIAL_API_KEY", settings.admin_api_key or "SaaS_Secret_123")
        api_key = ApiKey(
            org_id=org.id,
            name="Default Key",
            key_hash=hash_api_key(raw_key)
        )
        db.add(api_key)

        # 4. (Optional) Create initial IG Account from existing env
        if settings.ig_user_id and settings.ig_access_token:
            acc = IGAccount(
                org_id=org.id,
                name="Default Instagram",
                ig_user_id=settings.ig_user_id,
                access_token=settings.ig_access_token,
                active=True
            )
            db.add(acc)

        db.commit()
        print(f"Bootstrap complete. Use API Key: {raw_key}")
    except Exception as e:
        print(f"Bootstrap failed: {e}")
        db.rollback()
    finally:
        db.close()

@app.on_event("startup")
def on_startup():
    print("STARTUP: Creating/verifying database tables...")
    Base.metadata.create_all(bind=engine)
    
    from sqlalchemy import text
    print("STARTUP: Running Admin Enhancements migration...")
    is_postgres = "postgresql" in str(engine.url)
    try:
        with engine.begin() as conn:
            # 1. Update topic_automations
            auto_cols = [
                ("enrich_with_hadith", "BOOLEAN DEFAULT FALSE"),
                ("hadith_topic", "VARCHAR"),
                ("hadith_source_id", "INTEGER"),
                ("hadith_append_style", "VARCHAR DEFAULT 'short'"),
                ("hadith_max_len", "INTEGER DEFAULT 450"),
                ("media_asset_id", "INTEGER"),
                ("media_tag_query", "JSONB" if is_postgres else "TEXT"),
                ("media_rotation_mode", "VARCHAR DEFAULT 'random'")
            ]
            for col, col_def in auto_cols:
                try:
                    stmt = f"ALTER TABLE topic_automations ADD COLUMN {'IF NOT EXISTS' if is_postgres else ''} {col} {col_def}"
                    conn.execute(text(stmt))
                    print(f"Migration: Checked/Added column {col} to topic_automations")
                except Exception:
                    pass
            
            # 2. Update posts
            post_cols = [
                ("media_asset_id", "INTEGER")
            ]
            for col, col_def in post_cols:
                try:
                    stmt = f"ALTER TABLE posts ADD COLUMN {'IF NOT EXISTS' if is_postgres else ''} {col} {col_def}"
                    conn.execute(text(stmt))
                    print(f"Migration: Checked/Added column {col} to posts")
                except Exception as e:
                    print(f"Migration (posts) status: {e}")
    except Exception as e:
        print(f"CRITICAL Migration Error: {e}")
    
    # Debug OpenAI Key presence
    key = settings.openai_api_key
    if key:
        print(f"STARTUP: OpenAI API Key detected")
    else:
        print("STARTUP: WARNING: OpenAI API Key is MISSING!")

    bootstrap_saas()
    
    try:
        app.state.scheduler = start_scheduler(SessionLocal)
    except Exception as e:
        print("Scheduler start failed:", repr(e))
        app.state.scheduler = None

@app.get("/health")
def health():
    import datetime
    return {
        "status": "ok", 
        "version": "1.0.3", 
        "now": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }