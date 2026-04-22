import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.models import Post, TopicAutomation

def check_history():
    db = SessionLocal()
    try:
        # Find the automation ID for "weekly reminder"
        auto = db.query(TopicAutomation).filter(TopicAutomation.name == "weekly reminder").first()
        if not auto:
            print(" x Could not find automation 'weekly reminder'")
            return
            
        print(f"Checking history for Automation: {auto.name} (ID: {auto.id})")
        
        # Get last 5 posts
        posts = db.query(Post).filter(Post.automation_id == auto.id).order_by(Post.created_at.desc()).limit(5).all()
        
        for p in posts:
            print(f"\n[Post {p.id}] Status: {p.status} | Created: {p.created_at}")
            if p.flags:
                # Ensure it's a dict
                flags = p.flags if isinstance(p.flags, dict) else json.loads(p.flags or "{}")
                print(f" Flags: {json.dumps(flags, indent=2)}")
            if p.last_error:
                print(f" Last Error Field: {p.last_error}")
                
    finally:
        db.close()

if __name__ == "__main__":
    check_history()
