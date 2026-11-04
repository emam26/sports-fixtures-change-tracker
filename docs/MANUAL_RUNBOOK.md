# Manual Runbook

## Stage 3–10 verification and local operation — NOT RUN

Run in order and stop at the first failure. Return complete non-secret output.
Never paste `.env`, a password, token, or complete connection string.

### 1. Install updated dependencies

Where: WSL Bash  
Working directory: `/mnt/f/sports-fixtures-change-tracker`

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Expected: editable installation completes without a resolver error.

### 2. Static checks

Where: same WSL Bash and directory.

```bash
ruff check .
ruff format --check .
```

Expected: both exit zero. Stop after either failure and return the diagnostic; do
not auto-format before preserving the evidence.

### 3. Offline tests

```bash
pytest -q -m "not sqlserver"
```

Expected: all selected tests pass without SQL Server or internet access. Return the
summary and warnings.

### 4. Identify and validate immutable snapshots

```bash
find data/raw -type f -name metadata.json -print | sort
```

Copy an exact parent directory from that output into each placeholder:

```bash
python scripts/evaluate_snapshot.py "<SNAPSHOT_DIRECTORY>"
python scripts/import_snapshot.py --snapshot "<SNAPSHOT_DIRECTORY>" --dry-run
```

Expected Matchday 3: 18 unique completed matches and SHA-256
`88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`.
Expected Matchday 4: 18 unique unfinished matches, absent results, and SHA-256
`a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`.
Stop if a hash differs. Do not paste raw response content.

### 5. Read-only SQL Server integration test

Where: WSL Bash. Target: configured dedicated `SportsFixturesTracker` database.

```bash
RUN_SQLSERVER_INTEGRATION=yes pytest -q -m sqlserver
```

Expected: the 12-table schema test passes. This command does not import data.

### 6. Controlled import and replay

```bash
python scripts/import_snapshot.py "<MATCHDAY_3_SNAPSHOT_A>"
python scripts/import_snapshot.py "<MATCHDAY_3_SNAPSHOT_A>"
python scripts/import_snapshot.py "<MATCHDAY_3_SNAPSHOT_B>"
python scripts/import_snapshot.py "<MATCHDAY_4_SNAPSHOT>"
```

Pause after the first command and record the result/goal/change row counts using
the corresponding query in Step 7. Run the exact replay, execute that count query
again, and require all three values to be unchanged before continuing.

Expected domain state: 36 unique provider match IDs, 18 finished and 18 unfinished.
Exact and same-content replay must not duplicate matches/results/goals or create
false changes. Provenance/import counts may grow and are not domain duplicates.

### 7. Verify database invariants

Where: a confirmed SQL client. Target: `SportsFixturesTracker`.

```sql
SELECT COUNT(*) AS matches,
       COUNT(DISTINCT provider_match_id) AS unique_provider_matches,
       SUM(CASE WHEN is_finished = 1 THEN 1 ELSE 0 END) AS finished,
       SUM(CASE WHEN is_finished = 0 THEN 1 ELSE 0 END) AS unfinished
FROM dbo.matches;

SELECT provider_match_id, COUNT(*) AS duplicates
FROM dbo.matches
GROUP BY provider_match_id
HAVING COUNT(*) > 1;

SELECT (SELECT COUNT(*) FROM dbo.match_results) AS result_rows,
       (SELECT COUNT(*) FROM dbo.match_goals) AS goal_rows,
       (SELECT COUNT(*) FROM dbo.match_changes) AS change_rows;

SELECT status, COUNT(*) AS runs
FROM dbo.import_runs
GROUP BY status
ORDER BY status;

SELECT COUNT(*) AS recorded_changes FROM dbo.match_changes;

SELECT provider, scope_key, matchday_number, last_source_update_utc,
       last_processed_at_utc, last_successful_import_run_id
FROM dbo.sync_checkpoints
ORDER BY provider, scope_key;
```

Expected first row: `36 / 36 / 18 / 18`; the match duplicate query returns zero
rows. Capture result/goal/change counts before and after the exact replay; all three
must remain unchanged. Baseline and unchanged replay create no business changes.
Goal count is source-dependent and must be compared with parsed data, not guessed.

### 8. Inspect operations and run the local API

```bash
python scripts/inspect_operations.py --limit 20
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

Expected: Uvicorn listens on `http://127.0.0.1:8000`. In a browser, inspect
`/health`, `/docs`, and `/`. Verify filters, details, changes, operations, responsive
layout, keyboard focus, and that note writes return 403 by default. Stop with
Ctrl+C. Do not return headers containing a note token.

### 9. Live one-shot sync — only after Steps 1–8 pass

This may make source requests and SQL writes:

```bash
python scripts/sync_openligadb.py --matchday 3 --matchday 4
```

Expected: each matchday is safely skipped or captured/imported once. Retries are
bounded. OpenLigaDB permits 60 requests per minute; do not run repeatedly or add
aggressive polling.

### 10. Scheduling handoff — do not activate yet

First verify the wrapper manually:

```bash
bash scripts/run_scheduled_sync.sh --matchday 3 --matchday 4
```

Expected: one pass and no overlap. Logs/lock are under ignored `data/runtime/`.
Inspect a stale lock before manual removal. Scheduler activation remains a manual
user action described in `DEPLOYMENT_LOCAL.md`.

This runbook is for manual execution by the project owner. Commands below are
instructions only; they were not executed during the Stage 3 handoff.

Never include `.env`, a password, or a complete connection string in returned
output. Stop at the first failed prerequisite and report only the non-secret
error and command.

## 1. WSL prerequisites

Where: WSL Bash. Working directory: `/mnt/f/sports-fixtures-change-tracker`.

```bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
python -m pip install --editable '.[dev]'
```

Expected: editable installation completes without an error. If the environment
is not already present, create it with `python3 -m venv .venv` first. The
Windows host IP used by WSL can change after a WSL or network restart, so verify
the current value in `.env` before any SQL Server operation.

Historical owner-supplied Stage 0 evidence from 2026-11-02 records a successful
editable installation, Ruff lint, Ruff formatting with 10 files formatted, and
pytest with 5 tests in 0.13 seconds. It also records a successful database
check against server `CANVASIT`, login `sports_tracker_app`, database
`SportsFixturesTracker`, edition `Standard Developer Edition (64-bit)`, and
version `17.0.1000.7`. Do not treat this historical evidence as Stage 3 import
evidence.

## 2. Static and offline checks

Where: WSL Bash, same directory. These commands do not contact OpenLigaDB or
SQL Server.

```bash
ruff check .
ruff format --check .
python -m pytest -q
```

Expected: Ruff reports no violations, format check reports no required changes,
and the tests pass. These checks are **NOT RUN** as part of this handoff.

Locate the saved snapshot directories without changing them:

```bash
find data/raw/ucl/2026/matchday-3 -name metadata.json -print | sort
find data/raw/ucl/2026/matchday-4 -name metadata.json -print | sort
```

## 3. Dry-run Matchday 3

Where: WSL Bash, same directory. This reads local `response.json` and
`metadata.json` only.

```bash
SNAPSHOT_M3="$(dirname "$(find data/raw/ucl/2026/matchday-3 -name metadata.json -print | sort | head -n 1)")"
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M3" --dry-run
```

Expected success pattern:

```text
Dry run passed: 18 matches, 36 results, 74 goals
Snapshot SHA-256: 88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348
```

The goal count is based on the inspected saved response and should be confirmed
by this dry run. If the selected directory is one of the two identical
Matchday 3 captures, the hash must be the value above.

## 4. Dry-run Matchday 4

```bash
SNAPSHOT_M4="$(dirname "$(find data/raw/ucl/2026/matchday-4 -name metadata.json -print | sort | head -n 1)")"
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M4" --dry-run
```

Expected success pattern:

```text
Dry run passed: 18 matches, 0 results, 0 goals
Snapshot SHA-256: a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245
```

The 18 future fixtures must remain unfinished and must not receive fabricated
zero scores.

## 5. Initial SQL Server import

Where: WSL Bash, same directory. Target: the configured `SportsFixturesTracker`
database on the SQL Server instance in `.env`.

```bash
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M3"
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M4"
```

Expected: each command prints a successful import status, a run ID, the
snapshot location/hash, and counts for matches/results/goals/changes. The first
import establishes the baseline, so normal baseline change count is zero.

If an import fails, the CLI now reports the named SQL operation and a sanitized
underlying exception. It never prints the SQL statement, parameters, connection
string, or password. Preserve only that non-secret diagnostic output for
investigation; do not paste `.env` contents or raw snapshot files.

The primary transaction contains teams, matches, results, goals, changes, and
checkpoints. After a confirmed rollback, the importer may intentionally retain a
source snapshot, competition/season rows, a `Failed` import run, and a validation
issue as separate provenance. Those rows are not partial fixture data and must
not be deleted as routine recovery. If the CLI says rollback failed or that state
is unconfirmed, stop: do not retry the import until the database is inspected.

`dbo.teams.team_icon_url` accepts only optional HTTP(S) URL metadata up to 2,048
characters. OpenLigaDB embedded `data:` images and oversized URLs are imported as
`NULL` with a warning that contains only a type/length summary; the snapshot and
team/match identity remain usable.

Identity-returning SQL batches may expose intermediate non-row results through
ODBC; the importer advances through those result sets before reading the
inserted identity. If the command still fails, return the complete non-secret
error and operation name before retrying.

Rerun the failed command only after recording the diagnostic. Then inspect the
failed import run with the read-only query in Step 7 before retrying.

Do not run a live API fetch as part of this procedure. These imports replay the
immutable saved snapshots and are reproducible offline.

### Read-only recovery inspection after a failed import

Where: a confirmed SQL client. Target: `SportsFixturesTracker`.

```sql
SELECT TOP (20)
    ir.import_run_id,
    ir.status,
    ir.failure_phase,
    ir.error_summary,
    ir.started_at_utc,
    ir.completed_at_utc,
    ss.source_snapshot_id,
    ss.local_directory,
    ss.sha256
FROM dbo.import_runs AS ir
LEFT JOIN dbo.source_snapshots AS ss
    ON ss.source_snapshot_id = ir.source_snapshot_id
WHERE ir.provider = N'OpenLigaDB'
ORDER BY ir.import_run_id DESC;

SELECT
    (SELECT COUNT(*) FROM dbo.teams WHERE provider = N'OpenLigaDB') AS teams,
    (SELECT COUNT(*) FROM dbo.matches WHERE provider = N'OpenLigaDB') AS matches,
    (SELECT COUNT(*) FROM dbo.match_results) AS results,
    (SELECT COUNT(*) FROM dbo.match_goals) AS goals,
    (SELECT COUNT(*) FROM dbo.match_changes) AS changes,
    (SELECT COUNT(*) FROM dbo.sync_checkpoints WHERE provider = N'OpenLigaDB')
        AS checkpoints;

SELECT provider_team_id,
       team_name,
       CASE WHEN team_icon_url IS NULL THEN NULL ELSE LEN(team_icon_url) END
           AS team_icon_url_characters
FROM dbo.teams
WHERE provider = N'OpenLigaDB'
ORDER BY provider_team_id;
```

Purpose: distinguish intentional failed-run provenance from unexpected current
domain rows without deleting anything. Return only the non-secret output. If the
failure run reports a confirmed rollback and no unexpected current rows were
created, rerun the same saved snapshot after completing the offline checks. If
rollback was unconfirmed, stop and return this output for diagnosis.

## 6. Idempotency replay

Replay exactly the same Matchday 3 directory:

```bash
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M3"
```

Expected: the run succeeds, but match/result/goal counts in the database do not
increase and the new run reports zero business changes. The snapshot row is
reused by provider and local directory rather than duplicated.

Record the relevant run IDs and compare the database counts before and after.

## 7. Database verification

Where: a confirmed SQL Server client connected to `SportsFixturesTracker`.
Execute the following read-only query after the imports:

```sql
SELECT status, COUNT(*) AS run_count
FROM dbo.import_runs
GROUP BY status;

SELECT
    (SELECT COUNT(*) FROM dbo.matches) AS matches,
    (SELECT COUNT(*) FROM dbo.match_results) AS results,
    (SELECT COUNT(*) FROM dbo.match_goals) AS goals,
    (SELECT COUNT(*) FROM dbo.match_changes) AS changes,
    (SELECT COUNT(*) FROM dbo.source_snapshots) AS snapshots,
    (SELECT COUNT(*) FROM dbo.sync_checkpoints) AS checkpoints,
    (SELECT COUNT(*) FROM dbo.validation_issues) AS validation_issues;

SELECT TOP (20)
    import_run_id, status, source_snapshot_id, matches_seen, matches_inserted,
    matches_updated, matches_unchanged, matches_rejected, results_seen,
    validation_issue_count, failure_phase, error_summary,
    started_at_utc, completed_at_utc
FROM dbo.import_runs
ORDER BY import_run_id DESC;
```

For a clean run against an otherwise empty Stage 2 database, after Matchday 3,
Matchday 4, and one Matchday 3 replay, the expected domain counts are 36
matches, 36 result rows, 74 goals, and zero changes from the replay. There are
two source snapshots if one directory from each matchday was imported. There
are three successful import runs. Existing rows from earlier manual checks or
other experiments must be reported separately rather than treated as a failed
expectation.

Verify that Matchday 4 has no result rows and that the 36 matches have unique
provider match IDs. Verify that change count does not increase after replay.

## 8. Controlled change-history check

The ordinary unit tests use sanitized local fixtures and a memory store; they do
not need SQL Server. Run them with:

```bash
python -m pytest tests/test_ingestion.py -q
```

The test cases cover initial import, duplicate replay, an updated score,
unfinished matches, invalid records, and transaction failure/recovery. They
must be reported as offline tests, not as SQL Server integration evidence.

For a SQL Server integration check, use a disposable test database or a known
isolated schema. Import a baseline fixture, import one fixture with an explicit
full-time score change, and query `dbo.match_changes` for exactly one intended
field transition. Replay that updated fixture and verify no second transition
is created. Never test controlled changes against production data.

## 9. Rollback and recovery check

Use the sanitized failure-injection test first. For SQL Server, arrange a
controlled failure in an isolated test database only, then verify that current
matches, results, goals, changes, and checkpoints have no partial rows. Confirm
that a failed `import_runs` record is present when the failure occurred after a
run could be recorded. Retry the same snapshot and verify that it succeeds
without duplicates.

## 10. Evaluation record

Record, for each run:

- input snapshot hash and byte count;
- valid/rejected match counts and validation issue codes;
- matches/results/goals inserted, updated, and unchanged;
- change rows created and whether each is a true controlled transition;
- SQL import wall-clock latency and environment details;
- counts before and after an identical replay;
- rollback result and retry result.

These measurements evaluate correctness, duplication rate, change-detection
accuracy, transaction rollback, snapshot replay, and import latency. Incremental
request efficiency and rate-limit compliance are future live-source evaluations;
Stage 3 does not poll or schedule requests. OpenLigaDB’s 60-requests-per-minute
limit must be respected, and aggressive polling is prohibited.
## Manual recovery of the dedicated development database

`sql/manual_reset_development_import_data.sql` is a **manual-only** recovery
script for the current failed-import state. It is not a migration and is not
called by the application. It applies only to the dedicated
`SportsFixturesTracker` development database that was empty before the failed
test imports; it must never be used to discard legitimate development, test, or
production data.

1. In SSMS, select `SportsFixturesTracker`, create a **full backup** through
   **Tasks > Back Up...**, and wait for the SSMS success confirmation. This is
   a prerequisite; the script never creates a backup automatically.
2. Open the script and run its **PREVIEW ONLY** section. Confirm the database
   name, one `source_snapshot_id` of `7`, import run `1` as `Started`, import
   run `2` as `Failed`, both runs pointing to snapshot `7`, and the reported
   development counts: 14 teams, 7 matches, 14 results, and 32 goals. Stop if
   any value differs or if `match_notes` contains a row.
3. Only after confirming that this is the disposable dedicated development
   database, remove the two comment markers around the **DESTRUCTIVE EXECUTION**
   section, replace `@confirmation`'s `NULL` value with
   `N'RESET-DEDICATED-DEVELOPMENT-DATABASE'`, and run that section as one batch.
   Its transaction requires server `CANVASIT`, repeats the scope checks, deletes
   in foreign-key dependency order, and rolls back on an error.
4. Run the preview section again. All twelve application tables listed by the
   script must report zero rows. Do not start another import until this check is
   clean.

The destructive block deliberately stops if the actual state differs from the
reviewed recovery scope. Preserve the backup and return the non-secret SSMS
error or output rather than broadening the deletion scope.
