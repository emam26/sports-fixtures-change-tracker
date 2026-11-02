# Build Plan and Progress

This is the changing implementation record. PROJECT_ROADMAP.md defines the stages; this file tracks current work, decisions, evidence, and the next action.

Prepared: 2026-10-25. These starter documents were prepared outside the user's checkout. Adding them does not establish that application code exists. Codex must inspect the actual repository.

## Current stage

Stage 1 — OpenLigaDB source retrieval and raw snapshot capture. Implemented and manually verified on 2026-11-02; not committed or pushed.
Stage 0 — setup and planning. Complete and verified on 2026-11-02.

Confirmed from user-reported command output on 2026-11-01:
- SQL Server host: CANVASIT.
- SQL Server edition: Standard Developer Edition.
- SQL Server version: 17.0.1000.7.
- Database: SportsFixturesTracker.
- Runtime login: sports_tracker_app.
- TCP connectivity from WSL: 172.20.80.1:1433.
- ODBC Driver 18 is installed.
- sqlcmd authentication succeeded.
- A Python 3.14.4 virtual environment was created.
- pyodbc 5.3.0 was installed.
- A manual Python connection succeeded.
- No password was recorded in this document.

Implemented in this checkout:
- A standard `src/sports_tracker` package layout.
- Environment-backed and validated SQL Server settings with ODBC-safe escaping.
- A reusable pyodbc connection helper.
- A read-only `scripts/check_database.py` metadata check.
- Focused offline configuration tests and basic pytest/Ruff configuration.

Unconfirmed or NOT RUN:
- No SQL import, schema, API, UI, or scheduler checks have been performed. Live OpenLigaDB retrieval and raw snapshot capture are covered by the Stage 1 evidence below.
- SQL loading, change tracking, retries, rollback, recovery, API, UI, scheduling, and later-stage evaluations remain NOT RUN.
- `docs/PROJECT_ROADMAP.md` is referenced by `AGENTS.md` but is absent from this checkout.

Current planned scope:
- Competition: UEFA Champions League 2026/27.
- OpenLigaDB shortcut: `ucl`.
- Season: `2026`.
- League ID: `4946`.
- Initial scope: Matchdays 3 and 4.
- Expansion scope: all 144 league-phase fixtures, followed by later knockout fixtures.
- SQL ingestion is not complete or verified; Stage 1 source retrieval and raw snapshot capture are verified separately below.

Stage 1 implementation in this checkout:
- HTTPX runtime dependency and source configuration for the OpenLigaDB base URL, shortcut, season, league ID, timeout, and raw directory.
- Reusable client for one requested matchday with explicit timeout, descriptive User-Agent, safe URL construction, custom network/HTTP/body/JSON errors, and basic identity checks.
- Immutable raw snapshot writer for exact response bytes and provenance metadata, using timestamp/hash directories and no-overwrite behavior.
- `scripts/fetch_openligadb.py` with required `--matchday` and concise success/error output.
- Isolated MockTransport tests for endpoint construction, snapshots, hashing, no-overwrite behavior, invalid JSON, identity failure, and HTTP failure.

Verified Stage 1 evidence supplied by the user on 2026-11-02:
- Editable installation completed successfully.
- Ruff lint passed.
- Ruff format check passed: 14 files formatted.
- pytest passed: 15 tests in 0.50 seconds.
- Source: curated UEFA Champions League 2026/27; shortcut `ucl`; season `2026`; expected League ID `4946`.
- Matchday 3: 18 matches; all 18 completed; all had results; 18 unique match IDs; 76,432 response bytes.
- Matchday 3 SHA-256: `88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`.
- Two preserved Matchday 3 snapshots were captured at 09:47 and 10:24 UTC on 2026-11-02 with identical content hashes.
- Matchday 4: 18 matches; all 18 unfinished; all had empty `matchResults` arrays; 18 unique match IDs; 53,969 response bytes.
- Matchday 4 SHA-256: `a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`.
- The two matchdays contained 36 unique match IDs in total.
- Raw response and metadata files are preserved under `data/raw/`, which is Git-ignored.
- Completed and future match data shapes were verified against saved real API responses; result types included `HalfTime` and `After90Minutes`.
- No password, `.env` contents, or raw snapshot files are recorded in Git or this document.

Verified Stage 0 evidence supplied by the user on 2026-11-02:
- Editable project installation succeeded.
- Ruff check passed.
- Ruff formatting check passed with 10 files formatted.
- pytest passed: 5 tests in 0.13 seconds.
- `scripts/check_database.py` succeeded.
- Server: CANVASIT.
- Login: sports_tracker_app.
- Database: SportsFixturesTracker.
- Edition: Standard Developer Edition (64-bit).
- Version: 17.0.1000.7.
- `.env` is ignored by Git.
- No password or `.env` contents were recorded.

## Stage tracker

| Stage | Deliverable | Completion evidence | Status |
| --- | --- | --- | --- |
| 0 | Environment, SQL connection, instructions, plan | Dedicated interpreter and successful connection query | Complete and verified (2026-11-02) |
| 1 | Real UCL matchday capture and validated source contract | Capture manifest and passing offline checks | Implemented; manually verified 2026-11-02; not committed or pushed |
| 2 | SQL schema and repeatable first import | Reconciliation and duplicate-free rerun | Not started |
| 3 | Observed changes, recovery, incremental UCL league-phase and knockout imports | Controlled change, rollback, retry, and reconciliation | Not started |
| 4 | FastAPI and local notes CRUD | Normal, missing, and invalid request checks | Not started |
| 5 | HTML/CSS/JavaScript interface | Browser review and notes workflow | Not started |
| 6 | Scheduled imports | Evidence of a real scheduled run and logs | Not started |
| 7 | Final verification, docs, demo, GitHub publication | Final checklist and published implementation | Not started |

## Evidence ledger

These results were supplied by the user; they were not independently executed by Codex.

| Evidence | Check | Supplied result | What it establishes |
| --- | --- | --- | --- |
| E001 | git status --short --branch | main...origin/main with no file entries | Reported branch and clean working tree at that time |
| E002 | python3 --version | Python 3.13.13 | Version of the invoked interpreter |
| E003 | cat /etc/os-release | Ubuntu 26.04 LTS | Reported distribution |
| E004 | uname -m | x86_64 | Reported architecture |
| E005 | SQL Server identity and version | CANVASIT; Standard Developer Edition; 17.0.1000.7 | User-reported SQL Server target |
| E006 | Database and runtime login | SportsFixturesTracker; sports_tracker_app | User-reported database target and login |
| E007 | WSL TCP connectivity | 172.20.80.1:1433 | User-reported network reachability |
| E008 | ODBC and sqlcmd prerequisites | ODBC Driver 18 installed; sqlcmd authentication succeeded | User-reported driver and CLI checks |
| E009 | Python prerequisites | Python 3.14.4 virtual environment; pyodbc 5.3.0 installed | User-reported environment setup |
| E010 | Manual Python connection | Succeeded | User-reported connection evidence; not the permanent project check |
| E011 | Editable project installation | Succeeded | User-reported Stage 0 installation evidence |
| E012 | Ruff check | Passed | User-reported static check evidence |
| E013 | Ruff formatting check | Passed; 10 files formatted | User-reported formatting evidence |
| E014 | pytest | Passed; 5 tests in 0.13 seconds | User-reported offline test evidence |
| E015 | `scripts/check_database.py` | Succeeded; CANVASIT; sports_tracker_app; SportsFixturesTracker; Standard Developer Edition (64-bit); 17.0.1000.7 | User-reported read-only SQL Server check evidence |
| E016 | `.env` ignore rule | `.env` is ignored by Git | User-reported ignore-rule evidence |

| E017 | Stage 1 installation and quality checks | Editable installation succeeded; Ruff lint passed; Ruff format check passed with 14 files formatted; pytest passed 15 tests in 0.50 seconds | User-reported Stage 1 verification evidence |
| E018 | Matchday 3 source capture | 18 completed matches; results present; 18 unique IDs; 76,432 bytes; SHA-256 `88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348` | User-reported saved-response evidence |
| E019 | Matchday 3 repeat snapshot | Snapshots at 09:47 and 10:24 UTC on 2026-11-02; identical content hashes | User-reported preservation and repeat-capture evidence |
| E020 | Matchday 4 source capture | 18 unfinished matches; empty `matchResults` arrays; 18 unique IDs; 53,969 bytes; SHA-256 `a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245` | User-reported saved-response evidence |
| E021 | Cross-matchday identity and result shapes | 36 unique IDs; completed/future shapes verified; `HalfTime` and `After90Minutes` result types observed | User-reported source-contract evidence |
| E022 | Raw-data ignore boundary | Responses and metadata under `data/raw/`; `data/raw/` Git-ignored | User-reported repository-boundary evidence |

Treat E005–E016 as Stage 0 evidence and E017–E022 as Stage 1 evidence only; they do not verify SQL loading or later stages. Keep large logs and raw snapshots local; record concise relevant results without secrets.

## Planned engineering evaluation for later stages

These evaluations are planned and remain NOT RUN. They belong to the SQL loading and change-tracking stages, not to the current Stage 1 retrieval implementation:

- **Idempotency:** replay an identical saved snapshot and verify that it creates no duplicate current rows, observed-change rows, or checkpoint updates.
- **Change-detection accuracy:** use controlled fixture variants and saved source snapshots to measure true changes, unchanged replays, false positives, and false negatives. Result types, including `HalfTime` and `After90Minutes`, must be interpreted explicitly.
- **Transaction rollback:** inject a failure during a SQL Server batch and verify that current records, change history, and successful checkpoints are not left partially committed.
- **Incremental request efficiency:** measure requests needed for the active matchdays and later incremental refreshes, while remaining below OpenLigaDB's 60-requests-per-minute limit and avoiding aggressive polling.
- **Snapshot replay:** replay preserved response bytes offline and verify the recorded hash, provenance, and deterministic downstream outcome without contacting OpenLigaDB.

Future or unfinished matches must retain `NULL` scores. Missing results must never be converted to zero, and a result must not be selected without checking its explicit result type.

## Decisions

| Decision | Status | Reason |
| --- | --- | --- |
| Python, SQL Server, FastAPI, plain HTML/CSS/JS | Agreed stack | Covers collection, relational storage, API, and review UI |
| WSL Bash; repository on F drive | Confirmed preference | User-selected workflow |
| All operational execution is manual | Confirmed requirement | User runs terminal, SQL, API, browser, scheduling, and Git steps |
| UCL Matchdays 3 and 4 before all 144 league-phase fixtures | Agreed sequence | Makes correctness and troubleshooting manageable |
| Configurable competition parameters | Required design constraint | Keep shortcut, season, league ID, and matchday selection reusable while the current scope remains UCL-only |
| All-or-nothing current-record update per matchday | Proposed for implementation | Avoids partially applied invalid batches |
| SQL Server host, auth, and driver | User evidence supplied | CANVASIT, SportsFixturesTracker, sports_tracker_app, TCP 172.20.80.1:1433, and ODBC Driver 18 are recorded; the permanent project check remains NOT RUN |
| Scheduler | Unresolved | Deferred until the import is reliable |

## Stage 0 verification handoff - 2026-11-02

This historical Stage 0 handoff is superseded by the Stage 1 verification handoff below. Stage 0 remains complete and verified: editable installation succeeded; Ruff lint passed; Ruff format checking passed with 10 files formatted; pytest passed 5 tests in 0.13 seconds; `scripts/check_database.py` succeeded; and `.env` is Git-ignored. No password or `.env` contents are recorded. The permanent current status is Stage 1 implemented and manually verified, with SQL loading and every later stage still not started.

## Stage 1 verification handoff - 2026-11-02

Stage 1 was implemented and manually verified by the user on 2026-11-02. It has not been committed or pushed. The following commands are the reproducible manual verification set; they were not executed by Codex in this handoff:

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

The user reported that editable installation succeeded, Ruff lint passed, Ruff format checking passed with 14 files formatted, and pytest passed 15 tests in 0.50 seconds. The two Matchday 3 fetches preserved snapshots captured at 09:47 and 10:24 UTC with identical content hashes. Matchday 3 produced 18 completed matches with results, 18 unique IDs, 76,432 response bytes, and SHA-256 `88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`. Matchday 4 produced 18 unfinished matches with empty `matchResults` arrays, 18 unique IDs, 53,969 response bytes, and SHA-256 `a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`. There were 36 unique match IDs across both matchdays.

The saved real responses confirmed completed and future-match data shapes, including `HalfTime` and `After90Minutes` result types. Raw response and metadata files are preserved under `data/raw/`, which is Git-ignored. No password, `.env` content, or raw snapshot contents are recorded here.

SQL loading, schema creation, change tracking, retries, recovery, API/UI work, scheduling, and the engineering evaluations above remain NOT RUN and are not part of Stage 1.

## Stage 1 implementation record - 2026-11-02 (before manual verification)

- Stage and status: This was the pre-verification implementation record. It is superseded by the Stage 1 verification handoff above; Stage 1 is now manually verified from user-supplied evidence.
- Files changed: `pyproject.toml`, `.env.example`, `.gitignore`, `src/sports_tracker/__init__.py`, `src/sports_tracker/config.py`, `src/sports_tracker/openligadb.py`, `src/sports_tracker/snapshots.py`, `scripts/fetch_openligadb.py`, `tests/test_config.py`, and `tests/test_openligadb.py`, plus the Stage 1 documentation updates.
- Implemented behavior: one-request OpenLigaDB client, basic UCL identity checks, exact response-byte capture, metadata with SHA-256 and provenance, timestamp/hash snapshot directories, no-overwrite protection, safe CLI errors, and isolated MockTransport tests.
- Checks at the time of this record: editable installation, tests, Ruff checks, real UCL requests, and provider snapshot creation were still pending. The later user-supplied verification record supersedes that pending status.
- Current blocker and next step: no Stage 1 implementation blocker is known. The next stage is SQL Server schema/loading design; do not begin later stages until that plan is reviewed.

## Previous handoff - 2026-11-01

- Stage and status: Stage 0 foundation implemented; manual verification pending.
- Files changed: `pyproject.toml`, `.env.example`, `src/sports_tracker/__init__.py`, `src/sports_tracker/config.py`, `src/sports_tracker/database.py`, `scripts/check_database.py`, `tests/test_config.py`, `README.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_PLAN.md`, and `docs/MANUAL_RUNBOOK.md`.
- Implemented behavior: validated `.env` settings, ODBC Driver 18 connection-string escaping, password-redacted diagnostics, reusable pyodbc connections, a read-only metadata check, focused configuration tests, and basic pytest/Ruff configuration.
- Manual commands provided: activate `.venv`, install the editable project with development dependencies, create and edit `.env`, run pytest, run Ruff, and run the permanent database check.
- Checks and supplied evidence: the user supplied SQL Server, network, ODBC, sqlcmd, virtual-environment, pyodbc, and manual Python connection evidence listed above.
- Checks NOT RUN: editable installation, automated tests, Ruff, and `scripts/check_database.py`; no schema, import, API, UI, scheduler, or live-source checks.
- Failure or blocker: `docs/PROJECT_ROADMAP.md` is referenced but absent; no Stage 0 implementation blocker remains before manual verification.
- Decision and reason: keep all operational execution manual and keep the SQL password only in the ignored local `.env` file.
- Exact next step: follow the numbered commands under `Next manual handoff`, stopping after the first failed prerequisite and returning only non-secret output.

## Scope update handoff - 2026-11-01

- Stage and status: This historical scope update established the UCL-only scope. Stage 0 remains complete, and the later Stage 1 verification handoff now records retrieval and raw snapshot capture as manually verified.
- Files changed: `README.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_PLAN.md`, and `docs/MANUAL_RUNBOOK.md`.
- Implemented behavior: documentation now identifies UEFA Champions League 2026/27, OpenLigaDB shortcut `ucl`, season `2026`, league ID `4946`, Matchdays 3 and 4 as the starting scope, and expansion to all 144 league-phase fixtures plus later knockout fixtures.
- Design constraint: competition shortcut, season, league ID, and matchday selection remain configurable for future reuse; no other competition is currently planned.
- Checks and supplied evidence: read-only search confirmed that superseded competition names, shortcuts, and prior-season scope terms are absent from `README.md` and `docs/`.
- Checks at the time of this scope update: all project code, tests, linters, API calls, database commands, imports, and scheduled runs were not yet verified. The later Stage 1 verification handoff records the subsequent user-supplied results.
- Failure or blocker: none introduced by this documentation-only scope update. `AGENTS.md` was not modified because the requested edit scope excludes it.
- Exact next step: review the UCL scope wording, then follow the existing manual verification handoff only when ready; do not treat this documentation update as ingestion evidence.

## Next manual handoff

Stage 1 retrieval and raw snapshot capture are implemented and manually verified. The next stage is the SQL Server schema/loading design; it is not started. Keep all future execution manual and return only non-secret results. Do not paste `.env`, passwords, complete connection strings, raw response bodies, or raw snapshot files.

## Previous manual handoff (superseded by user verification)

1. Stage 0 verification is complete based on the user-supplied evidence above.
2. Install the updated project so HTTPX is available, then rerun the offline tests and Ruff checks after this Stage 1 change.
3. Run `python scripts/fetch_openligadb.py --matchday 3` and `python scripts/fetch_openligadb.py --matchday 4` separately with the local source settings.
4. Return only non-secret output, including match count, snapshot location, hash, and errors if any. Do not start transformation or later stages.

Do not install or reconfigure the database based only on an assumption that SSMS includes the engine.

## Update format for each handoff

- Stage and status:
- Files changed:
- Implemented behavior:
- Manual commands provided:
- Checks and supplied evidence:
- Checks NOT RUN:
- Failure or blocker:
- Decision and reason:
- Exact next step:

Update existing entries rather than keeping conflicting versions of the plan.
