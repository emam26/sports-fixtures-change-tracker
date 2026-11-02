# Build Plan and Progress

This is the changing implementation record. PROJECT_ROADMAP.md defines the stages; this file tracks current work, decisions, evidence, and the next action.

Prepared: 2026-10-25. These starter documents were prepared outside the user's checkout. Adding them does not establish that application code exists. Codex must inspect the actual repository.

## Current stage

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
- No import, schema, API, UI, scheduler, or live-source checks have been performed.
- `docs/PROJECT_ROADMAP.md` is referenced by `AGENTS.md` but is absent from this checkout.

Current planned scope:
- Competition: UEFA Champions League 2026/27.
- OpenLigaDB shortcut: `ucl`.
- Season: `2026`.
- League ID: `4946`.
- Initial scope: Matchdays 3 and 4.
- Expansion scope: all 144 league-phase fixtures, followed by later knockout fixtures.
- Ingestion is not complete or verified.

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
| 1 | Real UCL matchday capture and validated source contract | Capture manifest and passing offline checks | Not started |
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

Treat E005–E016 as Stage 0 evidence only; they do not verify UCL ingestion or later stages. Keep large logs local; record concise relevant results without secrets.

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

## Verification handoff - 2026-11-02

- Stage and status: Stage 0 complete and verified; UCL ingestion and every later stage remain not started.
- Files changed: `.gitignore`, `README.md`, `docs/BUILD_PLAN.md`, and `docs/MANUAL_RUNBOOK.md`.
- Implemented behavior: recorded the successful editable installation, Ruff checks, pytest result, read-only database check, SQL Server metadata, and `.env` ignore evidence without any password or `.env` contents.
- Checks and supplied evidence: editable installation succeeded; Ruff check passed; Ruff formatting check passed with 10 files formatted; pytest passed 5 tests in 0.13 seconds; `scripts/check_database.py` succeeded against the recorded server, login, database, edition, and version.
- Checks NOT RUN: UCL ingestion, source/API calls, schema work, imports, API, UI, scheduling, and all later-stage verification.
- Failure or blocker: no Stage 0 blocker remains; `docs/PROJECT_ROADMAP.md` remains absent as previously recorded.
- Exact next step: begin Stage 1 for UCL Matchdays 3 and 4 only when ready; do not treat the Stage 0 evidence as ingestion evidence.

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

- Stage and status: Stage 0 foundation remains implemented; competition scope is now UCL-only and ingestion remains NOT RUN.
- Files changed: `README.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_PLAN.md`, and `docs/MANUAL_RUNBOOK.md`.
- Implemented behavior: documentation now identifies UEFA Champions League 2026/27, OpenLigaDB shortcut `ucl`, season `2026`, league ID `4946`, Matchdays 3 and 4 as the starting scope, and expansion to all 144 league-phase fixtures plus later knockout fixtures.
- Design constraint: competition shortcut, season, league ID, and matchday selection remain configurable for future reuse; no other competition is currently planned.
- Checks and supplied evidence: read-only search confirmed that superseded competition names, shortcuts, and prior-season scope terms are absent from `README.md` and `docs/`.
- Checks NOT RUN: all project code, tests, linters, API calls, database commands, imports, and scheduled runs.
- Failure or blocker: none introduced by this documentation-only scope update. `AGENTS.md` was not modified because the requested edit scope excludes it.
- Exact next step: review the UCL scope wording, then follow the existing manual verification handoff only when ready; do not treat this documentation update as ingestion evidence.

## Next manual handoff

1. Stage 0 verification is complete based on the user-supplied evidence above.
2. Keep UCL ingestion and every later stage marked not started.
3. When proceeding, begin Stage 1 with UCL Matchdays 3 and 4 only and return non-secret evidence after each manual prerequisite.

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
