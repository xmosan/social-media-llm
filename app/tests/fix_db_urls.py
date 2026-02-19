from app.db import SessionLocal
from app.models import Post
from app.config import settings
import os

def fix_urls():
    db = SessionLocal()
    print(f"Current BASE_URL in .env: {settings.public_base_url}")
    
    posts = db.query(Post).all()
    updated_count = 0
    for post in posts:
        if post.media_url and "localhost" in post.media_url or "127.0.0.1" in post.media_url:
            filename = post.media_url.split("/")[-1]
            new_url = f"{settings.public_base_url}/uploads/{filename}"
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
    fix_urls()
