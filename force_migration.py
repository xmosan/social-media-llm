import os
from sqlalchemy import create_engine, text
from app.config import settings

def run_migration():
    print("Forcing Migration for Admin Enhancements...")
    db_url = settings.database_url
    if not db_url:
        print("ERROR: DATABASE_URL not found in environment.")
        return

    # Handle postgres:// vs postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)
    
    with engine.begin() as conn:
        # 1. Update topic_automations
        auto_cols = [
            ("enrich_with_hadith", "BOOLEAN DEFAULT FALSE"),
            ("hadith_topic", "VARCHAR"),
            ("hadith_source_id", "INTEGER"),
            ("hadith_append_style", "VARCHAR DEFAULT 'short'"),
            ("hadith_max_len", "INTEGER DEFAULT 450"),
            ("media_asset_id", "INTEGER"),
            ("media_tag_query", "JSONB"),
            ("media_rotation_mode", "VARCHAR DEFAULT 'random'")
        ]
        print("Migrating topic_automations...")
        for col, col_def in auto_cols:
            try:
                # Using IF NOT EXISTS if it's postgres
                if "postgresql" in engine.drivername:
                    conn.execute(text(f"ALTER TABLE topic_automations ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                else:
                    conn.execute(text(f"ALTER TABLE topic_automations ADD COLUMN {col} {col_def}"))
                print(f"  OK: {col}")
            except Exception as e:
                print(f"  SKIP/FAIL: {col} -> {e}")
        
        # 2. Update posts
        post_cols = [
            ("media_asset_id", "INTEGER")
        ]
        print("Migrating posts...")
        for col, col_def in post_cols:
            try:
                if "postgresql" in engine.drivername:
                    conn.execute(text(f"ALTER TABLE posts ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                else:
                    conn.execute(text(f"ALTER TABLE posts ADD COLUMN {col} {col_def}"))
                print(f"  OK: {col}")
            except Exception as e:
                print(f"  SKIP/FAIL: {col} -> {e}")

    print("Migration attempt finished.")

if __name__ == "__main__":
    run_migration()
