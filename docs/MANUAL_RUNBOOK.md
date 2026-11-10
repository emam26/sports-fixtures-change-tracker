# Manual Runbook

## Evidence boundary

The owner has already verified the project foundation, raw Matchday 3/4 captures,
the deployed 12-table schema, and the first successful Matchday 3 import (run `3`,
snapshot `8`, 18 inserted matches, 36 results, 74 goals, four safe icon warnings).

Everything below is a manual verification plan for the latest working tree. No new
command in this runbook was executed by Codex. Run in order, stop at the first
failure, and return only non-secret output. Never paste `.env`, passwords, tokens,
complete connection strings, or raw response content.

## 1. Environment and editable installation

Where: WSL Bash  
Working directory: `/mnt/f/sports-fixtures-change-tracker`

```bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
python -m pip install --editable '.[dev]'
```

Purpose: install the current package and development dependencies into the dedicated
project environment. Expected: the prompt uses the project `.venv` and installation
finishes without a resolver error. Stop and return the non-secret error if activation
or installation fails. Do not install into Conda base.

## 2. Static checks

Where: same WSL Bash and directory.

```bash
ruff check .
ruff format --check .
```

Purpose: verify lint and formatting without modifying files. Expected: both commands
exit zero. Stop after the first failure and return its full diagnostic. Do not use
`--fix` during this evidence pass.

## 3. Offline tests

Where: same WSL Bash and directory. These tests must not use SQL Server or internet.

```bash
python -m pytest -q -m "not sqlserver"
```

Expected: all selected tests pass; one SQL Server group may be deselected. Return the
pass/deselect count, elapsed time, and warnings. Stop on a failure.

## 4. Identify and validate immutable snapshots

Where: same WSL Bash and directory.

```bash
find data/raw/ucl/2026/matchday-3 -type f -name metadata.json -print | sort
find data/raw/ucl/2026/matchday-4 -type f -name metadata.json -print | sort
```

Purpose: list evidence without changing it. Expected: two Matchday 3 metadata files
and at least the verified Matchday 4 metadata file. Do not paste raw JSON.

For offline validation, set these variables in WSL Bash by pasting directory paths
from the listing only:

```bash
export SNAPSHOT_M3_DRY='<one verified Matchday 3 snapshot directory>'
export SNAPSHOT_M4='<verified Matchday 4 snapshot directory>'
```

Run offline evaluation and validation:

```bash
python scripts/evaluate_snapshot.py "$SNAPSHOT_M3_DRY"
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M3_DRY" --dry-run
python scripts/evaluate_snapshot.py "$SNAPSHOT_M4"
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M4" --dry-run
```

Expected Matchday 3: 18 matches, 36 results, 74 goals, SHA-256
`88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`.

Expected Matchday 4: 18 matches, zero results, zero goals, SHA-256
`a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`.

Stop if a hash, identity, or count differs.

## 4A. Season discovery and one-time league-phase backfill

The current verified database has Matchdays 3 and 4 only. This procedure preserves
those rows, their field-level change history, immutable snapshots, and synchronization
checkpoints. It never resets or deletes the dedicated development database.

Where: WSL Bash, project directory.

First audit local raw-capture coverage. This is offline and opens neither SQL Server
nor OpenLigaDB:

```bash
python scripts/report_season_coverage.py
```

Expected with the reported current state: the command prints exit status `1` because
the report is intentionally incomplete. Matchdays 3 and 4 have 18 captured fixture
IDs each, while Matchdays 1, 2, 5, 6, 7, and 8 are `not-captured`. `not-captured`
means only that no local immutable snapshot is present; it is not evidence that the
provider lacks those fixtures. Return this non-secret report before continuing.

Where: WSL Bash, project directory. This command makes two bounded read-only provider
requests, writes no raw snapshot, and performs no database import:

```bash
python scripts/discover_openligadb_season.py
```

Expected: it prints the available-groups and full-season URLs, the matchdays each
source view reports, their union, and any disagreement. Stop and return that output if
either endpoint is unavailable, returns no league-phase matchdays, or the views
disagree. Do not treat a full-season response as an importable snapshot.

For each of Matchdays 1, 2, 5, 6, 7, and 8 that discovery explicitly reports as a
league-phase matchday, run this small batch one matchday at a time. Replace only the
matchday number; do not capture Matchdays 3 or 4 again during this backfill:

```bash
python scripts/fetch_openligadb.py --matchday 1
```

Expected: one immutable snapshot location, a SHA-256, and the source match count. If
the provider returns an error, empty/invalid contract, or a count other than the
expected 18, stop. Preserve the output and mark the matchday as a source-data gap; do
not fabricate fixtures or retry aggressively. Respect the documented 60 requests per
minute limit.

For each successfully captured directory, run offline validation before the SQL write:

```bash
export BACKFILL_SNAPSHOT='<Snapshot location printed by fetch_openligadb.py>'
python scripts/evaluate_snapshot.py "$BACKFILL_SNAPSHOT"
python scripts/import_snapshot.py --snapshot "$BACKFILL_SNAPSHOT" --dry-run
python scripts/import_snapshot.py --snapshot "$BACKFILL_SNAPSHOT"
```

Expected: the first two commands have no network or database side effect; the dry run
reports the provider match/result/goal counts without fabricated scores. The final
command reports one successful import. Stop if it reports validation errors, a failed
transaction, or a count that conflicts with the capture output. Do not proceed to the
next matchday until the SQL check below succeeds.

Where: SSMS or another confirmed SQL Server client. Target database:
`SportsFixturesTracker` only.

```sql
USE [SportsFixturesTracker];
GO

IF DB_NAME() <> N'SportsFixturesTracker'
    THROW 50000, 'Wrong database selected; stop without changes.', 1;

SELECT m.matchday_number,
       COUNT(*) AS fixtures,
       COUNT(DISTINCT m.provider_match_id) AS unique_provider_fixture_ids,
       SUM(CASE WHEN m.source_match_is_finished = 1 THEN 1 ELSE 0 END) AS completed,
       SUM(CASE WHEN m.source_match_is_finished = 0 THEN 1 ELSE 0 END) AS upcoming,
       SUM(CASE WHEN m.kickoff_utc IS NULL THEN 1 ELSE 0 END) AS kickoff_not_recorded
FROM dbo.matches AS m
INNER JOIN dbo.competition_seasons AS cs
    ON cs.competition_season_id = m.competition_season_id
INNER JOIN dbo.competitions AS c
    ON c.competition_id = cs.competition_id
WHERE c.provider = N'OpenLigaDB'
  AND c.provider_shortcut = N'ucl'
  AND cs.season_start_year = 2026
GROUP BY m.matchday_number
ORDER BY m.matchday_number;

SELECT ir.matchday_number,
       ir.status,
       COUNT(*) AS import_runs,
       MAX(ir.completed_at_utc) AS latest_completion_utc
FROM dbo.import_runs AS ir
INNER JOIN dbo.competition_seasons AS cs
    ON cs.competition_season_id = ir.competition_season_id
INNER JOIN dbo.competitions AS c
    ON c.competition_id = cs.competition_id
WHERE ir.provider = N'OpenLigaDB'
  AND c.provider_shortcut = N'ucl'
  AND cs.season_start_year = 2026
GROUP BY ir.matchday_number, ir.status
ORDER BY ir.matchday_number, ir.status;

SELECT m.provider_match_id, COUNT(*) AS duplicate_count
FROM dbo.matches AS m
INNER JOIN dbo.competition_seasons AS cs
    ON cs.competition_season_id = m.competition_season_id
INNER JOIN dbo.competitions AS c
    ON c.competition_id = cs.competition_id
WHERE m.provider = N'OpenLigaDB'
  AND c.provider_shortcut = N'ucl'
  AND cs.season_start_year = 2026
GROUP BY m.provider_match_id
HAVING COUNT(*) > 1;
```

Expected: each successfully imported matchday has unique provider IDs, no duplicate
query rows, and an appropriate import-run status. A raw capture without a successful
import run is an importer/workflow issue; a discovery omission or failed source capture
is a source-data availability issue. Return these non-secret aggregates after each
batch. Do not proceed if a duplicate appears or a prior Matchday 3/4 count decreases.

Only after every individually captured matchday is reviewed, rerun:

```bash
python scripts/report_season_coverage.py
```

Do not claim 144 fixtures until this report shows `captured-complete` for all eight
configured league-phase matchdays and the SQL query shows 144 distinct provider
fixture IDs. Knockout-stage groups are outside this one-time backfill and require a
separate source-shape review plus explicit opt-in.

## 5. Database connectivity and read-only integration test

Where: WSL Bash, same directory.  
Target: the configured dedicated `SportsFixturesTracker` database.

```bash
python scripts/check_database.py
RUN_SQLSERVER_INTEGRATION=yes python -m pytest -q -m sqlserver
```

Purpose: confirm the intended server/login/database and deployed 12-table schema
before mutation. Expected connection metadata remains server `CANVASIT`, runtime
login `sports_tracker_app`, database `SportsFixturesTracker`, Standard Developer
Edition (64-bit), version `17.0.1000.7`; the schema test passes. Stop on any mismatch.

## 6. Pre-replay SQL baseline

Where: SSMS or another confirmed SQL Server client.  
Target database: `SportsFixturesTracker` only.

```sql
USE [SportsFixturesTracker];
GO

SELECT CAST(SERVERPROPERTY(N'ServerName') AS nvarchar(128)) AS server_name,
       DB_NAME() AS database_name;

SELECT source_snapshot_id, local_directory, sha256, matchday_number,
       retrieved_at_utc
FROM dbo.source_snapshots
WHERE source_snapshot_id = 8;

SELECT COUNT(*) AS matches,
       COUNT(DISTINCT provider_match_id) AS unique_provider_matches,
       SUM(CASE WHEN source_match_is_finished = 1 THEN 1 ELSE 0 END) AS finished,
       SUM(CASE WHEN source_match_is_finished = 0 THEN 1 ELSE 0 END) AS unfinished
FROM dbo.matches
WHERE provider = N'OpenLigaDB';

SELECT (SELECT COUNT(*) FROM dbo.match_results) AS result_rows,
       (SELECT COUNT(*) FROM dbo.match_goals) AS goal_rows,
       (SELECT COUNT(*) FROM dbo.match_changes) AS change_rows,
       (SELECT COUNT(*) FROM dbo.sync_checkpoints
        WHERE provider = N'OpenLigaDB') AS checkpoint_rows,
       (SELECT COUNT(*) FROM dbo.import_runs
        WHERE provider = N'OpenLigaDB') AS import_run_rows;
```

Purpose: establish the exact before-state and obtain snapshot `8`'s local directory.
Expected source snapshot hash is the verified Matchday 3 hash. Expected domain state
before Matchday 4 remains 18 unique completed matches, 36 results, and 74 goals.
Record all counts. Stop if the server/database identity, hash, or domain state differs.

Where: WSL Bash, project directory. Set the exact replay path using only the
`local_directory` value returned for source snapshot `8`:

```bash
export SNAPSHOT_M3_EXACT='<source_snapshot_id 8 local_directory>'
```

Do not continue if that directory is missing or its offline hash differs from the
verified Matchday 3 hash.

## 7. Exact Matchday 3 replay

Where: WSL Bash, project directory.

```bash
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M3_EXACT"
```

Purpose: test real SQL idempotency against the exact already imported directory.
Expected: `Succeeded`, source snapshot ID `8`, 18 seen, 0 inserted, 0 updated, 18
unchanged, 36 results observed, 74 goals observed, and 0 changes recorded. Four
non-blocking icon warnings can be recorded again because they are source validation
observations.

Immediately rerun the read-only count queries from Step 6. Match/result/goal/change
counts must not change. The checkpoint row and successful snapshot ID remain the
same, while `last_successful_import_run_id` is expected to advance to the successful
replay run. Import-run/validation provenance may increase. Stop if a domain count,
checkpoint row count, or checkpoint snapshot identity changes unexpectedly.

Additional duplicate checks in the SQL client:

```sql
SELECT provider, provider_match_id, COUNT(*) AS duplicate_count
FROM dbo.matches
GROUP BY provider, provider_match_id
HAVING COUNT(*) > 1;

SELECT match_id, provider_result_id, COUNT(*) AS duplicate_count
FROM dbo.match_results
GROUP BY match_id, provider_result_id
HAVING COUNT(*) > 1;

SELECT match_id, provider_goal_id, COUNT(*) AS duplicate_count
FROM dbo.match_goals
GROUP BY match_id, provider_goal_id
HAVING COUNT(*) > 1;
```

Expected: all three queries return zero rows.

## 8. Import Matchday 4

Where: WSL Bash, project directory.

```bash
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M4"
```

Purpose: import the saved unfinished-fixture shape without a network request.
Expected: `Succeeded`, 18 seen and inserted, 0 result records, 0 goal records, and no
fabricated business changes for the new baseline.

Verify in the confirmed SQL client:

```sql
USE [SportsFixturesTracker];
GO

SELECT COUNT(*) AS matches,
       COUNT(DISTINCT provider_match_id) AS unique_provider_matches,
       SUM(CASE WHEN source_match_is_finished = 1 THEN 1 ELSE 0 END) AS finished,
       SUM(CASE WHEN source_match_is_finished = 0 THEN 1 ELSE 0 END) AS unfinished
FROM dbo.matches
WHERE provider = N'OpenLigaDB';

WITH result_counts AS
(
    SELECT match_id, COUNT(*) AS result_rows
    FROM dbo.match_results
    GROUP BY match_id
),
goal_counts AS
(
    SELECT match_id, COUNT(*) AS goal_rows
    FROM dbo.match_goals
    GROUP BY match_id
)
SELECT m.matchday_number,
       COUNT(*) AS matches,
       SUM(CASE WHEN m.source_match_is_finished = 1 THEN 1 ELSE 0 END) AS finished,
       SUM(COALESCE(rc.result_rows, 0)) AS result_rows,
       SUM(COALESCE(gc.goal_rows, 0)) AS goal_rows
FROM dbo.matches AS m
LEFT JOIN result_counts AS rc ON rc.match_id = m.match_id
LEFT JOIN goal_counts AS gc ON gc.match_id = m.match_id
WHERE m.provider = N'OpenLigaDB'
GROUP BY m.matchday_number
ORDER BY m.matchday_number;

SELECT m.provider_match_id, mr.result_type_kind,
       mr.points_team1, mr.points_team2
FROM dbo.matches AS m
INNER JOIN dbo.match_results AS mr ON mr.match_id = m.match_id
WHERE m.provider = N'OpenLigaDB'
ORDER BY m.provider_match_id, mr.result_order_id;

SELECT provider, scope_key, matchday_number,
       last_source_update_utc, last_processed_at_utc,
       last_successful_snapshot_id, last_successful_import_run_id
FROM dbo.sync_checkpoints
WHERE provider = N'OpenLigaDB'
ORDER BY matchday_number;
```

Use the following independent totals as a second check:

```sql
SELECT (SELECT COUNT(*) FROM dbo.matches
        WHERE provider = N'OpenLigaDB') AS matches,
       (SELECT COUNT(*) FROM dbo.match_results) AS result_rows,
       (SELECT COUNT(*) FROM dbo.match_goals) AS goal_rows,
       (SELECT COUNT(*) FROM dbo.match_changes) AS change_rows;
```

Expected state for the historical Matchday 3/4 proof only: 36 matches / 36 unique
provider match IDs, 18 finished, 18 unfinished, 36 result rows, and 74 goal rows.
The preserved Matchday 4 capture has no result or goal rows, while Matchday 3 retains
explicit `HalfTime` and `After90Minutes` rows. The owner’s later current-database
evidence reports all 36 fixtures finished after subsequent source observations; do
not confuse that current state with the immutable historical capture. The league-
phase backfill changes totals only through separately preserved, validated snapshots;
do not reuse this 36-fixture baseline as a full-season expectation.

## 8A. Reviewed Matchday 2 conflicting-result recovery

This is a manual, one-snapshot recovery for the reported Matchday 2 source conflict
in match `87412` (Viking vs FC Bayern München). The strict parser remains the default.
Do not use the recovery option for an unrelated snapshot or for a source record that
has not been reviewed. The option quarantines both conflicting `HalfTime` records
(`129519: 2-0` and `129520: 0-0`); it never chooses one. The unambiguous
`After90Minutes` record `129521: 3-3` is retained only after the existing result,
goal, team, identity, and timestamp validation passes.

The raw response and metadata must remain unchanged. The deployed schema requires one
`match_results` row per result type, so the quarantined source records are preserved
by the immutable raw snapshot and an auditable `validation_issues` row, not silently
discarded or forced into a second `HalfTime` row. Synchronization does not enable this
option automatically.

Where: SSMS or another confirmed SQL Server client. Target database:
`SportsFixturesTracker` only. First retrieve the exact local directory for source
snapshot `17`; do not infer it from a filename:

```sql
USE [SportsFixturesTracker];
GO

IF DB_NAME() <> N'SportsFixturesTracker'
    THROW 50000, 'Wrong database selected; stop without changes.', 1;

SELECT source_snapshot_id,
       provider,
       matchday_number,
       local_directory,
       sha256,
       byte_count
FROM dbo.source_snapshots
WHERE source_snapshot_id = 17;
```

Return only the non-secret directory, hash, byte count, and matchday. Stop if the
row is absent, the database name is wrong, or the directory is not the preserved
Matchday 2 capture. In WSL, set the returned directory manually:

```bash
export SNAPSHOT_M2='<source_snapshot_id 17 local_directory>'
```

Where: WSL Bash, project directory. These commands are offline and do not write SQL
data or call OpenLigaDB. First prove that strict validation still rejects the source
conflict:

```bash
python scripts/evaluate_snapshot.py "$SNAPSHOT_M2"
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M2" --dry-run
```

Expected: the strict dry run exits non-zero and reports
`duplicate-result-type` with both result IDs and values. Stop if the raw response
hash or the reported conflict differs from the reviewed values.

Now run the explicitly enabled offline recovery validation:

```bash
python scripts/evaluate_snapshot.py \
  "$SNAPSHOT_M2" \
  --allow-conflicting-nonfinal-results
python scripts/import_snapshot.py \
  --snapshot "$SNAPSHOT_M2" \
  --dry-run \
  --allow-conflicting-nonfinal-results
```

Expected: the dry run reports warning
`conflicting-nonfinal-result-quarantined`, names `129519`/`2-0` and
`129520`/`0-0`, retains one final result `129521`/`3-3`, and reports no validation
errors. It must not print Base64 data, a password, or a complete connection string.
Stop if final-vs-goal consistency or any other validation fails.

Before the SQL write, record the response hash without displaying response content:

```bash
sha256sum "$SNAPSHOT_M2/response.json"
```

The digest must equal the `sha256` returned by the SSMS query. Only after that review,
run the one write command:

```bash
python scripts/import_snapshot.py \
  --snapshot "$SNAPSHOT_M2" \
  --allow-conflicting-nonfinal-results
```

Expected: one successful import for snapshot `17`, `Results observed: 3`, one
persisted result row for this match, and a warning count including the quarantine
issue. A replay of the same command is allowed only as an explicit idempotency check;
it must not add a match, result, goal, or change-history row. A replay may add a new
warning row tied to its own import-run provenance. Do not rerun aggressively or
enable the flag for synchronization.

Where: SSMS, same target database. Run these read-only checks after the import:

```sql
USE [SportsFixturesTracker];
GO

IF DB_NAME() <> N'SportsFixturesTracker'
    THROW 50000, 'Wrong database selected; stop without changes.', 1;

SELECT m.provider_match_id,
       mr.provider_result_id,
       mr.result_type_kind,
       mr.points_team1,
       mr.points_team2
FROM dbo.matches AS m
INNER JOIN dbo.match_results AS mr ON mr.match_id = m.match_id
WHERE m.provider = N'OpenLigaDB'
  AND m.provider_match_id = 87412
ORDER BY mr.provider_result_id;

SELECT validation_issue_id,
       import_run_id,
       source_snapshot_id,
       source_record_type,
       source_record_id,
       issue_code,
       severity,
       issue_message,
       source_value
FROM dbo.validation_issues
WHERE source_snapshot_id = 17
  AND issue_code = N'conflicting-nonfinal-result-quarantined'
ORDER BY validation_issue_id;

SELECT import_run_id,
       status,
       failure_phase,
       error_summary,
       results_seen,
       validation_issue_count,
       completed_at_utc
FROM dbo.import_runs
WHERE source_snapshot_id = 17
ORDER BY import_run_id DESC;
```

Expected for match `87412`: an `After90Minutes` row with `3-3`, no new `HalfTime`
row from this recovery, and a result-type validation issue containing both source IDs
and score values. A pre-existing `HalfTime` row from an earlier successful observation
is not deleted or replaced by this procedure; if the query shows one, stop and review
its prior provenance before treating the current match as resolved. The raw snapshot
remains the authority for the two quarantined records.
If the enabled dry run fails, do not run the write command; return the non-secret
validation output for diagnosis. If the SQL import fails, verify that no partial
fixture/result/goal/change/checkpoint rows were committed and that only the normal
failed-run provenance was recorded. Do not delete or reset existing data as part of
this recovery.

## 9. Inspect operations

Where: WSL Bash, project directory.

```bash
python scripts/inspect_operations.py --limit 20
```

Purpose: display non-secret import/checkpoint diagnostics. Expected: the verified
historical runs/checkpoints remain present, and each later backfill matchday has its
own successful run/checkpoint only after import succeeds. Return IDs, statuses,
counts, and timestamps only.

## 10. API and dashboard

Where: WSL Bash, project directory.

```bash
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

Expected: Uvicorn listens on `http://127.0.0.1:8000`. Keep that terminal open.

If a dashboard opened before a source update reports HTTP 404 for all `/api/insights/*`
requests, first stop the old project Uvicorn process with Ctrl+C and rerun this command
from the current checkout. The verified temporary port-8765 server is separate from port
8000; changing the frontend to use port 8765 is not a fix. After restart, hard-reload `/`
and confirm the browser requests the current `/assets/app.js` and `/assets/styles.css`.

Where: browser on the same machine.  
Base address: `http://127.0.0.1:8000`

1. Open `/health`; expect `status=ok`, `database=available`.
2. Open `/docs`; inspect the documented status, competition, matchday, fixture,
   read-only Insights, checkpoint, import, validation, and note endpoints.
3. Open `/` with a hard reload. Confirm the public navigation and page order are
   Overview, Match Explorer, Insights, and Change Intelligence. Each section must show a visible loading
   or data state rather than collapsing into an unexplained blank content area. There
   must be no Import & Sync Monitor link or visible operations cards.
4. In browser developer tools, confirm `/assets/styles.css` and `/assets/app.js`
   return `200`. The public page must not request `/api/import-runs`,
   `/api/sync-checkpoints`, or `/api/validation-issues`; those remain local diagnostic
   APIs. Return the non-secret console/network diagnostic if an asset fails or an
   operational request is made.
5. Confirm the competition selector and matchdays are discovered from the database.
   Select the available season and confirm overview values refresh. Verify that **Last
   updated** matches the latest successful synchronization timestamp returned by
   `/api/dashboard-summary`, or reads `Not recorded` when no such timestamp exists.
   It must not display snapshot/import-run IDs or imply a newer source observation.
   Confirm `/api/freshness` returns an opaque revision and that the small browser
   check indicator is separate from the database synchronization timestamp.
6. Open the Insights section. Confirm its cards, matchday goal trend, result split,
   team comparison, team search/sort, recent-results detail, and highest-scoring
   completed-match list are populated only from the selected local season. The UI
   must show an explicit empty/error state when analytics routes fail; it must not
   invent scores for unfinished fixtures. The source's final-score result is used, valid
   `0-0` results count, and observed goal-event counts remain distinct from full-time
   score totals. Confirm the Insights source line uses the latest successful
   synchronization timestamp or says `Not recorded`, never a browser-generated
   refresh claim. Select a matchday bar and confirm it moves the Match Explorer to
   that loaded matchday without fabricating any fixture.
7. Filter by matchday, status, team, and kickoff order; clear filters and confirm
   recovery. The recommended All order must show all completed matches together from
   newest to oldest kickoff, then nearest upcoming fixtures. Completed must show newest
   first and Upcoming nearest first. Known kickoffs must precede missing kickoffs;
   equal kickoffs must remain deterministic. An unmatched team search must show a useful
   empty state.
8. Open completed and unfinished fixture details. Confirm future score reads "Not
   supplied", while completed results retain explicit types and goal events.
9. Inspect global and per-fixture changes. Confirm related result/goal fields from one
   observation are grouped into readable events with Inserted, Updated, or Removed
   badges; use the disclosure to inspect mapped field details. Technical field names
   must not be primary labels, inserted records must not read as `Not supplied →
   value`, and long detail histories must scroll vertically without overlapping text.
   Confirm observation/capture times are clearly provenance, not a goal occurrence
   time, and that source snapshot identity appears only for recorded business changes.
10. Use keyboard-only navigation and a narrow browser width; confirm focus and dialog
   controls remain usable. After the page initially loads, simulate offline mode in
   browser developer tools and use a dashboard refresh button; expect a visible safe
   API error panel rather than silent disappearance.
11. With default configuration, confirm note-write controls explain that writes are
   disabled and note writes return 403 in `/docs`.
12. Stop Uvicorn with Ctrl+C.

13. Leave the dashboard open while a separate manual synchronization completes.
    Confirm the browser checks `/api/freshness` while visible, reloads the data panels
    only after the returned revision changes, and preserves the active section,
    Match Explorer filters/sort, and Change Intelligence page. Temporarily block the
    freshness request in developer tools and confirm the current data remains visible
    with a bounded retry message. Hide the tab and confirm freshness polling pauses;
    make it visible again and confirm one check resumes.

For a read-only API smoke check while Uvicorn is running, use WSL Bash in the
project directory:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/api/insights/summary
curl --fail --silent --show-error http://127.0.0.1:8000/api/insights/teams
curl --fail --silent --show-error http://127.0.0.1:8000/api/freshness
curl --fail --silent --show-error http://127.0.0.1:8000/api/insights/matchdays
```

Expected: HTTP 200 JSON responses. If the selection contains no loaded records,
zero/empty analytics are valid. To inspect one team, take a `provider_team_id` from
the teams response and request `/api/insights/teams/{provider_team_id}`; do not
paste secrets or complete environment configuration into the terminal transcript.

If local note writes are deliberately enabled in `.env`, use a new local token of at
least 16 characters, restart the API, and test create/edit/archive through the
dashboard. Enter the token only into the password field. Confirm the note disappears
after archive and that source fixture/result values do not change. Disable writes
again after the demonstration. Never return or screenshot the token.

### Portfolio demonstration and screenshot checklist

Create screenshots only after the corresponding check has passed. Suggested evidence:

- fixture board filtered to completed Matchday 3;
- fixture board filtered to unfinished Matchday 4 with "Not supplied" scores;
- one completed fixture detail showing explicit result types and goals;
- overview showing the accurate Last updated indicator for the loaded selection;
- terminal summaries for Ruff, offline pytest, and non-secret SQL count checks;
- one narrow viewport demonstrating the responsive layout and visible focus state.

Crop out terminal history and unrelated applications. Never capture `.env`, a note
token field containing a value, raw snapshot content, passwords, complete connection
strings, private backup paths, or failed diagnostics containing sensitive local data.
Caption real source/import evidence separately from synthetic change/rollback tests.

## 11. Live one-shot synchronization

Prerequisite: Steps 1-10 all passed. This step makes real OpenLigaDB requests and SQL
writes. OpenLigaDB's documented limit is 60 requests per minute. The command is a
bounded one-shot process; it is not a daemon and must not be placed in an infinite
FastAPI background loop.

The normal scheduler-ready invocation is:

Where: WSL Bash, project directory.

```bash
python scripts/sync_openligadb.py
```

The command reads local fixture/checkpoint state before selecting work. It prioritizes
unseen groups, unfinished fixtures whose kickoff is within the configured
`OPENLIGADB_NEAR_KICKOFF_WINDOW_MINUTES` or has passed while still unfinished, recent
completed matchdays, and older matchdays after
`OPENLIGADB_OLDER_MATCHDAY_INTERVAL_HOURS`. Rechecks are bounded by the configured
near-kickoff and recent-completion intervals, and at most
`OPENLIGADB_MAX_MATCHDAYS_PER_RUN` matchdays are selected. Missing kickoff values are
not scheduled values. The structured `sync_matchdays_selected` event records the
reason for every selected matchday.

For a one-time source-discovery/backfill planning pass, use:

```bash
python scripts/sync_openligadb.py --discover
```

Discovery compares both provider views and adds only explicit groups within the
configured league-phase scope to the same bounded planner. For a reviewed one-time
backfill, bypass the planner for named groups:

```bash
python scripts/sync_openligadb.py --matchday 5
```

Repeat the command with one `--matchday` per invocation when a specific backfill must
be auditable. Do not use the manual conflict-recovery flag in synchronization; the
known Matchday 2 conflicting HalfTime records remain strict failures and require the
reviewed snapshot-import procedure in section 8A.

Expected: each selected matchday is imported or reliably skipped once. A failed
last-change signal triggers a conservative full fetch. One matchday failure does not
hide another selected outcome, but the overall exit is non-zero. Exit code `3` means
the lock was already held; no synchronization work should be repeated until the owner
of the lock is checked. Do not rerun aggressively.

Inspect logs and database state:

```bash
tail -n 50 data/runtime/logs/sync.jsonl
python scripts/inspect_operations.py --limit 20
```

Return event names, matchdays, selection reasons, statuses, hashes, run IDs, and
timestamps only. Stop if a log contains any secret or if a checkpoint advances
without a successful import.

## 12. Wrapper and Task Scheduler

Where: WSL Bash, project directory.

```bash
bash scripts/run_scheduled_sync.sh
```

Expected: the same stored-state, bounded one-shot behavior and exit codes documented
in [DEPLOYMENT_LOCAL.md](DEPLOYMENT_LOCAL.md). Use the `--discover` argument only for
a deliberate provider-discovery/backfill pass. Do not activate a scheduled trigger
until the wrapper passes and SQL/log evidence is reviewed.

Where: Windows PowerShell.

```powershell
wsl.exe --list --verbose
```

Use the confirmed distribution name in Task Scheduler exactly as documented in
`DEPLOYMENT_LOCAL.md`. Select "Do not start a new instance". The application lock is
the second guard. Do not put secrets in task arguments or descriptions.

## 13. Final Git review, commit, and push

Prerequisite: all intended evidence is recorded in `docs/BUILD_PLAN.md`. The project
owner performs every Git operation.

Where: WSL Bash, project directory.

```bash
git status --short
git diff --check
git diff --stat
git diff
git ls-files .env data/raw data/runtime data/backups
```

Expected: review every changed file; `git diff --check` is clean; the final command
prints no secret/local artifact. Also confirm a representative raw file and local
backup are ignored without adding them:

```bash
git check-ignore -v .env
git check-ignore -v data/raw/ucl/2026/matchday-3
git check-ignore -v data/runtime/sync.lock
git check-ignore -v example-local-backup.bak
```

Stage only reviewed project files, inspect the staged diff, then commit and push to
the already intended branch/remote:

```bash
git add -- .gitignore .env.example README.md pyproject.toml docs scripts sql src tests
git status --short
git diff --cached --check
git diff --cached
git commit -m "Complete local fixture tracker implementation"
git push
```

Stop before commit if `.env`, `data/raw/`, `data/runtime/`, database backups, unrelated
work, or a secret appears in the staged set. Do not change Git identity, rewrite
history, force-push, or delete unrelated modifications.
