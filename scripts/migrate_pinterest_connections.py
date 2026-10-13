"""Add owner-pilot Pinterest connections without changing existing posts/accounts."""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(connection):
    if connection.dialect.name != 'postgresql':
        raise RuntimeError('PostgreSQL required')
    connection.execute(text("SET LOCAL lock_timeout='5s'"))
    connection.execute(text("SET LOCAL statement_timeout='30s'"))
    connection.execute(text('''CREATE TABLE IF NOT EXISTS pinterest_connection_attempts (
        id VARCHAR(64) PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        state_hash VARCHAR(64) NOT NULL, stage VARCHAR(16) NOT NULL, expires_at TIMESTAMPTZ NOT NULL)'''))
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_pinterest_connection_attempts_user_id ON pinterest_connection_attempts(user_id)'))
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_pinterest_connection_attempts_expires_at ON pinterest_connection_attempts(expires_at)'))
    connection.execute(text('''CREATE TABLE IF NOT EXISTS pinterest_connections (
        id SERIAL PRIMARY KEY, org_id INTEGER NOT NULL UNIQUE REFERENCES orgs(id),
        user_id INTEGER NOT NULL REFERENCES users(id), username VARCHAR(150) NOT NULL,
        encrypted_tokens TEXT, expires_at TIMESTAMPTZ, active BOOLEAN NOT NULL DEFAULT false,
        sandbox BOOLEAN NOT NULL DEFAULT true, refresh_pending BOOLEAN NOT NULL DEFAULT false,
        board_id VARCHAR(64), board_name VARCHAR(255))'''))


if __name__ == '__main__':
    url = make_url(os.environ['DATABASE_URL'])
    if url.get_backend_name() not in {'postgres', 'postgresql'}:
        raise SystemExit('PostgreSQL required')
    engine = create_engine(url.set(drivername='postgresql+psycopg'), hide_parameters=True)
    with engine.begin() as connection:
        migrate(connection)
    engine.dispose()
    print('Pinterest connection migration completed')
