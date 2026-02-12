from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone

from ..models import Post
from .publisher import publish_to_instagram

def _utcnow():
    return datetime.now(timezone.utc)

def run_due_posts(db_factory):
    db: Session = db_factory()
    try:
        now = _utcnow()
        stmt = select(Post).where(
            Post.status == "scheduled",
            Post.scheduled_time.is_not(None),
            Post.scheduled_time <= now
        )
        due = db.execute(stmt).scalars().all()

        for post in due:
            try:
                if not post.media_url:
                    raise ValueError("No media_url set (must be public https URL)")
                result = publish_to_instagram(caption=post.caption or "", media_url=post.media_url)
                if result.get("ok"):
                    post.status = "published"
                    post.published_time = now
                else:
                    post.status = "failed"
                    post.flags = {**(post.flags or {}), "publish_error": result}
            except Exception as e:
                post.status = "failed"
                post.flags = {**(post.flags or {}), "publish_error": str(e)}

        db.commit()
    finally:
        db.close()

def start_scheduler(db_factory):
    sched = BackgroundScheduler()
    sched.add_job(
        func=run_due_posts,
        trigger=IntervalTrigger(seconds=60),
        args=[db_factory],
        id="publish_due_posts",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    return sched