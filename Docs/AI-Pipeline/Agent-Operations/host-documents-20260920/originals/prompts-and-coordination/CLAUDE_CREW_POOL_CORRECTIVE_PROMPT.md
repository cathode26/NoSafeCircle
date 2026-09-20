# Correct role-scoped ExecutionCrew session pooling

Work only in `/workspace`, which must be the Windows checkout
`C:\NSC\ClaudeCrewPoolCorrective\NoSafeCircle` on branch
`claude/fix-pooled-execution-crews-v2` at exact starting commit
`7116530b503d7c641efd5f07da2144a5f364b643`.

Read `AGENTS.md` and every guidance file it requires for the code and tests you
touch. Inspect current state before editing. Do not reset, rebase, merge, switch
branches, clean, stash, push, mutate GitHub Issues, touch rehearsal, invoke nested
containers, or alter production `main`. Preserve unrelated state. Create one
focused local commit with the repository automation identity when complete.

The first pooling draft was independently reviewed and must not be merged as-is.
Correct all of these defects without widening scope:

1. At the real `run_crew` pooled-lease invocation boundary, fail closed unless
   every assignment identity matches current execution: task ID, worker run ID,
   role, provider, exact routed model and reasoning effort, exact captured source
   commit, exact source checkout identity, scheduler-proven repository identity,
   the role's expected capability class, and the current
   `CREW_SESSION_PROTOCOL_VERSION`.

2. Do not advertise a provider session as reusable before that role's
   AgentRuntime result, semantic validation, and deterministic changed-path
   validation are complete. Replace unconditional `reusable_role_sessions`
   output with strict durable per-role evidence. Missing, failed, malformed,
   unused, or scope/semantic-rejected role results must never become reusable.

3. Add strict serialization/loading for `DurableAssignmentResult` and bind it to
   the exact lease, crew run, persisted role result/artifact identity, provider
   confirmation, and deterministic validation decision. A process exit code,
   caller assertion, or session ID alone is not evidence. Tampered or missing
   durable evidence must quarantine/refuse reuse.

4. Reuse the existing `Pipeline/AgentRuntime/session_lifecycle.py` policy; do not
   duplicate it. Enforce these already-committed limits only between assignments:

   - worker budget 48 weighted units: fast=1, standard=3, deep=6;
   - therefore exactly 48 fast, 16 standard, or 8 deep completed assignments;
   - architect budget 100 completed admission cycles;
   - idle/wait costs zero;
   - immediate retirement for incompatibility or identity failure;
   - retirement after two consecutive provider/output failures;
   - retirement when known context use is at least 70%;
   - retirement after three comparable latency samples are at least 2x baseline;
   - never interrupt or retire an active assignment.

5. Reject any nested session compatibility protocol that differs from
   `CREW_SESSION_PROTOCOL_VERSION`, both at construction and durable restoration.

6. Replace the literal U+0008 bytes in
   `Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py` with real regex word
   boundaries, and make the banned-process-control test demonstrably fail when a
   forbidden operation is injected into a target method.

Allowed implementation boundary:

- `Pipeline/ExecutionCrew/session_pool.py`
- `Pipeline/ExecutionCrew/run_crew.py`
- `Pipeline/ExecutionCrew/README.md`
- `Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py`
- one narrowly named new ExecutionCrew test file if behavioral integration tests
  cannot be cleanly placed in the existing file.

You may import and use existing AgentRuntime session lifecycle/provider-session
APIs, but do not edit AgentRuntime, TaskReviewAgent, TaskGraph, gameplay, Unity
assets, task contracts, policies, or documentation outside the ExecutionCrew
paths above. If the required contract cannot be implemented within this boundary,
stop and report the exact missing seam instead of widening it.

Required tests must be behavioral and must be demonstrated to fail against the
pre-correction starting implementation, then pass afterward:

- full `run_crew` rejects wrong source commit, checkout, repository, capability
  class, and protocol separately;
- a scope-rejected Implementer confirmation cannot appear reusable and check-in
  quarantines it;
- failed/schema-invalid role output cannot appear reusable;
- a successful role's exact durable artifact can check in;
- missing or tampered role-result evidence cannot check in;
- early contract-audit termination cannot strand or falsely recycle leases for
  roles never invoked;
- repair attempts keep the same exact role session;
- nested protocol `9.9` with top-level protocol `1.0` is rejected;
- worker caps are exactly 48 fast / 16 standard / 8 deep assignments;
- architect retires after exactly 100 completed cycles;
- idle/wait consumes zero;
- retirement never interrupts an active assignment;
- every early-retirement condition is covered;
- the process-control regression is non-vacuous.

Run at least:

```text
python -B Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py
python -B Pipeline/ExecutionCrew/tests/crew_provider_session_smoke_test.py
python -B Pipeline/AgentRuntime/tests/provider_session_smoke_test.py
python -B Pipeline/AgentRuntime/tests/session_lifecycle_smoke_test.py
python -B Pipeline/ExecutionCrew/execution_crew_smoke_test.py
python -B Pipeline/TaskReviewAgent/tests/git_identity_guard_smoke_test.py
python -B -m py_compile <every changed Python file>
git diff --check
```

Before committing, require the exact changed path set to stay inside the allowed
boundary. Stage only those exact paths. Use:

`No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`

Final report: exact commit SHA and parent, changed paths, concrete pre-fix failure
evidence for every new behavior, post-fix test results, and any unresolved
integration constraint. Leave the checkout clean and do not push.
