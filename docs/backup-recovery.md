# Backup recovery and operating checks

Production uses PostgreSQL 17 and the S3-compatible `sabeel-backups` bucket.
The app filesystem is ephemeral. A local dump is not a durable production backup.
This procedure does not start the application or scheduler against restored data.

## Runtime safeguards

- The canonical backup service takes a logical `pg_dump` snapshot at 03:00 UTC.
  It contains data and schema, without owners or grants. Re-provision database
  roles/permissions deliberately during a real recovery. Database snapshots do not
  back up environment secrets, deployment configuration, or Cloudinary image bytes.
- Compression is stored privately, uploaded to S3 with SHA-256 metadata, then
  checked against remote size and metadata before retention runs. A checksum in
  metadata is transfer evidence, not a successful restore or protection against
  an attacker who can replace both the object and its metadata.
- Keep the newest 14 snapshots. This is a snapshot count, not a guaranteed number
  of days. Failed uploads do not trigger retention. Partial retention failures log
  `backup_retention_failed` and require attention.
- `scheduled_database_backup` raises on failure or non-durable storage, so
  APScheduler cannot report a failed return value as successful execution.
- At startup (after 30 seconds) and hourly, `backup_freshness` checks the newest
  remote snapshot. Missing, empty or older-than-26-hour snapshots trigger a new
  backup. Storage errors fail visibly and retry at the next check. A fresh snapshot
  is reused. The 26-hour tolerance is detection/retry policy, not a guaranteed RPO.
- Production currently runs one app worker/replica. A process-local lock prevents
  overlapping manual/daily/recovery dumps in that configuration. Before scaling
  schedulers, introduce leader election or an external singleton backup job.
- The admin health response intentionally keeps `backup_verified=false`: runtime
  configuration and a fresh object do not establish successful recovery.

## Approved isolated restore drill

Downloading production data requires explicit approval. Store only the needed S3
settings in an operator-owned file outside Git, with mode 0600 and parent directory
0700. Never paste credentials into chat or command arguments. The file contains:
`S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`, `S3_ENDPOINT_URL`, `S3_REGION`,
`S3_ADDRESSING_STYLE` (`virtual` for Railway's virtual-host addressing).

```sh
python -B scripts/verify_backup_restore.py \
  --env-file /private/path/backup-restore.env \
  --pg-bin /path/to/postgresql-17/bin \
  --report /private/path/restore-result.json
```

The tool uses the newest snapshot, checks size and SHA-256 when available, checks
gzip integrity, and restores with `ON_ERROR_STOP` into a private temporary cluster
using a Unix socket with TCP disabled. It checks row counts, account/workspace
relationships, validated constraints and valid indexes. It stops that cluster and
removes the private snapshot; only aggregate results remain. Legacy snapshots
without checksum metadata are explicitly reported as unverified for checksum.
They can still establish restore evidence if the SQL and integrity checks pass.

The tool cannot overwrite an existing report and never accepts a destination
database URL. On failure it reports the exception class, withholding provider/SQL
messages that may include credentials or private rows. If interrupted by a hard
kill or machine crash, inspect only this drill's `sabeel-restore-*` and
`sabeel-snapshot-*` directories, stop its identified cluster, then remove its
private temporary files. Never stop or clean an unrelated PostgreSQL instance.

A passing drill establishes recoverability of that exact snapshot, not of future
backups, source correctness, media availability, environment-secret recovery, or
a production recovery time objective. Run after backup/schema changes and before
public launch, recording snapshot timestamp, checksum, outcome and elapsed time.

### 2026-10-09 production snapshot drill

With the owner's approval, the 03:00:01 UTC S3 snapshot was downloaded into
restricted temporary storage and restored to disposable PostgreSQL 17 at 20:29 UTC.
It restored 1,408 posts, 6,249 content items, 12 Instagram accounts and 13 workspaces.
There were zero orphan/mismatched post-account relationships, orphan post
workspaces, unvalidated constraints or invalid indexes. Gzip integrity and
downloaded size passed. This legacy object had no SHA-256 metadata, so the report
explicitly records `checksum_verified=false`; no remote checksum comparison is
claimed. The SQL restore passed and the private snapshot and cluster were removed.
The application/scheduler never ran against restored production data. Total drill
time was 2.5 seconds on this machine; this is not a production recovery-time promise.

## Real incident recovery

1. Keep admission closed; pause publishing/automations and AI generation while
   diagnosing. Record the current deployment and database state. Do not reset
   production tables or blindly restore over the current database.
2. Check `/health`, `/ready`, Railway deploy status, recent errors and database
   capacity. Distinguish a provider outage from a database/application outage.
3. Select a backup timestamp deliberately. Restore into a **separate** PostgreSQL
   instance and validate source/card/caption/media relationships, users/accounts,
   draft states, sequences and publishing claims. Apply required reviewed additive
   migrations to the restored instance; a snapshot can predate the current schema.
4. Reconcile posts published or attempted after that snapshot with Meta before
   enabling the scheduler. Never turn `publishing` or `publish_unknown` into an
   automatic retry merely because a database was restored.
5. Obtain explicit approval for production data cutover. Preserve the original
   database/backup, switch the connection deliberately, run health and affected-flow
   checks with jobs disabled, then enable jobs after reconciliation. Record RPO/RTO
   from the actual incident rather than promising a number from a synthetic test.

## Alert acceptance and current limits

An application log is not a delivered alert. Independently monitor `/health` and
`/ready`; alert on persistent failures, `backup_job_failed`,
`backup_storage_unavailable`, `backup_retention_failed`, stale/missing
`backup_freshness`, and missing hourly freshness events (the app may be down).
Use an external monitor so the app's own outage cannot disable detection.
Suggested starting thresholds: three failed one-minute health checks; missing
backup-check heartbeat for two hours; volume 70% warning/85% critical; sustained
RAM/CPU pressure. Tune using measured traffic. The 24-hour inspection is not a load
test and app API attempt budgets are not provider currency budgets.

Railway's [alert guidance](https://docs.railway.com/guides/alerts-crashes-failed-deploys)
describes native notifications, resource monitors and project webhooks. As of this
audit no project webhooks were configured. That alone does not establish whether
native email alerts/monitors exist. The plugin cannot verify notification delivery,
volume-backup settings or the text of the remaining Postgres warning. Axiom's token
name is configured, but ingestion and notification delivery are not verified.
The owner selected an operational email destination. The existing local Axiom
token received HTTP 403 on the monitor-management API; no permissions were changed
and no notification was sent. Use the owner's dashboard to configure an external
monitor and prove actual inbox delivery with a clearly labeled test. Do not treat
an email sent manually, a console log or ingestion acceptance as that proof.

The log shipper now checks HTTP status and the provider's accepted/failed counts.
Rejected, partial or uncertain batches emit rate-limited `log_delivery_failed`
notices directly to the Railway console, without recursing into the shipper or
exposing log payloads, provider responses or tokens. Subsequent successful batches
emit `log_delivery_recovered` with the earlier unconfirmed count; those earlier
events are not retried or claimed delivered. The queue remains in-memory and is
not a durable log spool. These console notices still need external monitoring.
The email service returns false when unconfigured or when provider acceptance is
unconfirmed; it no longer prints email contents or reports a console fallback as
delivery. Provider acceptance is not inbox receipt.

## Controlled creator pilot

Keep `SIGNUP_ENABLED=false`. The subsequent [tester-access release](tester-access.md)
provides expiring, single-use invitations at `/admin/testers`, private creator
workspaces and revocation. Do not use a shared administrator account or temporarily
open registration. Testers need their own workspace and Meta connection, normal
AI allowances and manual source/page review. Signed-in feedback is available at
`/app/feedback` and only superadmins can read `/admin/feedback`. Physical iOS/Android,
fresh Meta onboarding, alert delivery and qualified source/context review remain
launch conditions; an invitation is not a readiness certification.

## Deployment / rollback

No schema migration or existing-data rewrite. Old snapshots remain readable; new
ones add object metadata and omit SQL grants for portable recovery. Rollback only
the application commit if necessary; retain all snapshots and existing guard
tables. Rolling back removes freshness recovery and truthful scheduler failure
reporting, so monitor backups manually until the fix is restored.
