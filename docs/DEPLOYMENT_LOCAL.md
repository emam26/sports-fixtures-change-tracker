# Local deployment and scheduling handoff

Status: implementation prepared; server and scheduler **NOT RUN**.

## Security posture

This is a single-machine application. Keep FastAPI bound to `127.0.0.1`; the CLI
refuses a non-loopback host and middleware enforces loopback by default. Do not add
router forwarding, public tunnels, or broad firewall rules. `.env`, raw snapshots,
runtime logs, lock files, and write tokens stay outside Git.

## One-shot operation

The supported scheduling unit is:

```bash
cd /mnt/f/sports-fixtures-change-tracker
bash scripts/run_scheduled_sync.sh --matchday 3 --matchday 4
```

It starts one process, acquires an atomic lock, performs at most one decision per
matchday, and exits. It is not a daemon and does not aggressively poll. The source
limit is 60 requests per minute; use a conservative interval such as 30 minutes
during relevant periods, with wider intervals outside them.

## Windows Task Scheduler proposal

Do not create a task until the exact wrapper passes manually. In Windows Task
Scheduler, create a user-owned task whose action is `wsl.exe` and arguments are:

```text
--cd /mnt/f/sports-fixtures-change-tracker bash scripts/run_scheduled_sync.sh --matchday 3 --matchday 4
```

Use a 30-minute trigger only when monitoring is needed, disable concurrent task
instances, and stop the task after a bounded duration. Do not store a password in
the arguments. Task creation and activation remain manual user operations.

## Recovery

If a run fails after capture, preserve the snapshot and validate/replay it offline
with `scripts/import_snapshot.py`. If `data/runtime/sync.lock` remains after a crash,
first confirm no sync process or scheduled task is active and inspect the lock's
host/PID/time. Remove it manually only after that check. Never delete raw snapshots
as a recovery mechanism.

Use `scripts/inspect_operations.py --limit 20` plus `dbo.import_runs`,
`dbo.validation_issues`, and `dbo.sync_checkpoints` to diagnose. Logs may name error
types and hashes but must never contain passwords, tokens, `.env` content, or a
complete connection string.
