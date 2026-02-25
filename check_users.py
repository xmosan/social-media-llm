from sqlalchemy import create_url
from app.db import SessionLocal
from app.models import User
import json

def check_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        result = []
        for u in users:
            result.append({
                "id": u.id,
                "email": u.email,
                "is_superadmin": u.is_superadmin,
                "is_active": u.is_active,
                "google_id": u.google_id
            })
        print(json.dumps(result, indent=2))
    finally:
        db.close()

if __name__ == "__main__":
    check_users()
