def run_automation_once(db: Session, automation_id: int) -> Post | None:
    """
    Core engine to run one automation cycle using the decoupled Content Provider architecture.
    """
    automation = db.query(TopicAutomation).filter(TopicAutomation.id == automation_id).first()
    if not automation or not automation.enabled:
        return None
    
    try:
        topic_base = automation.topic_prompt
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
            "instructions": [
                "Do NOT output the topic label literally.",
                "Do NOT output 'AUTO: <name>' literally as the caption.",
                "You MUST build the post primarily around the structured `source_items` provided below.",
                "DO NOT hallucinate or generate quotes/hadith/verses that are not explicitly provided in the `source_items`.",
                "Always cite the exact reference provided."
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
