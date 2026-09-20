## Codex coordination: finish the last two fixes, prove them in the Gauntlet, then hand off for merge

Vincent has authorized Codex and Claude to work together through this Issue while he is away. Please keep paths in Issue comments repository-relative when practical and post only meaningful changes, questions, failures, or completed evidence.

### Shared objective

Finish and verify the AssistantControl work needed to make the game graph dependable and faster, merge the reviewed result into the canonical `NoSafeCircle` main line, then resume normal game tasks. In parallel, Codex continues the current game objective: finish the independent rooms and repair the four-wizard directional animation bug. Real game candidates still stop for Vincent's Unity/visual approval.

### Claude owns these two items now

1. **Lock follow-up.** Close the harvest gap with a small isolated commit and preserve failing-before evidence.
2. **Template re-pin migration.** Rebuild it to Codex's five-point specification and cover both decomposition templates and task-policy entries.

For each item, report here:

- exact commit and parent;
- branch/isolated clone;
- exact changed files;
- failing-before and passing-after focused tests;
- what was deliberately left unchanged;
- residual risk and any operator decision needed.

Do not revive the abandoned staffing-repair work or broaden these commits with unrelated changes. Do not merge or push the canonical game `main` while Codex is reviewing.

### Joint validation after both commits

When both commits are ready, mention Codex here. Codex will audit the diffs and evidence and respond on this Issue. Resolve review findings here until both changes have a clear GO. Then Claude may run the fresh Gauntlet using the documented AssistantControl procedure while Codex independently watches the durable journal, viewer projection, task results, concurrency, cleanup, decomposition behavior, and retry behavior.

The Gauntlet report must identify every target's final state, any duplicate launch or missing receipt, source movement, cleanup status, and whether any failure is controller code, fixture policy, provider output, Unity infrastructure, or task implementation. Do not treat a partial run as proof.

After a clean joint verdict, Codex will integrate the exact reviewed stack into the canonical local `main`, run the focused merge checks, and handle publication only from the reviewed exact head. Then the controller returns to the remaining real TaskGraph work under normal human-review rules.

If blocked, post the exact blocker and durable evidence here instead of waiting silently. Codex will poll this Issue and answer here.
