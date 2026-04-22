# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import os
import time
import logging
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# --- CORE ARCHITECTURE: POSTGRESQL MANDATORY ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")

def _create_engine_with_retries(db_url: str):
    if not db_url or "postgresql" not in db_url and "postgres" not in db_url:
        logger.error("CRITICAL: DATABASE_URL is missing or does not point to a PostgreSQL instance.")
        # We allow it to fail here, but the app will crash on startup check.
        raise ValueError("This project has moved fully to PostgreSQL. sqlite is no longer supported for production.")

    # Driver fixes
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if db_url.startswith("postgresql://") and "+psycopg" not in db_url:
        # Defaulting to psycopg (preferred for PG 16+)
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Production-grade pooling
    engine = create_engine(
        db_url,
        pool_size=15,
        max_overflow=25,
        pool_recycle=3600,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10}
    )
    
    retries = 3
    backoff = 2
    for attempt in range(retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Database connection failed. Retrying in {backoff}s... ({e})")
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(f"Failed all DB connection attempts for {db_url}.")
                raise e

# Initialize the global engine
try:
    if not DATABASE_URL:
        # DIAGNOSTIC DUMP: Help user identify why env var is missing
        env_keys = list(os.environ.keys())
        logger.error(f"FATAL: DATABASE_URL is missing in environment. Visible keys: {env_keys}")
        
        # STEP 1: DATABASE CONNECTION VALIDATION
        raise RuntimeError(
            "DATABASE_URL is missing. Sabeel Studio requires PostgreSQL for production. "
            "Please ensure your platform (Railway/Docker) has a DATABASE_URL variable set."
        )
         
    engine = _create_engine_with_retries(DATABASE_URL)
    print("✅ Connected to PostgreSQL Matrix")
    # Log for production monitoring
    logger.info("[DB] Connected to PostgreSQL Matrix")
except Exception as e:
    logger.critical(f"DATABASE INITIALIZATION FAILED: {e}")
    # In a full Postgres move, we don't have a secondary fallback anymore.
    raise e

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def sync_database_schema(log_func=None):
    """
    Perform a resilient, granular schema sync for PostgreSQL.
    """
    def _log(msg):
        if log_func: log_func(msg)
        print(f"SCHEMA SYNC: {msg}")

    _log(f"Starting native Postgres sync (Dialect: {engine.dialect.name}, Driver: {engine.driver})")
    
    # Constants for PG
    json_type = "JSONB" if engine.dialect.name == "postgresql" else "JSON"
    ts_type = "TIMESTAMP WITH TIME ZONE"
    
    missing_cols = {
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
            ("strictness_mode", "VARCHAR DEFAULT 'balanced'"),
            ("source_metadata", json_type),
            ("card_message", json_type),
            ("caption_message", json_type)
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
            ("topic_pool", json_type),
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
            ("cadence", "VARCHAR DEFAULT 'daily'"),
            ("posts_per_day", "INTEGER DEFAULT 1"),
            ("post_spacing_hours", "INTEGER DEFAULT 4"),
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
            ("verification_mode", "VARCHAR DEFAULT 'standard'"),
            ("style_dna_id", "INTEGER"),
            ("style_dna_pool", json_type),
            ("automation_version", "INTEGER DEFAULT 1")
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
            ("tags", "VARCHAR DEFAULT ''"),
            ("admin_notes", "TEXT")
        ]
    }

    for key, cols in missing_cols.items():
        tbl = key if not key.endswith("_extended") else key.split("_")[0]
        for col, col_def in cols:
            try:
                with engine.begin() as conn:
                    # Native Postgres syntax
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                _log(f"SUCCESS: {tbl}.{col} added/verified")
            except Exception as e:
                _log(f"DETAIL: {tbl}.{col} skip or error: {str(e)[:100]}")
                pass

    # Ensure Nullability for global content
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE content_sources ALTER COLUMN org_id DROP NOT NULL"))
            conn.execute(text("ALTER TABLE content_items ALTER COLUMN org_id DROP NOT NULL"))
            _log("SUCCESS: org_id nullability updated")
    except Exception as e:
        _log(f"DETAIL: Nullability update error: {e}")
    
    _log("PostgreSQL native sync complete.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()