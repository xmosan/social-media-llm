"""Add launch counters and leases explicitly before deployment; no data rewrites.

DATABASE_URL must be supplied by the operator. No dotenv or app startup.
Rollback: deploy the previous app; retain these tables. Never reset counters
as part of a deploy. This migration is additive and safe to run repeatedly.
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("This migration requires PostgreSQL")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS usage_buckets (
        key VARCHAR(100) NOT NULL, window_start TIMESTAMPTZ NOT NULL,
        attempts INTEGER NOT NULL, PRIMARY KEY (key, window_start))"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_usage_buckets_window_start ON usage_buckets (window_start)"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS ai_usage_leases (
        id VARCHAR(36) PRIMARY KEY, org_id INTEGER NOT NULL REFERENCES orgs(id),
        expires_at TIMESTAMPTZ NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_usage_leases_org_id ON ai_usage_leases (org_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_usage_leases_expires_at ON ai_usage_leases (expires_at)"))


if __name__ == "__main__":
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise SystemExit("PostgreSQL required")
    engine = create_engine(url.set(drivername="postgresql+psycopg"), hide_parameters=True)
    with engine.begin() as connection:
        migrate(connection)
    engine.dispose()
    print("Launch guard migration completed")
