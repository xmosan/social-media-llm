import os
import sys
from sqlalchemy import create_engine, text
from app.config import settings

def upgrade_db():
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        print("Checking posts table...")
        
        # Check topic
        try:
            conn.execute(text("ALTER TABLE posts ADD COLUMN topic VARCHAR"))
            print("Added topic to posts")
        except Exception as e:
            print("topic likely exists or error:", e)
            
        # Check post_type
        try:
            conn.execute(text("ALTER TABLE posts ADD COLUMN post_type VARCHAR"))
            print("Added post_type to posts")
        except Exception as e:
            print("post_type likely exists or error:", e)
            
        # Check source_reference
        try:
            conn.execute(text("ALTER TABLE posts ADD COLUMN source_reference VARCHAR"))
            print("Added source_reference to posts")
        except Exception as e:
            print("source_reference likely exists or error:", e)
            
        conn.commit()

if __name__ == "__main__":
    upgrade_db()
