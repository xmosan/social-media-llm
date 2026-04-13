# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use absolute path for SQLite to avoid permission issues with relative paths in some environments
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# We'll use a new DB name to avoid blocked "app.db" if it has OS-level locks
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "saas.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

import time
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

def _create_engine_with_retries(db_url: str):
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if db_url.startswith("postgresql://") and "+psycopg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    test_engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    
    retries = 3
    backoff = 2
    for attempt in range(retries):
        try:
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return test_engine
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Database connection failed. Retrying in {backoff}s... ({e})")
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(f"Failed all DB connection attempts for {db_url}.")
                raise e

try:
    engine = _create_engine_with_retries(DATABASE_URL)
    print(f"Connecting to DB: {DATABASE_URL}")
except Exception as primary_e:
    secondary_url = os.getenv("SECONDARY_DATABASE_URL")
    if secondary_url:
        logger.warning(f"PRIMARY DATABASE ({DATABASE_URL}) FAILED. Falling back to SECONDARY_DATABASE_URL.")
        engine = _create_engine_with_retries(secondary_url)
        # Update DATABASE_URL so downstream things (like sqlite pragma) use the new one
        DATABASE_URL = secondary_url
    else:
        raise primary_e

# Enable WAL mode for SQLite to prevent "database is locked" errors during concurrent access
if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def sync_database_schema(log_func=None):
    """
    Perform a resilient, granular schema sync.
    Absolute source of truth for all table columns. 
    """
    def _log(msg):
        if log_func: log_func(msg)
        print(f"SCHEMA SYNC: {msg}")

    # Use dialect name which is more reliable than drivername in SQLAlchemy 2.0
    is_postgres = engine.dialect.name == "postgresql"
    json_type = "JSONB" if is_postgres else "JSON"
    ts_type = "TIMESTAMP WITH TIME ZONE" if is_postgres else "TIMESTAMP"
    
    _log(f"Starting resilient sync (Dialect: {engine.dialect.name}, Driver: {engine.driver})")
    
    missing_cols = {
        "posts": [
            # INTELLIGENCE ENGINE FIELDS (Priority Zero)
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
        ],
        "users": [
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
            ("created_at", ts_type + " DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", ts_type + " DEFAULT CURRENT_TIMESTAMP")
        ],
        "ig_accounts": [
            ("profile_picture_url", "TEXT"),
            ("username", "VARCHAR"),
            ("fb_page_id", "VARCHAR"),
            ("expires_at", ts_type),
            ("active", "BOOLEAN DEFAULT TRUE")
        ],
        "topic_automations": [
            ("library_topic_slug", "VARCHAR"),
            ("tone", "VARCHAR DEFAULT 'medium'"),
            ("language", "VARCHAR DEFAULT 'english'"),
            ("banned_phrases", json_type),
            ("include_hashtags", "BOOLEAN DEFAULT TRUE"),
            ("hashtag_set", json_type),
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
            ("media_tag_query", json_type),
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
            ("library_scope", json_type),
            ("content_provider_scope", "VARCHAR DEFAULT 'all_sources'"),
            ("pillars", json_type),
            ("frequency", "VARCHAR DEFAULT 'daily'"),
            ("custom_days", json_type),
            ("source_mode", "VARCHAR DEFAULT 'balanced'"),
            ("tone_style", "VARCHAR DEFAULT 'deep'"),
            ("verification_mode", "VARCHAR DEFAULT 'standard'")
        ],
        "posts_extended": [
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
            ("hashtags", json_type),
            ("alt_text", "TEXT"),
            ("flags", json_type + " DEFAULT '{}'"),
            ("last_error", "TEXT"),
            ("scheduled_time", ts_type),
            ("published_time", ts_type),
            ("visual_mode", "VARCHAR DEFAULT 'upload'"),
            ("visual_prompt", "TEXT"),
            ("library_item_id", "INTEGER"),
            ("used_source_id", "INTEGER"),
            ("used_content_item_ids", json_type),
            ("created_at", ts_type + " DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", ts_type + " DEFAULT CURRENT_TIMESTAMP")
        ],
        "content_items": [
            ("owner_user_id", "INTEGER"),
            ("item_type", "VARCHAR DEFAULT 'note'"),
            ("arabic_text", "TEXT"),
            ("translation", "TEXT"),
            ("meta", json_type + " DEFAULT '{}'"),
            ("tags", json_type),
            ("topic", "VARCHAR"),
            ("topics", json_type + " DEFAULT '[]'"),
            ("topics_slugs", json_type + " DEFAULT '[]'"),
            ("source_id", "INTEGER"),
            ("text", "TEXT"),
            ("last_used_at", ts_type),
            ("use_count", "INTEGER DEFAULT 0")
        ],
        "content_sources": [
            ("category", "VARCHAR"),
            ("description", "TEXT"),
            ("config", json_type + " DEFAULT '{}'"),
            ("enabled", "BOOLEAN DEFAULT TRUE")
        ],
        "waitlist_entries": [
            ("ip_address", "VARCHAR"),
            ("user_agent", "VARCHAR"),
            ("referrer", "VARCHAR"),
            ("utm_source", "VARCHAR"),
            ("utm_medium", "VARCHAR"),
            ("utm_campaign", "VARCHAR"),
            ("tags", "VARCHAR DEFAULT ''")
        ]
    }

    for key, cols in missing_cols.items():
        tbl = key if not key.endswith("_extended") else key.split("_")[0]
        for col, col_def in cols:
            try:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                    else:
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def}"))
                _log(f"SUCCESS: {tbl}.{col} added/verified")
            except Exception as e:
                _log(f"DETAIL: {tbl}.{col} skip or error: {str(e)[:100]}")
                pass

    # Ensure Nullability for global content
    try:
        with engine.begin() as conn:
            if is_postgres:
                conn.execute(text("ALTER TABLE content_sources ALTER COLUMN org_id DROP NOT NULL"))
                conn.execute(text("ALTER TABLE content_items ALTER COLUMN org_id DROP NOT NULL"))
                _log("SUCCESS: org_id nullability updated")
    except Exception as e:
        _log(f"DETAIL: Nullability update error: {e}")
    
    _log("Resilient sync complete.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()