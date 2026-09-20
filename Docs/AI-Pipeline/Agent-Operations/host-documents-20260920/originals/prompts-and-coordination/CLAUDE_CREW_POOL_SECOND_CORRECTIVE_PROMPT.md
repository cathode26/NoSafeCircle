# Correct remaining pooled ExecutionCrew identity and lifecycle defects

Work only in `/workspace`, which must be the Windows checkout
`C:\NSC\ClaudeCrewPoolCorrective\NoSafeCircle` on branch
`claude/fix-pooled-execution-crews-v2` at exact starting commit
`ceb590b8086a712dacf1555ff1c458224d890bf4`.

Read `AGENTS.md` and every guidance file it requires for the code/tests you
touch. Inspect the checkout and verify the exact starting HEAD before editing.
Do not reset, rebase, merge, switch branches, clean, stash, push, mutate GitHub
Issues, touch rehearsal, invoke nested containers, or alter production `main`.
Preserve unrelated state. Create one focused local commit using
`No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`.

The two-commit pooling feature (`7116530b... + ceb590b8...`) remains unapproved.
An independent Windows/adversarial review found these blockers. Correct all of
them within the existing ExecutionCrew path boundary:

1. Bind the actual invoked provider and model at the real pooled `run_crew`
   boundary. For every pooled role, the resolved configuration provider/model
   and returned `AgentResult.provider`/`AgentResult.model` must exactly match the
   lease's provider and routed model, even when a `provider_factory` is injected.
   The current fake returns provider `fake` while evidence claims `claude-code`;
   fix the fake/config identity rather than weakening the production check.
   Add full-run wrong-provider and wrong-model regressions and prove no session
   is advertised/checkable as reusable.

2. Make durable role evidence inseparable from its exact assignment. The role
   artifact itself must use a strict schema and bind at least: crew run ID,
   lease ID, assignment/record ID, role, task ID, worker ID, source commit,
   source checkout identity, scheduler-proven repository identity, capability
   class, protocol version, provider, routed model/reasoning, exact provider
   confirmation, role outcome, semantic decision, changed-path decision, and
   artifact identity. `DurableAssignmentResult.evidence_reason` must compare
   every field against the trusted lease/result and refuse extras/missing or
   mismatches. Copying or borrowing a successful same-role artifact from a
   different run/lease/task/source must fail closed.

3. Make the committed two-consecutive-provider/output-failure lifecycle
   reachable through the real pool. A first provider/output failure must update
   the exact `SessionLifecycleState` failure streak without advertising the
   failed role in `reusable_role_sessions` and without treating the failed
   assignment as validated evidence. Keep it in an explicit non-advertised
   probation/retry state that only the pool can deliberately offer for a
   controlled compatible retry. A second consecutive provider/output failure
   retires it; an intervening successful, fully evidenced assignment resets the
   streak. Never return a failed role as a successful reusable result, and never
   interrupt an active assignment. Replace the impossible hand-seeded test with
   a behavioral checkout/fail/controlled-retry/fail and fail/retry/succeed test.

4. A mismatched or malformed cold-start provider confirmation is untrusted. It
   must never replace the lease/session's trusted identity in quarantine or
   lifecycle state. Preserve the lease identity for pre-bound sessions; for a
   provider-assigned cold session with no trusted ID, retain no adopted identity
   unless exact confirmation succeeds. Add exact regression coverage.

5. Fix the Windows CRLF-vacuous regression in
   `pooled_run_crew_smoke_test.py`: write exact bytes (or explicitly disable
   newline translation), hash the actual on-disk bytes, assert that on-disk hash
   equals the constructed durable claim, then prove the semantic contradiction
   reaches the intended `disagrees with the durable claim` path on Windows and
   Linux.

6. Exercise nested protocol mismatch through full `run_crew`, not only the
   helper. Use an adversarial invalid-object fixture if normal construction
   correctly refuses it, and prove zero provider invocations.

Allowed paths remain exactly:

- `Pipeline/ExecutionCrew/session_pool.py`
- `Pipeline/ExecutionCrew/run_crew.py`
- `Pipeline/ExecutionCrew/README.md`
- `Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py`
- `Pipeline/ExecutionCrew/tests/pooled_run_crew_smoke_test.py`

Do not edit AgentRuntime or TaskReviewAgent. Do not add another lifecycle policy.
If the exact guarantees cannot be implemented inside this boundary, stop and
report the missing seam instead of approximating it.

Demonstrate every new regression fails against starting commit `ceb590b8...`
and passes afterward. Run at least:

```text
python -B Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py
python -B Pipeline/ExecutionCrew/tests/pooled_run_crew_smoke_test.py
python -B Pipeline/ExecutionCrew/tests/crew_provider_session_smoke_test.py
python -B Pipeline/AgentRuntime/tests/provider_session_smoke_test.py
python -B Pipeline/AgentRuntime/tests/session_lifecycle_smoke_test.py
python -B Pipeline/ExecutionCrew/tests/execution_crew_smoke_test.py
python -B Pipeline/TaskReviewAgent/tests/git_identity_guard_smoke_test.py
python -B -m py_compile <every changed Python file>
git diff --check
```

Before committing, require the exact changed path set to stay within the allowed
boundary and stage only those exact paths. Final report: exact commit and parent,
changed paths, per-defect pre-fix failure evidence, post-fix results, Windows-EOL
test construction, and unresolved production integration constraints. Leave the
checkout clean and do not push.
