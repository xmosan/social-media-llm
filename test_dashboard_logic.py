import os
import sys
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, create_engine
from sqlalchemy.orm import sessionmaker
import asyncio

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

DATABASE_URL = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@nozomi.proxy.rlwy.net:45252/railway"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.models import Post, Org, IGAccount, User, OrgMember

def test_dashboard():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        org_id = user.active_org_id if user and user.active_org_id else 1
        org = db.query(Org).filter(Org.id == org_id).first()
        
        # 1. Stats Calculation
        weekly_post_count = db.query(func.count(Post.id)).filter(
            Post.org_id == org_id,
            Post.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        ).scalar() or 0
        
        account_count = db.query(func.count(IGAccount.id)).filter(IGAccount.org_id == org_id).scalar() or 0
        
        # 3. Next Post
        now_utc = datetime.now(timezone.utc)
        next_post = db.query(Post).filter(
            Post.org_id == org_id,
            Post.status == "scheduled",
            Post.scheduled_time > now_utc
        ).order_by(Post.scheduled_time.asc()).first()

        next_post_countdown = "No posts scheduled"
        next_post_time = "--:--"
        next_post_caption = "Create your first automation to see content here."
        
        if next_post:
            diff = next_post.scheduled_time - now_utc
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            next_post_countdown = f"{diff.days}d {hours}h {minutes}m"
            next_post_time = next_post.scheduled_time.strftime("%b %d, %H:%M")
            next_post_caption = f'{next_post.caption[:80]}...' if next_post.caption else "Untitled Post"

            escaped_caption = (next_post.caption or "").replace('`', '\\`').replace('${', '\\${')
            next_post_time_iso = next_post.scheduled_time.isoformat()
            
        print("Dashboard check passed.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_dashboard()
