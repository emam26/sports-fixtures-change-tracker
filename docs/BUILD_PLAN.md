# Build Plan

## Current scope

The project implements UEFA Champions League 2026/27 through OpenLigaDB:

- shortcut: `ucl`
- season: `2026`
- expected league ID: `4946`
- configured league-phase expectation: Matchdays 1-8, 18 fixtures per matchday
- verified imported coverage: Matchdays 3 and 4 only (36 fixtures)
- pending source-backed coverage: Matchdays 1, 2, 5, 6, 7, and 8
- later scope: provider-advertised knockout fixtures after explicit source review

Competition identity remains configurable for future work, but no other competition
is currently implemented or claimed.

## Stage status - 2026-11-06

| Stage | Implemented state | Evidence state |
| --- | --- | --- |
| 0 - foundation | src package, configuration, SQL connection, tooling | Owner verified |
| 1 - source capture | bounded client, contract checks, immutable raw snapshots | Owner verified on MD3/MD4 |
| 2 - SQL schema | 12-table SQL Server schema | Owner reports deployed |
| 3 - typed import | validation, upserts, provenance, changes, rollback, checkpoints | MD3/MD4 current data verified; latest audit not run |
| 4 - offline replay/evaluation | dry-run and deterministic evaluation CLIs | Prior dry run verified; latest edits not run |
| 5 - incremental synchronization | last-change decision, retries, lock, logs, partial failures | Initial/repeat manual sync verified; latest audit not run |
| 6 - local FastAPI | status, discovery, fixtures, history, operations, notes | Owner verified read-only endpoint responses; latest audit not run |
| 7 - browser dashboard | three public sections, filters, detail, optional notes | Browser visual audit remains pending after latest changes |
| 8 - one-shot scheduling support | WSL wrapper and Task Scheduler handoff | No task registered or activated |
| 9 - test/evaluation framework | offline, mocked, repository, SQL-gated plans | 85 non-SQL passed / 1 deselected before latest audit |
| 10 - portfolio documentation | architecture, API, testing, evaluation, runbook | Updated; owner review pending |

No release-readiness command was executed during the 2026-11-06 audit. Static
checks, tests, SQL replay/import, HTTP, API server, browser, scheduler, and Git review
are **NOT RUN** for the latest working tree.

## Evidence ledger

### Stage 0 - owner-supplied evidence

On 2026-11-01 and 2026-11-02, the owner reported:

- SQL Server `CANVASIT`, Standard Developer Edition (64-bit), version `17.0.1000.7`;
- database `SportsFixturesTracker` and runtime login `sports_tracker_app`;
- WSL TCP connectivity to the then-current Windows host address on port 1433;
- ODBC Driver 18 and `sqlcmd` authentication;
- Python 3.14.4 project virtual environment and pyodbc 5.3.0;
- successful manual Python and permanent database-check connections;
- editable installation, Ruff lint, Ruff formatting check, and five passing tests;
- `.env` ignored by Git.

The host address can change after WSL or network restart. No password is recorded.

### Stage 1 - owner-supplied source evidence

- Matchday 3: 18 completed matches, 18 unique provider match IDs, 36 typed result
  records in later dry-run/import evidence, 76,432 response bytes, SHA-256
  `88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`.
- Two Matchday 3 captures at 09:47 and 10:24 UTC on 2026-11-02 have identical
  content hashes and distinct immutable provenance directories.
- Matchday 4: 18 unfinished matches, 18 unique provider match IDs, empty result
  arrays, 53,969 response bytes, SHA-256
  `a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`.
- 36 unique provider match IDs exist across the two matchdays.
- Saved completed records include explicit `HalfTime` and `After90Minutes` results.
- The owner previously reported 15 Stage 1 tests passing in 0.50 seconds.

OpenLigaDB documents a 60-requests-per-minute limit. The implementation uses
one-shot work and bounded retries; aggressive polling is prohibited.

### Stage 2 and import recovery - owner-supplied evidence

The owner reports that the 12-table schema from `sql/001_initial_schema.sql` is
deployed. The source uses `source_snapshots.local_directory nvarchar(750)` so its
nonclustered unique key remains under SQL Server's 1,700-byte key limit.

Initial import failures exposed three concrete defects that were repaired before the
first success:

1. pyodbc identity batches could expose intermediate non-row result sets; the store
   now advances to the active identity result set before `fetchone()`;
2. a failed import needed a confirmed primary rollback before writing separate
   failure provenance;
3. OpenLigaDB can provide embedded Base64 team icons; these are omitted from the
   nullable URL column with content-free warnings.

The owner backed up and reset the dedicated development database with the guarded
manual recovery script. The first successful Matchday 3 baseline was then reported:

- import run ID `3`;
- source snapshot ID `8`;
- 18 inserted completed matches;
- 36 result rows;
- 74 goals;
- four safe embedded-icon warnings.

The latest owner-supplied offline baseline before this audit was 56 passing non-SQL
tests. It does not verify the audit edits below.

### 2026-11-06 release-verification follow-up

The owner subsequently reported that the database connection and SQL Server
integration test succeeded. The non-SQL suite reported 81 passing tests and one
failure in `test_sync_cli_returns_nonzero_after_partial_failure`.

Static inspection identified configuration-name drift in
`scripts/sync_openligadb.py`: `SyncSettings` exposes
`backoff_initial_seconds` and `backoff_max_seconds`, while the CLI attempted to
read `initial_backoff_seconds` and `max_backoff_seconds`. The first missing
attribute raised before `sync_run_started` could be logged, which explains the
test's empty event list. The CLI now maps the validated settings to the
corresponding `RetryPolicy` fields, and the regression test captures and verifies
that policy before asserting both lifecycle events and the non-zero partial-failure
exit. These corrections are NOT RUN pending owner verification.

### 2026-11-06 dashboard completion follow-up

The owner reported that opening the local root page showed little more than headings.
Static inspection found no broken FastAPI root route, asset mount, package-data rule,
or HTML/JavaScript selector mismatch: `/` returns the packaged web index and
`/assets` mounts that same directory. The practical failure mode was a sparse,
JavaScript-dependent presentation with blank data containers and insufficiently
prominent API failure states, not evidence of a static-path repair.

The dashboard was therefore completed rather than cosmetically patched:

- a visible, responsive dashboard shell is present before API data resolves;
- a new read-only dashboard-summary route supplies real fixture, finished/upcoming,
  goal-event, change, and latest committed-checkpoint metrics;
- a paged cross-fixture change route supplies real before/after values and source
  snapshot provenance without one browser request per fixture;
- the match explorer keeps API filters, adds client-side kickoff ordering, preserves
  nullable future scores, and exposes typed detail, goals, change history, and local
  notes;
- operational records continue to distinguish captured source evidence from a
  successful import/checkpoint; and
- API/static-asset/repository contract tests now cover the new routes and dashboard
  entry assets.

No schema, raw snapshot, SQL Server data, `.env`, server process, browser check, or
test was run for this implementation. The dashboard and all added tests are **NOT
RUN** pending owner verification.

### 2026-11-06 owner-supplied post-sync evidence

The owner subsequently verified the following operational facts. This evidence applies
to the working tree before the audit edits below and does not verify those edits:

- 36 distinct UCL fixtures are loaded and all are marked finished;
- 72 typed result rows and 144 goal rows are present;
- 936 records are field-level `match_changes` events resulting from Matchday 4
  completion. They are not 936 distinct changed fixtures;
- an initial synchronization and an unchanged repeat synchronization succeeded, with
  the repeat producing no false business changes;
- `/api/dashboard-summary`, `/api/matches`, `/api/match-changes`, `/api/import-runs`,
  `/api/validation-issues`, and `/api/sync-checkpoints` each returned HTTP `200`;
- the SQL Server integration test passed and the database connection succeeded; and
- the prior non-SQL suite reported 85 passed and one deselected test.

The existing source policy remains deliberate: the observed provider
`source_time_zone_id` transition from `W. Europe Standard Time` to `NULL` is retained
as source metadata, and a last-change value without an offset is not promoted to UTC.
The synchronizer conservatively performs a full retrieval rather than skipping on an
ambiguous timestamp. No timezone offset is invented.

### 2026-11-06 local dashboard HTTP audit follow-up

Browser automation is not available in the editing environment, so no browser
screenshot, JavaScript-console inspection, or click-through claim is made. A permitted
read-only localhost audit of the already-running API did establish the following
pre-edit facts:

- `/`, `/assets/styles.css`, `/assets/app.js`, and `/openapi.json` each returned HTTP
  `200` with the expected content type;
- `/health` reported the database available, and competition discovery, fixtures,
  match detail, change feed, import-run, checkpoint, validation-issue, and read-only
  note endpoints returned data or an intentional empty response; and
- `/api/dashboard-summary`, both with and without the loaded competition-season ID,
  returned the generic HTTP `500` response.

This rules out a missing static mount as the observed source of the sparse page. Source
inspection isolated the live failure to the dashboard aggregate query, whose CTE/scalar
subquery formulation was not covered by a real SQL Server API check. It has been
replaced with small, parameterized reads using the same deployed tables exercised by
the working endpoints. Failures now produce a local operation name and exception type
without logging sensitive SQL or configuration data. The current server was not
restarted after this edit, so the repaired endpoint, browser behavior, and tests remain
**NOT RUN**.

The dashboard now also has real cross-fixture change pagination using the existing
`limit`/`offset` API contract, responsive pagination controls, and a new asset cache
version. Static/API/repository tests were extended for these contracts; they are also
**NOT RUN**.

Files changed during the initial dashboard completion before this HTTP audit:

- `src/sports_tracker/api/models.py`
- `src/sports_tracker/api/repository.py`
- `src/sports_tracker/api/app.py`
- `src/sports_tracker/web/index.html`
- `src/sports_tracker/web/app.js`
- `src/sports_tracker/web/styles.css`
- `tests/test_api.py`
- `tests/test_api_repository.py`
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_PLAN.md`
- `docs/COMMIT_PLAN.md`
- `docs/DEPLOYMENT_LOCAL.md`
- `docs/MANUAL_RUNBOOK.md`
- `docs/TESTING.md`

Files additionally changed in the local dashboard HTTP audit follow-up:

- `src/sports_tracker/api/repository.py`
- `src/sports_tracker/web/index.html`
- `src/sports_tracker/web/app.js`
- `src/sports_tracker/web/styles.css`
- `tests/test_api.py`
- `tests/test_api_repository.py`
- `docs/API.md`
- `docs/BUILD_PLAN.md`
- `docs/DEPLOYMENT_LOCAL.md`
- `docs/TESTING.md`

### Current full-stack audit implementation (NOT RUN)

The current audit corrected the dashboard's field-change metric semantics, added an
affected-fixture count, added non-positive path-ID validation, eliminated a known
favicon request, and added latest-request-wins guards for overview, fixture,
matchday, detail, and change reads. Change-page bounds and null-kickoff ordering were
also made deterministic. No test, Ruff check, API restart, browser check, SQL
operation, sync, or Git action was run for these changes.

Files changed for this audit:

- `src/sports_tracker/api/app.py`
- `src/sports_tracker/api/models.py`
- `src/sports_tracker/api/repository.py`
- `src/sports_tracker/web/index.html`
- `src/sports_tracker/web/app.js`
- `src/sports_tracker/web/styles.css`
- `tests/test_api.py`
- `tests/test_api_repository.py`
- `docs/API.md`
- `docs/BUILD_PLAN.md`
- `docs/DEPLOYMENT_LOCAL.md`
- `docs/TESTING.md`

### 2026-11-06 public dashboard scope refinement (NOT RUN)

The public dashboard now exposes only Overview, Match Explorer, and Change
Intelligence. The Import & Sync Monitor navigation item, section, client-side API
requests, event handler, and dedicated CSS were removed. Overview retains a compact
**Last updated** indicator sourced exclusively from
`latest_successful_sync_at_utc` in the existing dashboard-summary API response. It
describes the latest successful synchronization recorded by the local database and
does not claim a newer source observation or reveal snapshot/import-run identifiers.

Import runs, synchronization checkpoints, validation issues, immutable snapshots,
SQL tables, ingestion, synchronization, and loopback API endpoints remain unchanged.
They are available to local development/diagnostic tooling but are intentionally not
requested or displayed by the public browser page. The technical footer disclaimers
and the earlier import-health headline copy remain removed from the frontend.

Files changed for this refinement:

- `src/sports_tracker/web/index.html`
- `src/sports_tracker/web/app.js`
- `src/sports_tracker/web/styles.css`
- `tests/test_api.py`
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_PLAN.md`
- `docs/DEPLOYMENT_LOCAL.md`
- `docs/MANUAL_RUNBOOK.md`
- `docs/TESTING.md`

No tests, static checks, API restart, browser verification, SQL operation, snapshot
operation, Git command, commit, or push was run for this refinement. All new and
changed checks are **NOT RUN** pending owner verification.

### 2026-11-07 Change Intelligence presentation repair (NOT RUN)

The frontend now preserves the API's field-level change records while grouping only
related fixture, result, or goal fields that share a change kind, observation time,
source snapshot, and import run. It maps recognized stored fields to human labels and
derives constrained summaries such as `Match completed`, `Final score recorded`, and
`Goal event added` only when their recorded differences support those statements.

Inserted records now present recorded details without a fabricated `Not supplied →
value` comparison. Updated records retain separately positioned previous/current
values, and removed records retain their previous value. Event provenance remains
explicit; snapshot observation and capture timestamps are never represented as goal
occurrence times. Individual mapped field details are collapsed by default, and the
match-detail history has a bounded vertical scroll area with responsive wrapping to
prevent overlap or horizontal overflow.

No API route, importer, SQL schema/table, raw snapshot, SQL Server data, credential,
or local-only security control changed. The backend remains the system of record for
all technically distinct rows and provenance.

Files changed for this repair:

- `src/sports_tracker/web/index.html`
- `src/sports_tracker/web/app.js`
- `src/sports_tracker/web/styles.css`
- `tests/test_api.py`
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_PLAN.md`
- `docs/DEPLOYMENT_LOCAL.md`
- `docs/MANUAL_RUNBOOK.md`
- `docs/TESTING.md`

The new frontend/API contract assertions and all manual visual checks are **NOT RUN**.
No test, formatter, linter, API request, server, SQL command, browser session, Git
command, commit, or push was executed for this repair.

### 2026-11-07 UCL league-phase coverage implementation (NOT RUN)

Owner-supplied database evidence remains limited to 36 completed UCL fixtures from
Matchdays 3 and 4, with 936 legitimate field-level change records. Matchdays 1, 2, 5,
6, 7, and 8 are not claimed captured or imported. Existing snapshots, checkpoints,
imports, fixtures, and change records were not modified.

The current database evidence supplied on 2026-11-06 reports that all 36 imported
fixtures are finished. This does not rewrite the preserved Matchday 4 raw capture,
which recorded 18 unfinished fixtures; source observations can update current rows
while the original response remains immutable.

The configuration now expresses the expected UCL league phase as Matchdays 1-8 with
18 fixtures per matchday. The OpenLigaDB client can compare the documented
`getavailablegroups` and full-season `getmatchdata` views. It retains disagreements
as warnings, selects only explicit provider group-order IDs, and defaults sync to the
configured league phase. Potential knockout groups remain excluded until an operator
explicitly opts in after source-shape review.

`report_season_coverage.py` is an offline raw-capture audit. It compares configured
fixture expectations with unique provider match IDs in immutable local snapshots and
labels a missing local snapshot as `not-captured`, not as provider unavailability or
an importer failure. The manual SSMS aggregate separately establishes imported rows
and import-run outcomes. No 144-fixture claim is made until both evidence paths agree.

Unfinished fixtures retain `NULL` scores. A missing provider kickoff now becomes a
validation warning while retaining the fixture with a `NULL` kickoff; malformed
non-empty timestamps remain import-blocking errors. The API orders null kickoffs last.
The public dashboard exposes All matches, Upcoming, and Completed filters, a
chronological Overview upcoming-fixture list, and a `Kickoff to be confirmed` state
without asserting a postponement or fabricating a date.

Files changed for this coverage implementation:

- `.env.example`
- `README.md`
- `src/sports_tracker/config.py`
- `src/sports_tracker/openligadb.py`
- `src/sports_tracker/ingestion.py`
- `src/sports_tracker/season_coverage.py` (new)
- `src/sports_tracker/api/repository.py`
- `src/sports_tracker/web/index.html`
- `src/sports_tracker/web/app.js`
- `src/sports_tracker/web/styles.css`
- `scripts/discover_openligadb_season.py` (new)
- `scripts/report_season_coverage.py` (new)
- `scripts/sync_openligadb.py`
- `tests/test_config.py`
- `tests/test_openligadb.py`
- `tests/test_ingestion.py`
- `tests/test_season_coverage.py` (new)
- `tests/test_sync_cli.py`
- `tests/test_api.py`
- `tests/test_api_repository.py`
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_PLAN.md`
- `docs/EVALUATION.md`
- `docs/MANUAL_RUNBOOK.md`
- `docs/SOURCE_NOTES.md`
- `docs/TESTING.md`

All static checks, offline tests, provider discovery, raw capture, SQL queries,
imports, synchronization, API/browser checks, and Git actions for this implementation
are **NOT RUN**. The next manual step is the small static/offline test batch followed
by the coverage report and source-discovery command in `docs/MANUAL_RUNBOOK.md`.

## Release-readiness implementation audit

### Ingestion and configuration

- Source timeout and retry backoff values must be positive and finite.
- Existing safe HTTP(S) team icons are preserved when later source icon data is
  embedded, invalid, or too long.
- Provider identity, baseline semantics, nullable future scores, explicit result
  types, transactional rollback, separate failure provenance, and checkpoint
  consistency remain unchanged.
- Missing child rows are not interpreted as deletions; that policy remains deferred.

### Synchronization and scheduling

- All sync captures use the canonical Stage 1 writer and directory convention.
- The parser receives validated OpenLigaDB settings.
- SQL checkpoint lookup uses deployed `provider_shortcut` and `season_start_year`
  columns.
- Reliable non-newer signals skip; unsupported, empty, malformed, failed, or
  timezone-naive signals force a full fetch.
- A matchday failure does not block later matchdays; any partial-failure pass exits
  non-zero.
- Duplicate matchday arguments are rejected. Structured start/completion events are
  logged under ignored `data/runtime/`.
- The shell wrapper remains a one-shot `.venv` entry point; no task was activated.

### FastAPI and dashboard

- Repository SQL now matches deployed competition, season, match, result, goal,
  import, validation, checkpoint, and note columns.
- DML result-set handling and note transaction commit/rollback are explicit.
- API models retain nullable result/goal scores and expose matchday summaries,
  expanded import status, synchronization checkpoints, and non-secret service status.
- Unexpected repository errors return generic HTTP 500 content and log only the
  exception type.
- The public dashboard discovers competition seasons/matchdays, filters current
  fixtures, shows typed detail and changes, and supports optional token-gated local
  note create/edit/archive. Import, validation, and checkpoint records remain in
  loopback-only development/diagnostic endpoints rather than public dashboard UI.
- Provider text uses `textContent`; the note token is not stored in browser storage.

### Security and release artifacts

- `.env` and `.env.*` remain ignored while `.env.example` remains trackable.
- Raw snapshots, runtime logs/locks, build artifacts, virtual environments, local SQL
  backup/data files, and `data/backups/` are ignored.
- No raw bytes, deployed SQL data, `.env`, password, token, or secret was modified.
- No public bind, authentication expansion, deployment, scheduler activation, commit,
  or push was performed.

## Files changed in the 2026-11-06 audit

- `.gitignore`
- `README.md`
- `src/sports_tracker/config.py`
- `src/sports_tracker/ingestion.py`
- `src/sports_tracker/synchronization.py`
- `src/sports_tracker/api/models.py`
- `src/sports_tracker/api/repository.py`
- `src/sports_tracker/api/app.py`
- `src/sports_tracker/web/index.html`
- `src/sports_tracker/web/app.js`
- `src/sports_tracker/web/styles.css`
- `scripts/import_snapshot.py`
- `scripts/sync_openligadb.py`
- `tests/test_api.py`
- `tests/test_api_repository.py` (new)
- `tests/test_config.py`
- `tests/test_import_snapshot_cli.py` (new)
- `tests/test_sql_diagnostics.py`
- `tests/test_sync_cli.py` (new)
- `tests/test_synchronization.py`
- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `docs/TESTING.md`
- `docs/EVALUATION.md`
- `docs/DEPLOYMENT_LOCAL.md`
- `docs/MANUAL_RUNBOOK.md`
- `docs/SOURCE_NOTES.md`
- `docs/COMMIT_PLAN.md`
- `docs/BUILD_PLAN.md`

## Acceptance gates

Run each gate in order and do not infer later success from an earlier gate:

1. editable installation and Ruff lint/format check;
2. offline tests excluding `sqlserver`;
3. immutable snapshot evaluation/dry run and hash confirmation;
4. read-only SQL connectivity/schema check;
5. exact Matchday 3 replay with unchanged domain/change counts and stable checkpoint
   snapshot identity (the successful run pointer may advance);
6. Matchday 4 import with 36 total unique matches and no future score rows;
7. real API and browser checks, including default-disabled notes;
8. one live bounded sync pass and log/checkpoint review;
9. one manual wrapper run, then optional Task Scheduler activation;
10. final Git ignore, diff, staged-content, commit, and push review.

Exact commands, SQL, expected outputs, stop conditions, and the Task Scheduler handoff
are in `docs/MANUAL_RUNBOOK.md`.

## Current blocker and next manual step

Verification of the new season-discovery, coverage, nullable-kickoff, and dashboard
changes is the current blocker. Where: WSL Bash. Working directory:
`/mnt/f/sports-fixtures-change-tracker`.

```bash
source .venv/bin/activate
ruff check .
ruff format --check .
python -m pytest \
  tests/test_config.py \
  tests/test_openligadb.py \
  tests/test_season_coverage.py \
  tests/test_ingestion.py \
  tests/test_sync_cli.py \
  tests/test_api.py \
  tests/test_api_repository.py -q
python scripts/report_season_coverage.py
```

Expected: both Ruff commands exit zero; the focused tests pass without network or SQL;
and the coverage report documents the current local capture gap without changing data.
Stop at the first failure and return the complete non-secret diagnostic. Only then run
the provider discovery and one-time backfill steps in `docs/MANUAL_RUNBOOK.md`; do not
run a live synchronization pass until those gates pass.

## Remaining limitations

- Exact replay, Matchday 4 SQL import, and current SQL repository queries are not yet
  manually verified.
- No controlled mutation/rollback test has been run against a separate SQL Server
  test database.
- Omission/retraction semantics, knockout-specific shapes, penalties/extra time, and
  season transitions need additional source evidence.
- Last-change skip correctness requires empirical comparison with later preserved
  full responses.
- The API is local-only and uses a single note-write token; it is not a public or
  multi-user security model.
- No benchmark, screenshot, scheduled run, commit, or push is claimed.
