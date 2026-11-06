# Testing strategy

Status: all tests added or changed in the 2026-11-06 audit are **NOT RUN**. The last
owner-supplied baseline before this audit was 56 passing non-SQL tests; it does not
verify the current working tree.

## Offline default suite

Run from WSL Bash in `/mnt/f/sports-fixtures-change-tracker`:

```bash
source .venv/bin/activate
python -m pytest -q -m "not sqlserver"
```

This suite is designed to require neither internet access nor a live database. It
covers:

- source URL construction, identity contract, invalid JSON, HTTP/network failures,
  explicit timeouts, finite bounded retries, and mock transport behavior;
- immutable byte capture, metadata, SHA-256, canonical directories, and no overwrite;
- typed parsing of completed and unfinished source records;
- safe HTTP(S) team icons, embedded-data omission, oversized-value omission, and
  preservation of a previously stored safe icon;
- initial import, exact replay, distinct same-content snapshots, controlled fixture,
  result, and goal changes, and non-deletion semantics for omitted records;
- rollback during child mutation and checkpoint advancement, failed-run provenance,
  rollback failure reporting, and safe retry;
- credential-safe CLI reporting when the initial SQL connection cannot be opened;
- SQL cursor handling for intermediate non-row result sets and credential-redacted
  diagnostics;
- overlap locking, deployed-schema checkpoint lookup, conservative last-change
  fallback, canonical sync capture, continuation after a partial failure, duplicate
  matchday rejection, and non-zero partial-failure CLI exit;
- API validation, nullable score serialization, generic failure responses, note
  authorization/update/archive, and status/matchday/checkpoint routes;
- repository SQL mapping against the actual deployed table/column names and note
  transaction behavior;
- CLI configuration propagation for offline snapshot evaluation.

HTTP tests use `httpx.MockTransport`. Import unit tests use an in-memory transactional
store. Repository tests use scripted cursors. None of these substitutes for real
SQL Server behavior.

## Static checks

Run before pytest:

```bash
ruff check .
ruff format --check .
```

Do not use `--fix` in the evidence pass. Preserve the first diagnostic and stop if a
check fails.

## Opt-in SQL Server checks

Tests marked `sqlserver` are skipped unless explicitly enabled:

```bash
RUN_SQLSERVER_INTEGRATION=yes python -m pytest -q -m sqlserver
```

The existing integration test is read-only and verifies the expected 12-table schema.
It must target the confirmed dedicated `SportsFixturesTracker` database. SQLite is
not used as a SQL Server substitute.

Controlled mutation/rollback tests must use a separate disposable test database with
explicit owner approval. They must never delete or mutate the project database that
contains the verified import. Synthetic failures and controlled changes must be
labeled as tests, not naturally observed provider events.

## Manual SQL and browser checks

Automated API tests do not verify the real repository against SQL Server. After the
offline suite and read-only schema check pass, manually verify:

- exact Matchday 3 replay leaves match/result/goal/change counts unchanged;
- Matchday 4 adds 18 unfinished matches and no fabricated result/goal rows;
- import runs and checkpoints reference the expected snapshot/run IDs;
- `/health`, `/api/competitions`, `/api/matchdays`, `/api/matches`, match detail,
  `/api/sync-checkpoints`, import runs, and validation issues return successfully;
- the browser handles loading, empty, error, nullable score, narrow-screen, and
  keyboard-focus states;
- note writes return 403 by default and work only with an enabled local token.

Follow [MANUAL_RUNBOOK.md](MANUAL_RUNBOOK.md) for the ordered commands and SQL.

## Evidence standard

For every category, record date/time, exact command or browser action, selected and
deselected test counts, pass/fail summary, elapsed time, and non-secret warnings.
Keep these categories separate:

1. static checks;
2. offline tests;
3. SQL Server schema checks;
4. real snapshot replay/import checks;
5. live source synchronization;
6. API checks;
7. browser checks;
8. scheduled runs.

A pass in one category does not imply another passed. Never infer benchmarks,
database behavior, or live-source behavior from mocks alone.
