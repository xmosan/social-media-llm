# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

"""
automation_service.py — Phase 1 Service Wrapper

High-level orchestration interface for the Automation system.
This is a FACADE over the existing, working implementation in:
  - services/automation_runner.py   (core generation engine)
  - services/scheduler.py           (job scheduling)

IMPORTANT: This file does NOT change automation_runner.py.
All existing /automations routes continue to call automation_runner directly.
This wrapper enables:
  - Phase 2: Style DNA injection into automation runs
  - Future: cleaner async execution, webhook callbacks, run history
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Post, TopicAutomation, IGAccount
from app.logging_setup import log_event

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# INPUT / OUTPUT MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AutomationRunResult:
    """Result of a single automation execution cycle."""
    post: Optional[Post] = None
    automation_id: Optional[int] = None
    status: str = "unknown"     # success | failed | skipped | no_content
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.post is not None and self.status == "success"


@dataclass
class StyleDNASpec:
    """
    Resolved Style DNA for use in visual generation within an automation run.
    Phase 1: This spec is built from the legacy `style_preset` string.
    Phase 2: This will be loaded from the `style_dna` table.
    """
    family: str = "sacred_black"
    atmosphere: str = "contemplative"
    ornament_level: str = "corner"
    tone_style: str = "deep"
    variation_pool: list = field(default_factory=lambda: ["lighting", "texture"])
    locked_traits: dict = field(default_factory=dict)
    visual_prompt: Optional[str] = None
    glow_aura: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM STYLE DNA PRESETS
# These map automation style_preset strings → structured StyleDNASpec.
# Phase 2 will replace this with a database lookup.
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_STYLE_DNA_PRESETS: dict[str, StyleDNASpec] = {
    "islamic_reminder": StyleDNASpec(
        family="sacred_black",
        atmosphere="sacred",
        ornament_level="minimal",
        tone_style="deep",
        variation_pool=["lighting", "texture", "glow"],
        locked_traits={"mood": "sacred"},
    ),
    "nature_reflection": StyleDNASpec(
        family="emerald_forest",
        atmosphere="peaceful",
        ornament_level="minimal",
        tone_style="soft",
        variation_pool=["fog_density", "foliage", "lighting"],
        locked_traits={"atmosphere": "peaceful"},
    ),
    "celestial": StyleDNASpec(
        family="celestial_night",
        atmosphere="celestial",
        ornament_level="none",
        tone_style="deep",
        variation_pool=["nebula", "stars", "lighting"],
        locked_traits={},
    ),
    "parchment_hadith": StyleDNASpec(
        family="parchment_manuscript",
        atmosphere="contemplative",
        ornament_level="moderate",
        tone_style="scholarly",
        variation_pool=["lighting", "texture", "ornament"],
        locked_traits={"material": "parchment"},
    ),
    "luxury_quote": StyleDNASpec(
        family="luxury_marble",
        atmosphere="majestic",
        ornament_level="corner",
        tone_style="direct",
        variation_pool=["vein_direction", "reflection", "illumination"],
        locked_traits={},
    ),
    "desert_hikma": StyleDNASpec(
        family="sacred_desert",
        atmosphere="contemplative",
        ornament_level="corner",
        tone_style="direct",
        variation_pool=["scene_type", "detail", "lighting"],
        locked_traits={},
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# CORE SERVICE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def run_automation(db: Session, automation_id: int, force_publish: bool = False) -> AutomationRunResult:
    """
    Execute one cycle of an automation.

    Phase 1: Delegates directly to automation_runner.run_automation_once().
    Phase 2: Will inject Style DNA before calling the runner.

    Returns an AutomationRunResult.
    """
    automation = db.query(TopicAutomation).filter(
        TopicAutomation.id == automation_id
    ).first()

    if not automation:
        return AutomationRunResult(
            automation_id=automation_id,
            status="skipped",
            error="Automation not found",
        )

    if not automation.enabled and not force_publish:
        return AutomationRunResult(
            automation_id=automation_id,
            status="skipped",
            error="Automation is disabled",
        )

    log_event("automation_service_run_start", automation_id=automation_id, forced=force_publish)

    try:
        from app.services.automation_runner import run_automation_once

        # Phase 2 hook: Style DNA injection will go here
        # style_dna = resolve_style_dna(db, automation)
        # inject_style_dna_into_runner(automation, style_dna)

        post = run_automation_once(db, automation_id, force_publish=force_publish)

        if not post:
            return AutomationRunResult(
                automation_id=automation_id,
                status="failed",
                error="Automation runner returned no post",
            )

        status = "success" if post.status not in ("failed",) else "failed"
        log_event("automation_service_run_complete",
                  automation_id=automation_id, post_id=post.id, status=status)

        return AutomationRunResult(
            post=post,
            automation_id=automation_id,
            status=status,
        )

    except Exception as e:
        logger.error(f"[AutomationService] run_automation({automation_id}) failed: {e}",
                     exc_info=True)
        log_event("automation_service_run_error", automation_id=automation_id, error=str(e))
        return AutomationRunResult(
            automation_id=automation_id,
            status="failed",
            error=str(e),
        )


def get_automation_style_dna(db: Session, automation: TopicAutomation) -> StyleDNASpec:
    """
    Resolves the StyleDNA for a given automation.

    Phase 1: Maps the legacy `style_preset` string to a system preset.
    Phase 2: Loads from the `style_dna` table using `automation.style_dna_pool`
             with intelligent back-to-back prevention via rotation_engine.pick_style().

    Returns a StyleDNASpec (always — uses 'islamic_reminder' as fallback).
    """
    from app.models import StyleDNA, Post
    from app.services.rotation_engine import pick_style

    pool = getattr(automation, "style_dna_pool", []) or []
    last_style_id = (getattr(automation, "flags", {}) or {}).get("last_style_id")

    # Intelligent pick: avoid back-to-back same style
    selected_dna_id = pick_style(pool, last_style_id=last_style_id)

    if not selected_dna_id:
        # No pool — fall back to single style_dna_id if set
        selected_dna_id = getattr(automation, "style_dna_id", None)

    if getattr(automation, "automation_version", 1) >= 2 and selected_dna_id:
        db_obj = db.get(StyleDNA, selected_dna_id)
        if db_obj:
            logger.info(f"[STYLE_DNA] Selected: '{db_obj.name}' (id={selected_dna_id}, "
                        f"last={last_style_id}, pool={pool})")
            return StyleDNASpec(
                family=db_obj.family,
                atmosphere=db_obj.atmosphere,
                ornament_level=db_obj.ornament_level,
                tone_style=db_obj.tone_style,
                variation_pool=db_obj.variation_pool or [],
                locked_traits=db_obj.locked_traits or {}
            )

    preset_key = getattr(automation, "style_preset", "islamic_reminder") or "islamic_reminder"
    return SYSTEM_STYLE_DNA_PRESETS.get(
        preset_key,
        SYSTEM_STYLE_DNA_PRESETS["islamic_reminder"]
    )


def list_system_presets(db: Session = None) -> list[dict]:
    """
    Returns all system Style DNA presets.
    Phase 2: Reads from DB.
    """
    if db:
        from app.models import StyleDNA
        presets = db.query(StyleDNA).filter(StyleDNA.is_system_preset == True).all()
        if presets:
            return [
                {
                    "id": p.id,
                    "key": p.name.lower().replace(" ", "_"),
                    "label": p.name,
                    "family": p.family,
                    "atmosphere": p.atmosphere,
                    "ornament_level": p.ornament_level,
                    "tone_style": p.tone_style,
                } for p in presets
            ]

    # Fallback to in-memory if DB not supplied/seeded
    return [
        {
            "id": None,
            "key": key,
            "label": key.replace("_", " ").title(),
            "family": spec.family,
            "atmosphere": spec.atmosphere,
            "ornament_level": spec.ornament_level,
            "tone_style": spec.tone_style,
        }
        for key, spec in SYSTEM_STYLE_DNA_PRESETS.items()
    ]


def seed_style_dna(db: Session) -> None:
    """
    Phase 2: Safely seed the 6 core system presets into the DB.
    """
    from app.models import StyleDNA
    
    # Pre-defined mapping of key -> name since the dict keys are technically identifiers
    preset_names = {
        "islamic_reminder": "Dark Sacred",
        "parchment_hadith": "Warm Parchment",
        "nature_reflection": "Emerald Calm",
        "celestial": "Celestial Night",
        "luxury_quote": "Luxury Marble",
        "desert_hikma": "Sacred Desert"
    }
    
    for key, spec in SYSTEM_STYLE_DNA_PRESETS.items():
        name = preset_names.get(key, key)
        # Check if exists
        exists = db.query(StyleDNA).filter(StyleDNA.name == name, StyleDNA.is_system_preset == True).first()
        if not exists:
            new_dna = StyleDNA(
                org_id=None,
                name=name,
                family=spec.family,
                atmosphere=spec.atmosphere,
                palette_key=None,
                ornament_level=spec.ornament_level,
                tone_style=spec.tone_style,
                variation_pool=spec.variation_pool,
                locked_traits=spec.locked_traits,
                is_system_preset=True
            )
            db.add(new_dna)
    db.commit()


def get_automation_history(db: Session, automation_id: int,
                           org_id: int, limit: int = 20) -> list[Post]:
    """
    Returns the most recent posts generated by a given automation.
    """
    from sqlalchemy import select
    stmt = (
        select(Post)
        .where(Post.automation_id == automation_id, Post.org_id == org_id)
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def enable_automation(db: Session, automation_id: int, org_id: int) -> bool:
    """Enable an automation and reload scheduler jobs."""
    automation = db.query(TopicAutomation).filter(
        TopicAutomation.id == automation_id,
        TopicAutomation.org_id == org_id,
    ).first()
    if not automation:
        return False
    automation.enabled = True
    db.commit()
    _reload_scheduler(db)
    log_event("automation_service_enabled", automation_id=automation_id)
    return True


def disable_automation(db: Session, automation_id: int, org_id: int) -> bool:
    """Disable an automation and reload scheduler jobs."""
    automation = db.query(TopicAutomation).filter(
        TopicAutomation.id == automation_id,
        TopicAutomation.org_id == org_id,
    ).first()
    if not automation:
        return False
    automation.enabled = False
    db.commit()
    _reload_scheduler(db)
    log_event("automation_service_disabled", automation_id=automation_id)
    return True


def simulate_growth_plan(
    db: Session, 
    org_id: int, 
    topic_pool: list[str], 
    style_dna_ids: list[int], 
    language: str = "english",
    count: int = 2
) -> list[dict]:
    """
    Simulation Engine for Growth Plan V2.
    Generates realistic post previews including grounded sources, captions, and real visuals.
    """
    import random
    from app.services.library_retrieval import retrieve_relevant_chunks
    from app.services.quran_service import search_quran, normalize_quran_verse
    from app.services.relevance_engine import validate_source_relevance
    from app.services.llm import generate_topic_caption
    from app.services.image_renderer import render_minimal_quote_card
    from app.config import settings
    import os

    results = []
    
    # 1. Resolve Style DNA objects
    from app.models import StyleDNA
    styles = []
    for sid in style_dna_ids:
        s = db.get(StyleDNA, sid)
        if s: styles.append(s)
    
    # Fallback to defaults if no styles found
    if not styles:
        default_dna = get_automation_style_dna(db, TopicAutomation(style_preset="islamic_reminder"))
        styles = [default_dna]

    for i in range(min(count, 5)): # Limit to 5 samples
        topic = topic_pool[i % len(topic_pool)] if topic_pool else "Daily Reminder"
        style = styles[i % len(styles)]
        
        # 2. Content Discovery (Favor Quran for Simulation variety)
        # Try Quran search first
        pooled_items = search_quran(db, topic, limit=3)
        
        primary_item = None
        fallback_mode = False
        relevance_audit = None
        
        if pooled_items:
            for cand in pooled_items:
                # Audit - Use cand.title as ContentItem doesn't have .reference
                cand_ref = getattr(cand, "reference", getattr(cand, "title", "Quran"))
                audit = validate_source_relevance(topic, cand.text, cand_ref)
                if audit["accepted"]:
                    # Ensure Arabic text exists - Fetch if missing
                    if not cand.arabic_text:
                        print(f"📡 [QURAN_ARABIC] fetching Arabic for {cand_ref}")
                        try:
                            from app.services.quran_service import get_verse_by_reference
                            item = get_verse_by_reference(db, cand_ref)
                            if item and item.arabic_text:
                                cand.arabic_text = item.arabic_text
                                print(f"📡 [QURAN_ARABIC] loaded")
                            else:
                                print(f"📡 [QURAN_ARABIC][FAIL] missing Arabic for {cand_ref}")
                        except Exception as e:
                            print(f"⚠️ [QURAN_ARABIC] fetch error: {e}")

                    if cand.arabic_text:
                        primary_item = cand
                        relevance_audit = audit
                        break
        
        if not primary_item:
            # Try general library logic if Quran check was too strict or failed
            chunks = retrieve_relevant_chunks(db, org_id, query=topic, k=3)
            if chunks:
                for c in chunks:
                    audit = validate_source_relevance(topic, c.get("text", ""), c.get("source", ""))
                    if audit["accepted"]:
                        # Convert chunk to pseudo-item
                        from types import SimpleNamespace
                        primary_item = SimpleNamespace(
                            text=c.get("text"),
                            arabic_text=c.get("arabic_text"),
                            reference=c.get("source"),
                            provider=c.get("item_type", "library")
                        )
                        relevance_audit = audit
                        break

        if not primary_item:
            # Try parsing topic for exact Quran reference (e.g. "Surah 70, Verse 5")
            import re
            q_match = re.search(r"Surah\s+(\d+),?\s+Verse\s+(\d+)", topic, re.I)
            if not q_match:
                q_match = re.search(r"Qur'?an\s+(\d+):(\d+)", topic, re.I)
            
            if q_match:
                s_num, a_num = q_match.groups()
                print(f"📡 [QURAN_ARABIC] Direct topic match: {s_num}:{a_num}")
                from app.services.quran_service import get_quran_ayah
                exact_item = get_quran_ayah(db, int(s_num), int(a_num))
                if exact_item:
                    primary_item = exact_item
                    relevance_audit = {"accepted": True, "reason": "Direct reference match"}

        if not primary_item:
            fallback_mode = True
            primary_item = SimpleNamespace(
                text=topic,
                arabic_text=None,
                reference="Reflection Preview",
                provider="reflection"
            )

        # 3. Generate Caption
        item_ref = getattr(primary_item, "reference", getattr(primary_item, "title", "Quran"))
        is_verified_quran = "quran" in (getattr(primary_item, "provider", "") or "").lower() and not fallback_mode
        
        context_payload = {
            "mode": "grounded_library",
            "snippet": {
                "text": primary_item.text,
                "reference": item_ref,
                "item_type": "quran" if is_verified_quran else getattr(primary_item, "provider", "reflection")
            }
        }
        
        llm_res = generate_topic_caption(
            topic=topic,
            style=style.family if hasattr(style, "family") else "sacred_black",
            tone="medium",
            language=language,
            extra_context=context_payload
        )

        # 4. Generate Visual (Only for Sample 1 to stay fast)
        visual_url = None
        if i == 0:
            try:
                from app.services.automation_runner import clean_translation_for_card
                quote_text = clean_translation_for_card(primary_item.text)
                reference = (item_ref or "Sacred Guidance").upper()
                
                segments = [{"text": reference, "size": 36}]
                # Dual language for Quran
                is_quran = "quran" in (getattr(primary_item, "provider", "") or "").lower() and not fallback_mode
                if is_quran and primary_item.arabic_text:
                    segments.append({"text": primary_item.arabic_text, "size": 60, "is_arabic": True})
                    segments.append({"text": quote_text, "size": 52})
                else:
                    segments.append({"text": quote_text, "size": 72})
                
                # Map Family to Renderer Preset
                family = style.family if hasattr(style, "family") else "sacred_black"
                family_map = {
                    "sacred_black": "quran",
                    "emerald_forest": "fajr",
                    "celestial_night": "laylulqadr",
                    "parchment_manuscript": "scholar",
                    "luxury_marble": "kaaba",
                    "sacred_desert": "madinah"
                }
                render_style = family_map.get(family, "quran")
                
                visual_url = render_minimal_quote_card(
                    segments=segments,
                    output_dir=settings.uploads_dir,
                    style=render_style,
                    visual_prompt=style.visual_prompt if hasattr(style, "visual_prompt") else None,
                    mode="custom" if hasattr(style, "visual_prompt") and style.visual_prompt else "preset"
                )
                # Mark as preview
                if visual_url and "/uploads/" in visual_url:
                    basename = visual_url.split("/")[-1]
                    new_name = f"preview_{basename}"
                    os.rename(os.path.join(settings.uploads_dir, basename), os.path.join(settings.uploads_dir, new_name))
                    from app.config import build_public_media_url
                    visual_url = build_public_media_url(new_name)
                    
            except Exception as ve:
                logger.error(f"Visual preview generation failed: {ve}")

        results.append({
            "sample_index": i + 1,
            "topic": topic,
            "style_name": style.name if hasattr(style, "name") else "Dark Sacred",
            "source_type": "quran" if is_verified_quran else getattr(primary_item, "provider", "reflection"),
            "source_label": "Qur'an Preview" if is_verified_quran else "Reflection Preview",
            "source_reference": item_ref,
            "grounding_text": primary_item.text,
            "arabic_text": primary_item.arabic_text,
            "caption": llm_res.get("caption"),
            "hashtags": llm_res.get("hashtags", []),
            "visual_url": visual_url,
            "fallback_mode": fallback_mode,
            "relevance_reason": relevance_audit.get("reason") if relevance_audit else "Manual Reflection"
        })

    return results

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _reload_scheduler(db: Session) -> None:
    """Reload APScheduler jobs after automation changes."""
    try:
        from app.services.scheduler import reload_automation_jobs
        reload_automation_jobs(lambda: db)
    except Exception as e:
        logger.warning(f"[AutomationService] Scheduler reload failed (non-fatal): {e}")
