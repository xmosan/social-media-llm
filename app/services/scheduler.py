from datetime import datetime, timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Post
from app.services.publisher import publish_to_instagram


def publish_daily(db_factory: Callable[[], Session], max_posts: int = 1) -> int:
    """
    Publish up to `max_posts` scheduled posts.
    Runs once per day.
    """
    db = db_factory()
    try:
        stmt = (
            select(Post)
            .where(Post.status == "scheduled")
            .order_by(Post.created_at.asc())
            .limit(max_posts)
        )
        posts = db.execute(stmt).scalars().all()
        if not posts:
            return 0

        if not settings.ig_access_token or not settings.ig_user_id:
            raise RuntimeError("Missing IG_ACCESS_TOKEN or IG_USER_ID")

        published = 0
        now = datetime.now(timezone.utc)

        for post in posts:
            if not post.caption or not post.media_url:
                post.status = "failed"
                db.commit()
                continue

            caption_full = post.caption
            if post.hashtags:
                caption_full += "\n\n" + " ".join(post.hashtags)

            result = publish_to_instagram(caption=caption_full, media_url=post.media_url)

            if not isinstance(result, dict) or not result.get("ok"):
                post.status = "failed"
                db.commit()
                continue

            post.status = "published"
            post.published_time = now
            db.commit()
            published += 1

        return published
    finally:
        db.close()


def start_scheduler(db_factory: Callable[[], Session]):
    # run once daily at 9:00 AM Detroit time
    sched = BackgroundScheduler(timezone="America/Detroit")

    sched.add_job(
        publish_daily,
        trigger=CronTrigger(hour=9, minute=0),
        args=[db_factory],
        kwargs={"max_posts": 1},
        id="daily_publish",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,  # 1 hour grace
    )

    sched.start()
    return sched