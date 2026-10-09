# Instagram connection safeguards — 9 October 2026

A creator connection now uses a short-lived server-side handoff. Previously the
callback did not verify OAuth state, temporary provider credentials were stored
in a readable signed browser session, and account selection could deactivate
existing accounts before validating the selection. Legacy endpoints provided a
second cookie-based connection path. The mobile selection screen also prevented
reconnection and automatically saved a lone returned account.

## Behavior and implementation

- `instagram_auth.py` validates the exact configured callback origin/path and
  uses the same Graph version as the existing publisher (v24.0). This alignment
  is not a claim that this is Meta's newest version. Discovery uses fixed Graph
  endpoints, bearer headers, bounded pagination, validated account/page IDs and
  sanitized errors. Callback work has a 60-second total deadline. Returned token
  expiry is recorded; missing expiry stays unknown.
- `instagram_connection.py` creates a 15-minute, one-use handoff bound to the
  signed-in user, browser handle and authorized workspace. Only hashes of the
  handle and OAuth state are stored. Pending provider data is encrypted using a
  domain-separated key derived from the existing application secret. The cookie
  contains an opaque handle, never provider credentials. This does not change
  storage of established IGAccount credentials; those retain their existing DB
  representation and require normal database protection.
- Callback state is consumed atomically before provider calls. Account selection
  validates every selected Instagram/Page pair before changing anything and
  commits saved accounts and handoff consumption together. PostgreSQL locks
  prevent concurrent duplicate saves. Reconnect preserves account IDs and other
  account activation states. Current and legacy connection routes share this
  service. Expired handoffs are removed on new connection and every 15 minutes.
- Middleware removes legacy credential-bearing session fields and expires the
  old standalone token cookie. Connection responses use no-store/no-referrer.
  HTTP client INFO logging is suppressed because token exchange URLs contain
  credentials. Old sessions that were halfway through connecting must start
  again; established account connections and posts remain in place.
- The mobile selection screen renders returned names as text, requires an
  explicit choice, supports reconnect, prevents duplicate submission and restores
  controls after failure. Cancellation, missing accounts and provider failure return to
  a visible recovery screen, with allowlisted messages rather than hidden dashboard
  query text. Account choices are disabled while saving. The request
  timeout directs users to check their workspace before retrying an uncertain
  save. No publishing occurs during account connection.
- Disconnect clears access and disables the existing account without deleting
  rows referenced by posts. Reading the current account or opening a dashboard no longer reactivates it.
  The legacy setup finalizer validates workspace membership, rejects manual
  tokens, skips automation creation without an account, and leaves any newly
  created plan disabled and requiring manual approval.

## Migration and deployment

Run `scripts/migrate_instagram_connections.py` with an explicitly supplied
production PostgreSQL `DATABASE_URL` before deploying. It adds only
`instagram_connection_attempts` and two indexes, with bounded lock/statement
waits. It does not alter users, accounts, posts, canonical sources or media.
Startup schema validation intentionally fails if this table is missing. No new
provider, secret, OAuth permission, or production content rewrite is introduced.

The additive table can remain during an application rollback. Do not drop it as
routine rollback. Reverting reintroduces the old connection weaknesses; if a
provider incompatibility appears, prefer disabling new connections while keeping
existing publishing intact. A secret rotation expires pending handoffs and signed
sessions, so users must start again. Existing accounts are not reconnected by this
release. Previous code could log credential-bearing data; restrict historical log
access and rotate any credentials confirmed exposed. No incident or access abuse
has been established by this audit.

## Evidence and limits

- 321 isolated Python checks, 36 disposable PostgreSQL/startup checks and 70
  JavaScript interaction checks passed locally. Coverage includes same-browser
  state, expiry/replay, workspace/user changes and revoked membership, cancellation,
  sanitized provider failures, real DB concurrency, migration repeatability,
  reconnect identity, preservation of post foreign keys, expired handoff cleanup,
  legacy session removal, and no automatic plan activation.
- Actual selection HTML/JS was inspected in the browser with synthetic local
  account/API fixtures at 320px, 390px and 1280px. Explicit reconnect, successful
  navigation, expired discovery and failed save recovery were exercised. Inspected
  phone controls had no horizontal overflow; the primary button was 52px tall.
- No live Meta consent grant, real account disconnect, new creator invitation,
  paid AI generation, scheduling or publication was performed for these checks.
  Fresh non-admin Meta connection and feed/Story permissions remain a pilot task.
  Responsive browser inspection is not physical iOS/Android creator validation.

The evidence bundle is outside Git at
`Sabeel Model Evaluation/2026-10-09-instagram-onboarding/review.html` and records the
production migration, CI/deployment results and follow-up checks. The current S3
restore, external alert delivery, physical-phone creator review and qualified
source/context review remain launch acceptance conditions.

References: [Starlette session behavior](https://www.starlette.dev/middleware/)
and [OAuth security BCP](https://www.rfc-editor.org/rfc/rfc9700.html). We do not
claim a full independent security assessment from this focused repair.
