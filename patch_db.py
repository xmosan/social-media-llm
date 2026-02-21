import psycopg2
import sys

# Railway DB URL
DATABASE_URL = "postgresql://postgres:SOPYFzWCHLpWhPZJvUfEwDqGVpeIjtgN@nozomi.proxy.rlwy.net:45252/railway"

def run_migration():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        print("Adding content_item_id to posts table...")
        cur.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS content_item_id INTEGER REFERENCES content_items(id);")
        
        print("Ensuring content_items has org_id index...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_content_items_org_id ON content_items(org_id);")

        conn.commit()
        print("Migration successful.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
