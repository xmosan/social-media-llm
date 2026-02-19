import os
import sys
from sqlalchemy import create_url, create_engine
from sqlalchemy.orm import sessionmaker

# Add parent dir to path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models import Base, Org, User, ApiKey, IGAccount, TopicAutomation, Post

# CONFIGURATION
# Set these in your environment before running
SQLITE_URL = os.getenv("SQLITE_URL", "sqlite:///./saas.db")
PG_URL = os.getenv("PG_URL")  # e.g., postgresql://user:pass@host:port/dbname

if not PG_URL:
    print("ERROR: PG_URL environment variable is required.")
    sys.exit(1)

def migrate():
    print(f"--- MIGRATION START: {SQLITE_URL} -> PostgreSQL ---")
    
    sqlite_engine = create_engine(SQLITE_URL)
    pg_engine = create_engine(PG_URL)
    
    # Create tables in PG if they don't exist
    print("Bootstrap: Creating schemas in PostgreSQL...")
    Base.metadata.create_all(pg_engine)
    
    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)
    
    with SqliteSession() as src, PgSession() as dst:
        # 1. ORGS
        print("Migrating: Organizations...")
        orgs = src.query(Org).all()
        for o in orgs:
            dst.merge(o)
        dst.commit()
        print(f"Done: {len(orgs)} organizations.")
        
        # 2. USERS
        print("Migrating: Users...")
        users = src.query(User).all()
        for u in users:
            dst.merge(u)
        dst.commit()
        print(f"Done: {len(users)} users.")
        
        # 3. API KEYS
        print("Migrating: API Keys...")
        keys = src.query(ApiKey).all()
        for k in keys:
            dst.merge(k)
        dst.commit()
        print(f"Done: {len(keys)} keys.")
        
        # 4. IG ACCOUNTS
        print("Migrating: Instagram Slots...")
        accs = src.query(IGAccount).all()
        for a in accs:
            dst.merge(a)
        dst.commit()
        print(f"Done: {len(accs)} accounts.")
        
        # 5. AUTOMATIONS
        print("Migrating: Topic Automations...")
        autos = src.query(TopicAutomation).all()
        for a in autos:
            dst.merge(a)
        dst.commit()
        print(f"Done: {len(autos)} automations.")
        
        # 6. POSTS (Optional: might be heavy, but let's take them)
        print("Migrating: Post History...")
        posts = src.query(Post).all()
        for p in posts:
            dst.merge(p)
        dst.commit()
        print(f"Done: {len(posts)} posts.")

    print("--- MIGRATION SUCCESSFUL ---")

if __name__ == "__main__":
    migrate()
