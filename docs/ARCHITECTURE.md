# Architecture

## Scope and verification boundary

The implemented scope is UEFA Champions League 2026/27 (`ucl`, season `2026`,
expected league ID `4946`). The configured league-phase expectation is Matchdays 1-8
with 18 fixtures per matchday (144 total), while the owner has verified database
coverage only for Matchdays 3 and 4 (36 fixtures) as of 2026-11-06. Provider,
competition, season, expected matchdays, and expected fixtures-per-matchday are
configuration inputs. UCL is the only competition currently implemented and
documented; knockout groups remain opt-in after source-shape review.

The owner has verified the project foundation, two real raw matchday shapes, the
deployed 12-table schema, and the first Matchday 3 SQL import. The latest audit
edits, exact Matchday 3 replay, Matchday 4 import, API/browser flow, live one-shot
synchronization, and scheduling remain **NOT RUN**.

## Data flow

```text
OpenLigaDB documented endpoints
  -> bounded HTTP client and conservative last-change decision
  -> immutable response.json + metadata.json under ignored data/raw/
  -> typed offline parser and validation
  -> one SQL Server transaction
       current rows + changes + successful run + checkpoint
  -> parameterized FastAPI repository on loopback
  -> plain HTML/CSS/JavaScript dashboard
```

`response.json` is source evidence and is never rewritten. SQL Server stores
normalized current state, snapshot provenance, import outcomes, validation issues,
observed changes, checkpoints, and separately owned local notes.

## Source capture and identity

The reusable client builds encoded URLs from validated configuration, sends a
descriptive user agent, uses an explicit timeout, and applies bounded transient
retries. The matchday endpoint is:

```text
/getmatchdata/ucl/2026/{matchday}
```

Season discovery additionally compares both documented provider views:

```text
/getavailablegroups/ucl/2026
/getmatchdata/ucl/2026
```

Discovery treats neither endpoint as complete truth by itself. It reports groups
advertised only by one endpoint, builds a union of explicit positive group-order IDs,
and by default limits synchronization to configured league-phase matchdays.
Additional groups, including potential knockout rounds, require explicit opt-in; the
system does not infer a fixture or result for an absent group.

The basic source contract requires a top-level list and, for every item, `matchID`,
`leagueShortcut=ucl`, `leagueSeason=2026`, and `leagueId=4946`.

The single snapshot writer stores exact response bytes and separate metadata under:

```text
data/raw/ucl/2026/matchday-{n}/{UTC timestamp}_{full SHA-256}/
```

An existing directory is never overwritten. Identical content captured at different
times can intentionally produce distinct provenance directories with the same hash.
Season discovery responses are used only to select matchdays; every importable
backfill record still comes from a separately captured immutable matchday response.

## Observed OpenLigaDB mapping

The typed mapping is based on inspected saved Matchday 3 and 4 responses:

- identity: `matchID`, `leagueShortcut`, `leagueSeason`, `leagueId`, `leagueName`;
- teams: `team1` and `team2`, including IDs, names, abbreviations, group, icon, and
  Wikidata fields;
- fixture: `matchDateTimeUTC`, `matchDateTime`, `timeZoneID`, `matchIsFinished`,
  `group`, `location`, and `lastUpdateDateTime`;
- results: `matchResults[]`, retaining provider ID, explicit result type, order,
  names/descriptions, and nullable score pairs;
- goals: `goals[]`, retaining provider ID, scorer fields, minute, cumulative score,
  scoring team, and penalty/own-goal/overtime flags.

The deployed `match_results` table enforces one row per match and result-type kind.
Therefore the parser rejects duplicate result kinds by default. A narrowly scoped,
manual recovery flag can quarantine duplicate `HalfTime` variants when every
variant and the unambiguous `After90Minutes` result still pass the independent
score and goal consistency checks. No provider variant is selected: the final
result is retained, the conflicting half-time records remain in the immutable raw
snapshot, and a `validation_issues` row records the result IDs and score values
with `source_record_type=result`. Other duplicate kinds and any failed validation
remain import-blocking errors. Synchronization never enables this recovery flag.

The observed `lastUpdateDateTime` lacks an offset. It is preserved as raw text and is
not guessed into UTC. A timezone-aware `matchDateTimeUTC` is authoritative for
kickoff. Future fixtures with an empty result list keep absent/`NULL` scores; zero is
never a missing-value substitute. `HalfTime` and `After90Minutes` are stored and
interpreted separately. The schema permits a `NULL` kickoff. When an unfinished
provider fixture has no `matchDateTimeUTC`, parsing retains the fixture with a warning
and `NULL` kickoff rather than inventing a date; malformed non-empty timestamps remain
errors. A later source-backed kickoff update is persisted as a normal field-level
change. The importer does not infer a separate postponed or rescheduled status from
missing data; it preserves the provider's current finish flag, kickoff value, and
field-level transition instead.

`dbo.teams.team_icon_url` is nullable `nvarchar(2048)` URL metadata, not image
storage. Only trimmed absolute HTTP(S) URLs within that limit are retained. Embedded
`data:` images, malformed values, and oversized URLs become `NULL` with a warning
that includes only type and character count. If an existing team already has a safe
HTTP(S) icon, a later unusable source value does not erase it. Team identity and
fixture import do not depend on icon availability. The API/dashboard do not expose
or render team icon values.

## Transactional import semantics

The importer resolves and validates a local snapshot before opening SQL Server. It
then uses the deployed schema and parameterized pyodbc calls:

1. Ensure snapshot, competition, season, and import-run provenance.
2. Upsert teams by `(provider, provider_team_id)`.
3. Insert/update matches by `(provider, provider_match_id)`.
4. Insert/update typed results by match/provider result identity and result type.
5. Insert/update goals by match/provider goal identity.
6. Compare incoming business values with current values and record one field-level
   `match_changes` row per real transition.
7. Mark the run successful and advance its matchday checkpoint.
8. Commit once.

A new match is a baseline and creates no fabricated prior history. An exact or
same-content replay must not duplicate matches, results, goals, or changes. Snapshot
and import-run provenance can legitimately grow for distinct observations.

SQL Server DML batches that finish with `SCOPE_IDENTITY()` can expose intermediate
non-row result sets through pyodbc. The store advances to an active result set before
reading the identity. All domain writes, changes, successful status, and checkpoint
advancement use one transaction.

On failure, the primary transaction is rolled back. A separate failed-run record is
attempted only after rollback succeeds. That separate provenance can intentionally
retain the snapshot, competition/season identity, failed run, and safe validation
issue; these are not partial fixture data. If rollback itself fails, no new
failure-provenance transaction is attempted and database state is reported as
unconfirmed.

Missing result or goal rows in a later response are not interpreted as deletes in
the current implementation. Retraction/deletion semantics require provider evidence
and a deliberate policy before implementation.

## Incremental synchronization

The synchronizer performs one bounded pass and is not a daemon. An atomic file lock
is acquired before matchday planning, source discovery, or import, so overlapping
workers fail before they can perform synchronization work. With no explicit
`--matchday` or `OPENLIGADB_MATCHDAYS` override, the planner reads loaded fixture
matchdays and their successful checkpoint times from SQL Server. It prioritizes
unseen groups, unfinished fixtures at or within the configurable near-kickoff window,
recently completed matchdays, and finally older matchdays whose lower-frequency
interval has elapsed. A per-run cap prevents repeatedly fetching the complete season.
Missing kickoff values are never treated as scheduled times. A matchday with no
stored fixture rows is eligible only when provider discovery explicitly identifies it.

The optional `--discover` command compares the provider's available-groups and
full-season views, adds newly advertised groups within the configured scope to the
planner, and records the selection reason in the structured log. Explicit matchday
arguments remain the safe one-time backfill path. The planner does not infer that a
fixture is finished because its kickoff has passed.

After a selected matchday is fetched, the existing reliable timezone-aware last-change
signal is compared with the committed SQL checkpoint. Unsupported, empty, malformed,
failed, or timezone-ambiguous signals conservatively force a full fetch. The known
Matchday 2 conflicting `HalfTime` records remain strict-import failures; only the
reviewed manual snapshot command may enable the narrow quarantine policy.

Fetched responses use the same canonical immutable snapshot writer as manual Stage 1
capture. A failed import leaves the captured evidence available for offline replay.
One matchday failure is logged and reported without preventing later requested
matchdays from being attempted. A pass containing any failure exits non-zero.

Structured JSON logs and the lock live under ignored `data/runtime/`. Logged fields
are bounded operational identifiers, error types, hashes, and timestamps; credentials,
tokens, `.env` content, SQL parameters, and complete connection strings are excluded.
Checkpoint advancement remains inside the successful import transaction.

## API and browser boundary

FastAPI uses Pydantic response models, bounded pagination, validated filters,
parameterized SQL, and loopback middleware. The repository queries the deployed
column names directly. Nullable database scores remain nullable in API responses.
Unhandled failures return a generic response and log only the exception type.

The API provides health/status, competition-season and matchday discovery, a
season-scoped dashboard aggregate, a lightweight freshness revision, fixture list/detail, explicit results and goals,
per-fixture and cross-fixture field changes with source-snapshot provenance, import
runs, validation issues, synchronization checkpoints, local-note CRUD, and a
read-only analytics surface for season, team, and matchday insights.

Analytics uses a dedicated service over a repository query that returns one row per
fixture. The query pre-aggregates `match_goals` before joining them, and selects only
the `After90Minutes` result projection. The service excludes unfinished or
score-incomplete fixtures from completed-match denominators, retains valid 0-0
results, and calculates deterministic team home/away splits, recent form, matchday
trends, result distributions, and highest-scoring completed fixtures. It reports
observed source goal-event rows separately from score totals and does not implement
official UEFA standings or tiebreakers. Analytics is read-only and requires no schema
change.

Note writes are disabled by default. When enabled, they require a separate local
token. The browser holds that token only in page memory and sends it only in the
write header. It is never returned by the status endpoint, stored in browser storage,
or written to logs. This is a single-machine safety gate, not internet-grade
authentication. Notes are application-owned and cannot update source fixtures,
results, goals, changes, snapshots, or checkpoints.

The framework-free public dashboard has four API-backed sections in this order: Overview,
Match Explorer, Insights, and Change Intelligence. Overview presents a small **Last updated** value
from `latest_successful_sync_at_utc`; it is the timestamp of the latest successful
synchronization recorded by the database, not evidence of a more recent source poll.
The freshness endpoint returns an opaque revision derived from the latest successful
raw snapshot content hash and selected season. Identical source-byte replays therefore
do not force a browser reload, while the browser's own check time remains a separate
client-side fact.
It also presents a compact Upcoming fixtures list sourced from unfinished local
records and ordered by reliable UTC kickoff, with records lacking a kickoff placed
last and labelled as to be confirmed. The dashboard discovers loaded competition
seasons and matchdays, filters All matches, Upcoming, and Completed fixture views,
uses SQL-side Match Explorer ordering before pagination (all completed fixtures in
reverse kickoff order, then upcoming fixtures in nearest-kickoff order for the default
All view), orders nullable kickoffs deterministically, distinguishes missing scores, presents
explicit result/goal types and snapshot provenance, and optionally manages local notes. Every
section starts with a visible loading shell and renders an explicit empty or safe
failure state. Source text is assigned with `textContent`, not HTML injection.

Change Intelligence is a presentation layer over immutable field-level
`match_changes` rows. It groups fields only when they identify the same fixture,
result, or goal record within one observation/import provenance tuple. Recognized
fields receive human labels and constrained summaries such as `Match completed`,
`Final score recorded`, or `Goal event added`; the UI uses those summaries only when
the stored differences support them. Individual field details remain available in an
expandable, responsive disclosure. Snapshot observation/capture times remain labeled
as provenance and are never displayed as a goal occurrence time.

Import runs, validation issues, and synchronization checkpoints remain available only
through loopback API routes and local development/diagnostic tooling. The public
browser dashboard neither requests nor renders those operational records.

## Persistence backend selection

`DATABASE_BACKEND=sqlserver` remains the local default and uses the unchanged pyodbc
store/repository. `DATABASE_BACKEND=postgresql` selects Psycopg connections,
`PostgreSQLImportStore`, `PostgreSQLRepository`, PostgreSQL checkpoint readers, and the
database lease used by unattended synchronization. Parsing, validation, change
calculation, conflict quarantine, and snapshot replay remain shared Python logic.

The PostgreSQL schema is a separate reviewed artifact at
`sql/postgresql/001_initial_schema.sql`; it uses `timestamptz`, boolean values,
`RETURNING`, `LATERAL`, `LIMIT/OFFSET`, and an explicit checkpoint counter because
SQL Server `datetime2`, `bit`, `OUTPUT/SCOPE_IDENTITY`, `OUTER APPLY`, pagination, and
`rowversion` are not portable. The migration utility compares existing rows and stops
on mismatches. Cloud synchronization writes and verifies private S3-compatible
snapshot objects before import; missing credentials or an unavailable object store
fail before checkpoint advancement. Local disk is staging only and is not treated as
a Render/GitHub archive.

## Deployed schema assumptions

The implementation reuses the owner's deployed 12 tables without migration:

- source/provenance: `source_snapshots`, `import_runs`, `validation_issues`;
- identity/current state: `competitions`, `competition_seasons`, `teams`, `matches`,
  `match_results`, `match_goals`;
- history/operations: `match_changes`, `sync_checkpoints`;
- application-owned data: `match_notes`.

The source file is `sql/001_initial_schema.sql`, including
`source_snapshots.local_directory nvarchar(750)`. A schema mismatch must stop the
manual workflow; the application does not self-migrate the deployed database.

## Known limitations and research threats

- The latest static checks and offline suite have not been run by the owner.
- Exact SQL replay and Matchday 4 import are awaiting verification.
- Two matchdays do not cover knockout formats, postponements, penalties, extra time,
  source deletion, or every correction pattern.
- Mock-store tests cannot establish pyodbc/SQL Server transaction behavior; controlled
  destructive tests require a separate test database.
- Last-change endpoint semantics require continued empirical auditing against later
  full fetches.
- Automatic provider-side rate-limit discovery is absent; retries are bounded and
  scheduler frequency remains an operator responsibility. The documented 60 RPM
  limit is a ceiling, not a polling target. The browser freshness poll does not
  initiate source or SQL writes.
- Current full league-phase provider availability has not been verified in this
  working tree. The discovery and coverage code is **NOT RUN** until the owner
  performs the documented manual checks.
- There is no public deployment, external authentication, worker queue, or
  multi-competition user experience.
