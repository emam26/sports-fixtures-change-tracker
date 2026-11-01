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

Status: the project foundation is implemented, but the commands below are NOT RUN by Codex. The user must execute them manually and return only non-secret output.

### WSL Bash, project environment

Working directory: `/mnt/f/sports-fixtures-change-tracker`.

```bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
python -m pip install -e ".[dev]"
if [ ! -f .env ]; then cp .env.example .env; fi
```

Expected result: the existing virtual environment is active and the local package, `pyodbc==5.3.0`, `python-dotenv`, pytest, and Ruff are installed. If activation or installation fails, stop and return the non-secret error before continuing.

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

Expected result: the focused configuration tests pass. This is an offline check and does not establish SQL Server connectivity. If it fails, stop and return the non-secret failure output.

```bash
ruff check .
```

Expected result: Ruff reports no errors. This is a static check and does not establish SQL Server connectivity. If it fails, stop and return the non-secret failure output.

### WSL Bash, permanent read-only database check

Working directory: `/mnt/f/sports-fixtures-change-tracker`; use the local `.env` and the active virtual environment. Target: SQL Server `CANVASIT`, database `SportsFixturesTracker`, runtime login `sports_tracker_app`, current reported TCP address `172.20.80.1:1433`.

```bash
python scripts/check_database.py
```

Expected result: `Database connection succeeded.` followed by server name, login name, database name, edition, and product version. The script runs a read-only metadata query and must never display the password or complete connection string. The user has already reported a successful manual Python connection, but this permanent project check remains NOT RUN until this command is executed.

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

Status: user-reported prerequisites are established; Stage 0 project installation and checks remain NOT RUN.

User-reported evidence on 2026-11-01: Python 3.14.4 virtual environment created and pyodbc 5.3.0 installed. Use the Stage 0 procedure above to record the actual activation, editable installation, pytest, and Ruff results. Do not modify Conda base.

## Database connection and schema

Status: user-reported connection prerequisites and a manual Python connection are confirmed; the permanent project check remains NOT RUN.

User-reported target on 2026-11-01: SQL Server `CANVASIT`, Standard Developer Edition, version `17.0.1000.7`; database `SportsFixturesTracker`; runtime login `sports_tracker_app`; TCP `172.20.80.1:1433`; ODBC Driver 18 installed; sqlcmd authentication succeeded. No password is recorded here. The Stage 0 script performs only its read-only metadata query; no tables or schema are created.

Record the actual current WSL-visible host if it differs after a restart. Keep actual passwords outside this document.

SQL intended for a query window must be labeled as SQL, with its target database. It must not be pasted into Bash.

## Source capture, imports, and replay

Status: not implemented or verified.

After Stages 1–3, document commands to capture one matchday, inspect provenance, validate, import, repeat unchanged input, inspect issues, and retry or replay an eligible failed input.

Document the selected data scope and where raw responses and logs are retained. Keep controlled test changes separate from real collected data.

## Tests

Status: focused configuration tests are written but NOT RUN.

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
