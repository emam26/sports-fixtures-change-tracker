# Sports Fixtures & Change Tracker

**An auditable football fixture tracker with historical change detection, match analytics, and a public web dashboard.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Cloud%20DB-PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Source](https://img.shields.io/badge/Football%20data-OpenLigaDB-334155)](https://www.openligadb.de/)
![What I learned](https://img.shields.io/badge/What_I_learned-data_pipelines_%26_change_tracking-198754?style=flat-square)

### [**Open the current Render dashboard**](https://sports-fixtures-change-tracker.onrender.com/)

> **Coverage:** UEFA Champions League **2026/2027 league phase** (matchdays 1–8). This project tracks stored source observations and changes

## Overview

Sports Fixtures & Change Tracker collects football fixture data from OpenLigaDB, validates it before import, and preserves what changed between observations. It is built around a simple question: **not just what does a fixture say now, but what did the source report previously, and how did it change?**

> [!TIP]
> **I learned to validate football data, preserve source history, and trace fixture changes over time.**
>
> **I built:** a pipeline for immutable snapshots, validated imports, field-level change tracking, match analytics, and a public dashboard.
The project has two deployment paths:

- **Local data pipeline:** immutable OpenLigaDB response snapshots, validation, transactional import, and historical change tracking in Microsoft SQL Server.
- **Public, read-only dashboard:** GitHub Actions updates Neon PostgreSQL, verifies private snapshot provenance, exports validated JSON and deploys the HTML/CSS/JavaScript dashboard to GitHub Pages.

The existing Render site stays available during rollout. The GitHub Pages cutover and unattended cloud synchronization require the repository setup in [Deployment to GitHub Pages](docs/DEPLOYMENT_PAGES.md).

## Explore the dashboard

| Section | What you can explore |
| --- | --- |
| **Overview** | Competition context, fixture totals, completed and upcoming matches, stored goal-event counts, recorded changes, and upcoming fixtures. |
| **Match Explorer** | Search and filter fixtures by team, matchday, or status, with client-side filtering and predictable chronological ordering on Pages. |
| **Insights** | Read-only team, matchday, score, result, and goal-event summaries derived from stored records. |
| **Change Intelligence** | Fixture and result history, field-level before/after values, and source provenance where available. |


On Pages, **Last successful sync** shows when the published synchronization pass finished, in the browser’s timezone. Failed passes leave the published timestamp and data in place. Unfinished matches can have missing scores.

## Data coverage and verification

The implemented competition is **Champions League 2026/2027**. The internal source season key is `2026` (`ucl`, OpenLigaDB league ID `4946`); the user-facing competition name does not append the key again.

The following is an **owner-verified historical database snapshot**, not a continuously refreshed count or a live match result:

| Measure | Recorded value |
| --- | ---: |
| League-phase fixtures | **144** |
| Finished / unfinished fixtures | **72 / 72** |
| Stored result rows | **143** |
| Stored goal-event rows | **291** |
| Historical field-level changes | **936** |
| Teams represented | **36** |
| League-phase matchdays | **8** |

Result rows and goal-event rows are database records, not necessarily the number of finished matches or goals scored. In the cloud migration verification, **all 12 checked domain tables matched** between SQL Server and Neon PostgreSQL. The live `/api/competitions` endpoint was also observed responding with HTTP 200 after deployment configuration was corrected (November 13, 2026).

## Engineering highlights

- **Immutable evidence:** each captured response is stored with request metadata, retrieval time, byte count, and SHA-256 hash; existing captures are never overwritten.
- **Validation before import:** checks cover provider identity, match IDs, timestamps, teams, result types, and score relationships.
- **Transactional database writes:** fixtures, scores, events, change history, checkpoints, and import-run evidence are handled together.
- **Idempotent replay:** an unchanged source snapshot can be reprocessed without fabricating new changes.
- **Field-level change tracking:** historical observations are distinguishable from the current fixture state.
- **Static public access:** the browser reads a same-origin JSON export. GitHub Actions holds the Neon and object-store credentials and publishes an artifact from a fixed file allowlist.
- **Shared frontend:** HTML, CSS, and JavaScript use FastAPI locally and validated JSON on Pages.

### Architecture

```mermaid
flowchart TD
    A[OpenLigaDB] --> B[Local Python ingestion]
    B --> C[(Microsoft SQL Server)]
    C --> D[Local FastAPI dashboard]
    C -. Historical migration .-> G[(Neon PostgreSQL)]
    A --> E[Daily GitHub Actions sync]
    E --> F[(Private S3-compatible snapshot archive)]
    E --> G
    G --> H[Validation and SQL reconciliation]
    F --> H
    H --> I[Pages artifact with frontend and JSON]
    I --> J[Public GitHub Pages dashboard]
```

### Example: conflicting source results

One Matchday 2 snapshot included conflicting halftime results for provider match `87412` (Viking vs FC Bayern München): `2–0` and `0–0`, while the separately validated final result was `3–3`. The pipeline rejects ambiguous data by default. The Pages sync uses the previously reviewed quarantine for those exact two records and preserves the independently validated final score. New conflicts still block publication.

See [source notes](docs/SOURCE_NOTES.md), [architecture](docs/ARCHITECTURE.md), and the [manual runbook](docs/MANUAL_RUNBOOK.md) for the audit and recovery boundaries.

## Technology stack

| Area | Technologies |
| --- | --- |
| Data collection and validation | Python, `httpx`, Pydantic |
| Local persistence | Microsoft SQL Server, `pyodbc`, ODBC Driver 18 |
| Cloud persistence | PostgreSQL on Neon, `psycopg` 3 |
| Backend | FastAPI, Uvicorn |
| Frontend | HTML, CSS, vanilla JavaScript |
| Public hosting | GitHub Pages with GitHub Actions deployment artifacts |
| Quality checks | pytest, Ruff, SQL parity and snapshot checks |
| Football data provider | OpenLigaDB |

## Run locally

This section covers the **local SQL Server workflow**; it assumes SQL Server, the required ODBC driver, and database configuration are available.

```bash
git clone https://github.com/emam26/sports-fixtures-change-tracker.git
cd sports-fixtures-change-tracker

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --editable '.[dev,sqlserver]'
cp .env.example .env
```

Configure `.env` with your **own local** settings. Never commit `.env`, database URLs, passwords, snapshots, or logs.

Once the database is configured, run the local dashboard:

```bash
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**.

For existing snapshots, the project provides offline evaluation, dry-run import, and replay commands:

```bash
python scripts/evaluate_snapshot.py "<SNAPSHOT_DIRECTORY>"
python scripts/import_snapshot.py --snapshot "<SNAPSHOT_DIRECTORY>" --dry-run
```

Read [the manual runbook](docs/MANUAL_RUNBOOK.md) before running a real import or synchronization; those operations can write to the database and request fresh provider data.

### Validation

```bash
ruff check .
ruff format --check .
python -m pytest -q -m "not sqlserver and not neon"
```

SQL Server and Neon integration tests require isolated targets and explicit opt-in. See the [testing guide](docs/TESTING.md).

## Repository map

| Path | Purpose |
| --- | --- |
| [`src/sports_tracker/`](src/sports_tracker/) | Source client, snapshot management, validation, import, persistence, API, analytics, and synchronization |
| [`src/sports_tracker/web/`](src/sports_tracker/web/) | Browser interface and assets |
| [`scripts/`](scripts/) | Manual capture, migration, parity, import, replay, diagnostics, and API entry points |
| [`sql/`](sql/) | SQL Server schema and recovery scripts |
| [`tests/`](tests/) | Automated checks and opt-in integration tests |
| [`docs/`](docs/) | System design, deployment, operations, evidence, and testing documentation |
| `data/raw/` | Local immutable source snapshots (ignored by Git) |

### Documentation

| Guide | Start here for… |
| --- | --- |
| [Architecture](docs/ARCHITECTURE.md) | Components, data boundaries, and persistence design |
| [API](docs/API.md) | Dashboard and service endpoint contracts |
| [Project state](docs/PROJECT_STATE.md) | Current milestones, decisions, and outstanding tasks |
| [Build plan](docs/BUILD_PLAN.md) | Implementation phases and evidence ledger |
| [Manual runbook](docs/MANUAL_RUNBOOK.md) | Safe operation, troubleshooting, imports, and recovery |
| [Testing](docs/TESTING.md) | Unit, integration, and verification strategy |
| [GitHub Pages deployment](docs/DEPLOYMENT_PAGES.md) | Secrets, first deployment, activation, and recovery |
| [Deployment feasibility](docs/POSTGRES_DEPLOYMENT_FEASIBILITY.md) | PostgreSQL/Neon migration design and constraints |
| [Source notes](docs/SOURCE_NOTES.md) | OpenLigaDB observations and provider caveats |

## Deployment status and limitations

| Component | Status |
| --- | --- |
| Local SQL Server data pipeline | Implemented and owner-verified |
| Historical SQL Server → Neon migration | Verified (12/12 checked tables matched) |
| Render-hosted public dashboard | **Deployed**; database API connectivity verified |
| GitHub Pages and automated cloud sync | Implemented. Production setup and an observed scheduled run are pending. |
| Durable cloud storage for raw source snapshots | Private S3-compatible adapter. Production bucket and historical object audit require verification. |
| Knockout-stage tracking and other competitions | Outside the published scope |

The workflow is scheduled once daily at **8:17 AM Bangladesh time (02:17 UTC)**. GitHub may delay the start. **Daily polling can miss intermediate source changes**, including updates that are reversed between polls. The dashboard records observed changes and OpenLigaDB can update records late or leave fields incomplete. [Deployment and verification instructions](docs/DEPLOYMENT_PAGES.md)
