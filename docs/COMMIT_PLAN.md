# Proposed commit structure

No Git command was performed during the release-readiness audit. Commit only after
the latest static checks, offline tests, SQL replay/import checks, API/browser review,
and documentation evidence are complete.

If the working tree still supports clean separation, review these groups:

1. **Harden ingestion and synchronization** - configuration bounds, safe icon
   preservation, canonical snapshot capture, checkpoint lookup, partial-failure
   behavior, CLI diagnostics, and regressions.
2. **Align and complete the local API** - deployed-schema query fixes, nullable
   models, status/matchday/checkpoint routes, generic errors, note transactions, and
   repository/API tests.
3. **Complete the dashboard** - the three public sections, dynamic filters, fixture
   detail, accurate Last updated evidence, optional local notes, accessibility, and
   responsive states. Keep import/synchronization operations in local diagnostic
   tooling rather than the public browser UI.
4. **Finalize security and documentation** - ignore rules, architecture, runbook,
   testing/evaluation, local scheduling, and evidence updates.

If earlier work is already interdependent, one carefully reviewed implementation
commit is safer than artificial history surgery. Do not rewrite history or discard
unrelated user changes merely to match this proposal.

Before every commit:

```bash
git status --short
git diff --check
git diff
git ls-files .env data/raw data/runtime data/backups
```

After staging reviewed files:

```bash
git diff --cached --check
git diff --cached
```

Do not include `.env` variants other than `.env.example`, raw snapshots, runtime
logs/locks, local database backups/data files, tokens, generated caches, virtual
environments, or unrelated work. The exact final command sequence and stop conditions
are in `docs/MANUAL_RUNBOOK.md`.
