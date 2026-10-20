"""Add private owner authentication state without changing any existing account.

Apply with the separate PostgreSQL administrator connection before deployment.
Keep the column on rollback. Once enrolled, never roll back to an application
that ignores MFA: that would bypass the second factor.
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

SQL = "ALTER TABLE users ADD COLUMN IF NOT EXISTS owner_mfa JSON"


def migrate(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL required")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text(SQL))


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
    print("Owner authentication migration completed")
