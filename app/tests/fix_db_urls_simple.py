import sys
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    media_url = Column(Text)

def fix_urls(new_base_url):
    # Use the default sqlite path
    engine = create_engine("sqlite:///./app.db")
    Session = sessionmaker(bind=engine)
    db = Session()
    
    print(f"Target BASE_URL: {new_base_url}")
    
    posts = db.query(Post).all()
    updated_count = 0
    for post in posts:
        if post.media_url and ("localhost" in post.media_url or "127.0.0.1" in post.media_url):
            filename = post.media_url.split("/")[-1]
            new_url = f"{new_base_url}/uploads/{filename}"
            print(f"Updating Post #{post.id}: {post.media_url} -> {new_url}")
            post.media_url = new_url
            updated_count += 1
    
    if updated_count > 0:
        db.commit()
        print(f"✅ Successfully updated {updated_count} posts.")
    else:
        print("No posts with 'localhost' URLs found.")
    db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fix_db_urls_simple.py <new_base_url>")
    else:
        fix_urls(sys.argv[1])
