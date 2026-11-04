# Engineering evaluation plan

Status: planned; no Stage 3–10 evaluation below has been completed.

## Correctness

For preserved Matchdays 3 and 4, compare parsed provider match IDs and selected
fields against the saved response, then compare SQL current state against parsed
records. Required known totals are 18 matches per matchday and 36 unique IDs across
both. Matchday 3 has 18 completed matches with results. Matchday 4 has 18 unfinished
matches with absent result arrays; their scores must remain `NULL`/absent.

Report field agreement as `matching evaluated fields / evaluated fields`. Include
provider identity, teams, kickoff, finish state, each typed result, and each goal.
Do not report 100% unless every selected field was actually compared.

## Idempotency and duplication

Import one snapshot, replay it, then import the second same-hash Matchday 3 capture.
Measure duplicate domain rows for matches, result identity, and goal identity.

`duplication rate = unexpected duplicate rows / expected unique rows`

Target: zero. Provenance/import observations are expected to differ from domain
row counts and must not be mislabeled as duplicates.

## Change-detection accuracy

Use sanitized controlled fixtures to alter one field at a time: kickoff, location,
finish state, `HalfTime`, `After90Minutes`, result description, and goal data.
Compute precision and recall against the known injected changes. Include unchanged
replay as a negative control and omission of a match as a non-deletion control.
Target unit-fixture precision and recall: 1.0. These are simulated test changes and
must never be described as naturally observed upstream changes.

## Transaction recovery

Inject failure during result persistence and again during checkpoint advancement.
Verify current match/result/goal state, changes, and checkpoint equal the prior
commit; verify a failed import record exists where designed; then retry the same
snapshot and verify one successful transition. Repeat against a separate SQL Server
test database before claiming database-level rollback behavior.

## Incremental request efficiency

For a scheduled observation window, record last-change checks, full matchday
requests, skipped checks, retries, and failures from structured logs.

`full-fetch ratio = full matchday requests / last-change checks`

Lower is better only if correctness is retained. Audit a sample of skips against a
later full fetch. Never optimize by exceeding OpenLigaDB's 60-request-per-minute
limit or by trusting an ambiguous timestamp.

## Replay and latency

Replay each saved snapshot offline and verify deterministic parsed identities and
hashes. Measure parse latency with `scripts/evaluate_snapshot.py`; separately time
transactional import and API list/detail requests over repeated runs, reporting
median, p95, sample count, machine context, and cold/warm distinction. The small
initial dataset does not justify broad scalability claims.

## Threats to validity

Two matchdays do not cover knockout formats, postponements, penalties, extra time,
provider deletions, or every goal correction. Mock-store tests cannot establish
pyodbc/SQL Server transaction behavior. Last-change endpoint semantics require
continued empirical auditing. Expansion to all 144 league-phase fixtures and later
knockouts is gated on the evaluations above.
