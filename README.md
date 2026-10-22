# ⚽ Sports Fixtures & Change Tracker

> Football fixture imports, data checks, and observed change tracking with Python and SQL Server.

![Status: Design stage](https://img.shields.io/badge/status-design%20stage-yellow)
![Python](https://img.shields.io/badge/language-Python-3776AB?logo=python&logoColor=white)
![SQL Server](https://img.shields.io/badge/database-SQL%20Server-CC2927)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)

The project addresses a practical question: **what changed in a fixture or result, and which import recorded it?** The planned application collects football data from OpenLigaDB, checks incoming records, stores them in SQL Server, and keeps a history of observed changes.

> [!NOTE]
> This repository currently documents the design. Implementation has not started.
> The features, schema, and checks below are planned. Setup commands, screenshots,
> and test results will be added alongside working code.

## Why this project

A sports website can receive a fixture more than once, receive it before a result is available, or receive a changed kickoff time later. Simply appending every API response produces duplicates and loses the explanation of what changed.

The intended user is someone maintaining a small sports data application. They should be able to review the latest records, see changes observed by this application, and investigate imports that need attention.

## Data source

Data will come from [OpenLigaDB](https://www.openligadb.de/), a community-maintained sports database. It is not an official league feed.

The initial scope is Bundesliga (`bl1`), using the 2025/26 season for an initial load and 2026/27 for continuing updates. OpenLigaDB uses the season's starting year in its URLs.

Reference endpoints:

- [2025/26 matches](https://api.openligadb.de/getmatchdata/bl1/2025)
- [2026/27 matches](https://api.openligadb.de/getmatchdata/bl1/2026)
- [API documentation](https://api.openligadb.de/index.html)
- [OpenAPI specification](https://api.openligadb.de/swagger/v1/swagger.json)

Read access does not require an API key. The documented limit is 60 requests per minute per IP. The collector will use the provider's last-change endpoint to avoid repeatedly downloading unchanged matchdays.

OpenLigaDB data is provided under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Attribution and the applicable data-sharing requirements must accompany any published data extracts. A code license does not replace the data license.

## Planned workflow

1. Fetch a season or matchday and preserve the original JSON with its URL, retrieval time, and payload hash.
2. Check required identifiers, team references, timestamps, and result fields.
3. Store valid records in SQL Server and record rejected records with an explanation.
4. Compare incoming business fields with the stored match and record observed changes.
5. Commit records, validation issues, and the synchronization checkpoint together.
6. Expose the stored data through FastAPI and a small HTML, CSS, and JavaScript interface.

Unchanged imports should not create extra matches or change-history entries. Fetch timestamps will be kept separate from the fields used to identify a changed match.

## Planned features

- Initial season import and subsequent matchday updates.
- Current fixture and result lookup, with league, season, and team filters.
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

There is no runnable application release yet. Start by documenting the source contract and creating the SQL schema, then implement one manual season import. Installation and launch commands will be added alongside the corresponding code.
