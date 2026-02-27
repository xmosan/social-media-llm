import os
import sys
import asyncio
from unittest.mock import MagicMock

# Mock openai so it doesn't crash on import due to local env corruption
sys.modules['openai'] = MagicMock()

os.environ["DATABASE_URL"] = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@nozomi.proxy.rlwy.net:45252/railway"
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.db import SessionLocal
from app.models import User
from app.routes.app_pages import app_dashboard_page

async def test_all_users():
    db = SessionLocal()
    users = db.query(User).all()
    print(f"Testing {len(users)} users...")
    
    for user in users:
        try:
            print(f"Testing for user {user.email} (ID: {user.id})")
            if not user.active_org_id:
                # Mock the active org fix that happens in route
                from app.models import OrgMember
                membership = db.query(OrgMember).filter(OrgMember.user_id == user.id).first()
                if membership:
                    user.active_org_id = membership.org_id
                    
            res = await app_dashboard_page(user=user, db=db)
            print(f"  Success! Length: {len(res.body)}")
        except Exception as e:
            print(f"  CRASH on user {user.email}:")
            import traceback
            traceback.print_exc()
            
    db.close()

if __name__ == "__main__":
    asyncio.run(test_all_users())
