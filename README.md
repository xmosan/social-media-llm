# Social Media LLM - SaaS

> **NOTICE**: This repository contains proprietary software owned by Mohammed Hassan. It is shared strictly for academic grading purposes. Unauthorized copying, modification, distribution, or use is prohibited.

## Disaster Recovery Plan

Recovery requires a verified backup and an explicit cutover. Startup retries the configured PostgreSQL connection three times, then fails. It does not switch to `SECONDARY_DATABASE_URL`, fall back to SQLite, or create/repair the schema. `SECONDARY_DATABASE_URL`, `ENV_BACKUP_KEY`, and `PRIMARY_REGION` are legacy configuration fields; they do not implement automatic failover or environment snapshots.

### Backup storage and schedule

When the application scheduler is enabled, `app/services/scheduler.py` requests a database dump daily at **03:00 UTC**. The administrator's portable-backup action calls the same service in `app/services/backups.py`.

- The production image includes `pg_dump` 17. Backups are gzip-compressed SQL files named `backup_<timestamp>_<uuid>.sql.gz`.
- Set `BACKUP_STORAGE_TYPE=s3` and configure `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`, and `S3_REGION` through the deployment's secret/configuration store. For Railway buckets, also configure `S3_ENDPOINT_URL` and `S3_ADDRESSING_STYLE=virtual`; use Railway reference variables for credentials.
- Remote objects live under `database_backups/`. The service verifies the uploaded object's size and attempts to retain the latest 14 remote snapshots. Retention failures are logged separately.
- Local copies are in the process working directory's `backups/` folder (`/app/backups` in the image). They are not durable on an unmounted Railway application filesystem. The administrator download endpoint only retrieves local copies.
- Railway's native volume backups are separate from these SQL dumps. Check their schedule and completed snapshots in **Postgres → Backups**. Point-in-time recovery is another, separately configured feature.

A successful upload is not proof of restoration. Check the latest remote object's timestamp and test recovery periodically. A daily schedule does not guarantee a recovery point if the application or backup job is unavailable.

### Restore into an isolated database first

1. Obtain approval before handling a production backup. Download a selected `.sql.gz` object from private remote storage into a restricted temporary directory; do not commit it or print its contents. The dump can contain credentials and private user data.
2. Provision a separate, empty PostgreSQL 17 database from `template0`. Verify its host and name are not production. Do not start the application, scheduler, or provider integrations against the restored copy.
3. Configure libpq connection settings for that disposable target, using a protected password file or secret injection rather than credentials in shell arguments. Check archive integrity with `gzip -t`, then restore with the PostgreSQL client:

   ```sh
   # PGHOST, PGPORT, PGUSER, and PGDATABASE must identify the disposable target.
   # BACKUP_FILE must identify the approved local .sql.gz copy.
   set -o pipefail
   gzip -t "$BACKUP_FILE" && gzip -dc "$BACKUP_FILE" | psql -X --set ON_ERROR_STOP=on --single-transaction
   ```

   These dumps contain `--clean --if-exists` statements: restoring can drop objects in the target. Never aim a recovery drill at production. They omit object ownership but may retain grants; any referenced roles must be reviewed and provisioned on the isolated target. Do not ignore SQL errors. See [PostgreSQL's SQL-dump restoration guidance](https://www.postgresql.org/docs/17/backup-dump.html#BACKUP-DUMP-RESTORE).
4. Verify schema, row counts, organization/account relationships, exact source metadata, separate card/caption fields, schedules, and saved publication IDs/statuses using read-only checks. Record the snapshot timestamp, restore duration, and results without recording private rows. Do not publish recovered jobs as a test.
5. Remove the disposable database and temporary dump through the approved cleanup process. Keep the remote recovery snapshot.

CI exercises real PostgreSQL dump/restore with synthetic fixtures in `tests/postgres/test_backend_postgres.py`, including source metadata and uncertain publication state. That proves the tested mechanism; it does not certify an actual production backup. Production restoration must be recorded separately after a drill.

### Manual cutover or deployment in a new region

1. Approve a maintenance window, confirm a current backup, and record the existing deployment/database target for rollback. Stop the old application's writers and scheduler before cutover to avoid competing publishers or divergent data.
2. Restore to and verify a separate target as above. Provision the application from the intended commit and inject configuration from the existing secure configuration store; the application does not generate encrypted environment snapshots. Preserve the shared session signing key and required provider configuration without placing secrets in Git or logs.
3. Set `DATABASE_URL` to the verified target, initially with `SCHEDULER_ENABLED=false`, and deploy. Startup performs a read-only schema check. Resolve missing schema through a reviewed migration, not startup synchronization or table recreation.
4. Verify `/health` and `/ready`, authentication, organization isolation, and saved source/card/caption data. Review overdue schedules and reconcile uncertain Instagram publication results before enabling one scheduler. Do not retry uncertain publishing blindly.
5. Re-enable scheduling only after the old instance is stopped and the recovered state is reviewed. If rollback is necessary, stop the new instance first. Account for any writes accepted after cutover before returning to the old database; switching URLs alone does not reconcile them.

## Centralized Observability (Axiom)

The system is instrumented with rigorous, non-blocking structured JSON logging that correlates multi-service requests via UUIDs. It ships directly to Axiom without the need for a Heavy Forwarder or Datadog agent.

### Setup Instructions
To enable remote streaming, configure the following environment variables in your `.env` or Railway project variables:

- `AXIOM_TOKEN="xaat-YOUR-API-KEY"` (Required to enable shipping)
- `AXIOM_DATASET="social-media-llm"` (Defaults to "social-media-llm")
- `AXIOM_ORG_ID="your-org-id"` (Optional if your token already scopes to the organization)

**Security Checks:**
- Secret keys (`OPENAI_API_KEY`, Access Tokens, Authorization headers) are natively redacted before leaving the host memory.
- If Axiom ever goes offline, the in-memory log buffer queue naturally drops logs after timing out, heavily ensuring your application will *never* crash due to an observability outage.
- To check the health of the logging shipper, a Superadmin can visit `/admin/debug/logging`.
