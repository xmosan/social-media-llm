"""Add expiring OAuth handoffs. Explicit operator URL; no dotenv or app startup."""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL required")
    connection.execute(text("SET LOCAL lock_timeout='5s'"))
    connection.execute(text("SET LOCAL statement_timeout='30s'"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS instagram_connection_attempts (
        id VARCHAR(64) PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        state_hash VARCHAR(64) NOT NULL, stage VARCHAR(16) NOT NULL,
        encrypted_payload TEXT, expires_at TIMESTAMPTZ NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_instagram_connection_attempts_user_id ON instagram_connection_attempts(user_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_instagram_connection_attempts_expires_at ON instagram_connection_attempts(expires_at)"))


if __name__ == "__main__":
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise SystemExit("PostgreSQL required")
    engine = create_engine(url.set(drivername="postgresql+psycopg"), hide_parameters=True)
    with engine.begin() as connection:
        migrate(connection)
    engine.dispose()
    print("Instagram handoff migration completed")
