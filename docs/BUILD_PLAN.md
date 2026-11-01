# Build Plan and Progress

This is the changing implementation record. PROJECT_ROADMAP.md defines the stages; this file tracks current work, decisions, evidence, and the next action.

Prepared: 2026-10-25. These starter documents were prepared outside the user's checkout. Adding them does not establish that application code exists. Codex must inspect the actual repository.

## Current stage

Stage 0 — setup and planning. Foundation implemented; manual verification pending.

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
- The permanent project check script has not been run.
- The automated tests and Ruff check have not been run.
- The editable project installation has not been run.
- No import, schema, API, UI, scheduler, or live-source checks have been performed.
- `docs/PROJECT_ROADMAP.md` is referenced by `AGENTS.md` but is absent from this checkout.

## Stage tracker

| Stage | Deliverable | Completion evidence | Status |
| --- | --- | --- | --- |
| 0 | Environment, SQL connection, instructions, plan | Dedicated interpreter and successful connection query | In progress; foundation implemented; permanent check and tests NOT RUN |
| 1 | Real matchday capture and validated source contract | Capture manifest and passing offline checks | Planned |
| 2 | SQL schema and repeatable first import | Reconciliation and duplicate-free rerun | Planned |
| 3 | Observed changes, recovery, incremental and season imports | Controlled change, rollback, retry, and reconciliation | Planned |
| 4 | FastAPI and local notes CRUD | Normal, missing, and invalid request checks | Planned |
| 5 | HTML/CSS/JavaScript interface | Browser review and notes workflow | Planned |
| 6 | Scheduled imports | Evidence of a real scheduled run and logs | Planned |
| 7 | Final verification, docs, demo, GitHub publication | Final checklist and published implementation | Planned |

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

Do not treat these as application verification. Keep large logs local; record concise relevant results without secrets.

## Decisions

| Decision | Status | Reason |
| --- | --- | --- |
| Python, SQL Server, FastAPI, plain HTML/CSS/JS | Agreed stack | Covers collection, relational storage, API, and review UI |
| WSL Bash; repository on F drive | Confirmed preference | User-selected workflow |
| All operational execution is manual | Confirmed requirement | User runs terminal, SQL, API, browser, scheduling, and Git steps |
| One matchday before whole seasons | Agreed sequence | Makes correctness and troubleshooting manageable |
| All-or-nothing current-record update per matchday | Proposed for implementation | Avoids partially applied invalid batches |
| SQL Server host, auth, and driver | User evidence supplied | CANVASIT, SportsFixturesTracker, sports_tracker_app, TCP 172.20.80.1:1433, and ODBC Driver 18 are recorded; the permanent project check remains NOT RUN |
| Scheduler | Unresolved | Deferred until the import is reliable |

## Latest handoff - 2026-11-01

- Stage and status: Stage 0 foundation implemented; manual verification pending.
- Files changed: `pyproject.toml`, `.env.example`, `src/sports_tracker/__init__.py`, `src/sports_tracker/config.py`, `src/sports_tracker/database.py`, `scripts/check_database.py`, `tests/test_config.py`, `README.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_PLAN.md`, and `docs/MANUAL_RUNBOOK.md`.
- Implemented behavior: validated `.env` settings, ODBC Driver 18 connection-string escaping, password-redacted diagnostics, reusable pyodbc connections, a read-only metadata check, focused configuration tests, and basic pytest/Ruff configuration.
- Manual commands provided: activate `.venv`, install the editable project with development dependencies, create and edit `.env`, run pytest, run Ruff, and run the permanent database check.
- Checks and supplied evidence: the user supplied SQL Server, network, ODBC, sqlcmd, virtual-environment, pyodbc, and manual Python connection evidence listed above.
- Checks NOT RUN: editable installation, automated tests, Ruff, and `scripts/check_database.py`; no schema, import, API, UI, scheduler, or live-source checks.
- Failure or blocker: `docs/PROJECT_ROADMAP.md` is referenced but absent; no Stage 0 implementation blocker remains before manual verification.
- Decision and reason: keep all operational execution manual and keep the SQL password only in the ignored local `.env` file.
- Exact next step: follow the numbered commands under `Next manual handoff`, stopping after the first failed prerequisite and returning only non-secret output.

## Next manual handoff

1. WSL Bash, `/mnt/f/sports-fixtures-change-tracker`: activate the existing `.venv` with `source .venv/bin/activate`.
2. Install the local project and development tools with `python -m pip install -e ".[dev]"`.
3. Copy `.env.example` to `.env`, set `SQL_SERVER_HOST` to the current WSL-visible Windows host address, and enter the password only in the ignored local file.
4. Run `python -m pytest`; expect the focused configuration tests to pass. Stop and return the non-secret failure if it does not.
5. Run `ruff check .`; expect no lint errors. Stop and return the non-secret failure if it does not.
6. Run `python scripts/check_database.py`; expect the read-only success message and server metadata, with no password or complete connection string.
7. Return only non-secret output. Do not start Stage 1 until these checks are reviewed.

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
