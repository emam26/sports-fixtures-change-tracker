# Testing strategy

All Stage 3 repair and Stage 4–10 tests are **NOT RUN** after the latest edits.

## Offline default suite

`pytest -q -m "not sqlserver"` is designed to require neither internet nor a live
database. It covers:

- source contract, invalid JSON, HTTP failures, and endpoint construction;
- immutable byte capture, SHA-256, and no-overwrite behavior;
- typed parsing of finished and unfinished matches;
- initial import, exact replay, distinct identical captures, score corrections,
  kickoff/location/result-description changes, and omitted-record semantics;
- rollback at result mutation and checkpoint advancement, failed-run evidence, and
  successful retry;
- overlap locking, conservative last-change decisions, and bounded retry behavior;
- API filtering, typed result responses, missing resources, and note-write gates.

MockTransport is used for HTTP tests. The in-memory import store models transaction
commit/rollback without pretending to reproduce SQL Server-specific behavior.

## Opt-in SQL Server checks

Tests marked `sqlserver` are skipped unless `RUN_SQLSERVER_INTEGRATION=yes`. Run them
only against the confirmed dedicated database after reviewing the test. SQLite is
not used as a substitute. The initial integration check is deliberately read-only:
it verifies the expected 12 tables. Controlled mutation and rollback evaluation
must use a separate test database, never the production-like project database.

## Required evidence

Record the exact command, date, selected/deselected count, pass/fail count, elapsed
time, and relevant tool version. A passing offline suite does not imply SQL Server,
live source, API, browser, or scheduler success. Each category needs separate
evidence in `docs/BUILD_PLAN.md`.
