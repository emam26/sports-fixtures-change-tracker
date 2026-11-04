# Architecture

## Implemented Stage 3–10 architecture — verification pending

This section describes code in the working tree. Every new component remains
**NOT RUN** after the 2026-11-03 edits.

```text
OpenLigaDB documented endpoints
  -> bounded client and conservative last-change check
  -> immutable response.json + metadata.json under ignored data/raw/
  -> typed offline parser and source validation
  -> one SQL Server transaction
       provenance + current state + field changes + checkpoint
  -> parameterized FastAPI query layer on 127.0.0.1
  -> plain HTML/CSS/JavaScript dashboard
```

`response.json` is evidentiary and is never rewritten. SQL Server owns normalized
current state, observations, validation issues, import outcomes, and checkpoints.
`dbo.match_notes` is application-owned and separate from source-owned fixture and
result fields.

### Import semantics

Provider IDs determine identity. A new match establishes a baseline and does not
fabricate earlier history. A later distinct observation creates one structured
record per changed field. Replaying unchanged content may add provenance but must
not duplicate domain rows or create false changes.

Unfinished matches with no provider result retain absent/`NULL` scores. Finished
results preserve explicit types including `HalfTime` and `After90Minutes`. Invalid
identity, relationship, timestamp, or score combinations fail validation before
current state changes.

Fixture/result/goal writes, changes, successful status, and checkpoint advancement
share a transaction. Failure provenance is recorded in a separate transaction
only after the primary rollback succeeds. If rollback fails, the importer does
not attempt or commit a failed-run record and reports that database state is
unconfirmed. Retrying is safe only after a confirmed rollback or manual database
inspection.

`dbo.teams.team_icon_url` is optional `nvarchar(2048)` metadata, not image
storage. The importer retains only trimmed absolute HTTP(S) URLs that fit that
limit. Embedded `data:` URIs, malformed values, and oversized URLs are stored as
`NULL` with a warning that reports only the type and character count. The current
browser API and dashboard display team names only; they do not expose or render
team-icon values.

### Synchronization and recovery

The synchronizer is one-shot. An atomic lock prevents overlap. A full matchday is
skipped only when a reliable timezone-aware last-change value is not newer than the
committed checkpoint. Unsupported, empty, malformed, or timezone-ambiguous signals
force retrieval. Transient retries use capped backoff.

Structured logs rotate under ignored `data/runtime/` and exclude credentials. If
capture succeeds but import fails, the snapshot remains available for offline
replay. Stale locks require manual inspection; the process never guesses that
another owner is dead.

### API and browser boundary

FastAPI uses typed models, bounded pagination, validated filters, parameterized
SQL, loopback middleware, and generic database errors. Note mutation is off by
default and requires a separate local token when enabled. It cannot update source
fixtures or results.

The browser provides fixture filters, result/goal detail, field changes, import
runs, and validation issues. Provider values use `textContent`, not HTML injection.

### Deferred scope

No public deployment, external authentication, worker queue, schema expansion, or
multi-competition scope is implemented. Expansion to all 144 UCL league-phase
fixtures and later knockouts follows only after Matchdays 3 and 4 pass correctness,
idempotency, rollback, replay, and incremental-efficiency evaluation.

## Scope and boundaries

The current implementation is UCL-only in its documented behavior:

| Property | Current value |
| --- | --- |
| Competition | UEFA Champions League 2026/27 |
| OpenLigaDB shortcut | `ucl` |
| Season | `2026` |
| Expected league ID | `4946` |
| Initial matchdays | `3`, `4` |
| Planned eventual coverage | 144 league-phase fixtures and later knockout fixtures |

Provider, competition, season, and matchday values are configuration inputs so
that another competition can be supported later. No other competition is
currently implemented or claimed.

## Layers

1. **Raw source layer** — Stage 1 stores the exact HTTP response bytes as
   `response.json` and provenance in `metadata.json`. A timestamp/hash-based
   directory is never overwritten. `data/raw/` is ignored by Git.
2. **Parsing and validation layer** — `src/sports_tracker/ingestion.py` reads
   local snapshots and maps the observed OpenLigaDB fields into typed records.
   It validates identity and relationships before database writes.
3. **Transactional persistence layer** — `SQLServerImportStore` uses the
   deployed SQL Server schema through parameterized pyodbc statements. The
   snapshot, import run, current rows, child rows, changes, and checkpoint are
   coordinated by one transaction. DML-plus-identity batches advance through
   intermediate ODBC result sets before reading `SCOPE_IDENTITY()`.
4. **Manual CLI layer** — `scripts/import_snapshot.py` supports offline
   dry-runs and explicit imports of one saved snapshot. It does not fetch the
   live API or schedule work.

## Observed OpenLigaDB mapping

The mapping is based on the saved UCL responses inspected before implementation:

- match identity: `matchID`, `leagueShortcut`, `leagueSeason`, `leagueId`, and
  `leagueName`;
- teams: `team1` and `team2`, including `teamId`, `teamName`, `shortName`,
  `tla`, `teamIconUrl`, `teamGroupName`, and `wikidataId`;
- fixture: `matchDateTimeUTC`, `matchDateTime`, `timeZoneID`, `matchIsFinished`,
  `group`, `location`, and `lastUpdateDateTime`;
- results: `matchResults[]`, with `resultID`, `resultName`,
  `resultTypeKind`, `resultTypeID`, `resultOrderID`, `pointsTeam1`, and
  `pointsTeam2`;
- goals: `goals[]`, with `goalID`, scorer fields, `matchMinute`, cumulative
  `scoreTeam1`/`scoreTeam2`, `scoringTeamId`, and own-goal/penalty/overtime
  flags.

The source’s `lastUpdateDateTime` was observed without an offset. It is retained
as raw source text rather than being guessed into UTC. `matchDateTimeUTC` is the
authoritative kickoff timestamp when it is present and timezone-aware.

## Import semantics

The importer follows this sequence:

1. Resolve a snapshot directory and verify its metadata, response byte count,
   SHA-256, provider, URL, shortcut, season, and league ID.
2. Parse every record. Invalid records create actionable validation issues;
   invalid input does not partially update current fixture data.
3. Begin a SQL transaction and ensure the source snapshot, competition, season,
   and import run exist.
4. Upsert teams by provider/team ID, then matches by provider/match ID.
5. Upsert explicit result rows by provider/result ID and result type. The
   `HalfTime` row is not substituted for `After90Minutes`.
6. Upsert goals by provider/goal ID, preserving the source’s cumulative score
   and flags.
7. Compare incoming values with the current match/child values. Insert a
   structured `match_changes` row only for an actual value transition. A first
   import establishes the baseline and does not fabricate a change from NULL.
8. Mark the import run successful and advance the checkpoint only after all
   writes are valid. Commit once.

An identical replay finds the existing provider keys, updates no business
values, and records no additional change history. A different snapshot can
record changes such as final score, finish state, kickoff, team, result, or goal
fields. Missing rows in a later source response are not interpreted as deletes
in Stage 3.

Unfinished future fixtures have no result rows when the source has an empty
`matchResults` array. The importer never changes an unknown future score to
zero. Any SQL score columns remain NULL/absent until an explicit source result
exists. Result types must always be interpreted explicitly: half-time is an
intermediate state and `After90Minutes` is the ordinary regulation full-time
state; additional source result types require deliberate handling.

## Failure and recovery

Validation happens before business-row writes. SQL failures roll back the
transaction. The importer then attempts a separate failed-run record with a
safe status/message; it never writes a password, connection string, or raw
secret to the database or console. Retrying the same snapshot is safe because
provider IDs and schema unique constraints make the operation idempotent.

Raw snapshot files are never edited by the importer. A failed import does not
delete or replace source evidence.

## Existing schema assumptions

Stage 3 intentionally reuses the deployed 12-table schema:

- `source_snapshots` stores source provenance and the local directory;
- `competitions` and `competition_seasons` identify the competition;
- `teams`, `matches`, `match_results`, and `match_goals` hold current data;
- `import_runs` and `validation_issues` provide operational provenance;
- `match_changes` stores field-level transitions;
- `sync_checkpoints` records the last successful snapshot;
- `match_notes` remains outside automated source ownership.

The importer assumes the SQL file currently deployed by the owner, including
the `source_snapshots.local_directory nvarchar(750)` limit, provider-aware
unique constraints, and the score/foreign-key constraints. It does not perform
schema migration. A deployment mismatch must stop the manual run and be
diagnosed before retrying.

## Deliberate limitations and open questions

- SQL Server integration has not been executed in this handoff.
- The ordinary test suite and lint/format checks have not been executed in this
  handoff.
- Source `lastUpdateDateTime` timezone semantics need a provider decision before
  it can be used as a UTC checkpoint value.
- Player identity is retained as source fields; no player dimension is created.
- A later stage must define deletion/retraction semantics for records omitted
  from a source response.
- Live retries, rate limiting, incremental request planning, and scheduling are
  not implemented.
- The exact goal count is source-data evidence to be confirmed by the owner’s
  dry run; it is not a hard-coded importer assumption.
