"""Add invitation records and nullable access bounds; no existing data changes.

Run with explicit DATABASE_URL before deploying the app. Repeatable PostgreSQL
migration. Rollback: deploy the preceding app and retain these columns/table.
Do not roll back while tester grants are active (old app lacks expiry checks).
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("This migration requires PostgreSQL")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tester_expires_at TIMESTAMPTZ"))
    connection.execute(text("ALTER TABLE orgs ADD COLUMN IF NOT EXISTS tester_expires_at TIMESTAMPTZ"))
    connection.execute(text("ALTER TABLE orgs ADD COLUMN IF NOT EXISTS tester_revoked_at TIMESTAMPTZ"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS tester_invitations (
        id VARCHAR(36) PRIMARY KEY, email VARCHAR(254) NOT NULL UNIQUE,
        token_hash VARCHAR(64) NOT NULL UNIQUE,
        created_by INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL, pilot_days INTEGER NOT NULL,
        redeemed_at TIMESTAMPTZ, user_id INTEGER UNIQUE REFERENCES users(id),
        org_id INTEGER UNIQUE REFERENCES orgs(id), access_expires_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ, revoked_by INTEGER REFERENCES users(id))"""))


if __name__ == "__main__":
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise SystemExit("PostgreSQL required")
    engine = create_engine(url.set(drivername="postgresql+psycopg"), hide_parameters=True)
    with engine.begin() as connection:
        migrate(connection)
    engine.dispose()
    print("Tester access migration completed")
