# Claude task: exact-commit admission snapshot performance fix

You are working in the isolated full clone mounted at `/workspace`.

## Identity and starting authority

- Host checkout: `C:\NSC\ClaudeAdmissionSnapshot-20260905\NoSafeCircle`
- Container checkout: `/workspace`
- Required branch: `claude/source-admission-snapshot-perf`
- Required starting HEAD: `2bc1a29636f33edcaa78775c2cfcfff189156447`
- Base is the locally composed orchestration + scale line. It is not published.
- Commit identity must be `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`.

Before editing, read `AGENTS.md`, `Docs/Engineering/UNITY_TESTING_POLICY.md`, `Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md`, and the relevant TaskReviewAgent runbook/README. Verify the exact branch, HEAD, and clean tree. If any precondition differs, stop and report it.

Do not clone, fetch, pull, push, open or modify GitHub, switch branches, merge, rebase, reset, clean, restore, stash, or force anything. Do not run Docker from inside Docker. Do not touch `C:\NSC\Rehearsal`, any Issue, any live checkout/claim/container, Unity content, production main, or NSC-042. Do not use WebSearch or WebFetch. Work only in `/workspace`.

## Measured defect

The 1,000-task component test recorded 6,605 Git subprocesses, including 6,306 `rev-parse` calls. Exactly 6,163 came from `PollingOrchestrator._load_candidate` checking HEAD per candidate. `_mixed_portfolio` runs once for each architect batch and again over the whole fresh portfolio before each individual launch even though that pass immediately selects one task.

The larger live blocker is hidden by the test's in-memory task loader and fake Stage 2: production `load_committed_task` runs one `git show` per task, while `plan_dispatch` evaluates every committed task ID. At 1,000 tasks and 1,262 observed Stage-2 calls, the current live path can imply at least 1,262,000 task-contract `git show` processes before other Git work.

Repository-wide decomposition policy/task auditing is also rebuilt on each `_mixed_portfolio` call. The committed-path probe is currently cached only per architect batch.

## Required end state

Implement a bounded, read-only immutable `SourceCommitAdmissionSnapshot` (the exact name may vary only if the repository already has a better established abstraction) shared by `dispatch_plan.py` and `polling_orchestrator.py` where appropriate.

The snapshot must be keyed strictly by the exact verified source commit and may contain only immutable repository facts for that commit:

- bulk committed task bytes or parsed contracts plus deterministic task-contract hashes;
- TaskGraph states needed by admission;
- decomposition policy and its repository-wide audit result;
- a lazy committed-path inventory.

Use a bounded cache or explicit discard rule so obsolete commits cannot accumulate indefinitely.

Never cache or reuse mutable authority across launches: GitHub Issues/comments/events/labels, claims, leases, reservations, active checkout observations, source-refresh outcomes, scheduler health, or worker/provider state. A launched child can mutate Issue authority.

For every launch, preserve the existing fresh source refresh and mutable Issue/claim/reservation/active-checkout/Stage-2 checks. Revalidate only the architect-admitted task/work-type pair against the fresh plan instead of rebuilding the entire portfolio. Preserve plan-source equality and selected task-contract hash validation. Perform one final HEAD observation after constructing or using the immutable snapshot. If HEAD moves or the selected contract hash differs, discard the remaining admissions before any provider or worker starts. Fail closed; do not synthesize authority.

Keep existing public APIs compatible unless a small explicit optional snapshot parameter is required. Do not weaken duplicate-authority, retired-Issue, decomposition-resume, contract-hash, provider, or reservation protections already on this branch.

## Mandatory red-before / green-after regressions

Create deterministic tests that fail against the unmodified starting semantics and pass after the fix. Prove the failure before implementation or by running the new tests against an exact base-file/module fixture; retain concise evidence in your final report.

1. `test_multi_candidate_portfolio_uses_one_head_observation_and_source_move_blocks_before_architect`
2. `test_prelaunch_revalidation_loads_only_selected_pair_but_refreshes_mutable_authority`
3. `test_source_commit_snapshot_reuses_bulk_authority_and_invalidates_on_head_change`
4. `test_cached_task_contract_hash_mismatch_blocks_before_spawn`
5. `test_committed_path_snapshot_is_reused_only_for_identical_commit`
6. A quick 100-candidate counter test proving command/load complexity is bounded and not candidate-times-launch.

Test names may be adjusted to repository naming conventions, but each behavior must be explicit and non-vacuous. Confirm each new regression can actually fail before its fix; do not merely assert source text or mock away the behavior being proven.

After focused tests pass, run the relevant fast broad suites: polling orchestrator, dispatch plan, committed task loader, decomposition authorization/policy, resource reservations, completed-Issue guard, synthetic validation/approval, thousand-task generation/capacity tests, identity guard, `taskcontrol validate`, `py_compile`, and `git diff --check`. Run other directly affected suites discovered through imports/callers.

Only after all focused and broad fast gates pass, run the long thousand scheduler test once. If the production-compatible counter surface is genuinely exercised, tighten its bounds to approximately `rev-parse <= 1350` and total Git subprocesses `<= 1700`; use no elapsed-time assertion. If the test still injects fakes that bypass production task loading, add a separate bounded production-path counter test instead of claiming the live cost is fixed.

## Commit and report

Stage only exact changed paths. Verify the staged set and automation identity. Commit the complete focused change locally; do not push.

Report:

- exact starting and ending HEADs, branch, and checkout;
- changed paths and why each changed;
- the immutable/mutable authority boundary;
- red-before evidence for every new behavior-changing regression;
- focused and broad test results, including subprocess/load counters and long-test elapsed time if run;
- any remaining production path that still scales as tasks x launches or performs repeated fetches;
- uncertainties, deliberately excluded work, and clean-tree status.

Do not claim the live 10/80/1,000 gauntlets ran. This task fixes and verifies the scheduler implementation only.
