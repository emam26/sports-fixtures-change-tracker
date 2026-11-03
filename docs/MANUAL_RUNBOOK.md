# Manual Runbook

Codex prepares instructions; the user executes them. This file should become the repeatable operating guide as the application is implemented.

Read AGENTS.md for execution rules and BUILD_PLAN.md for current status. None of the operational sections below implies the application already works.

## Terminal and repository

Use WSL/Ubuntu Bash for project terminal commands.

Repository: /mnt/f/sports-fixtures-change-tracker.

The following checks have already been reported by the user:

```bash
cd /mnt/f/sports-fixtures-change-tracker
git status --short --branch
python3 --version
cat /etc/os-release
uname -m
```

They establish environment details only. Results are recorded in BUILD_PLAN.md. Run commands individually and resolve a failure before dependent steps.

## Stage 0 foundation verification

Status: Stage 0 is complete and verified from user-supplied manual execution evidence on 2026-11-02. Codex did not execute the commands. SQL loading/ingestion and every later stage remain not started; Stage 1 retrieval and raw snapshot capture are covered by the separate verification record below.

### WSL Bash, project environment

Working directory: `/mnt/f/sports-fixtures-change-tracker`.

```bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
python -m pip install -e ".[dev]"
if [ ! -f .env ]; then cp .env.example .env; fi
```

Verified result on 2026-11-02: editable project installation succeeded. The local package, `pyodbc==5.3.0`, `python-dotenv`, pytest, and Ruff were available. `.env` is ignored by Git. No password or `.env` contents were recorded.

Edit `.env` locally after copying it. Set `SQL_SERVER_HOST` to the current Windows host address visible from WSL, keep `SQL_SERVER_PORT=1433`, and enter the password only in `.env`. The user-reported address is currently `172.20.80.1`; it may change after a WSL or network restart. Inspect the current candidate with:

```bash
WIN_HOST_IP="$(awk '/^nameserver / {print $2; exit}' /etc/resolv.conf)"
printf 'Use SQL_SERVER_HOST=%s\n' "$WIN_HOST_IP"
```

Do not paste the password or `.env` contents into chat.

### WSL Bash, offline project checks

Working directory: `/mnt/f/sports-fixtures-change-tracker`; keep the virtual environment active.

```bash
python -m pytest
```

Verified result on 2026-11-02: pytest passed 5 tests in 0.13 seconds. This is an offline check and does not establish UCL ingestion or later-stage behavior.

```bash
ruff check .
```

Verified result on 2026-11-02: Ruff check passed. This is a static check and does not establish UCL ingestion or later-stage behavior.

Ruff formatting verification also passed, with 10 files formatted.

### WSL Bash, permanent read-only database check

Working directory: `/mnt/f/sports-fixtures-change-tracker`; use the local `.env` and the active virtual environment. Target: SQL Server `CANVASIT`, database `SportsFixturesTracker`, runtime login `sports_tracker_app`, current reported TCP address `172.20.80.1:1433`.

```bash
python scripts/check_database.py
```

Verified result on 2026-11-02: `scripts/check_database.py` succeeded and reported server `CANVASIT`, login `sports_tracker_app`, database `SportsFixturesTracker`, edition `Standard Developer Edition (64-bit)`, and version `17.0.1000.7`. The script runs a read-only metadata query and did not record or display the password or complete connection string.

## Stage 1 OpenLigaDB retrieval and raw snapshots

Status: Stage 1 is complete, tested, documented, committed, and pushed according to the user's supplied status. Codex did not execute the live requests or verification in this handoff.

Source scope: UEFA Champions League 2026/27; OpenLigaDB shortcut `ucl`; season `2026`; expected league ID `4946`; initial Matchdays 3 and 4. The endpoint is `/getmatchdata/ucl/2026/{matchday}` under `https://api.openligadb.de`.

The source client uses an explicit timeout and descriptive User-Agent, validates only the top-level list, `matchID`, shortcut, season, and league ID, and does not schedule or poll. Successful responses are preserved byte-for-byte as `response.json`; `metadata.json` records provider, URL, source identity, retrieval UTC time, HTTP status, content type, byte count, and SHA-256. Snapshot directories include a UTC timestamp and full hash, and existing snapshots are never overwritten.

### WSL Bash, Stage 1 prerequisites

Working directory: `/mnt/f/sports-fixtures-change-tracker`; use the active `.venv`.

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
ruff format --check .
```

Expected result: HTTPX is installed, the isolated tests pass, Ruff reports no errors, and formatting is clean. The user-supplied results are recorded below; Codex did not run these checks. Stop on the first failure and return only non-secret output.

### WSL Bash, initial UCL captures

Working directory: `/mnt/f/sports-fixtures-change-tracker`; use the local `.env` and active `.venv`. Ensure the source settings identify `ucl`, season `2026`, league ID `4946`, and `data/raw` before making a request.

Run each command separately:

```bash
python scripts/fetch_openligadb.py --matchday 3
python scripts/fetch_openligadb.py --matchday 4
```

Expected result: each command prints a match count, snapshot location, SHA-256 hash, and concise success message. The raw files should be under the configured `data/raw` directory. The user-supplied results for these live commands are recorded below; Codex did not run them. Stop after the first failure and return only non-secret output.

OpenLigaDB read access is documented as limited to 60 requests per minute per IP. Do not use aggressive polling, add scheduling, or repeat requests beyond what is needed for the explicitly selected matchday captures.

## Stage 1 manual verification record — 2026-11-02

This record contains user-supplied evidence. It was not executed by Codex. Stage 1 is complete, tested, documented, committed, and pushed according to the user's supplied status.

From WSL Bash, in the repository root, the reproducible command set is:

```bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
ruff format --check .
python scripts/fetch_openligadb.py --matchday 3
python scripts/fetch_openligadb.py --matchday 3
python scripts/fetch_openligadb.py --matchday 4
```

Observed results supplied for the 2026-11-02 handoff:

- Editable installation succeeded.
- Ruff lint passed.
- Ruff format checking passed with 14 files formatted.
- pytest passed 15 tests in 0.50 seconds.
- The source was curated UEFA Champions League 2026/27 (`ucl`, season `2026`, expected League ID `4946`).
- Matchday 3 returned 18 matches: all 18 were completed, all had results, and all 18 match IDs were unique. The response was 76,432 bytes with SHA-256 `88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`.
- Two Matchday 3 snapshots were preserved at 09:47 and 10:24 UTC, with identical content hashes.
- Matchday 4 returned 18 matches: all 18 were unfinished, all had empty `matchResults` arrays, and all 18 match IDs were unique. The response was 53,969 bytes with SHA-256 `a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`.
- The two matchdays contained 36 unique match IDs. Saved real responses confirmed completed and future-match shapes and included `HalfTime` and `After90Minutes` result types.
- Raw response and metadata files are preserved under `data/raw/`, and `data/raw/` is Git-ignored. Do not add raw snapshot files, `.env`, `.env` contents, or passwords to Git.

Future or unfinished matches must keep scores as `NULL`; missing results must never be converted to zero. Interpret result entries explicitly by `resultType`, including `HalfTime` and `After90Minutes`, rather than choosing a score from an undifferentiated result list.

The OpenLigaDB read limit is 60 requests per minute per IP. Do not use aggressive polling. Stage 1 fetches one requested matchday only and does not implement scheduling or repeated polling.

## Planned engineering evaluations — NOT RUN

These evaluations are planned for later SQL loading and change-tracking stages:

- **Idempotency:** replay an identical snapshot and verify no duplicate current rows, observed changes, or checkpoint updates.
- **Change-detection accuracy:** compare controlled fixture variants and unchanged replays, measuring false positives and false negatives while interpreting result types explicitly.
- **Transaction rollback:** inject a SQL Server batch failure and verify current records, change history, and successful checkpoints are not partially committed.
- **Incremental request efficiency:** measure request counts for active matchdays and later refreshes while respecting the 60-requests-per-minute limit.
- **Snapshot replay:** replay saved response bytes offline and verify hash, provenance, and deterministic downstream results without a network request.

All five evaluations remain NOT RUN. SQL loading, change tracking, retries, recovery, API/UI work, and scheduling are also NOT RUN.

## Stage 2 SQL Server schema design

Status: Stage 2 schema design is implemented in `sql/001_initial_schema.sql` but NOT RUN. The script has not been parsed, executed, deployed, or verified against SQL Server. It creates missing dbo objects only, does not drop or alter existing objects, and issues no permissions. Do not run it as `sports_tracker_app`; that runtime login is intentionally not a DDL administrator.

The schema includes `competitions`, `competition_seasons`, `teams`, `matches`, `match_results`, `match_goals`, `import_runs`, `source_snapshots`, `validation_issues`, `match_changes`, `sync_checkpoints`, and `match_notes`. Raw response bytes remain on disk under Git-ignored `data/raw/`; `source_snapshots` stores metadata and paths only. Future matches retain no fabricated result rows or 0-0 scores. `HalfTime` and `After90Minutes` are distinct result types.

### SSMS, preflight checks before applying the DDL

Where: SSMS, connected with the administrative Windows Authentication session, using a query window whose target is the existing `SportsFixturesTracker` database. Do not paste passwords or `.env` contents into SSMS or chat.

Run this read-only preflight query first:

```sql
USE [SportsFixturesTracker];
GO

SELECT
    DB_NAME() AS database_name,
    SUSER_SNAME() AS executing_login,
    compatibility_level,
    state_desc
FROM sys.databases
WHERE name = DB_NAME();

SELECT
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CONNECT') AS can_connect,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE') AS can_create_table,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'ALTER') AS can_alter_database;

SELECT
    name AS existing_stage2_table
FROM sys.tables
WHERE schema_id = SCHEMA_ID(N'dbo')
  AND name IN
  (
      N'competitions', N'competition_seasons', N'teams', N'matches',
      N'match_results', N'match_goals', N'import_runs', N'source_snapshots',
      N'validation_issues', N'match_changes', N'sync_checkpoints', N'match_notes'
  )
ORDER BY name;
```

Expected result: the database row shows `SportsFixturesTracker` and an online state; the first permission value is `1`; and the final query returns no rows unless a prior or unrelated schema already uses one of these names. If any named table already exists, stop and return only the table names for design review. If the session cannot connect or has no DDL capability, stop without running the schema.

### SSMS, apply and verify the schema manually

After the preflight is clean, open `sql/001_initial_schema.sql` in the same administrative SSMS session, confirm its first executable statement is `USE [SportsFixturesTracker]`, and execute the complete script as one batch sequence. Expected result: SSMS reports successful completion without an error; no data-loading rows are inserted.

Then run this read-only structural check:

```sql
USE [SportsFixturesTracker];
GO

SELECT name AS table_name
FROM sys.tables
WHERE schema_id = SCHEMA_ID(N'dbo')
  AND name IN
  (
      N'competitions', N'competition_seasons', N'teams', N'matches',
      N'match_results', N'match_goals', N'import_runs', N'source_snapshots',
      N'validation_issues', N'match_changes', N'sync_checkpoints', N'match_notes'
  )
ORDER BY name;

SELECT
    OBJECT_SCHEMA_NAME(parent_object_id) AS parent_schema,
    OBJECT_NAME(parent_object_id) AS parent_table,
    name AS foreign_key_name,
    OBJECT_NAME(referenced_object_id) AS referenced_table,
    is_disabled
FROM sys.foreign_keys
WHERE parent_object_id IN
(
    SELECT object_id
    FROM sys.tables
    WHERE schema_id = SCHEMA_ID(N'dbo')
      AND name IN
      (
          N'competitions', N'competition_seasons', N'teams', N'matches',
          N'match_results', N'match_goals', N'import_runs', N'source_snapshots',
          N'validation_issues', N'match_changes', N'sync_checkpoints', N'match_notes'
      )
)
ORDER BY parent_table, foreign_key_name;
```

Expected result: all twelve tables are listed, foreign keys are present and enabled, and no fixture or raw-response rows have been loaded. Return only the non-secret table and foreign-key output. Do not proceed to data loading; that belongs to a later stage.

Planned Stage 2 verification checks, all NOT RUN, are: duplicate provider match identity rejection; orphan foreign-key rejection; NULL/missing results for upcoming fixtures without fabricated 0-0 rows; distinct `HalfTime` and `After90Minutes` result rows; provenance for identical snapshot hashes captured at different times; idempotent reimport without duplicate fixture state or changes; field-level historical change recording; and transaction rollback with checkpoint recovery plus a separately persisted failure diagnostic.

## Required format for future procedures

Every procedure must identify:
- Stage and prerequisites.
- Terminal, SQL client, or browser.
- Working directory, interpreter/environment, database, or API base address.
- Exact command, SQL, request, or action.
- Expected success pattern and what to do if it fails.
- Non-secret evidence to return.
- Whether the procedure has actually been verified.

Do not insert guessed executable names or commands for code that does not yet exist. Add exact steps after Codex implements the corresponding files, then mark them verified only after the user supplies output.

## Project environment and dependencies

Status: Stage 0 project installation and checks are complete and verified from user-supplied evidence dated 2026-11-02.

User-reported evidence: Python 3.14.4 virtual environment created, pyodbc 5.3.0 installed, editable project installation succeeded, Ruff check passed, Ruff formatting check passed with 10 files formatted, and pytest passed 5 tests in 0.13 seconds. Do not modify Conda base.

## Database connection and schema

Status: user-reported connection prerequisites, manual Python connection, and permanent project check are confirmed for Stage 0; no schema or ingestion work has started.

User-reported target and verified check on 2026-11-02: SQL Server `CANVASIT`, Standard Developer Edition (64-bit), version `17.0.1000.7`; database `SportsFixturesTracker`; runtime login `sports_tracker_app`; TCP `172.20.80.1:1433`; ODBC Driver 18 installed; sqlcmd authentication succeeded. No password is recorded here. The Stage 0 script performs only its read-only metadata query; no tables or schema are created.

Record the actual current WSL-visible host if it differs after a restart. Keep actual passwords outside this document.

SQL intended for a query window must be labeled as SQL, with its target database. It must not be pasted into Bash.

## Source capture, imports, and replay

Status: Stage 1 retrieval and raw snapshot capture are implemented and manually verified from user-supplied evidence on 2026-11-02. Codex did not execute the verification. SQL loading, transformation, import, change tracking, retries, rollback, recovery, replay, and later source workflows remain NOT RUN.

Current planned source scope: UEFA Champions League 2026/27 through OpenLigaDB shortcut `ucl`, season `2026`, league ID `4946`. Begin with Matchdays 3 and 4, then expand to all 144 league-phase fixtures and later knockout fixtures. No ingestion is complete or verified.

Stage 1 capture commands and observed outputs are recorded above. After Stages 2–3, document commands to inspect provenance, validate, import, repeat unchanged input, inspect issues, and retry or replay an eligible failed input.

Document the selected data scope and where raw responses and logs are retained. Keep controlled test changes separate from real collected data.

## Tests

Current status: the user reported that the complete test suite passed 15 tests in 0.50 seconds on 2026-11-02. This is user-supplied evidence; Codex did not run the tests. Any earlier pre-verification note stating that the Stage 1 tests were NOT RUN is historical and superseded by that report.

Status: focused Stage 0 configuration tests were reported as passed on 2026-11-02: 5 tests in 0.13 seconds. The complete suite was subsequently reported as passed: 15 tests in 0.50 seconds. These are user-supplied results; Codex did not run the tests.

Run `python -m pytest` from the active WSL virtual environment for the offline configuration tests. Keep separate procedures for SQL Server integration tests, live-source checks, API requests, browser checks, and scheduled-run checks.

Use a dedicated test database for controlled changes and rollback demonstrations. Clearly identify any command that creates, changes, or removes test data. Never infer SQL Server correctness from an unrelated in-memory substitute.

## API and browser

Status: not implemented or verified.

Record the actual local launch command and address after implementation. For each API example, include method, route, request body where needed, expected status, and important response fields.

Record browser checks for filters, match history, import issues, and note creation/editing/deletion. Include empty and failed-request behavior.

## Scheduling

Status: scheduler not selected.

After Stage 6, record setup, inspection, logs, disabling, and removal commands for the chosen scheduler. Use explicit interpreter and working-directory settings. State the requirements for the machine, WSL, and database to remain available.

Only an actual scheduled run establishes that scheduling works.

## Git review and publication

The user performs all Git operations manually. Before publication, review the actual working tree and ignore rules. Commit and push instructions should refer to confirmed changes and the current branch.

## Troubleshooting record

Add entries only for problems actually encountered:
- Symptom and exact failing step.
- Relevant non-secret error.
- Cause supported by the investigation.
- Fix and any files changed.
- User-run verification.
- Remaining uncertainty, if any.

Record missing evidence as unknown rather than supplying an invented successful result.
