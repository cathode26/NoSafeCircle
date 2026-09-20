# Handoff: PR #134 CI failures (pipeline code) — 2026-09-17

**What is needed and why:** Release Agent opened a temporary CI-validation PR for the release commit. 4 checks failed; 2 of them are pipeline code/test failures that need the code owner, not the Release Agent.

**Inputs:**
- Commit under test: `46dd7cd09afa6d7de0b8c1369b59ac015795bd7a` (local `main`)
- PR: https://github.com/cathode26/NoSafeCircle/pull/134 (temporary, draft, never merged — do not merge)
- Branch: `release-ci/main-46dd7cd09`

**Failures (from `gh run view --log-failed`, fetched via a Gmail host job):**

1. **Assistant Candidate CI / Exact candidate integrity** — run 35196373787, job 105120474024
   https://github.com/cathode26/NoSafeCircle/actions/runs/35196373787/job/105120474024?pr=134
   Step "Run focused orchestration checks" (`python -m unittest ...`), `FAILED (failures=1, errors=2)`, 90 tests run:
   ```
   ERROR: test_review_alarm_activates_after_thirty_minutes_for_exact_candidate
   AttributeError: type object 'ViewerTests' has no attribute
   'test_review_alarm_activates_after_thirty_minutes_for_exact_candidate'

   ERROR: test_review_alarm_disappears_after_approve_or_deny_state
   AttributeError: type object 'ViewerTests' has no attribute
   'test_review_alarm_disappears_after_approve_or_deny_state'.
   Did you mean: 'test_review_queue_clears_after_approve_or_deny_state'?

   FAIL: test_host_pool_persists_role_routes_and_isolates_runtime_controls
   (Pipeline.TaskReviewAgent.tests.provider_profiles_test.CrewProfileTests...)
   File "...\Pipeline\TaskReviewAgent\tests\provider_profiles_test.py", line 512
       self.assertEqual(len(assignment["leases"]),5)
   AssertionError: 4 != 5
   ```
   Two tests referenced on `ViewerTests` appear renamed/missing (test file likely `test_viewer.py`, suggested match `test_review_queue_clears_after_approve_or_deny_state`), plus an off-by-one lease-count assertion in `provider_profiles_test.py`.

2. **TaskReviewAgent Deterministic Validation / windows-smoke-1** — run 35196373786, job 105120474500
   https://github.com/cathode26/NoSafeCircle/actions/runs/35196373786/job/105120474500?pr=134
   Step "Run provider-session pool state-machine smoke tests" (`python Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py`), exit 1:
   ```
   PASS test_a_returned_implementer_session_is_reused_as_an_implementer
   PASS test_reuse_resumes_rather_than_creating_a_second_provider_session
   PASS test_claude_and_codex_pools_remain_separate
   Traceback (most recent call last):
     File "...\Pipeline\ExecutionCrew\tests\session_pool_smoke_test.py", line 1967, in <module>
       raise SystemExit(main(sys.argv[1:]))
     File "...\session_pool_smoke_test.py", line 1960, in main
       test()
     File "...\session_pool_smoke_test.py", line 402, in test_every_crew_role_keeps_its_own_pool
       require(
     File "...\session_pool_smoke_test.py", line 110, in require
       raise AssertionError(message)
   AssertionError: ('implementer', 'test_author', 'validator')
   ```
   `test_every_crew_role_keeps_its_own_pool` fails a `require()` check asserting pool isolation across the three roles.

**Not included here:** 2 more failing checks (windows-core and windows-smoke-3) are both the same root cause — trailing whitespace in generated Unity asset files (`.meta`/`.controller`/`.asset` under `Assets/.../Generated/...`), which is Unity's own YAML serialization convention (e.g. `userData: ` with a real trailing space is how Unity writes an empty field), not sloppy authoring. Release Agent is asking Vincent whether to add a path exclusion to the whitespace check (there's already a precedent exclusion in `d1b2-core-deterministic.yml` for evidence logs). No action needed from Pipeline Maintainer on those two.

**Constraints:** Never weaken these tests to pass; this is real test/code drift, not a check-config issue.

**Done means:** fixes land on local `main` (Game Agent merges per the main-write protocol). Tell the Release Agent by title when the fix commit is on local main, with its sha — Vincent's "push" already covers re-running CI on the new head; Release Agent will just note the commit changed and why.

**Report to:** Release Agent (session title "Release Agent for No Safe Circle").
