# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from datetime import datetime, timezone, timedelta
from typing import Callable
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Post, IGAccount, TopicAutomation
from app.services.post_service import publish_post
from app.services.automation_runner import run_automation_once
from app.services.automation_schedule import automation_triggers
from app.services.backups import backup_postgres_database
from app.security.ownership import require_account
from fastapi import HTTPException

def run_automation_job(db_factory: Callable[[], Session], automation_id: int, trigger=None):
    """Execution wrapper for background automation jobs."""
    db = db_factory()
    try:
        occurrence = None
        if trigger is not None:
            now = datetime.now(timezone.utc)
            occurrence = trigger.get_next_fire_time(None, now - timedelta(seconds=300))
            if occurrence is None or occurrence > now:
                return
        run_automation_once(db, automation_id, scheduled_for=occurrence)
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
            try:
                acc = require_account(db, auto.org_id, auto.ig_account_id, active=True)
            except HTTPException:
                continue
            
            try:
                for i, trigger in enumerate(automation_triggers(acc, auto)):
                    sched.add_job(
                        run_automation_job,
                        trigger=trigger,
                        args=[db_factory, auto.id, trigger],
                        id=f"auto_{auto.id}_{i}",
                        replace_existing=True,
                        max_instances=1,
                        coalesce=True,
                        misfire_grace_time=300,
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
            try:
                result = publish_post(db, post.id, post.org_id)
                if result.ok:
                    published += 1
                elif result.status_code in {403, 422}:
                    # A validation failure needs user action; do not retry it every minute.
                    post.status = "failed"
                    post.flags = {**(post.flags or {}), "publish_error": result.error}
                    db.commit()
            except Exception:
                db.rollback()  # The committed publish claim remains for reconciliation.


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

    # 3. Daily Database Backups
    sched.add_job(
        backup_postgres_database,
        trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="daily_database_backup",
        replace_existing=True,
        max_instances=1
    )

    sched.start()
    _global_scheduler = sched
    return sched

def reload_automation_jobs(db_factory: Callable[[], Session]):
    """Helper to refresh automation jobs when settings change in UI."""
    if _global_scheduler:
        sync_automation_jobs(_global_scheduler, db_factory)
