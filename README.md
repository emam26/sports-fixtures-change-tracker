# ⚽ Sports Fixtures & Change Tracker

> Football fixture imports, data checks, and observed change tracking with Python and SQL Server.

![Status: Stage 0 complete](https://img.shields.io/badge/status-Stage%200%20complete-brightgreen)
![Python](https://img.shields.io/badge/language-Python-3776AB?logo=python&logoColor=white)
![SQL Server](https://img.shields.io/badge/database-SQL%20Server-CC2927)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)

The project addresses a practical question: **what changed in a fixture or result, and which import recorded it?** The planned application collects football data from OpenLigaDB, checks incoming records, stores them in SQL Server, and keeps a history of observed changes.

> [!NOTE]
> This repository documents the planned application and the verified Stage 0
> foundation. UCL ingestion, the schema, API, UI, scheduler, and all later-stage
> checks have not started.

## Why this project

A sports website can receive a fixture more than once, receive it before a result is available, or receive a changed kickoff time later. Simply appending every API response produces duplicates and loses the explanation of what changed.

The intended user is someone maintaining a small sports data application. They should be able to review the latest records, see changes observed by this application, and investigate imports that need attention.

## Data source

Data will come from [OpenLigaDB](https://www.openligadb.de/), a community-maintained sports database. It is not an official league feed.

The current scope is the UEFA Champions League 2026/27: OpenLigaDB shortcut `ucl`, season `2026`, league ID `4946`. Start with Matchdays 3 and 4, then expand to all 144 league-phase fixtures and later knockout fixtures. OpenLigaDB uses the season's starting year in its URLs.

Reference endpoints:

- [2026/27 Champions League matches](https://api.openligadb.de/getmatchdata/ucl/2026)
- [API documentation](https://api.openligadb.de/index.html)
- [OpenAPI specification](https://api.openligadb.de/swagger/v1/swagger.json)

Read access does not require an API key. The documented limit is 60 requests per minute per IP. Stage 1 fetches only one explicitly requested matchday and does not schedule or poll; do not use aggressive polling or exceed the provider's limit.

OpenLigaDB data is provided under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Attribution and the applicable data-sharing requirements must accompany any published data extracts. A code license does not replace the data license.

## Planned workflow

1. Fetch the configured UCL 2026/27 season or selected matchday and preserve the original JSON with its URL, retrieval time, and payload hash.
2. Check required identifiers, team references, timestamps, and result fields.
3. Store valid records in SQL Server and record rejected records with an explanation.
4. Compare incoming business fields with the stored match and record observed changes.
5. Commit records, validation issues, and the synchronization checkpoint together.
6. Expose the stored data through FastAPI and a small HTML, CSS, and JavaScript interface.

Unchanged imports should not create extra matches or change-history entries. Fetch timestamps will be kept separate from the fields used to identify a changed match.

## Planned features

- Initial UCL Matchdays 3 and 4 import, followed by the remaining league-phase and knockout matchdays.
- Current fixture and result lookup, with competition, season, and team filters.
- A history showing previous and current values for observed schedule and result changes.
- Import summaries showing accepted, rejected, unchanged, and changed records.
- An error view for reviewing records that could not be imported.
- Local match notes that users can create, update, and delete. Notes will not modify OpenLigaDB records.
- Retry handling for temporary request failures, with failed imports available for a later rerun.

Scheduling will use a simple local scheduler after the manual import works reliably. Docker is an optional later setup, rather than a prerequisite for the first version.

## Proposed database

| Table | Purpose |
| --- | --- |
| `import_runs` | Track each import, its scope, outcome, counts, and errors. |
| `source_snapshots` | Record captured responses and their provenance. |
| `teams` | Store source team identifiers and names. |
| `matches` | Store one current record per source match. |
| `match_changes` | Preserve observed previous and current field values. |
| `validation_issues` | Explain rejected or questionable records. |
| `sync_checkpoints` | Record the last successfully processed scope. |
| `match_notes` | Store application-owned notes separately from source data. |

SQL work will include keys and constraints, transactional loading, import reconciliation queries, and views for current matches and change history. Index choices will follow the actual filtering queries.

## Important data rules

- A match without a result is not automatically invalid; it may not have finished.
- Missing scores will remain missing rather than being converted to zero.
- Kickoff times will use the explicit UTC field. Offset-free source timestamps will not be silently treated as UTC.
- A false finished flag alone will not be used to invent scheduled, live, or postponed states.
- A failed database transaction must not advance its checkpoint.
- Rejected records must remain visible; a partial import must not appear fully successful.
- Change history starts with this application's observations. It cannot reconstruct earlier source revisions.
- Records absent from one response will not be silently deleted.

## Planned stack

| Area | Choice |
| --- | --- |
| Collection and processing | Python |
| Database and SQL | Microsoft SQL Server, T-SQL |
| Application API | FastAPI |
| Review interface | HTML, CSS, JavaScript |
| Automated checks | pytest and database integration checks |
| Version control | Git and GitHub |

## Completion evidence

The first usable version should demonstrate:

- A real source import that reconciles with the captured response.
- A repeated import that creates no duplicate matches or false changes.
- A changed record producing an understandable history entry.
- Clear handling of malformed records and missing results.
- Recovery from an interrupted or failed import.
- Working API filters and local-note operations.
- Documented setup instructions, sample requests, and actual test results.

Deliberately altered test fixtures will be labeled as test data and kept separate from captured source responses. No throughput, uptime, or time-saving claims are currently established.

## Current setup

Stage 0 is complete and verified from user-supplied execution evidence on 2026-11-02. Editable project installation succeeded, Ruff checking passed, Ruff formatting verification passed with 10 files formatted, pytest passed 5 tests in 0.13 seconds, and `scripts/check_database.py` succeeded.

The verified SQL Server metadata was: server `CANVASIT`, login `sports_tracker_app`, database `SportsFixturesTracker`, edition `Standard Developer Edition (64-bit)`, and version `17.0.1000.7`. The local `.env` file is ignored by Git; no password or `.env` contents are recorded here.

Stage 1 source retrieval and raw snapshot code is implemented but NOT RUN. No live source request or raw snapshot has been verified. Later transformation, ingestion, API, UI, scheduler, and database schema stages remain not started.

## Stage 1 source retrieval

The reusable OpenLigaDB client targets the configured UEFA Champions League 2026/27 source: shortcut `ucl`, season `2026`, expected league ID `4946`, and endpoint `/getmatchdata/ucl/2026/{matchday}`. It validates only the basic source identity contract, preserves successful response bytes as `response.json`, and writes `metadata.json` with provenance, retrieval, HTTP, size, and SHA-256 fields. No transformation or repeated polling is included.

Competition settings remain configurable for future reuse through the OpenLigaDB shortcut, season, league ID, and matchday selection. The only currently planned competition is the UEFA Champions League 2026/27.

## Stage 0 WSL setup

Run these commands in WSL Bash from `/mnt/f/sports-fixtures-change-tracker` after reviewing the local prerequisites:

```bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
python -m pip install -e ".[dev]"
if [ ! -f .env ]; then cp .env.example .env; fi
```

Edit `.env` locally. Set `SQL_SERVER_HOST` to the current Windows host address visible from WSL, keep port `1433`, and enter the SQL login password only in this ignored local file. The currently reported address is `172.20.80.1`; it can change after a WSL or network restart. To inspect the current candidate address:

```bash
WIN_HOST_IP="$(awk '/^nameserver / {print $2; exit}' /etc/resolv.conf)"
printf 'Use SQL_SERVER_HOST=%s\n' "$WIN_HOST_IP"
```

After the local `.env` is complete, run the checks separately:

```bash
python -m pytest
ruff check .
python scripts/check_database.py
```

The first check covers offline configuration tests. The database script runs one read-only metadata query and must print only connection metadata, never the password or complete connection string. These checks were verified manually on 2026-11-02 with the results recorded above; they establish Stage 0 only.

After the Stage 0 checks, run each initial UCL capture separately when ready:

```bash
python scripts/fetch_openligadb.py --matchday 3
python scripts/fetch_openligadb.py --matchday 4
```

These commands contact OpenLigaDB and remain NOT RUN for Stage 1. Expect a match count, snapshot location, SHA-256 hash, and concise success message. Stop on the first failure and return only non-secret output. Do not poll aggressively; respect the provider's 60-requests-per-minute-per-IP limit.
