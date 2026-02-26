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
        topic_base = automation.topic_prompt
        log_event("automation_run_start", automation_id=automation.id, topic=topic_base, style=automation.style_preset)
        
        # 1. Topic Variations (Sub-angles)
        try:
            variations = generate_topic_variations(topic_base, count=5)
            import random
            topic = random.choice(variations)
            log_event("automation_topic_variation", automation_id=automation.id, original=topic_base, selected=topic)
        except Exception as e:
            print(f"[AUTO] Topic variation failed: {e}")
            topic = topic_base

        # 2. Content Seed & Library Retrieval
        selected_items = []
        library_context = None
        seed_mode = getattr(automation, "content_seed_mode", "none") or "none"
        
        if seed_mode == "auto_library":
            chunks = retrieve_relevant_chunks(db, automation.org_id, topic, k=5)
            if chunks:
                library_context = {
                    "mode": "auto_library",
                    "sources": chunks,
                    "manual_seed": None
                }
            else:
                log_event("automation_no_library_sources", automation_id=automation.id, topic=topic)
                # Fallback: still generate but flag it
                library_context = {
                    "mode": "none",
                    "sources": [],
                    "manual_seed": None
                }
        elif seed_mode == "manual":
            seed_text = getattr(automation, "content_seed_text", None)
            library_context = {
                "mode": "manual_seed",
                "sources": [],
                "manual_seed": seed_text
            }
        
        # NEW: Prebuilt Packs Retrieval
        lib_scope = getattr(automation, "library_scope", []) or []
        if "prebuilt" in lib_scope:
            packs = load_prebuilt_packs()
            match = None
            norm_topic = topic.lower().strip()
            
            # Simple keyword/tag matcher
            for pack in packs:
                for item in pack.get("items", []):
                    # Check tags
                    if norm_topic in [t.lower() for t in item.get("tags", [])]:
                        match = item
                        break
                    # Check keywords in text
                    if norm_topic in item["text"].lower():
                        match = item
                        break
                if match: break
            
            if match:
                # If we already have library_context from auto_library, we might want to prioritize prebuilt
                # or merge. The requirement says: "Select MAX 1 snippet. Pass into generate_topic_caption as structured extra_context"
                # So we override or set it.
                library_context = {
                    "mode": "grounded_library",
                    "topic": topic,
                    "snippet": {
                        "text": match["text"],
                        "reference": match.get("reference"),
                        "source": match.get("source")
                    }
                }
            elif not library_context:
                # If no prebuilt match and no auto_library context, set a default
                library_context = {"mode": "none"}
        
        # 3. Content Selection (Legacy/Other Sources)
        new_cursor = automation.last_item_cursor

        # NEW: Pluggable Content Sources
        try:
            if getattr(automation, "source_id", None) and getattr(automation, "source_mode", "none") != "none":
                selected_items, new_cursor = select_items_for_automation(
                    db,
                    org_id=automation.org_id,
                    source_id=automation.source_id,
                    items_per_post=getattr(automation, "items_per_post", 1) or 1,
                    selection_mode=getattr(automation, "selection_mode", "random") or "random",
                    last_item_cursor=automation.last_item_cursor,
                )
        except Exception as e:
            print(f"[AUTO] Source selection failed: {e}")
            log_event("automation_source_error", automation_id=automation.id, error=str(e))
        
        # LEGACY: Content Library (if no items from sources and enabled)
        if not selected_items and automation.use_content_library:
            try:
                content_item = pick_content_item(
                    db=db,
                    org_id=automation.org_id,
                    topic=topic,
                    content_type=automation.content_type,
                    avoid_repeat_days=automation.avoid_repeat_days,
                    automation_id=automation.id,
                    ig_account_id=automation.ig_account_id
                )
                if content_item:
                    selected_items = [content_item]
            except Exception as e:
                print(f"[AUTO] Library selection failed: {e}")

        # If we have NEITHER selected items NOR library chunks, and we are in auto_library mode, we flag it.
        # But per requirements if library empty -> still generate generic.

        # 1.5 Content Profile Injection
        content_profile_prompt = None
        if getattr(automation, "content_profile_id", None):
            from app.models import ContentProfile
            profile = db.query(ContentProfile).filter(ContentProfile.id == automation.content_profile_id).first()
            if profile:
                prompt_parts = []
                if profile.niche_category:
                    prompt_parts.append(f"You are generating content for a {profile.niche_category} brand.")
                if profile.focus_description:
                    prompt_parts.append(f"Focus: {profile.focus_description}")
                if profile.content_goals:
                    prompt_parts.append(f"Goal: {profile.content_goals}")
                if profile.tone_style:
                    prompt_parts.append(f"Tone: {profile.tone_style}")
                if profile.allowed_topics:
                    prompt_parts.append(f"Core Topics to Discuss: {', '.join(profile.allowed_topics)}")
                if profile.banned_topics:
                    prompt_parts.append(f"AVOID Discussing: {', '.join(profile.banned_topics)}")
                
                content_profile_prompt = "\n".join(prompt_parts)

        # 2. Build Context payload & Generate
        context_payload = {
            "topic": topic,
            "style": automation.style_preset,
            "tone": automation.tone or "medium",
            "language": automation.language or "english",
            "banned_phrases": automation.banned_phrases if isinstance(automation.banned_phrases, list) else None,
            "source_items": [
                {"title": getattr(it, "title", None), "text": getattr(it, "text", it.text_en if hasattr(it, "text_en") else ""), "url": getattr(it, "url", None), "id": it.id}
                for it in selected_items
            ],
            "content_seed": getattr(automation, "content_seed", None),
            "content_profile_prompt": content_profile_prompt,
            "creativity_level": getattr(automation, "creativity_level", 3),
            "instructions": [
                "Do NOT output the topic label literally.",
                "Do NOT output 'AUTO: <name>' literally as the caption.",
                "If source_items are provided, incorporate at least 1 item meaningfully.",
                "Avoid music references and other disallowed content per policy.",
            ],
        }
        
        # Merge Library Context
        if library_context:
            context_payload.update(library_context)
            if library_context.get("mode") == "auto_library" and not library_context.get("sources"):
                context_payload["instructions"].append("No library sources found for this topic. Generate a generic educational caption WITHOUT and quotes or citations.")

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
            return None # Re-raise or handle as hard failure
            
        if automation.hashtag_set:
            hashtags = automation.hashtag_set
            
        log_event("automation_caption_generated", automation_id=automation.id, caption_len=len(caption), hashtags_count=len(hashtags))
        
        # 3. Media Selection / Generation
        primary_item = selected_items[0] if selected_items else None
        concepts = primary_item.topics[0] if primary_item and hasattr(primary_item, "topics") and primary_item.topics else None
        
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
            media_url = None

        # FALLBACK: If AI generation failed, try to reuse last upload
        if not media_url and "ai" in (automation.image_mode or ""):
            print("[AUTO] AI Media failed. Falling back to reuse_last_upload...")
            media_url = resolve_media_url(
                db=db,
                org_id=automation.org_id,
                ig_account_id=automation.ig_account_id,
                image_mode="reuse_last_upload",
                topic=topic
            )
        
        # 4. Final Post Creation
        if automation.image_mode == "quote_card" or (media_url is None and automation.image_mode != "none_placeholder" and primary_item):
            # Generate a quote card
            try:
                filename = f"quote_{automation.id}_{int(datetime.now().timestamp())}.jpg"
                file_path = os.path.join(settings.uploads_dir, filename)
                
                text_to_use = getattr(primary_item, "text", getattr(primary_item, "text_en", ""))
                attribution = getattr(primary_item, "source_name", "")
                if getattr(primary_item, "reference", None):
                    attribution += f" ({primary_item.reference})"
                
                create_quote_card(text_to_use, attribution, file_path)
                media_url = f"{settings.public_base_url.rstrip('/')}/uploads/{filename}"
                print(f"[AUTO] Quote card generated: {media_url}")
            except Exception as e:
                print(f"[AUTO] Quote card failed: {e}")

        # 4. Create Post
        status = "scheduled"
        flags = {}
        
        if seed_mode == "auto_library" and library_context and not library_context.get("sources"):
            status = "needs_review"
            flags["reason"] = "no_library_sources_found"
            
        if automation.approval_mode == "needs_manual_approve" and status != "needs_review":
            status = "drafted"
            
        source_text = f"AUTO: {automation.name} | topic={topic}"
        if primary_item:
            source_text += f" | content_id={primary_item.id}"

        new_post = Post(
            org_id=automation.org_id,
            ig_account_id=automation.ig_account_id,
            is_auto_generated=True,
            automation_id=automation.id,
            content_item_id=primary_item.id if primary_item else None,
            used_source_id=automation.source_id if selected_items else None,
            used_content_item_ids=[it.id for it in selected_items],
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
        is_default = caption.strip() == topic.strip() or caption.strip() == auto_str
        
        validation_failed = result.get("validation_failed", False)
        fail_reason = result.get("fail_reason", "invalid_caption")
        
        if validation_failed or not caption or is_default or is_filler or is_too_short:
            reason = fail_reason
            if is_filler: reason = "filler_detected"
            if is_too_short: reason = "too_short"
            if is_default: reason = "default_text_echo"
            
            print(f"[AUTO] FAILED GUARDRAIL: {reason}. Output: {caption[:50]}...")
            log_event("automation_guardrail_failed", automation_id=automation.id, reason=reason)
            new_post.status = "failed"
            new_post.flags = {
                "automation_error": f"LLM returned invalid/filler caption: {caption}", 
                "reason": reason,
                "raw_result": result
            }
            automation.last_error = f"Guardrail check failed: {reason}"
            db.add(new_post)
            db.commit()
            return new_post

        # 5.5 Media Validation Guardrail
        if not media_url:
            print(f"[AUTO] FAILURE: media_url is missing. Mode: {automation.image_mode}")
            new_post.status = "failed"
            new_post.flags = {"automation_error": "media_url is missing/generation failed"}
            automation.last_error = "Media generation failed or asset missing"
            db.add(new_post)
            db.commit()
            return new_post

        db.add(new_post)
        db.flush() # Get new_post.id
        
        # 6. Track Usage
        if selected_items:
            mark_items_used(db, selected_items)
            automation.last_item_cursor = str(new_cursor) if new_cursor else None
            
            for it in selected_items:
                usage = ContentUsage(
                    org_id=automation.org_id,
                    ig_account_id=automation.ig_account_id,
                    automation_id=automation.id,
                    post_id=new_post.id,
                    content_item_id=it.id,
                    used_at=datetime.now(dt_timezone.utc),
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
