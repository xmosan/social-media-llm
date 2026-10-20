"""Upgrade legacy credentials after deploying the compatible reader/writer.

Run a portable backup first. Default is a count-only dry run. The transaction
locks rows, verifies every envelope, and changes only nonempty legacy tokens.
Keep the deployed encryption-capable version as the rollback floor; older app
versions cannot read upgraded credentials. Never print credential values.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.security.connection_tokens import PREFIX, open_token, seal_token


def migrate(connection, *, apply=False):
    rows = connection.execute(text(
        "SELECT id, access_token FROM ig_accounts ORDER BY id FOR UPDATE"
    )).all()
    encrypted = legacy = empty = 0
    for row in rows:
        value = row.access_token
        if not value:
            empty += 1
        elif value.startswith(PREFIX):
            open_token(value)
            encrypted += 1
        else:
            legacy += 1
            if apply:
                sealed = seal_token(value)
                if open_token(sealed) != value:
                    raise RuntimeError("Credential round-trip verification failed")
                connection.execute(text("UPDATE ig_accounts SET access_token=:value WHERE id=:id"),
                                   {"id": row.id, "value": sealed})
    return {"encrypted": encrypted, "legacy": legacy, "disconnected": empty,
            "upgraded": legacy if apply else 0, "remaining_legacy": 0 if apply else legacy}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-id", help="Verified pre-change portable backup identifier")
    args = parser.parse_args()
    if args.apply and not args.backup_id:
        parser.error("--apply requires --backup-id after verifying a fresh backup")
    from app.db import engine
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            result = migrate(connection, apply=args.apply)
        print(json.dumps(result))
    except Exception:
        print("Credential maintenance failed; transaction rolled back. No credentials were printed.", file=sys.stderr)
        raise SystemExit(1)
