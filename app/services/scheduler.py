from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Post
from app.services.publisher import publish_to_instagram

def start_scheduler(db: Session):
    """Publishes scheduled posts whose scheduled_time <= now (UTC). Returns count."""
    now = datetime.now(timezone.utc)

    stmt = (
        select(Post)
        .where(Post.status == "scheduled")
        .where(Post.scheduled_time != None)  # noqa: E711
        .where(Post.scheduled_time <= now)
        .order_by(Post.scheduled_time.asc())
    )

    posts = db.execute(stmt).scalars().all()
    if not posts:
        return 0

    if not settings.ig_access_token or not settings.ig_user_id:
        # fail loudly so you notice misconfig
        raise RuntimeError("Missing IG_ACCESS_TOKEN or IG_USER_ID")

    published = 0
    for post in posts:
        if not post.caption or not post.media_url:
            post.status = "failed"
            db.commit()
            continue

        caption_full = post.caption
        if post.hashtags:
            caption_full += "\n\n" + " ".join(post.hashtags)

        try:
            publish_to_instagram(
                ig_user_id=settings.ig_user_id,
                access_token=settings.ig_access_token,
                image_url=post.media_url,
                caption=caption_full,
            )
            post.status = "published"
            post.published_time = now
            db.commit()
            published += 1
        except Exception:
            post.status = "failed"
            db.commit()

    return published
