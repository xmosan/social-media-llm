import os
import sys
from sqlalchemy import create_engine, text

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

def run_migration():
    print("Running migration for Admin Library Manager...")
    db_url = settings.database_url
    if not db_url:
        print("ERROR: DATABASE_URL not found.")
        return

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(db_url)
    is_postgres = "postgresql" in engine.drivername

    with engine.begin() as conn:
        # 1. Update content_sources
        source_cols = [
            ("category", "VARCHAR"),
            ("description", "TEXT")
        ]
        print("Migrating content_sources...")
        for col, col_def in source_cols:
            try:
                if is_postgres:
                    conn.execute(text(f"ALTER TABLE content_sources ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                else:
                    conn.execute(text(f"ALTER TABLE content_sources ADD COLUMN {col} {col_def}"))
                print(f"  OK: {col}")
            except Exception as e:
                print(f"  SKIP/FAIL: {col} -> {e}")

        # SQLite doesn't support ALTER COLUMN DROP NOT NULL easily.
        # For development, we hope most queries will just work or we'll handle it in the ORM.
        # But if we want to be safe in Postgres:
        if is_postgres:
            try:
                conn.execute(text("ALTER TABLE content_sources ALTER COLUMN org_id DROP NOT NULL"))
                print("  OK: content_sources.org_id -> nullable")
            except Exception as e:
                print(f"  FAIL: content_sources.org_id -> nullable: {e}")

        # 2. Update content_items
        item_cols = [
            ("item_type", "VARCHAR DEFAULT 'note'"),
            ("arabic_text", "TEXT"),
            ("translation", "TEXT"),
            ("meta", "JSONB" if is_postgres else "JSON")
        ]
        print("Migrating content_items...")
        for col, col_def in item_cols:
            try:
                if is_postgres:
                    conn.execute(text(f"ALTER TABLE content_items ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                else:
                    conn.execute(text(f"ALTER TABLE content_items ADD COLUMN {col} {col_def}"))
                print(f"  OK: {col}")
            except Exception as e:
                print(f"  SKIP/FAIL: {col} -> {e}")

        if is_postgres:
            try:
                conn.execute(text("ALTER TABLE content_items ALTER COLUMN org_id DROP NOT NULL"))
                print("  OK: content_items.org_id -> nullable")
            except Exception as e:
                print(f"  FAIL: content_items.org_id -> nullable: {e}")

    print("Migration finished.")

if __name__ == "__main__":
    run_migration()
