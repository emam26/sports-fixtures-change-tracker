# OpenLigaDB source notes

Current source identity:

- Competition: UEFA Champions League 2026/27
- Shortcut: `ucl`
- Season: `2026`
- Expected League ID: `4946`
- Initial scope: Matchdays 3 and 4

The source client uses the documented matchday route
`/getmatchdata/{leagueShortcut}/{leagueSeason}/{groupOrderId}` and the documented
last-change route
`/getlastchangedate/{leagueShortcut}/{leagueSeason}/{groupOrderId}`. A last-change
response is an optimization hint, not source truth: only a parsed timezone-aware
timestamp can suppress a full request, and later evaluation must audit skip
correctness. Unsupported, empty, malformed, failed, or timezone-naive signals
therefore require a full matchday retrieval.

OpenLigaDB documents a limit of 60 requests per minute. The project therefore uses
one-shot synchronization, bounded retry, and conservative scheduling. It does not
provide rapid polling or repeated background loops.

Manual capture and one-shot synchronization use the same immutable snapshot writer
and `data/raw/ucl/2026/matchday-{n}/` directory convention.

Before publishing or redistributing source data, review the provider's current
terms and attribution guidance. This repository keeps raw captures local and
Git-ignored by default; it does not assume redistribution permission.

Authoritative references:

- <https://api.openligadb.de/index.html>
- <https://github.com/OpenLigaDB/OpenLigaDB-Samples/blob/master/README.md>
