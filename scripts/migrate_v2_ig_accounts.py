import os
import sys
import logging
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

# Add the parent directory to sys.path to allow importing from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import engine

def migrate():
    """
    Properly migrates the ig_accounts table to include all required columns for the 
    Selection OAuth flow. This replaces previous 'auto-hacks' with a stable script.
    """
    logger.info("Starting Instagram Accounts Schema Migration (v2)...")
    
    is_postgres = "postgresql" in engine.drivername
    
    with engine.begin() as conn:
        # 1. Ensure Table Exists
        logger.info("Step 1: Checking for ig_accounts table...")
        id_col = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS ig_accounts (
                id {id_col},
                org_id INTEGER REFERENCES orgs(id),
                name VARCHAR NOT NULL,
                ig_user_id VARCHAR NOT NULL,
                access_token TEXT NOT NULL,
                active BOOLEAN DEFAULT TRUE,
                timezone VARCHAR DEFAULT 'America/Detroit',
                daily_post_time VARCHAR DEFAULT '09:00',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # 2. Add New Columns
        logger.info("Step 2: Syncing columns...")
        
        # Define columns to ensure
        target_cols = [
            ("profile_picture_url", "TEXT"),
            ("fb_page_id", "VARCHAR"),
            ("expires_at", "TIMESTAMP WITH TIME ZONE")
        ]
        
        for col_name, col_def in target_cols:
            try:
                if is_postgres:
                    # Postgres supports IF NOT EXISTS for ADD COLUMN
                    conn.execute(text(f"ALTER TABLE ig_accounts ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
                else:
                    # SQLite does not support IF NOT EXISTS, we use try/except block
                    try:
                        conn.execute(text(f"ALTER TABLE ig_accounts ADD COLUMN {col_name} {col_def}"))
                    except Exception as e:
                        if "duplicate column name" in str(e).lower():
                            logger.info(f"Column '{col_name}' already exists in SQLite.")
                            continue
                        raise e
                
                logger.info(f"Successfully synced column: {col_name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"Column '{col_name}' already exists.")
                else:
                    logger.error(f"Failed to sync column '{col_name}': {e}")
                    raise e

    logger.info("Migration (v2) complete. The ig_accounts table is now fully synchronized with the model.")

if __name__ == "__main__":
    try:
        migrate()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
