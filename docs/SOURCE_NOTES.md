# OpenLigaDB source notes

Current source identity:

- Competition: UEFA Champions League 2026/27
- Shortcut: `ucl`
- Season: `2026`
- Expected League ID: `4946`
- Configured league-phase expectation: Matchdays 1-8, 18 fixtures per matchday
- Verified imported coverage as of 2026-11-06: Matchdays 3 and 4 only

The source client uses the documented matchday route
`/getmatchdata/{leagueShortcut}/{leagueSeason}/{groupOrderId}`, the full-season route
`/getmatchdata/{leagueShortcut}/{leagueSeason}`, the available-groups route
`/getavailablegroups/{leagueShortcut}/{leagueSeason}`, and the documented last-change route
`/getlastchangedate/{leagueShortcut}/{leagueSeason}/{groupOrderId}`. A last-change
response is an optimization hint, not source truth: only a parsed timezone-aware
timestamp can suppress a full request, and later evaluation must audit skip
correctness. Unsupported, empty, malformed, failed, or timezone-naive signals
therefore require a full matchday retrieval.

Season discovery compares the available-groups and full-season views. Neither is
assumed complete in isolation: differences are reported for operator review, and all
backfill imports still begin with one separately preserved matchday response. The
full-season discovery response is not itself used as an import snapshot.

OpenLigaDB documents a limit of 60 requests per minute. The project therefore uses
one-shot synchronization, bounded retry, and conservative scheduling. It does not
provide rapid polling or repeated background loops.

Manual capture and one-shot synchronization use the same immutable snapshot writer
and `data/raw/ucl/2026/matchday-{n}/` directory convention.

The offline `report_season_coverage.py` command counts distinct provider `matchID`
values in valid local raw captures against the configured league-phase expectation.
It reports `not-captured` separately from malformed local capture evidence and never
claims database-import success. SQL import-run/checkpoint checks remain the separate
evidence for importer outcomes.

Before publishing or redistributing source data, review the provider's current
terms and attribution guidance. This repository keeps raw captures local and
Git-ignored by default; it does not assume redistribution permission.

Authoritative references:

- <https://api.openligadb.de/index.html>
- <https://github.com/OpenLigaDB/OpenLigaDB-Samples/blob/master/README.md>
