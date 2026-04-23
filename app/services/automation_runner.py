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
from app.services.image_renderer import render_quote_card, render_minimal_quote_card
from app.services.relevance_engine import validate_source_relevance
from app.config import settings
import pytz
import os
import requests
from app.services.content_sources import select_items_for_automation, mark_items_used
from app.logging_setup import log_event

logger = logging.getLogger(__name__)
import threading
_automation_locks = {}
_locks_mutex = threading.Lock()

def get_lock_for_automation(automation_id: int):
    with _locks_mutex:
        if automation_id not in _automation_locks:
            _automation_locks[automation_id] = threading.Lock()
        return _automation_locks[automation_id]

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

def clean_translation_for_card(text: str) -> str:
    """
    Cleans up translator artifacts like [brackets] for a more premium visual card look.
    Removes the brackets but keeps the inner text if it feels like part of the flow.
    Also removes footnote digits (e.g. "verily. 1") that clutter the card.
    """
    import re
    if not text: return ""
    # 1. Remove brackets but keep the content inside them
    cleaned = re.sub(r'\[(.*?)\]', r'\1', text)
    # 2. Remove footnote digits at the end of sentences (e.g., ". 1" or "word. 12")
    # This matches a digit that appears at the end of a string or after a period/space
    cleaned = re.sub(r'(?<=\.)\s*\d+\b', '', cleaned)
    cleaned = re.sub(r'\s+\d+\s*$', '', cleaned)
    
    # 3. Remove digit artifacts like "Iblees;1" or explicit footnotes like " (1) "
    cleaned = re.sub(r';\d+', '', cleaned)
    cleaned = re.sub(r'\(\s*\d+\s*\)', '', cleaned)
    
    # 4. Remove stray punctuation at the start or loose artifacts
    cleaned = cleaned.strip()
    
    # 5. Collapse whitespace
    return " ".join(cleaned.split())

def format_hashtags(tags: list[str]) -> list[str]:
    """Converts space-separated or raw tags into proper CamelCase #hashtags."""
    if not tags: return []
    formatted = []
    for t in tags:
        # CamelCase: capitalize every word, remove spaces
        camel = "".join([w.capitalize() for w in t.replace("#", "").split()])
        if camel:
            formatted.append(f"#{camel}")
    return formatted[:10] # limit to 10 for clean look

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
        if last_post:
            return last_post.media_url
        
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
                    from app.config import build_public_media_url
                    final_url = build_public_media_url(filename)
                    
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

def run_automation_once(db: Session, automation_id: int, force_publish: bool = False) -> Post | None:
    """
    Core engine to run one automation cycle using the decoupled Content Provider architecture.
    """
    lock = get_lock_for_automation(automation_id)
    if not lock.acquire(blocking=False):
        print(f"🔒 [LOCK] Automation {automation_id} is already in progress. Skipping duplicate execution.")
        return None
    
    try:
        automation = db.query(TopicAutomation).filter(TopicAutomation.id == automation_id).first()
        if not automation or not automation.enabled:
            return None
        
        # 1. Topic Pool Rotation Logic
        pool = automation.topic_pool or []
        topic_base = automation.topic_prompt
        
        post_count = db.query(Post).filter(Post.automation_id == automation.id).count()
        if pool:
            topic_base = pool[post_count % len(pool)]
            log_event("automation_topic_selected", automation_id=automation.id, topic=topic_base, index=post_count % len(pool))

        # 2. Pillar Rotation Logic
        pillars = automation.pillars or []
        if pillars:
            selected_pillar = pillars[post_count % len(pillars)]
            # If topic exists, use it as grounding context, otherwise use pillar as main topic
            topic_base = f"{selected_pillar}: {topic_base}" if topic_base else selected_pillar
            log_event("automation_pillar_selected", automation_id=automation.id, pillar=selected_pillar, index=post_count % len(pillars))

        # PHASE 2: Load Style DNA System
        from app.services.automation_service import get_automation_style_dna
        style_dna_spec = get_automation_style_dna(db, automation)

        log_event("automation_run_start", automation_id=automation.id, topic=topic_base, style=automation.style_preset)
        print(f"[STYLE_DNA] preset loaded: {style_dna_spec.family} (Atmosphere: {style_dna_spec.atmosphere})")
        
        # 1. Topic Variations
        try:
            variations = generate_topic_variations(topic_base, count=5)
            import random
            topic = random.choice(variations)
            log_event("automation_topic_variation", automation_id=automation.id, original=topic_base, selected=topic)
        except Exception as e:
            print(f"[AUTO] Topic variation failed: {e}")
            topic = topic_base

        # 2. Modular Content Provider Polling
        from app.services.content_providers import UserLibraryProvider, SystemLibraryProvider
        
        provider_scope = getattr(automation, "content_provider_scope", "all_sources")
        active_providers = []
        
        if provider_scope in ["all_sources", "user_library"]:
            active_providers.append(UserLibraryProvider())
            
        if provider_scope in ["all_sources", "system_library"]:
            active_providers.append(SystemLibraryProvider())
            
        pooled_items = []
        target_limit = 5 # Fetch more for filtering pool
        
        # Dual-pass logic: Try the variation first, then the base topic
        attempts = [topic, topic_base] if topic != topic_base else [topic]
        
        for search_query in attempts:
            if pooled_items: break # Found enough in first pass
            
            for provider in active_providers:
                needed = target_limit - len(pooled_items)
                if needed <= 0: break
                
                try:
                    items = provider.get_content(db, automation.org_id, search_query, limit=needed)
                    pooled_items.extend(items)
                    if items:
                        log_event("provider_content_sourced", 
                                  automation_id=automation.id, 
                                  provider=provider.provider_name, 
                                  count=len(items),
                                  query=search_query)
                except Exception as e:
                    print(f"[PROVIDER] Error in {provider.provider_name}: {e}")
                
        # 1.45 Relevance Filtering Gate (v2 Integrity)
        primary_item = None
        relevance_results = {}
        fallback_mode = False
        
        # We audit up to the first 3 candidates
        for candidate in pooled_items[:3]:
            audit = validate_source_relevance(topic_base, candidate.text, candidate.reference)
            relevance_results[candidate.original_id] = audit
            
            if audit["accepted"]:
                # QUALITY GATE FIX: Ensure Arabic exists for Quran posts
                is_quran = "quran" in (candidate.provider or "").lower()
                if is_quran and (not candidate.arabic_text or len(candidate.arabic_text) < 10):
                    print(f"📡 [QURAN_ARABIC] fetching Arabic for confirmed Quran candidate: {candidate.reference}")
                    try:
                        from app.services.quran_service import get_verse_by_reference
                        item = get_verse_by_reference(db, candidate.reference)
                        if item and item.arabic_text:
                            candidate.arabic_text = item.arabic_text
                            print(f"📡 [QURAN_ARABIC] loaded")
                        else:
                            print(f"⚠️ [QURAN_ARABIC] fetch failed for {candidate.reference}. Rejecting.")
                            continue
                    except Exception as e:
                        print(f"⚠️ [QURAN_ARABIC] fetch error: {e}")
                        continue

                primary_item = candidate
                log_event("quran_relevance_passed", automation_id=automation.id, reference=candidate.reference, reason=audit["reason"])
                break
            else:
                log_event("quran_relevance_rejected", automation_id=automation.id, reference=candidate.reference, reason=audit["reason"])

        if not primary_item:
            # FALLBACK: No highly relevant verse found -> Switch to Reflection Mode
            fallback_mode = True
            log_event("automation_relevance_fallback", automation_id=automation.id, topic=topic_base)
            print(f"⚠️ [RELEVANCE] No high-confidence match found for '{topic_base}'. Falling back to Reflection Mode.")
            # Use the first item anyway if it's not empty, but mark as reflection
            primary_item = pooled_items[0] if pooled_items else None

        # [SAFETY] Guardrail: Abort if exactly 0 items found
        if not primary_item:
            log_event("automation_no_content_found", automation_id=automation.id, topic=topic, scope=provider_scope)
            automation.last_error = "No verified content found across chosen providers."
            db.commit()
            return None

        # QUALITY GATE FIX: Re-check Arabic for Quran posts again to be absolutely sure
        if not fallback_mode and "quran" in (primary_item.provider or "").lower():
            if not primary_item.arabic_text:
                print(f"❌ [QUALITY_GATE] BLOCKING: Arabic missing for confirmed Quran post {primary_item.reference}.")
                automation.last_error = f"Arabic source missing for {primary_item.reference}. Re-run needed."
                db.commit()
                return None

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
        import random
        chosen_variation = random.choice(style_dna_spec.variation_pool) if style_dna_spec.variation_pool else "standard"
        print(f"[STYLE_DNA] variation chosen: {chosen_variation}")
        print(f"[STYLE_DNA] visual payload built")

        # 1.6 Source Selection & Grounding (v2 Consistency Fix)
        # Determine the definitive reference for the entire post
        if fallback_mode:
            final_reference = f"{topic_base.split(':')[0].strip().capitalize()} Reflection"
        else:
            final_reference = (primary_item.reference if primary_item else "").strip()
            
        if not final_reference: final_reference = "Sacred Guidance"
        # Clean text for visual cards but keep original for caption if needed
        uncleaned_text = primary_item.text if primary_item else topic
        quote_text_cleaned = clean_translation_for_card(uncleaned_text)

        print(f"[POST_SOURCE] selected source: {final_reference}")

        context_payload = {
            "topic": topic,
            "style": style_dna_spec.family,
            "tone": automation.tone or "medium",
            "language": automation.language or "english",
            "mode": "grounded_library",  # FORCE GROUNDING
            "snippet": {
                "item_type": "quran" if "quran" in (primary_item.provider if primary_item else "").lower() else "reference",
                "text": uncleaned_text,
                "reference": final_reference
            },
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
            "source_mode": "strict", # Enforce single source
            "tone_style": style_dna_spec.tone_style,
            "verification_mode": getattr(automation, "verification_mode", "standard"),
            "instructions": [
                "Do NOT output the topic label literally.",
                "Do NOT output 'AUTO: <name>' literally as the caption.",
                f"You MUST use the provided GROUNDED SNIPPET (ref: {final_reference}) as your primary source.",
                f"The citation in your caption MUST EXACTLY match: {final_reference}.",
                "DO NOT hallucinate other verses.",
                f"TONE STYLE: {getattr(automation, 'tone_style', 'deep')}."
            ],
        }

        print(f"[AUTO] Generating for automation_id={automation.id} topic='{topic}'")
        
        try:
            result = generate_topic_caption(
                topic=topic,
                style=style_dna_spec.family,
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
            
        # CamelCase Formatting for clean footer
        hashtags = format_hashtags(hashtags)
            
        log_event("automation_caption_generated", automation_id=automation.id, caption_len=len(caption), hashtags_count=len(hashtags))
        
        # 3. Resolve Media & Recovery Recipe Ingredients
        concepts = primary_item.topic_tags[0] if primary_item and primary_item.topic_tags else None
        
        # Use early-defined ingredients
        quote_text = quote_text_cleaned
        reference = final_reference
        
        media_url = None
        
        # SPECIAL: Quote Card Mode (v9.0 Premium Upgrade)
        if automation.image_mode == "quote_card":
            
            # 1. Resolve Background
            bg_url = resolve_media_url(
                db=db, org_id=automation.org_id, ig_account_id=automation.ig_account_id,
                image_mode="use_library_image", media_asset_id=automation.media_asset_id,
                media_tag_query=automation.media_tag_query
            )
            if not bg_url:
                bg_url = resolve_media_url(
                    db=db, org_id=automation.org_id, ig_account_id=automation.ig_account_id,
                    image_mode="ai_nature_photo", topic=topic, automation_id=automation.id
                )
            
            # 2. Render Premium Quote Card
            try:
                # 1. Reference (Top Zone)
                card_segments = [
                    {"text": reference.upper(), "size": 36}
                ]
                
                # 2. Arabic (Middle Zone) - Prominent if exists
                is_quran = "quran" in (primary_item.provider if primary_item else "").lower() and not fallback_mode
                if is_quran and primary_item.arabic_text:
                    card_segments.append({"text": primary_item.arabic_text, "size": 60, "is_arabic": True})
                    # Use smaller English quote if Arabic exists to avoid overcrowding
                    card_segments.append({"text": quote_text, "size": 52})
                else:
                    # Standard Single-Language Layout
                    card_segments.append({"text": quote_text, "size": 72})
                
                print(f"📡 [v9.0] Rendering premium {'Dual-Language ' if is_quran else ''}card for {reference}")
                
                # Download bg if exists, otherwise render_minimal_quote_card will use preset/AI
                tmp_bg_path = None
                if bg_url:
                     import requests, time
                     bg_res = requests.get(bg_url, timeout=30)
                     if bg_res.status_code == 200:
                         tmp_bg_path = os.path.join(settings.uploads_dir, f"tmp_bg_{int(time.time())}.jpg")
                         with open(tmp_bg_path, "wb") as f: f.write(bg_res.content)
                
                # CALL PREMIUM RENDERER
                media_url = render_minimal_quote_card(
                    segments=card_segments,
                    output_dir=settings.uploads_dir,
                    style=automation.style_preset or "quran",
                    visual_prompt=style_dna_spec.visual_prompt,
                    mode="custom" if style_dna_spec.visual_prompt else "preset",
                    text_style_prompt=style_dna_spec.glow_aura # reuse aura context for text style bias
                )
                
                if tmp_bg_path and os.path.exists(tmp_bg_path): os.remove(tmp_bg_path)
                
                # Check for source mismatch in caption (v2 Guardrail)
                reference_clean = reference.replace("Qur'an", "").replace("Quran", "").strip()
                if reference_clean.lower() not in caption.lower() and ":" in reference:
                    print(f"❌ [POST_SOURCE_MISMATCH] BLOCKING: reference {reference} not found in caption.")
                    automation.last_error = f"Source mismatch detected: Card={reference}, Caption source missing."
                    db.commit()
                    return None
                    # We don't block here yet, but we log it.

            except Exception as e:
                print(f"[AUTO] Premium Quote card rendering failed: {e}")
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

        # FALLBACK: If all primary modes failed, force a high-quality Quote Card generation
        if not media_url:
            print(f"[AUTO] Forced fallback to quote_card for automation {automation.id}")
            
            # Call Premium Renderer as fallback
            try:
                card_segments = [
                    {"text": reference.upper(), "size": 36},
                    {"text": quote_text, "size": 72}
                ]
                media_url = render_minimal_quote_card(
                    segments=card_segments,
                    output_dir=settings.uploads_dir,
                    style=automation.style_preset or "quran",
                    visual_prompt=style_dna_spec.visual_prompt,
                    mode="custom" if style_dna_spec.visual_prompt else "preset"
                )
            except Exception as e:
                print(f"[AUTO] Forced fallback rendering failed: {e}")

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
            scheduled_time=compute_next_run_time(db.get(IGAccount, automation.ig_account_id), automation) if status == "scheduled" else None,
            # RECOVERY RECIPE: Store ingredients for just-in-time regeneration
            source_metadata={
                "recovery_recipe": {
                    "quote_text": quote_text,
                    "reference": final_reference,
                    "bg_url": bg_url if 'bg_url' in locals() else None,
                    "visual_mode": automation.image_mode if not fallback_mode else "quote_card",
                    "style": automation.style_preset
                },
                "is_fallback_reflection": fallback_mode,
                "relevance_audit": relevance_results.get(primary_item.original_id) if primary_item else None
            },
            flags={"relevance_check": "fallback" if fallback_mode else "passed"}
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

        # 7. Immediate Publishing if configured OR forced
        should_publish = force_publish or (automation.posting_mode == "publish_now" and automation.approval_mode == "auto_approve")
        
        if should_publish:
            log_event("automation_publish_attempt", automation_id=automation.id, post_id=new_post.id, forced=force_publish)
            acc = db.get(IGAccount, automation.ig_account_id)
            
            if force_publish:
                print(f"🚀 [SHARE_NOW] Triggered for automation_id={automation.id}")

            print(f"📡 [IG_PUBLISH] Starting for post_id={new_post.id}")
            print(f"🔍 [MEDIA_PREFLIGHT] Checking integrity of {new_post.media_url}")

            pub_res = publish_to_instagram(
                caption=f"{new_post.caption}\n\n" + " ".join(new_post.hashtags or []),
                media_url=new_post.media_url,
                ig_user_id=acc.ig_user_id,
                access_token=acc.access_token
            )
            
            # --- AUTO-RECOVERY RETRY LOOP ---
            if not pub_res.get("ok") and pub_res.get("error") in ["media_asset_stale", "MEDIA_STALE_OR_MISSING"]:
                print(f"🔄 [MEDIA_RECOVERY] Stale media detected. Attempting automatic regeneration...")
                recovery_success = recover_stale_media(new_post, db)
                
                if recovery_success:
                    print(f"✅ [MEDIA_RECOVERY] Regeneration successful. Retrying publish...")
                    print(f"🔍 [MEDIA_PREFLIGHT] Retry check for {new_post.media_url}")
                    pub_res = publish_to_instagram(
                        caption=f"{new_post.caption}\n\n" + " ".join(new_post.hashtags or []),
                        media_url=new_post.media_url,
                        ig_user_id=acc.ig_user_id,
                        access_token=acc.access_token
                    )
                else:
                    print(f"❌ [MEDIA_RECOVERY] Regeneration failed. Blocking publish.")

            if pub_res.get("ok"):
                print(f"✨ [IG_PUBLISH] Success! Post shared to Instagram.")
                new_post.status = "published"
                new_post.published_time = datetime.now(dt_timezone.utc)
            else:
                new_post.status = "failed"
                publish_err = pub_res.get("error")
                
                if publish_err in ["media_asset_stale", "MEDIA_STALE_OR_MISSING"]:
                    publish_err = "Media asset wiped from ephemeral storage (stale). Please regenerate manually."
                elif isinstance(publish_err, dict):
                    publish_err = publish_err.get("message") or str(publish_err)
                
                new_post.flags = {**new_post.flags, "publish_error": publish_err}
                automation.last_error = f"Publish failed: {publish_err}"
                print(f"❌ [IG_PUBLISH] Failed: {publish_err}")

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
        # Re-fetch automation inside the exception to ensure we can set last_error
        try:
            auto = db.query(TopicAutomation).get(automation_id)
            if auto:
                auto.last_error = str(e)
                db.commit()
        except:
            pass
        return None
    finally:
        lock.release()

def recover_stale_media(post: Post, db: Session) -> bool:
    """
    Just-in-time regeneration for quote cards lost to ephemeral storage wipes.
    Uses the 'Recovery Recipe' stored in source_metadata.
    """
    from app.config import settings
    from .image_renderer import render_quote_card, render_minimal_quote_card
    import os
    import time
    import requests

    # 1. Extract Recipe
    recipe = (post.source_metadata or {}).get("recovery_recipe")
    
    if not recipe:
        # Fallback to legacy fields for older posts
        if post.card_message:
            recipe = {
                "quote_text": post.card_message.get("headline", post.topic),
                "reference": post.card_message.get("supporting_text", post.source_reference),
                "visual_mode": "quote_card",
                "bg_url": None
            }
        else:
            missing_reason = "missing_recipe_in_metadata"
            if not post.card_message and not post.topic: missing_reason = "no_card_message_or_topic"
            
            print(f"❌ [MEDIA_RECOVERY_FAIL] Missing metadata for post_id={post.id}. Reason: {missing_reason}")
            log_event("media_recovery_fail", post_id=post.id, reason=missing_reason)
            return False

    print(f"🔄 [MEDIA_RECOVERY] stale image detected for post_id={post.id}")
    print(f"🔄 [MEDIA_RECOVERY] regenerating visual using recipe...")

    try:
        quote_text = recipe.get("quote_text") or "Divine Guidance"
        reference = recipe.get("reference") or ""
        bg_url = recipe.get("bg_url")
        
        tmp_bg_path = None
        if bg_url:
            try:
                bg_res = requests.get(bg_url, timeout=20)
                if bg_res.status_code == 200:
                    tmp_bg_path = os.path.join(settings.uploads_dir, f"tmp_bg_recov_{int(time.time())}.jpg")
                    with open(tmp_bg_path, "wb") as f:
                        f.write(bg_res.content)
            except Exception as bg_e:
                print(f"⚠️ [MEDIA_RECOVERY] Background download failed: {bg_e}")
                tmp_bg_path = None # render_quote_card will provide a procedural fallback

        # Re-render using Premium Pipeline (v9.0)
        card_segments = [
            {"text": reference.upper(), "size": 36},
            {"text": quote_text, "size": 72}
        ]
        
        # Zone 2: Arabic
        if recipe.get("visual_mode") == "quote_card" and post.source_metadata.get("arabic_text"):
             card_segments.append({"text": post.source_metadata["arabic_text"], "size": 38, "is_arabic": True})
        
        new_media_url = render_minimal_quote_card(
            segments=card_segments,
            output_dir=settings.uploads_dir,
            style=recipe.get("style", "quran"),
            visual_prompt=recipe.get("visual_prompt"),
            mode="custom" if recipe.get("visual_prompt") else "preset"
        )
        
        # Cleanup
        if tmp_bg_path and os.path.exists(tmp_bg_path):
            os.remove(tmp_bg_path)

        # Update Post
        post.media_url = new_media_url
        db.commit()
        db.refresh(post)
        
        log_event("media_recovery_success", post_id=post.id, new_url=new_media_url)
        print(f"✅ [MEDIA_RECOVERY] new media url: {new_media_url}")
        return True
        
    except Exception as e:
        print(f"❌ [MEDIA_RECOVERY_FAIL] regeneration failed: {e}")
        log_event("media_recovery_error", post_id=post.id, error=str(e))
        return False
