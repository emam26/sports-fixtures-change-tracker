# Local deployment and scheduling handoff

Status: API, wrapper, and scheduling configuration after the latest edits are **NOT
RUN**. Do not activate a task until every prerequisite below passes manually.

## Security posture

This is a single-machine application. Keep FastAPI bound to `127.0.0.1`; the CLI
refuses a non-loopback host and middleware enforces loopback by default. Do not add a
public tunnel, router forwarding, reverse proxy, or broad firewall rule. `.env`, raw
snapshots, runtime logs/locks, SQL backups, and note tokens stay outside Git.

## Local API

Where: WSL Bash  
Working directory: `/mnt/f/sports-fixtures-change-tracker`

```bash
source .venv/bin/activate
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

Expected: Uvicorn listens only on `http://127.0.0.1:8000`. Verify `/health`, `/docs`,
and `/` in the browser, then stop with Ctrl+C. A non-loopback `--host` must be refused.

## Dashboard verification

Where: browser on the same machine.  
Base address: `http://127.0.0.1:8000`

After any source edit, stop and restart the non-reload Uvicorn process, then open `/`
and perform a hard reload. Expected: the page immediately shows a styled overview,
match explorer, and change-intelligence feed with loading text rather than a blank
content area. In browser developer tools, confirm
`/assets/styles.css` and `/assets/app.js` each return `200`.

Then verify the following against only real local records:

1. The competition selector is populated from `/api/competitions`; selecting a season
   refreshes the summary, matchdays, fixtures, and change feed.
2. Overview cards show fixture, finished, upcoming, goal-event, and field-change-event
   counts. Confirm the field-change card also names the distinct number of affected
   fixtures; do not describe the event total as a count of changed matches. The small
   **Last updated** indicator must show only the timestamp from the latest successful
   synchronization recorded by the database, or `Not recorded` when none exists. It
   must not imply a newer source poll or expose snapshot/import-run identifiers.
3. Team search, matchday, All matches/Upcoming/Completed filters, kickoff order, and
   Clear change the fixture board without fabricated scores. Future scores must display
   `Not supplied`; fixtures without a reliable provider kickoff must remain last and
   read `Kickoff to be confirmed`, not a fabricated date or unsupported postponement.
4. Overview's Upcoming fixtures panel shows only unfinished local records in
   chronological kickoff order. Its empty state means no unfinished records are loaded,
   not that the provider has no future fixtures.
5. An empty search result renders a clear no-records state. With developer tools set
   to offline after the page has loaded, use a refresh button and confirm a visible,
   non-secret API error panel appears.
   Confirm the public page does not request `/api/import-runs`,
   `/api/sync-checkpoints`, or `/api/validation-issues`; those loopback endpoints are
   retained for local development and debugging only.
6. The change feed groups related field-level records into understandable fixture,
   result, or goal events. Verify Inserted, Updated, and Removed badges; meaningful
   summaries; observation/provenance labels; and expandable mapped field details. Raw
   storage field names must not be the primary labels. When the total exceeds one
   page, Previous and Next fetch the adjacent API page; changing competition or
   clearing filters returns to the first page.
7. Open a fixture with several changes. Verify that result/goal fields from one source
   observation are grouped, inserted records say that information was recorded rather
   than `Not supplied → value`, and the nested history scrolls vertically without
   text overlap or horizontal overflow. Observation/capture timestamps must be labeled
   as provenance, never presented as a goal occurrence time. Also verify typed
   results/goals, nullable scores, and visible local-note write state. Do not enter or
   screenshot a token unless note writes were deliberately enabled locally.
8. At a narrow viewport and with keyboard-only navigation, confirm focus indicators,
   section links, filters, buttons, and the detail dialog are usable.
   Confirm missing or invalid kickoff timestamps stay last in both kickoff orders.
   Rapidly change the competition, matchday, and search filters; the final selection
   must remain rendered rather than being overwritten by an earlier response or
   triggering a stale follow-on request.
9. Confirm browser developer tools reports no `/favicon.ico` 404. The page uses an
   inline favicon and must not make a separate favicon request.

The browser displays UTC API timestamps in its local timezone. A missing or changing
provider `source_time_zone_id` must not be used to infer an offset, and an ambiguous
source update time must remain absent/unconverted rather than being presented as a
precise local timestamp.

Stop and return the failing browser console message or non-secret network response if
an asset fails to load, an API response is malformed, or a panel remains in its loading
state. Do not expose the service beyond loopback while diagnosing it.

### Dashboard API audit check

Where: WSL Bash, project directory, while the local API is running.

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/api/dashboard-summary
```

Expected: a `200` JSON object with fixture, finished, upcoming, goal, field-change
event (`detected_changes`), and distinct affected-fixture (`changed_fixtures`) counts,
plus nullable latest-checkpoint fields. Stop if this returns HTTP 500; return
only the non-secret server log line containing `Dashboard summary read failed` and its
operation/error type. Do not return SQL parameters, a connection string, or `.env`
content.

## One-shot synchronization wrapper

Where: WSL Bash, same directory. This performs real HTTP and SQL operations.

```bash
bash scripts/run_scheduled_sync.sh --discover
```

Expected: one bounded pass. The script is not a daemon and does not poll. It uses the
project `.venv`, the Python process lock, bounded retries, canonical immutable source
capture, and structured logs under ignored `data/runtime/`.

Exit codes:

- `0`: every requested matchday imported or safely skipped;
- `1`: configuration/runtime failure or at least one failed matchday;
- `2`: wrapper prerequisite or command-line argument failure;
- `3`: another synchronization process owns the lock.

OpenLigaDB documents 60 requests per minute. Use a conservative interval, such as 30
minutes only during relevant periods and a wider interval otherwise. Never treat the
limit as a target or run repeated manual polling.

## Windows Task Scheduler preparation

First identify the exact WSL distribution. Where: Windows PowerShell.

```powershell
wsl.exe --list --verbose
```

Record the distribution name that owns `/mnt/f/sports-fixtures-change-tracker`. Stop
if the project wrapper has not already passed manually in that same distribution.

In Task Scheduler, choose **Create Task** (not Basic Task) and review these settings:

1. Run only when the intended local user is logged on unless you have separately
   reviewed non-interactive credential implications.
2. Trigger no more frequently than the reviewed operational interval.
3. Action program:
   `C:\Windows\System32\wsl.exe`
4. Action arguments (replace only the distribution placeholder):

   ```text
   -d <CONFIRMED-DISTRIBUTION> --cd /mnt/f/sports-fixtures-change-tracker bash scripts/run_scheduled_sync.sh --discover
   ```

5. Leave **Start in** empty; WSL's `--cd` supplies the project directory.
6. Under Settings, select **Do not start a new instance** when the task is already
   running. The application lock remains the second overlap guard.
7. Stop the task after a bounded duration (for example, 15 minutes) and do not force
   repeated immediate restarts.
8. Do not place a password, SQL connection string, note token, or `.env` value in the
   task name, arguments, description, or history.

Do not enable the trigger yet. Run the task once manually from Task Scheduler,
confirm exit result `0x0`, inspect the latest structured log, then compare SQL import
runs/checkpoints. Enable the trigger only after those checks pass.

## Failure recovery

If capture succeeds but import fails, preserve the snapshot and validate/replay it
offline with `scripts/import_snapshot.py`. Never delete raw snapshots as recovery.

If `data/runtime/sync.lock` remains after a crash, first confirm no sync process or
scheduled task is active and inspect the lock's host, PID, and acquisition time.
Remove it manually only after proving it is stale.

Use:

```bash
python scripts/inspect_operations.py --limit 20
```

and read-only queries against `dbo.import_runs`, `dbo.validation_issues`, and
`dbo.sync_checkpoints`. Logs may contain event names, error types, hashes, and
timestamps, but must never contain credentials, tokens, `.env` content, SQL
parameters, or complete connection strings.
