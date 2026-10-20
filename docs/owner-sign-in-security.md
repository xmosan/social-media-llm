# Owner sign-in protection

The configured, active platform owner must complete an authenticator challenge
after a password or verified Google sign-in. Normal creator sign-in is unchanged.
This is TOTP-based MFA, not phishing-resistant passkey authentication.

## Behavior

- The primary sign-in issues a five-minute, one-use challenge cookie. Its JWT
  audience prevents use as an application session. Starting another sign-in
  replaces the pending challenge.
- First-time setup requires a fresh primary sign-in. An existing session alone
  cannot enroll an authenticator. Existing owner sessions remain usable until
  enrollment is completed; deployment alone does not mean MFA is activated.
- Enrollment revokes existing sessions. Enrolled owners cannot use ordinary
  password-only JWTs, including old sessions or tokens from another login path.
- Owner sessions expire within eight hours. Administrative writes and backup
  downloads require second-factor verification within fifteen minutes.
- PostgreSQL row locks protect challenge consumption, TOTP replay state, recovery
  consumption, code replacement and session revocation. Attempt budgets persist
  across processes. Provider/storage errors fail closed.
- Ten random 128-bit recovery codes are shown once. Only keyed hashes are stored.
  A recovery code still requires primary sign-in, is consumed once and revokes
  other sessions. Replacing recovery codes requires a new authenticator code.
- Authenticator secrets are encrypted with a purpose-specific key derived from
  `SECRET_KEY`. No code or setup key is logged or stored in browser storage. The
  owner-security page has a strict, self-hosted Content Security Policy.

## Deployment

1. Verify a current durable backup. Test restoration separately from production.
2. Use the separate database administrator connection to apply
   `scripts/migrate_owner_mfa.py`. It adds only nullable `users.owner_mfa JSON`,
   with bounded lock/statement timeouts. The restricted runtime role cannot DDL.
3. Deploy after security, browser, PostgreSQL, startup and dependency checks pass.
4. Check health/readiness, logged-out boundaries and existing creator/owner flows.
5. The owner signs in afresh, enrolls their authenticator themselves and saves
   recovery codes outside Sabeel. Confirm a new sign-in requires the second factor.

Keep the nullable column on rollback. After enrollment, **never roll back to a
release that ignores owner MFA**; use a compatible fix or suspend owner access.
Do not insert fabricated enabled state to make a health check pass.

## Recovery

Use a saved recovery code after normal sign-in if the authenticator is temporarily
unavailable. Other sessions are revoked. The browser does not offer a way to remove
the factor, replace its secret or substitute an email link.

For a permanently lost authenticator, a separately authenticated Railway/database
administrator must verify the owner's identity out of band before resetting MFA.
Do not accept a support message or access to the Sabeel inbox alone as identity
proof. Verify the intended owner ID and configured email, take a fresh backup,
and record the authorized reason without credentials. In one administrator
transaction, lock that exact owner row, increment its `session_version`, clear
`owner_mfa`, and commit. This revokes all sessions and requires fresh primary
sign-in and enrollment; it is not a routine troubleshooting step. Verify enrollment
and a subsequent new sign-in before closing the incident.

Preserve the application `SECRET_KEY` in the owner's protected recovery material
as well as Railway. A database dump alone cannot recover encrypted TOTP,
Instagram or Pinterest credentials without it. Do not rotate this key casually:
use a deliberate decrypt/re-encrypt migration with the old and new keys, revoke
sessions/challenges, replace keyed recovery codes and verify provider connections.
If the runtime/key is compromised, disconnect or rotate affected provider tokens;
encryption at rest does not protect against a compromised running application.

## Evidence and limitations

Regression tests cover password and Google login, expired/replaced challenges,
wrong and replayed codes, concurrent requests, recovery consumption, session
revocation, attempt limits, CSRF, migration repeatability, ordinary creator login,
timeouts and one-time recovery display. Real-owner activation is a separate
user-performed acceptance check, not something inferred from tests.

The legacy application's inline-script CSP migration, perimeter DDoS controls,
operator-account MFA confirmation and an independent security assessment remain
separate work. Do not describe this change as a comprehensive security certification.

References: [OWASP MFA guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
and [PyOTP security guidance](https://pyauth.github.io/pyotp/).
