Continue the SAME persisted Claude session for one exact constructor-invariant correction.

Required checkout /workspace, branch claude/fix-pooled-execution-crews-v2, clean starting HEAD 303c8fb6485d57ac1daabbf83dbd709bae23a694. Verify first. Do not reset/rebase/switch/clean/stash/clone/push or touch live resources.

Allowed files only: Pipeline/ExecutionCrew/session_pool.py, Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py, Pipeline/ExecutionCrew/README.md.

REPRODUCED DEFECT

PooledSession.__post_init__ enforces state="retired" => lifecycle.phase="retired", but not the inverse. SessionPool.from_dict still accepts a payload with state="quarantined", a quarantine_reason, and lifecycle.phase="retired". That record is omitted by sessions_for("retired"), so the public pool state and authoritative lifecycle again disagree.

Fix the single authoritative constructor invariant so lifecycle.phase == "retired" iff PooledSession.state == "retired". Preserve legitimate quarantined records with lifecycle None or non-retired lifecycle as currently allowed. Add a non-vacuous from_dict regression that starts with a genuine retired record, mutates only its public state/reason to quarantined, proves 303c8fb accepts it and omits it from retired reporting, and proves the corrected tree rejects it. Confirm internal settlement paths still construct valid states.

Run focused session_pool and pooled_run_crew tests, AgentRuntime lifecycle tests, py_compile, and diff check. Commit only the focused fix with repository-guarded automation identity; do not push. Return exact commit/parent and concise evidence. Do not broaden scope or repeat the full prior analysis.
