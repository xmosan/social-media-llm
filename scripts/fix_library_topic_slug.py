import sqlalchemy
import sys

URL = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@nozomi.proxy.rlwy.net:45252/railway"

engine = sqlalchemy.create_engine(URL)
with engine.begin() as conn:
    print("Executing ALTER TABLE...")
    conn.execute(sqlalchemy.text("ALTER TABLE topic_automations ADD COLUMN IF NOT EXISTS library_topic_slug VARCHAR"))
    print("Done.")

