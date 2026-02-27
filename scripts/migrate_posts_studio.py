import os
from sqlalchemy import text
from sqlalchemy.engine import create_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not found in environment")
    exit(1)

# Handle possible sqlite/postgresql differences
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def migrate():
    print(f"Connecting to {DATABASE_URL.split('@')[-1]}...")
    with engine.connect() as conn:
        # Add visual_mode
        try:
            conn.execute(text("ALTER TABLE posts ADD COLUMN visual_mode VARCHAR DEFAULT 'upload' NOT NULL"))
            print("Added visual_mode column")
        except Exception as e:
            print(f"visual_mode might already exist: {e}")
            conn.rollback()

        # Add visual_prompt
        try:
            conn.execute(text("ALTER TABLE posts ADD COLUMN visual_prompt TEXT"))
            print("Added visual_prompt column")
        except Exception as e:
            print(f"visual_prompt might already exist: {e}")
            conn.rollback()

        # Add library_item_id
        try:
            conn.execute(text("ALTER TABLE posts ADD COLUMN library_item_id INTEGER REFERENCES content_items(id)"))
            print("Added library_item_id column")
        except Exception as e:
            print(f"library_item_id might already exist: {e}")
            conn.rollback()
            
        conn.commit()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
