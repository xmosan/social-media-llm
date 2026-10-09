"""Atomic PostgreSQL launch budgets shared by every app replica and worker.

Reserve BEFORE dispatch, commit independently from the post transaction. Failed
or uncertain provider attempts still count. A fallback is a separate attempt.
No refunds/retries, no in-memory bypass, no superadmin exemption. These are call
budgets (with bounded inputs/outputs), not a provider currency/billing ledger.
"""
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import hmac
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.config import settings
from app.security.usage_context import current_scope

logger = logging.getLogger(__name__)


class UsageLimitError(HTTPException):
    def __init__(self, message, status=429, retry_after=60):
        super().__init__(status, message, headers={"Retry-After": str(max(1, int(retry_after)))})


def _session():
    from app.db import SessionLocal
    return SessionLocal()


def _now(db):
    if db.get_bind().dialect.name != "postgresql":
        raise UsageLimitError("Generation controls are unavailable. Your work is kept; try again shortly.", 503)
    db.execute(text("SET LOCAL statement_timeout = '5s'"))
    db.execute(text("SET LOCAL lock_timeout = '3s'"))
    return db.execute(text("SELECT clock_timestamp()" )).scalar_one()


def _increment(db, key, start, maximum, message, retry_after):
    result = db.execute(text("""INSERT INTO usage_buckets (key, window_start, attempts)
        VALUES (:key, :start, 1) ON CONFLICT (key, window_start) DO UPDATE
        SET attempts = usage_buckets.attempts + 1
        WHERE usage_buckets.attempts < :maximum RETURNING attempts"""),
        {"key": key, "start": start, "maximum": maximum}).scalar_one_or_none()
    if result is None:
        raise UsageLimitError(message, retry_after=retry_after)


def require_signup_enabled():
    if not settings.signup_enabled:
        raise HTTPException(403, "Sabeel is in private preview. New accounts are not open yet. Existing creators can sign in.")


def check_auth_attempt(identity=None):
    """Five-minute global + HMAC identity windows, independent of spoofable IPs.

    Counts all attempts, including successful ones. No account existence lookup
    and no persistent email/IP storage. Edge DDoS protection is still separate.
    """
    try:
        with _session() as db, db.begin():
            now = _now(db)
            start = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
            retry = (start + timedelta(minutes=5) - now).total_seconds()
            message = "Too many sign-in attempts. Please wait a few minutes and try again."
            _increment(db, "auth:global", start, settings.auth_global_attempts, message, retry)
            if identity is not None:
                digest = hmac.new(settings.secret_key.encode(), str(identity).strip().casefold()[:320].encode(), hashlib.sha256).hexdigest()
                _increment(db, "auth:identity:" + digest, start, settings.auth_identity_attempts, message, retry)
            db.execute(text("DELETE FROM usage_buckets WHERE window_start < :cutoff"), {"cutoff": now - timedelta(days=7)})
    except SQLAlchemyError:
        logger.error("auth_limit_storage_unavailable")
        raise UsageLimitError("Sign-in is temporarily unavailable. Please try again shortly.", 503) from None


def reserve(kind):
    scope = current_scope.get()
    if not scope or not isinstance(scope.org_id, int) or scope.org_id <= 0:
        raise UsageLimitError("Select your workspace before generating. Your work is kept.", 403)
    if not settings.ai_generation_enabled:
        raise UsageLimitError("AI generation is temporarily paused. You can still edit and export saved work.", 503)
    if kind not in {"text", "image"}:
        raise ValueError("Unknown generation kind")
    org_id = scope.org_id
    suffix = "images" if kind == "image" else "text"
    try:
        with _session() as db, db.begin():
            now = _now(db)
            # Short transaction lock only; never held across network work.
            db.execute(text("SELECT pg_advisory_xact_lock(731209, 1)"))
            now = db.execute(text("SELECT clock_timestamp()" )).scalar_one()
            db.execute(text("DELETE FROM ai_usage_leases WHERE expires_at <= :now"), {"now": now})
            counts = db.execute(text("SELECT count(*), count(*) FILTER (WHERE org_id = :org) FROM ai_usage_leases"), {"org": org_id}).one()
            if counts[0] >= settings.ai_global_concurrency or counts[1] >= settings.ai_workspace_concurrency:
                raise UsageLimitError("Generation is busy. Wait for the current work to finish, then try again. Your draft is kept.", retry_after=15)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            retry = (start + timedelta(days=1) - now).total_seconds()
            _increment(db, f"ai:global:{kind}", start, getattr(settings, f"ai_global_daily_{suffix}"),
                       "Sabeel has reached today's preview generation limit. It resets at 00:00 UTC. You can still edit and export saved work.", retry)
            _increment(db, f"ai:org:{org_id}:{kind}", start, getattr(settings, f"ai_workspace_daily_{suffix}"),
                       f"Your workspace has reached today's {kind} generation limit. It resets at 00:00 UTC. You can still edit and export saved work.", retry)
            lease_id = str(uuid.uuid4())
            # Covers the SDK's per-phase timeouts + decoding. Crashes expire;
            # unknown attempts retain their daily count rather than being retried.
            ttl = 4 * max(settings.image_generation_timeout_seconds, settings.text_generation_timeout_seconds) + 120
            db.execute(text("INSERT INTO ai_usage_leases (id, org_id, expires_at) VALUES (:id, :org, :expiry)"),
                       {"id": lease_id, "org": org_id, "expiry": now + timedelta(seconds=ttl)})
            db.execute(text("DELETE FROM usage_buckets WHERE window_start < :cutoff"), {"cutoff": now - timedelta(days=7)})
        return lease_id
    except SQLAlchemyError:
        logger.error("ai_limit_storage_unavailable")
        raise UsageLimitError("Generation controls are temporarily unavailable. Your work is kept; try again shortly.", 503) from None


@contextmanager
def paid_call(kind):
    lease_id = reserve(kind)
    try:
        yield
    finally:
        try:
            with _session() as db, db.begin():
                _now(db)
                db.execute(text("DELETE FROM ai_usage_leases WHERE id = :id"), {"id": lease_id})
        except SQLAlchemyError:
            # Never discard a paid success because cleanup is unavailable.
            # The lease remains conservatively occupied until expiry.
            logger.error("ai_lease_cleanup_unavailable")


def usage_status(org_id):
    try:
        with _session() as db:
            now = _now(db)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            rows = dict(db.execute(text("SELECT key, attempts FROM usage_buckets WHERE window_start = :start AND key IN (:image, :writing)"),
                       {"start": start, "image": f"ai:org:{org_id}:image", "writing": f"ai:org:{org_id}:text"}).all())
            return {"generation_enabled": settings.ai_generation_enabled,
                    "reset_at": (start + timedelta(days=1)).isoformat(),
                    "images": {"used": rows.get(f"ai:org:{org_id}:image", 0), "limit": settings.ai_workspace_daily_images},
                    "text": {"used": rows.get(f"ai:org:{org_id}:text", 0), "limit": settings.ai_workspace_daily_text},
                    "concurrency": settings.ai_workspace_concurrency}
    except SQLAlchemyError:
        raise UsageLimitError("Usage information is temporarily unavailable.", 503) from None
