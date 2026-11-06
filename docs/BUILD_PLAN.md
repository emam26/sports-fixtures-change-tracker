# Build Plan

## Current scope

The project implements UEFA Champions League 2026/27 through OpenLigaDB:

- shortcut: `ucl`
- season: `2026`
- expected league ID: `4946`
- initial proof scope: Matchdays 3 and 4
- planned expansion after evaluation: all 144 league-phase fixtures and later
  knockout fixtures

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
| 7 - browser dashboard | filters, detail, operations, optional notes | Browser visual audit remains pending after latest changes |
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

- a visible, responsive four-section shell is present before API data resolves;
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
matchday, detail, change, and operational reads. Change-page bounds and null-kickoff
ordering were also made deterministic. No test, Ruff check, API restart, browser
check, SQL operation, sync, or Git action was run for these changes.

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
- The dashboard discovers competition seasons/matchdays, filters current fixtures,
  shows typed detail and changes, displays import/validation/checkpoint state, and
  supports optional token-gated local note create/edit/archive.
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

Verification of the synchronization CLI correction and completed dashboard is the
current blocker. Where: WSL Bash. Working directory:
`/mnt/f/sports-fixtures-change-tracker`.

```bash
source .venv/bin/activate
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

In a second WSL Bash terminal in the same directory, verify the repaired aggregate
route before browser work:

```bash
source .venv/bin/activate
curl --fail --silent --show-error http://127.0.0.1:8000/api/dashboard-summary
python -m pytest \
  tests/test_sync_cli.py::test_sync_cli_returns_nonzero_after_partial_failure -q
python -m pytest tests/test_api.py tests/test_api_repository.py -q
ruff check .
ruff format --check .
python -m pytest -q -m "not sqlserver"
```

Expected: both focused test groups pass, both Ruff commands exit zero, and the
complete selected offline suite has no failures. The `curl` route must return HTTP
`200` JSON rather than the pre-edit `500`. Then follow the browser procedure in
`docs/DEPLOYMENT_LOCAL.md`. Stop at the first failure and return the complete
non-secret diagnostic. Do not run a live synchronization pass until this gate passes.

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
