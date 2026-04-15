import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def run_diagnostics():
    with engine.connect() as conn:
        print("--- DB DIAGNOSTICS ---")
        tables = ["orgs", "users", "content_sources", "content_items", "library_topic_synonyms", "user_interactions"]
        for table in tables:
            try:
                res = conn.execute(text(f"SELECT count(*) FROM {table}"))
                count = res.scalar()
                print(f"Table {table}: {count} rows")
            except Exception as e:
                print(f"Table {table}: Error checking count - {e}")

        print("\n--- CONTENT SOURCES ---")
        try:
            res = conn.execute(text("SELECT id, name, org_id, source_type FROM content_sources LIMIT 10"))
            for row in res:
                print(row)
        except Exception as e:
            print(f"Error checking sources: {e}")

if __name__ == "__main__":
    run_diagnostics()
