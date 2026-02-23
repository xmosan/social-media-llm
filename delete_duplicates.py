import os
import sys

# Must add current dir to path to find app module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.db import SessionLocal
from app.models import IGAccount

def clean_duplicates():
    db = SessionLocal()
    try:
        # Find all accounts named Sabeelullah
        accounts = db.query(IGAccount).filter(IGAccount.name == "Sabeelullah").all()
        
        if not accounts:
            print("No Sabeelullah accounts found.")
            return

        # Keep the first one, delete the rest
        keeper = accounts[0]
        deleted_count = 0
        
        for acc in accounts[1:]:
            print(f"Deleting duplicate account ID {acc.id}")
            db.delete(acc)
            deleted_count += 1
            
        db.commit()
        print(f"Successfully deleted {deleted_count} duplicates. Kept account ID {keeper.id}.")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean_duplicates()
