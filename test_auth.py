import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models import User
from app.security.auth import verify_password

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db = SessionLocal()
users = db.query(User).all()

print(f"Total users in DB: {len(users)}")
for u in users:
    print(f"User: {u.email}, is_superadmin: {u.is_superadmin}, has_password: {bool(u.password_hash)}")

auth_email = os.getenv("SUPERADMIN_EMAIL", settings.superadmin_email)
auth_pass = os.getenv("SUPERADMIN_PASSWORD", settings.superadmin_password)

print(f"Configured Email: {auth_email}")
print(f"Configured Pass Length: {len(auth_pass) if auth_pass else 0}")
if auth_email and auth_pass:
    u = db.query(User).filter(User.email == auth_email).first()
    if u:
        print(f"Password verification: {verify_password(auth_pass, u.password_hash)}")
    else:
        print("User not found in DB")
db.close()
