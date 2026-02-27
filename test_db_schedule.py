import os
import sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Post, Org

DATABASE_URL = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@nozomi.proxy.rlwy.net:45252/railway"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_dashboard():
    db = SessionLocal()
    try:
        org = db.query(Org).first()
        if not org:
            print("No org found.")
            return

        now_utc = datetime.now(timezone.utc)
        
        # Dashboard Next Post Query
        next_post = db.query(Post).filter(
            Post.org_id == org.id,
            Post.status == "scheduled",
            Post.scheduled_time > now_utc
        ).order_by(Post.scheduled_time.asc()).first()
        
        print(f"Current UTC time: {now_utc}")
        if next_post:
            print(f"Next Scheduled Post Found: {next_post.id}")
            print(f"Caption: {next_post.caption[:30] if next_post.caption else ''}")
            print(f"Scheduled Time: {next_post.scheduled_time}")
            print(f"Is > now_utc: {next_post.scheduled_time > now_utc}")
        else:
            print("No next scheduled post found.")
            
        print("\nAll Scheduled Posts:")
        all_scheduled = db.query(Post).filter(Post.status == "scheduled").all()
        for p in all_scheduled:
            print(f"- ID: {p.id}, Time: {p.scheduled_time}, Caption: {p.caption[:30] if p.caption else ''}, >now: {p.scheduled_time > now_utc}")
    finally:
        db.close()

if __name__ == "__main__":
    check_dashboard()
