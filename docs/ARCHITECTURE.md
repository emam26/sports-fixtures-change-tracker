# Architecture

Status: proposed application design. The Stage 0 configuration and connection foundation is implemented in code but has not been executed or verified by Codex. Source capture, schema, import, API, interface, and scheduling remain proposals.

## Purpose and scope

Collect real football fixtures/results, preserve source evidence, validate and store current records in SQL Server, record observed changes, and provide a local review interface.

Begin with one Bundesliga matchday from 2025/26. Expand to full 2025/26 and 2026/27 after repeatable import and recovery checks pass.

The application is a local portfolio project. It does not claim an existing customer, production deployment, or continuous operation while the user's computer is off.

## Implemented Stage 0 foundation

- `pyproject.toml` defines the Python package, runtime dependencies, development tools, pytest configuration, and Ruff configuration.
- `sports_tracker.config` loads local `.env` values, validates SQL Server settings, and builds an ODBC Driver 18 connection string with brace-quoted values and escaped closing braces.
- `sports_tracker.database` provides reusable pyodbc connection helpers with context-managed cleanup.
- `scripts/check_database.py` runs one read-only SQL Server metadata query without displaying the password or complete connection string.

No database tables, migrations, ingestion, API, UI, or scheduler are implemented in Stage 0.

## Components

| Component | Responsibility |
| --- | --- |
| Source client | Retrieve OpenLigaDB responses with bounded timeouts and failure handling |
| Raw capture | Preserve original JSON and request/retrieval provenance |
| Normalization and validation | Convert supported fields and reject or report invalid records |
| Import service | Apply valid changes and maintain run status and checkpoints |
| SQL Server | Store relationships, current state, history, issues, and notes |
| FastAPI | Expose current data and application-owned notes |
| HTML/CSS/JavaScript | Let users review data and manage notes |
| Scheduler | Invoke the existing import command at the documented interval |

Prefer one small application with a reusable import command. Exact package names, entry points, ports, environment, and scheduler remain implementation decisions.

## Source contract

Consult current official documentation during Stage 1:
- https://api.openligadb.de/index.html
- https://api.openligadb.de/swagger/v1/swagger.json

OpenLigaDB is community-maintained. Verify field meanings, result metadata, request limits, attribution, and applicable data-license requirements before implementing source behavior.

Preserve missing scores on unfinished records. Do not invent detailed match states from a finished flag alone. Use explicit UTC kickoff data where supplied; preserve uncertainty in source timestamps without offsets.

A captured response should retain the request details, retrieval time, HTTP status, content hash, and complete source body. Keep captured data outside Git by default.

## Proposed relational model

| Table | Purpose |
| --- | --- |
| import_runs | Scope, status, timing, counters, and failure diagnostics |
| source_snapshots | Trace captured responses and provenance to runs |
| teams | Source team identity and current supported attributes |
| matches | Current normalized fixtures and results |
| match_changes | Observed old/new business values and associated imports |
| validation_issues | Record-level or batch-level reasons an import cannot proceed |
| sync_checkpoints | Mark successfully applied source updates |
| match_notes | Application-owned notes linked to matches |

Define exact columns, keys, foreign keys, nullability, indexes, and source-ID scope in Stage 2. SQL Server integration tests must use SQL Server itself.

## Import consistency

Proposed policy: all-or-nothing current-record updates per matchday.

1. Start a run and preserve its source evidence.
2. Normalize and validate the selected batch.
3. If validation fails, retain diagnostics without partially changing current matches or advancing the success checkpoint.
4. If valid, apply teams/current matches, business-change history, and the success checkpoint within the defined transaction boundary.
5. If database work fails, roll back its changes and persist the failed-run diagnostic outside the failed transaction.

Specify which metadata is retained before the transaction and how failed-run details are written after rollback. Decide the overlap/concurrency strategy before implementing it. File capture and database commit are separate operations; document their failure handling rather than implying a single atomic filesystem/database transaction.

Use stable source identifiers and relational constraints. Compare normalized business fields, excluding retrieval-only metadata.

## History and incremental updates

The first import establishes a baseline. History begins when the application observes a later difference, not at an invented earlier event time.

Record old value, new value, observed time, and import reference. An unchanged repeated input must produce no duplicate matches or false business changes. Preserve relevant source update markers without inventing their timezone.

Use documented source change polling and bounded retries. Checkpoints represent successful application, not merely successful downloads.

## API and interface

Planned capabilities:
- Filtered, paginated matches and match details.
- Observed change history.
- Import runs and validation issues.
- Create/read/update/delete of local notes.

Exact routes and response contracts will be defined in Stage 4. Parameterize SQL, validate input, and keep note writes transactional. Notes cannot overwrite source-owned scores or fixtures.

The interface must support real imported data, understandable errors, empty history, and notes that persist after refresh. Safely render external text.

## SQL and verification

Useful reports include import reconciliation, duplicate checks, recent changes, rejected records, and failed runs. Use joins and analytical SQL where they answer those questions. Review a real frequently used query and justify indexes with its execution plan.

Verify offline normalization and failure boundaries, real SQL Server behavior, API requests, browser workflows, and scheduling separately. Controlled data changes and failures belong in clearly labeled tests with a separate database.

Do not publish invented performance gains, scale, screenshots, or passing badges. Record actual results in BUILD_PLAN.md.

## Deferred decisions

Database host and authentication; Python environment; exact schema and migration approach; application entry points and routes; synchronization locking; scheduler; raw-data retention.

Resolve these from the user's environment and implementation evidence, not guessed setup.
