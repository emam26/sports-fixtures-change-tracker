# Architecture

Status: Stage 0 is complete. Stage 1 is complete, tested, documented, committed, and pushed according to the user's supplied status. Stage 2 schema design is implemented in `sql/001_initial_schema.sql` but NOT RUN; SQL loading, change tracking, API, interface, and scheduling remain unimplemented.

## Purpose and scope

Collect real football fixtures/results, preserve source evidence, validate and store current records in SQL Server, record observed changes, and provide a local review interface.

The current competition scope is the UEFA Champions League 2026/27: OpenLigaDB shortcut `ucl`, season `2026`, league ID `4946`. Start with Matchdays 3 and 4, then expand to all 144 league-phase fixtures and later knockout fixtures after repeatable import and recovery checks pass.

The application is a local portfolio project. It does not claim an existing customer, production deployment, or continuous operation while the user's computer is off.

## Implemented Stage 0 foundation

- `pyproject.toml` defines the Python package, runtime dependencies, development tools, pytest configuration, and Ruff configuration.
- `sports_tracker.config` loads local `.env` values, validates SQL Server settings, and builds an ODBC Driver 18 connection string with brace-quoted values and escaped closing braces.
- `sports_tracker.database` provides reusable pyodbc connection helpers with context-managed cleanup.
- `scripts/check_database.py` runs one read-only SQL Server metadata query without displaying the password or complete connection string.

No database tables, migrations, ingestion, API, UI, or scheduler are implemented in Stage 0.

Competition selection must remain configurable through the OpenLigaDB shortcut, season, league ID, and matchday selection so the architecture can support future competitions. Only the UEFA Champions League 2026/27 is currently planned; this configurability does not imply that other competitions or ingestion are implemented.

## Implemented Stage 1 foundation

Stage 1 source retrieval and raw snapshot code is complete, tested, documented, committed, and pushed according to the user's supplied status. The HTTPX client fetches one explicitly requested matchday, applies only basic source-identity checks, and raises descriptive custom errors for network, HTTP, empty-body, and invalid-JSON failures. The snapshot writer preserves exact response bytes and writes provenance metadata with a UTC retrieval time, HTTP status, content type, byte count, and SHA-256 hash in a timestamp/hash directory without overwriting an existing snapshot. Scheduling and repeated polling are intentionally excluded and remain unimplemented.

## Implemented Stage 2 schema design

Stage 2 is implemented as the unapplied T-SQL script `sql/001_initial_schema.sql`. It creates guarded, dbo-scoped tables and indexes for competitions, competition seasons, teams, matches, match results, observed goals, import runs, source snapshots, validation issues, match changes, synchronization checkpoints, and application-owned match notes. The script uses an explicit `SportsFixturesTracker` database context, a transaction with error handling, and no destructive statements or permission grants. It has NOT been executed, deployed, or verified against SQL Server.

The schema deliberately stores raw snapshot metadata and filesystem paths, not the original response bytes. A unique local snapshot directory identifies each capture, while the content hash is indexed but not unique, so identical response bytes captured at different times remain distinct observations. The unique provider/source identities and per-snapshot change key support later idempotent import logic without claiming that ETL has been implemented.

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

## Stage 2 entity relationships

| Entity | Purpose and principal relationships |
| --- | --- |
| `competitions` | Provider-level competition identity, such as OpenLigaDB `ucl`. One competition has many `competition_seasons`. |
| `competition_seasons` | Provider league ID and season identity. One season has many `matches`, `import_runs`, and `sync_checkpoints`. |
| `teams` | One provider team identity and source-owned attributes. A team can be referenced as home or away by many matches and as the scoring team for goals. |
| `matches` | One current fixture per `(provider, provider_match_id)`, linked to one competition season and two teams. Stores matchday/stage and source timestamps. |
| `match_results` | Child result observations keyed by provider result ID and distinct `result_type_kind`, including `HalfTime` and `After90Minutes`. Future matches have no fabricated result rows. |
| `match_goals` | Optional child goal observations using fields confirmed in saved Stage 1 responses. It is not required for a future match with an empty `goals` collection. |
| `source_snapshots` | Metadata for each preserved response: URL, retrieval time, HTTP details, hash, size, and local paths. Raw bytes remain on disk. |
| `import_runs` | Later ETL run status, scope, counts, errors, replay relationship, and source snapshot reference. A failure record may be written after a rolled-back transaction. |
| `validation_issues` | Detailed record/field problems tied to an import run and/or snapshot. |
| `match_changes` | Field-level observed history tied to a match, import run, snapshot, old/new values, and observation time. |
| `sync_checkpoints` | One application-managed scope checkpoint that advances only after successful processing. It references the successful import and snapshot. |
| `match_notes` | Application-owned notes linked to matches, independent of source-owned fixture and result columns. |

The principal foreign-key paths are `competitions -> competition_seasons -> matches`; `teams -> matches`; `matches -> match_results/match_goals/match_changes/match_notes`; `source_snapshots -> import_runs/validation_issues/match_changes/sync_checkpoints`; and `import_runs -> validation_issues/match_changes/sync_checkpoints`. The script adds indexes for provider identity, competition/season, kickoff, home/away team filtering, matchday/stage, import inspection, change history, snapshot lookup, and checkpoint lookup.

## Source contract

Consult current official documentation during Stage 1:
- https://api.openligadb.de/index.html
- https://api.openligadb.de/swagger/v1/swagger.json

OpenLigaDB is community-maintained. Verify field meanings, result metadata, request limits, attribution, and applicable data-license requirements before implementing source behavior.

Preserve missing scores on unfinished records as `NULL`; never convert missing future results to zero. Interpret result entries explicitly by `resultType`, including `HalfTime` and `After90Minutes`, and do not choose a score from an undifferentiated result list or infer a detailed state from a finished flag alone. Use explicit UTC kickoff data where supplied; preserve uncertainty in source timestamps without offsets.

A captured response should retain the request details, retrieval time, HTTP status, content hash, and complete source body. Keep captured data outside Git by default.

The saved Matchday 3 and 4 responses were inspected before designing the child tables. Match records contain nested `team1`/`team2`, `group`, `matchResults`, and `goals` objects. Result records expose `resultID`, `resultTypeID`, `resultTypeKind`, order, descriptions, and team points. Goal records expose `goalID`, cumulative team scores, minute, scorer fields, scoring team, penalty/own-goal/overtime flags, and an optional comment, so the observed fields are represented in `match_goals` without inventing additional provider fields. Matchday 4 has empty result and goal collections, so no 0-0 or placeholder child rows are created.

The observed `matchDateTimeUTC` includes an explicit `Z` and maps to `kickoff_utc`. The observed `lastUpdateDateTime` is offset-free, so the schema provides both nullable `source_last_update_utc` and `source_last_update_raw`; later ETL must leave the UTC column null unless the provider's timezone semantics are verified.

## Planned engineering evaluation

The following evaluations are planned for later SQL loading and change-tracking stages. All remain NOT RUN:

- **Idempotency:** replay an identical snapshot and verify no duplicate current rows, observed changes, or checkpoint updates.
- **Change-detection accuracy:** compare controlled fixture variants and unchanged replays, measuring false positives and false negatives while interpreting result types explicitly.
- **Transaction rollback:** inject a SQL Server batch failure and verify current records, change history, and successful checkpoints are not partially committed.
- **Incremental request efficiency:** measure request counts for active matchdays and later refreshes while respecting OpenLigaDB's 60-requests-per-minute limit and avoiding aggressive polling.
- **Snapshot replay:** replay saved response bytes offline and verify hash, provenance, and deterministic downstream results without a network request.

## Stage 2 relational model implemented in SQL

| Table | Purpose |
| --- | --- |
| competitions | Provider and competition shortcut identity |
| competition_seasons | Source league ID and season identity |
| teams | Source team identity and current supported attributes |
| matches | Current normalized fixtures and results |
| match_results | Explicit result-type scores, including half-time and final results |
| match_goals | Observed provider goal events and cumulative score fields |
| import_runs | Scope, status, timing, counters, replay, and failure diagnostics |
| source_snapshots | Captured response provenance and local paths, not raw bytes |
| validation_issues | Record-level or batch-level reasons an import cannot proceed |
| match_changes | Observed old/new business values and associated imports |
| sync_checkpoints | Mark successfully applied source updates |
| match_notes | Application-owned notes linked to matches |

The exact columns, keys, foreign keys, nullability, indexes, and source-ID scope are defined in `sql/001_initial_schema.sql`. The DDL remains unapplied. SQL Server integration tests must use SQL Server itself.

## Stage 2 verification plan — NOT RUN

Before any later import is accepted, perform these checks against SQL Server in a separate controlled test database or approved test schema as appropriate. None has been completed:

- **Unique match identity:** attempt duplicate `(provider, provider_match_id)` values and confirm the unique constraint rejects them without changing existing rows.
- **Referential integrity:** attempt orphan competition-season, team, result, snapshot, change, checkpoint, and note rows and confirm foreign keys reject them.
- **Upcoming fixture scores:** load a Matchday 4-shaped fixture with no result rows and confirm no fabricated 0-0 result is created; valid completed 0-0 must remain distinguishable from missing results.
- **Result-type modeling:** load `HalfTime` and `After90Minutes` rows for one match and confirm both remain distinct with their own result identity and scores.
- **Snapshot provenance:** record two snapshots with the same SHA-256 and different retrieval timestamps and confirm both remain queryable with separate IDs and paths.
- **Idempotent reimport support:** reprocess the same snapshot in a later ETL test and confirm fixture state is not duplicated and the per-snapshot change key prevents duplicate observed changes.
- **Historical change support:** modify one business field in controlled input and confirm one field-level old/new history row points to the correct import and snapshot.
- **Transaction rollback and checkpoint recovery:** inject a failure after partial staging and confirm current rows, changes, and checkpoints do not advance; persist the failed-run diagnostic after rollback in a separate transaction.

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
