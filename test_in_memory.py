from sqlalchemy import create_engine, Column, Integer, JSON, String, cast
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class ContentItem(Base):
    __tablename__ = "content_items"
    id = Column(Integer, primary_key=True)
    topics_slugs = Column(JSON, default=list)

engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

# Add some data
db.add(ContentItem(topics_slugs=["worship", "ramadan"]))
db.add(ContentItem(topics_slugs=["fasting", "deeds"]))
db.commit()

# Test .contains([topic])
print("Testing .contains()...")
try:
    topic = "worship"
    results = db.query(ContentItem).filter(ContentItem.topics_slugs.contains([topic])).all()
    print(f"Found {len(results)} items via contains()")
except Exception as e:
    print(f"Exception for contains: {e}")

# Test cast to String and ilike
print("Testing cast and ilike...")
try:
    topic = "worship"
    results = db.query(ContentItem).filter(cast(ContentItem.topics_slugs, String).ilike(f'%"{topic}"%')).all()
    print(f"Found {len(results)} items via ilike")
except Exception as e:
    print(f"Exception for ilike: {e}")

