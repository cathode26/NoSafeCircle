Continue the SAME persisted Claude session. Apply one final narrow correction found by independent review.

Checkout /workspace (host C:\NSC\ClaudeCrewPoolCorrective\NoSafeCircle), branch claude/fix-pooled-execution-crews-v2, required clean starting HEAD d5f8ba762ec39659b4f55fbe004b73bf0792c79d. Verify these before editing. Do not reset/rebase/switch/clean/stash/clone/push or touch live resources.

Allowed files: Pipeline/ExecutionCrew/session_pool.py, Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py, and Pipeline/ExecutionCrew/README.md only.

DEFECT

After an explicit probation retry's second counted provider/output failure, AgentRuntime finish_assignment correctly returns lifecycle.phase="retired", but SessionPool.check_in sends every proven non-reusable result through _settle_quarantined, which hardcodes PooledSession.state="quarantined". As a result sessions_for("retired") omits conversations that the lifecycle retired. A current regression even expects quarantined while describing it as retired.

REQUIRED FIX

- When authoritative lifecycle output is phase="retired", settle the public pool record as state="retired" with no quarantine/probation reason and preserve the retired lifecycle.
- Keep state="quarantined" for untrusted/unproven/non-lifecycle evidence that is not authoritatively retired.
- Apply the same normalization to every lifecycle-driven retirement cause already implemented (second consecutive provider/output failure, identity/compatibility retirement, context threshold, comparable latency) without duplicating the lifecycle policy.
- Add non-vacuous regressions that fail at d5f8ba7 and pass after: second counted failure appears in sessions_for("retired") and not quarantined; an immediate lifecycle retirement cause also surfaces retired; ordinary unproven evidence remains quarantined/non-reusable.
- Preserve all prior fixes and exact durable-state invariants.
- Run session_pool, pooled_run_crew, AgentRuntime lifecycle/provider, ExecutionCrew, identity guard, py_compile, and diff checks.
- Commit this focused fix with repository-guarded automation identity. Do not push.

Return exact commit/parent, changed paths, pre-fix failure evidence, post-fix results, and any uncertainty. Be concise and finish the correction.
