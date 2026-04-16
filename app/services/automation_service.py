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

def run_automation(db: Session, automation_id: int) -> AutomationRunResult:
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

    if not automation.enabled:
        return AutomationRunResult(
            automation_id=automation_id,
            status="skipped",
            error="Automation is disabled",
        )

    log_event("automation_service_run_start", automation_id=automation_id)

    try:
        from app.services.automation_runner import run_automation_once

        # Phase 2 hook: Style DNA injection will go here
        # style_dna = resolve_style_dna(db, automation)
        # inject_style_dna_into_runner(automation, style_dna)

        post = run_automation_once(db, automation_id)

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


def get_automation_style_dna(automation: TopicAutomation) -> StyleDNASpec:
    """
    Resolves the StyleDNA for a given automation.

    Phase 1: Maps the legacy `style_preset` string to a system preset.
    Phase 2: Will load from the `style_dna` table using `automation.style_dna_id`.

    Returns a StyleDNASpec (always — uses 'islamic_reminder' as fallback).
    """
    # Phase 2 hook:
    # if hasattr(automation, 'style_dna_id') and automation.style_dna_id:
    #     return _load_style_dna_from_db(db, automation.style_dna_id)

    preset_key = getattr(automation, "style_preset", "islamic_reminder") or "islamic_reminder"
    return SYSTEM_STYLE_DNA_PRESETS.get(
        preset_key,
        SYSTEM_STYLE_DNA_PRESETS["islamic_reminder"]
    )


def list_system_presets() -> list[dict]:
    """
    Returns all system Style DNA presets.
    Used by the Automations UI to populate the style picker.
    """
    return [
        {
            "key": key,
            "label": key.replace("_", " ").title(),
            "family": spec.family,
            "atmosphere": spec.atmosphere,
            "ornament_level": spec.ornament_level,
            "tone_style": spec.tone_style,
        }
        for key, spec in SYSTEM_STYLE_DNA_PRESETS.items()
    ]


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
