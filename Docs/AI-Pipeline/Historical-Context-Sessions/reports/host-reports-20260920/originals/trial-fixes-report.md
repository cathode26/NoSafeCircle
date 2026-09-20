# Trial fixes: corrected-review apply, and the Source lane held around a decomposition proposal

To: Codex / Astra
Worktree: `C:\nscrev\trial`, branch `throughput/gauntlet-trial`, base `573302b`
(the cherry-picked bounded author correction; the staffing commit `37899ac` is
deliberately absent from this base). Nothing pushed, nothing merged, no Docker,
no provider call, nothing under `C:\NSC` touched.

| Commit | Subject |
| --- | --- |
| `9521f4e` | AssistantControl: apply the corrected decomposition review shape, and nothing else |
| `bdc9a92` | AssistantControl: hold the Source lane while a decomposition proposal is in flight |

`git diff 573302b HEAD --check` is clean. The working tree is clean.

---

## Commit A — `9521f4e`, the corrected review shape reaches apply

**Files**

- `Pipeline/AssistantControl/decomposition.py` (+32/-3)
- `Pipeline/AssistantControl/test_decomposition.py` (+235)

**The defect.** `_verify_review` required `len(rounds) == 2` and unpacked
`author, reviewer = rounds`. A `review_ready` run that used the one bounded
author correction retains its deterministically rejected first round, so its
`rounds` list holds three entries — the rejected round 1, the correction that
authored the reviewed candidate, and the reviewer. `apply_decomposition` refused
every such proposal with *Decomposition review must contain exactly one author
and one reviewer round*. The proposal the correction exists to rescue could
never be applied.

**The behaviour now.** Exactly two round shapes verify and nothing else.

*Uncorrected* — unchanged from before: two rounds, author then reviewer, with
`author_corrections_used` 0 or absent. An uncorrected pair that claims
`author_corrections_used: 1` is refused with *counts an author correction its
rounds do not carry*.

*Corrected* — three rounds, and `author_corrections_used == 1`:

| Entry | Required |
| --- | --- |
| `rounds[0]` | `role: task_decomposer`, `requested_provider: providers[0]`, `agent_status: succeeded`, `status: rejected`, `candidate_after: null`, `correction_of_round: null` |
| `rounds[1]` | `correction_of_round: 1`, `role: task_decomposer`, `requested_provider: providers[0]`, `agent_status: succeeded`, `status: correction_candidate_valid`, `candidate_after == latest_candidate` |
| `rounds[2]` | the reviewer, exactly as today, plus `correction_of_round: null` |

Anything else stays refused: a correction with any other status, a correction
without the count, a correction naming another round, a first round that already
produced a candidate, a reviewer round claiming to be a correction, and any
fourth round. The returned review keeps its existing shape; `models` names the
round that authored the reviewed candidate, which for a corrected run is the
correction.

**The two other readers of the same run result.**

- `Pipeline/TaskReviewAgent/local_decomposition_apply.py` (162–193) never had the
  positional assumption: it takes the reviewer from `rounds[-1]` and the
  authoring round from the last earlier entry carrying a `candidate_after`,
  which is the correction. It additionally requires two distinct *confirmed
  pooled session ids*, and the correction is not offered to pooled runs, so a
  corrected run cannot reach it at all. No change.
- `Pipeline/TaskReviewAgent/decomposition_authorization.py` — **this one is not
  what the brief predicted, and is reported rather than changed.**
  `_call_accounting_valid` requires `len(rounds) == calls_used`, and
  `_round_chain_invalid` reads `rounds[1:]` as the reviewer rounds. A corrected
  run has three rounds and `calls_used: 2`, so it is refused as
  `bounded_call_accounting_invalid`. It is **not** pooled-gated for a
  cross-provider run: `_validated_provider_order` only consults
  `pooled_sessions` for the same-provider case, so a cross-provider corrected run
  does reach the accounting check. Its caller, `polling_orchestrator`, passes
  `--enable-decomposition-session-pool` only when session pooling is enabled
  (`polling_orchestrator.py:2217-2222`), so this is unreachable for a pooled
  deployment but not unreachable in general. Nothing regresses — that module
  refuses a corrected run today and still refuses it — but if the Issue-driven
  path is ever expected to apply a corrected proposal with pooling off, it needs
  its own repair. Listed under residual risks.

**Failing before, on `573302b`** (detached worktree `C:\nscrev\before-573302b`,
final test file copied in, only the new class run):

```
ERROR: test_one_bounded_correction_between_the_rounds_verifies
  File "...\Pipeline\AssistantControl\decomposition.py", line 207, in _verify_review
    raise ValueError("Decomposition review must contain exactly one author and one reviewer round")
ValueError: Decomposition review must contain exactly one author and one reviewer round
Ran 1 test in 1.101s
FAILED (errors=1)
```

The whole new class at `573302b`: `Ran 9 tests ... FAILED (failures=7, errors=1)`
— the ninth is `test_a_second_correction_entry_is_refused`, which passes before
the repair only because the old code refused everything three rounds long.

**Passing after**

```
python -m unittest Pipeline.AssistantControl.test_decomposition
Ran 11 tests in 19.634s
OK
```

---

## Commit B — `bdc9a92`, the Source lane waits for a proposal

**Files**

- `Pipeline/AssistantControl/graph_controller.py` (+122/-3)
- `Pipeline/AssistantControl/test_background_jobs.py` (+251)
- `Pipeline/AssistantControl/README.md` (+18)
- `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` (+9, loop item 4)

**The defect.** NSC-1145 returned a correct two-child proposal that was thrown
away: the controller integrated NSC-1143 at 22:36:03Z while the proposal's
87-second provider call, launched at 22:34:42Z, was still running, and the round
was rejected with *source HEAD changed during provider invocation* and *source
tree changed during provider invocation*.

**The rule, all derived from the current plan and the durable job indexes.**

1. While any `decompose` job is active (index status in `ACTIVE_STATUSES`),
   `integrate` and `apply_decomposition` are held. Nothing else is: settlement,
   post-crew launches, `prepare`/`refresh_prepared`/`scope`,
   `reserve`/`start_worker`, `sync_candidate` and `auto_approve` all continue,
   because none of them advances the Source commit.
2. At most one proposal is in flight. A second decompose-ready parent is held
   until the first job has ended **and** its `apply_decomposition` has landed or
   been recorded as failed (reason `decomposition_apply_pending`).
3. A Source-moving action ready in the same cycle as a new `decompose` launch
   goes first; the launch is held for exactly that cycle (reason
   `source_lane_action_ready`).

**How it is expressed.** `plan()` calls the new `_source_lane_holds` and returns
a new top-level `held` list; each held action also keeps its place in
`next_actions` carrying a `held` record `{task_id, kind, reason,
blocking_task_id, blocking_job_id}`, so `graph-plan` and the viewer show what is
waiting and why, and the viewer's one-action-per-task and
actionable/blocked-disjoint invariants are untouched. `_choose_run_action`
filters held actions out before its existing priority classes run — no class was
reordered and no action's execution changed — and when a hold is all that
remains the loop waits on the blocking job instead of ending the run.
`_journal_source_lane_holds` writes one `source_lane_held` event per hold per
invocation, re-journaling only if the blocking job or the reason changes and
forgetting a hold when it is released.

**Restart.** Every input is durable, so a fresh controller instance over the
same records derives an identical `held` list from the job index alone. It
journals that hold once more under its own invocation id — a restart is a new
invocation and records why it is holding; it does not re-journal per cycle.
Test (5) asserts both halves: identical `held` records across instances, and
exactly one `source_lane_held` event for the restarted invocation across four
planning cycles that all held the same action.

**Tests** (all loop-level, fixture clock/host, `fake_foreground`). `fake_foreground`
gained one optional `on_source_move(kind, task_id)` hook so a test can land a
fixture Source move; no existing caller changes.

| Test | Proves |
| --- | --- |
| `test_every_other_action_continues_while_the_source_lane_is_held` | settle, post-crew launch, prepare/scope/reserve/start_worker and `auto_approve` all run with a proposal in flight; no `integrate` runs; the final plan holds both approved candidates |
| `test_integrate_is_held_while_a_decomposition_proposal_is_in_flight` | the ready `integrate` is held with the exact blocking job id, and runs at fixture time 50.0 — the instant the proposal ends — with no job then running |
| `test_second_decomposition_waits_for_the_first_proposal_and_its_apply` | launches at 0.0 and 20.0 only; the second is held first as `decomposition_proposal_in_flight`, then as `decomposition_apply_pending`, and starts only after the first apply |
| `test_held_actions_become_eligible_when_the_proposal_ends` | both a held `integrate` and a held second `decompose` are released when the proposal ends, Source move first and the launch on the next cycle |
| `test_ready_integrate_goes_first_and_the_decomposition_launches_next_cycle` | rule 3 in isolation: integrate at 0.0 with no job running, launch on the next cycle |
| `test_restarted_controller_rebuilds_the_hold_from_the_durable_index` | a new controller instance reconstructs the identical hold and journals it once for its invocation across four held cycles |

**Failing before, on `573302b`** (detached worktree, final test file copied in,
only that test run):

```
ERROR: test_integrate_is_held_while_a_decomposition_proposal_is_in_flight
  File "...\test_background_jobs.py", line 665, in test_...
    integrate["held"],
KeyError: 'held'
Ran 1 test in 3.726s
FAILED (errors=1)
```

Because the `KeyError` stops the test before the loop runs, the same fixture was
also replayed without assertions on both revisions, which is the behavioural
proof:

```
=== BEFORE (573302b) ===            === AFTER (bdc9a92) ===
plan marks the integrate held : False       plan marks the integrate held : True
completed actions : [('integrate','NSC-899'),   completed actions : [('wait_job','NSC-1200'),
                    ('integrate','NSC-899')]                        ('integrate','NSC-899')]
integrate ran at fixture time : 0.0         integrate ran at fixture time : 50.0
decompose jobs running then   : ['NSC-1200'] decompose jobs running then  : []
proposal ends at fixture time : 50.0        proposal ends at fixture time : 50.0
source_lane_held events       : []          source_lane_held events       : 1 event, blocking NSC-1200
```

Before the repair the integration moves Source at fixture time 0.0 with the
proposal still running — NSC-1145 exactly.

**Passing after**

```
python -m unittest Pipeline.AssistantControl.test_background_jobs.BackgroundJobLoopTests
Ran 28 tests in 166.121s
OK

python -m unittest Pipeline.AssistantControl.test_background_jobs
Ran 60 tests in 240.300s
OK

python -m unittest Pipeline.AssistantControl.test_graph_controller
Ran 33 tests in 118.396s
OK

python -m unittest Pipeline.AssistantControl.test_decomposition
Ran 11 tests in 19.634s
OK
```

---

## Residual risks

1. **`decomposition_authorization.py` still refuses a corrected run.**
   `_call_accounting_valid` (`len(rounds) == calls_used`) and
   `_round_chain_invalid` (`rounds[1:]` are reviewer rounds) do not know about a
   correction entry. Unreachable while the Issue-driven path runs with session
   pooling on, reachable with pooling off. Out of this repair's scope; decide
   whether the Issue path must apply corrected proposals.
2. **`held` is a new top-level plan key and `correction_of_round` a new round
   key,** both additive under an unchanged `SCHEMA_VERSION` /
   `ROUND_RESULT_SCHEMA_VERSION`. Every consumer read is `.get`-based, and the
   viewer's plan preflight checks a fixed subset, so nothing refuses the new
   keys — but a future exact-key comparison anywhere would.
3. **The hold reads the recorded index status, not a fresh observation.** The
   run loop harvests ended jobs before every plan, so it is accurate there; a
   bare `graph-plan` between harvests can report a hold for a job that has just
   ended. It errs toward holding, never toward releasing early.
4. **Fixture Source moves in the new tests are simulated** (`on_source_move`
   marks the record integrated/applied); the real `integrate` and
   `apply_decomposition` are not exercised end to end here, as in the existing
   loop tests.
5. **`models` in a corrected review names the correction's model**, not the
   rejected first round's. Same provider in practice, but a report reading
   `review["models"]` sees the correcting call.
6. **Leftover worktree, not mine to remove:** `C:\nscrev\before-37899ac` is
   still registered in the `C:\nscrev\decomp-fix` clone from the earlier
   failing-before run. I was instructed not to touch that clone, so it needs a
   `git -C /c/nscrev/decomp-fix worktree remove --force /c/nscrev/before-37899ac`
   plus `worktree prune` from whoever owns it. The `C:\nscrev\trial` worktree I
   created for this job (`before-573302b`) has been removed and pruned.
