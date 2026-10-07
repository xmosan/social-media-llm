# Social Media LLM - SaaS

## Text generation

All runtime text calls use `app/services/text_provider.py` and the Responses API.
Writing (captions, separate reflections, cards, drafts and rewrites) uses GPT-6
Astra at low reasoning effort. Topic variations, source relevance checks and
optional color selection use GPT-6 Luna with no reasoning. These defaults were
checked against official OpenAI documentation and live account access on
2026-10-07; availability and aliases can change.

| Variable | Default |
| --- | --- |
| `OPENAI_TEXT_MODEL` | `gpt-6-astra` |
| `OPENAI_TEXT_REASONING_EFFORT` | `low` |
| `OPENAI_UTILITY_MODEL` | `gpt-6-luna` |
| `OPENAI_UTILITY_REASONING_EFFORT` | `none` |
| `TEXT_GENERATION_TIMEOUT_SECONDS` | `45` |

Uses the existing `OPENAI_API_KEY`; no new key or schema migration is required.
Override models only with tested Responses-compatible models and matching
reasoning settings. Astra and GPT-6.1 Sol require at least low reasoning effort.
Requests are stateless (`store=false`), bounded to 2,048 output tokens (including
reasoning), and have no automatic retries or hidden fallback model. Structured
outputs are schema-validated locally; refusal, truncation and invalid output
are failures. Logs contain model, schema, elapsed time and output-token count,
not provider response bodies or prompts.

Canonical source fields are assembled by the application. Optional AI reflections
may be omitted on failure; fake scripture, unrelated fallback captions and mock
successes are not substituted. Generic “add Ayah/Hadith” rewriting is rejected:
select a verified source in Studio instead. Source-relevance checks fail closed
when unavailable. Existing deterministic topic and color fallbacks remain.

Before changing either model, run the isolated backend and PostgreSQL suites,
then bounded live checks of reflection, rewrite, structured caption/draft,
relevance acceptance/rejection and utility output. The initial 12-case live pass
succeeded (writing 2.63–8.67 seconds; utilities 1.41–3.32 seconds). This is a small
application compatibility evaluation, not a general model benchmark. No test
posts were published for this migration. Roll back to the previous deployment if
a model/configuration change fails; do not silently reinstate retired model IDs.

Official references: [GPT-6 migration](https://developers.openai.com/api/docs/guides/latest-model),
[Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[deprecations](https://developers.openai.com/api/docs/deprecations).


> **NOTICE**: This repository contains proprietary software owned by Mohammed Hassan. It is shared strictly for academic grading purposes. Unauthorized copying, modification, distribution, or use is prohibited.

## Sabeel Vision model configuration

Production image generation uses OpenAI only. All Studio, automation, and legacy image paths use the shared adapter in `app/services/image_provider.py`; historical `dalle` and `gemini` engine values resolve to that same service. The UI presents Sabeel Vision. Google is available only in the explicit comparison script, not as a production fallback.

| Variable | Default |
| --- | --- |
| `OPENAI_IMAGE_MODEL` | `gpt-image-2.5-sunburst` |
| `OPENAI_IMAGE_FALLBACK_MODEL` | `gpt-image-2.5-flare` (empty disables fallback) |
| `OPENAI_IMAGE_QUALITY` | `medium` (`low`, `medium`, or `high`) |
| `IMAGE_GENERATION_TIMEOUT_SECONDS` | `120` per provider attempt |

Keep `OPENAI_API_KEY` in the deployment secret store. Responses are decoded from image bytes, then rendered and uploaded through the existing media pipeline. Source text remains separate from generation. Model and quality are included in the background cache identity, and the actual model is logged without credentials or prompts. Fallback occurs once only for explicit HTTP 404, 429, or 503 responses; content refusals, authentication failures, and uncertain timeouts do not trigger another paid request. A provider-wide outage can still affect both OpenAI models.

Before changing defaults, run the bounded comparison script with an output directory outside the repository. It prints a dry-run plan unless `--live` is present. Use `--models sunburst flare` for OpenAI only; `--env-file` names a private existing credential file, never a committed file. It records attempts before calling the provider to prevent accidental paid retries after interruption. Generated files and per-request timing/usage are local evaluation artifacts, not repository content. Confirm model access, inspect actual cards, and check provider retirement notices before deploying a replacement.

## Card typography and Hadith search

Cards use bundled Amiri for Arabic, Qur'anic marks, and mixed text containing ﷺ.
Pillow 12.2.0 with native RAQM shaping is required: source Unicode is sent directly
to the shaping engine without manual reversal. The Docker build installs FriBiDi
and verifies RAQM support. On macOS, install FriBiDi and check
`python -c "from PIL import features; assert features.check_feature('raqm')"`
before running the renderer or isolated tests. If using a private native-library
prefix, pass `DYLD_FALLBACK_LIBRARY_PATH=<prefix>/lib` to the test runner.

Reference, Arabic, translation, and optional labeled reflection share a measured
layout. Longer cards use 1080 × 1350 portrait; short cards remain 1080 square.
Content that cannot fit at readable sizes fails before background generation.
No block is silently dropped, no reference hidden, and source case is preserved.
Previously saved images are not rewritten; regenerate their visuals to apply the fix.

Hadith search returns a bounded batch plus `next_cursor`, `complete`, and
`pages_scanned`. Studio offers **Search more narrations** and collection selection.
Each call checks at most three provider pages; no empty batch claims the whole
collection has been searched. Page hints travel with selected source metadata and
are re-fetched with exact collection/ID validation before use. The inconsistent
single-record provider endpoint remains disabled. Older saved records without a
page hint keep the existing bounded lookup and fail closed if not found.

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
