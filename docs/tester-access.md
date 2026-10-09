# Private creator tester access

Open `/admin/testers` while signed in as a platform superadmin. This is a deliberately small pilot, not open registration. Creating an invitation does not send email. Send its private link to the specified creator yourself. Do not put it in a public chat or analytics system.

## Behavior

- One invitation per normalized email. Only new accounts can join; existing accounts are never promoted, reset, or reactivated by an invitation.
- Defaults: link valid for 7 days, creator access for 30 days from redemption. Admin UI offers 1/7/14-day links and 14/30/60-day access; API bounds are 1–30 and 1–90 respectively.
- New users receive one private workspace and ordinary owner membership, never platform admin access. Password, Google signup and invitations share `provision_creator`.
- Pilot access uses the current workspace/global AI budgets, concurrency and manual review guards. The join screen reads configured daily call limits. Limits count attempted provider calls, not guaranteed completed images, and reset at 00:00 UTC.
- Tokens contain 256 bits of randomness. Only SHA-256 hashes are stored. The link fragment is read once into page memory and removed from browser history before API calls. API calls use POST bodies, not token URLs. Pages have no third-party assets, are not cacheable, and prohibit referrers/framing. Validation errors cannot echo secrets.
- Links are bearer credentials bound to an email string; this does **not** independently verify email ownership. Trusted private delivery by the admin is required. Signup email verification/delivery automation is not included. If exposed or lost, revoke an unused link and issue a replacement.
- Single-use redemption holds a PostgreSQL row lock. Creating the account, workspace, membership and consuming the invitation is one transaction. Concurrent redemption can create only one workspace. Failed transactions leave no partial account.
- Expiry denies password/Google/current-session access, workspace API keys, paid generation reservations and the shared account guard used by scheduling/publishing/automation execution. Existing non-pilot accounts have NULL bounds and are unchanged.
- Revocation additionally deactivates the user, marks the workspace revoked, disables automations and moves `scheduled` posts to `drafted` with schedule cleared. Drafts/media/source records and published/unknown/in-progress statuses are retained. Already dispatched provider work or publication may finish; it cannot be recalled.
- Existing sessions become unusable on the next authenticated request. Revocation is terminal in this first pilot interface; no automatic reactivation, renewal, billing or deletion. Expiry leaves scheduled records intact but unable to run. The latest 200 invitation records are listed.

## Deployment and rollback

Apply `scripts/migrate_tester_access.py` with an explicit PostgreSQL `DATABASE_URL` before deploying. It adds one invitation table and three nullable timestamp columns. No existing rows are updated; repeated execution is safe. Startup schema verification remains enabled. Record existing-table digests excluding new nullable fields and compare after migration.

An older app ignores pilot expiry. Before rollback, revoke all issued access and pause the pilot; do not drop the new schema or erase audit records. Application rollback alone is not an access-control rollback plan.

## Verification and launch boundary

`tests/postgres/test_tester_access.py` covers real PostgreSQL transactions, concurrent issuance/redemption, session/RBAC/key guards, background boundaries, expiry, revocation, retained data and repeatable migration. `tests/ui/tester_access.test.cjs` covers duplicate submission, failures, secret handling and recovery. The browser fixture uses a disposable local PostgreSQL database and synthetic accounts; it is not a production signup or human usability study.

Keep public signup closed. Start with a personally invited small group after operational launch blockers are resolved. Creator review, qualified source review and physical iPhone/Android testing are still required; automated checks cannot replace them.

## Website versus mobile app

Keep the responsive website for the pilot. It supports quick invitation links and immediate fixes while preserving one backend and interface. Evaluate an installable PWA after real-device checks; do not cache private invitation responses or authenticated API responses in a future service worker. iOS/Android installation steps and capabilities differ, and some in-app browsers do not support installation: https://web.dev/learn/pwa/installation

Consider native apps only when pilot evidence shows meaningful gaps in sharing/export, device integrations or notifications. A thin website wrapper can face App Store minimum-functionality review: https://developer.apple.com/app-store/review/guidelines/#minimum-functionality

No native app or PWA/service worker is introduced in this change. Restore-drill credentials and external alert delivery remain separate operational checks; inviting testers does not certify public-launch readiness.
