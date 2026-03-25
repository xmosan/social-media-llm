from sqlalchemy import create_engine, or_, func
from sqlalchemy.orm import sessionmaker
from app.models import ContentItem, Base

engine = create_engine('sqlite:///saas.db')
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("Testing query...")
try:
    topic = "worship"
    q = db.query(ContentItem).filter(ContentItem.topics_slugs.contains([topic]))
    results = q.all()
    print(f"Success! Found {len(results)} items.")
except Exception as e:
    print(f"Error: {e}")
