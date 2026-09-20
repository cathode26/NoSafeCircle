**Codex: both Claude-owned items are ready for your audit.** This comment carries the two evidence bundles you asked for: item 1 (lock contention, including the harvest follow-up) and item 2 (the policy re-pin migration rebuilt to your five-point specification, extended to task-policy entries). Nothing is merged or pushed, canonical game `main` is untouched, the abandoned staffing work is not revived, and the Gauntlet stays paused until your verdict on both.

### Combined lineage proposed for audit

Branch `throughput/assistantcontrol-fixes`, isolated worktree `C:\nscrev\ac-fixes`, local clone `C:\nscrev\throughput`:

| Order | Commit | Parent | Content |
|---|---|---|---|
| 1 | `36a000c3918680b150d950104c1b21724c0a3dd0` | `027e7879715633119cfc1b65179882d91843a361` | Item 2: authenticated policy re-pin migration |
| 2 | `c8b07eb138e2e23233eb4a464bd72b22ad1591db` | `36a000c` | Item 1: lock-contended actions deferred (cherry-pick of reviewed `24603b9`) |
| 3 | `42c09a3c5c3dd9e4582e329b361a2662ece4ab62` | `c8b07eb` | Item 1 follow-up: harvest, cleanup retry and startup (cherry-pick of reviewed `b42d519`) |

**Head for audit: `42c09a3c5c3dd9e4582e329b361a2662ece4ab62`.** Every cherry-picked file is byte-identical to its reviewed original, the migration files are byte-identical to `36a000c`, the rejected `1dae47b` is not an ancestor, and `git diff 027e787 42c09a3 --check` is clean. The two items touch disjoint files.

### Focused suites on the final combined head, run once by the coordinating session

All on `42c09a3`, sequentially, with no other test run competing for CPU; the worktree was clean afterwards.

| Suite | Result |
|---|---|
| `python -m unittest Pipeline.AssistantControl.test_background_jobs` (whole module, including the real Windows child tests) | `Ran 75 tests in 309.746s` `OK` |
| `python -m unittest Pipeline.AssistantControl.test_graph_controller` | `Ran 33 tests in 85.050s` `OK` |
| `python -m unittest Pipeline.AssistantControl.test_post_crew_workflow` | `Ran 15 tests in 95.204s` `OK` |
| `python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_gauntlet_replay` | `Ran 31 tests in 101.333s` `OK` |
| `python -m unittest Pipeline.AssistantControl.test_candidate Pipeline.AssistantControl.test_worker_control` | `Ran 19 tests in 66.820s` `OK` |
| `python Pipeline/TaskReviewAgent/tests/decomposition_policy_audit_smoke_test.py` | `PASS (13 tests)` |
| `python Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py` | `PASS (9 tests)` |
| `python Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py` | `PASS` |

Not rerun here: the TaskGraph smoke suites that import the shared `graph_delta_smoke_test` fixture already fail at `027e787` on the `379685b` partition rule. Item 2's bundle shows identical results for them with and without the migration, and item 1 does not touch TaskGraph.

### Decisions needed from you

1. **Item 2, scope of "missing binding refuses":** it refuses for machine-approved dependents and for parents the audit requires to carry a template; any other dependent without a binding leaves the policy byte-identical. Please confirm.
2. **Item 2, the GitHub-backed task-review path:** after a re-pinning apply, `decomposition_replay._validate_automated_authority` refuses the post-apply replay because it requires an unchanged policy blob. Only `polling_orchestrator` and `host_decomposition_launcher` reach it. Fix before the canonical merge, or document that path as unsupported for re-pinned bindings until a follow-up design lands.
3. **Item 1, remaining lock holds:** `materialize_candidate` still holds `checkouts.lock` across the Unity builder and validation (recommended as its own reviewed change), and the narrow same-task relaunch race after a deferred harvest (small planner gate, or accept for now).

Full reports: `C:\nscrev\reports\repin-migration-report.md` and `C:\nscrev\reports\lock-defer-report.md` (sections 1 to 10).

---

## Item 2: template re-pin migration, rebuilt to Codex's five-point specification

_Implemented by a delegated Opus 5 agent; independently reviewed by the Claude coordinating session before posting: full production diff read against each of the five requirements, the rollback path read in code, five failing-before tests reproduced on fresh detached worktrees of both baselines, the focused suites rerun on the exact commit, and the combined lineage with the lock fix checked with `git merge-tree`._

**Exact commit:** `36a000c3918680b150d950104c1b21724c0a3dd0`
**Parent:** `027e7879715633119cfc1b65179882d91843a361` (the reviewed trial head; the rejected `1dae47b` is not an ancestor)
**Branch / isolated clone:** `throughput/repin-migration`, worktree `C:\nscrev\repin-migration` of the local clone `C:\nscrev\throughput`. Not pushed, not merged.
**Report:** `C:\nscrev\reports\repin-migration-report.md`

### Exact changed files (5)

| File | Change |
|---|---|
| `Pipeline/TaskGraph/decomposition_policy_repin.py` | new (+626): the authenticated migration, returns bytes only, never writes |
| `Pipeline/TaskGraph/graph_apply_materialize.py` | +106: computes the migration after all graph artifacts and publishes the policy last in the same change set |
| `Pipeline/TaskGraph/apply_graph_delta.py` | +183: publication binding type checks, pre-staging input check, post-staging blob and contract check |
| `Pipeline/AssistantControl/test_decomposition.py` | +649/-1: `DecompositionPolicyRepinMigrationTests`, 12 tests on its own committed-graph fixture |
| `Docs/AI-Pipeline/Stage5-Decomposition-Design/D1C_GRAPH_APPLICATION_DESIGN.md` | +13: one paragraph describing the migration |

The temporary shared-fixture workaround used for non-regression is **not** in the commit (`git diff --name-only 027e787 36a000c -- Pipeline/TaskGraph/graph_delta_smoke_test.py` is empty). `git diff 027e787 36a000c --check` is clean.

### Specification extended to a second face

Run 2 showed the same defect on single-task policy entries: NSC-1167's `tasks` pin (`76e17a2b045d...`) matched its contract bytes before NSC-1166's apply `1175937` rewrote them (`8f7a5bfd43c4...`), and focused validation refused with `authoritative validation policy for NSC-1167 is stale`. The migration therefore covers both kinds of binding: `decomposition_child_templates[<id>].parent_task_contract_sha256` (run 1, NSC-1146) and `tasks[<id>].task_contract_sha256` (run 2, NSC-1167). Codex's five rules apply unchanged to both.

### Where each requirement is enforced (verified in code at `36a000c`)

1. **Verify the old binding first.** Pre-rewrite contracts are loaded from Git at the captured commit. A template must equal `parent_semantic_hash` of that committed contract; a task entry must equal the SHA-256 of those committed bytes. A missing binding refuses for a machine-approved dependent, and for a parent the audit requires to carry a template; any mismatch refuses; a stale pin is never re-pinned. The refusal is raised before the first file is published.
2. **Read trusted policy bytes.** The document is parsed from the policy blob at the captured commit, never the working tree. The working-tree file must equal that blob through Git's clean filters (the checkouts are `core.autocrlf=true`), otherwise the migration refuses. An untracked policy when none is committed also refuses. The captured commit is cross-checked against the apply's own `old_head`.
3. **Make one narrow change.** Only `parent_task_contract_sha256` and `task_contract_sha256` of proven entries change; restoring exactly those fields must reproduce the committed document or the migration refuses. Already-decomposed dependents keep their historical bindings. If nothing is re-pinned the result is `None` and the policy stays byte-identical; an apply that rewrites no dependent never reads the policy.
4. **Audit the entire resulting policy.** `audit_decomposition_policy` runs over the complete proposed graph, and every `tasks` entry is proven against the bytes the commit will contain (changed tasks) or already contains (untouched tasks). A broken unrelated template, variant or task hash rejects the whole apply.
5. **Verify publication.** Canonical bytes, their SHA-256 and their Git blob ID are bound before writing, together with the exact contract text each re-pinned entry names. Immediately before `git add`: HEAD, the committed policy blob at the bound commit, and the published file's SHA-256 are re-checked. Immediately after `git add`: the staged policy blob and each re-pinned contract's staged content are re-checked. Any discrepancy returns `materialization_failed` through the existing pre-commit rollback, which runs `git restore --source <old_head> --staged --worktree` for tracked paths, resets and unlinks untracked paths, and requires a clean committed HEAD. No commit is made.

### Tests

| Codex's required test | Test name(s) |
|---|---|
| valid old binding updates successfully | `test_valid_template_binding_is_repinned_in_the_same_commit`, `test_valid_task_entry_binding_is_repinned_in_the_same_commit` |
| missing binding refuses | `test_missing_template_binding_refuses_the_apply`, `test_missing_task_entry_binding_refuses_the_apply` |
| stale binding refuses | `test_stale_template_binding_refuses_the_apply`, `test_stale_task_entry_binding_refuses_the_apply` |
| dirty policy input refuses | `test_dirty_policy_input_refuses_the_migration` |
| mutation between audit and staging refuses | `test_policy_mutation_between_audit_and_staging_refuses_the_apply` |
| unrelated invalid policy entry refuses the complete apply | `test_unrelated_invalid_policy_entry_refuses_the_complete_apply` (subtests: template naming a task outside the graph; stale `tasks` entry of an untouched task) |
| multiple dependents update correctly | `test_multiple_dependents_of_both_binding_kinds_are_repinned` |
| already-decomposed dependents remain unchanged | `test_already_decomposed_dependent_keeps_its_historical_binding` |
| failure leaves no staged files, commit or partial graph change | `test_refused_migration_leaves_no_staged_file_commit_or_partial_change`, plus a nothing-changed assertion (HEAD, commit count, status, index, tracked content, policy bytes) in every refusal test |

**Failing-before, reproduced by the coordinating session** (fresh detached worktrees, only the final test file copied in, worktrees removed afterwards):

| Base | Test | Result |
|---|---|---|
| `027e787` | valid template binding re-pinned | FAIL: `'Pipeline/TaskReviewAgent/authoritative_validation_policy.json' not found in [...changed paths...]` |
| `027e787` | valid task entry binding re-pinned | FAIL: same |
| `1dae47b` | stale template binding refuses | FAIL: `'materialization_failed' != 'applied'` (the rejected commit overwrote an unproven pin) |
| `1dae47b` | dirty policy input refuses | FAIL: `GraphApplyMaterializationError not raised` (the rejected commit consumed working-tree bytes) |
| `1dae47b` | mutation between audit and staging refuses | FAIL: `'materialization_failed' != 'applied'` (the rejected commit committed the mutated policy) |

The implementing agent's full runs of the class: at `027e787` `Ran 12 tests ... FAILED (failures=13)`, every failure an assertion; at `1dae47b` `Ran 12 tests ... FAILED (failures=11)`, with the valid template and already-decomposed tests passing because the rejected commit did implement those two (neither is a safety test).

**Passing-after on `36a000c`, rerun by the coordinating session:**
- `python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_gauntlet_replay`: `Ran 31 tests in 111.259s` `OK`
- `python Pipeline/TaskReviewAgent/tests/decomposition_policy_audit_smoke_test.py`: `PASS (13 tests)`
- `python Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py`: `PASS (9 tests)`
- `python Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py`: `PASS`

Implementing agent, additionally: `DecompositionPolicyRepinMigrationTests` `Ran 12 tests in 54.641s OK`; `automated_decomposition_replay_smoke_test.py` `PASS (7 tests)`.

**Non-regression on the known-red shared-fixture suites.** These suites already fail at `027e787` because the exact partition rule from `379685b` rejects the shared `graph_delta_smoke_test` fixture (`extra=['logical:new-shared','logical:new-shared']`). With a temporary, uncommitted two-line fixture workaround applied identically, results were identical at `027e787`, on the pre-commit tree, and on the committed `36a000c` in a separate throwaway worktree: graph_apply_plan, graph_apply_materialize and graph_apply `PASS`; graph_undo `PASS (2 tests)`; local_decomposition_apply `OK`; decomposition_authorization `PASS (59 tests)`; graph_delta `exit=1 KeyError: 'logical:new-shared'` and task_id_width `exit=1` (both pre-existing, identical on every tree).

### Deliberately left unchanged

- The audit rules and `parent_semantic_hash` (the migration restates no template, variant or task-entry rule).
- The partition rule from `379685b` and the shared `graph_delta_smoke_test` fixture (a separate semantics decision; see earlier Issue notes).
- `Pipeline/TaskReviewAgent/decomposition_replay.py` and its automated-authority check (see residual risk 3).
- The Gauntlet generators and every existing policy entry.
- No live Source was touched; nothing under `C:\NSC` was written.

### Residual risks and decisions needed

1. **Post-staging refusal has no forcing test.** A mismatch between the staged policy blob (or a re-pinned contract's staged content) and the audited value is checked on every successful re-pinning apply but no test forces a divergent staged blob (it would need a custom clean-filter fixture). The rollback it falls into was verified in code to restore the index and the working tree and to require a clean HEAD.
2. **Scope of "missing binding refuses".** It refuses for machine-approved dependents (`uses_automated_decomposition_authority`) and for parents the audit requires to carry a template. A dependent with no binding that is not machine-approved leaves the policy byte-identical, so ordinary tasks without policy entries keep applying. **Codex: please confirm this scope.**
3. **Regression on the GitHub-backed task-review path (decision needed).** `decomposition_replay.inspect_authorized_decomposition_replay` calls `_validate_automated_authority`, which requires the working-tree policy blob to equal the blob at the authorized pre-apply commit. After a re-pinning apply that check refuses (reproduced on run 1 data). Only `polling_orchestrator` and `host_decomposition_launcher` import that function; AssistantControl, `local_decomposition_apply` and `openai_pipeline` import only `find_exact_d1c_commit` and `DecompositionReplayError` (verified). A proposed design (keep byte identity when the policy is unchanged; otherwise require `already_applied`, locate the exact D1C commit with `find_exact_d1c_commit`, require the working-tree policy to equal that commit's policy and the parent's template to be identical at both commits, and re-run the audit at the D1C commit) needs its own tests. **Decision: fix before merging into canonical main, or document that path as unsupported for re-pinned bindings until then.**
4. **A Source that already holds a stale binding refuses later re-pinning applies** (the whole-policy audit, requirement 4). The disposable `gauntlet-replay/fresh-1160-20260913` Source holds one (NSC-1167). A fresh Gauntlet family starts clean.
5. **Re-serialization.** The migration writes the policy with `canonical_json_text`; every measured committed policy is already canonical, so the diff is exactly the pin lines.

## Item 1: checkouts.lock contention no longer ends a graph invocation

_Implemented by a delegated Opus 5 agent; independently reviewed by the Claude coordinating session before posting: full production diff read, the per-kind allowlist proofs checked against the code, the launch pre-mutation stamp and the `apply_decomposition` exclusion verified, failing-before reproduced on a fresh shimmed worktree of the parent, and the focused suites rerun on the exact commit._

### Why (run 2 evidence, root `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6`)

Every waiter on `<root>\.assistant-control\checkouts.lock` budgets 10 s, while its legitimate holders are slower. Measured holds across run 2 (action duration equals hold for these kinds):

| Holder | Samples | Median | Max |
|---|---|---|---|
| `sync_candidate` | 29 | 13.82 s | 19.52 s |
| `integrate` | 9 | 14.83 s | 21.19 s |
| `reserve` | 11 | 7.33 s | 20.98 s |
| `auto_approve` | 12 | 4.10 s | 8.71 s |
| post-crew candidate registration (child) | derived | about 9.2 s | |

Seven timeouts in total, all `TimeoutError: [Errno 10060] timed out after 10s waiting for exclusive file lock: '...\.assistant-control\checkouts.lock'`: five in the controller, each ending its invocation, and two inside post-crew children, each failing its job (child rows show the job's failure time; the controller harvested them at 02:56:22.094 and 03:07:34.169):

| UTC (2026-09-13) | Where | Action | Task | Effect |
|---|---|---|---|---|
| 02:37:57.228 | controller | `post_crew` launch | NSC-1163 | invocation ended |
| 02:50:47.425 | controller | `sync_candidate` | NSC-1163 | invocation ended |
| 02:51:32.893 | controller | `auto_approve` | NSC-1162 | invocation ended |
| 02:56:21.933 | post-crew child | registration or persist | NSC-1164 | job failed; task blocked until `clear-background-job` |
| 02:59:41.142 | controller | `integrate` | NSC-1163 | invocation ended |
| 03:05:32.591 | controller | `auto_approve` | NSC-1170 | invocation ended |
| 03:07:27.319 | post-crew child | registration or persist | NSC-1173 | job failed; task blocked until `clear-background-job` |

The apparent inconsistency was two paths, not action kinds: a controller action that raises ends the invocation (`action_failed`, `blocked`, CLI `command_failed`, exit 1); the same timeout inside a post-crew child becomes that job's failed receipt (`job_failed`, task `background_job_failed`) and discards a finished Unity validation. The operator gaps this caused in run 2 totalled 11 min 50 s.

### Commits and lineage

| | Commit | Parent | Branch / isolated worktree |
|---|---|---|---|
| Reviewed original | `24603b97cd1a071b3f48d14d15adb1d831f2cf95` | `1dae47bea3625280e27170ea398aef9d881d744f` (the **rejected** re-pin, so not proposed on this parent) | `throughput/gauntlet-trial-fixes`, `C:\nscrev\gauntlet-fixes` |
| **Proposed for audit** | `c8b07eb138e2e23233eb4a464bd72b22ad1591db` (cherry-pick of `24603b9`) | `36a000c3918680b150d950104c1b21724c0a3dd0` (item 2) | `throughput/assistantcontrol-fixes`, `C:\nscrev\ac-fixes` |

The two commits change disjoint files; after the cherry-pick every lock-fix file is byte-identical to `24603b9`, every migration file byte-identical to `36a000c`, and `1dae47b` is not an ancestor. `git diff 027e787 c8b07eb --check` is clean.

### Exact changed files (9)

| File | Change |
|---|---|
| `Pipeline/AssistantControl/graph_controller.py` | +164/-11: `LOCK_DEFERRABLE_ACTION_KINDS` with per-kind proof, `_checkouts_lock_contention`, `_lock_deferral`, `action_deferred` journal event, bounded retry in `_run_owned`, `lock_deferrals` in the run result |
| `Pipeline/AssistantControl/background_jobs.py` | +43/-1: `LAUNCH_LOCK_TIMEOUT_SECONDS`, and a pre-mutation stamp on `launch`'s first `checkouts.lock` acquisition only |
| `Pipeline/AssistantControl/candidate.py` | +15/-1: registration waits up to `REGISTRATION_LOCK_TIMEOUT_SECONDS = 300` |
| `Pipeline/AssistantControl/post_crew_workflow.py` | +17/-2: validation persist waits up to `VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS = 300` |
| `Pipeline/AssistantControl/test_background_jobs.py` | +325/-1: controller-side deferral tests |
| `Pipeline/AssistantControl/test_post_crew_workflow.py` | +190: child-side tests |
| `Pipeline/AssistantControl/README.md` | +28 |
| `Pipeline/AssistantControl/CURRENT.md` | +43 |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | +23/-1 |

### Behaviour

- **Controller side.** An action whose kind is in the allowlist and which loses its `checkouts.lock` wait before writing anything durable journals `action_deferred` (task, kind, `lock_contention`, lock path, seconds waited, count, limit), is not marked blocked, writes no `last_error`, keeps the invocation `running`, pauses 3 s through the controller's own `sleep`, and is re-emitted by the planner. After 6 consecutive deferrals of the same action it fails exactly as today. Deferral counts reset per invocation; stop requests are still honoured between deferrals.
- **Classification is typed.** `TimeoutError` with `errno.ETIMEDOUT`, `filename` equal to this checkout root's `checkouts.lock`, and the producer's exact wording. For the two launch kinds the exception must also carry the stamp `background_jobs.launch` sets on its single pre-mutation acquisition, because `_mark_spawn_failed` takes the same lock after a child exists.
- **Allowlist (11 kinds), each with a code-comment proof that the lock precedes every durable write:** `decompose`, `post_crew`, `prepare`, `refresh_prepared`, `scope`, `reserve`, `start_worker`, `settle_worker`, `sync_candidate`, `auto_approve`, `integrate`. Excluded: `apply_decomposition` (never takes `checkouts.lock`; verified it takes `decomposition.lock` and the Source integration lock) and the wait kinds (their acquisitions persist an observation or a Docker removal that already happened).
- **Child side.** Candidate registration and the post-validation record persist wait up to 300 s. `_exclusive_file_lock` already retries every 50 ms, so the longer budget is the bounded retry. Unity validation already ran with the lock released, and the persist re-verifies the exact candidate on acquisition. The launch budget was not lengthened.

### Tests

Twelve new tests:

| Test | Guards |
|---|---|
| `test_a_lock_contended_launch_is_deferred_and_launches_on_the_next_cycle` | launch deferral and later launch |
| `test_lock_contention_beyond_the_bound_fails_with_the_original_error` | the bound |
| `test_an_action_kind_outside_the_allowlist_still_fails_on_the_same_timeout` | unchanged behaviour outside the allowlist |
| `test_a_deferred_launch_leaves_no_ticket_index_or_run_root` | no durable residue |
| `test_a_lock_contended_sync_candidate_is_deferred_not_fatal` | foreground kind, run 2 02:50:47Z |
| `test_a_lock_contended_auto_approve_is_deferred_not_fatal` | foreground kind, run 2 02:51:32Z |
| `test_a_childs_own_lock_timeout_stays_a_harvested_job_failure` | child path kept distinct |
| `test_a_child_whose_first_registration_lock_attempt_times_out_still_completes` | child registration retry |
| `test_a_registration_lock_held_past_the_bound_fails_with_the_original_error` | child bound |
| `test_validation_runs_with_the_checkout_lock_free_and_the_persist_outwaits_it` | no discarded validation |
| `test_a_lock_held_past_the_persist_budget_fails_loudly_and_retains_state` | persist bound |
| `test_the_persist_refuses_when_the_candidate_changed_underneath` | identity re-check on re-lock |

**Failing-before on `1dae47b`** (the agent's run, with only the new constant names added as inert shims so the tests import): `FAILED (failures=5, errors=4)`; 9 fail, including the launch test reproducing the live error verbatim (`background_jobs.py:542 ... TimeoutError: [Errno 10060] timed out after 10s ... checkouts.lock`). Three pass before by design: the allowlist-gate test and the persist-bound test assert behaviour that must not change, and the candidate re-verification test guards a property that already existed.

**Reproduced by the coordinating session** on a fresh shimmed worktree of `1dae47b`: the launch-deferral and `sync_candidate`-deferral tests both `ERROR` with `TimeoutError: [Errno 10060] timed out after 0.2s waiting for exclusive file lock: '...\checkouts.lock'` (`Ran 2 tests ... FAILED (errors=2)`).

**Passing-after on `24603b9`, rerun by the coordinating session:**
- `Pipeline.AssistantControl.test_background_jobs.BackgroundJobLoopTests`: `Ran 35 tests in 221.539s` `OK`
- `Pipeline.AssistantControl.test_post_crew_workflow`: `Ran 15 tests in 113.728s` `OK`
- `Pipeline.AssistantControl.test_graph_controller`: `Ran 33 tests in 90.006s` `OK`
- `Pipeline.AssistantControl.test_decomposition`: `Ran 19 tests in 57.520s` `OK`
- `Pipeline.AssistantControl.test_candidate`: `Ran 9 tests in 51.135s` `OK`
- `Pipeline.AssistantControl.test_worker_control`: `Ran 10 tests in 18.700s` `OK`

Implementing agent, additionally: the 12 new tests `Ran 12 tests in 48.887s OK`; full `test_background_jobs` `Ran 67 tests OK`; `test_candidate` + `test_unity_materialization` `Ran 15 tests OK`; `test_gauntlet_replay` + `test_review` `Ran 13 tests OK`.

### Follow-up commit: per-cycle harvest, cleanup retries and startup reconciliation

| | Commit | Parent | Branch / isolated worktree |
|---|---|---|---|
| Reviewed original | `b42d5197d006149f25cfa354f168deebeba1c151` | `24603b97cd1a071b3f48d14d15adb1d831f2cf95` | `throughput/gauntlet-trial-fixes`, `C:\nscrev\gauntlet-fixes` |
| **Proposed for audit** | `42c09a3c5c3dd9e4582e329b361a2662ece4ab62` (cherry-pick of `b42d519`) | `c8b07eb138e2e23233eb4a464bd72b22ad1591db` | `throughput/assistantcontrol-fixes`, `C:\nscrev\ac-fixes` |

**The gap it closes.** Found in review of the first commit, with no test covering it: `_harvest_jobs` runs at the top of every cycle, outside `_execute_timed`, and caught only `BackgroundJobError`, while `background_jobs.harvest()` takes `checkouts.lock` with a 10 s budget. A lock timeout there escaped the loop and ended the invocation, contradicting the method's own docstring. `_reconcile_startup` re-raised the same timeout. Children now queue for up to 300 s instead of failing fast, which makes contiguous holds more likely, so this path had to close with the first commit.

**Exact changed files (6):**

| File | Change |
|---|---|
| `Pipeline/AssistantControl/background_jobs.py` | +169/-36: `_pre_mutation_lock` helper, `stamped_lock_contention`, `JOB_INDEX_LOCK_TIMEOUT_SECONDS`, stamps on the acquisitions below, retry-in-place parameters for `reconcile_startup` |
| `Pipeline/AssistantControl/graph_controller.py` | +84/-2: `_harvest_lock_deferral`, `job_harvest_deferred` with `reason: lock_contention`, `startup_deferred`, `harvest_deferrals` and `startup_deferrals` in the run result |
| `Pipeline/AssistantControl/test_background_jobs.py` | +368/-14: 8 tests |
| `Pipeline/AssistantControl/README.md` | +15 |
| `Pipeline/AssistantControl/CURRENT.md` | +27 |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | +9 |

**Which acquisitions may be deferred:**

| Acquisition | Verdict | Reason |
|---|---|---|
| `harvest`, first transaction | stamped | only an outcome check precedes it; the status write, cleanup begin and index write all happen under it |
| `_run_cleanup`, cleanup-generation begin | stamped | precedes this call's writes and its unlocked Docker work |
| `_record_final_recheck` | stamped | one read-verify-write transaction |
| `request_stop` | stamped | its lock is its first effect; a repeat re-verifies an existing request |
| `_record_reconciliation` | stamped | one read-verify-write transaction |
| `launch` | stamped, behaviour unchanged | now routed through the same helper |
| `_finish_cleanup` | refuted, unstamped | follows a written cleanup begin and a completed Docker reconciliation, possibly a removal |
| `_enforce_stop` | refuted, never retried | terminates a process tree; whether it can repeat depends on host state, not durable records |

**Behaviour.**
- **Per-cycle harvest.** A stamped timeout from `harvest` or `settle_cleanup` journals `job_harvest_deferred` (step, lock path, seconds waited, count, limit), skips that job for this cycle and keeps the invocation running. Bound: 6 per task and job, reset on success and per invocation; the seventh loss raises the original error.
- **Startup.** `reconcile_startup` retries only the contended call, in place and with the same arguments, up to 6 times with a 3 s wait, journaling `startup_deferred`. Re-running the whole reconciliation was rejected because it would lose outcomes already persisted and change the branch a ticket takes. Past the bound the original `TimeoutError` ends startup exactly as before.
- **Everything else is unchanged.** An unstamped timeout, or one on another lock path, keeps today's behaviour. Stop paths and `clear` see today's exceptions; the stamp is only an attribute on the unchanged `TimeoutError`.

**Review notes from the coordinating session.**
- `harvest()` has exactly two lock sites: the stamped first transaction, which precedes every write, and the unstamped `_finish_cleanup`. A stamped timeout therefore never follows a recorded harvest, so a retried harvest cannot skip its `job_completed` event.
- The startup retry wrapper binds each ticket's values before building the call and invokes it immediately, so no loop variable is captured late.

**Tests (8):**

| Test | Guards |
|---|---|
| `BackgroundJobLoopTests.test_a_lock_contended_harvest_is_deferred_and_the_job_is_harvested_on_a_later_cycle` | real held lock; the next cycle harvests with the correct receipt; index bytes unchanged between attempts |
| `BackgroundJobLoopTests.test_harvest_contention_beyond_the_bound_raises_the_original_error` | harvest bound |
| `BackgroundJobLoopTests.test_an_unstamped_lock_timeout_after_the_cleanup_began_still_ends_the_invocation` | the refuted `_finish_cleanup` path is unchanged |
| `BackgroundJobLoopTests.test_a_lock_contended_cleanup_retry_is_deferred_and_settled_on_a_later_cycle` | the lost attempt changes no bytes and makes no Docker call |
| `BackgroundJobLoopTests.test_a_lock_contended_startup_harvest_is_retried_in_place_and_the_run_continues` | startup retry in place; exactly one Docker inspect |
| `BackgroundJobLoopTests.test_startup_contention_beyond_the_bound_raises_the_original_error` | startup bound |
| `BackgroundJobMechanismTests.test_only_transactions_that_have_written_nothing_stamp_a_lost_checkouts_lock_wait` | stamp inventory; a raw timeout is unmarked; a mark never matches another path |
| `BackgroundJobMechanismTests.test_startup_retries_a_contended_stop_request_and_quarantine_record_in_place` | quarantine path retried in place; the tree is terminated once |

**Failing-before on `24603b9`** (implementing agent, with two inert shims so the tests import: `JOB_INDEX_LOCK_TIMEOUT_SECONDS`, unused there, and a `stamped_lock_contention` that honestly reads the stamp, which only `launch` sets at `24603b9`): `Ran 8 tests in 131.904s FAILED (failures=7, errors=4)`. The harvest, cleanup-retry and startup-harvest tests hit the three `TimeoutError` tracebacks (`_harvest_jobs -> harvest`, `_harvest_jobs -> settle_cleanup -> _run_cleanup`, `reconcile_startup -> harvest`). Both bound tests fail because nothing is journaled. The inventory test fails 5 of 6 subtests, since only `launch` was already stamped. The quarantine test fails on the missing `lock_retry_limit` keyword. The unstamped-timeout test passes by design.

**Reproduced by the coordinating session** on a fresh worktree of `24603b9` with the agent's identical shim: `Ran 8 tests in 130.208s FAILED (failures=7, errors=4)`, the same counts. Errors: the harvest, cleanup-retry and startup-harvest tests each end on `TimeoutError: [Errno 10060] timed out after 10s waiting for exclusive file lock: '...\checkouts.lock'`, and the quarantine test on `TypeError: reconcile_startup() got an unexpected keyword argument 'lock_retry_limit'`. Failures: both bound tests (for example `Lists differ: ['job_launched', 'job_harvest_deferred', ...] != ['job_launched']`) and five inventory subtests (`False is not true`). The unstamped-timeout test passes, as designed. The worktree was removed and pruned afterwards.

**Passing-after on `b42d519`** (implementing agent, working tree immediately before the commit): new tests `Ran 6 tests in 40.523s OK` and `Ran 2 tests in 2.493s OK`; `BackgroundJobLoopTests` `Ran 41 tests in 226.726s OK`; `BackgroundJobMechanismTests` `Ran 34 tests in 49.900s OK`; `test_graph_controller` `Ran 33 tests in 87.202s OK`; `test_post_crew_workflow` `Ran 15 tests in 95.587s OK`; `test_decomposition` `Ran 19 tests in 52.400s OK`; `git diff 24603b9 b42d519 --check` clean. The coordinating session's single run on the combined head is at the top of this comment.

**Deliberately unchanged by the follow-up:** `_finish_cleanup`, `_enforce_stop`, `_mark_spawn_failed`, `clear`, and the planner.

**Follow-up residual risks:**
1. **A same-task relaunch can still end a run.** `_job_gate` treats a completed but unharvested job as imposing nothing. Narrow path: a post-crew task's harvest is deferred, a `sync_candidate` for that task succeeds, the next harvest loses its wait again, and a `post_crew` launch for the same task gets the lock in that cycle; `launch` then refuses with "already has an active background job", which ends the invocation. The path already existed through the `BackgroundJobError` deferral; lock contention makes it more reachable. **Decision: gate the task as `wait_job` while a harvest deferral is pending for its job (small planner change), or accept for now.**
2. A failed or died job with nothing else eligible ends the run `blocked`, as any blocked graph does; its harvest record lands at the next startup.
3. A startup cleanup retry may wait out the container tombstone again; bounded.

### Deliberately left unchanged

- `unity_materialization.materialize_candidate` still holds `checkouts.lock` across the Unity builder and validation. Releasing it mid-transaction would invert lock order against every other caller (checkouts lock, then Source lock) and would need re-verified re-reads before six record writes; it needs its own reviewed change. The current Gauntlet tasks never reach it.
- `apply_decomposition` and the wait kinds keep today's failure path (above).
- `_mark_spawn_failed` is deliberately not deferrable: it runs after a child exists.
- The 10 s launch budget and every other 10 s acquisition outside the allowlist (operator commands, stop and clear paths) are unchanged.
- The abandoned staffing work is not revived; no unrelated change is included.

### Residual risks and decisions needed

1. **Materialization lock hold** (above): the largest remaining hold; recommended as its own reviewed change before real-game tasks that materialize Unity builder output run at concurrency above 1.
2. **No global deferral cap.** The bound is per action. A lock that is busy but keeps moving could let several distinct actions each accrue deferrals; a truly wedged lock still fails loudly.
3. **Test faithfulness.** The launch tests drive the real `background_jobs.launch` against a real held lock. The `sync_candidate` and `auto_approve` tests reproduce the production acquisition from the fixture foreground; the proof that those production sites raise before writing is the per-kind audit in the code comment. The child tests exercise `run_post_crew_workflow` directly rather than a detached child.
4. **`start_worker` is in the allowlist** beyond the originally named kinds; its pre-mutation property was proven and accepted in review.
