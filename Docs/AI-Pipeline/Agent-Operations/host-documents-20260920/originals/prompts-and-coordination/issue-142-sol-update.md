OpenAI GPT-5.6 Sol — coordination and architect-latency investigation

Current Claude architect evidence is in `C:\NSC\TwoLocalGauntletDemo-t20260909-015701z\all-claude\Checkouts\.task-review-agent\local-rehearsals\claude-local-all-claude-reset-t20260909-025044z\orchestrator\architect\agent_runtime\architect-portfolio-d2e81e140c294b38\{request.json,result.json,provider.log}`.

Measured result: 112.769 s architect duration, 99.491 s inside the provider API, seven turns, and 11,814 output tokens including 3,381 thinking tokens. The request already embedded all seven complete task contracts and reservations in a 43,158-character prompt, but the architect then spent two `Glob` calls and three `Read` calls rediscovering task/source facts before StructuredOutput. The final decisions were valid: implementation for NSC-1001/1003/1004/1005/899, decomposition for NSC-898, and NSC-1007 waiting on NSC-1001.

`Pipeline/TaskReviewAgent/architect_preflight.py` has the same portfolio request behavior at historical `b8d92e27e840759ab8043fb772e455ded7d31356` and current base `9ed1a4305e868d2b692ead7aaa6e6625779276e3`; this is longstanding prompt/tool duplication, not a regression introduced by the current uncommitted patch.

Proposed minimal fix: make mixed-portfolio architect selection use its supplied hash-bound contract/reservation snapshot directly, remove repository search/read capabilities for that request, and change the evidence instruction so paths and observations may cite supplied committed task contracts without a second repository lookup. Keep the complete strict output schema and all deterministic post-validation, pair coverage, dependency, reservation, and admission checks unchanged. This requires the provider no-tool suffix to be role-aware so architect instructions are never appended to supervisor requests.

Targeted tests should prove: (1) portfolio architect requests have empty capabilities and no repository-wide context paths; (2) the prompt identifies supplied contract data as authoritative evidence; (3) Claude argv exposes only StructuredOutput for this role; (4) the complete existing architect batch validator still rejects missing pairs, invented admissions, bad hashes, dependency/reservation conflicts, and malformed evidence; and (5) supervisor no-tool requests receive supervisor-specific guidance rather than architect guidance.

For the user-requested Codex counterpart, two external helpers are prepared and syntax-checked, without execution or source/process changes:

- `C:\NSC\TwoLocalGauntletDemo-t20260909-015701z\Verify-CodexSourceBuild.py`
- `C:\NSC\TwoLocalGauntletDemo-t20260909-015701z\Rebuild-CodexSource.ps1`

They require base `9ed1a4305e868d2b692ead7aaa6e6625779276e3`, branch `integration/gauntlet-convergence-20260908`, exactly 23 changed files, runtime patch SHA-256 `8f852629860d5e18922bf594b061311b7eb1e2f05d314c72fec054ab9a4279d1`, the eight-task LOCAL profile with MaxWorkers 20, exact reuse/archive of run `claude-local-all-codex-restart2-t20260909-025324z`, and viewer/API verification on port 8802.
