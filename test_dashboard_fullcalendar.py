import os
import sys
import calendar
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

DATABASE_URL = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@nozomi.proxy.rlwy.net:45252/railway"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.models import Post, Org, User

def test_calendar():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        org_id = user.active_org_id if user and user.active_org_id else 1
        org = db.query(Org).filter(Org.id == org_id).first()
        
        today = datetime.now(timezone.utc)
        year = today.year
        month = today.month
        
        cal = calendar.Calendar(firstweekday=6)
        month_days = cal.monthdayscalendar(year, month)
        
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
            
        posts_query = db.query(Post).filter(
            Post.org_id == org_id,
            Post.scheduled_time >= month_start,
            Post.scheduled_time < month_end
        ).all()
        
        posts_by_day = {}
        for p in posts_query:
            if not p.scheduled_time: continue
            d_key = p.scheduled_time.day
            posts_by_day[d_key] = posts_by_day.get(d_key, 0) + 1
            
        calendar_grid = ""
        for week in month_days:
            for day in week:
                if day == 0:
                    calendar_grid += '<div class="p-4 border-r border-b border-white/5 opacity-0"></div>'
                else:
                    count = posts_by_day.get(day, 0)
                    calendar_grid += f"<div>Day {day} Count {count}</div>"
                    print(f"Processed day {day}")
                    
        print("Calendar page logic passed.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_calendar()
