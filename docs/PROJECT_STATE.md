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
- PostgreSQL deployment SQL uses explicit `public`-qualified grants: the API role is
  read-only on public data tables, the sync role has required importer DML plus lease
  replacement only, and the migrator is separate. No role credentials are stored here.
- Migration utilities normalize Psycopg mapping rows, reject unsafe schema identifiers,
  compare complete source/target key sets, report target counts before apply, and roll
  back target transactions on failure. Raw-object database rollback cannot undo an object
  upload; safe orphan review remains an owner gate.
- `scripts/audit_snapshots.py` and `sports_tracker.snapshot_audit` provide an offline,
  deterministic local inventory. Optional `--sqlserver` reconciliation is explicit and
  read-only; it distinguishes valid, corrupt, missing-referenced, path/hash-mismatch,
  and unreferenced-local evidence without deduplicating repeated retrievals.
- Snapshot object uploads now clean up every object created by the failed attempt while
  preserving pre-existing objects; migration preview/apply rejects unsafe local-path
  relationships, target-only snapshot rows, and target hash/size/locator mismatches.
- New offline regression coverage for these boundaries is written but has not been run.

## Owner-verified evidence

The latest owner-run verification reported:

- Offline verification: **209 passed, 2 deselected**, with one non-blocking
  Starlette deprecation warning.
- Ruff lint: **PASS**.
- Ruff formatting: **PASS**, 78 files.
- Git whitespace validation: **PASS**.
- Local snapshot audit: **PASS**, 17 valid pairs and 4 duplicate response-hash groups.
- SQL Server snapshot reconciliation: **PASS**; 14 database-referenced snapshots,
  0 missing referenced snapshots, 0 corrupt referenced snapshots, and 3
  unreferenced local capture directories.
- Historical Neon parity: **12/12 tables MATCH**.

The three unreferenced local capture directories are retained evidence and must be
independently accounted for. A database-driven object-storage migration must not be
assumed to include them. Object storage and deployment remain **NOT YET VERIFIED**.

## Evidence boundary

No Python, tests, Ruff, SQL, HTTP/API, synchronization, migration, cloud provisioning,
Render startup, or Git operation was run for this implementation. Owner-reported local
SQL Server evidence remains historical evidence only.

## Blockers before cloud use

1. Verify the selected private object-storage endpoint, bucket policy, credentials,
   replay, hash checks, and orphan cleanup in a disposable Neon target.
2. Apply and review `sql/postgresql/001_initial_schema.sql` and `002_roles.sql`, then
   verify the actual role/table/sequence privileges.
3. Run migration preview, stop on mismatch or target-only rows, and apply only after parity review.
4. Run raw snapshot reconciliation and review any durable object orphan before retrying.
5. Create separate least-privilege Neon login roles and secret-scoped GitHub/Render settings.
6. Execute the staged offline, SQL, cloud, and browser checks in the runbook.

The local audit must run before the object-storage migration. `17` local pairs versus
`14` database rows is not itself evidence that three files are disposable; review the
explicit reconciliation categories and preserve all distinct retrievals.

## Next owner action

Use the manual commands in [`MANUAL_RUNBOOK.md`](MANUAL_RUNBOOK.md), beginning with the
offline lint/test checks and PostgreSQL schema review. Stop if a prerequisite fails.
## Current deployment-readiness handoff — 2026-11-12

- PostgreSQL sync-role lease access now includes `SELECT`, `INSERT`, and `DELETE` on `public.sync_leases`; the role remains `NOLOGIN` and no broad table grants were added.
- Added offline parity-report and PostgreSQL preflight utilities. They are read-only by default and redact credentials; parity reports distinguish `MATCH`, `MISMATCH`, `MISSING`, `ERROR`, and `NOT CHECKED`.
- Added a guarded, opt-in Neon integration-test foundation, a lease-renewal regression test, FastAPI lifespan coverage, and an offline CI workflow. These checks are written but **NOT RUN** in this handoff.
- Existing SQL Server behavior, snapshots, credentials, and database records are unchanged. Applying PostgreSQL schema/roles, migration preview, parity, preflight, cloud storage, and integration checks remain owner-executed blockers.
