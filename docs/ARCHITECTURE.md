# Architecture

## Scope and verification boundary

The implemented scope is UEFA Champions League 2026/27 (`ucl`, season `2026`,
expected league ID `4946`), beginning with Matchdays 3 and 4. Provider, competition,
season, and matchday identity are configuration inputs for future reuse, but UCL is
the only competition currently implemented and documented. Planned expansion to all
144 league-phase fixtures and later knockout fixtures is gated on the initial
evaluation.

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
retries. The full-data endpoint is:

```text
/getmatchdata/ucl/2026/{matchday}
```

The basic source contract requires a top-level list and, for every item, `matchID`,
`leagueShortcut=ucl`, `leagueSeason=2026`, and `leagueId=4946`.

The single snapshot writer stores exact response bytes and separate metadata under:

```text
data/raw/ucl/2026/matchday-{n}/{UTC timestamp}_{full SHA-256}/
```

An existing directory is never overwritten. Identical content captured at different
times can intentionally produce distinct provenance directories with the same hash.

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

The observed `lastUpdateDateTime` lacks an offset. It is preserved as raw text and is
not guessed into UTC. A timezone-aware `matchDateTimeUTC` is authoritative for
kickoff. Future fixtures with an empty result list keep absent/`NULL` scores; zero is
never a missing-value substitute. `HalfTime` and `After90Minutes` are stored and
interpreted separately.

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
prevents overlapping local runs. It skips a full matchday fetch only when a reliable,
timezone-aware last-change signal is not newer than the committed SQL checkpoint.
Unsupported, empty, malformed, failed, or timezone-ambiguous signals conservatively
force a full fetch.

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

The API provides health/status, competition-season and matchday discovery, fixture
list/detail, explicit results and goals, field changes, import runs, validation
issues, synchronization checkpoints, and local-note CRUD.

Note writes are disabled by default. When enabled, they require a separate local
token. The browser holds that token only in page memory and sends it only in the
write header. It is never returned by the status endpoint, stored in browser storage,
or written to logs. This is a single-machine safety gate, not internet-grade
authentication. Notes are application-owned and cannot update source fixtures,
results, goals, changes, snapshots, or checkpoints.

The framework-free dashboard discovers loaded competition seasons and matchdays,
filters fixtures, distinguishes missing scores, presents result/goal provenance,
shows changes and operational status, and optionally manages local notes. Source
text is assigned with `textContent`, not HTML injection.

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
  scheduling frequency remains an operator responsibility. The documented 60 RPM
  limit is a ceiling, not a polling target.
- There is no public deployment, external authentication, worker queue, or
  multi-competition user experience.
