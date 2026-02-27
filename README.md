# Social Media LLM - SaaS

> **NOTICE**: This repository contains proprietary software owned by Mohammed Hassan. It is shared strictly for academic grading purposes. Unauthorized copying, modification, distribution, or use is prohibited.

## Disaster Recovery Plan

This platform is built with production reliability mechanisms to quickly recover from regional or system-wide disruptions. 

### How to restore from backup
1. Obtain the latest `.sql.gz` backup file either from the local `/backups/` directory or your configured S3 bucket (`s3://<BUCKET_NAME>/database_backups/`).
2. Decompress the file: `gunzip backup_YYYY_MM_DD_HHMM.sql.gz`
3. Restore the SQL dump to your new PostgreSQL instance using `psql`:
   `psql <NEW_DATABASE_URL> -f backup_YYYY_MM_DD_HHMM.sql`
   (Note: Ensure your new database is empty, as the dump contains the entire schema definitions).

### How to switch DATABASE_URL to secondary
The backend features an automatic connection retry loop with exponential backoff on startup.
If `DATABASE_URL` (the primary database) fails after 3 sequential connection attempts, the system will seamlessly swap the connection pool to the `SECONDARY_DATABASE_URL` environment variable assuming it is configured. 

To permanently cutover to a secondary database manually:
1. Replace `DATABASE_URL` in your `.env` or Railway Variables with the connection string for your read replica or fallback database.
2. Restart the deployment.

### How to redeploy in new region
If the `PRIMARY_REGION` cluster is inaccessible due to a provider outage:
1. Verify you have the most recent encrypted Environment Config snapshot generated. 
2. Spin up a new Railway project or Docker host in the secondary region.
3. Decrypt your environment variables locally using the `ENV_BACKUP_KEY` and inject them into the new host deployment's variables.
4. Set `DATABASE_URL` to your fallback database. Alternatively, provision a fresh PostgreSQL database in the new region and restore the latest S3 SQL.gz backup to it.

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
