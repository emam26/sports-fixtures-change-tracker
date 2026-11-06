# Engineering evaluation plan

The owner has verified one successful Matchday 3 baseline import. The comparative
evaluations below remain planned and **NOT COMPLETED** unless explicitly identified
as prior source evidence.

## Fixed source evidence

- Matchday 3: 18 completed matches, 36 result records, 74 goals in the successful
  import, response SHA-256
  `88d0c86d9fda325e1dd2f90cc1ef81eacafa3ef47df9e5d31335912519e1c348`.
- Matchday 4: saved response has 18 unfinished matches and empty result arrays,
  response SHA-256
  `a6758a21588bd4d8634882b5909ed32d54f03b56a8a9dd1a4280155bd425f245`.
- Two Matchday 3 captures have the same content hash but different retrieval times.

These values are acceptance inputs, not performance or idempotency results.

## League-phase coverage

The configured UCL league-phase target is eight matchdays with 18 fixtures each (144
expected fixtures). Run `scripts/report_season_coverage.py` before and after each
backfill batch. It counts distinct provider match IDs from immutable local source
captures only; `not-captured` is a local evidence gap, not proof that the provider has
no fixture or that the importer failed. Pair it with the manual SQL per-matchday
aggregate and import-run status query in `MANUAL_RUNBOOK.md`.

```text
capture coverage = distinct valid raw provider match IDs / 144
import coverage  = distinct imported provider match IDs / 144
```

Report missing source-advertised groups, invalid captures, failed imports, duplicate
provider IDs, and unscheduled (`NULL` kickoff) fixtures separately. Do not collapse
these failure modes into one percentage or claim full coverage before both measures
are verified.

## Parsing correctness

Replay each immutable snapshot with `scripts/evaluate_snapshot.py` and the import
CLI dry run. Compare parsed provider IDs and selected fields directly with saved
metadata/response evidence, then compare imported SQL rows with the parsed records.

Required fields include competition identity, team IDs, kickoff, finish state,
every explicit result type/score, and every goal identity/cumulative score.

```text
field agreement = matching evaluated fields / all evaluated fields
```

Report the numerator and denominator. Do not state 100% unless every declared field
was actually compared. Matchday 4 scores must remain absent/`NULL`.

## Idempotency and duplication

Record domain counts, import-run counts, snapshot counts, and change counts before
and after:

1. exact replay of the already imported Matchday 3 directory;
2. import of the second same-hash Matchday 3 capture;
3. replay of the same Matchday 4 directory.

```text
duplication rate = unexpected duplicate domain rows / expected unique domain rows
```

Target: zero for matches, result identity, and goal identity. Additional distinct
snapshot/import-run provenance is expected and must not be mislabeled as a domain
duplicate.

## Change-detection accuracy

Use sanitized unit fixtures to alter one field at a time: kickoff, location, finish
state, `HalfTime`, `After90Minutes`, result description, and goal data. Include exact
replay as a negative control and omission as a non-deletion control.

```text
precision = true recorded changes / all recorded changes
recall = true recorded changes / all injected changes
```

Target for deterministic unit fixtures: 1.0 precision and 1.0 recall. These are
synthetic controlled changes and must never be presented as naturally observed
upstream events.

## Transaction rollback and recovery

Offline tests inject failures during result mutation and checkpoint advancement.
They must show that teams/matches/results/goals/changes/checkpoints return to the
prior commit, safe failed-run provenance remains where designed, and a retry can
succeed.

Before making a database-level atomicity claim, repeat a controlled test against a
separate disposable SQL Server test database. Record before/after checksums or row
counts and transaction status. Never inject failure or delete data in the project
database containing the verified Matchday 3 import.

## Request efficiency

For an explicitly scheduled observation window, count structured events:

- last-change checks;
- full matchday fetches;
- reliable skips;
- retry attempts;
- matchday failures and partial-failure passes.

```text
full-fetch ratio = full matchday requests / last-change checks
```

Lower is useful only if correctness is retained. Audit a sample of reliable skips
against a later manual full fetch. Unsupported, malformed, failed, or timezone-naive
signals must not produce a skip. OpenLigaDB's 60 RPM limit is a hard ceiling, not an
evaluation target.

## Latency and throughput

Measure parsing, SQL import, and API list/detail separately. Report median, p95,
sample count, machine context, dataset size, and cold/warm conditions. Parsing can be
measured with `scripts/evaluate_snapshot.py`; SQL and API timing must be measured by
the owner during real manual runs.

```text
fixture throughput = successfully processed fixtures / import elapsed seconds
```

Do not infer scalability from two matchdays or from one timing sample. No benchmark
number is currently claimed.

## Threats to validity

Two matchdays do not cover knockout formats, postponements, penalties, extra time,
provider deletions, every goal correction, or season transitions. Mock transports
and in-memory stores cannot establish network or SQL Server guarantees. The provider
last-change endpoint needs ongoing empirical comparison with preserved full responses.
