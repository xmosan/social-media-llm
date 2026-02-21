import os
import sqlalchemy
from sqlalchemy import create_url

# Use the URL retrieved from Railway dash
DATABASE_URL = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@postgres.railway.internal:5432/railway"

# Transform for psycopg if needed (Railway often provides postgres:// which needs postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = sqlalchemy.create_engine(DATABASE_URL)

migrations = [
    "ALTER TABLE topic_automations ADD COLUMN IF NOT EXISTS use_content_library BOOLEAN DEFAULT TRUE",
    "ALTER TABLE topic_automations ADD COLUMN IF NOT EXISTS avoid_repeat_days INTEGER DEFAULT 30",
    "ALTER TABLE topic_automations ADD COLUMN IF NOT EXISTS content_type VARCHAR",
    "ALTER TABLE topic_automations ADD COLUMN IF NOT EXISTS include_arabic BOOLEAN DEFAULT FALSE"
]

with engine.connect() as conn:
    for sql in migrations:
        print(f"Running: {sql}")
        try:
            conn.execute(sqlalchemy.text(sql))
            conn.commit()
            print("Done.")
        except Exception as e:
            print(f"Failed: {e}")

print("Migration complete.")
