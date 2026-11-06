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
| GET | `/api/dashboard-summary` | Aggregate fixture, goal, change, and checkpoint facts |
| GET | `/api/matches` | Filtered fixture page |
| GET | `/api/matches/{match_id}` | Fixture, typed results, and goals |
| GET | `/api/matches/{match_id}/changes` | Field-level observed history |
| GET | `/api/match-changes` | Cross-fixture observed change page with snapshot provenance |
| GET | `/api/sync-checkpoints` | Last successful matchday checkpoints |
| GET | `/api/import-runs` | Recent import outcomes |
| GET | `/api/validation-issues` | Recent validation evidence |
| GET | `/api/matches/{match_id}/notes` | Active local notes |
| POST | `/api/matches/{match_id}/notes` | Add a local note |
| PUT | `/api/notes/{note_id}` | Edit an active local note |
| DELETE | `/api/notes/{note_id}` | Archive an active local note |

`GET /api/matchdays` accepts optional `competition_season_id`.

`GET /api/dashboard-summary` accepts optional `competition_season_id`. It returns
counts for current fixture records, provider goal events, and recorded business
changes, plus the most recently processed successful checkpoint for the selected
season. A checkpoint is written only after a successful import transaction; its
timestamp is not evidence that a live polling process is currently running.
`detected_changes` is explicitly a count of field-level change events; it is not a
count of changed matches. `changed_fixtures` is the distinct-fixture count for those
events, so consumers can present the two measures without conflating them.
The repository reads these four facts through small, parameterized queries against
the deployed tables. If one component fails, the local server logs only the logical
operation name and exception type; it never logs SQL parameters, SQL text, connection
details, tokens, or credentials.

`GET /api/matches` accepts `competition_season_id`, `matchday`, `finished`,
`search`, `limit`, and `offset`. Search wildcard characters are escaped before the
parameterized `LIKE` query. Scores in match, result, and goal responses are nullable
because the source can genuinely omit them. The detail response never substitutes a
half-time value for `After90Minutes`.

`kickoff_utc`, result timestamps, checkpoint timestamps, and observation timestamps
are UTC API fields. The dashboard renders those values in the browser's local timezone.
`source_time_zone_id` is provider metadata, not an offset to infer missing timestamps:
the observed transition from `W. Europe Standard Time` to `NULL` remains source
evidence and is never silently converted.

`GET /api/match-changes` accepts `competition_season_id`, `limit`, and `offset` and
returns a page ordered by observation time. Each row includes the home/away fixture
identity, before/after values, source snapshot ID, a compactable SHA-256 value, and
snapshot retrieval time. It exposes only changes recorded by the importer; an empty
page means no observed field-level changes for the selection, not that a source was
never checked.

Operational list routes currently return bounded arrays rather than page envelopes.
Callers select `limit` and `offset`; the dashboard uses the latest 20 rows.

## Dashboard assets and resilience

`GET /` serves the framework-free dashboard. `/assets/app.js` and
`/assets/styles.css` are mounted from the packaged `sports_tracker.web` directory.
The page has visible loading shells and safe error panels for each API-backed
section. The cross-fixture change feed uses the API's `limit` and `offset` contract
for accessible Previous/Next pagination. All provider text is inserted with
`textContent`; browser assets do not contain SQL credentials, `.env` values, or note
tokens.

## Errors and security

Validation failures, including zero or negative resource IDs, use FastAPI's normal 4xx
responses. Valid but missing matches/notes return 404. `/health` returns 503 with
`Database unavailable` when its SQL probe fails.
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
