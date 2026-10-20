# Separate runtime database access from administrator maintenance

The production audit on 20 October confirmed private networking and encrypted
PostgreSQL transport, but the application still uses a database superuser.
Do not describe this follow-up as deployed until the runtime identity is changed.

`scripts/provision_runtime_database_role.py` prepares `sabeel_runtime` with only
CONNECT, public-schema USAGE, table SELECT/INSERT/UPDATE/DELETE and sequence
USAGE/SELECT. It grants the same permissions on future objects created by the
maintenance owner. It does not transfer ownership or change the running app's URL.
It rejects an unknown existing role, role memberships, elevated flags and PUBLIC
CREATE permissions rather than silently modifying another service's permissions.

This limits permanent DDL, role creation, server-file reads and escalation.
It does not isolate creators within PostgreSQL: the application still enforces
workspace/record ownership. An app compromise could still access app data.

## Operator cutover

1. Verify a fresh durable backup. Keep the existing administrator URL available
   in the **Postgres service**, not as another variable in the app service.
2. In the currently deployed app's Railway Console, run the script with no flags
   for inspection. To provision, the operator runs:

   ```sh
   python scripts/provision_runtime_database_role.py --apply --backup-id <verified-backup-identifier>
   ```

   Enter a password-manager-generated 40–128 character password containing only
   letters, numbers, underscores and hyphens, twice at the hidden prompts.
   The script converts it to a SCRAM verifier before sending the CREATE ROLE
   statement. It never prints a password or full connection URL.
3. In **Sabeel Studio service → Variables**, replace DATABASE_URL with the same
   private host, port, database and SSL options, but username `sabeel_runtime`
   and the new password. Do not change Postgres's administrator variables.
   Remove any duplicate administrator URL from the app service.
4. Apply the variable change and wait for a healthy deployment.
5. Verify `/ready`, login, draft save/reopen, source read, social-account retrieval
   and an actual portable backup. Inspect `current_user` and `rolsuper` in the
   app console: the former should be `sabeel_runtime`, the latter false.
6. Future migrations run through the **Postgres service's administrator
   connection**, not by enabling startup migrations or elevating the app.

No data/schema migration is performed. If cutover fails, restore the previous
DATABASE_URL from the Postgres service and redeploy; do not roll back the
application before the encryption-compatible release. Do not drop the runtime
role or change its password as a routine retry.

## Validation

Disposable PostgreSQL tests exercise real restricted-role writes, sequences,
advisory locking and a complete pg_dump using the production flags. They verify
that permanent CREATE/ALTER/DROP/TRUNCATE, role creation, switching to the
administrator and server-file reads fail. Preparation is repeatable and rejects
unknown roles and invalid passwords without changing them.

References: [PostgreSQL GRANT](https://www.postgresql.org/docs/17/sql-grant.html),
[default privileges](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html),
[pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[libpq password verifier API](https://www.psycopg.org/psycopg3/docs/api/pq.html#psycopg.pq.PGconn.encrypt_password).
