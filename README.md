# Sports Fixtures & Change Tracker

A local-first Python and SQL Server application that preserves OpenLigaDB source
responses, imports UEFA Champions League fixtures transactionally, records observed
field-level changes, and exposes the current state through FastAPI and a plain
HTML/CSS/JavaScript dashboard.

## Current scope and evidence

The implemented scope is UEFA Champions League 2026/27:

- OpenLigaDB shortcut: `ucl`
- season: `2026`
- expected league ID: `4946`
- initial coverage: Matchdays 3 and 4
- later planned coverage: all 144 league-phase fixtures, followed by knockout fixtures

The architecture keeps provider and competition identity configurable, but no other
competition is currently claimed as implemented.

Owner-supplied evidence confirms the project foundation, immutable raw capture, the
deployed 12-table schema, and the first successful Matchday 3 SQL import. Import run
`3` / source snapshot `8` inserted 18 completed matches, 36 typed results, and 74
goals; four embedded team icons were safely omitted with warnings. The real exact
replay, Matchday 4 SQL import, updated offline suite, API/browser flow, live one-shot
sync, and scheduled operation remain awaiting manual verification after the latest
edits.

## Architecture

```text
OpenLigaDB
  -> bounded HTTP client and conservative last-change check
  -> immutable response.json + metadata.json under ignored data/raw/
  -> typed parsing and validation
  -> one SQL Server transaction for current data, changes, run status, and checkpoint
  -> loopback FastAPI query layer
  -> responsive, framework-free browser dashboard
```

Key invariants:

- Raw response bytes are never rewritten.
- Provider IDs and SQL uniqueness constraints prevent duplicate domain rows.
- An initial observation establishes a baseline; it does not invent earlier changes.
- Future scores remain absent/`NULL`, never fabricated as zero.
- `HalfTime`, `After90Minutes`, and other result types remain explicit.
- Fixture, result, goal, change, successful run, and checkpoint writes commit together.
- Failed-run provenance is attempted separately only after a confirmed rollback.
- Local notes cannot overwrite provider-owned fixture or result data.

See [Architecture](docs/ARCHITECTURE.md) for mappings, boundaries, and limitations.

## Technology stack

- Python 3.11+ (the owner currently uses Python 3.14)
- `httpx`, `pyodbc` 5.3.0, `python-dotenv`
- Microsoft SQL Server 2025 and ODBC Driver 18
- FastAPI, Pydantic, and Uvicorn
- pytest and Ruff
- Plain HTML, CSS, and JavaScript

## WSL setup

From WSL Bash:

```bash
cd /mnt/f/sports-fixtures-change-tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --editable '.[dev]'
cp .env.example .env
```

Put real local settings only in `.env`. Never commit or paste that file, a password,
a write token, or a complete connection string. The Windows host IP visible from WSL
can change after a WSL or network restart; reconfirm it before database operations.

## Reproducible workflow

Validate a saved snapshot without network or database access:

```bash
python scripts/evaluate_snapshot.py "<SNAPSHOT_DIRECTORY>"
python scripts/import_snapshot.py --snapshot "<SNAPSHOT_DIRECTORY>" --dry-run
```

Import the same immutable snapshot only after the dry run succeeds:

```bash
python scripts/import_snapshot.py --snapshot "<SNAPSHOT_DIRECTORY>"
```

Run the local application only after database verification:

```bash
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Note writes are disabled by default. If explicitly
enabled locally, they also require a separate token and remain local-only.

The one-shot synchronizer is intentionally not a daemon:

```bash
python scripts/sync_openligadb.py --matchday 3 --matchday 4
```

This command makes real source requests and SQL writes. Run it only after offline,
SQL, API, and browser checks pass. OpenLigaDB documents a 60-requests-per-minute
limit; aggressive polling is prohibited.

## Security and local artifacts

`.env` and `.env.*` files other than `.env.example`, raw snapshots, runtime logs/locks, virtual
environments, build outputs, and common SQL Server backup/data files are ignored by
Git. Raw snapshots and local database backups must never be added manually.

The API binds to loopback by default and returns generic unhandled-error responses.
SQL credentials and note tokens are not returned by status endpoints or written to
application logs.

## Documentation

- [Build status and evidence](docs/BUILD_PLAN.md)
- [Manual verification and operation](docs/MANUAL_RUNBOOK.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Testing strategy](docs/TESTING.md)
- [Evaluation plan](docs/EVALUATION.md)
- [Local scheduling](docs/DEPLOYMENT_LOCAL.md)
- [Source notes](docs/SOURCE_NOTES.md)
- [Commit plan](docs/COMMIT_PLAN.md)

No new lint, test, SQL, network, API, browser, scheduler, or Git result is claimed
until the project owner supplies the corresponding manual evidence.
