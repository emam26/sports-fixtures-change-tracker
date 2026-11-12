# Cloud Deployment Readiness Audit

**Repository:** Sports Fixtures & Change Tracker
**Audit date:** 2026-11-10
**Target:** Render Free web service, Azure SQL Database, GitHub Actions synchronization, and GitHub source control
**Status:** Repository inspection only; no implementation, deployment, migration, or operational execution was performed.

**Current decision context:** This document remains the historical Azure SQL networking
assessment. The selected replacement architecture is Render + Neon PostgreSQL/private
object storage + GitHub Actions; see [`POSTGRES_DEPLOYMENT_FEASIBILITY.md`](POSTGRES_DEPLOYMENT_FEASIBILITY.md)
for the current implementation and verification gates.

## Executive recommendation

**Immediate public deployment: NO-GO.**

The FastAPI application can serve the existing dashboard from one web service, and the SQL schema uses features that are generally available in Azure SQL Database. The repository is not yet ready for public exposure, however. Disabling the local-only guard would expose internal operational routes without an equivalent public authorization boundary. Raw snapshots and logs are local-filesystem artifacts, the ODBC system dependency is not packaged, and the synchronization lock does not coordinate separate GitHub runners.

**Conditional pre-production GO:** possible after the P0 blockers below are implemented and manually verified against a non-production Azure SQL target and a private cloud deployment.

This audit does not claim that Render, Azure SQL Free, GitHub Actions scheduling, networking, or current free-tier allowances satisfy the target architecture. Those provider-specific points require current verification against official documentation and the actual account and region.

## Evidence boundary

### Confirmed by source inspection

- pyproject.toml declares Python >=3.11, FastAPI, Uvicorn, HTTPX, Pydantic, pyodbc 5.3.0, and python-dotenv.
- setuptools package-data includes the dashboard HTML, CSS, and JavaScript.
- src/sports_tracker/api/app.py creates FastAPI, serves the dashboard at /, mounts /assets, and registers the API routes.
- scripts/run_api.py deliberately permits loopback hosts only and defaults to port 8000.
- src/sports_tracker/runtime.py and database.py open SQL Server through ODBC Driver 18 using validated environment settings and autocommit=False.
- openligadb.py, snapshots.py, ingestion.py, and synchronization.py implement bounded retrieval, immutable local snapshots, typed validation, transactional import, checkpoints, retries, and a local process lock.
- sql/001_initial_schema.sql creates twelve dbo tables and indexes, but does not create a database, login, contained user, firewall rule, role, grant, backup, or cloud storage object.
- There is no Dockerfile, .dockerignore, render.yaml, GitHub Actions workflow, cloud storage adapter, or distributed database lock in the inspected checkout.
- The public dashboard uses same-origin relative API paths and no longer exposes the operations monitor in its visible UI. Operational read routes remain registered in the backend.
- API_LOCAL_ONLY defaults to yes; note writes default to disabled. The local-only middleware is the current broad access boundary.

### Supplied owner evidence, not re-executed

The owner has reported a local SQL Server state of 144 unique league-phase fixtures, 72 finished fixtures, 72 unfinished fixtures, 143 stored result records, 291 stored goal-event records, and 936 field-level change records. The owner also reported successful local API/database checks and an earlier automated result of 129 passing tests with one SQL Server test deselected and Ruff lint/format checks passing.

These values are not cloud verification, were not re-queried here, and do not prove that the current working tree has passed its latest checks. Current documentation is internally inconsistent: docs/ARCHITECTURE.md and docs/SOURCE_NOTES.md still contain earlier Matchday 3/4 or NOT RUN milestones, while newer owner-supplied evidence describes all eight configured league-phase matchdays. Reconcile this before migration or a current-coverage claim.

### Missing project documentation

AGENTS.md requires docs/PROJECT_ROADMAP.md, but that file is absent from the inspected checkout. This is a documentation/reproducibility gap, not a cloud runtime blocker.

## Current architecture

~~~text
OpenLigaDB
    -> OpenLigaDBClient with explicit timeout and bounded transient retries
    -> data/raw/ucl/2026/matchday-{n}/{timestamp}_{sha256}/
       response.json + metadata.json
    -> offline typed parser and source-contract validation
    -> SQLServerImportStore through one pyodbc transaction
       current fixtures/results/goals
       source/import provenance
       validation issues
       field-level match changes
       successful synchronization checkpoint
    -> FastAPI repository with parameterized SQL queries
    -> static HTML/CSS/JavaScript dashboard
~~~

| Concern | Current implementation | Cloud implication |
| --- | --- | --- |
| Python package | src/sports_tracker, installed through setuptools | Compatible with a normal Python build; runtime is not pinned beyond >=3.11 |
| Web startup | scripts/run_api.py launches Uvicorn and refuses non-loopback hosts | Not suitable unchanged as a public Render command |
| App factory | sports_tracker.api.app:create_app | Suitable for a Uvicorn factory deployment |
| Frontend | Packaged web assets served by FastAPI | Same-service serving is feasible if package-data remains included |
| Database | Per-operation pyodbc connections, autocommit=False | Requires Linux ODBC Driver 18, TLS settings, timeout policy, and capacity testing |
| Synchronization | One-shot CLI, local lock, local JSONL log | Needs durable job logging and a distributed lock |
| Raw snapshots | Local immutable data/raw directories | Render and GitHub runner filesystems cannot be assumed durable |
| Secrets | .env/process environment with redacted representations | Cloud secret storage is required |

## Render Free compatibility

### Feasible in principle

The application is a conventional synchronous-route ASGI service. The frontend is served by the same application, so the current same-origin design does not require CORS. The package-data declaration includes the static assets.

A future Render command would need to use the platform-assigned port and a non-loopback bind:

~~~text
uvicorn sports_tracker.api.app:create_app --factory --host 0.0.0.0 --port $PORT
~~~

This is a proposed command, not an executed or validated command. It intentionally does not use scripts/run_api.py, whose current purpose is to protect local development.

### Blockers

1. Linux ODBC is not packaged. pyodbc is only the Python binding; unixODBC and Microsoft ODBC Driver 18 must also exist in the runtime. No Dockerfile or native-build instructions provide them. A Docker deployment is the most reproducible option, subject to current Render support and limits.
2. API_LOCAL_ONLY=yes rejects non-loopback clients. Turning it off without route-level authorization would expose operational and note routes.
3. The local wrapper does not consume a dynamic port. The cloud entry point must use $PORT while retaining the loopback-safe local wrapper.
4. requires-python is a lower bound. A cloud build needs a pinned platform runtime or container image.
5. /health performs a SQL probe and returns 503 when SQL is unavailable. There is no separate liveness endpoint, so sleeping/cold-starting dependencies can look like application failure.
6. No persistent snapshot or log storage is established. Do not make the web service filesystem the source of truth.

Current Render sleep/cold-start behavior, memory and CPU limits, build limits, outbound networking, persistent-disk behavior, and egress-IP behavior require current official-documentation verification. They were NOT VERIFIED in this audit.

## Azure SQL compatibility

### Compatible or likely compatible

The schema and repository use ordinary SQL Server features:

- bigint identities, nvarchar, varchar, bit, int, smallint, and datetime2(7);
- primary/foreign keys, unique and check constraints, and nonclustered indexes;
- SYSUTCDATETIME defaults;
- COUNT_BIG, COALESCE, CASE, TOP, OUTER APPLY, parameterized predicates, OFFSET/FETCH, and aggregates;
- explicit transaction handling and autocommit=False;
- provider-ID uniqueness and provenance/change-history tables.

These are source-level findings, not an Azure SQL execution result. Compatibility level, collation, identity behavior, query plans, locking, and ODBC behavior require testing against the selected Azure SQL database.

### Migration adjustments required

sql/001_initial_schema.sql begins with USE [SportsFixturesTracker] and GO. GO is a client batch separator; a cloud migration runner must connect directly to the target database. The target database must be provisioned separately. The schema script is not a database-creation or permission-provisioning script.

sql/manual_reset_development_import_data.sql contains a CANVASIT server guard and is a development recovery script. It must never be used as a cloud migration script.

The schema has no migration-version table and only creates missing objects. It does not reconcile schema drift. Use a reviewed migration process and record a target schema fingerprint.

### Authentication and permissions

The current connection string uses SQL authentication fields, UID and PWD, with ODBC Driver 18. An Azure SQL contained user could work, but the login/user, grants, secret rotation, and firewall are not implemented here. Entra/managed-identity authentication is not implemented by the current pyodbc.connect call.

Use separate least-privilege identities:

- migration identity, used only during migration;
- synchronization identity with only importer DML/read rights;
- read-only dashboard identity;
- no migration credentials in Render or scheduled jobs after migration.

Derive the exact grants from ingestion.py, synchronization.py, and api/repository.py, then test them against a non-production target. Do not grant db_owner as a shortcut.

### TLS and connection handling

The local example uses SQL_SERVER_TRUST_CERTIFICATE=yes for local use. Cloud configuration must use Encrypt=yes and TrustServerCertificate=no with certificate validation. The current connection code has no explicit database connection timeout or cloud connection-capacity policy; both need implementation and testing.

### Transactions and concurrency

The importer coordinates current rows, changes, successful run status, and checkpoint advancement in a transaction. Failed-run provenance is attempted after rollback. This is a good local baseline but not a cloud coordination mechanism:

- RunLock is a file in data/runtime and only protects processes sharing that filesystem.
- GitHub-hosted runners do not share that file.
- GitHub Actions concurrency helps within a workflow group but is not sufficient for manual runs, retries, or other writers.
- Azure SQL needs a database-backed lease, such as a carefully scoped sp_getapplock or an expiry-based lease table.

The lock should cover the import critical section without holding a SQL transaction open during unnecessary HTTP work. Acquisition, timeout, release, and crash recovery need integration tests.

## Raw snapshots and provenance

The local snapshot writer is immutable, but its storage assumption is not cloud-safe:

- response.json and metadata.json are written below local data/raw;
- source_snapshots stores path strings, not response bytes;
- SafeJsonLogger writes rotating JSONL below local data/runtime/logs;
- Render restarts and GitHub runners must be treated as ephemeral until verified otherwise.

Use a private object-storage container, preferably Azure Blob Storage if the account and cost model permit it. Preserve exact response bytes and metadata as separate immutable objects keyed by provider, shortcut, season, matchday, UTC capture time, and SHA-256. Store a logical object key or reviewed URI in the existing path columns if it fits their limits; do not silently leave inaccessible runner-local paths.

Before implementation, decide:

1. whether import uses local staging, an object-store adapter, or both;
2. how object immutability/versioning and overwrite prevention work;
3. which identity uploads and reads objects;
4. how offline replay obtains a saved snapshot without another provider request;
5. how a failed SQL import retains its snapshot;
6. how keys fit local_directory nvarchar(750) and path columns;
7. retention, backup, deletion, access logging, and cost controls.

Do not place raw snapshots in a public GitHub repository, public blob container, or Render filesystem. GitHub artifacts may be temporary diagnostics but should not be the authoritative archive until retention and access controls are verified.

## Automated synchronization design

### Existing behavior

The current one-shot CLI:

1. loads validated source and sync settings;
2. acquires a local RunLock;
3. reads checkpoint/matchday state;
4. optionally compares provider discovery views;
5. uses the last-change signal when reliable, otherwise fetches fully;
6. preserves response bytes through the snapshot writer;
7. strictly parses the saved snapshot;
8. imports through SQL Server;
9. writes local structured JSONL events and returns non-zero for failures.

The HTTP client has explicit timeout and bounded transient retries. Keeping synchronization independent of Render is correct. It is not yet a cloud job because its lock, snapshots, and logs are local filesystem features.

### Recommended GitHub Actions shape

Add a workflow only after storage, lock, network, and security blockers are resolved:

~~~yaml
name: Synchronize OpenLigaDB

on:
  schedule:
    - cron: "17 * * * *"
  workflow_dispatch:

concurrency:
  group: sports-fixtures-synchronization
  cancel-in-progress: false

jobs:
  synchronize:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - checkout
      - install pinned Python and ODBC dependencies
      - run offline validation and bounded synchronization
      - upload only reviewed non-secret diagnostics
~~~

This is a design sketch, not a workflow file or executed job. Scheduled workflows can be delayed or skipped. The job should use the bounded synchronization entry point, not call a dashboard endpoint to trigger writes.

Inject secrets through encrypted repository/environment secrets. Fail closed when a required secret is absent. Never print environment values.

### Matchday 2 conflict policy

Strict parsing rejects conflicting result kinds by default. The manual import CLI has explicit opt-in for quarantining conflicting non-final variants; synchronization does not enable it automatically.

Scheduled runs must remain strict. If a recovery input is later added, it should be workflow_dispatch-only with explicit confirmation, visible provenance, raw snapshot preservation, validation/quarantine of every conflicting result ID/value, independent final-score validation, and a test proving scheduled runs cannot inherit the flag.

A recurring source conflict should fail safely, preserve the snapshot, record failure provenance, and alert an operator. It must not weaken validation to keep a job green.

### Freshness and failure visibility

/api/freshness is a read-only revision from the latest successful checkpoint/snapshot. It does not say that a job is running. Private monitoring should cover workflow status, snapshot hash, import status/failure phase, validation severity, checkpoint advancement, duration, retry count, stale-data age, storage errors, database connectivity, and lock contention.

The public dashboard should expose only safe freshness and generic data-load errors. It should not expose SQL errors, payloads, credentials, snapshots, or internal run diagnostics.

## Public security audit

### Route classification

| Route class | Current examples | Cloud assessment |
| --- | --- | --- |
| Dashboard/static | /, /assets/* | Publicly serveable after asset/caching review |
| Public read model | competitions, matchdays, matches, summary, freshness, insights, match detail, changes | Could be public read-only data after query/rate-limit review |
| Health/status | /health, /api/status | Define deliberate public responses |
| Operational diagnostics | /api/sync-checkpoints, /api/import-runs, /api/validation-issues | Must not be anonymous; current protection is only broad local-only middleware |
| Note reads | /api/matches/{id}/notes | Review whether notes are public |
| Note writes | POST notes, PUT notes, DELETE notes | Must remain disabled or receive real authentication |
| API documentation | /docs | Protect or disable publicly unless intentionally published |

The operational routes are not requested by the dashboard, but they remain reachable backend endpoints. Setting API_LOCAL_ONLY=no for Render removes the current network boundary for all routes. This is a critical blocker.

### Minimum security changes

1. Introduce an explicit reviewed public-read mode rather than overloading a boolean switch.
2. Enforce route-level policy: public reads only; diagnostics require private authentication or are disabled; note writes remain disabled unless authenticated.
3. Protect or disable /docs and diagnostics in public mode.
4. Keep SQL, provider, storage, and admin credentials in platform secret stores.
5. Use Encrypt=yes and TrustServerCertificate=no for Azure SQL.
6. Add request/rate limits and retain bounded query limits.
7. Configure trusted-host/proxy behavior deliberately; never trust unreviewed forwarded headers.
8. Keep same-origin CORS absent, or use a narrow allowlist; never use wildcard CORS with credentialed writes.
9. Add structured safe cloud logging with correlation/job IDs.
10. Add dependency and container vulnerability scanning.

### Error handling

The generic 500 response and credential-redacted SQL diagnostics are positive defaults. /health reports database availability and /api/status reports mode flags; review these public semantics but do not use them as a substitute for authenticated operations.

The frontend uses safe text insertion and does not contain credentials. This does not make the backend safe when local-only mode is disabled.

## Free-tier and operational feasibility

The target needs an additional durable-storage and observability decision. Azure Blob Storage is the natural candidate but may have storage, transaction, egress, or account requirements outside a free allowance.

| Area | Risk or question | Status |
| --- | --- | --- |
| Render Free | Sleep, cold starts, limits, outbound egress, persistent disk, egress IP | NOT VERIFIED |
| Azure SQL Free | Eligibility, card/subscription, quota, duration, region, backups, overage | NOT VERIFIED |
| Azure SQL network | Firewall, Render egress, GitHub runner IP variability, private endpoints | NOT VERIFIED |
| GitHub Actions | Free minutes, schedule delays, concurrency, artifact retention, secrets | NOT VERIFIED |
| Object storage | Free allowance, versioning, access policy, durability, egress, lifecycle | NOT VERIFIED |
| OpenLigaDB | 60 RPM, attribution, availability, automation policy | Project limit documented; current provider policy requires review |

Do not use a broad Azure SQL firewall rule just to accommodate dynamic hosted runners. A private network, controlled runner, or different architecture may be required, affecting the free requirement.

Even within allowances, describe the service as scheduled and best-effort, not guaranteed 24/7 or real-time. Render may sleep, scheduled Actions may be delayed, the provider may be unavailable, and Azure quotas may throttle or stop service.

## Deployment blockers ranked by severity

### P0 — before any public deployment

1. Unauthenticated operational surface if local-only mode is disabled.
2. Missing Linux ODBC and container packaging.
3. Ephemeral snapshot and log storage.
4. No distributed synchronization lock.
5. Unimplemented Azure network, TLS, least-privilege permissions, and secret rotation.
6. No migration/cutover process for the database and snapshots.
7. No scheduled workflow, concurrency policy, secret injection, or recovery gate.

### P1 — before production-ready claims

1. Pin cloud runtime and dependency/build provenance.
2. Define liveness/readiness and outage behavior.
3. Add connection timeout/capacity tests.
4. Add rate limiting, host/proxy policy, protected docs, and security scanning.
5. Add private alerts for stale checkpoints, failed imports, validation errors, and quota/network failures.
6. Reconcile evidence dates and add the missing roadmap documentation.

### P2 — operational quality

1. Durable logs and incident-replay procedure.
2. Snapshot retention and source-attribution policy.
3. Cloud smoke test and browser acceptance check after deployment.
4. Metrics for cold start, API latency, import duration, retry rate, duplication, change detection, and rollback.

## Required implementation changes by exact file

This is a plan only. No implementation changes were made during this audit.

| File or new path | Required change |
| --- | --- |
| Dockerfile (new) | Reproducible Linux image with pinned Python, unixODBC, ODBC Driver 18, non-root user, and Uvicorn factory command |
| .dockerignore (new) | Exclude .env, snapshots, logs, virtual environments, caches, and database artifacts |
| pyproject.toml | Pin or constrain the tested cloud runtime/dependency set |
| render.yaml or reviewed Render settings | Build/start commands, health behavior, and non-secret environment names |
| .github/workflows/sync.yml (new) | Conservative schedule, manual dispatch, workflow concurrency, timeout, secrets, ODBC setup, bounded sync, diagnostics |
| src/sports_tracker/config.py | Deployment/storage/timeout policy and safe public/recovery defaults |
| .env.example | Cloud-safe variable names and safe TLS defaults without credentials |
| src/sports_tracker/database.py and runtime.py | Cloud-tested driver, timeout, and controlled connection behavior |
| src/sports_tracker/api/app.py | Public-read route policy, protected diagnostics/docs, health semantics, proxy/host handling |
| src/sports_tracker/snapshots.py | Durable private object-storage adapter with exact bytes/hash and replay support |
| src/sports_tracker/ingestion.py | Reconcile provenance paths/object keys and verify cloud-identity SQL behavior |
| src/sports_tracker/synchronization.py | Database/distributed lease, safe cloud logs, explicit conflict gating |
| scripts/sync_openligadb.py | Cloud interfaces while keeping strict scheduled defaults and failure exits |
| sql/002_cloud_support.sql, only if needed | Prefer no schema change; if needed, add a separate backward-compatible migration |
| tests/ | Packaging/startup, authorization, storage, distributed lock, Azure SQL, retry, conflict, idempotency, rollback, and redaction coverage |
| docs after implementation | Record only evidence from the actual cloud target and keep local/cloud checks separate |

## Safe migration and deployment sequence

### Phase 0 — baseline

1. Reconcile the coverage/documentation conflict and record the authoritative evidence date.
2. Collect non-secret counts for all twelve tables, the latest successful checkpoint, unresolved validation issues, and snapshot inventory.
3. Verify each referenced raw snapshot and SHA-256.
4. Back up the local database and copy raw snapshots to a separate protected archive. Do not delete or reset local data.

### Phase 1 — Azure SQL

1. Provision the target database and record its identity.
2. Create least-privilege contained users through a reviewed administrative channel.
3. Configure encrypted, narrow network access; stop if it requires an unreviewed 0.0.0.0 rule.
4. Apply the schema against the target connection, not by relying on USE.
5. Run read-only compatibility and SQL integration checks on a clean target.

### Phase 2 — data and snapshots

1. Export/import while preserving provider IDs, timestamps, current rows, history, provenance, validation issues, and checkpoints.
2. Transfer raw response and metadata files to private immutable object storage.
3. Reconcile every path/object key and SHA-256 without rewriting bytes.
4. Compare counts, hashes, and checkpoints between local and Azure.
5. Replay a saved snapshot in a disposable cloud scope and verify no duplicates or false changes.

### Phase 3 — private web service

1. Build and scan the container.
2. Inject only the read-only dashboard identity and required public configuration.
3. Keep note writes disabled and diagnostics protected.
4. Start Uvicorn on $PORT and verify assets, health, and public APIs.
5. Exercise empty, stale, database-unavailable, and cold-start states without leakage.

### Phase 4 — private synchronization

1. Configure GitHub Actions secrets and storage/database identities.
2. Manually dispatch one approved matchday in strict mode.
3. Verify snapshot hash, import status, checkpoint, changes, and failure logs.
4. Repeat and verify idempotency.
5. Inject a controlled failure and verify rollback with failed-run provenance.
6. Test overlapping jobs and confirm only one enters the import critical section.

### Phase 5 — schedule

1. Confirm provider request budget and interval.
2. Enable schedule only after repeated manual success.
3. Keep conflict recovery disabled for scheduled runs; route conflicts to review.
4. Monitor stale age, failures, validation, retries, lock contention, storage, and quota.
5. Keep Render read-only; never use dashboard freshness as a scheduler trigger.

## Manual verification commands for later

All commands below are instructions only and were NOT RUN during this audit. Do not paste .env, passwords, tokens, complete connection strings, or raw payloads into reports.

### Offline repository checks

Where: WSL Bash, /mnt/f/sports-fixtures-change-tracker.

~~~bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
ruff check .
ruff format --check .
python -m pytest -q -m "not sqlserver"
~~~

Expected: no Ruff diagnostics and all selected offline tests pass. Stop at the first failure.

### Local SQL integration check

Where: WSL Bash, same directory.

~~~bash
RUN_SQLSERVER_INTEGRATION=yes python -m pytest -q -m sqlserver
~~~

Expected: opt-in checks pass against the intended isolated SQL Server test database. This is not an Azure compatibility result.

### Local API smoke test

Where: WSL Bash, same directory.

~~~bash
python scripts/run_api.py --host 127.0.0.1 --port 8000
~~~

Where: browser, http://127.0.0.1:8000. Verify assets, dashboard sections, filters, nullable scores, Insights, Change Intelligence, and generic error states. Stop if an operational endpoint is requested by the public page or a secret is displayed.

### Azure SQL read-only checks

Where: SSMS or a confirmed SQL client, connected only to the named Azure SQL target.

~~~sql
SELECT DB_NAME() AS database_name,
       CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version;

SELECT compatibility_level
FROM sys.databases
WHERE name = DB_NAME();

SELECT name
FROM sys.tables
WHERE schema_id = SCHEMA_ID(N'dbo')
ORDER BY name;

SELECT name, type_desc
FROM sys.database_principals
WHERE name IN (N'sports_tracker_dashboard', N'sports_tracker_sync');
~~~

Expected: the intended target database, recorded compatibility level, twelve expected application tables, and reviewed contained principals. Stop if identity or principals are unexpected.

### Migration reconciliation checks

Where: SSMS against Azure SQL after the separately reviewed migration.

~~~sql
SELECT 'competitions' AS table_name, COUNT_BIG(*) AS row_count FROM dbo.competitions
UNION ALL SELECT 'competition_seasons', COUNT_BIG(*) FROM dbo.competition_seasons
UNION ALL SELECT 'teams', COUNT_BIG(*) FROM dbo.teams
UNION ALL SELECT 'source_snapshots', COUNT_BIG(*) FROM dbo.source_snapshots
UNION ALL SELECT 'matches', COUNT_BIG(*) FROM dbo.matches
UNION ALL SELECT 'match_results', COUNT_BIG(*) FROM dbo.match_results
UNION ALL SELECT 'match_goals', COUNT_BIG(*) FROM dbo.match_goals
UNION ALL SELECT 'import_runs', COUNT_BIG(*) FROM dbo.import_runs
UNION ALL SELECT 'validation_issues', COUNT_BIG(*) FROM dbo.validation_issues
UNION ALL SELECT 'match_changes', COUNT_BIG(*) FROM dbo.match_changes
UNION ALL SELECT 'sync_checkpoints', COUNT_BIG(*) FROM dbo.sync_checkpoints
UNION ALL SELECT 'match_notes', COUNT_BIG(*) FROM dbo.match_notes;

SELECT TOP (20)
       source_snapshot_id, provider, local_directory, response_path,
       metadata_path, byte_count, sha256, retrieved_at_utc
FROM dbo.source_snapshots
ORDER BY source_snapshot_id DESC;

SELECT TOP (20)
       sync_checkpoint_id, provider, scope_key, matchday_number,
       last_processed_at_utc, last_successful_snapshot_id,
       last_successful_import_run_id
FROM dbo.sync_checkpoints
ORDER BY updated_at_utc DESC, sync_checkpoint_id DESC;
~~~

Expected: approved counts match, every snapshot path maps to a durable object with the same byte count/hash, and checkpoints refer only to successful imports. Stop on any discrepancy.

### Future container verification

These commands become valid only after the planned Dockerfile exists. They were not run:

~~~bash
docker build --tag sports-fixtures-change-tracker:local .
docker run --rm --env-file .env -p 8000:8000 \
  sports-fixtures-change-tracker:local
~~~

Expected: the image starts with ODBC available, binds the configured port, serves assets, and contains no .env, raw snapshots, or logs.

### Future GitHub Actions verification

After a reviewed workflow exists, use GitHub Actions workflow dispatch for one approved matchday. Verify only non-secret outputs:

- job status and duration;
- selected matchday and safe event names;
- snapshot byte count and SHA-256;
- import-run status/failure phase;
- checkpoint advancement only after success;
- no duplicates or false changes on replay;
- conflict recovery remains disabled unless explicitly selected through the reviewed manual path.

Do not enable the schedule until two controlled manual runs and one failure/retry test pass.

## Planned evaluation metrics

These evaluations are planned, not completed:

| Metric | Measurement | Acceptance evidence |
| --- | --- | --- |
| Correctness | Compare provider IDs, teams, kickoff, finish flags, results, goals, and nullable future scores with saved snapshots | Zero unexplained reviewed mismatches |
| Duplication rate | Compare provider-ID counts before/after exact replay | Zero new domain duplicates and zero false changes |
| Change detection | Apply a controlled source update and inspect persisted fields | Exactly intended transitions with provenance |
| Rollback integrity | Inject failures at mutation/checkpoint operations | Current data/checkpoints unchanged; failure provenance retained |
| Import latency | Measure capture, upload, validation, SQL, and total job | Fits timeout with margin |
| Retry behavior | Record transient failures and attempt counts | Bounded retries and no duplicate side effects |
| Freshness | Compare checkpoint time, job completion, and dashboard revision | Public timestamp advances only after success |
| Snapshot replay | Lose local staging and replay from object storage | Exact bytes and metadata recoverable |
| Security | Inspect image, logs, workflow, routes, headers, and permissions | No secret leakage or anonymous operational writes |
| Availability | Measure cold start and dependency outages | Generic visible errors and preserved last good data |

## Final status

| Category | Status |
| --- | --- |
| Repository architecture audit | Completed by source inspection |
| Render compatibility execution | NOT RUN |
| Azure SQL compatibility/deployment test | NOT RUN |
| Docker build | NOT RUN; no Dockerfile currently exists |
| GitHub Actions workflow | NOT IMPLEMENTED; no workflow exists |
| Cloud migration | NOT RUN and not initiated |
| Public security test | NOT RUN |
| Cloud API/browser smoke test | NOT RUN |
| Scheduled synchronization | NOT RUN and not configured |
| Git operations, commit, push, deployment | NOT RUN |

**Recommendation:** NO-GO for immediate public hosting. Proceed only after the staged conditional plan resolves route authorization, ODBC/container packaging, durable snapshot storage, distributed locking, network/TLS/permissions, migration rehearsal, and manual cloud verification.
