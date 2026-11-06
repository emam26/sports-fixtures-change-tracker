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

## One-shot synchronization wrapper

Where: WSL Bash, same directory. This performs real HTTP and SQL operations.

```bash
bash scripts/run_scheduled_sync.sh --matchday 3 --matchday 4
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
   -d <CONFIRMED-DISTRIBUTION> --cd /mnt/f/sports-fixtures-change-tracker bash scripts/run_scheduled_sync.sh --matchday 3 --matchday 4
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
