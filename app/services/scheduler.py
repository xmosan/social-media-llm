from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Post
from app.services.publisher import publish_to_instagram


def run_due_posts(db: Session) -> int:
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
            result = publish_to_instagram(caption=caption_full, media_url=post.media_url)

            if isinstance(result, dict) and result.get("ok"):
                post.status = "published"
                post.published_time = now
                db.commit()
                published += 1
            else:
                post.status = "failed"
                post.flags = {**(post.flags or {}), "publish_error": result}
                db.commit()

        except Exception as e:
            post.status = "failed"
            post.flags = {**(post.flags or {}), "publish_exception": str(e)}
            db.commit()

    return published


def start_scheduler(db_factory: Callable[[], Session]):
    """
    MVP scheduler: runs once at startup.
    Later we can replace this with APScheduler/Cron worker.
    """
    db = db_factory()
    try:
        return run_due_posts(db)
    finally:
        db.close()
