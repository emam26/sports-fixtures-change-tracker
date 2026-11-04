# Proposed commit structure

No commit or Git command was performed. After every relevant manual gate passes,
the user can review and create small commits in this order:

1. **Repair Stage 3 import and rollback tests** — importer bug fix, Ruff/format
   repairs, stronger idempotency/change/rollback tests.
2. **Add bounded synchronization and recovery tooling** — configuration, retry and
   last-change client support, lock/log/checkpoint coordinator, one-shot scripts.
3. **Add local FastAPI query service** — models, parameterized repository, security
   defaults, API tests.
4. **Add accessible local dashboard** — static HTML/CSS/JavaScript assets.
5. **Add evaluation, integration gates, and handoff documentation** — tests,
   evaluation helper, runbooks, deployment/scheduling proposal.

Do not include `.env`, `data/raw/`, `data/runtime/`, logs, lock files, local tokens,
or generated caches. If a gate fails, fix and repeat that gate before combining it
with later-stage work.
