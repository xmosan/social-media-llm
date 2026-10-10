# Database credential rotation

## 2026-10-10 production rotation

An active PostgreSQL credential was embedded in two legacy maintenance scripts.
The seed script was fixed in PR 41. The topic-library schema utility now also
requires `DATABASE_URL` from its environment. Neither script should be run as an
application startup task. Historical copies contain a retired password; do not
restore that password during rollback.

The owner authorized rotation. The operation changed the existing database role's
password, with no table, role-privilege, schema, account-access or content changes.
A new random credential was generated in restricted operator storage. A
client-generated SCRAM verifier was sent over TLS to PostgreSQL, rather than
putting a plaintext password in an SQL command or command-line argument.

Railway's database password settings and derived connection URLs were updated
without deploying first. Sabeel's `DATABASE_URL` now references
`${{Postgres.DATABASE_URL}}`, using the private database connection. After the
database accepted the new password, the local maintenance environment was updated
and Sabeel was redeployed. Postgres itself did not require a restart.

Verification recorded:

- A fresh connection succeeds with the replacement password and requires TLS.
- A fresh connection using the retired password fails authentication.
- No pre-rotation database client sessions remain after the app redeployment.
- Counts remain 14 users, 14 workspaces, 1,409 posts, 6,249 content items,
  127 media assets and 3 tester invitations. The rotation performed no table writes.
- Three user records remain active (two owner records and one invited tester);
  eleven legacy records remain disabled. The two pending invitations remain pending.
- `/health` and `/ready` return HTTP 200; the owner console reads production data.
- The code tree contains no copies of the retired password. Git history and other
  historical checkouts were not rewritten, and the retired password cannot log in.

The successful cutover deployment is `d741eb6b-5e64-4e44-a12e-3b9bedde5deb`.
The subsequent source cleanup has its own normal CI and deployment verification.
No new production-data restore drill or publication was performed for this rotation.

## Future maintenance

Prefer Railway's supported database credential regeneration where available.
Changing only an environment variable does not change an existing PostgreSQL role
password; changing only the role leaves dependent services with stale credentials.
Coordinate both sides, then redeploy every dependent service and check fresh
connections, background services, and old-password rejection.

Before changing credentials, inventory services and local maintenance consumers,
review any pending deployments, verify the current connection, and record a
recovery path. Keep replacement material outside Git with restricted permissions.
If a cutover fails, reconcile the settings with the newly accepted credential;
do not return to a password that was exposed. Never put secrets in reports,
application logs, shell history, screenshots or commit messages.

Reference: [Railway database connection settings](https://docs.railway.com/databases/database-view)
and [PostgreSQL 17 ALTER ROLE](https://www.postgresql.org/docs/17/sql-alterrole.html).
