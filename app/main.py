import os
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.proxy_headers import ProxyHeadersMiddleware

from .db import engine, SessionLocal
from .models import Base, Org, ApiKey, IGAccount
from .security import hash_api_key, require_api_key
from .routes import posts, admin, orgs, ig_accounts, automations, library
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
        "database_url_scheme": settings.database_url.split(":")[0] if settings.database_url else None,
        "org_id": org_id
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

def bootstrap_saas():
    """Seed initial Org and API Key for development/first run."""
    print("DIAGNOSTIC: Bootstrapping SaaS...")
    t0 = time.time()
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
        # If INITIAL_API_KEY is not in env, we use settings.admin_api_key as a fallback
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
    # In multi-tenant, we typically drop/create in DEV but use migrations in PROD.
    # For this MVP, we ensure tables exist.
    print("STARTUP: Creating/verifying database tables...")
    Base.metadata.create_all(bind=engine)
    
    # Debug OpenAI Key presence
    key = settings.openai_api_key
    if key:
        masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
        print(f"STARTUP: OpenAI API Key detected: {masked}")
    else:
        print("STARTUP: WARNING: OpenAI API Key is MISSING!")

    print(f"STARTUP: Tables ready. Engine URL prefix: {str(engine.url)[:30]}...")
    
    # Run bootstrap
    bootstrap_saas()
    
    # Start Scheduler
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
        "mode": "multi-tenant", 
        "version": "1.0.2", 
        "now": datetime.datetime.now().isoformat(),
        "openai_key_configured": bool(settings.openai_api_key)
    }