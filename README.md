# Codex Assignment — Professional GitHub Portfolio README

Act as a senior data engineer, technical documentation specialist, and GitHub portfolio reviewer.

Project: Sports Fixtures & Change Tracker

Repository: `/mnt/f/sports-fixtures-change-tracker`

## Objective

Rewrite the root `README.md` as a polished, professional, evidence-based GitHub portfolio case study.

Use the presentation quality and structure of a strong data-engineering portfolio README: informative introduction, technology badges, verified metrics, dashboard sections, engineering achievements, architecture, reproducibility, and limitations.

This README should appeal to recruiters and engineers hiring for:

- Data Engineer
- Data Solutions Engineer
- SQL Server Developer
- Python Developer
- Backend/Data Integration Engineer

Do not exaggerate the project's technical maturity.

## 1. Critical evidence rule

**Only present completed and verified work as completed.**

The repository may contain code for features that have not been executed or manually validated.

Code existence is not proof of successful operation.

Before drafting, inspect:

- Existing root README
- Architecture documentation
- API documentation
- Testing documentation
- Build plan
- Manual runbook
- Current Python implementation
- SQL schema and queries
- Dashboard HTML/CSS/JavaScript
- Existing screenshot directories, if any

Cross-check every claim against repository evidence and the verified facts below.

Never invent results, timestamps, metrics, screenshots, deployments, or successful executions.

## 2. Known verified project evidence

Project name: Sports Fixtures & Change Tracker.

Source: OpenLigaDB.

Competition identity:

- UEFA Champions League 2026/27
- Shortcut: `ucl`
- Season: `2026`
- Expected league ID: `4946`

Previously verified SQL database state:

- 144 unique league-phase fixtures
- 72 finished fixtures
- 72 unfinished fixtures
- 143 stored result records
- 291 stored goal records
- 936 historical field-level change records

Previously verified API observations:

- 36 teams returned by the Insights teams endpoint
- 8 matchdays returned by the matchdays endpoint
- Insights summary, teams, and matchdays endpoints returned successful responses
- Match Explorer API sorting was verified against actual stored fixtures
- Local SQL Server connectivity succeeded

Latest explicitly reported automated verification:

- 129 tests passed
- 1 SQL Server test deselected
- Ruff lint passed
- Ruff formatting passed
- One nonblocking Starlette deprecation warning

These are historical verification observations, not claims about the current live state. Check for any newer evidence in repository documentation before deciding which evidence snapshot to report.

Do not call 291 goal records "291 goals scored" unless independently proven. Do not call 936 field-level changes "936 match events" or "936 score corrections."

## 3. Important engineering accomplishments

Describe only those supported by evidence:

- Python integration with OpenLigaDB
- Immutable raw JSON snapshots
- Source-identity validation
- SQL Server data modeling
- Transactional snapshot ingestion
- Idempotent replay
- Match and result normalization
- Result and goal record storage
- Field-level change tracking
- SQL import history and checkpoints
- Read-only FastAPI endpoints
- Football Insights analytics
- Local HTML/CSS/JavaScript dashboard
- Match Explorer filtering, sorting, and pagination

Explain how these components contribute to data reliability.

Do not describe the project as a big-data system, enterprise production deployment, or machine-learning platform.

## 4. Matchday 2 data-quality case study

Include a short, accessible example of real-world source-data quality handling.

The OpenLigaDB snapshot contained contradictory HalfTime result records for match 87412:

- Result ID 129519: 2–0
- Result ID 129520: 0–0

The approved recovery policy:

- Leaves strict validation as the default
- Requires explicit opt-in for conflicting nonfinal results
- Quarantines both conflicting halftime variants
- Does not arbitrarily choose a score
- Retains independently valid full-time data
- Preserves the immutable raw snapshot
- Records validation provenance

Verified recovery outcome:

- Matchday 2 import succeeded
- All 144 league-phase fixtures were subsequently present
- Match 87412 stored only its independently valid 3–3 After90Minutes result
- Total result records reconciled to 143
- Existing 936 field-level changes remained preserved

Write this as a concise engineering achievement, not a lengthy incident report.

## 5. Dashboard presentation

Organize the dashboard explanation in this order:

1. Overview
2. Match Explorer
3. Insights
4. Change Intelligence

Explain each section in plain language.

Mention only working, verified behavior.

The project has recently received additional UI changes, including chronological sorting, visual spacing adjustments, and automatic refresh features.

Do not claim that the latest UI changes have passed browser acceptance unless you find actual evidence.

Do not advertise guaranteed live scoring.

### Screenshots

Search for genuine dashboard screenshots already present in the repository.

Only embed screenshots if:

- The image file actually exists
- The image shows the real running application
- The represented implementation has been verified
- No secrets or sensitive local information are visible
- The screenshot accurately represents the documented state

Use descriptive captions and meaningful image alt text.

If suitable screenshots do not exist, do not invent screenshots, link to nonexistent image files, or add image placeholders.

A text-only dashboard section is acceptable until verified screenshots are available.

## 6. Automatic synchronization and freshness

Treat this section carefully.

Some scheduler-ready synchronization and browser-freshness functionality has been implemented.

Previously verified:

- Unit/API checks passed
- `/api/freshness` returned a revision and timestamp
- Repeated reads returned a stable revision

Not yet proven by the supplied evidence:

- End-to-end automatic synchronization
- Successful scheduler execution
- Actual new source updates imported automatically
- Freshness revision changing after meaningful new data
- Browser automatic refresh after a real synchronization
- Public cloud deployment
- Continuous unattended operation

Do not describe these as completed production features.

If necessary, explain the established manual synchronization capability and current operational limitations in the Limitations section.

## 7. README structure

Create an attractive but concise README using the following sections.

### Title and technology badges

Use Shields.io badges for relevant technologies.

Avoid badges claiming successful CI, deployment, production readiness, or live operation without evidence.

### Project overview

Write a short, clear paragraph explaining the problem and solution.

### Verified project highlights

Present the verified fixture, team, result, goal-record, and field-change counts.

Clearly identify the evidence snapshot and measurement definitions.

### Football dashboard

Explain the four sections.

Embed only verified screenshots, if available.

### Key engineering achievements

Highlight:

- Immutable snapshots
- Transactional SQL ingestion
- Data validation
- Idempotent imports
- Historical change detection
- Source-conflict quarantine
- Analytics APIs

### Data pipeline and architecture

Include a GitHub-compatible Mermaid diagram describing the implemented pipeline:

OpenLigaDB → raw snapshots → validation/normalization → SQL Server → change history and analytical queries → FastAPI → dashboard.

Distinguish existing manual or scheduler-ready synchronization from proven automatic cloud operation.

### Data quality and validation

Summarize the Matchday 2 conflict and explain safeguards.

### Reproducibility and quality

Use accurate setup commands and actual test evidence.

Distinguish offline tests from opt-in SQL Server integration tests.

Do not include credentials, private network addresses, personal Windows paths, or secrets.

### Technology stack

Python, SQL Server, T-SQL, pyodbc, FastAPI, OpenLigaDB, vanilla HTML/CSS/JavaScript, Ruff, pytest, Git.

Use the project's actual dependency declarations where possible.

### Repository guide

Link to actual existing repository directories and documentation.

Verify relative paths.

### Limitations

Explain:

- OpenLigaDB is community-maintained, not an official UEFA feed
- Data accuracy depends partly on provider records
- Dataset represents a specific imported snapshot
- Source timestamps can be missing or ambiguous
- Automatic cloud operation has not been established
- Local development is not public production hosting
- Advanced live match-event feeds, possession and xG are not established capabilities

Do not add an ambitious future roadmap presented as implemented functionality.

## 8. Style requirements

Use the supplied Olist README as a structural inspiration, not as content to copy.

The README should be:

- Professional
- Clear
- Visually organized
- Concise but informative
- Recruiter-friendly
- Technically credible
- Grounded in verified evidence

Prefer a strong introduction, useful metrics and clear diagrams over excessive decorative badges.

Avoid generic AI-sounding claims such as:

- Revolutionary analytics platform
- Enterprise-grade production infrastructure
- Seamless real-time intelligence
- Cutting-edge AI-driven predictions
- Fully automated live football system

Do not present unexecuted features as achievements.

Use precise distinctions between matches, result rows, goal-event rows and change-history rows.

## 9. Change scope

**Modify only the root `README.md`.**

Do not modify application code, SQL scripts, tests, project data, documentation outside the root README, or configuration.

Do not delete or overwrite existing project evidence.

Do not run Python, Ruff, pytest, SQL, HTTP, Git, imports, synchronization or deployment.

You may inspect repository files through read-only operations.

Do not commit or push.

## 10. Final report

After updating README.md, report:

1. Sections created or revised
2. Verified facts used
3. Evidence source for every numerical claim
4. Screenshots included, if any
5. Claims deliberately omitted because they are unverified
6. Relative links checked through inspection
7. Any unresolved documentation inconsistencies
8. Confirmation that only README.md was modified

Mark execution-based verification as NOT RUN.

Implement the README rewrite now, without touching unfinished features.
