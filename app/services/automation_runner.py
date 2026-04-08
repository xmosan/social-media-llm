# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import logging
from typing import Any
from datetime import datetime, timezone as dt_timezone, timedelta
from sqlalchemy.orm import Session
from app.models import TopicAutomation, Post, IGAccount, ContentUsage, MediaAsset, ContentItem
from app.services.llm import generate_topic_caption, generate_caption_from_content_item, generate_ai_image, generate_topic_variations
from app.services.publisher import publish_to_instagram
from app.services.content_library import pick_content_item
from app.services.image_card import create_quote_card
from app.services.library_retrieval import retrieve_relevant_chunks
from app.services.prebuilt_loader import load_prebuilt_packs
from app.services.image_card import create_quote_card
from app.services.image_renderer import render_quote_card
from app.config import settings
import pytz
import os
import requests
from app.services.content_sources import select_items_for_automation, mark_items_used
from app.logging_setup import log_event

logger = logging.getLogger(__name__)

def compute_next_run_time(ig_account: IGAccount, automation: TopicAutomation) -> datetime:
    """
    Determines next UTC time for the automation.
    """
    tz_str = automation.timezone or ig_account.timezone or "UTC"
    time_str = automation.post_time_local or ig_account.daily_post_time or "09:00"
    frequency = getattr(automation, "frequency", "daily")
    custom_days = getattr(automation, "custom_days", []) or []
    
    tz = pytz.timezone(tz_str)
    now_tz = datetime.now(tz)
    
    hour, minute = map(int, time_str.split(":"))
    scheduled_today = now_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # 3x Weekly: Mon, Wed, Fri
    # Weekly: Fri
    # Custom: Use list
    target_days = []
    if frequency == "daily":
        target_days = [0,1,2,3,4,5,6]
    elif frequency == "3x_weekly":
        target_days = [0,2,4] # Mon, Wed, Fri
    elif frequency == "weekly":
        target_days = [4] # Fri
    elif frequency == "custom":
        day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        target_days = [day_map[d] for d in custom_days if d in day_map]
    
    if not target_days: target_days = [0,1,2,3,4,5,6] # Fallback to daily

    # Find next available day
    found_next = False
    for i in range(8):
        check_day = scheduled_today + timedelta(days=i)
        if check_day.weekday() in target_days:
            if check_day > now_tz:
                scheduled_next = check_day
                found_next = True
                break
    
    if not found_next:
        scheduled_next = scheduled_today + timedelta(days=1)
        
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
        "ai_minimal_gradient"
    ]
    if image_mode in ai_modes:
        mode_prompts = {
            "ai_nature_photo": "Realistic high-quality nature photography of ",
            "ai_islamic_pattern": "Elegant seamless Islamic geometric pattern with colors of ",
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
                    
                    # Also register it in Media for future reuse/filter
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
    Core engine to run one automation cycle using the decoupled Content Provider architecture.
    """
    automation = db.query(TopicAutomation).filter(TopicAutomation.id == automation_id).first()
    if not automation or not automation.enabled:
        return None
    
    try:
        # Pillar Rotation Logic
        pillars = automation.pillars or []
        topic_base = automation.topic_prompt
        
        if pillars:
            # Count previous SUCCESSFUL posts to determine rotation index
            post_count = db.query(Post).filter(Post.automation_id == automation.id, Post.status == "published").count()
            selected_pillar = pillars[post_count % len(pillars)]
            # If topic_prompt exists, use it as grounding context, otherwise use pillar as main topic
            topic_base = f"{selected_pillar}: {topic_base}" if topic_base else selected_pillar
            log_event("automation_pillar_selected", automation_id=automation.id, pillar=selected_pillar, index=post_count % len(pillars))

        log_event("automation_run_start", automation_id=automation.id, topic=topic_base, style=automation.style_preset)
        
        # 1. Topic Variations
        try:
            variations = generate_topic_variations(topic_base, count=5)
            import random
            topic = random.choice(variations)
            log_event("automation_topic_variation", automation_id=automation.id, original=topic_base, selected=topic)
        except Exception as e:
            print(f"[AUTO] Topic variation failed: {e}")
            topic = topic_base

        # 2. NEW: Modular Content Provider Polling
        from app.services.content_providers import UserLibraryProvider, SystemLibraryProvider
        
        provider_scope = getattr(automation, "content_provider_scope", "all_sources")
        active_providers = []
        
        if provider_scope in ["all_sources", "user_library"]:
            active_providers.append(UserLibraryProvider())
            
        if provider_scope in ["all_sources", "system_library"]:
            active_providers.append(SystemLibraryProvider())
            
        pooled_items = []
        target_limit = getattr(automation, "items_per_post", 1) or 1
        
        for provider in active_providers:
            needed = target_limit - len(pooled_items)
            if needed <= 0: break
            
            try:
                items = provider.get_content(db, automation.org_id, topic, limit=needed)
                pooled_items.extend(items)
                if items:
                    log_event("provider_content_sourced", 
                              automation_id=automation.id, 
                              provider=provider.provider_name, 
                              count=len(items))
            except Exception as e:
                print(f"[PROVIDER] Error in {provider.provider_name}: {e}")
                
        # [SAFETY] Guardrail: Abort if exactly 0 items found
        if not pooled_items:
            log_event("automation_no_content_found", automation_id=automation.id, topic=topic, scope=provider_scope)
            automation.last_error = "No verified content found across chosen providers."
            new_post = Post(
                org_id=automation.org_id,
                ig_account_id=automation.ig_account_id,
                is_auto_generated=True,
                automation_id=automation.id,
                status="failed",
                source_type="automation",
                source_text=f"AUTO: {automation.name} | topic={topic}",
                caption="",
                flags={"automation_error": "No verified content found across chosen providers.", "reason": "no_content_found"}
            )
            db.add(new_post)
            db.commit()
            return new_post

        # 1.5 Content Profile Injection
        content_profile_prompt = None
        if getattr(automation, "content_profile_id", None):
            from app.models import ContentProfile
            profile = db.query(ContentProfile).filter(ContentProfile.id == automation.content_profile_id).first()
            if profile:
                prompt_parts = []
                if profile.niche_category: prompt_parts.append(f"You are generating content for a {profile.niche_category} brand.")
                if profile.focus_description: prompt_parts.append(f"Focus: {profile.focus_description}")
                if profile.content_goals: prompt_parts.append(f"Goal: {profile.content_goals}")
                if profile.tone_style: prompt_parts.append(f"Tone: {profile.tone_style}")
                if profile.allowed_topics: prompt_parts.append(f"Core Topics to Discuss: {', '.join(profile.allowed_topics)}")
                if profile.banned_topics: prompt_parts.append(f"AVOID Discussing: {', '.join(profile.banned_topics)}")
                content_profile_prompt = "\\n".join(prompt_parts)

        # 2. Build Context payload & Generate
        context_payload = {
            "topic": topic,
            "style": automation.style_preset,
            "tone": automation.tone or "medium",
            "language": automation.language or "english",
            "banned_phrases": automation.banned_phrases if isinstance(automation.banned_phrases, list) else None,
            "source_items": [
                {
                    "title": item.source, 
                    "text": item.text, 
                    "reference": item.reference, 
                    "arabic_text": item.arabic_text,
                    "id": item.original_id,
                    "provider": item.provider
                }
                for item in pooled_items
            ],
            "content_profile_prompt": content_profile_prompt,
            "creativity_level": getattr(automation, "creativity_level", 3),
            "source_mode": getattr(automation, "source_mode", "balanced"),
            "tone_style": getattr(automation, "tone_style", "deep"),
            "verification_mode": getattr(automation, "verification_mode", "standard"),
            "instructions": [
                "Do NOT output the topic label literally.",
                "Do NOT output 'AUTO: <name>' literally as the caption.",
                "You MUST build the post primarily around the structured `source_items` provided below.",
                "DO NOT hallucinate or generate quotes/hadith/verses that are not explicitly provided in the `source_items`.",
                "Always cite the exact reference provided.",
                f"SOURCE MODE: {getattr(automation, 'source_mode', 'balanced')}. (Strict means only use provided items, Balanced means you can add connective tissue/context).",
                f"TONE STYLE: {getattr(automation, 'tone_style', 'deep')}. (Apply this specific voice to the writing)."
            ],
        }

        print(f"[AUTO] Generating for automation_id={automation.id} topic='{topic}'")
        
        try:
            result = generate_topic_caption(
                topic=topic,
                style=automation.style_preset,
                tone=automation.tone or "medium",
                language=automation.language or "english",
                banned_phrases=automation.banned_phrases if isinstance(automation.banned_phrases, list) else None,
                content_profile_prompt=content_profile_prompt,
                creativity_level=getattr(automation, "creativity_level", 3),
                extra_context=context_payload
            )
            caption = result.get("caption", "").strip()
            hashtags = result.get("hashtags", [])
            alt_text = result.get("alt_text", "")
        except Exception as e:
            print(f"[AUTO] LLM Generation failed: {e}")
            automation.last_error = f"LLM Generation failed: {str(e)}"
            db.commit()
            return None
            
        if automation.hashtag_set:
            hashtags = automation.hashtag_set
            
        log_event("automation_caption_generated", automation_id=automation.id, caption_len=len(caption), hashtags_count=len(hashtags))
        
        # 3. Media Selection / Generation
        primary_item = pooled_items[0] if pooled_items else None
        concepts = primary_item.topic_tags[0] if primary_item and primary_item.topic_tags else None
        media_url = None
        
        # SPECIAL: Quote Card Mode
        if automation.image_mode == "quote_card":
            quote_text = primary_item.text if primary_item else topic
            reference = primary_item.reference if primary_item else ""
            
            # Prefer library image
            bg_url = resolve_media_url(
                db=db, org_id=automation.org_id, ig_account_id=automation.ig_account_id,
                image_mode="use_library_image", media_asset_id=automation.media_asset_id,
                media_tag_query=automation.media_tag_query
            )
            # Fallback to AI nature
            if not bg_url:
                bg_url = resolve_media_url(
                    db=db, org_id=automation.org_id, ig_account_id=automation.ig_account_id,
                    image_mode="ai_nature_photo", topic=topic, automation_id=automation.id
                )
            
            if bg_url:
                try:
                    import requests
                    import time
                    bg_res = requests.get(bg_url, timeout=30)
                    if bg_res.status_code == 200:
                        tmp_bg_path = os.path.join(settings.uploads_dir, f"tmp_bg_{int(time.time())}.jpg")
                        with open(tmp_bg_path, "wb") as f:
                            f.write(bg_res.content)
                        
                        media_url = render_quote_card(tmp_bg_path, quote_text, reference, settings.uploads_dir)
                        if os.path.exists(tmp_bg_path): os.remove(tmp_bg_path)
                            
                        if "." in caption:
                            caption = caption.split(".")[0] + "."
                        else:
                            caption = f"{reference}"
                    else:
                        raise Exception(f"Failed to download background: {bg_res.status_code}")
                except Exception as e:
                    print(f"[AUTO] Quote card rendering failed: {e}")
                    log_event("automation_media_error", automation_id=automation.id, error=str(e))
        else:
            try:
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
            except Exception as e:
                print(f"[AUTO] Media resolution error: {e}")

        # FALLBACK: If AI generation failed, try to reuse last upload
        if not media_url and automation.image_mode != "quote_card" and "ai" in (automation.image_mode or ""):
            media_url = resolve_media_url(
                db=db, org_id=automation.org_id, ig_account_id=automation.ig_account_id,
                image_mode="reuse_last_upload", topic=topic
            )

        # 4. Create Post
        status = "scheduled"
        if automation.approval_mode == "needs_manual_approve":
            status = "drafted"
            
        source_text = f"AUTO: {automation.name} | topic={topic}"
        if primary_item:
            source_text += f" | provider={primary_item.provider} | ref={primary_item.original_id}"

        new_post = Post(
            org_id=automation.org_id,
            ig_account_id=automation.ig_account_id,
            is_auto_generated=True,
            automation_id=automation.id,
            content_item_id=int(primary_item.original_id) if primary_item and primary_item.original_id and primary_item.original_id.isdigit() else None,
            used_source_id=None,
            used_content_item_ids=[it.original_id for it in pooled_items if it.original_id],
            status=status,
            source_type="automation",
            source_text=source_text,
            media_url=media_url,
            caption=caption,
            hashtags=hashtags,
            alt_text=alt_text,
            scheduled_time=compute_next_run_time(db.get(IGAccount, automation.ig_account_id), automation) if status == "scheduled" else None
        )
        
        # 5. Guardrail & Validation
        auto_str = f"AUTO: {automation.name}"
        caption_lower = caption.lower()
        filler_indicators = ["enhance your daily reminder", "welcome to our page", "here is your caption"]
        
        is_filler = any(f in caption_lower for f in filler_indicators)
        is_too_short = len(caption) < 20
        is_default = caption.strip() == topic.strip() or caption.strip() == auto_str or caption.strip() == automation.name
        
        validation_failed = result.get("validation_failed", False)
        fail_reason = result.get("fail_reason", "invalid_caption")
        
        if validation_failed or not caption or is_default or is_filler or is_too_short:
            reason = "invalid_generated_caption"
            detail_reason = fail_reason
            if is_filler: detail_reason = "filler_detected"
            if is_too_short: detail_reason = "too_short"
            if is_default: detail_reason = "default_text_echo"
            
            print(f"[AUTO] FAILED GUARDRAIL: {detail_reason}")
            log_event("automation_guardrail_failed", automation_id=automation.id, reason=detail_reason)
            new_post.status = "failed"
            new_post.flags = {"automation_error": f"LLM returned invalid/filler caption: {caption}", "reason": reason, "detail_reason": detail_reason}
            automation.last_error = f"Guardrail check failed: {detail_reason}"
            db.add(new_post)
            db.commit()
            return new_post

        if not media_url:
            new_post.status = "failed"
            new_post.flags = {"automation_error": "media_url is missing/generation failed"}
            automation.last_error = "Media generation failed or asset missing"
            db.add(new_post)
            db.commit()
            return new_post

        db.add(new_post)
        db.flush() 
        
        # 6. Track Usage (Updated for decoupled items)
        for it in pooled_items:
            if it.original_id and it.original_id.isdigit():
                usage = ContentUsage(
                    org_id=automation.org_id,
                    ig_account_id=automation.ig_account_id,
                    automation_id=automation.id,
                    post_id=new_post.id,
                    content_item_id=int(it.original_id),
                    used_at=datetime.now(dt_timezone.utc),
                    status="selected"
                )
                db.add(usage)
            
            if it.original_id and it.original_id.isdigit():
                db_item = db.get(ContentItem, int(it.original_id))
                if db_item:
                    db_item.use_count += 1
                    db_item.last_used_at = datetime.now(dt_timezone.utc)

        # 7. Immediate Publishing if configured
        if automation.posting_mode == "publish_now" and automation.approval_mode == "auto_approve":
            log_event("automation_publish_attempt", automation_id=automation.id, post_id=new_post.id)
            acc = db.get(IGAccount, automation.ig_account_id)
            pub_res = publish_to_instagram(
                caption=f"{new_post.caption}\\n\\n" + " ".join(new_post.hashtags or []),
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
        import traceback
        log_event("automation_run_exception", automation_id=automation_id, error=str(e), traceback=traceback.format_exc(limit=3))
        print(f"[AUTO] ERROR in runner for automation_id={automation_id}: {repr(e)}")
        logger.error(f"Automation {automation_id} failed: {e}")
        automation.last_error = str(e)
        db.commit()
        return None
