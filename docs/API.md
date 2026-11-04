# Local API

Status: implemented in the working tree; **NOT RUN**.

The service binds to `127.0.0.1` by default and rejects non-loopback clients when
`API_LOCAL_ONLY=yes`. It uses parameterized SQL Server queries, Pydantic models,
bounded pagination (`limit <= 200`), and generic database errors that do not expose
credentials or SQL details.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Database readiness |
| GET | `/api/competitions` | Loaded competition seasons |
| GET | `/api/matches` | Filtered fixture page |
| GET | `/api/matches/{match_id}` | Fixture, typed results, and goals |
| GET | `/api/matches/{match_id}/changes` | Field-level history |
| GET | `/api/import-runs` | Recent import outcomes |
| GET | `/api/validation-issues` | Recent validation evidence |
| GET | `/api/matches/{match_id}/notes` | Active local notes |
| POST | `/api/matches/{match_id}/notes` | Add a local note |
| PUT | `/api/notes/{note_id}` | Edit a local note |
| DELETE | `/api/notes/{note_id}` | Archive a local note |

`GET /api/matches` accepts `competition_season_id`, `matchday`, `finished`,
`search`, `limit`, and `offset`. Source scores remain nullable. The detail response
does not collapse `HalfTime` and `After90Minutes` into an ambiguous value.

## Note-write boundary

Writes are disabled unless `API_ALLOW_NOTE_WRITES=yes`. Enabling them also requires
a locally generated value of at least 16 characters in `API_NOTES_WRITE_TOKEN`.
Send it only in the `X-Notes-Token` header over the local interface. Never commit,
log, screenshot, or paste it. This is a local safety gate, not internet-grade user
authentication; do not expose the service publicly.

Notes are application-owned. Archiving a note is a soft delete. No note endpoint
updates provider matches, scores, goals, snapshots, or change history.
