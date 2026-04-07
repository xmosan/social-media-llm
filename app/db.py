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

def sync_database_schema():
    """
    Perform a resilient, granular schema sync.
    Every column addition is isolated in its own transaction to prevent rollback cascades.
    """
    is_postgres = engine.drivername and "postgresql" in engine.drivername
    json_type = "JSONB" if is_postgres else "JSON"
    
    # Define all mission-critical columns that might be missing in production
    missing_cols = {
        "ig_accounts": [
            ("profile_picture_url", "TEXT"),
            ("fb_page_id", "VARCHAR"),
            ("expires_at", "TIMESTAMP WITH TIME ZONE" if is_postgres else "TIMESTAMP"),
            ("username", "VARCHAR")
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
            ("strictness_mode", "VARCHAR DEFAULT 'balanced'"),
            ("visual_mode", "VARCHAR DEFAULT 'upload'"),
            ("visual_prompt", "TEXT"),
            ("library_item_id", "INTEGER")
        ],
        "content_items": [
            ("item_type", "VARCHAR DEFAULT 'note'"),
            ("arabic_text", "TEXT"),
            ("translation", "TEXT"),
            ("meta", json_type),
            ("tags", json_type),
            ("topic", "VARCHAR"),
            ("topics", json_type),
            ("topics_slugs", json_type)
        ],
        "content_sources": [
            ("category", "VARCHAR"),
            ("description", "TEXT"),
            ("config", json_type),
            ("enabled", "BOOLEAN DEFAULT TRUE")
        ]
    }

    print(f"SCHEMA SYNC: Starting resilient sync (DB: {'Postgres' if is_postgres else 'SQLite'})...")
    
    for tbl, cols in missing_cols.items():
        for col, col_def in cols:
            # Use a fresh transaction for EVERY command
            try:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                    else:
                        # SQLite doesn't support IF NOT EXISTS for ADD COLUMN, so we rely on the try/except
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def}"))
                # print(f"  [OK] {tbl}.{col}")
            except Exception as e:
                # Silently skip if column already exists or other non-critical error
                # print(f"  [SKIP] {tbl}.{col} (Reason: {e})")
                pass

    # Ensure Nullability for global content
    try:
        with engine.begin() as conn:
            if is_postgres:
                conn.execute(text("ALTER TABLE content_sources ALTER COLUMN org_id DROP NOT NULL"))
                conn.execute(text("ALTER TABLE content_items ALTER COLUMN org_id DROP NOT NULL"))
    except Exception:
        pass
    
    print("SCHEMA SYNC: Resilient sync complete.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()