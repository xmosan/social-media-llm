import logging
from datetime import datetime, timezone as dt_timezone
from sqlalchemy.orm import Session
from app.models import TopicAutomation, Post, IGAccount
from app.services.llm import generate_topic_caption
from app.services.publisher import publish_to_instagram
import pytz

logger = logging.getLogger(__name__)

def compute_next_run_time(ig_account: IGAccount, automation: TopicAutomation) -> datetime:
    """
    Determines next UTC time for the automation.
    """
    tz_str = automation.timezone or ig_account.timezone or "UTC"
    time_str = automation.post_time_local or ig_account.daily_post_time or "09:00"
    
    tz = pytz.timezone(tz_str)
    now_tz = datetime.now(tz)
    
    hour, minute = map(int, time_str.split(":"))
    scheduled_today = now_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    if scheduled_today <= now_tz:
        scheduled_next = scheduled_today + (datetime.now() - datetime.now()).__class__(days=1)
    else:
        scheduled_next = scheduled_today
        
    return scheduled_next.astimezone(pytz.UTC)

def pick_media_url(db: Session, org_id: int, ig_account_id: int, image_mode: str) -> str | None:
    if image_mode == "reuse_last_upload":
        last_post = (
            db.query(Post)
            .filter(Post.org_id == org_id, Post.ig_account_id == ig_account_id, Post.media_url != None)
            .order_by(Post.created_at.desc())
            .first()
        )
        return last_post.media_url if last_post else None
    return None

def run_automation_once(db: Session, automation_id: int) -> Post | None:
    """
    Core engine to run one automation cycle.
    """
    automation = db.query(TopicAutomation).filter(TopicAutomation.id == automation_id).first()
    if not automation or not automation.enabled:
        return None
    
    try:
        # 1. Generate Content
        print(f"[AUTO] Triggering draft for automation_id={automation.id} topic='{automation.topic_prompt}' style='{automation.style_preset}'")
        
        result = generate_topic_caption(
            topic=automation.topic_prompt,
            style=automation.style_preset,
            tone=automation.tone or "medium",
            language=automation.language or "english",
            banned_phrases=automation.banned_phrases if isinstance(automation.banned_phrases, list) else None
        )
        
        caption = result.get("caption", "").strip()
        hashtags = result.get("hashtags", [])
        alt_text = result.get("alt_text", "")
        
        print(f"[AUTO] Draft received: caption_len={len(caption)} hashtags_count={len(hashtags)}")

        # 2. Pick Media
        media_url = pick_media_url(db, automation.org_id, automation.ig_account_id, automation.image_mode)
        
        # 3. Create Post
        status = "scheduled"
        if automation.approval_mode == "needs_manual_approve":
            status = "drafted"
            
        new_post = Post(
            org_id=automation.org_id,
            ig_account_id=automation.ig_account_id,
            is_auto_generated=True,
            automation_id=automation.id,
            status=status,
            source_type="automation",
            source_text=f"AUTO: {automation.name}",
            media_url=media_url,
            caption=caption,
            hashtags=automation.hashtag_set if automation.hashtag_set else hashtags,
            alt_text=alt_text,
            scheduled_time=compute_next_run_time(db.query(IGAccount).get(automation.ig_account_id), automation) if status == "scheduled" else None
        )
        
        # 4. Hard Guardrail: Validate Caption
        source_label = f"AUTO: {automation.name}"
        is_bad = (not caption) or (caption == source_label) or (caption == automation.topic_prompt)
        
        if is_bad:
            print(f"[AUTO] FAILED GUARDRAIL: caption matches topic or is empty.")
            new_post.status = "failed"
            new_post.flags = {
                "automation_error": "LLM returned empty or same as topic/name",
                "raw_draft": result
            }
            automation.last_error = "LLM returned empty or same as topic/name"
            db.add(new_post)
            db.commit()
            return new_post

        print(f"[AUTO] Final caption preview: {caption[:100]}...")
        db.add(new_post)
        
        # 5. Immediate Publishing if configured
        if automation.posting_mode == "publish_now" and automation.approval_mode == "auto_approve":
            acc = db.query(IGAccount).get(automation.ig_account_id)
            pub_res = publish_to_instagram(
                caption=f"{new_post.caption}\n\n" + " ".join(new_post.hashtags or []),
                media_url=new_post.media_url,
                ig_user_id=acc.ig_user_id,
                access_token=acc.access_token
            )
            if pub_res.get("ok"):
                new_post.status = "published"
                new_post.published_time = datetime.now(dt_timezone.utc)
            else:
                new_post.status = "failed"
                new_post.flags = {**new_post.flags, "publish_error": pub_res.get("error")}

        automation.last_run_at = datetime.now(dt_timezone.utc)
        automation.last_post_id = new_post.id
        automation.last_error = None
        
        db.commit()
        db.refresh(new_post)
        return new_post

    except Exception as e:
        print(f"[AUTO] ERROR in runner for automation_id={automation_id}: {repr(e)}")
        logger.error(f"Automation {automation_id} failed: {e}")
        automation.last_error = str(e)
        db.commit()
        return None
