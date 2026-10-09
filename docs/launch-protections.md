# Private-preview admission and generation safeguards

Sabeel is still in private preview. This change protects existing creators while
we complete real-device, source/context and operational launch checks. It is not
an unrestricted-launch approval or a subscription/pricing implementation.

## Admission

`SIGNUP_ENABLED` defaults to `false`, independently of `COMING_SOON_MODE`.
Email registration rejects new accounts before hashing or creating records.
Google callbacks reject new accounts too; existing active accounts can sign in.
Google identity must include a verified email, and conflicting linked identities
cannot be attached. OAuth state verification stays with Authlib. No invitations
are issued, no existing user permissions change, and no users are deleted.

The register page explains private-preview access. Google denial returns to sign
in with the same explanation. Raw OAuth state, user email and provider exception
bodies are no longer logged. Both current host-only session cookies and legacy
Google Domain cookies are cleared at logout.

Every password attempt (including successes) consumes a five-minute global and
normalized-identity counter. Google start/callback requests consume the global
counter. Keys contain a signing-key HMAC, never the email or IP. This avoids
relying on client-controlled forwarding headers. Defaults are 10 attempts per
identity and 300 across the app per fixed five-minute UTC window. Configurable:
`AUTH_IDENTITY_ATTEMPTS`, `AUTH_GLOBAL_ATTEMPTS`. A 429 includes `Retry-After`.
These controls do not replace edge DDoS protection or a security review. Opening
password signup also needs a deliberate email-verification/recovery policy.

## AI budgets

The shared configured text and image providers reserve before dispatch. Studio,
legacy endpoints, preview generation and scheduled workers use these providers.
FastAPI's authorized workspace dependency binds a request-owned scope; scheduled
workers derive a fresh scope from their saved automation. An absent scope denies
paid work. Superadmins and workspace API keys are subject to the same budgets.

| Setting | Default |
|---|---:|
| `AI_WORKSPACE_DAILY_IMAGES` | 20 |
| `AI_WORKSPACE_DAILY_TEXT` | 200 |
| `AI_GLOBAL_DAILY_IMAGES` | 100 |
| `AI_GLOBAL_DAILY_TEXT` | 1,000 |
| `AI_WORKSPACE_CONCURRENCY` | 2 |
| `AI_GLOBAL_CONCURRENCY` | 8 |
| `AI_GENERATION_ENABLED` | true |

These are configurable **provider-attempt** allowances, not successful-post
counts or currency billing. A workflow can make several writing calls. Failed,
timed-out, refused and malformed provider responses still consume an attempt;
an eligible image fallback needs its own reservation. No automatic paid retry is
added. Text input plus instructions is limited to 40,000 characters, image briefs
to 12,000; text output remains capped at 2,048 tokens. Oversized input is rejected,
never silently truncated by the guard. Current configured models, image size,
quality and source rendering are unchanged. Raw adapters remain available to
explicit offline evaluation scripts; app routes use only configured providers.

Daily windows reset at 00:00 UTC. PostgreSQL commits reservations independently
of the post transaction, so rollback or app restart cannot erase attempts. A short
transaction lock coordinates leases across replicas. The lock is released before
network work. Leases are released on completion/failure and expire after four
configured provider timeout intervals plus two minutes following a crash. A
failed cleanup retains the lease until expiry without discarding a paid output.
Counters older than seven days and expired leases are cleaned opportunistically.
Storage failure denies new paid calls. Global provider usage outside this app,
actual invoices, project spending limits and upstream alerts are not measured.

`AI_GENERATION_ENABLED=false` pauses new provider dispatch. Source browsing,
manual editing, saved media, exports and layout-only reuse remain available.
Creators can inspect their workspace's allowance under You. A limit response
keeps the idea/source/previous valid visual, restores controls and reports the
reset or busy state; it does not automatically retry. Automation quota failures
roll back the run, retain its error, and create no partial post. Existing manual
source/visual approval and publishing guards remain in force.

## Deployment and rollback

Run `scripts/migrate_launch_guards.py` explicitly with the operator-supplied
PostgreSQL `DATABASE_URL` **before** deploying. It creates only `usage_buckets`
and `ai_usage_leases` plus their indexes, with bounded lock/statement timeouts.
It is idempotent, does not rewrite any existing table/data, and never loads dotenv
or starts the application. Startup's existing schema check detects missing
schema. The disposable PostgreSQL tests cover absence, repeat migration, existing
records, counter persistence, competing requests, lease expiry and real startup.

Deploy the prior application to roll back; leave both additive tables intact.
Never reset counters as a deployment step. Restoring old code removes these
protections, so block registration at the edge or retain the admission patch
if a rollback is required. The landing page alone is not an access control. Do not turn `SIGNUP_ENABLED` on simply to test an
existing account. Cohort admission/invitation and email recovery remain separate
work before onboarding external testers.

## Phone follow-up

The live walkthrough found that pressing Return in a source field could submit
the surrounding form and open a scheduling alert. Form submission now exits
unless the editor is on Share; search keeps its existing debounced behavior.
This also protects single-line design fields. Explicit Share actions retain
all their account, review, time and duplicate-submit checks.

## Verification boundary

Automated tests use synthetic inputs, mock provider responses and disposable
PostgreSQL. Browser failure checks use a visibly labelled local HTTP fixture.
Production checks must record actual deployed revision, migration, health,
allowance visibility, a bounded live provider attempt, exact saved-source/media
preservation and export. Store final results outside Git in
`Sabeel Model Evaluation/2026-10-08-launch-guards/review.html`.
Real creator, qualified source/context and physical-phone approvals have not
occurred. Current S3 restore, provider budgets/alerts, edge protection and fresh
Meta onboarding still require their own evidence.
