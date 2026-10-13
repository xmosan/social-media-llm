"""Allow workspace drafts without Instagram; existing relationships are untouched.

Run explicitly before deployment with DATABASE_URL. PostgreSQL only. Reversible
application rollout: retain this nullable column. Do not restore NOT NULL while
unassigned drafts exist; never delete or assign users' work to force a rollback.
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("This migration requires PostgreSQL")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("ALTER TABLE posts ALTER COLUMN ig_account_id DROP NOT NULL"))


if __name__ == "__main__":
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise SystemExit("PostgreSQL required")
    engine = create_engine(url.set(drivername="postgresql+psycopg"), hide_parameters=True)
    with engine.begin() as connection:
        migrate(connection)
    engine.dispose()
    print("Workspace draft migration completed")
