# CI #134 round 2: retired contract locality auditor in three CI-run tests

**Problem.** Release CI on PR #134 (after merge 8a2cb497c) still failed windows-smoke-1: `Pipeline/ExecutionCrew/tests/pooled_run_crew_smoke_test.py` crashed with `SessionPoolError: unsupported ExecutionCrew pool role: contract_locality_auditor`.

**Root cause.** Commit `6e718ece2` ("Remove blocking execution audits from task runs") retired the role: out of `CREW_PROFILE_ROLES` (lean = implementer + validator; standard and full = implementer + test_author + validator), out of `session_pool.CREW_SESSION_ROLES`, and out of `role_profiles`. Tests written for the old crew still expected it.

**Fix.** Commit `3f728559a` on `fix/ci-134b` (base `8a2cb497c`), three test files:
- `pooled_run_crew_smoke_test.py`: drops the auditor role map and fake audit output; the auditor-only early-termination test becomes `test_a_lean_profile_skip_leaves_its_lease_unproven_and_unrecycled`, which proves the same pool property through the lean profile's skipped Test Author: the untouched lease is quarantined as "no durable assignment result", a later lease for that role starts a new session instead of resuming it, and the invoked roles check back in idle.
- `quota_failover_smoke_test.py`: drops the auditor from the role loop; the surviving roles keep their scope and handoff coverage.
- `production_end_to_end_smoke_test.py`: drops it from `required_roles`; the assertion that a standard crew must NOT include the auditor stays.
No assertion was loosened; the fixed counts became the current role counts.

**Tests (TEMP under C:\nscrev\tmp\ci-134b).** At head: pooled_run_crew PASS, quota_failover PASS, production_end_to_end PASS, session_pool PASS, provider_profiles 41/41, compileall clean, `git diff --check` clean, blobs LF.
**Failing before:** the `8a2cb497c` copy of pooled_run_crew against this code raises the unsupported-role error.

**Review.** Host Claude Opus pipeline-reviewer (Gmail account): APPROVE. It judged the rewritten test real rather than circular, noted it overlaps `test_lean_profile_invokes_only_required_pooled_roles`, and confirmed the failing-before.

**Still stale, not run by CI (test-debt pass):** `execution_crew_smoke_test.py` (fails at head), `crew_provider_session_smoke_test.py:34`, `AgentRuntime/tests/provider_session_smoke_test.py:561`, `prompt_context_reduction_smoke_test.py`, `GauntletView/tests/local_crew_view_test.py`, the `session_pool.py:11` docstring, `ExecutionCrew/README.md:139`, and the dead `if "contract_locality_auditor" in required_roles:` branch at `run_crew.py:2612`, whose prompt import 6e718ece2 removed, so it would raise NameError if reached.
