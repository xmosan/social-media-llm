"""Add the nullable workspace brand snapshot. Run explicitly before deploying.

DATABASE_URL must be supplied by the operator; no dotenv or application startup.
Idempotent, additive, no data rewrite. Rollback: deploy the previous application;
leave this nullable column in place to preserve brand data.
"""
import os
from sqlalchemy import create_engine, text


def migrate(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("This migration requires PostgreSQL")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("ALTER TABLE orgs ADD COLUMN IF NOT EXISTS brand_kit JSON"))


if __name__ == "__main__":
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        migrate(connection)
    engine.dispose()
    print("Workspace brand-kit migration completed")
