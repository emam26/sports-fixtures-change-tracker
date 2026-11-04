# Sports Fixtures & Change Tracker

> **Implementation handoff (2026-11-03):** Stage 3 repairs and the Stage 4–10
> implementation are present in the working tree but remain **NOT RUN** after the
> latest edits. Do not treat lint, tests, SQL integration, live synchronization,
> API, browser, or scheduling as verified until manual evidence is recorded.

The current scope is UEFA Champions League 2026/27 (`ucl`, season `2026`, League
ID `4946`), beginning with Matchdays 3 and 4. The architecture is configurable for
later expansion, but no other competition is currently implemented or planned.

## Current application surface

The local-first path preserves OpenLigaDB responses byte-for-byte, validates and
imports saved snapshots transactionally, records real field-level changes, and
supports conservative one-shot synchronization. A loopback-only FastAPI service
and plain HTML/CSS/JavaScript dashboard expose fixtures, provenance, import health,
validation issues, and separately owned local notes.

Future scores remain absent/`NULL` until the provider supplies a result. Result
types such as `HalfTime` and `After90Minutes` are retained explicitly; zero is never
used as a missing-value substitute.

Handoff documentation:

- [Architecture](docs/ARCHITECTURE.md)
- [Build status](docs/BUILD_PLAN.md)
- [Manual runbook](docs/MANUAL_RUNBOOK.md)
- [API](docs/API.md)
- [Testing](docs/TESTING.md)
- [Evaluation](docs/EVALUATION.md)
- [Local deployment](docs/DEPLOYMENT_LOCAL.md)
- [Source notes](docs/SOURCE_NOTES.md)
- [Proposed commit structure](docs/COMMIT_PLAN.md)

A staged Python and SQL Server application for preserving OpenLigaDB football
responses, importing them transactionally, and recording meaningful fixture
changes. The current planned scope is UEFA Champions League 2026/27:

- OpenLigaDB shortcut: `ucl`
- season: `2026`
- expected league ID: `4946`
- initial source coverage: matchdays 3 and 4
- eventual source coverage: all 144 league-phase fixtures and later knockout fixtures

The architecture remains configurable for future competitions, but UCL is the
only competition currently implemented and documented.

## Current status

- Stage 0 foundation: complete and manually verified by the project owner.
- Stage 1 raw OpenLigaDB capture: implemented and manually verified by the project owner.
- Stage 2 SQL Server schema: deployed by the project owner.
- Stage 3 snapshot importer: implemented, but the current checkout has not been
  executed or verified in this handoff.
- Later API, UI, scheduling, and broader competition work: not started.

The saved Matchday 3 and Matchday 4 responses under `data/raw/` are immutable
inputs. `data/raw/` is ignored by Git. Do not place `.env` or passwords in the
repository.

## WSL setup

From WSL Bash:

```bash
cd /mnt/f/sports-fixtures-change-tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --editable '.[dev]'
cp .env.example .env
```

Set the local SQL Server values in `.env` only. The Windows host IP used by WSL
can change after a WSL restart or a network restart; confirm the current host
address before running a database import. Never paste the password or complete
connection string into issue reports or chat.

## Stage 3 offline workflow

The importer reads a saved snapshot directory containing `response.json` and
`metadata.json`; it does not make an API request. Start with an offline dry run:

```bash
SNAPSHOT_M3="$(dirname "$(find data/raw/ucl/2026/matchday-3 -name metadata.json -print | sort | head -n 1)")"
python scripts/import_snapshot.py --snapshot "$SNAPSHOT_M3" --dry-run
```

Then import Matchday 3 and Matchday 4 manually, replaying the same Matchday 3
directory afterward to verify idempotency. The exact sequence and SQL checks
are in [`docs/MANUAL_RUNBOOK.md`](docs/MANUAL_RUNBOOK.md).

The importer validates the observed OpenLigaDB identity, teams, timestamps,
result types, scores, and goals before changing SQL Server state. A completed
match must have an `After90Minutes` result. An unfinished match remains without
a fabricated score; future scores are represented as SQL `NULL` or absent
result rows. Half-time and full-time result types are interpreted explicitly.

## Repository guide

- [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md): staged implementation status and evidence.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): data flow, schema mapping, and invariants.
- [`docs/MANUAL_RUNBOOK.md`](docs/MANUAL_RUNBOOK.md): commands and manual verification.
- [`sql/001_initial_schema.sql`](sql/001_initial_schema.sql): the deployed schema source.
- `src/sports_tracker/ingestion.py`: typed parsing, validation, and SQL Server import logic.
- `scripts/import_snapshot.py`: offline dry-run/import CLI.

No claim of a completed Stage 3 import or test run is made until the project
owner supplies the manual execution results.
