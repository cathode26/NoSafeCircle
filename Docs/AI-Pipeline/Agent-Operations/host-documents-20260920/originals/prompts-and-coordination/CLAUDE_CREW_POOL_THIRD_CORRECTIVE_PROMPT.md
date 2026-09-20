Continue the SAME persisted Claude session and repair exactly one independently reproduced blocker in your existing checkout.

Checkout: /workspace (host C:\NSC\ClaudeCrewPoolCorrective\NoSafeCircle)
Required branch: claude/fix-pooled-execution-crews-v2
Required starting HEAD: c0dd75cda229fae85d4e08b9d68a3ae8be55af99

Before editing, verify the branch, exact HEAD, and a clean tree. Do not reset, rebase, switch branches, clean, stash, clone, push, or touch any live GitHub Issue/container/rehearsal checkout. Only the same five ExecutionCrew files remain in scope:

- Pipeline/ExecutionCrew/session_pool.py
- Pipeline/ExecutionCrew/run_crew.py
- Pipeline/ExecutionCrew/README.md
- Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py
- Pipeline/ExecutionCrew/tests/pooled_run_crew_smoke_test.py

BLOCKER REPRODUCED BY INDEPENDENT REVIEW

Durable pool restoration accepts a PooledSession with state="idle" while its lifecycle is between_assignments with consecutive_provider_output_failures == 1. is_reusable_at() checks only pool state/time, so ordinary checkout() resumes it, bypassing the required non-advertised probation state and explicit offer_probation_retry gate. The relevant starting code is around session_pool.py:803-882 and idle advertisement around :1039-1043.

Required correction:

1. Make pool-state/lifecycle-state correlation a strict invariant at every trust boundary, especially construction/deserialization. At minimum:
   - idle requires lifecycle between_assignments and failure streak exactly 0;
   - probation requires lifecycle between_assignments and failure streak exactly 1;
   - a one-failure lifecycle must never be represented or advertised as ordinary idle;
   - retired/quarantined/active correlations must remain fail-closed and internally consistent. Do not create a second lifecycle policy; consume AgentRuntime's committed lifecycle state.
   Independently reproduced ACTIVE-state contradictions must also be rejected:
   - lifecycle=None is permitted only for a genuinely fresh mode="start" lease whose prior/session completed count is 0; a warm mode="resume" lease must retain its assigned lifecycle;
   - an active lease's prior_completed_assignment_count must equal the session/lifecycle completed count;
   - assigned lifecycle workload_class must equal the session compatibility workload_class (a standard session must not be assigned as fast, or vice versa).
2. Confirm there is no in-memory mutation path that can produce the same mismatch after construction. If there is, close it at the narrowest authoritative boundary.
3. Add non-vacuous regressions that fail against exact starting commit c0dd75c before the fix and pass after it:
   - forged/restored idle + streak 1 is rejected before ordinary checkout;
   - genuine probation + streak 1 round-trips and is not advertised to ordinary checkout;
   - it can be resumed only by one explicit offer_probation_retry;
   - restored resume lease with completed_count=1 and lifecycle=None fails closed rather than resetting history in _finish;
   - active lease prior count inconsistent with session/lifecycle count fails closed;
   - active lifecycle workload inconsistent with compatibility workload fails closed;
   - analogous contradictory retired/quarantined combinations fail closed if the schema permits them.
4. Preserve all earlier guarantees: exact assignment evidence, provider/model binding, cold-start identity, two-failure retirement, success reset, byte-exact CRLF tests, protocol mismatch zero invocation, backward compatibility when pooling is absent.
5. Run the focused suites and py_compile/diff checks. Use byte-exact writes and hashes in tests.
6. Commit only this focused fix, with the repository automation identity obtained from the repository guard. Do not push.

Return exact commit/parent, changed paths, pre-fix failure evidence, post-fix test results, and any unresolved production integration limitation. Be concise and finish the fix; do not spend turns re-explaining the entire prior stack.
