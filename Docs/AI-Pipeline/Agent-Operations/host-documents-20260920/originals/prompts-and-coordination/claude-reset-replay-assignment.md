## Claude assignment: add a safe AssistantControl Gauntlet replay reset

Please implement this in your existing workspace and report the commit, changed files, and focused test results here.

The operator expects Reset to make a disposable AssistantControl task runnable again without hiccups. The legacy TaskReviewAgent reset tools do not understand AssistantControl state.

Add a small AssistantControl command, preferably `reset-replay`, with these boundaries:

- Dry-run by default; require `--apply` for mutation.
- Accept the selected task IDs and the AssistantControl checkout root.
- Read the exact original source branch and pre-run source commit from the authenticated controller/preflight record. Do not accept a guessed base.
- Operate only on a clean local `gauntlet-replay/*` branch with no Git remote. Refuse production/main, a dirty source, branch mismatch, a non-ancestor binding, or any live controller/worker.
- Restore the disposable source branch to the exact recorded pre-run commit.
- Preserve old evidence by moving the old AssistantControl root to a uniquely named sibling archive. Do not recursively delete it.
- Recreate an empty owned checkout root and persist an exact fresh scope containing only the selected task IDs, so viewer/graph-plan shows only those tasks.
- Preserve task contracts in Source. Clear stale controller ownership, decomposition failures, reservations, worker records, task checkouts, candidate receipts, and projections by virtue of the new empty root.
- Never contact GitHub, push, alter a remote, or touch the real project.
- Make interrupted archive/reset/recreate steps recoverable and idempotent.
- Add focused real-Git tests for: successful failed-decomposition reset; refusal with live controller; refusal on dirty/wrong/remote branch; evidence archive retained; repeated command recovers; and only the selected task appears in the fresh scope.

Current reproduction facts:
- source branch had a controller preflight at the clean base, then locally integrated several disposable Gauntlet commits;
- one decomposition task has a retained failed record;
- the old controller has exited;
- desired fresh scope is only NSC-1124.

Keep all repository references relative in this Issue. Do not apply the command to Vincent's machine.
