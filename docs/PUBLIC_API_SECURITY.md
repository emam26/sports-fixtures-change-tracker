# Public API Security

Status: Phase 1 implementation complete in the working tree; manual execution and automated checks remain **NOT RUN**.

This document describes the explicit FastAPI deployment modes and the backend allowlist
used by the Sports Fixtures & Change Tracker. It is not a replacement for network
controls, TLS, secret management, future administrative authentication, or a cloud
security review.

## Deployment modes

### Local mode

Local mode is the default:

~~~dotenv
API_DEPLOYMENT_MODE=local
API_LOCAL_ONLY=yes
API_ALLOW_NOTE_WRITES=no
API_NOTES_WRITE_TOKEN=
~~~

Local mode preserves existing development behavior:

- the application is intended to bind to loopback;
- middleware rejects non-loopback clients when API_LOCAL_ONLY=yes;
- local /health, /docs, and /openapi.json remain available;
- operational read routes remain available for local diagnostics;
- note writes remain disabled unless explicitly enabled with a sufficiently long local
  token;
- synchronization, ingestion, SQL access, and local operational tooling are unchanged.

The local scripts/run_api.py wrapper continues to refuse non-loopback host values.

### Public read-only mode

Public mode is an explicit opt-in:

~~~dotenv
API_DEPLOYMENT_MODE=public_readonly
API_LOCAL_ONLY=no
API_ALLOW_NOTE_WRITES=no
API_NOTES_WRITE_TOKEN=
~~~

The application rejects:

- an unknown API_DEPLOYMENT_MODE;
- API_LOCAL_ONLY=no while API_DEPLOYMENT_MODE remains local;
- public_readonly with API_LOCAL_ONLY=yes;
- public_readonly with API_ALLOW_NOTE_WRITES=yes;
- any public configuration that enables note writes.

API_LOCAL_ONLY=no alone is therefore not sufficient to expose the application. The
public mode allowlist is enforced in backend middleware before FastAPI route dispatch.
Public mode permits only exact GET paths required by the dashboard and returns a
generic 404 for all other paths or methods.

This phase does not add an authentication service. Public mode is intentionally
read-only; administrative and note-write capabilities remain unavailable.

## Exact public route/method matrix

The following paths are allowed in public_readonly mode, and only with GET.

| Method | Exact path | Purpose |
| --- | --- | --- |
| GET | / | Dashboard HTML |
| GET | /assets/app.js | Dashboard JavaScript |
| GET | /assets/styles.css | Dashboard stylesheet |
| GET | /api/status | Minimal dashboard service status; note writes are always false |
| GET | /api/competitions | Loaded competition/season identity |
| GET | /api/matchdays | Matchday summaries |
| GET | /api/matches | Filtered, sorted, paginated fixture list |
| GET | /api/matches/{positive_integer} | One fixture detail |
| GET | /api/matches/{positive_integer}/changes | One fixture's observed changes |
| GET | /api/dashboard-summary | Overview counts and latest successful synchronization timestamp |
| GET | /api/freshness | Opaque successful-import revision and timestamp |
| GET | /api/insights/summary | Read-only analytical summary |
| GET | /api/insights/teams | Read-only team analytics |
| GET | /api/insights/teams/{positive_integer} | One team's read-only analytics |
| GET | /api/insights/matchdays | Read-only matchday analytics |
| GET | /api/match-changes | Paginated cross-fixture change intelligence |

Query strings remain subject to existing FastAPI validation, pagination limits, filters,
and repository parameterization. The path allowlist does not widen query validation.

Dynamic paths require an ASCII positive decimal identifier and are matched as complete
paths. These are not equivalent to an allowed path:

- a trailing slash, such as /api/matches/10/;
- an encoded identifier, such as /api/matches/%31%30;
- an encoded separator, such as /api/matches/10%2Fchanges;
- a path prefix or suffix containing an allowed path;
- a non-GET method;
- an unknown or malformed identifier.

Static assets are exact allowlist entries. Adding a new public asset requires explicit
backend review.

## Protected and unavailable in public mode

| Method/path | Reason |
| --- | --- |
| GET /health | Operational database health detail; not a dashboard dependency |
| GET /api/sync-checkpoints | Synchronization diagnostics |
| GET /api/import-runs | Import and failure provenance diagnostics |
| GET /api/validation-issues | Validation diagnostics and source evidence |
| GET /api/matches/{id}/notes | Local application-owned notes are not public |
| POST /api/matches/{id}/notes | Database write; note creation |
| PUT /api/notes/{id} | Database write; note update |
| DELETE /api/notes/{id} | Database write; note archive |
| GET /docs | OpenAPI documentation disabled in public mode |
| GET /redoc | ReDoc disabled in public mode |
| GET /openapi.json | OpenAPI schema disabled in public mode |
| Any PATCH, POST, PUT, DELETE, OPTIONS, HEAD, or other method | No public write or method bypass |

Unknown paths are denied as well. Public mode does not rely on hiding navigation
items or frontend request code; the backend policy is authoritative.

## Response and error boundaries

Public mode does not return:

- SQL text or SQL parameters;
- database credentials, passwords, tokens, or complete connection strings;
- filesystem paths or local snapshot directories;
- synchronization logs or internal lock details;
- Python tracebacks or exception messages;
- raw OpenLigaDB payloads;
- note-write tokens or deployment environment values.

Unexpected repository failures use the existing generic response:

~~~json
{"detail":"The request could not be completed."}
~~~

The application logs only the exception type for the generic handler. This is a safe
baseline, not a complete production observability design. Cloud logging still needs
reviewed redaction, correlation IDs, retention, access control, and alerting.

The /api/status route is allowed because the dashboard requests it to determine whether
local note controls should be rendered. Public configuration guarantees that note
writes are disabled, and the response contains no token or database detail.

No permissive CORS policy or proxy-trust behavior was introduced. The dashboard keeps
same-origin relative API requests. If a future deployment separates frontend and API,
CORS and trusted-proxy behavior require a separate review.

## Preserved functionality

This phase does not change:

- OpenLigaDB retrieval, discovery, rate limiting, or immutable raw snapshots;
- offline snapshot evaluation or SQL Server import;
- transactional rollback, provenance, change tracking, or synchronization checkpoints;
- fixture filters, server-side sorting, pagination, nullable scores, or freshness logic;
- Overview, Match Explorer, Insights, or Change Intelligence rendering;
- local diagnostic routes and local note-write authorization;
- the local loopback startup wrapper.

Public mode removes access to internal operations and note routes at the HTTP boundary;
it does not delete those backend capabilities or database records.

## Manual verification

All checks in this section are **NOT RUN** by the implementation agent.

### Offline checks

Where: WSL Bash. Directory: /mnt/f/sports-fixtures-change-tracker.

~~~bash
cd /mnt/f/sports-fixtures-change-tracker
source .venv/bin/activate
ruff check .
ruff format --check .
python -m pytest -q -m "not sqlserver"
~~~

Stop on the first failure and return only non-secret diagnostics.

### Public-mode configuration and API tests

The offline test suite should cover:

- default local configuration;
- explicit public-readonly configuration;
- rejection of API_LOCAL_ONLY=no without public mode;
- rejection of public mode with local-only access or note writes;
- every allowed GET route;
- denial of health, diagnostics, notes, documentation, unknown, encoded, and
  trailing-slash paths;
- denial of POST, PUT, PATCH, DELETE, OPTIONS, HEAD, and other methods;
- generic responses for repository failures;
- no repository write method calls in public mode.

### Manual local application checks

Where: WSL Bash, same directory.

~~~bash
python scripts/run_api.py --host 127.0.0.1 --port 8000
~~~

This starts local mode and is not a public deployment command. In a browser, verify
the dashboard at /, plus /health, /docs, local diagnostics, and existing note-write
behavior. Do not expose the process beyond loopback.

### Public-mode smoke check after a later deployment

Public mode has not been deployed by this phase. After a separately reviewed
deployment, verify only non-secret behavior:

1. GET / and both exact assets return 200.
2. All allowed football GET routes return their documented response shape.
3. /health, diagnostics, notes, /docs, /redoc, and /openapi.json return 404.
4. Encoded and trailing-slash variants return 404.
5. All non-GET methods return 404.
6. A forced repository failure returns the generic 500 body.
7. Browser developer tools show only approved dashboard requests.
8. No response, log, image, or source asset contains a credential, token, SQL string,
   traceback, or local filesystem path.

Do not treat a browser check as evidence that Azure SQL, Docker, Render, cloud storage,
or scheduled synchronization is ready.

## Remaining security work before Render

This phase is only the public API access boundary. Before Render deployment, still
complete and verify:

- Linux packaging of unixODBC and Microsoft ODBC Driver 18;
- explicit cloud start command using the platform port;
- Azure SQL least-privilege identities, TLS validation, firewall/network design, and
  connection timeouts;
- durable private raw-snapshot and operational-log storage;
- a database/distributed synchronization lock;
- GitHub Actions secret handling, concurrency, rate budget, and failure alerting;
- public rate limiting and edge protection;
- protected deployment configuration and dependency/container scanning;
- liveness/readiness semantics separate from internal database diagnostics;
- migration rehearsal and local-to-cloud count/hash/checkpoint reconciliation;
- authentication and authorization for any future operational or note-writing surface.

Public-read-only mode is not a guarantee of 24/7 availability, source completeness,
real-time updates, or protection from denial-of-service traffic.
