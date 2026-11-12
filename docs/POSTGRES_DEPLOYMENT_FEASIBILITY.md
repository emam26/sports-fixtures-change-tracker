# PostgreSQL Deployment Feasibility

**Repository:** Sports Fixtures & Change Tracker
**Assessment date:** 2026-11-11
**Target:** Render Free FastAPI/frontend, Neon Free PostgreSQL, and GitHub Actions synchronization
**Decision:** **CONDITIONAL GO for a separately implemented portfolio/MVP deployment; NO-GO as an immediate drop-in or production-grade migration.**

This is a source-level feasibility assessment. No PostgreSQL database, cloud resource,
migration, Python command, test, SQL query, deployment, or workflow was executed.
The local SQL Server database, schema, snapshots, credentials, and behavior remain
unchanged.

## Implementation status

The compatibility foundation is now present in the working tree: `DATABASE_BACKEND`
selection, optional SQL Server packaging, Psycopg connection settings, a separate
PostgreSQL schema, PostgreSQL import/API/checkpoint/lease adapters, a guarded migration
utility, private S3-compatible snapshot storage, historical snapshot migration, role
grants, Render/GitHub deployment descriptors, and offline regression tests. These are
source-level changes only. The cloud path is not verified until the selected endpoint,
bucket policy, credentials, and replay behavior are manually tested.
The role grants are in `sql/postgresql/002_roles.sql`; LOGIN credentials are deliberately
not created or stored by the repository.

## Executive decision

The replacement is technically viable if it is treated as a second database backend:

- keep the current SQL Server backend as the reference implementation;
- add a separately reviewed PostgreSQL schema and repository implementation;
- reuse the existing parsing, validation, snapshot, and import-domain logic;
- preserve raw snapshots in durable private storage rather than runner or Render disks;
- use separate least-privilege Neon roles for the dashboard, synchronization, and migrations;
- prove row, timestamp, provenance, change-history, replay, and rollback parity before cutover.

It is not safe to point the existing application at Neon by changing a connection string.
The repository contains SQL Server-specific syntax in both the importer and API repository,
and the current schema contains SQL Server rowversion. A partial translation could silently
change historical ordering, NULL handling, duplicate behavior, or change history.

The current dataset is small enough for a free-tier feasibility proof, but Neon Free is
an availability and operations constraint, not a production SLA. Current Neon pricing
documents 1 GB PostgreSQL storage, 100 CU-hours per project per month, a maximum of 2 CU,
scale-to-zero after five inactive minutes, and 5 GB public network transfer per project
per month. Exhausting compute or network transfer suspends compute; exceeding storage
makes storage-increasing operations fail. These limits must be monitored and are not a
backup or uptime guarantee. See [Neon pricing](https://neon.com/pricing).

## Evidence from this checkout

### Reusable boundaries

- src/sports_tracker/ingestion.py defines the ImportStore protocol and keeps
  SnapshotImportProcessor dependent on that protocol rather than SQL syntax.
- The same module owns typed snapshot parsing, source identity validation, score/result
  validation, goal validation, icon normalization, field-level change calculation, replay
  semantics, and the failure/rollback contract. Those domain rules should be shared.
- snapshots.py and openligadb.py preserve provider response bytes and source metadata
  independently of the database driver.
- season_coverage.py is already an offline raw-capture audit and can remain backend
  independent; its report must continue to distinguish missing source captures from
  PostgreSQL import failures.
- api/repository.py defines a Repository protocol and maps database rows into API
  dictionaries. FastAPI response models and the browser contracts can remain stable if a
  PostgreSQL repository returns the same keys, NULLs, and timezone-aware values.

### SQL Server-specific boundaries

- SQLServerImportStore in ingestion.py uses dbo, question-mark parameters,
  SCOPE_IDENTITY(), multi-statement INSERT/SELECT batches, SYSUTCDATETIME(), and
  SQL Server result-set advancement for pyodbc.
- SQLServerRepository in api/repository.py uses dbo, question-mark parameters,
  COUNT_BIG, TOP (1), OUTER APPLY, CONVERT, SQL Server string literals, and
  OFFSET/FETCH pagination.
- SQLCheckpointReader and SyncMatchdayReader in synchronization.py contain additional
  SQL Server queries.
- runtime.py and database.py retain the pyodbc and ODBC Driver 18 adapters, while the
  package now includes Psycopg and an optional SQL Server extra.
- import_snapshot.py and sync_openligadb.py select the configured SQL Server or
  PostgreSQL connection/store path explicitly.
- RunLock is a local filesystem lock. A GitHub-hosted runner does not share it with
  another runner or with Render.
- sql/001_initial_schema.sql remains the SQL Server schema; the separate PostgreSQL
  schema, role grants, and private object-storage adapter are now additional artifacts.
- source_snapshots still stores locators and hashes, while the PostgreSQL cloud path
  stores the authoritative response.json and metadata.json pair in private storage.

## Domain reuse decision

**Yes, with a strict adapter boundary.** The intended shape is:

    OpenLigaDB client and immutable snapshot writer
            |
    typed parser and validation (shared)
            |
    SnapshotImportProcessor (shared)
            |                         |
    SQLServerImportStore       PostgreSQLImportStore
    SQLServerRepository        PostgreSQLRepository

The new PostgreSQL store must implement ImportStore with:

1. one transaction for current rows, real field-level changes, successful run status,
   and checkpoint advancement;
2. rollback of every partial fixture/result/goal/change/checkpoint write;
3. failed-run provenance only after primary rollback;
4. idempotent provider-key upserts and replay behavior; and
5. the same validation-issue, quarantine, conflict-recovery, and NULL-score semantics.

The failure-provenance path should use a fresh connection or separately controlled
transaction after rollback. PostgreSQL rejects further commands on an aborted transaction
until ROLLBACK. Psycopg documents this in
[transaction management](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

The compatibility foundation is implemented behind the existing protocols. The SQL
Server store and schema remain the local reference implementation; PostgreSQL behavior
still requires the staged offline, target-database, migration, and replay verification
listed in the runbook.

## Exact SQL Server features requiring adaptation

| Current feature | Where observed | PostgreSQL design | Correctness risk |
|---|---|---|---|
| dbo schema | schema and all SQL repositories | Use a dedicated sports_tracker schema and qualify every table | search_path through transaction pooling can resolve the wrong object |
| bigint IDENTITY | all primary-key tables | bigint GENERATED BY DEFAULT AS IDENTITY; preserve migrated IDs and reset sequences | remapping IDs without every FK and history row changes provenance |
| bit | active, finished, penalty, archive flags | boolean | do not coerce nullable flags to false |
| nvarchar(n)/(max) | names, paths, issue text, old/new values | varchar(n)/text with the same logical limits | length and collation semantics differ; truncation must remain an error |
| varchar(n), char(64) | statuses, severities, hashes | equivalent PostgreSQL character types | preserve exact status and hash policy |
| datetime2(7) | all UTC columns | timestamp(6) with time zone after explicit UTC normalization | PostgreSQL retains at most six fractional digits; naive values must not use server local time |
| rowversion | sync_checkpoints.checkpoint_version | explicit bigint version increment or a deliberate lock/version design | rowversion is a concurrency token, not a timestamp |
| SYSUTCDATETIME() | defaults and updates | explicit application UTC, or CURRENT_TIMESTAMP for acceptable transaction-time defaults | now()/CURRENT_TIMESTAMP is transaction-start time, not provider observation time |
| USE, GO, XACT_ABORT, TRY/CATCH, THROW | schema script | reviewed versioned migration tool and driver transaction | client batch syntax and error semantics are not portable |
| OBJECT_ID, sys.indexes | schema existence/index checks | migration history plus PostgreSQL catalog checks | IF NOT EXISTS does not repair wrong existing definitions |
| SCOPE_IDENTITY and DML batches | SQLServerImportStore inserts | one INSERT ... RETURNING primary key statement | copied nextset logic could associate the wrong ID |
| question-mark parameters | pyodbc calls | Psycopg positional `%s` placeholders | string interpolation would create injection/quoting defects; see [Psycopg parameters](https://www.psycopg.org/psycopg3/docs/basic/params.html) |
| TOP (1) | result/checkpoint projections | LIMIT 1 after identical deterministic ORDER BY | dropping a tie-breaker can change selected scores |
| OUTER APPLY | final-result projections | LEFT JOIN LATERAL, or an equivalent ordered aggregate/window query | a normal join can multiply rows and corrupt scores/analytics; see [PostgreSQL LATERAL](https://www.postgresql.org/docs/current/queries-table-expressions.html) |
| COUNT_BIG | aggregates | PostgreSQL count(*) already returns bigint | preserve empty aggregate and NULL-sum behavior |
| OFFSET/FETCH | API pagination | OFFSET `%s` LIMIT `%s` with the same stable ordering | pagination must remain after ordering |
| CONVERT(nvarchar, year) | competition list | CAST(year AS text) | preserve API field types |
| LEN/LTRIM/RTRIM | schema blank checks | length(btrim(...)) | trailing-space semantics differ |
| N string literals | result-type filters | PostgreSQL text literals | preserve exact After90Minutes and HalfTime identity |
| collation-dependent LIKE | team search | explicit LIKE/ILIKE policy and index | search results can change under PostgreSQL default collation |
| file lock | synchronization | GitHub concurrency plus a database-backed lease or direct-session advisory lock | workflow concurrency does not cover all writers; transaction-pooler sessions cannot hold session advisory locks |

No MERGE, IDENTITY_INSERT, sp_getapplock, or SQL Server stored procedure was observed
in the inspected application code. They should not be introduced as migration shortcuts.
PostgreSQL INSERT ... ON CONFLICT is the likely upsert primitive, but each statement
must be tested against the existing unique keys and change-history semantics. PostgreSQL
documents RETURNING in [INSERT](https://www.postgresql.org/docs/current/sql-insert.html).

## Schema and historical-correctness plan

Create a separate PostgreSQL migration set. Do not convert sql/001_initial_schema.sql in
place. Keep the twelve logical tables:

- competitions, competition_seasons, teams;
- source_snapshots, matches, match_results, match_goals;
- import_runs, validation_issues, match_changes, sync_checkpoints, match_notes.

Preserve primary/foreign keys, unique keys, check constraints, nullable score pairs, and
provider identity keys. Keep team_icon_url as nullable URL metadata and keep the current
Base64 normalization policy; do not silently change it to image storage.

Normalize only fields proven to represent UTC. Keep source_last_update_raw as original
provider text and retain the rule that ambiguous provider timestamps are not guessed.
PostgreSQL distinguishes timestamp without time zone from timestamptz and permits at most
six fractional digits; see [date/time types](https://www.postgresql.org/docs/current/datatype-datetime.html).

For migrated IDs, choose one auditable policy: copy IDs and all foreign keys exactly, then
set each sequence above the copied maximum; or remap every ID and verify all relationships.
Copying IDs is preferable for auditability. PostgreSQL identity columns allow explicit
values with GENERATED BY DEFAULT; see [identity columns](https://www.postgresql.org/docs/17/ddl-identity-columns.html).

Do not reconstruct history from only current fixture rows. match_changes depends on the
sequence of distinct observations. Safe choices are:

- exact migration of all current rows, changes, runs, issues, snapshots, and checkpoints;
  or
- offline replay of every preserved raw snapshot in chronological capture order, including
  failed/provenance records and the reviewed Matchday 2 recovery behavior.

If historical raw snapshots are unavailable, exact table migration is required. Replay is
a verification method, not permission to omit provenance. Neither path may rewrite response
bytes or invent an earlier source state.

Before cutover compare row counts by table and provider key, all FK/unique-key groups,
snapshot hashes/URLs/byte counts/times, nullable result scores, goal links, every change
field/kind/old/new/provenance value, import statuses, validation issues, checkpoints, and
API JSON for completed, unfinished, 0-0, missing-kickoff, and changed fixtures.

The owner-reported local dataset is small enough that 144 fixtures and 936 field-level
changes are expected to fit well below 1 GB, but this is not a measured Neon size.
Indexes, text history, future snapshots, and continued change records must be measured.
Raw bytes are excluded because the current schema stores paths and metadata, not payloads.

## Required adapter work and current status

The following components are implemented in the compatibility foundation, but each
requires owner-run parity and permission checks before production use:

1. `src/sports_tracker/postgres_ingestion.py` implements `ImportStore` with Psycopg 3,
   parameter binding, `RETURNING` IDs, idempotent change inserts, and rollback.
2. `src/sports_tracker/api/postgres_repository.py` implements the current API contract;
   `SQLServerRepository` is unchanged.
3. PostgreSQL settings/runtime adapters are isolated from `DatabaseSettings`.
4. PostgreSQL checkpoint/matchday readers, a database lease, and injected store factories
   support unattended synchronization without changing local SQL Server behavior.
5. `scripts/migrate_sqlserver_to_postgres.py` previews or applies only absent rows after
   comparing existing target rows; it normalizes Psycopg mapping rows, rejects unsafe
   schema identifiers, detects target-only rows, reports target counts before apply, and
   explicitly rolls back on failure.

The raw-object archive now has a private S3-compatible adapter in
`src/sports_tracker/storage.py` and a separate historical migration utility. The
snapshot migration accepts the configured mapping-row format and explicitly rolls back
database locator updates on failure. Object uploads are not part of the database
transaction, so any orphan object remains safe but requires manual hash/reference review.
The selected endpoint, bucket policy, credentials, retention, and replay behavior remain
manual verification gates.

Use a pooled Neon connection for bounded Render read traffic and a direct connection for
schema migration and the long import unless every lock/session requirement is proven safe
through the pooler. Neon describes pooled/direct strings and transaction-mode PgBouncer in
[connection pooling](https://neon.com/docs/connect/connection-pooling). Qualify every table
and do not depend on SET search_path through a transaction pooler.

Neon requires TLS and recommends sslmode=verify-full; use channel_binding=require when
supported by the selected Psycopg/libpq stack. Do not silently downgrade certificate
verification. See [Connect to Neon securely](https://neon.com/docs/connect/connect-securely).
Keep the full DATABASE_URL only in Render/GitHub secret stores.

### Least privilege

Use separate roles:

| Role | Required scope | Must not have |
|---|---|---|
| migration owner | DDL and controlled migration | Render or scheduled-job use |
| synchronization writer | importer/provenance/current-row DML and required reads; no DDL | ownership or role management |
| dashboard reader | SELECT on reviewed tables/views | any write or DDL privilege |
| optional notes writer | only local-note CRUD if intentionally enabled | source fixture/result/change/checkpoint writes |

`sql/postgresql/002_roles.sql` creates or normalizes NOLOGIN group roles and uses
explicit `public.`-qualified table and identity-sequence grants. The API group receives
only reviewed public SELECT tables; the synchronization group receives importer DML and
INSERT/DELETE on `sync_leases` but no domain DELETE, notes, migration ledger, or DDL;
the migrator is owner-operated and separate. It does not create LOGIN credentials.
Neon states that SQL-created roles require selective grants, while Console/API-created
roles are administrative unless an access level is selected. See [Neon roles](https://neon.com/docs/manage/roles).
The owner must test actual ON CONFLICT, identity-sequence, and RETURNING grants before
deployment; a read-only database role does not replace FastAPI route restrictions.

## Render, GitHub Actions, and Neon connectivity

Neon public endpoints are reachable from both Render and GitHub-hosted runners, avoiding
the Azure SQL firewall/IP-allowlist problem. This is simpler, not private networking:
the endpoint remains Internet-reachable and relies on TLS, credentials, grants, and
application controls. The Neon pricing table does not show Free-plan private networking
or IP allow rules as included capabilities; verify the selected account/region before
relying on either control.

GitHub Actions OIDC is not a PostgreSQL login. The job needs a dedicated Neon database
credential or a separately designed short-lived exchange. Store only the sync role secret
in an encrypted GitHub environment and never expose it to untrusted pull-request runs.
The repository now contains `.github/workflows/synchronize.yml`; it uses a dedicated
secret, a database lease, private object storage, and an explicit activation gate. The
scheduled job requires the repository variable `ENABLE_SYNC=true`; manual dispatch
requires the boolean `activate` input. Missing storage configuration fails before
provider import and cannot advance a checkpoint.

Use workflow concurrency and retain a database-backed guard. GitHub documents that
scheduled jobs can be delayed or dropped under load and that concurrency applies only to
jobs sharing its group. See [scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
and [workflow concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
Use a lease row with expiry/compare-and-set, or a direct-connection session advisory lock.
Do not use a transaction-pooler connection for a session advisory lock.

## Immutable snapshots and recovery

A GitHub workspace or Render filesystem must not be the only copy of response.json and
metadata.json. The cloud minimum is:

1. capture exact bytes and compute SHA-256;
2. write response and metadata to a private immutable object key based on provider,
   shortcut, season, matchday, UTC capture time, and hash;
3. verify stored bytes and metadata before recording/advancing provenance;
4. store a logical object key within the existing path-column limits; and
5. provide offline replay from that object without another provider request.

`NeonS3SnapshotStore` implements the object pair with conditional create, byte
comparison, exact metadata-byte migration, and SHA-256 verification on retrieval.
Database import begins only after the object pair is verified. Object and database
transactions are not atomic: a failed database import can leave a durable orphan
object, which is safe to retry but must be reviewed by the owner. No WORM or S3 Object
Lock guarantee is assumed. The selected Neon endpoint, private bucket policy, retention,
egress, and restore behavior remain owner-verification gates; provider storage is not a
substitute for retaining every response and failed import record.

## Minimum viable migration sequence

### Phase 0 — freeze the reference

1. Keep SQL Server as source of truth; do not modify sql/001_initial_schema.sql.
2. Inventory all raw snapshots and metadata, including failed and quarantined runs.
3. Export secret-safe counts, keys, timestamps, hashes, and provenance relationships.
4. Choose durable snapshot storage and retention before writing PostgreSQL code.

### Phase 1 — isolated target

1. Create a separate Neon development branch/project and apply a versioned PostgreSQL schema.
2. Add the driver/runtime behind a backend selection defaulting to SQL Server locally.
3. Implement and unit-test the PostgreSQL store, repository, and checkpoint readers without
   changing SQL Server classes.
4. Add a backend-neutral synchronization factory and a database-backed single-writer guard.

### Phase 2 — semantic proof

1. Compare PostgreSQL API output with SQL Server for completed, unfinished, 0-0,
   missing-kickoff, and changed fixtures.
2. Test initial import, identical replay, changed score, conflict quarantine, invalid
   record, rollback, failed provenance, and retry.
3. Compare the full historical migration by key/hash, not only total count. Confirm that
   936 existing changes retain their source/import relationships.
4. Run synchronization twice: no duplicate rows or false changes, one correct checkpoint.
5. Measure scale-to-zero latency, import duration, pool wait, egress, storage, and CU-hours.

### Phase 3 — staged cutover

1. Use the dashboard reader role on Render and sync writer role on GitHub Actions.
2. Keep SQL Server read-only for a defined comparison period; do not dual-write casually.
3. Cut over only after parity and raw-archive gates pass.
4. Roll back by switching backend configuration, not by deleting or replaying unverified data.

## Evaluation gates

- **Correctness:** exact key/value/provenance parity and API parity on saved snapshots.
- **Duplication:** zero duplicate provider keys and zero changes on identical replay.
- **Change detection:** every expected transition and no false transition.
- **Rollback:** no partial current rows, changes, or checkpoint advancement after injected faults;
  failed provenance only after confirmed rollback.
- **Efficiency:** last-change/discovery checks avoid unnecessary fetches while unreliable
  signals force safe retrieval.
- **Replay:** every imported snapshot replays from immutable bytes with the same hash.
- **Operations:** duplicate jobs serialize, stale leases recover, TLS verification works,
  secrets stay out of logs, and grants reject unauthorized DDL/writes.
- **Free headroom:** measure table/index size, egress, CU-hours, pool wait, and backups.

## Blockers and unresolved questions

1. Which private durable archive will hold raw bytes and metadata, with retention and replay?
2. Are Neon Free IP allow rules/private networking available for the chosen project/region?
3. Will GitHub use a dedicated DB secret or a supported short-lived credential exchange?
4. Does SQL Server data use meaningful seventh fractional timestamp digits?
5. What case/accent behavior must team search and unique text keys preserve?
6. Should checkpoint versioning use an explicit counter or a lease/version table?
7. What recovery exists beyond Neon Free's limited restore/monitoring window?
8. What separate Render start command and public-readonly verification will be used?

## Final recommendation

**CONDITIONAL GO.** Proceed only with an isolated PostgreSQL compatibility project and
offline tests first. The domain and validation logic are reusable, but a separate
PostgreSQL store, repository, migration schema, connection/runtime path, distributed
single-writer guard, and durable snapshot archive are required. The SQL Server backend
should remain unchanged and the comparison baseline until parity and rollback evidence
are complete.

This is suitable for a low-volume portfolio/MVP deployment after those gates. It is not
a claim that the app is ready for public production on Neon Free, and it is not approval
to create resources or incur charges.

## Sources consulted

- [Neon pricing and Free-plan limits](https://neon.com/pricing)
- [Neon: connect from any application](https://neon.com/docs/connect/connect-from-any-app)
- [Neon: connect securely](https://neon.com/docs/connect/connect-securely)
- [Neon: connection pooling](https://neon.com/docs/connect/connection-pooling)
- [Neon: manage roles](https://neon.com/docs/manage/roles)
- [GitHub Actions scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub Actions workflow syntax and concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [PostgreSQL date/time types](https://www.postgresql.org/docs/current/datatype-datetime.html)
- [PostgreSQL identity columns](https://www.postgresql.org/docs/17/ddl-identity-columns.html)
- [PostgreSQL INSERT and RETURNING](https://www.postgresql.org/docs/current/sql-insert.html)
- [PostgreSQL table expressions and LATERAL](https://www.postgresql.org/docs/current/queries-table-expressions.html)
- [Psycopg 3 transaction management](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Psycopg 3 query parameters](https://www.psycopg.org/psycopg3/docs/basic/params.html)
## Current implementation handoff — 2026-11-12

The compatibility foundation now includes a read-only parity report (`scripts/verify_postgresql_parity.py`), a read-only deployment preflight (`scripts/preflight_postgresql.py`), and an offline PostgreSQL lease-renewal test. PostgreSQL synchronization requires `SELECT`, `INSERT`, and `DELETE` on `public.sync_leases`; domain-table delete access remains excluded. These additions are written but **NOT RUN**.

Parity is deliberately evidence-oriented: `MATCH`, `MISMATCH`, `MISSING`, `ERROR`, and `NOT CHECKED` are distinct outcomes. It compares migrated tables and reports counts, stable keys, field differences, source/target-only rows, snapshot hashes, semantic result/change summaries, quarantined conflict issues, and derived foreign-key violations. Timestamp comparison is UTC at Python microsecond precision; SQL Server `datetime2(7)` sub-microsecond precision is not silently inferred.

The deployment decision remains **CONDITIONAL GO** for a staged, isolated migration review. It is not authorization to connect a cloud job to production. First run the offline checks, then the read-only preflight and parity report, then review the dedicated-target Neon integration guard. A lease renewal fails closed when the owner row is lost; synchronization critical sections must remain shorter than the configured lease duration and must be operationally monitored.
