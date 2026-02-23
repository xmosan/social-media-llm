import logging
from typing import Any
from datetime import datetime, timezone as dt_timezone, timedelta
from sqlalchemy.orm import Session
from app.models import TopicAutomation, Post, IGAccount, ContentUsage, MediaAsset, ContentItem
from app.services.llm import generate_topic_caption, generate_caption_from_content_item, generate_ai_image
from app.services.publisher import publish_to_instagram
from app.services.content_library import pick_content_item
from app.services.image_card import create_quote_card
from app.services.sources.sunnah import pick_hadith_for_topic
from app.config import settings
import pytz
import os
import requests
from app.logging_setup import log_event

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

def pick_media_url(db: Session, org_id: int, ig_account_id: int, automation: Any) -> str | None:
    """
    Deprecated: Use resolve_media_url instead. 
    Kept for backward compatibility but made robust to strings.
    """
    mode = automation if isinstance(automation, str) else automation.image_mode
    # For backward compat, we just handle library and reuse
    if mode == "reuse_last_upload":
        last_post = (
            db.query(Post)
            .filter(Post.org_id == org_id, Post.ig_account_id == ig_account_id, Post.media_url != None)
            .order_by(Post.created_at.desc())
            .first()
        )
        return last_post.media_url if last_post else None
        
    if mode in ["use_library_image", "library_fixed", "library_tag"]:
        # If it's a string, we can't do library lookups without more info.
        # But this function is being replaced by the better one below.
        if isinstance(automation, str): return None
        
        if automation.media_asset_id:
            asset = db.get(MediaAsset, automation.media_asset_id)
            if asset: return asset.url
            
        if automation.media_tag_query:
            query = db.query(MediaAsset).filter(MediaAsset.org_id == org_id)
            assets = query.all()
            requested_tags = [t.lower() for t in (automation.media_tag_query or [])]
            matching = []
            for a in assets:
                asset_tags = [at.lower() for at in (a.tags or [])]
                if any(rt in asset_tags for rt in requested_tags):
                    matching.append(a)
            if matching:
                import random
                asset = random.choice(matching)
                return asset.url
    return None

def resolve_media_url(
    db: Session, 
    org_id: int, 
    ig_account_id: int, 
    image_mode: str, 
    topic: str = "general",
    automation_id: int | None = None,
    media_asset_id: int | None = None,
    media_tag_query: list[str] | None = None,
    content_concept: str | None = None
) -> str | None:
    """
    One-stop shop for finding or generating a media URL.
    Handles library, reuse, and AI generation.
    """
    # 1. Reuse logic
    if image_mode == "reuse_last_upload":
        last_post = (
            db.query(Post)
            .filter(Post.org_id == org_id, Post.ig_account_id == ig_account_id, Post.media_url != None)
            .order_by(Post.created_at.desc())
            .first()
        )
        return last_post.media_url if last_post else None

    # 2. Library logic
    if image_mode in ["use_library_image", "library_fixed", "library_tag"]:
        if media_asset_id:
            asset = db.get(MediaAsset, media_asset_id)
            if asset: return asset.url
            
        if media_tag_query:
            query = db.query(MediaAsset).filter(MediaAsset.org_id == org_id)
            assets = query.all()
            requested_tags = [t.lower() for t in (media_tag_query or [])]
            matching = []
            for a in assets:
                asset_tags = [at.lower() for at in (a.tags or [])]
                if any(rt in asset_tags for rt in requested_tags):
                    matching.append(a)
            if matching:
                import random
                asset = random.choice(matching)
                return asset.url
        return None

    # 3. AI Generation logic
    ai_modes = [
        "ai_generated", "ai_nature_photo", "ai_islamic_pattern", 
        "ai_calligraphy_no_text", "ai_minimal_gradient"
    ]
    if image_mode in ai_modes:
        mode_prompts = {
            "ai_nature_photo": "Realistic high-quality nature photography of ",
            "ai_islamic_pattern": "Elegant seamless Islamic geometric pattern with colors of ",
            "ai_calligraphy_no_text": "Artistic Islamic abstract calligraphy art without readable text, theme of ",
            "ai_minimal_gradient": "Modern minimal soft gradient background with colors of ",
            "ai_generated": ""
        }
        
        base_prompt = mode_prompts.get(image_mode, "")
        prompt_for_image = base_prompt + topic
        if content_concept:
            prompt_for_image += f" (Concept: {content_concept})"
        
        generated_url = generate_ai_image(prompt_for_image)
        if generated_url:
            # Save it locally and to library
            filename = f"ai_{automation_id or 'manual'}_{int(datetime.now().timestamp())}.jpg"
            file_path = os.path.join(settings.uploads_dir, filename)
            try:
                res = requests.get(generated_url, timeout=30)
                if res.status_code == 200:
                    with open(file_path, "wb") as f:
                        f.write(res.content)
                    final_url = f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
                    
                    # Also register it in Media Library for future reuse/filter
                    new_asset = MediaAsset(
                        org_id=org_id,
                        ig_account_id=ig_account_id,
                        url=final_url,
                        storage_path=file_path,
                        tags=["ai_generated", image_mode, topic[:30]]
                    )
                    db.add(new_asset)
                    db.commit()
                    return final_url
            except Exception as e:
                print(f"[MEDIA] Error downloading AI image: {e}")
                
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
        topic = automation.topic_prompt
        log_event("automation_run_start", automation_id=automation.id, topic=topic, style=automation.style_preset)
        
        # 1. Content Selection
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
        log_event("automation_caption_generated", automation_id=automation.id, caption_len=len(caption), hashtags_count=len(hashtags))
        
        # 2.5 Optional Enrichment: Hadith
        if automation.enrich_with_hadith:
            try:
                hadith_topic = automation.hadith_topic or automation.topic_prompt
                print(f"[AUTO] Enrichment enabled. Topic: {hadith_topic}")
                
                hadith = pick_hadith_for_topic(db, hadith_topic)
                if hadith:
                    # Truncate if needed
                    text = hadith.content_text
                    max_len = automation.hadith_max_len or 450
                    if len(text) > max_len:
                        text = text[:max_len-3] + "..."
                    
                    enrichment_text = f"\n\n📜 Hadith:\n{text}\n"
                    if hadith.reference:
                        enrichment_text += f"Source: {hadith.reference}"
                    if hadith.url:
                        enrichment_text += f" ({hadith.url})"
                        
                    caption += enrichment_text
                    print(f"[AUTO] Appended hadith from {hadith.reference}")
                else:
                    print(f"[AUTO] No hadith found for topic '{hadith_topic}'")
            except Exception as enrich_e:
                print(f"[AUTO] Enrichment ERROR (skipping): {enrich_e}")
                logger.error(f"Enrichment failed for automation {automation.id}: {enrich_e}")
        
        # 3. Media Selection / Generation
        concepts = content_item.topics[0] if content_item and content_item.topics else None
        media_url = resolve_media_url(
            db=db,
            org_id=automation.org_id,
            ig_account_id=automation.ig_account_id,
            image_mode=automation.image_mode,
            topic=topic,
            automation_id=automation.id,
            media_asset_id=automation.media_asset_id,
            media_tag_query=automation.media_tag_query,
            content_concept=concepts
        )
        
        # 4. Final Post Creation
        if automation.image_mode == "quote_card" or (media_url is None and automation.image_mode != "none_placeholder"):
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
            log_event("automation_guardrail_failed", automation_id=automation.id, reason="empty_caption")
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
            log_event("automation_publish_attempt", automation_id=automation.id, post_id=new_post.id)
            acc = db.get(IGAccount, automation.ig_account_id)
            pub_res = publish_to_instagram(
                caption=f"{new_post.caption}\n\n" + " ".join(new_post.hashtags or []),
                media_url=new_post.media_url,
                ig_user_id=acc.ig_user_id,
                access_token=acc.access_token
            )
            if pub_res.get("ok"):
                log_event("automation_publish_success", automation_id=automation.id, post_id=new_post.id)
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
        import traceback
        log_event("automation_run_exception", automation_id=automation_id, error=str(e), traceback=traceback.format_exc(limit=3))
        print(f"[AUTO] ERROR in runner for automation_id={automation_id}: {repr(e)}")
        logger.error(f"Automation {automation_id} failed: {e}")
        automation.last_error = str(e)
        db.commit()
        return None
