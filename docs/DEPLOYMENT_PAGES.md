# Deploy the dashboard to GitHub Pages

The Pages workflow synchronizes OpenLigaDB to Neon PostgreSQL with the existing
Python importer. The public site reads `data/dashboard.json` over HTTPS from the
same project path as its frontend. The Actions artifact contains the static site.

## Repository and data setup

1. Keep the Render service available throughout rollout. In the repository’s
   **Settings → Pages**, choose **GitHub Actions** as the source. Confirm that
   Actions can use the workflow’s official actions and that the `github-pages`
   environment allows deployment from the default branch. For unattended deployment,
   review any environment approval rules that would pause each scheduled run.
2. In an isolated Neon branch first, verify the existing PostgreSQL schema and apply
   [the role grants](../sql/postgresql/002_roles.sql) as an owner. Apply
   [the initial schema](../sql/postgresql/001_initial_schema.sql) if the database is
   empty. Reapply the role script for an existing deployment so the sync role can
   renew `sync_leases.expires_at_utc`. Use a LOGIN with membership in
   `sports_tracker_sync`. Use a direct Neon endpoint with TLS certificate
   verification and channel binding.
3. Prepare a private S3-compatible bucket and credentials for the
   `sports-fixtures/raw` prefix. Verify writes, reads and the existing cleanup
   permission for incomplete new pairs. Preserve historical provenance using the
   [snapshot audit and migration procedures](MANUAL_RUNBOOK.md#138-historical-raw-snapshot-audit-and-object-storage-gate).
   The database-driven migration covers referenced snapshots. Independently inventory
   and archive unreferenced historical captures you want to preserve. Keep local
   snapshots private and available for reconciliation.
4. In **Settings → Secrets and variables → Actions → Secrets**, configure the
   following repository secrets. Use the Actions interface or a secure CLI
   credential flow. Keep their values out of Git, chat, and workflow output.

   | Secret | Value |
   | --- | --- |
   | `POSTGRES_SYNC_DATABASE_URL` | Direct Neon URL for the synchronization login |
   | `OBJECT_STORAGE_ENDPOINT_URL` | HTTPS endpoint for the private object store |
   | `OBJECT_STORAGE_BUCKET` | Private bucket name |
   | `OBJECT_STORAGE_REGION` | Region accepted by the endpoint |
   | `OBJECT_STORAGE_ACCESS_KEY_ID` | Credential for the archive prefix |
   | `OBJECT_STORAGE_SECRET_ACCESS_KEY` | Corresponding secret key |

5. Leave the Actions repository variable `ENABLE_SYNC` unset during initial rollout.
   Once the workflow is on the default branch, open **Actions → Synchronize
   OpenLigaDB and deploy Pages → Run workflow**, select the default branch, and set
   `activate=true`. Verify that synchronization, artifact upload and deployment
   succeed. Use the deployment job’s environment URL as the public URL.

## Verify the first deployment

- In a browser, open the URL and all four dashboard sections. Check fixture totals,
  kickoff ordering, matchday and status filters, team search, fixture details, goals
  and nullable scores. Check Insights charts, team detail and ranking, and Change
  Intelligence pagination, expandable entries and provenance where records exist.
- Confirm that the browser requests its own relative `data/dashboard.json` and
  frontend assets, with zero FastAPI data requests. The file preview and artifact
  inventory should show no `.env`, raw responses, object locators, operational
  endpoints, SQL backup, local notes, or workflow logs.
- Verify the UI’s **Last successful sync** matches `synchronizedAt` in the JSON.
  Compare fixture, completed and upcoming counts, goal rows, field-level changes and
  distinct changed fixtures with SQL for the scoped season. For details and trend
  calculations verify finished scores, per-matchday totals and team statistics.
  The export itself checks SQL counts and verifies the archived source content
  against each committed checkpoint before writing the JSON.
- Dispatch the same source state again and compare domain counts, provider fixture
  IDs and change-event counts. Repeated retrievals can add legitimate snapshots and
  import records. Use an isolated target to simulate a broken source or snapshot;
  verify the failure cannot upload or deploy an artifact.
- Set the repository variable `ENABLE_SYNC` to `true` under **Actions → Variables**
  after one successful manual deployment. Verify the first successful scheduled run
  before changing the public link or retiring Render.

## Schedule and recovery

GitHub starts the workflow once daily at **8:17 AM Bangladesh time (02:17 UTC)**,
subject to schedule delays. Daily polling can miss intermediate OpenLigaDB changes,
including changes reversed between retrievals. The displayed timestamp describes the
published full pass. On an unchanged pass it can advance even when committed
matchday checkpoint timestamps are older. GitHub can disable scheduled workflows in
public repositories after 60 days without repository activity. If that happens,
re-enable this workflow in Actions and dispatch a new run.
[GitHub schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

A failed matchday, archival read, or reconciliation blocks artifact upload and
leaves the previous successful Pages deployment active. Earlier matchdays may have
committed valid work to Neon. Inspect the failed job and private SQL records, then
dispatch again after fixing the issue. A deployment-only failure can be retried
while the validated artifact is available. The workflow serializes scheduled and
manual runs and has no permission to commit to the repository.

During rollout, use Render as the known fallback. To pause daily synchronization,
unset `ENABLE_SYNC`. To recover a previous application version, revert the affected
code on the default branch and dispatch a fresh validated deployment. Keep committed
database history and private snapshots for replay.
