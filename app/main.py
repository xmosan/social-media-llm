# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import time
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uuid

from .db import engine, SessionLocal, get_db
from .models import Base, Org, ApiKey, IGAccount, User, OrgMember, ContentSource, ContentItem, ContentUsage
from .security.auth import get_password_hash
from .routes import posts, admin, orgs, ig_accounts, automations, library, media, auth, profiles, auth_google, auth_ig, public, sources, app_pages, admin_library, admin_global_library
from .services.scheduler import start_scheduler
from .config import settings
from .logging_setup import setup_logging, request_id_var, log_event

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
    
    log_startup("MIGRATION: Ensuring all tables exist...")
    try:
        # Standard creation
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        log_startup(f"MIGRATION: Metadata creation failed: {e}")

    with engine.begin() as conn:
        log_startup("MIGRATION: Checking/Creating content_sources and content_items manually...")
        is_postgres = "postgresql" in engine.drivername
        
        # Manual Source Table Creation (Fallback)
        try:
            id_col = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
            json_type = "JSONB" if is_postgres else "JSON"
            
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS content_sources (
                    id {id_col},
                    org_id INTEGER REFERENCES orgs(id),
                    name VARCHAR NOT NULL,
                    source_type VARCHAR NOT NULL,
                    category VARCHAR,
                    description TEXT,
                    config {json_type} NOT NULL DEFAULT '{{}}',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
        except Exception as e:
            log_startup(f"MIGRATION: Source table creation status: {e}")

        # Manual Item Table Creation
        try:
            id_col = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
            json_type = "JSONB" if is_postgres else "JSON"
            
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS content_items (
                    id {id_col},
                    org_id INTEGER REFERENCES orgs(id),
                    source_id INTEGER NOT NULL REFERENCES content_sources(id),
                    item_type VARCHAR DEFAULT 'note',
                    title VARCHAR,
                    text TEXT NOT NULL,
                    arabic_text TEXT,
                    translation TEXT,
                    url TEXT,
                    meta {json_type} NOT NULL DEFAULT '{{}}',
                    tags {json_type} NOT NULL DEFAULT '[]',
                    last_used_at TIMESTAMP WITH TIME ZONE,
                    use_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
        except Exception as e:
            log_startup(f"MIGRATION: Item table creation status: {e}")
            
        # 1. Force Column Check (Fix for broken/partial tables)
        tables_cols = {
            "content_sources": [
                ("org_id", "INTEGER"),
                ("category", "VARCHAR"),
                ("description", "TEXT"),
                ("config", "JSONB" if is_postgres else "TEXT"),
                ("enabled", "BOOLEAN DEFAULT TRUE")
            ],
            "content_items": [
                ("org_id", "INTEGER"),
                ("item_type", "VARCHAR DEFAULT 'note'"),
                ("arabic_text", "TEXT"),
                ("translation", "TEXT"),
                ("meta", "JSONB" if is_postgres else "JSON"),
                ("tags", "JSONB" if is_postgres else "JSON"),
                ("topic", "VARCHAR"),
                ("topics", "JSONB" if is_postgres else "JSON"),
                ("topics_slugs", "JSONB" if is_postgres else "JSON"),
                ("owner_user_id", "INTEGER"),
                ("use_count", "INTEGER DEFAULT 0"),
                ("last_used_at", "TIMESTAMP WITH TIME ZONE"),
                ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")
            ],
            "ig_accounts": [
                ("profile_picture_url", "TEXT"),
                ("fb_page_id", "VARCHAR")
            ],
            "posts": [
                ("intent_type", "VARCHAR"),
                ("target_audience", "VARCHAR"),
                ("source_foundation", "VARCHAR"),
                ("message_hint", "TEXT"),
                ("emotion", "VARCHAR"),
                ("depth", "VARCHAR"),
                ("post_format", "VARCHAR"),
                ("visual_style", "VARCHAR"),
                ("hook_style", "VARCHAR"),
                ("strictness_mode", "VARCHAR DEFAULT 'balanced'")
            ]
        }
        
        for tbl, cols in tables_cols.items():
            for col_name, col_def in cols:
                try:
                    if is_postgres:
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
                    else:
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_def}"))
                    log_startup(f"MIGRATION: Checked/Added {col_name} to {tbl}")
                except Exception:
                    pass

        # Ensure org_id is nullable (important for global)
        if is_postgres:
            try: conn.execute(text("ALTER TABLE content_sources ALTER COLUMN org_id DROP NOT NULL"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE content_items ALTER COLUMN org_id DROP NOT NULL"))
            except Exception: pass

        # 2. DEFINITIVE IG_ACCOUNTS SCHEMA SYNC (Taking Control)
        log_startup("MIGRATION: Syncing ig_accounts table...")
        ig_cols = [
            ("profile_picture_url", "TEXT"),
            ("username", "VARCHAR"),
            ("fb_page_id", "VARCHAR"),
            ("expires_at", "TIMESTAMP WITH TIME ZONE"),
            ("active", "BOOLEAN DEFAULT TRUE")
        ]
        for col, col_def in ig_cols:
            try:
                if is_postgres:
                    conn.execute(text(f"ALTER TABLE ig_accounts ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                else:
                    conn.execute(text(f"ALTER TABLE ig_accounts ADD COLUMN {col} {col_def}"))
                log_startup(f"MIGRATION: Verified/Added {col} to ig_accounts")
            except Exception as e:
                log_startup(f"MIGRATION: Notice on ig_accounts.{col}: {e}")
                pass

    log_startup("MIGRATION: Finished aggressive library schema checks.")

# -------------------------------------------------

# Startup validation checks
REQUIRED_VARS = ["OPENAI_API_KEY", "IG_ACCESS_TOKEN", "DATABASE_URL", "JWT_SECRET"]
missing_vars = [
    var for var in REQUIRED_VARS 
    if not os.environ.get(var) and not getattr(settings, var.lower() if var != "JWT_SECRET" else "secret_key", None)
]
if "DATABASE_URL" not in missing_vars and (not settings.database_url or "sqlite" in settings.database_url):
    missing_vars.append("DATABASE_URL (Production Postgres required)")
if "JWT_SECRET" not in missing_vars and settings.secret_key == "change-me-in-production-for-jwt":
    missing_vars.append("JWT_SECRET (Using default insecure key)")

if missing_vars:
    logger.warning(f"CRITICAL STARTUP WARNING: Missing or unsafe required variables: {', '.join(missing_vars)}")

app = FastAPI(title="Sabeel - Multi-tenant SaaS")

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
        
        # 1. ALLOWED PATHS (Always accessible)
        allowed_prefixes = [
            "/login", "/register", "/auth", "/static", "/api/contact", "/health", "/api-test", "/demo", "/contact"
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
def api_debug_automations(db: Session = Depends(get_db)):
    from app.models import TopicAutomation
    autos = db.query(TopicAutomation).all()
    return [{"id": a.id, "name": a.name, "topic": a.topic_prompt, "last_error": a.last_error} for a in autos]

@app.get("/api/debug-env")
def api_debug_env():
    return {
        "openai_api_key_set": bool(settings.openai_api_key),
        "openai_api_key_len": len(settings.openai_api_key) if settings.openai_api_key else 0,
        "database_url_scheme": settings.database_url.split(":")[0] if settings.database_url else None
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "database": "connected",
        "scheduler": "running",
        "version": "debug-v1"
    }

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

# Serve uploads
os.makedirs(settings.uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")

# Include Routers
app.include_router(public.router)
app.include_router(app_pages.router)
app.include_router(posts.router)
app.include_router(admin.router)
app.include_router(orgs.router)
app.include_router(ig_accounts.router)
app.include_router(ig_accounts.accounts_router)
app.include_router(automations.router)
app.include_router(library.router)
app.include_router(media.router)
app.include_router(auth.router)
app.include_router(auth_google.router)
app.include_router(auth_ig.router)
app.include_router(auth_ig.meta_alias_router)
app.include_router(profiles.router)
app.include_router(sources.router)
app.include_router(admin_library.router)
app.include_router(admin_global_library.router)

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
        superadmin_email = settings.superadmin_email or "Mohammed.Mme7@gmail.com"
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
        from sqlalchemy import text
        with engine.begin() as conn:
            is_postgres = "postgresql" in str(engine.url)
            log_startup(f"STARTUP: Database engine detected: {'Postgres' if is_postgres else 'SQLite'}")
            
            # Update ig_accounts
            ig_cols = [
                ("profile_picture_url", "TEXT"),
                ("username", "VARCHAR"),
                ("fb_page_id", "VARCHAR"),
                ("expires_at", "TIMESTAMP WITH TIME ZONE"),
                ("active", "BOOLEAN DEFAULT TRUE")
            ]
            for col, col_def in ig_cols:
                try:
                    stmt = f"ALTER TABLE ig_accounts ADD COLUMN {'IF NOT EXISTS' if is_postgres else ''} {col} {col_def}"
                    conn.execute(text(stmt))
                    log_startup(f"Migration: Checked column {col} in ig_accounts")
                except Exception: pass
            auto_cols = [
                ("library_topic_slug", "VARCHAR"),
                ("tone", "VARCHAR DEFAULT 'medium'"),
                ("language", "VARCHAR DEFAULT 'english'"),
                ("banned_phrases", "JSONB" if is_postgres else "TEXT"),
                ("include_hashtags", "BOOLEAN DEFAULT TRUE"),
                ("hashtag_set", "JSONB" if is_postgres else "TEXT"),
                ("include_arabic_phrase", "BOOLEAN DEFAULT TRUE"),
                ("posting_mode", "VARCHAR DEFAULT 'schedule'"),
                ("approval_mode", "VARCHAR DEFAULT 'auto_approve'"),
                ("image_mode", "VARCHAR DEFAULT 'reuse_last_upload'"),
                ("use_content_library", "BOOLEAN DEFAULT TRUE"),
                ("avoid_repeat_days", "INTEGER DEFAULT 30"),
                ("content_type", "VARCHAR"),
                ("include_arabic", "BOOLEAN DEFAULT FALSE"),
                ("post_time_local", "VARCHAR"),
                ("timezone", "VARCHAR"),
                ("enrich_with_hadith", "BOOLEAN DEFAULT FALSE"),
                ("hadith_topic", "VARCHAR"),
                ("hadith_source_id", "INTEGER"),
                ("hadith_append_style", "VARCHAR DEFAULT 'short'"),
                ("hadith_max_len", "INTEGER DEFAULT 450"),
                ("media_asset_id", "INTEGER"),
                ("media_tag_query", "JSONB" if is_postgres else "TEXT"),
                ("media_rotation_mode", "VARCHAR DEFAULT 'random'"),
                ("content_profile_id", "INTEGER"),
                ("creativity_level", "INTEGER DEFAULT 3"),
                ("content_seed", "TEXT"),
                ("source_id", "INTEGER"),
                ("source_mode", "VARCHAR DEFAULT 'none'"),
                ("content_seed_mode", "VARCHAR DEFAULT 'none'"),
                ("content_seed_text", "TEXT"),
                ("items_per_post", "INTEGER DEFAULT 1"),
                ("selection_mode", "VARCHAR DEFAULT 'random'"),
                ("last_item_cursor", "VARCHAR"),
                ("library_scope", "JSONB" if is_postgres else "TEXT"),
                ("content_provider_scope", "VARCHAR DEFAULT 'all_sources'")
            ]
            for col, col_def in auto_cols:
                try:
                    stmt = f"ALTER TABLE topic_automations ADD COLUMN {'IF NOT EXISTS' if is_postgres else ''} {col} {col_def}"
                    conn.execute(text(stmt))
                    log_startup(f"Migration: Checked column {col} in topic_automations")
                except Exception: pass
            
            # Update posts
            post_cols = [
                ("is_auto_generated", "BOOLEAN DEFAULT FALSE"),
                ("automation_id", "INTEGER"),
                ("status", "VARCHAR DEFAULT 'submitted'"),
                ("source_type", "VARCHAR DEFAULT 'form'"),
                ("source_text", "TEXT"),
                ("content_item_id", "INTEGER"),
                ("media_asset_id", "INTEGER"),
                ("topic", "VARCHAR"),
                ("post_type", "VARCHAR"),
                ("source_reference", "VARCHAR"),
                ("media_url", "TEXT"),
                ("caption", "TEXT"),
                ("hashtags", "JSONB" if is_postgres else "TEXT"),
                ("alt_text", "TEXT"),
                ("flags", "JSONB DEFAULT '{}'" if is_postgres else "TEXT DEFAULT '{}'"),
                ("last_error", "TEXT"),
                ("scheduled_time", "TIMESTAMP WITH TIME ZONE"),
                ("published_time", "TIMESTAMP WITH TIME ZONE"),
                ("visual_mode", "VARCHAR DEFAULT 'upload'"),
                ("visual_prompt", "TEXT"),
                ("library_item_id", "INTEGER"),
                ("used_source_id", "INTEGER"),
                ("used_content_item_ids", "JSONB" if is_postgres else "TEXT"),
                ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")
            ]
            for col, col_def in post_cols:
                try:
                    stmt = f"ALTER TABLE posts ADD COLUMN {'IF NOT EXISTS' if is_postgres else ''} {col} {col_def}"
                    conn.execute(text(stmt))
                    log_startup(f"Migration: Checked column {col} in posts")
                except Exception: pass

            # Update users
            user_cols = [
                ("name", "VARCHAR"),
                ("is_active", "BOOLEAN DEFAULT TRUE"),
                ("is_superadmin", "BOOLEAN DEFAULT FALSE"),
                ("onboarding_complete", "BOOLEAN DEFAULT FALSE"),
                ("active_org_id", "INTEGER"),
                ("google_id", "VARCHAR"),
                ("has_created_first_post", "BOOLEAN DEFAULT FALSE"),
                ("has_created_first_automation", "BOOLEAN DEFAULT FALSE"),
                ("has_connected_instagram", "BOOLEAN DEFAULT FALSE"),
                ("dismissed_getting_started", "BOOLEAN DEFAULT FALSE"),
                ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")
            ]
            for col, col_def in user_cols:
                try:
                    stmt = f"ALTER TABLE users ADD COLUMN {'IF NOT EXISTS' if is_postgres else ''} {col} {col_def}"
                    conn.execute(text(stmt))
                    log_startup(f"Migration: Checked column {col} in users")
                except Exception: pass

            # Update content_items
            item_cols = [
                ("owner_user_id", "INTEGER"),
                ("item_type", "VARCHAR DEFAULT 'note'"),
                ("arabic_text", "TEXT"),
                ("translation", "TEXT"),
                ("meta", "JSONB DEFAULT '{}'" if is_postgres else "TEXT DEFAULT '{}'"),
                ("topic", "VARCHAR"),
                ("topics", "JSONB DEFAULT '[]'" if is_postgres else "TEXT DEFAULT '[]'"),
                ("topics_slugs", "JSONB DEFAULT '[]'" if is_postgres else "TEXT DEFAULT '[]'"),
                ("source_id", "INTEGER"),
                ("text", "TEXT"),
                ("tags", "JSONB" if is_postgres else "TEXT"),
                ("last_used_at", "TIMESTAMP WITH TIME ZONE"),
                ("use_count", "INTEGER DEFAULT 0")
            ]
            for col, col_def in item_cols:
                try:
                    stmt = f"ALTER TABLE content_items ADD COLUMN {'IF NOT EXISTS' if is_postgres else ''} {col} {col_def}"
                    conn.execute(text(stmt))
                    log_startup(f"Migration: Checked column {col} in content_items")
                except Exception: pass
    except Exception as e:
        log_startup(f"STARTUP: Migration crash: {e}")

    # 3. Aggressive Library Migration
    try:
        run_admin_library_migration()
    except Exception as e:
        log_startup(f"STARTUP: Admin library migration failed: {e}")

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
    import traceback
    log_startup(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "diagnostic": str(exc)}
    )
    
