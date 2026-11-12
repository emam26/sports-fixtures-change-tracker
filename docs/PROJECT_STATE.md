# Current Project State

Updated 2026-11-12. This is the compact handoff for future agents; detailed design and
operational procedures remain in the linked documents.

## Implemented foundations

- SQL Server remains the default local backend and its schema/import classes are unchanged.
- PostgreSQL configuration, psycopg connection handling, a separate PostgreSQL schema,
  import store, API repository, checkpoint reader, database lease, and migration utility
  are present. See [`POSTGRES_DEPLOYMENT_FEASIBILITY.md`](POSTGRES_DEPLOYMENT_FEASIBILITY.md).
- Render and GitHub Actions deployment descriptors are present, with public-read-only
  startup and a twice-hourly bounded synchronization workflow. The workflow is gated
  by `ENABLE_SYNC=true` for schedules or `activate=true` for manual dispatch.
- Snapshot storage has an immutable local adapter and a private S3-compatible adapter.
  Cloud synchronization uploads and verifies response/metadata objects before import;
  Render/GitHub ephemeral disks are staging only. Object credentials remain external.

## Evidence boundary

No Python, tests, Ruff, SQL, HTTP/API, synchronization, migration, cloud provisioning,
Render startup, or Git operation was run for this implementation. Owner-reported local
SQL Server evidence remains historical evidence only.

## Blockers before cloud use

1. Verify the selected private object-storage endpoint, bucket policy, credentials,
   replay, hash checks, and orphan cleanup in a disposable Neon target.
2. Apply and review `sql/postgresql/001_initial_schema.sql` and `002_roles.sql`.
3. Run migration preview, raw snapshot reconciliation, then apply only after parity review.
4. Create separate least-privilege Neon login roles and secret-scoped GitHub/Render settings.
5. Execute the staged offline, SQL, cloud, and browser checks in the runbook.

## Next owner action

Use the manual commands in [`MANUAL_RUNBOOK.md`](MANUAL_RUNBOOK.md), beginning with the
offline lint/test checks and PostgreSQL schema review. Stop if a prerequisite fails.
