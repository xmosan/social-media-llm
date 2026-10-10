"""Invalidate old sessions without changing passwords or deleting creator data.

Apply before the application deployment. Existing accounts start at version zero,
which preserves current sessions. Retain this column on rollback; do not deploy an
older authentication implementation after returning accounts have been enabled.
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL required")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0"))


if __name__ == "__main__":
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise SystemExit("PostgreSQL required")
    engine = create_engine(url.set(drivername="postgresql+psycopg"), hide_parameters=True)
    try:
        with engine.begin() as connection:
            migrate(connection)
    finally:
        engine.dispose()
    print("Session version migration completed")
