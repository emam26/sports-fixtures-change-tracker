# Local API

Status: implemented in the working tree; latest edits **NOT RUN**.

The service binds to `127.0.0.1` by default and rejects non-loopback clients when
`API_LOCAL_ONLY=yes`. It uses parameterized SQL Server queries, typed Pydantic
responses, bounded pagination (`limit <= 200`), and generic unhandled-error responses.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Database readiness |
| GET | `/api/status` | Non-secret local-mode and note-write status |
| GET | `/api/competitions` | Loaded competition seasons |
| GET | `/api/matchdays` | Loaded matchday counts and kickoff ranges |
| GET | `/api/matches` | Filtered fixture page |
| GET | `/api/matches/{match_id}` | Fixture, typed results, and goals |
| GET | `/api/matches/{match_id}/changes` | Field-level observed history |
| GET | `/api/sync-checkpoints` | Last successful matchday checkpoints |
| GET | `/api/import-runs` | Recent import outcomes |
| GET | `/api/validation-issues` | Recent validation evidence |
| GET | `/api/matches/{match_id}/notes` | Active local notes |
| POST | `/api/matches/{match_id}/notes` | Add a local note |
| PUT | `/api/notes/{note_id}` | Edit an active local note |
| DELETE | `/api/notes/{note_id}` | Archive an active local note |

`GET /api/matchdays` accepts optional `competition_season_id`.

`GET /api/matches` accepts `competition_season_id`, `matchday`, `finished`,
`search`, `limit`, and `offset`. Search wildcard characters are escaped before the
parameterized `LIKE` query. Scores in match, result, and goal responses are nullable
because the source can genuinely omit them. The detail response never substitutes a
half-time value for `After90Minutes`.

Operational list routes currently return bounded arrays rather than page envelopes.
Callers select `limit` and `offset`; the dashboard uses the latest 20 rows.

## Errors and security

Validation failures use FastAPI's normal 4xx responses. Missing matches/notes return
404. `/health` returns 503 with `Database unavailable` when its SQL probe fails.
Unexpected repository failures return HTTP 500 with only:

```json
{"detail": "The request could not be completed."}
```

The exception type can be logged locally, but SQL text, parameters, passwords,
connection strings, `.env` content, and note tokens are not returned.

## Note-write boundary

Writes are disabled unless `API_ALLOW_NOTE_WRITES=yes`. Enabling them also requires
a locally generated value of at least 16 characters in `API_NOTES_WRITE_TOKEN`.
Send it only in the `X-Notes-Token` header over the loopback interface. Never commit,
log, screenshot, or paste the token.

The dashboard exposes note controls only when `/api/status` reports writes enabled.
The user enters the token in a password field; it remains only in page memory and is
not stored in local/session storage. Archiving is a soft delete. No note endpoint
updates provider-owned matches, scores, goals, snapshots, changes, or checkpoints.

This token is a local safety boundary, not multi-user or public authentication. Do
not expose the service through a public bind, tunnel, reverse proxy, or port forward.
