# Deploy the dashboard to GitHub Pages (Neon-only)

The public workflow uses **only Neon PostgreSQL, GitHub Actions and GitHub Pages**.
It stores exact response and metadata bytes in a private PostgreSQL table, imports
structured records, verifies current checkpoints and SQL analytics, and publishes
`data/dashboard.json`. The S3 adapter is retained only for optional legacy use.

## 1. Prepare the repository and database

Keep Render available. In **Settings → Pages**, choose **GitHub Actions** as the
source; allow the `github-pages` environment to deploy from the default branch.
Leave `ENABLE_SYNC` unset or false until manual publication is verified.

Create an isolated Neon branch from the existing sports tracker database. Confirm
the database and branch identity in the Neon SQL Editor. As owner, apply the
initial schema (001) only for an empty test database, then review/apply
`sql/postgresql/002_roles.sql` followed by
`sql/postgresql/003_raw_snapshot_archive.sql`. The third migration is additive,
creates `public.raw_snapshot_blobs`, and grants SELECT/INSERT to sync and migrator
groups only. It never replaces existing fixture records or snapshot identities.

Verify as owner:

```sql
SELECT current_database(), current_user;
SELECT count(*) AS fixtures FROM public.matches;
SELECT
  pg_has_role('sports_tracker_sync_login', 'sports_tracker_sync', 'MEMBER') AS member,
  has_table_privilege('sports_tracker_sync_login', 'public.raw_snapshot_blobs', 'SELECT') AS can_read,
  has_table_privilege('sports_tracker_sync_login', 'public.raw_snapshot_blobs', 'INSERT') AS can_insert,
  has_table_privilege('sports_tracker_sync_login', 'public.raw_snapshot_blobs', 'UPDATE') AS can_update,
  has_table_privilege('sports_tracker_sync_login', 'public.raw_snapshot_blobs', 'DELETE') AS can_delete,
  has_table_privilege('sports_tracker_api_login', 'public.raw_snapshot_blobs', 'SELECT') AS api_can_read,
  has_column_privilege('sports_tracker_sync_login', 'public.sync_leases',
                       'expires_at_utc', 'UPDATE') AS can_renew_lease;
```

Expected: member/read/insert/renew true; update/delete/API read false. The table
stores both original files as BYTEA and checks both SHA-256 values. The archive
has no foreign key to the provenance table because rejected and unreferenced
captures must also survive. No raw bytes are published.

## 2. Preserve historical source evidence before synchronization

Use the existing local WSL project and virtual environment, with SQL Server
credentials and the raw directory available. Pull the reviewed changes first.
Set `POSTGRES_DATABASE_URL` privately to the **isolated branch's migrator or
owner** direct URL (not the sync login), use verified TLS/channel binding, and
leave the existing local SQL Server settings intact. Do not paste credentials into
chat or commit them. Install the reviewed project dependencies if needed.

```bash
python scripts/audit_snapshots.py --root data/raw
python scripts/audit_snapshots.py --root data/raw --sqlserver
python scripts/migrate_snapshots_to_object_storage.py --postgresql
```

The old script name is retained for backward compatibility; `--postgresql`
selects the new archive and never loads object-storage credentials. The preview
checks local files, SQL Server source references, Neon IDs/hashes/locators and
the archive's existing contents. It also inventories unreferenced valid local
captures without manufacturing database history for them. Stop on any corruption,
missing file, unexpected target row, conflicting bytes or size-guard failure.

After reviewing the preview, back up existing evidence and run on the isolated branch:

```bash
python scripts/migrate_snapshots_to_object_storage.py --postgresql --apply
```

The archive writes and source locator updates commit together; a failure rolls
back both. Keep all original local files. Verify the counts and hashes:

```sql
SELECT count(*) AS archived_captures,
       sum(octet_length(response_bytes) + octet_length(metadata_bytes)) AS raw_bytes
FROM public.raw_snapshot_blobs;

SELECT count(*) AS missing_or_mismatched_references
FROM public.source_snapshots s
LEFT JOIN public.raw_snapshot_blobs b ON b.snapshot_key = s.local_directory
WHERE b.snapshot_key IS NULL OR b.response_sha256 <> s.sha256
   OR octet_length(b.response_bytes) <> s.byte_count
   OR encode(sha256(b.metadata_bytes), 'hex') <> b.metadata_sha256;
```

Expected missing/mismatched count: zero. Once the isolated test and role
checks pass, repeat migration 002/003, audit preview and apply against the verified
production Neon branch with the correct migration credentials. Existing Render
read-only access remains available. Do not reset or truncate any database.
This migration intentionally rejects extra target snapshot IDs; if production has
already ingested new cloud-only captures or migrated to S3, stop for reconciliation.

## 3. Configure the GitHub repository secret

Under **Settings → Secrets and variables → Actions → Secrets**, create:

| Secret | Value |
| --- | --- |
| POSTGRES_SYNC_DATABASE_URL | Direct production Neon URL for the dedicated synchronization login |

The workflow configures `verify-full` TLS and channel binding. It does not need
S3 credentials. Keep `ENABLE_SYNC` unset or false.

## 4. Manual deployment and validation

In **Actions → Synchronize OpenLigaDB and deploy Pages → Run workflow**, select
the default branch and set `activate=true` only after the preceding prerequisites
pass. Verify both synchronization and deployment jobs. The deployment environment
provides the public URL. No workflow edits, daily commits, or local servers are
needed to serve the public dashboard.

Check all four sections, filters, fixture details, charts, change history and
the last successful timestamp. In browser network tools confirm the relative
`data/dashboard.json` request and no FastAPI requests. The artifact allowlist is
`index.html`, `assets/app.js`, `assets/styles.css`, `data/dashboard.json`, and
`.nojekyll`. No secrets, raw bytes, local notes or operational files may appear.

Compare fixture counts, matchday totals, goals and observed changes against Neon.
Repeat a manual pass with the same source state; unchanged fixtures must not
create false change events. On an isolated target verify that a failed archive,
source validation or reconciliation cannot publish a new artifact.

## 5. Enable and maintain daily synchronization

Set repository Actions variable `ENABLE_SYNC=true` only after a successful
manual deployment. The daily schedule remains 02:17 UTC (08:17 Bangladesh time).
Verify the first scheduled run before updating the public link and retiring Render.
GitHub schedules can be delayed or disabled after inactivity. Daily polling can
miss intermediate source changes. The configured scope remains the 2026/27 UCL
league phase.

The runtime prints database size and stops before an estimated 400 MiB database
size, allowing a conservative margin for a small cloud database. This is an
application guard, **not a Neon billing guarantee**: provider quota, WAL, physical
storage and compute may differ. Monitor Neon usage and archive growth. Never
silently delete evidence; decide on additional storage or an explicitly reviewed
archive strategy if needed.

An error blocks new publication and keeps the last successful Pages artifact.
Earlier valid matchdays may already be committed. Inspect the failed job, fix
the cause, and dispatch a new pass. Unset ENABLE_SYNC to pause automation.
