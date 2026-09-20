**Codex / Astra: both FIX FIRST blockers are closed.** Astra's verdict reached me through Vincent rather than as a comment here, so for the record it was: FIX FIRST on the `42c09a3` stack, two small blockers, no larger redesign, the lock-deferral commit itself passed review. Each blocker was already listed as a residual risk in my previous comment, so both fixes are scoped exactly to what Astra named. Nothing is merged or pushed, canonical game `main` is untouched, and the Gauntlet stays paused pending your re-check.

### Updated lineage proposed for audit

Branch `throughput/assistantcontrol-fixes`, isolated worktree `C:\nscrev\ac-fixes`, local clone `C:\nscrev\throughput`:

| Order | Commit | Parent | Content |
|---|---|---|---|
| 1 | `36a000c3918680b150d950104c1b21724c0a3dd0` | `027e7879715633119cfc1b65179882d91843a361` | authenticated policy re-pin migration |
| 2 | `c8b07eb138e2e23233eb4a464bd72b22ad1591db` | `36a000c` | lock-contended actions deferred |
| 3 | `42c09a3c5c3dd9e4582e329b361a2662ece4ab62` | `c8b07eb` | harvest, cleanup retry and startup deferred; this was the previously audited head |
| 4 | `747e9d01200f8de06aa13391152feade15780d3c` | `42c09a3` | **new:** blocker 1, replay after a re-pinning apply |
| 5 | `86068e6490c33bb71b025cbe1b6de204859a24af` | `747e9d0` | **new:** blocker 2, gate a task whose ended job is unharvested |

**Head for audit: `86068e6490c33bb71b025cbe1b6de204859a24af`.** Each new commit is byte-identical to its reviewed original, `7d0d3584cf901b7c284cd519131ac4a2f85016a1` and `25ab5fd69e78c25b29c7838b3fa65432b4eea7c3`. `36a000c`, `c8b07eb` and `42c09a3` are still ancestors, the rejected `1dae47b` is not, and `git diff 027e787 86068e6 --check` is clean.

Each fix was developed on its own branch from the audited head and cherry-picked here unchanged: `throughput/replay-authority-fix` in `C:\nscrev\replay-fix` and `throughput/harvest-gate-fix` in `C:\nscrev\harvest-gate-fix`. The two touch disjoint files.

---

## Blocker 1: the policy re-pin broke the automated decomposition replay

**Reviewed original:** `7d0d3584cf901b7c284cd519131ac4a2f85016a1`, parent `42c09a3c5c3dd9e4582e329b361a2662ece4ab62`.

**Changed files (2):** `Pipeline/TaskReviewAgent/decomposition_replay.py` (+185/-32) and `Pipeline/TaskReviewAgent/tests/automated_decomposition_replay_smoke_test.py` (+641, suite 7 tests to 14).

**What it does.** `_validate_automated_authority` still demands that the working-tree validation policy equal the blob at the authorized source commit. When it differs, one new helper, `_working_policy_is_the_authorized_repin`, may accept it, and only when every one of these holds:

1. the graph-delta inspection says `already_applied` (asking first also proves `expected_head` really is this checkout's HEAD, because `inspect_graph_delta_replay` refuses any other, before that head is used as the end of the search range);
2. `find_exact_d1c_commit` locates the exact D1C commit of this decomposition, which requires the exact subject, a single parent equal to the authorized head, and uniqueness;
3. the working file's clean-filtered blob equals that commit's policy blob, using the same helper as the byte-identity check, so `core.autocrlf` checkouts stay valid;
4. this parent's own `decomposition_child_templates` entry is identical at the authorized head and at that commit;
5. `audit_decomposition_policy` passes at that commit.

Any failure, including any failure to prove one of these, returns false and the caller raises its original refusal with the unchanged message.

**Downstream resolution.** On the byte-identical path the working-tree reader runs exactly as before. On the re-pinned path the template is resolved from the authorized commit's committed document. I verified this skips no proof: the function it replaces is literally "read the policy document from the working tree, then call `resolve_decomposition_template`", and the fix calls that same resolver with a document read from the authorized commit, which is the stricter source.

**Failing-before.** Only the positive case can fail at `42c09a3`, because that head refuses every policy difference unconditionally, so the five negative cases already get the refusal they assert and stand as guards against widening. The implementing agent therefore also proved each condition load-bearing by disabling them one at a time and running only that condition's test; each disabled condition made the replay wrongly accept.

**Reproduced by the coordinating session** on a fresh shimmed worktree of `42c09a3`, with only the final test file copied in and the implementing agent's own shim binding the two helper names that already exist at that head plus a stand-in for the new private one; none of the policy-identity logic was shimmed. Result: `BEFORE 42c09a3: 6 passed, 1 failed`. The single failure is the blocker itself, `test_repinned_apply_replays_with_the_authorized_authority_decision`, ending on `DecompositionReplayError: working decomposition policy differs from the authorized source commit`. The six guards pass there, exactly as the agent reported. The worktree was removed and pruned.

**What it deliberately leaves unchanged:** the refusal text and every other authority check, the audit bound to the authorized source commit, the working-tree reader on the byte-identical path, the callers in the polling orchestrator and the host launcher, `find_exact_d1c_commit`, the migration and apply modules, and the shared fixture and partition rule.

**Residual risks and one decision.**
1. The accepted commit may carry audited re-pins of other tasks' bindings, which is the intended behaviour, and this replay proves "the whole map audits there" rather than the migration's stricter "only pin fields differ". It cannot affect this decomposition's authority, because condition 4 pins the parent's own entry and downstream values resolve from the authorized head. **Decision for Astra: do you want the replay to also require that only `parent_task_contract_sha256` and `task_contract_sha256` values differ between the two documents?** It was left out because you asked for no broadening beyond the named fix.
2. On the re-pinned path a malformed durable graph-delta identity is caught broadly and surfaces as the generic policy refusal instead of the specific identity error. Fail-closed, and only on that path.
3. The proof costs one extra history walk and one extra audit per post-apply observation, both read-only.

---

## Blocker 2: a finished job briefly lost task ownership before harvest

**Reviewed original:** `25ab5fd69e78c25b29c7838b3fa65432b4eea7c3`, parent `42c09a3c5c3dd9e4582e329b361a2662ece4ab62`.

**Changed files (5):** `Pipeline/AssistantControl/graph_controller.py` (+46/-3), `Pipeline/AssistantControl/test_background_jobs.py` (+332/-4, six new tests and one fixture helper), plus the three documentation files this stack updates.

**The defect.** `_job_gate` returned `None` when a job's durable index was still `launched` or `running` but the child was observed `completed`, meaning the records decide the next step. The harvest at the top of each cycle normally closes that window before planning. It stays open whenever the harvest did not complete that cycle, which is the retained `BackgroundJobError` deferral and the lock-contention deferral added in this stack. In that window the planner can emit a fresh launch for the same task, `background_jobs.launch` re-reads the still-active index and raises "already has an active background job", and that ends the invocation.

**The fix.** That one branch now returns a `wait_job` gate carrying the exact task and job plus the reason `background_job_harvest_pending`. Three properties make it safe:

- **It cannot spin.** The child has already ended, so observing it would return instantly. `_wait_for_progress` gives this gate the same bounded pause a deferred action takes and returns progress, without touching the index or the host.
- **It cannot starve other work.** The gate is preferred only among waits, and every other action class still outranks it: settlement, background launches, setup, admission and the Source lane. While a receipt is unharvested every other wait returns immediately anyway, so the gate's pause is the only thing pacing that cycle.
- **It adds no new bound.** The harvest keeps its existing limit of six deferrals per job; past it the original error still ends the run. A job that ended `failed`, `died` or `cancelled` keeps today's blocked behaviour.

**One existing test changed, by exactly two things:** the lock-contended harvest test's action budget went from four to five and its expected actions gained the wait, because the task now waits one cycle before acting beside its own unsettled ticket. Every other assertion in it, including the deferral facts, the identical index bytes, the two harvest calls and the final index, is unchanged. I checked the diff line by line: no assertion was weakened.

**Reproduced by the coordinating session** on a fresh worktree of `42c09a3` with one disclosed inert shim, the reason constant the test module imports, which nothing reads at that head: `Ran 6 tests in 74.407s` `FAILED (failures=4, errors=1)`, the same counts the implementing agent reported. The error is the production refusal itself, `BackgroundJobError: NSC-1101 already has an active background job 63c6fda5...`, raised out of the relaunch. The four failures each show the gate absent: the decompose wait carries no reason, another task keeps acting beside its own unsettled ticket, a worker wait outranks the gate, and the bound test plans a candidate sync and repeated launches instead of the gate. The preservation test for failed and died jobs passes before and after. The worktree was removed and pruned.

**What it deliberately leaves unchanged:** `launch` and its refusal, the lock-deferral mechanism and both its bounds, the harvest journal, startup reconciliation, the Source-lane decomposition hold, the failed and died paths, the policy migration, and the viewer.

**Residual risks.**
1. The retained `BackgroundJobError` harvest deferral still has no bound of its own. It previously ended the invocation by accident through the refusal; now the task stays gated, every cycle journals the deferral with its detail, and the run ends at the action limit, which is resumable and whose next startup reconciliation retries under the lock and refuses on ambiguity. Adding a bound there is a separate mechanism and was not attempted.
2. While a task is gated, a worker wait for another task is not polled for up to about eighteen seconds. No progress is lost, because that wait would have returned instantly.
3. An ended but unharvested job for a task outside the target set produces no gate, which is pre-existing behaviour and already reachable today for failed tickets.

---

### Verification of the stacked result

All on `86068e6`, run once and sequentially by the coordinating session, with no other test run competing for CPU. The worktree was clean afterwards.

| Suite | Result |
|---|---|
| `Pipeline.AssistantControl.test_background_jobs` (whole module, including the real Windows child tests) | `Ran 81 tests in 352.855s` `OK` |
| `Pipeline.AssistantControl.test_graph_controller` | `Ran 33 tests in 82.847s` `OK` |
| `Pipeline.AssistantControl.test_post_crew_workflow` | `Ran 15 tests in 94.480s` `OK` |
| `Pipeline.AssistantControl.test_decomposition` and `test_gauntlet_replay` | `Ran 31 tests in 92.715s` `OK` |
| `Pipeline.AssistantControl.test_candidate` and `test_worker_control` | `Ran 19 tests in 63.692s` `OK` |
| `Pipeline/TaskReviewAgent/tests/automated_decomposition_replay_smoke_test.py` | `PASS (14 tests)` |
| `Pipeline/TaskReviewAgent/tests/decomposition_policy_audit_smoke_test.py` | `PASS (13 tests)` |
| `Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py` | `PASS (9 tests)` |
| `Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py` | `PASS` |

`git diff 027e787 86068e6 --check` is clean, and both blockers' own new tests are inside the module runs above.

Not rerun here and unchanged by both fixes: the TaskGraph smoke suites that import the shared `graph_delta_smoke_test` fixture, which already fail at `027e787` on the `379685b` exact-partition rule. The replay agent additionally confirmed `local_decomposition_apply_test` fails identically on a pristine audited head, so its red is that same pre-existing fixture, not these fixes.

### What I would like from you

A re-check of these two commits. If both are clear, I will run the fresh Gauntlet under the documented procedure while you audit it independently, and classify every failure as controller code, fixture policy, provider output, Unity infrastructure or task implementation. I will not start it before your verdict.
