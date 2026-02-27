import os
import sys
import calendar
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
        
        print("Starting calendar logic...")
        # Calendar Construction (Next 7 days)
        calendar_headers = ""
        calendar_days = ""
        today = datetime.now(timezone.utc)
        for i in range(7):
            day = today + timedelta(days=i)
            calendar_headers += f'<div class="py-2 text-[8px] font-black text-center uppercase tracking-widest text-muted">{day.strftime("%a")}</div>'
            
            # Count posts for this day
            day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            post_count = db.query(func.count(Post.id)).filter(
                Post.org_id == org_id,
                Post.scheduled_time >= day_start,
                Post.scheduled_time < day_end
            ).scalar() or 0
            
            indicator = ""
            if post_count > 0:
                indicator = f'<div class="mt-2 w-1.5 h-1.5 rounded-full bg-brand"></div>'
                
            calendar_days += f"""
            <div class="border-r border-b border-white/5 flex flex-col items-center justify-center relative">
              <span class="text-[10px] font-black text-white/40">{day.day}</span>
              {indicator}
            </div>
            """
            
        print("Calendar logic passed.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_dashboard()
