# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import time
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
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

from .db import engine, SessionLocal, get_db
from .models import Base, Org, ApiKey, IGAccount, User, OrgMember, ContentSource, ContentItem, ContentUsage, WaitlistEntry, InboundMessage
from .security.auth import get_password_hash
from .routes import posts, admin, orgs, ig_accounts, automations, library, media, auth, profiles, auth_google, auth_ig, public, sources, app_pages, admin_library, admin_global_library, admin_backup
from .api.routes import waitlist, contact, admin_panel
from .services.scheduler import start_scheduler
from .config import settings
from .logging_setup import setup_logging, request_id_var, log_event
from .security.rbac import get_current_org_id

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
    try:
        # Standard creation
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        log_startup(f"MIGRATION: Metadata creation failed: {e}")

    # Use the new resilient sync for column additions
    try:
        sync_database_schema(log_startup)
        log_startup("MIGRATION: Resilient column sync complete.")
    except Exception as e:
        log_startup(f"MIGRATION: Resilient sync failed: {e}")

    log_startup("MIGRATION: Finished all schema checks.")

def run_startup_tasks():
    from app.db import SessionLocal
    # Phase 2: Seed Style DNA presets
    try:
        from app.services.automation_service import seed_style_dna
        db = SessionLocal()
        seed_style_dna(db)
        db.close()
        log_startup("STARTUP_TASKS: Style DNA seeding complete.")
    except Exception as e:
        log_startup(f"STARTUP_TASKS: Style DNA seeding failed: {e}")

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
            "/login", "/register", "/auth", "/static", "/favicon.ico", "/api/contact", "/health", "/api-test", "/demo", 
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

# Stabilize Secret Key (Prefer SECRET_KEY -> JWT_SECRET -> Fallback)
eff_secret_key = os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET") or settings.secret_key

from urllib.parse import urlparse
eff_domain = urlparse(settings.public_base_url).hostname if is_prod else None

app.add_middleware(
    SessionMiddleware, 
    secret_key=eff_secret_key,
    https_only=is_prod,
    same_site="lax",
    max_age=3600 * 24 * 7, # 1 week
    domain=eff_domain
)
app.add_middleware(ComingSoonMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

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
    except Exception as e:
        db_status = f"error: {str(e)[:80]}"
    
    scheduler_status = "running" if getattr(app.state, 'scheduler', None) else "not_started"
    llm_status = "configured" if settings.openai_api_key else "unconfigured"
    
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "scheduler": scheduler_status,
        "llm": llm_status,
        "version": "v7.0.0"
    }

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

@app.post("/api/quote-card/build-message")
async def api_build_quote_message(req: QuoteCardBuildRequest, db: Session = Depends(get_db)):
    from app.services.quote_message_service import build_quote_card_message
    from app.services.quran_service import get_verse_by_id, get_verse_by_key
    
    source_payload = {}
    if req.source_type == "quran":
        verse = None
        if req.item_id:
            verse = get_verse_by_id(db, int(req.item_id))
        elif req.reference:
            verse = get_verse_by_key(db, req.reference)
        
        if not verse:
            return JSONResponse(status_code=404, content={"detail": "Quran verse not found"})
        
        source_payload = {
            "reference": verse["reference"],
            "translation_text": verse["translation_text"],
            "arabic_text": verse["arabic_text"],
            "surah": verse["surah_number"],
            "ayah": verse["ayah_number"],
            "surah_name_en": verse["surah_name_en"]
        }
    elif req.source_type == "manual":
        source_payload = req.custom_payload or {}
        if req.reference and not source_payload.get("topic"):
            source_payload["topic"] = req.reference
    
    try:
        custom_prompt = (req.custom_payload or {}).get("custom_prompt", "")
        msg = build_quote_card_message(req.source_type, source_payload, req.tone, req.intent, custom_prompt)
        return {"card_message": msg, "source_metadata": source_payload}
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

@app.post("/api/caption/generate")
async def api_generate_caption(req: CaptionGenerateRequest, db: Session = Depends(get_db)):
    from app.services.caption_service import generate_caption_from_source
    from app.services.quran_service import get_verse_by_id, get_verse_by_key
    
    source_payload = {}
    if req.source_type == "quran":
        verse = None
        if req.item_id:
            verse = get_verse_by_id(db, int(req.item_id))
        elif req.reference:
            verse = get_verse_by_key(db, req.reference)
            
        if not verse:
            return JSONResponse(status_code=404, content={"detail": "Quran verse not found"})
            
        source_payload = {
            "reference": verse["reference"],
            "text": verse["translation_text"],
            "arabic_text": verse["arabic_text"],
            "surah_name_en": verse["surah_name_en"]
        }
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
    except Exception as e:
        logger.error(f"Error generating caption: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

# --- LEGACY ENDPOINTS ---

@app.post("/generate-caption")
async def generate_caption(data: dict):
    # Phase 3 Legacy Compat Wrapper
    from app.routes.studio import studio_generate_caption
    return studio_generate_caption(data)

@app.post("/generate-quote-card", summary="Generate a Cinematic Quote Card")
async def api_generate_quote_card(data: dict):
    # Phase 3 Legacy Compat Wrapper
    from app.routes.studio import studio_generate_visual
    from fastapi.responses import JSONResponse
    
    # Pre-map legacy string values for VisualRequest layout
    caption = data.get("caption", "").strip()
    if caption and not data.get("card_message"):
        data["card_message"] = {"headline": caption}

    try:
        return studio_generate_visual(data)
    except Exception as e:
        import traceback
        print(f"\n❌ [API] generate-quote-card EXCEPTION:\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": str(e)[:200]})

@app.get("/ready")
def readiness_check():
    from .db import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT id FROM users LIMIT 1"))
        return {"status": "ready"}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": "Database migrations pending or DB unreachable."})

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
    """Seed initial Org, API Key, and Superadmin User."""
    log_startup("BOOTSTRAP: Starting SaaS initialization...")
    db = SessionLocal()
    try:
        # 0. GOOGLE CONFIG CHECK
        log_startup(f"BOOTSTRAP: Google Client ID present in settings: {bool(settings.google_client_id)}")
        log_startup(f"BOOTSTRAP: Google Client Secret present in settings: {bool(settings.google_client_secret)}")
        
        # Check raw environment as well
        log_startup(f"BOOTSTRAP: ENV GOOGLE_CLIENT_ID: {bool(os.environ.get('GOOGLE_CLIENT_ID'))}")
        log_startup(f"BOOTSTRAP: ENV GOOGLE_CLIENT_SECRET: {bool(os.environ.get('GOOGLE_CLIENT_SECRET'))}")

        # 1. SUPERADMIN BOOTSTRAP
        # Use settings or a hardcoded fallback to ensure someone can always log in
        superadmin_email = settings.superadmin_email or "app.sabeel.studio@gmail.com"
        superadmin_pass = settings.superadmin_password or "Admin123!" # Hardcoded fallback for emergency access
        
        log_startup(f"BOOTSTRAP: Targeting superadmin email: {superadmin_email}")
        
        # Find user by email
        superadmin = db.query(User).filter(func.lower(User.email) == func.lower(superadmin_email)).first()
        
        if not superadmin:
            log_startup(f"BOOTSTRAP: Superadmin {superadmin_email} not found. Creating new...")
            superadmin = User(
                email=superadmin_email,
                password_hash=get_password_hash(superadmin_pass),
                is_superadmin=True,
                is_active=True,
                name="Platform Superadmin"
            )
            db.add(superadmin)
            db.flush()
            log_startup(f"BOOTSTRAP: Created superadmin with ID: {superadmin.id}")
        else:
            log_startup(f"BOOTSTRAP: Superadmin {superadmin.email} found. Syncing state...")
            superadmin.is_superadmin = True
            superadmin.is_active = True
            # Always sync password if provided in settings, otherwise keep existing
            if settings.superadmin_password:
                superadmin.password_hash = get_password_hash(settings.superadmin_password)
            db.flush()

        # 2. ORG CHECK
        org = db.query(Org).first()
        if not org:
            log_startup("BOOTSTRAP: Seeding initial multi-tenant data (Default Org)...")
            org = Org(name="Default Workspace")
            db.add(org)
            db.flush()
            
            # 3. API KEY
            raw_key = os.getenv("INITIAL_API_KEY", settings.admin_api_key or "SaaS_Secret_123")
            import hashlib
            api_key = ApiKey(
                org_id=org.id,
                name="Default Key",
                key_hash=hashlib.sha256(raw_key.encode()).hexdigest()
            )
            db.add(api_key)
            db.flush()
            log_startup("BOOTSTRAP: Created default organization and API key.")
        else:
            log_startup(f"BOOTSTRAP: Existing organization found: {org.name}")

        # 4. RELATIONSHIP CHECK
        if superadmin and org:
            is_member = db.query(OrgMember).filter(OrgMember.user_id == superadmin.id, OrgMember.org_id == org.id).first()
            if not is_member:
                log_startup(f"BOOTSTRAP: Linking superadmin {superadmin.email} to org {org.name}...")
                member = OrgMember(org_id=org.id, user_id=superadmin.id, role="owner")
                db.add(member)
        
        db.commit()
        log_startup("BOOTSTRAP: Core data committed successfully.")
        
        # 5. INITIAL IG ACCOUNT (REMOVED - Use OAuth flow instead)
        log_startup(f"BOOTSTRAP: Public Base URL is set to: {settings.public_base_url}")
        log_startup(f"BOOTSTRAP: FB_APP_ID present in settings: {bool(settings.fb_app_id)}")
        log_startup(f"BOOTSTRAP: FB_APP_SECRET present in settings: {bool(settings.fb_app_secret)}")
        log_startup("BOOTSTRAP: Finished.")
    except Exception as e:
        log_startup(f"BOOTSTRAP ERROR: {e}")
        import traceback
        log_startup(traceback.format_exc())
        db.rollback()
    finally:
        db.close()

@app.on_event("startup")
def on_startup():
    log_startup("EVENT: ON_STARTUP triggered.")
    
    # 1. Base Tables
    try:
        log_startup("STARTUP: Creating/verifying base metadata...")
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        log_startup(f"STARTUP: Metadata creation error: {e}")
    
    # 2. Sequential Migrations
    log_startup("STARTUP: Running migrations...")
    try:
        run_admin_library_migration()
        run_startup_tasks()
    except Exception as e:
        log_startup(f"STARTUP: Migrations/Startup Tasks failed: {e}")

    # 4. Bootstrap
    try:
        bootstrap_saas()
    except Exception as e:
        log_startup(f"STARTUP: Bootstrap failed: {e}")
    
    # 5. Scheduler
    try:
        app.state.scheduler = start_scheduler(SessionLocal)
        log_startup("STARTUP: Scheduler started.")
    except Exception as e:
        log_startup(f"STARTUP: Scheduler start failed: {e}")
        app.state.scheduler = None

    # 6. Final Config Check
    log_startup(f"STARTUP: OpenAI Key present: {bool(settings.openai_api_key)}")
    log_startup("STARTUP: Readiness check complete.")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_startup(f"GLOBAL ERROR: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )
    