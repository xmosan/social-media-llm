# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import logging
from typing import Any
from datetime import datetime, timezone as dt_timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
from app.models import TopicAutomation, Post, IGAccount, ContentUsage, MediaAsset, ContentItem
from app.services.llm import generate_topic_caption, generate_caption_from_content_item, generate_ai_image, generate_topic_variations
from app.services.post_service import publish_post as publish_saved_post, prepare_scheduled_post
from app.security.ownership import require_account, require_media, validate_automation_links
from app.services.content_library import pick_content_item
from app.services.image_card import create_quote_card
from app.services.library_retrieval import retrieve_relevant_chunks
from app.services.prebuilt_loader import load_prebuilt_packs
from app.services.image_card import create_quote_card
from app.services.image_renderer import render_quote_card, render_minimal_quote_card

# Maps Style DNA family string → renderer style preset (shared with Studio/scheduled-post system)
FAMILY_TO_RENDER_STYLE: dict[str, str] = {
    "editorial": "editorial",
    "quiet_photography": "quiet_photography",
    "minimal_paper": "minimal_paper",
    "sacred_black":         "quran",
    "emerald_forest":       "fajr",
    "celestial_night":      "laylulqadr",
    "parchment_manuscript": "scholar",
    "luxury_marble":        "kaaba",
    "sacred_desert":        "madinah",
    # New extended families
    "royal_velvet":         "midnight",
    "midnight_ink":         "kaaba",
    "dawn_horizon":         "madinah",
    "obsidian_stone":       "quran",
    "ocean_depth":          "fajr",
    "warm_copper":          "desert",
}

# Maps Style DNA family → scene key in SCENE_PROMPT_TEMPLATES.
# Scene mode generates a unique AI background per post (DALL-E / Gemini),
# cycling through themed variations — identical to the Studio rendering pipeline.
FAMILY_TO_SCENE_KEY: dict[str, str] = {
    "editorial": "editorial",
    "quiet_photography": "quiet_photography",
    "minimal_paper": "minimal_paper",
    "sacred_black":         "sacred_black",
    "emerald_forest":       "emerald_forest",
    "celestial_night":      "celestial_night",
    "parchment_manuscript": "parchment_manuscript",
    "luxury_marble":        "luxury_marble",
    "sacred_desert":        "sacred_desert",
    # New extended families
    "royal_velvet":         "royal_velvet",
    "midnight_ink":         "midnight_ink",
    "dawn_horizon":         "dawn_horizon",
    "obsidian_stone":       "obsidian_stone",
    "ocean_depth":          "ocean_depth",
    "warm_copper":          "warm_copper",
}
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
    from app.services.automation_schedule import next_automation_time
    return next_automation_time(ig_account, automation)


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
            return require_media(db, org_id, automation.media_asset_id).url
            
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
                return require_media(db, org_id, asset.id).url
    return None

def clean_translation_for_card(text: str) -> str:
    """Preserve source wording, translator brackets, and numeric annotations."""
    return text or ""


def clean_hadith_for_card(text: str, max_chars: int = 350) -> str:
    """
    Safely excerpts a Hadith translation for use on a visual quote card.
    Excerpts at the last sentence boundary before max_chars.
    Does NOT alter meaning. Full text is preserved in post metadata/caption.
    Logs [HADITH_CARD] when excerpting occurs.
    """
    if not text: return ""
    cleaned = clean_translation_for_card(text)
    if len(cleaned) <= max_chars:
        return cleaned

    import re, logging
    logger = logging.getLogger(__name__)
    truncated = cleaned[:max_chars]
    # Find last sentence boundary
    for sentinel in [". ", "! ", "? "]:
        pos = truncated.rfind(sentinel)
        if pos > max_chars // 2:
            excerpt = truncated[:pos + 1].strip()
            logger.info(f"[HADITH_CARD] long hadith excerpted (original={len(cleaned)}, card={len(excerpt)})")
            return excerpt
    # Fallback: hard cut at word
    pos = truncated.rfind(" ")
    excerpt = (truncated[:pos] + "\u2026").strip() if pos > 0 else truncated
    logger.info(f"[HADITH_CARD] long hadith excerpted (original={len(cleaned)}, card={len(excerpt)})")
    return excerpt

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
    require_account(db, org_id, ig_account_id, active=True)
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
            return require_media(db, org_id, media_asset_id).url
            
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
                return require_media(db, org_id, asset.id).url
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
                    final_url = build_public_media_url(filename, local_path=file_path)
                    
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

def run_automation_once(db: Session, automation_id: int, force_publish: bool = False, scheduled_for: datetime | None = None) -> Post | None:
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
        # Keep selection, generation and saving in one transaction. PostgreSQL
        # releases this automation lock when that transaction commits/rolls back.
        # Independent plans must not lose their occurrence while another runs.
        if db.get_bind().dialect.name == "postgresql":
            locked_account_id = automation.ig_account_id
            acquired = db.execute(text("SELECT pg_try_advisory_xact_lock(:namespace, :automation)"),
                                  {"namespace": 731204, "automation": automation.id}).scalar()
            if not acquired:
                log_event("automation_run_busy", automation_id=automation_id)
                return None
            db.refresh(automation)
            if not automation.enabled or automation.ig_account_id != locked_account_id:
                return None
        elif os.getenv("SABEEL_ISOLATED_SECURITY_TESTS") != "1":
            raise RuntimeError("Automation coordination requires PostgreSQL")
        occurrence = scheduled_for.astimezone(dt_timezone.utc).isoformat() if scheduled_for else None
        if occurrence:
            prior = db.query(Post).filter(Post.automation_id == automation.id,
                                          Post.flags["scheduled_occurrence"].as_string() == occurrence).first()
            if prior is not None:
                return prior
        validate_automation_links(db, automation.org_id, {
            field: getattr(automation, field) for field in (
                "ig_account_id", "media_asset_id", "content_profile_id", "style_dna_id", "style_dna_pool"
            )
        })
        
        # 1. Intelligent Topic Pool Rotation (rotation_engine)
        from app.services.rotation_engine import pick_topic, record_topic_used, latest_rotation
        
        pool = automation.topic_pool or []
        avoid_days = getattr(automation, "avoid_repeat_days", 30) or 30

        if pool:
            topic_base = pick_topic(
                topic_pool=pool,
                automation_id=automation.id,
                db=db,
                avoid_days=avoid_days,
            )
        else:
            topic_base = automation.topic_prompt

        log_event("automation_topic_selected", automation_id=automation.id, topic=topic_base,
                  pool_size=len(pool), avoid_days=avoid_days)
        print(f"[ROTATION] Selected topic: '{topic_base}' (pool size={len(pool)}, avoid_days={avoid_days})")

        rotation_topic = topic_base
        selected_pillar = None
        # 2. Pillar Rotation Logic (kept for backwards compat)
        pillars = automation.pillars or []
        if pillars:
            import random as _rnd
            # Exclude most recently used pillar if multiple exist
            last_pillar = latest_rotation(automation.id, db).get("rotation_pillar")
            pillar_candidates = [p for p in pillars if p != last_pillar] or pillars
            selected_pillar = _rnd.choice(pillar_candidates)
            topic_base = f"{selected_pillar}: {topic_base}" if topic_base else selected_pillar
            log_event("automation_pillar_selected", automation_id=automation.id, pillar=selected_pillar)

        # 3. Load Style DNA with intelligent back-to-back prevention
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
        
        # The selected plan topic defines the source pool. AI variations and
        # pillar labels are framing instructions, not source search terms:
        # their common words can otherwise match thousands of unrelated verses.
        attempts = [rotation_topic]
        
        for search_query in attempts:
            for provider in active_providers:
                try:
                    # Rank all matches across both selected libraries.
                    items = provider.get_content(db, automation.org_id, search_query, limit=None, automation_id=automation.id)
                    pooled_items.extend(items)
                    if items:
                        log_event("provider_content_sourced", 
                                  automation_id=automation.id, 
                                  provider=provider.provider_name, 
                                  count=len(items),
                                  query=search_query)
                except Exception as e:
                    print(f"[PROVIDER] Error in {provider.provider_name}: {e}")

        # Respect the configured Hadith feature gate
        if not getattr(settings, "hadith_in_automations_enabled", False):
            before_count = len(pooled_items)
            pooled_items = [i for i in pooled_items if getattr(i, "type", "") != "hadith"]
            if len(pooled_items) < before_count:
                print(f"[HADITH] Feature gate: filtered {before_count - len(pooled_items)} Hadith items from automation pool")

        from app.services.rotation_engine import rank_provider_items
        pooled_items = rank_provider_items(pooled_items, db, automation.id, avoid_days)
                
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
                is_quran = candidate.type == "quran"
                if is_quran and not candidate.arabic_text:
                    # Never borrow Arabic from a different translation/source record.
                    continue

                candidate_payload = {
                    **(candidate.meta or {}), "reference": candidate.reference,
                    "translation_text": candidate.text, "text": candidate.text,
                    "arabic_text": candidate.arabic_text,
                }
                if candidate.type in {"quran", "hadith"}:
                    from app.services.source_grounding import resolve_selected_source
                    if candidate.type == "quran":
                        candidate_payload["id"] = candidate.original_id
                    try:
                        candidate_payload = resolve_selected_source(db, automation.org_id, candidate.type, candidate_payload)
                    except (ValueError, HTTPException):
                        log_event("automation_source_verification_failed", automation_id=automation.id,
                                  content_item_id=candidate.original_id)
                        continue
                    candidate.reference = candidate_payload["reference"]
                    candidate.text = candidate_payload["translation_text"]
                    candidate.arabic_text = candidate_payload.get("arabic_text")
                primary_item = candidate
                source_payload = candidate_payload
                log_event("source_relevance_passed", automation_id=automation.id, reference=candidate.reference, reason=audit["reason"])
                break
            else:
                log_event("source_relevance_rejected", automation_id=automation.id, reference=candidate.reference, reason=audit["reason"])

        if not primary_item:
            automation.last_error = "No relevant, complete source passed validation."
            db.commit()
            return None

        # Only the selected source may feed generation and usage history.
        pooled_items = [primary_item]

        # [SAFETY] Guardrail: Abort if exactly 0 items found
        if not primary_item:
            log_event("automation_no_content_found", automation_id=automation.id, topic=topic, scope=provider_scope)
            automation.last_error = "No verified content found across chosen providers."
            db.commit()
            return None

        # QUALITY GATE FIX: Re-check Arabic for Quran posts again to be absolutely sure
        if not fallback_mode and primary_item.type == "quran":
            if not primary_item.arabic_text:
                print(f"❌ [QUALITY_GATE] BLOCKING: Arabic missing for confirmed Quran post {primary_item.reference}.")
                automation.last_error = f"Arabic source missing for {primary_item.reference}. Re-run needed."
                db.commit()
                return None

        # ── Hadith Automation Safety Pass (Validation Gate) ─────────────────────────
        if not fallback_mode and primary_item and primary_item.type == "hadith":
            has_reference = bool(primary_item.reference and primary_item.reference.strip())
            has_text = bool(primary_item.arabic_text or primary_item.text)
            
            if not has_reference or not has_text:
                print(f"❌ [HADITH_AUTOMATION][BLOCKED] reason=missing_critical_metadata ref={primary_item.reference}")
                log_event("hadith_automation_blocked", automation_id=automation.id, reason="missing_critical_metadata", reference=primary_item.reference)
                automation.last_error = "Hadith source integrity failed: missing reference or text."
                db.commit()
                return None
            else:
                print(f"✅ [HADITH_AUTOMATION] source validated ref={primary_item.reference}")
                log_event("hadith_automation_validated", automation_id=automation.id, reference=primary_item.reference)

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
                "item_type": "quran" if (primary_item is not None and primary_item.type == "quran") else "reference",
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
            if primary_item and primary_item.type == "hadith" and not fallback_mode:
                # Bypass generic LLM for Hadith to ensure STRICT GROUNDING
                from app.services.hadith_caption_service import generate_hadith_caption
                
                # Support extracting narrator from meta if available in UnifiedContent or elsewhere
                narrator_val = ""
                if hasattr(primary_item, "meta") and isinstance(primary_item.meta, dict):
                    narrator_val = primary_item.meta.get("narrator", "")

                payload = {
                    "reference": final_reference,
                    "translation_text": primary_item.text,
                    "narrator": narrator_val,
                    "arabic_text": primary_item.arabic_text,
                }
                caption = generate_hadith_caption(source_payload, tone=automation.tone or "calm")
                hashtags = automation.hashtag_set or ["#Hadith", "#PropheticWisdom", "#IslamicReminder"]
                alt_text = f"Hadith quote: {quote_text_cleaned}"
                
                result = {"caption": caption, "hashtags": hashtags, "alt_text": alt_text}
                print(f"✅ [HADITH_AUTOMATION] routed to strict generate_hadith_caption service")
            elif primary_item and primary_item.type == "quran" and not fallback_mode:
                # ── QURAN: use the SAME caption service as Studio/scheduled posts ──────────
                # This ensures Arabic + English appear in the post text, matching scheduled post behavior.
                from app.services.quran_caption_service import generate_ai_caption_from_quran
                tone_style = automation.tone or "reflective"
                quran_payload = {
                    "reference": final_reference,
                    "arabic_text": primary_item.arabic_text or "",
                    "translation_text": primary_item.text or uncleaned_text,
                }
                caption = generate_ai_caption_from_quran(quran_payload, style=tone_style)
                hashtags = automation.hashtag_set or ["#Quran", "#IslamicReminder", "#DailyReminder"]
                alt_text = f"Quranic verse: {quote_text_cleaned}"
                result = {"caption": caption, "hashtags": hashtags, "alt_text": alt_text}
                print(f"✅ [QURAN_AUTOMATION] routed to generate_ai_caption_from_quran (bilingual: arabic+english)")
            else:
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
            caption = result.get("caption", "").strip() if isinstance(result, dict) else (result or "").strip()
            hashtags = result.get("hashtags", []) if isinstance(result, dict) else []
            alt_text = result.get("alt_text", "") if isinstance(result, dict) else ""
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
        from app.services.rotation_engine import visual_history
        generation_metadata = {}
        prior_visuals = visual_history(db, automation.id)
        card_message = None
        quote_text = quote_text_cleaned
        reference = final_reference
        
        media_url = None
        
        # SPECIAL: Quote Card Mode (v9.0 Premium Upgrade)
        if automation.image_mode == "quote_card":
            
            bg_url = None
            # 2. Build structured card_message — IDENTICAL structure to Studio/image_card.py
            try:
                from app.services.image_card import generate_quote_card

                from app.services.quote_message_service import build_quote_card_message
                card_message = build_quote_card_message(
                    primary_item.type, source_payload,
                    automation.tone or "calm", getattr(automation, "intent_type", None) or "wisdom",
                )

                # Resolve scene key from Style DNA family
                _family     = style_dna_spec.family if style_dna_spec.family else "sacred_black"
                _scene_key  = FAMILY_TO_SCENE_KEY.get(_family, "sacred_black")
                _has_prompt = bool(style_dna_spec.visual_prompt and style_dna_spec.visual_prompt.strip())
                _render_mode = "custom" if _has_prompt else "scene"

                print(f"📡 [v9.0] Routing via generate_quote_card — family={_family}, scene={_scene_key}, mode={_render_mode}, arabic={bool(card_message.get('arabic_text'))}")

                def retain_automation_photo(image):
                    from app.services.visual_service import store_background
                    generation_metadata["background_token"] = store_background(
                        image, automation.org_id, style_dna_spec.visual_prompt if _has_prompt else "")

                # CALL generate_quote_card — same function Studio/scheduled posts use.
                # This ensures: Arabic reshaping, ZONE_SIZES, is_arabic flags, scene variation all match.
                media_url = generate_quote_card(
                    style=_scene_key,
                    visual_prompt=style_dna_spec.visual_prompt if _has_prompt else None,
                    mode=_render_mode,
                    text_style_prompt=style_dna_spec.glow_aura or "",
                    readability_priority=True,
                    experimental_mode=False,
                    engine="dalle",
                    glossy=False,
                    card_message=card_message,
                    visual_history=prior_visuals,
                    render_metadata=generation_metadata,
                    allow_sequence=True,
                    background_sink=retain_automation_photo if _scene_key == "quiet_photography" else None,
                )

                # Source mismatch guardrail
                reference_clean = reference.replace("Qur'an", "").replace("Quran", "").strip()
                if reference_clean.lower() not in caption.lower() and ":" in reference:
                    print(f"❌ [POST_SOURCE_MISMATCH] reference {reference} not in caption")
                    automation.last_error = f"Source mismatch: Card={reference}, Caption source missing."
                    db.commit()
                    return None

            except Exception as e:
                print(f"[AUTO] Premium Quote card rendering failed: {e}")
                import traceback; traceback.print_exc()
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

        from app.services.media_sequence import seal_manifest, validate_manifest
        manifest = generation_metadata.get("media_manifest")
        if manifest:
            manifest = seal_manifest(manifest, automation.org_id)
            validate_manifest(manifest, card_message, automation.org_id)

        # 4. Create Post
        # Unknown legacy policy values must never grant automatic approval.
        visual_review_required = bool(generation_metadata.get("quality", {}).get("review_required"))
        status = "scheduled" if automation.approval_mode == "auto_approve" and not visual_review_required else "drafted"
            
        source_text = primary_item.text

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
            visual_mode=automation.image_mode,
            source_foundation=primary_item.type if primary_item.type in {"quran", "hadith"} else None,
            source_reference=final_reference,
            source_text=source_text,
            card_message=card_message,
            caption_message={"caption": caption},
            media_url=media_url,
            post_format=manifest["format"] if manifest else None,
            caption=caption,
            hashtags=hashtags,
            alt_text=alt_text,
            scheduled_time=(scheduled_for or compute_next_run_time(db.get(IGAccount, automation.ig_account_id), automation)) if status == "scheduled" else None,
            # RECOVERY RECIPE: Store ingredients for just-in-time regeneration
            source_metadata={
                **source_payload,
                "visual_generation": generation_metadata,
                "reference": final_reference,
                "translation_text": primary_item.text,
                "arabic_text": primary_item.arabic_text,
                "provider": primary_item.provider,
                "source_type": primary_item.type,
                "original_id": primary_item.original_id,
                "metadata": dict(primary_item.meta or {}),
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
            flags={"relevance_check": "fallback" if fallback_mode else "passed", "scheduled_occurrence": occurrence,
                   "visual_review_required": visual_review_required,
                   **({"media_manifest": manifest, "visual_design": {"family": _scene_key,
                       "layout": "english_first", "direction": style_dna_spec.visual_prompt if _has_prompt else "",
                       "background_token": generation_metadata.get("background_token"), "media_manifest": manifest}}
                       if manifest else {})}
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
            new_post.flags = {**(new_post.flags or {}), "automation_error": f"LLM returned invalid/filler caption: {caption}", "reason": reason, "detail_reason": detail_reason}
            automation.last_error = f"Guardrail check failed: {detail_reason}"
            db.add(new_post)
            db.commit()
            return new_post

        if not media_url:
            new_post.status = "failed"
            new_post.flags = {**(new_post.flags or {}), "automation_error": "media_url is missing/generation failed"}
            automation.last_error = "Media generation failed or asset missing"
            db.add(new_post)
            db.commit()
            return new_post

        db.add(new_post)
        db.flush() 
        
        record_topic_used(new_post, rotation_topic, style_dna_spec.style_id, selected_pillar)

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

        from app.services.rotation_engine import repetition_issues
        repeats = repetition_issues(db, new_post)
        if repeats:
            new_post.status = "needs_review"
            new_post.flags = {**new_post.flags, "repetition_issues": repeats}
            automation.last_error = "Repeated content requires review: " + ", ".join(repeats)

        # 7. Immediate Publishing if configured OR forced
        should_publish = (not repeats and not visual_review_required and automation.approval_mode == "auto_approve"
                          and (force_publish or automation.posting_mode == "publish_now"))
        schedule_error = None
        if new_post.status == "scheduled" and not should_publish:
            try:
                prepare_scheduled_post(db, new_post)
            except HTTPException as error:
                schedule_error = error.detail
                new_post.status = "needs_review"
                new_post.last_error = str(error.detail)
                automation.last_error = str(error.detail)
        
        if should_publish:
            log_event("automation_publish_attempt", automation_id=automation.id, post_id=new_post.id, forced=force_publish)
            db.commit()  # The shared publisher operates on a saved post identity.
            outcome = publish_saved_post(db, new_post.id, automation.org_id)
            if not outcome.ok:
                automation.last_error = outcome.error
                if outcome.status_code in {403, 422}:
                    new_post.status = "failed"
                    new_post.flags = {**(new_post.flags or {}), "publish_error": outcome.error}

        automation.last_run_at = datetime.now(dt_timezone.utc)
        automation.last_post_id = new_post.id
        if not repeats and not schedule_error and (not should_publish or outcome.ok):
            automation.last_error = None

        db.commit()
        db.refresh(new_post)
        return new_post

    except Exception as e:
        import traceback
        log_event("automation_run_exception", automation_id=automation_id, error=str(e), traceback=traceback.format_exc(limit=3))
        print(f"[AUTO] ERROR in runner for automation_id={automation_id}: {repr(e)}")
        logger.error(f"Automation {automation_id} failed: {e}")
        db.rollback()
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
        db.rollback()  # Release an uncommitted selection lock on early exits.
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
