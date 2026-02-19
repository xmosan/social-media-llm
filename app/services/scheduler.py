from datetime import datetime, timezone
from typing import Callable
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Post, IGAccount, TopicAutomation
from app.services.publisher import publish_to_instagram
from app.services.automation_runner import run_automation_once

def run_automation_job(db_factory: Callable[[], Session], automation_id: int):
    """Execution wrapper for background automation jobs."""
    db = db_factory()
    try:
        run_automation_once(db, automation_id)
    finally:
        db.close()

def sync_automation_jobs(sched: BackgroundScheduler, db_factory: Callable[[], Session]):
    """
    Syncs the scheduler with all enabled TopicAutomations in the database.
    Removes existing auto jobs and re-adds them.
    """
    import time
    t0 = time.time()
    
    # 1. Clean up old jobs
    for job in list(sched.get_jobs()):
        if job.id.startswith("auto_"):
            sched.remove_job(job.id)

    # 2. Add enabled jobs
    db = db_factory()
    try:
        enabled_autos = db.query(TopicAutomation).filter(TopicAutomation.enabled == True).all()
        for auto in enabled_autos:
            acc = db.query(IGAccount).get(auto.ig_account_id)
            if not acc: continue
            
            time_str = auto.post_time_local or acc.daily_post_time or "09:00"
            tz_str = auto.timezone or acc.timezone or "UTC"
            try:
                hour, minute = map(int, time_str.split(":"))
                sched.add_job(
                    run_automation_job,
                    trigger=CronTrigger(hour=hour, minute=minute, timezone=tz_str),
                    args=[db_factory, auto.id],
                    id=f"auto_{auto.id}",
                    replace_existing=True,
                    max_instances=1
                )
            except Exception as e:
                print(f"FAILED TO SCHEDULE AUTO {auto.id}: {e}")
    finally:
        db.close()
        print(f"DIAGNOSTIC: sync_automation_jobs took {time.time()-t0:.4f}s")

def publish_due_posts(db_factory: Callable[[], Session]) -> int:
    """
    Check for any scheduled posts that are due (scheduled_time <= now).
    This runs every minute to handle all accounts/orgs.
    """
    db = db_factory()
    try:
        now = datetime.now(timezone.utc)
        stmt = (
            select(Post)
            .where(Post.status == "scheduled")
            .where(Post.scheduled_time <= now)
            .order_by(Post.scheduled_time.asc())
        )
        posts = db.execute(stmt).scalars().all()
        
        if not posts:
            return 0

        published = 0
        for post in posts:
            acc = db.get(IGAccount, post.ig_account_id)
            if not acc or not acc.active:
                continue

            caption_full = post.caption or ""
            if post.hashtags:
                caption_full += "\n\n" + " ".join(post.hashtags)

            result = publish_to_instagram(
                caption=caption_full, 
                media_url=post.media_url,
                ig_user_id=acc.ig_user_id,
                access_token=acc.access_token
            )

            if isinstance(result, dict) and result.get("ok"):
                post.status = "published"
                post.published_time = datetime.now(timezone.utc)
                db.commit()
                published += 1
            else:
                post.status = "failed"
                error_info = result.get("error") if isinstance(result, dict) else str(result)
                post.flags = {**(post.flags or {}), "publish_error": error_info}
                db.commit()

        return published
    finally:
        db.close()

# Global reference to scheduler for reloading
_global_scheduler = None

def start_scheduler(db_factory: Callable[[], Session]):
    """
    Start a BackgroundScheduler that checks for due posts every minute 
    and handles topic automations.
    """
    global _global_scheduler
    sched = BackgroundScheduler()
    
    # 1. Standard per-minute publishing check
    sched.add_job(
        publish_due_posts,
        trigger="interval",
        minutes=1,
        args=[db_factory],
        id="check_due_posts",
        replace_existing=True,
        max_instances=1
    )

    # 2. Daily Automation Jobs
    sync_automation_jobs(sched, db_factory)

    sched.start()
    _global_scheduler = sched
    return sched

def reload_automation_jobs(db_factory: Callable[[], Session]):
    """Helper to refresh automation jobs when settings change in UI."""
    if _global_scheduler:
        sync_automation_jobs(_global_scheduler, db_factory)