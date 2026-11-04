# Build Plan

## Implementation update — 2026-11-03

This status supersedes older summaries where they differ; historical evidence
below remains intact.

### Manual development-database recovery plan - 2026-11-04

Owner-supplied SQL Server state shows a failed first-import recovery case in the
dedicated `SportsFixturesTracker` development database: import runs `1`
(`Started`) and `2` (`Failed`) both reference source snapshot `7`; the database
contains 14 teams, 7 matches, 14 results, 32 goals, and one snapshot. The owner
reports that the database was empty before these failed imports and that the
latest non-SQL suite passed 56 tests. These facts are owner-supplied; no SQL,
tests, or imports were run in this handoff.

`sql/manual_reset_development_import_data.sql` now provides a read-only preview
and a separately commented destructive block. The execution block is restricted
to `SportsFixturesTracker`, repeats the exact observed-state checks inside a
serializable transaction, requires the operator to replace a `NULL` confirmation
value with an explicit token, verifies server `CANVASIT`, preserves local notes
by refusing to proceed when any exist, deletes dependencies before parents, and
verifies all 12 application tables are empty before commit. It is only for
resetting this dedicated disposable development database after a manual full
backup; it must not be used for legitimate development, test, or production
records. Manual review and execution remain **NOT RUN**.

### Import atomicity and team-icon normalization repair — 2026-11-03

The reported SQL Server 2628 failure was caused by an OpenLigaDB
`teamIconUrl` containing a Base64 `data:` URI. The deployed
`dbo.teams.team_icon_url` column is nullable `nvarchar(2048)`, so the importer
now treats it only as optional external URL metadata: absolute HTTP(S) URLs up
to 2,048 characters are retained; embedded, malformed, and oversized values are
replaced with `NULL` and a password-safe warning that contains no URI content.
Team provider identity and fixture loading are unchanged. No schema migration is
required.

Inspection also clarified why rows can remain after a failed import. Current
domain writes (teams, matches, results, goals, changes, and checkpoints) belong
to the primary transaction and must disappear after a successful rollback. The
snapshot, competition, season, failed import run, and validation issue are
intentional post-rollback provenance, committed separately. The importer now
uses explicit `autocommit=False`, no longer invokes a redundant rollback while
recording failure provenance, and does not commit that provenance if the primary
rollback itself fails. In the latter case it reports that database state is
unconfirmed rather than claiming a successful rollback.

New offline tests cover safe HTTP(S) URLs, embedded-data omission, oversized URL
omission, rollback of newly inserted teams before a fixture failure, rollback
failure handling, and explicit connection autocommit. These tests are **NOT
RUN**. The dashboard was inspected: it does not expose or render team icons, so
embedded provider data cannot reach the browser through the current UI.

Owner-supplied evidence immediately before this repair: the focused diagnostic
tests passed (`4 passed`), and the non-SQL suite passed (`47 passed, 1
deselected, 1 warning`). The same static-check pass still reported one import
ordering violation in `ingestion.py` and one formatting violation in
`test_sql_diagnostics.py`; all verification after this repair remains **NOT
RUN**.

### Rollback regression correction - 2026-11-04

The failing in-memory rollback regression did not reach the configured
`insert_match` failure point. Its fixture changed the home and away provider
team IDs to `30` and `40`, but left goals assigned to the original IDs `10` and
`20`. Snapshot validation correctly rejected that inconsistent record before
the transactional fixture loop. The fixture helper now keeps goal scoring-team
IDs aligned with overridden test-team IDs.

The main regression now injects a failure at checkpoint advancement, after new
teams, a match, two results, and three goals have been written. Its
non-transactional operation log proves those writes were attempted, while
post-failure assertions prove rollback removed every domain write and the
checkpoint. It separately verifies the expected committed failure provenance:
the snapshot, competition, season, failed import run, and its safe diagnostic
issue. A focused companion test still injects exactly at `insert_match` and
proves that the call is reached after the new team upserts.

Inspection of the SQL Server store found no additional transaction-safety
defect in this path: connections are opened with `autocommit=False`, primary
domain writes share that connection transaction, and failure provenance is
written only after the primary rollback succeeds. These updated offline tests
are **NOT RUN**.

### Evaluation CLI repair — 2026-11-03

The offline evaluation CLI now loads validated OpenLigaDB settings and passes
them to `load_snapshot`, matching `scripts/import_snapshot.py`. A regression
test verifies that the configured `OpenLigaDBSettings` object reaches the
loader. Inspection found no other CLI call sites omitting this required
argument. Duplicate class docstrings introduced in the configuration and
ingestion modules were removed. These edits remain **NOT RUN** pending manual
verification.

### SQL import cursor-result handling — 2026-11-03

The first Matchday 3 SQL import exposed `ProgrammingError: No results. Previous
SQL was not a query.` during `ensure_snapshot`; the same issue prevented the
failed-run recorder from creating its diagnostic run. The cause was confirmed in
the store: identity-returning batches execute DML followed by
`SELECT SCOPE_IDENTITY()`, but the code called `fetchone()` before advancing
past SQL Server's intermediate non-row result. `SQLServerImportStore` now checks
the cursor description and uses `nextset()` until the identity result set is
active, or raises a clear error if no identity result is returned. The same
central helper covers snapshot, run, team, match, result, and goal inserts, so
failed-run recording uses the corrected path as well.

The importer retains operation names for SQL-store errors and keeps the original
safe exception summary for stores without operation metadata. Rollback and
failed-run-recording failures remain separately logged. SQL statements,
parameters, connection strings, and credentials are not logged. No schema
change was necessary. New offline cursor-result regression tests and the
rollback test correction remain **NOT RUN**.

### Repair follow-up — first verification pass

The user reported that collection stopped in three test modules because the new
runtime adapter imported a nonexistent `load_sql_server_settings` name. The
existing configuration contract is `load_database_settings`; the adapter now uses
that loader lazily inside `open_sql_server_connection`, so module import does not
attempt a connection. The remaining reported unused import and test import-order
findings were also corrected. Targeted manual formatting normalization was applied
to all six files named by Ruff without executing the formatter. All corrections in
this follow-up remain **NOT RUN** pending user verification.

### Repair follow-up — second verification pass

The user reported `37 passed, 6 failed, 1 deselected`, one Ruff import-order
finding, and five files still requiring formatting. All six failures were isolated
to new retry/last-change tests: the URL builder was called with the wrong shape,
test settings omitted the required descriptive user agent, `RetryPolicy` lacked
its own bounds checks, and direct `LastChangeSignal` construction omitted response
metadata. The tests now use the implemented configuration and signal interfaces,
while the implementation validates retry bounds and finite positive backoff values.
No HTTP test uses the real network. These edits and the remaining manual formatting
normalization are **NOT RUN** pending the next user verification pass.

| Stage | Implementation status | Verification status |
|---|---|---|
| 0 — foundation | Complete | Manually verified 2026-11-02 |
| 1 — source capture | Complete | Manually verified 2026-11-02 |
| 2 — SQL schema | Complete; 12 tables deployed | Verified; user supplied commit `9d05663` |
| 3 — typed import | Repaired after reported lint/test failure | **NOT RUN after repair** |
| 4 — offline ETL and replay | Implemented on Stage 3 importer | **NOT RUN** |
| 5 — synchronization and recovery | Implemented | **NOT RUN** |
| 6 — local FastAPI service | Implemented | **NOT RUN** |
| 7 — browser dashboard | Implemented | **NOT RUN** |
| 8 — one-shot scheduling support | Implemented; no task activated | **NOT RUN** |
| 9 — test/evaluation framework | Implemented | **NOT RUN** |
| 10 — documentation and handoff | Implemented in working tree | Review pending |

No Stage 3–10 verification, database import, live request, server start, browser
check, or scheduler activation was performed during this handoff.

### Stage 3 repair

The last user-supplied diagnostics were 37 Ruff findings, three files requiring
formatting, and one failing test (`21 passed, 1 failed`). The rollback test changed
a final result but injected at `update_match`; final-score persistence actually
uses `update_result`. It now injects at the real operation, proves exact rollback
of result/goal/change/checkpoint state, injects again at checkpoint advancement,
and finally proves a clean retry can succeed.

A genuine failure-recording defect was corrected: failed-run season creation now
receives the snapshot league ID instead of the season value. Reported import-order,
unused-import, line-length, and formatting defects were edited without weakening
Ruff configuration. These corrections remain **NOT RUN**.

### Stage 4–10 behavior

- Saved snapshots support validation, deterministic offline replay, SQL upsert,
  provenance, field-level changes, rollback, and safe retry.
- The synchronizer skips a full request only when a reliable timezone-aware source
  timestamp is not newer than the committed checkpoint. Ambiguity forces a fetch.
- Retries are bounded and limited to network errors, HTTP 429, and selected 5xx
  responses; there is no polling loop.
- FastAPI is loopback-only by default. Queries are parameterized. Local note writes
  are disabled by default and require a separate token when enabled.
- The dashboard exposes fixtures, typed results/goals, history, import runs, and
  validation issues while rendering source text safely.
- Scheduling is a user-activated one-shot wrapper with an overlap lock and ignored,
  rotating structured logs.

### Schema decision

No migration is introduced. The deployed 12 tables already model snapshots,
imports, current state, changes, checkpoints, issues, and notes. Any future index
must be a numbered migration justified by measured query-plan evidence; do not
mutate a deployed database by editing `001_initial_schema.sql`.

### Current blocker and next step

Verification is the blocker. In WSL Bash at
`/mnt/f/sports-fixtures-change-tracker`, activate the existing environment, install
the updated editable dependencies, and run `ruff check .`. Stop on failure and
return the complete non-secret output. The full order is in `MANUAL_RUNBOOK.md`.

### Files changed in this handoff

Stage 3 repair changed `scripts/import_snapshot.py`,
`src/sports_tracker/ingestion.py`, and `tests/test_ingestion.py`. Later stages add
runtime configuration, synchronization, API code, dashboard assets, operational
scripts, isolated tests, and handoff documentation. `.env`, raw snapshot bytes,
deployed SQL, and secrets were not changed.

## Project scope

The current implementation targets UEFA Champions League 2026/27 through
OpenLigaDB:

- shortcut: `ucl`
- season: `2026`
- expected league ID: `4946`
- initial matchdays: 3 and 4
- eventual coverage: all 144 league-phase fixtures and later knockout fixtures

The code keeps provider, competition, season, and matchday values configurable
for future competitions. It does not claim that any future competition is
implemented.

## Stage status

### Stage 0 — project foundation

Complete and verified from owner-supplied evidence. The repository contains the
src-based Python package, configuration, SQL Server connection helper, tests,
and manual setup documentation. The owner reported successful Python 3.14.4
environment setup, pyodbc 5.3.0 installation, manual connection, and the
database check script.

The owner’s 2026-11-02 verification record also reports successful editable
installation, Ruff lint, Ruff formatting with 10 files formatted, and pytest
with 5 tests in 0.13 seconds. The database check reported server `CANVASIT`,
login `sports_tracker_app`, database `SportsFixturesTracker`, edition
`Standard Developer Edition (64-bit)`, and version `17.0.1000.7`. `.env` is
Git-ignored. These are owner-supplied historical checks; they do not imply that
the Stage 3 importer has run.

### Stage 1 — raw OpenLigaDB retrieval

Implemented and manually verified from owner-supplied evidence. Responses are
preserved byte-for-byte with metadata, timestamp/hash-based directories, and
immutable no-overwrite behavior. Matchday 3 and 4 captures are retained under
`data/raw/`, which is Git-ignored.

The source is subject to OpenLigaDB’s 60-requests-per-minute limit. This
project must not poll aggressively; Stage 1 deliberately has no scheduler or
repeated polling loop.

### Stage 2 — SQL Server schema

The 12-table SQL Server schema is deployed according to the project owner’s
report. The schema source remains `sql/001_initial_schema.sql`. The importer
uses the existing tables and constraints; it does not create or alter tables.

### Stage 3 — snapshot ingestion and change tracking

Code implemented in this handoff; execution remains **NOT RUN** pending manual
verification by the project owner.

Implemented scope:

- Reads existing `response.json` and `metadata.json` files without contacting
  OpenLigaDB.
- Parses the observed OpenLigaDB objects into typed teams, fixtures, results,
  and goals.
- Validates competition identity, provider IDs, required relationships,
  timezone-aware kickoff timestamps, explicit result types, score consistency,
  and goal-team relationships.
- Preserves unfinished future matches with no invented zero scores.
- Uses the existing SQL Server schema and parameterized pyodbc statements.
- Preserves snapshot provenance and import-run status.
- Uses provider IDs and existing unique constraints for idempotent upserts.
- Records field-level `match_changes` only when a distinct snapshot changes an
  existing current value; unchanged replay does not create changes.
- Advances the sync checkpoint only after the transactional data commit.
- Rolls back transactional writes on failure and attempts to record a failed
  import run for diagnosis and safe retry.
- Provides `scripts/import_snapshot.py` with offline `--dry-run` support.

The importer does not implement scheduling, retries against the live provider,
SQL loading for any other provider, API endpoints, UI behavior, or knockout
expansion logic.

## Verified source evidence available to the owner

The owner supplied the following Stage 1 evidence for the saved responses:

- Matchday 3: 18 matches, all completed, all with results, 18 unique provider
  match IDs, 76,432 bytes, SHA-256
  `88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`.
- Two Matchday 3 snapshots were captured at 09:47 and 10:24 UTC on
  2026-11-02, with identical content hashes.
- Matchday 4: 18 matches, all unfinished, all with empty `matchResults`, 18
  unique provider match IDs, 53,969 bytes, SHA-256
  `a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`.
- There are 36 unique provider match IDs across the two matchdays.
- Saved results include `HalfTime` and `After90Minutes` result types. The
  parser does not treat a half-time score as a final score.

These are source-capture facts, not evidence that Stage 3 SQL import has run.
The importer and test suite are **NOT RUN** in this handoff.

## Stage 3 manual evidence plan

Run the offline dry run first, then the unit tests and static checks, then the
SQL Server import in a controlled database. The expected sequence and SQL
queries are maintained in `docs/MANUAL_RUNBOOK.md`.

Minimum acceptance evidence:

1. Dry runs validate Matchday 3 as 18 matches, 36 results, and the observed
   goals; Matchday 4 as 18 matches with no results or fabricated scores.
2. The first SQL import succeeds and creates one baseline for each fixture.
3. Replaying the same directory leaves match, result, goal, and change counts
   unchanged and creates no new field-level changes.
4. An isolated updated-score fixture creates the intended field-level change
   once, and replaying it does not create another one.
5. A controlled SQL failure rolls back fixture, result, goal, change, and
   checkpoint writes while leaving a useful failed import run when feasible.

## Engineering evaluation plan

All metrics below are planned evaluations, not completed results:

- **Correctness:** valid source rows imported divided by valid rows in the
  sanitized fixture and saved snapshots; separately report rejected records and
  validation issue codes.
- **Duplication rate:** additional matches, results, goals, or changes after a
  byte-identical replay divided by the initial counts; target is zero.
- **Change-detection accuracy:** true positives, false positives, and false
  negatives on controlled before/after fixtures, with field-level precision and
  recall reported separately for fixture, result, and goal changes.
- **Transaction rollback:** verify that a forced failure leaves no partial
  transactional rows and that a retry succeeds without duplicate history.
- **Incremental request efficiency:** later live-source work should request
  only the configured matchdays/checkpoint range and respect the 60 RPM limit;
  it is not implemented in Stage 3.
- **Snapshot replay:** import a saved response repeatedly and compare all
  affected table counts, current values, checksums, and change rows.
- **Latency:** record dry-run parsing time and SQL import wall-clock time for
  each snapshot, including row counts and environment details. No latency claim
  is made before measurement.

## Current handoff

Changed for Stage 3: typed offline ingestion, importer CLI, sanitized tests,
and this documentation. No project commands, tests, SQL, live imports, API
requests, or Git operations were executed for this handoff. The next step is
the manual runbook sequence, stopping at the first failed prerequisite.
