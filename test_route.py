import asyncio
from app.db import SessionLocal
from app.routes.library import list_library_entries
from app.models import User

def test_library():
    db = SessionLocal()
    # Mock user
    user = db.query(User).first()
    if not user:
        print("No user found")
        return
    
    print(f"Testing library entries for user {user.email}")
    try:
        entries = list_library_entries(
            topic="worship", 
            scope=None, 
            db=db, 
            user=user
        )
        print(f"Success! Found {len(entries)} entries.")
    except Exception as e:
        print(f"Exception caught: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_library()
