# Backend security review — 20 October 2026

Scope: FastAPI routes, authentication/session handling, workspace/owner isolation,
source-library permissions, URL imports, image uploads, stored social credentials,
browser injection, errors/logging, public forms and production dependency updates.
This is an engineering audit with adversarial regression tests, not a claim that
all vulnerabilities have been found or an independent penetration test.

## Confirmed fixes

- Regular creators could mutate global library entries through legacy routes.
  Global records are now read-only outside the owner administration tools; private
  entries are scoped to their creator and active workspace membership is checked.
  Suggestions and automation retrieval no longer expose other creators' private entries.
- URL imports could fetch internal services. Fetches now require public HTTPS,
  validate DNS addresses, pin the selected address while verifying the host's TLS
  certificate, reject redirects, and bound response size/time. Owner media
  diagnostics accept only the existing canonical Cloudinary publishing URL format.
- Browser mutations now require a matching origin when supplied, reject cross-site
  fetches, and require origin/referer evidence for cookie-authenticated writes.
  Cookie-free service credentials and GET OAuth callbacks retain their existing
  authentication/state checks. Request bodies are bounded before multipart parsing.
- Uploaded images are decoded, pixel/byte/frame limited and re-encoded under random
  filenames. Metadata and appended payloads are removed. Server storage paths are
  no longer exposed by the media API. Document imports are bounded and fail clearly.
- HTML output escapes creator/provider strings in legacy account, automation,
  library and onboarding views. Browser responses add no-sniff, frame denial,
  restrictive object/base/frame policies and no-store for account/API responses.
- Signed sessions must contain expiry and subject. Production API documentation
  is disabled; diagnostic routes require the owner. Legacy paid GET debugging is retired.
- Public contact/waitlist forms have atomic PostgreSQL per-identity/global budgets,
  bounded fields and neutral CSV values. Signup responses do not reveal membership.
- Nested logging fields and embedded credential patterns are redacted. Generic
  HTTP 500 responses do not disclose SQL/provider exception details.
- Known-vulnerable runtime dependencies were updated, unused python-jose removed,
  direct runtime dependencies pinned and installed-runtime advisory auditing added
  to CI. This scan does not certify the operating system or obsolete vendored
  development environments present in repository history.

## Instagram token rollout

The TEXT column remains unchanged. New nonempty tokens are encrypted with
Fernet authenticated encryption and a purpose-specific key derived from the
existing application secret. Legacy plaintext rows remain readable during rollout.
Empty disconnected values retain existing SQL/filter semantics. Provider calls
receive the original token after decryption; no API response exposes it.

1. Deploy this compatible reader/writer and verify startup/connections.
2. Verify a fresh durable database backup exists.
3. Run `python scripts/encrypt_instagram_tokens.py` for counts only.
4. Run with `--apply --backup-id <verified-backup-identifier>` in the app service.
5. Confirm remaining_legacy is zero and recheck connected-account flows.

The migration locks records, verifies encryption round trips, preserves account
IDs/state/posts, and rolls back atomically on any invalid encrypted credential.
Repeated execution is safe. After applying, the minimum rollback version is this
compatible release: older releases cannot read encrypted credentials. Preserve the
application signing secret securely with recovery configuration. Rotating it also
requires a connection-credential migration or reconnection (Pinterest already uses
that secret). Database encryption does not protect against compromise of the app
runtime itself. Historical backups still contain their original credential data.

## Verification and limits

Local isolated backend and browser tests, Python 3.11 syntax validation, dependency
advisory scan and diff review are run before pushing. GitHub's production-container
checks exercise actual PostgreSQL, startup, concurrent limits, publishing
idempotency, backup restoration, token migration and rollback before merge.
Production health, owner access, account isolation at unauthenticated boundaries,
headers and the image-download flow must be checked after deployment.

No penetration/load testing against third-party providers or live creator accounts
is performed. No claim of prior exploitation or its absence follows from these
code findings. Follow-up security work should include owner MFA/re-authentication,
a full inline-script CSP migration, edge abuse controls, infrastructure/account
access review, secret rotation/recovery procedures, historical secret scanning and
an independent security assessment before a broad public launch. Keep additional
social integrations behind their own scoped OAuth and publishing tests.
