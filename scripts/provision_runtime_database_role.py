"""Prepare a restricted PostgreSQL login without switching the running app.

Default: inspect only. Apply after a verified backup, as the database owner.
The operator enters a new password interactively; secrets are never printed.
The existing administrator login and all table ownership remain unchanged.
"""
import argparse
import getpass
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from psycopg import sql

ROLE = "sabeel_runtime"
MARKER = "Sabeel restricted application role v1"


def inspect_role(connection):
    row = connection.execute(text("""
        SELECT r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication,
               r.rolbypassrls, r.rolcanlogin,
               shobj_description(r.oid, 'pg_authid') AS description,
               EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS member,
               EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid) AS owns_relations
        FROM pg_roles r WHERE r.rolname=:role
    """), {"role": ROLE}).mappings().first()
    if row is None:
        return {"exists": False, "managed": False, "restricted": False}
    forbidden = ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication",
                 "rolbypassrls", "member", "owns_relations")
    return {"exists": True, "managed": row["description"] == MARKER,
            "restricted": bool(row["rolcanlogin"] and not any(row[k] for k in forbidden))}


def provision(connection, *, password=None):
    """Caller owns the transaction. Existing passwords are never overwritten."""
    connection.execute(text("SELECT pg_advisory_xact_lock(731209, 40)"))
    before = inspect_role(connection)
    if before["exists"] and (not before["managed"] or not before["restricted"]):
        raise ValueError("Existing role requires manual review; no permissions changed")
    database, owner = connection.execute(text(
        "SELECT current_database(), current_user")).one()
    if owner == ROLE:
        raise ValueError("Run maintenance with the database owner, not the app role")
    other_owners = connection.execute(text("""
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m','f')
          AND pg_get_userbyid(c.relowner) != current_user
    """)).scalar_one()
    if other_owners:
        raise ValueError("Multiple object owners require a reviewed grant plan")
    driver = connection.connection.driver_connection
    with driver.cursor() as cursor:
        if not before["exists"]:
            # URL-safe so the owner can enter it in Railway without URL encoding.
            if not password or not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", password):
                raise ValueError("Use 40–128 random letters, numbers, underscores or hyphens")
            verifier = driver.pgconn.encrypt_password(
                password.encode(), ROLE.encode(), b"scram-sha-256").decode()
            cursor.execute(sql.SQL(
                "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
            ).format(sql.Identifier(ROLE), sql.Literal(verifier)))
            cursor.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(
                sql.Identifier(ROLE), sql.Literal(MARKER)))
        # Do not silently revoke privileges from PUBLIC or other services.
        # On older clusters a PUBLIC CREATE grant needs separate review.
        can_create = connection.execute(text("""
            SELECT has_schema_privilege(:role, 'public', 'CREATE')
                OR has_database_privilege(:role, current_database(), 'CREATE')
        """), {"role": ROLE}).scalar_one()
        if can_create:
            raise ValueError("PUBLIC/inherited CREATE permissions require separate review")
        for statement in (
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(ROLE)),
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)),
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(ROLE)),
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(ROLE)),
            sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(sql.Identifier(owner), sql.Identifier(ROLE)),
            sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(sql.Identifier(owner), sql.Identifier(ROLE)),
        ):
            cursor.execute(statement)
    result = inspect_role(connection)
    if not result["restricted"]:
        raise ValueError("Role verification failed")
    return {**result, "created": not before["exists"],
            "runtime_connection_changed": False, "table_ownership_changed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-id")
    args = parser.parse_args()
    if args.apply and not args.backup_id:
        parser.error("--apply requires a verified --backup-id")
    from app.db import engine
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            state = inspect_role(connection)
            password = None
            if args.apply and not state["exists"]:
                if not sys.stdin.isatty():
                    raise ValueError("New credentials require an interactive terminal")
                password = getpass.getpass("New app database password (40–128 URL-safe random characters): ")
                if password != getpass.getpass("Confirm password: "):
                    raise ValueError("Passwords did not match")
            result = provision(connection, password=password) if args.apply else state
        print(json.dumps(result))
    except Exception:
        print("Database role preparation failed; changes rolled back. Check the documented prerequisites. No credentials were printed.", file=sys.stderr)
        raise SystemExit(1)
