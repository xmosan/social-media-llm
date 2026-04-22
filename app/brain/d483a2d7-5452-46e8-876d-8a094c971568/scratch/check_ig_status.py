import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.models import IGAccount, TopicAutomation

def check_account():
    db = SessionLocal()
    try:
        # Find the automation ID for "weekly reminder"
        auto = db.query(TopicAutomation).filter(TopicAutomation.name == "weekly reminder").first()
        if not auto:
            print(" x Could not find automation 'weekly reminder'")
            return
            
        acc = db.query(IGAccount).filter(IGAccount.id == auto.ig_account_id).first()
        if not acc:
            print(f" x Could not find Instagram account for ID {auto.ig_account_id}")
            return
            
        print(f"Instagram Account: {acc.username or acc.name}")
        print(f" - ID: {acc.ig_user_id}")
        print(f" - FB Page ID: {acc.fb_page_id}")
        print(f" - Active: {acc.active}")
        
        has_token = bool(acc.access_token)
        print(f" - Access Token Present: {has_token}")
        
        # Check if the token is likely a long-lived one (usually longer than short-lived)
        if has_token:
            print(f" - Token Length: {len(acc.access_token)}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_account()
