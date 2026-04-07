import os
import sys
import time
from sqlalchemy import text, create_engine

# Add the parent directory to sys.path to allow importing from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def censor_url(url: str) -> str:
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.hostname}:{p.port}/{p.path}"
    except:
        return "[REDACTED]"

def run_migration():
    """
    Forceful migration script that runs in the Docker container lifecycle.
    """
    print("--- FORCE MIGRATION V3 STARTING ---")
    
    # Try to load from .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("WARNING: DATABASE_URL not found in environment! Falling back to SQLite.")
        # Fallback to saas.db to match app/db.py
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        database_url = f"sqlite:///{os.path.join(base_dir, 'saas.db')}"
        
    print(f"Connecting to: {censor_url(database_url)}")
    
    # Standard DB URL cleanup
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_engine(database_url, pool_pre_ping=True)
    
    retries = 5
    for i in range(retries):
        try:
            with engine.begin() as conn:
                is_postgres = "postgresql" in engine.name
                
                print(f"Schema check on Table: ig_accounts (Dialect: {engine.name}, Driver: {engine.url.drivername})")
                
                # 1. Ensure Table
                id_col = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS ig_accounts (
                        id {id_col},
                        org_id INTEGER,
                        name VARCHAR,
                        ig_user_id VARCHAR,
                        access_token TEXT,
                        active BOOLEAN DEFAULT TRUE,
                        timezone VARCHAR DEFAULT 'America/Detroit',
                        daily_post_time VARCHAR DEFAULT '09:00',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                # 2. Sync Columns
                cols = [
                    ("fb_page_id", "VARCHAR"),
                    ("profile_picture_url", "TEXT"),
                    ("expires_at", "TIMESTAMP WITH TIME ZONE")
                ]
                
                for col, col_def in cols:
                    try:
                        if is_postgres:
                            conn.execute(text(f"ALTER TABLE ig_accounts ADD COLUMN IF NOT EXISTS {col} {col_def}"))
                        else:
                            try: conn.execute(text(f"ALTER TABLE ig_accounts ADD COLUMN {col} {col_def}"))
                            except: pass
                        print(f"Verified column {col} is present.")
                    except Exception as e:
                        print(f"Notice on {col}: {e}")
                
            print("--- FORCE MIGRATION V3 SUCCESS ---")
            return
        except Exception as e:
            print(f"Migration attempt {i+1} failed: {e}")
            if i < retries - 1:
                time.sleep(2)
            else:
                print("FATAL: Migration could not be completed.")
                sys.exit(1)

if __name__ == "__main__":
    run_migration()
