# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import time
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uuid
import mimetypes

# Enforce strict MIME mappings for Meta transparency
mimetypes.add_type('image/jpeg', '.jpg')
mimetypes.add_type('image/jpeg', '.jpeg')
mimetypes.add_type('image/png', '.png')
mimetypes.add_type('video/mp4', '.mp4')

from .config import settings
from .db import engine, SessionLocal, get_db
from .models import Base, Org, ApiKey, IGAccount, User, OrgMember, ContentSource, ContentItem, ContentUsage, WaitlistEntry, InboundMessage
from .security.auth import require_user
from .services.source_grounding import resolve_selected_source
from .routes import posts, admin, orgs, ig_accounts, automations, library, media, auth, profiles, auth_google, auth_ig, public, sources, app_pages, admin_library, admin_global_library, admin_backup
from .api.routes import waitlist, contact, admin_panel
from .services.scheduler import start_scheduler
from .logging_setup import setup_logging, request_id_var, log_event
from .security.rbac import get_current_org_id
from .security.usage_context import UsageContextMiddleware
from .services.usage_limits import UsageLimitError

import logging
logger = logging.getLogger(__name__)

setup_logging()

# GLOBAL STARTUP LOG FOR DIAGNOSTICS
STARTUP_LOG = []

def log_startup(msg: str):
    print(f"STARTUP_DIAG: {msg}")
    STARTUP_LOG.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# --- DATABASE MIGRATION (Admin Library Manager) ---
def run_admin_library_migration():
    from sqlalchemy import text
    from .models import Base
    from .db import sync_database_schema
    
    log_startup("MIGRATION: Ensuring all tables exist...")
    Base.metadata.create_all(bind=engine)

    # Use the new resilient sync for column additions
    sync_database_schema(log_startup)
    log_startup("MIGRATION: Column sync complete.")

    log_startup("MIGRATION: Finished all schema checks.")

def run_startup_tasks():
    from app.db import SessionLocal
    # Phase 2: Seed Style DNA presets
    from app.services.automation_service import seed_style_dna
    with SessionLocal() as db:
        seed_style_dna(db)
        log_startup("STARTUP_TASKS: Style DNA seeding complete.")

# -------------------------------------------------

# Startup validation checks
REQUIRED_VARS = ["OPENAI_API_KEY", "IG_ACCESS_TOKEN", "DATABASE_URL", "JWT_SECRET"]
missing_vars = [
    var for var in REQUIRED_VARS 
    if not os.environ.get(var) and not getattr(settings, var.lower() if var != "JWT_SECRET" else "secret_key", None)
]

# Strict Postgres Enforcement
db_url = os.getenv("DATABASE_URL")
if not db_url or "postgres" not in db_url.lower():
    missing_vars.append("DATABASE_URL (NATIVE POSTGRESQL REQUIRED)")

if missing_vars:
    logger.critical(
        f"CRITICAL: Missing required environment variables: {', '.join(missing_vars)}. "
        f"Automation and LLM features will be degraded or unavailable."
    )

app = FastAPI(
    title="Sabeel - Multi-tenant SaaS",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

@app.get("/api-test")
def api_test():
    return {"ok": True}

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        start_time = time.time()
        
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            
            # Inject proprietary headers for HTML responses
            content_type = response.headers.get("content-type", "")
            if content_type and content_type.startswith("text/html"):
                response.headers["X-Content-Owner"] = "Mohammed Hassan"
                response.headers["X-License"] = "Proprietary"
                
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise e
        finally:
            latency = int((time.time() - start_time) * 1000)
            log_event(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=latency
            )
            request_id_var.reset(token)
            
        return response

class ComingSoonMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.coming_soon_mode:
            return await call_next(request)
            
        path = request.url.path

        # 0. BOT SANCTUARY: Allow Meta/Social manifest bots to bypass the wall for media fetching
        ua = request.headers.get("user-agent", "").lower()
        social_bots = ["facebookexternalhit", "facebookcatalog", "instagram", "twitterbot", "linkedinbot"]
        if any(bot in ua for bot in social_bots):
            return await call_next(request)
        
        # 1. ALLOWED PATHS (Always accessible)
        # FORCE PUBLIC ACCESS for /uploads to ensure Meta/Instagram fetcher NEVER hits a wall
        if path.startswith("/uploads/"):
            return await call_next(request)

        allowed_prefixes = [
            "/join", "/login", "/register", "/auth", "/static", "/favicon.ico", "/api/contact", "/health", "/ready", "/api-test", "/demo",
            "/contact", "/privacy", "/terms", "/docs", "/redoc", "/openapi.json", "/generate-caption", "/generate-quote-card", "/api/waitlist",
            "/api/quran", "/api/quote-card/build-message", "/api/caption/generate", "/library", "/api/library", "/app/library"
        ]
        if path == "/" or any(path.startswith(p) for p in allowed_prefixes):
            # If authenticated and visiting root, redirect to /app
            if path == "/" and request.cookies.get("access_token"):
                return RedirectResponse(url="/app")
            return await call_next(request)
            
        # 2. CHECK AUTHENTICATION FOR OTHER ROUTES
        # Fast path: check cookie existence
        if request.cookies.get("access_token"):
            return await call_next(request)
            
        # 3. REDIRECT UNSTHENTICATED TO COMING SOON PAGE
        return RedirectResponse(url="/")

# Robust Environment Detection
is_railway = os.getenv("RAILWAY_ENVIRONMENT") is not None
is_prod = is_railway or ("localhost" not in str(settings.public_base_url) and "127.0.0.1" not in str(settings.public_base_url))

# Settings validates the shared signing key before database initialization.

from urllib.parse import urlparse
eff_domain = urlparse(settings.public_base_url).hostname if is_prod else None

from app.security.instagram_session import LegacyInstagramSessionCleanup
# Runs inside SessionMiddleware so it can remove legacy credential payloads.
app.add_middleware(LegacyInstagramSessionCleanup)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=is_prod,
    same_site="lax",
    max_age=3600 * 24 * 7, # 1 week
    domain=eff_domain
)
app.add_middleware(ComingSoonMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(UsageContextMiddleware)

# NO OP - Removing first duplicate handler to clean up.

@app.get("/api/debug-automations")
def api_debug_automations(db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    from app.models import TopicAutomation
    autos = db.query(TopicAutomation).filter(TopicAutomation.org_id == org_id).all()
    return [{"id": a.id, "name": a.name, "topic": a.topic_prompt, "last_error": a.last_error} for a in autos]

@app.get("/api/debug-env")
def api_debug_env(org_id: int = Depends(get_current_org_id)):
    return {
        "openai_api_key_set": bool(settings.openai_api_key),
        "openai_api_key_len": len(settings.openai_api_key) if settings.openai_api_key else 0,
        "database_url_scheme": settings.database_url.split(":")[0] if settings.database_url else None
    }

@app.get("/health")
def health_check():
    from sqlalchemy import text
    db_status = "connected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"
    
    scheduler = getattr(app.state, "scheduler", None)
    scheduler_running = bool(scheduler and scheduler.running)
    scheduler_status = "disabled" if not settings.scheduler_enabled else ("running" if scheduler_running else "not_started")
    llm_status = "configured" if settings.openai_api_key else "unconfigured"
    
    healthy = db_status == "connected" and getattr(app.state, "ready", False) and (not settings.scheduler_enabled or scheduler_running)
    return JSONResponse(status_code=200 if healthy else 503, content={
        "status": "ok" if healthy else "degraded",
        "database": db_status,
        "scheduler": scheduler_status,
        "llm": llm_status,
        "version": "v7.0.0"
    })

from app.services.caption_engine import generate_islamic_caption
from app.services.image_card import generate_quote_card
from pydantic import BaseModel
from typing import Optional

# --- NEW STUDIO API ENDPOINTS ---

class QuoteCardBuildRequest(BaseModel):
    source_type: str
    reference: Optional[str] = None
    item_id: Optional[str] = None
    tone: str = "calm"
    intent: str = "wisdom"
    custom_payload: Optional[dict] = None

@app.post("/api/quote-card/build-message", dependencies=[Depends(require_user)])
async def api_build_quote_message(req: QuoteCardBuildRequest, db: Session = Depends(get_db),
                             org_id: int = Depends(get_current_org_id), user: User = Depends(require_user)):
    from app.services.quote_message_service import build_quote_card_message
    from app.services.quran_service import get_verse_by_id, get_verse_by_key
    
    source_payload = {}
    if req.source_type in {"quran", "hadith"}:
        selection = dict(req.custom_payload or {})
        if req.item_id:
            selection["id"] = req.item_id
        if req.reference:
            selection["reference"] = req.reference
        try:
            source_payload = resolve_selected_source(db, org_id, req.source_type, selection, user.id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
    elif req.source_type == "manual":
        source_payload = req.custom_payload or {}
        if req.reference and not source_payload.get("topic"):
            source_payload["topic"] = req.reference
    
    try:
        custom_prompt = (req.custom_payload or {}).get("custom_prompt", "")
        msg = build_quote_card_message(req.source_type, source_payload, req.tone, req.intent, custom_prompt)
        return {"card_message": msg, "source_metadata": source_payload}
    except UsageLimitError:
        raise
    except Exception as e:
        logger.error(f"Error building card message: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

class CaptionGenerateRequest(BaseModel):
    source_type: str
    reference: Optional[str] = None
    item_id: Optional[str] = None
    tone: str = "calm"
    intent: str = "wisdom"
    platform: str = "instagram"
    custom_payload: Optional[dict] = None

@app.post("/api/caption/generate", dependencies=[Depends(require_user)])
async def api_generate_caption(req: CaptionGenerateRequest, db: Session = Depends(get_db),
                             org_id: int = Depends(get_current_org_id), user: User = Depends(require_user)):
    from app.services.caption_service import generate_caption_from_source
    from app.services.quran_service import get_verse_by_id, get_verse_by_key
    
    source_payload = {}
    if req.source_type in {"quran", "hadith"}:
        selection = dict(req.custom_payload or {})
        if req.item_id:
            selection["id"] = req.item_id
        if req.reference:
            selection["reference"] = req.reference
        try:
            source_payload = resolve_selected_source(db, org_id, req.source_type, selection, user.id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
    elif req.source_type == "manual":
        source_payload = req.custom_payload or {}
        if req.reference and not source_payload.get("text"):
            source_payload["text"] = req.reference

    try:
        caption = generate_caption_from_source(
            req.source_type, 
            source_payload, 
            req.tone, 
            req.intent, 
            req.platform
        )
        return {"caption_message": caption}
    except UsageLimitError:
        raise
    except Exception as e:
        logger.error(f"Error generating caption: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

# --- LEGACY ENDPOINTS ---

@app.post("/generate-caption", dependencies=[Depends(require_user)])
async def generate_caption(data: dict, db: Session = Depends(get_db),
                           org_id: int = Depends(get_current_org_id), user: User = Depends(require_user)):
    # Phase 3 Legacy Compat Wrapper
    from app.routes.studio import studio_generate_caption
    return studio_generate_caption(data, db=db, org_id=org_id, user=user)

@app.post("/generate-quote-card", dependencies=[Depends(require_user)], summary="Generate a Cinematic Quote Card")
async def api_generate_quote_card(data: dict, db: Session = Depends(get_db),
                                  org_id: int = Depends(get_current_org_id)):
    # Phase 3 Legacy Compat Wrapper
    from app.routes.studio import studio_generate_visual
    from fastapi.responses import JSONResponse
    
    # Pre-map legacy string values for VisualRequest layout
    caption = data.get("caption", "").strip()
    if caption and not data.get("card_message"):
        data["card_message"] = {"headline": caption}

    try:
        return studio_generate_visual(data, org_id=org_id, db=db)
    except UsageLimitError:
        raise
    except Exception as e:
        import traceback
        print(f"\n❌ [API] generate-quote-card EXCEPTION:\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": str(e)[:200]})

@app.get("/ready")
def readiness_check():
    return health_check()

# Serve uploads and static assets with dynamic absolute pathing
uploads_absolute_path = settings.uploads_dir
os.makedirs(uploads_absolute_path, exist_ok=True)

# Static assets (fonts, system gallery, etc.)
static_absolute_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# EXPLICIT IMAGE SERVING OVERRIDE (Bypass StaticFiles if needed)
@app.get("/uploads/{filename}")
async def serve_upload_forced(filename: str):
    from fastapi.responses import FileResponse
    full_path = os.path.join(settings.uploads_dir, filename)
    if not os.path.exists(full_path):
        # DEEP 404 DIAGNOSTIC (Black Box logging for Railway)
        print(f"❌ [MEDIA_404] File not found: {full_path}")
        print(f"   - Current Working Directory: {os.getcwd()}")
        try:
            files = sorted(os.listdir(settings.uploads_dir))
            print(f"   - Recent local files in {settings.uploads_dir}: {files[-5:]}")
        except Exception as e:
            print(f"   - Could not list contents of {settings.uploads_dir}: {e}")
        
        raise HTTPException(status_code=404, detail=f"File not found on server at {full_path}")
    # Force correct MIME type regardless of extension sniffing
    content_type = "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else ("image/png" if filename.endswith(".png") else "application/octet-stream")
    
    # PRODUCTION HARDENING: Force no-cache to ensure Meta always gets the fresh binary
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(full_path, media_type=content_type, headers=headers)

app.mount("/uploads", StaticFiles(directory=uploads_absolute_path), name="uploads")
app.mount("/static", StaticFiles(directory=static_absolute_path), name="static")
print(f"📁 [System] Media mounted: {uploads_absolute_path}")
print(f"📁 [System] Assets mounted: {static_absolute_path}")

# Include Routers
from .routes import neural_hub, studio
app.include_router(studio.router)
app.include_router(neural_hub.router)
app.include_router(public.router)
app.include_router(posts.router)
app.include_router(admin.router)
app.include_router(orgs.router)
app.include_router(ig_accounts.router)
app.include_router(ig_accounts.accounts_router)
app.include_router(automations.router)
app.include_router(media.router)
from .routes import admin_diag
app.include_router(admin_diag.router)
app.include_router(auth.router)
from .routes import tester_access
app.include_router(tester_access.router)
app.include_router(auth_google.router)
app.include_router(auth_ig.router)
app.include_router(auth_ig.meta_alias_router)
app.include_router(profiles.router)
app.include_router(sources.router)
app.include_router(library.router)
app.include_router(admin_library.router)
app.include_router(admin_global_library.router)
app.include_router(app_pages.router)
from .api.routes import waitlist, contact, admin_panel, quran
app.include_router(waitlist.router)
app.include_router(contact.router)
app.include_router(admin_panel.router)
app.include_router(admin_backup.router)
app.include_router(quran.router)

def bootstrap_saas():
    """Provision an initial administrator only when explicitly enabled."""
    if not settings.bootstrap_superadmin:
        return
    from .services.bootstrap import bootstrap_saas as provision_initial_admin
    with SessionLocal() as db:
        try:
            provision_initial_admin(db, settings)
        except Exception:
            db.rollback()
            raise

@app.on_event("startup")
def on_startup():
    log_startup("EVENT: ON_STARTUP triggered.")
    app.state.ready = False
    app.state.scheduler = None
    # Legacy migrations/seeds require an explicit maintenance decision.
    if settings.run_startup_migrations:
        run_admin_library_migration()
        run_startup_tasks()
    from .db import validate_database_schema
    validate_database_schema()
    # Creator reference data only: no table/column changes or legacy reseeding.
    from .services.automation_service import seed_style_dna
    from .services.card_typography import DESIGN_FAMILIES
    with SessionLocal() as db:
        created = seed_style_dna(db, families=DESIGN_FAMILIES)
    log_startup(f"CREATOR_PRESETS: Ready; {created} new presets added.")
    bootstrap_saas()
    if settings.scheduler_enabled:
        app.state.scheduler = start_scheduler(SessionLocal)
        log_startup("STARTUP: Scheduler started.")
    app.state.ready = True
    log_startup("STARTUP: Readiness check complete.")

@app.on_event("shutdown")
def on_shutdown():
    app.state.ready = False
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
    app.state.scheduler = None

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # If it's a specific HTTP error or validation error, let FastAPI's default handlers deal with it
    if isinstance(exc, (HTTPException, StarletteHTTPException, RequestValidationError)):
        raise exc
    
    # Otherwise, it's a true unexpected error
    logger.error(f"UNEXPECTED ERROR: {exc}", exc_info=True)
    log_startup(f"GLOBAL ERROR: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )
