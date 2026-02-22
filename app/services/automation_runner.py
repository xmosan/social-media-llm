import logging
from datetime import datetime, timezone as dt_timezone, timedelta
from sqlalchemy.orm import Session
from app.models import TopicAutomation, Post, IGAccount, ContentUsage
from app.services.llm import generate_topic_caption, generate_caption_from_content_item, generate_ai_image
from app.services.publisher import publish_to_instagram
from app.services.content_library import pick_content_item
from app.services.image_card import create_quote_card
from app.config import settings
import pytz
import os
import requests

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
        scheduled_next = scheduled_today + timedelta(days=1)
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
    
    content_item = None
    try:
        # 1. Content Selection
        topic = automation.topic_prompt
        if automation.use_content_library:
            content_item = pick_content_item(
                db=db,
                org_id=automation.org_id,
                topic=topic,
                content_type=automation.content_type,
                avoid_repeat_days=automation.avoid_repeat_days,
                automation_id=automation.id,
                ig_account_id=automation.ig_account_id
            )
            
            if not content_item:
                print(f"[AUTO] FAILURE: No content found in library for topic '{topic}'")
                # Create a failed post so user can see what happened
                new_post = Post(
                    org_id=automation.org_id,
                    ig_account_id=automation.ig_account_id,
                    is_auto_generated=True,
                    automation_id=automation.id,
                    status="failed",
                    source_type="automation",
                    source_text=f"AUTO: {automation.name} | topic={topic}",
                    flags={"automation_error": "No content found in library for topic", "topic": topic}
                )
                db.add(new_post)
                automation.last_error = f"No content found for topic: {topic}"
                automation.last_run_at = datetime.now(dt_timezone.utc)
                db.commit()
                return new_post

        # 2. Generate Content
        print(f"[AUTO] Generating for automation_id={automation.id} topic='{topic}'")
        
        if content_item:
            result = generate_caption_from_content_item(
                content_item=content_item,
                style=automation.style_preset,
                tone=automation.tone or "medium",
                language=automation.language or "english",
                banned_phrases=automation.banned_phrases if isinstance(automation.banned_phrases, list) else None,
                include_arabic=automation.include_arabic,
                extra_hashtag_set=automation.hashtag_set
            )
        else:
            # Fallback for old mode if use_content_library is False
            result = generate_topic_caption(
                topic=topic,
                style=automation.style_preset,
                tone=automation.tone or "medium",
                language=automation.language or "english",
                banned_phrases=automation.banned_phrases if isinstance(automation.banned_phrases, list) else None
            )
        
        caption = result.get("caption", "").strip()
        hashtags = result.get("hashtags", [])
        if automation.hashtag_set:
            hashtags = automation.hashtag_set
            
        alt_text = result.get("alt_text", "")
        
        # 3. Media Selection / Generation
        media_url = pick_media_url(db, automation.org_id, automation.ig_account_id, automation.image_mode)
        
        if automation.image_mode == "ai_generated":
            prompt_for_image = topic
            if content_item and content_item.topics:
                prompt_for_image += f" (Concept: {content_item.topics[0]})"
            
            generated_url = generate_ai_image(prompt_for_image)
            if generated_url:
                filename = f"ai_{automation.id}_{int(datetime.now().timestamp())}.jpg"
                file_path = os.path.join(settings.uploads_dir, filename)
                try:
                    res = requests.get(generated_url, timeout=30)
                    if res.status_code == 200:
                        with open(file_path, "wb") as f:
                            f.write(res.content)
                        media_url = f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
                        print(f"[AUTO] AI Image generated and saved: {media_url}")
                    else:
                        print(f"[AUTO] FAILED downloading DALL-E image, HTTP {res.status_code}")
                except Exception as down_e:
                    print(f"[AUTO] ERROR downloading DALL-E image: {down_e}")

        elif automation.image_mode == "quote_card" or (media_url is None and automation.image_mode != "none_placeholder"):
            if content_item:
                # Generate a quote card
                filename = f"quote_{automation.id}_{int(datetime.now().timestamp())}.jpg"
                file_path = os.path.join(settings.uploads_dir, filename)
                
                attribution = content_item.source_name or ""
                if content_item.reference:
                    attribution += f" ({content_item.reference})"
                
                create_quote_card(content_item.text_en, attribution, file_path)
                media_url = f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
                print(f"[AUTO] Quote card generated: {media_url}")

        # 4. Create Post
        status = "scheduled"
        if automation.approval_mode == "needs_manual_approve":
            status = "drafted"
            
        source_text = f"AUTO: {automation.name} | topic={topic}"
        if content_item:
            source_text += f" | content_id={content_item.id}"

        new_post = Post(
            org_id=automation.org_id,
            ig_account_id=automation.ig_account_id,
            is_auto_generated=True,
            automation_id=automation.id,
            content_item_id=content_item.id if content_item else None,
            status=status,
            source_type="automation",
            source_text=source_text,
            media_url=media_url,
            caption=caption,
            hashtags=hashtags,
            alt_text=alt_text,
            scheduled_time=compute_next_run_time(db.get(IGAccount, automation.ig_account_id), automation) if status == "scheduled" else None
        )
        
        # 5. Guardrail (simpler for library content)
        if not caption:
            print(f"[AUTO] FAILED GUARDRAIL: caption is empty.")
            new_post.status = "failed"
            new_post.flags = {"automation_error": "LLM returned empty caption"}
            automation.last_error = "LLM returned empty caption"
            db.add(new_post)
            db.commit()
            return new_post

        db.add(new_post)
        db.flush() # Get new_post.id
        
        # 6. Track Usage
        if content_item:
            usage = ContentUsage(
                org_id=automation.org_id,
                ig_account_id=automation.ig_account_id,
                automation_id=automation.id,
                post_id=new_post.id,
                content_item_id=content_item.id,
                status="selected"
            )
            db.add(usage)

        # 7. Immediate Publishing if configured
        if automation.posting_mode == "publish_now" and automation.approval_mode == "auto_approve":
            acc = db.get(IGAccount, automation.ig_account_id)
            pub_res = publish_to_instagram(
                caption=f"{new_post.caption}\n\n" + " ".join(new_post.hashtags or []),
                media_url=new_post.media_url,
                ig_user_id=acc.ig_user_id,
                access_token=acc.access_token
            )
            if pub_res.get("ok"):
                new_post.status = "published"
                new_post.published_time = datetime.now(dt_timezone.utc)
                if content_item:
                    # Update usage status to published if we can find it (it's in current session)
                    pass # We'll just set it correctly initially or update if needed
            else:
                new_post.status = "failed"
                new_post.flags = {**new_post.flags, "publish_error": pub_res.get("error")}
                if content_item:
                    # If we really want to be precise, track usage as failed
                    pass

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
