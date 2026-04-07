import os
import sys
import logging
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DeepDebug")

# Add the parent directory to sys.path to allow importing from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import engine, DATABASE_URL

def censor_url(url: str) -> str:
    """Censored URL for safe display in logs."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}"
    except:
        return "[REDACTED]"

def get_current_columns(conn, table_name: str) -> list:
    """List all column names for a given table via information_schema."""
    query = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = :table_name
        ORDER BY ordinal_position;
    """)
    result = conn.execute(query, {"table_name": table_name})
    return [row[0] for row in result.fetchall()]

def debug_schema():
    logger.info("--- STARTING DEEP DB DIAGNOSTIC (POSTGRES) ---")
    logger.info(f"Targeting DATABASE_URL: {censor_url(DATABASE_URL)}")
    
    with engine.connect() as conn:
        # Step 1: Confirm Table Presence
        logger.info("Step 1: Inspecting current schema state for 'ig_accounts'...")
        columns_before = get_current_columns(conn, "ig_accounts")
        if not columns_before:
            logger.error("TABLE 'ig_accounts' NOT FOUND! Initializing it now...")
            # Table might be missing completely in this schema?
            # Create it just in case something is fundamentally broken
            conn.execute(text("CREATE TABLE IF NOT EXISTS ig_accounts (id SERIAL PRIMARY KEY, name TEXT, ig_user_id TEXT, org_id INTEGER)"))
            conn.commit()
            columns_before = get_current_columns(conn, "ig_accounts")

        logger.info(f"Current columns in 'ig_accounts': {', '.join(columns_before)}")
        
        # Step 2: Force Synchronization
        logger.info("Step 2: Forcing column synchronization...")
        target_cols = [
            ("fb_page_id", "VARCHAR"),
            ("profile_picture_url", "TEXT"),
            ("expires_at", "TIMESTAMP WITH TIME ZONE")
        ]
        
        for col_name, col_def in target_cols:
            if col_name in columns_before:
                logger.info(f"Column '{col_name}' already exists. Skipping.")
                continue
                
            logger.info(f"Adding missing column: {col_name} ({col_def})")
            try:
                # We use engine.begin() / conn.execute() inside the connection but manually commit to be absolutely safe
                conn.execute(text(f"ALTER TABLE ig_accounts ADD COLUMN {col_name} {col_def}"))
                logger.info(f"Migration successful for {col_name}.")
            except Exception as e:
                logger.error(f"Migration FAILED for {col_name}: {e}")
                
        # Manually commit all changes
        conn.commit()
        logger.info("Changes committed to database.")

        # Step 3: Final Verification
        logger.info("Step 3: Verification Audit...")
        columns_after = get_current_columns(conn, "ig_accounts")
        logger.info(f"POST-MIGRATION columns: {', '.join(columns_after)}")
        
        if "profile_picture_url" in columns_after:
            logger.info("--- VALIDATION SUCCESS: Schema is now stable. ---")
        else:
            logger.error("--- VALIDATION FAILED: The column was not added. Check for read-only access or schema locks. ---")

if __name__ == "__main__":
    try:
        debug_schema()
    except Exception as e:
        logger.error(f"Fatal error during diagnostic: {e}")
        sys.exit(1)
