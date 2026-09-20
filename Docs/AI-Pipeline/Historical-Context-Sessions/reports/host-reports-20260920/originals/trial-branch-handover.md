# Trial branch handover — `throughput/gauntlet-trial` (worktree `C:\nscrev\trial`)

Handed from session nsc-aa to session nsc-f7 on 2026-09-12 (local evening). From this
handover on, nsc-aa makes no change to this branch or worktree and stays read-only on
`C:\NSC`. Base: `e90670da5b5fc19567e1efe1cb655c43de292f4e` (Astra's local re-review: GO,
not posted to Issue #36). `37899ac` is deliberately excluded.

## Ordered commits (cherry-pick in this order onto `gauntlet-trial/fresh-e90670d` from `4f46117`)

1. `573302bcbf02597ee5fd3db3729c9ed5d2b72e8a` — TaskDecomposition: one bounded author
   correction before the independent reviewer round (cherry-pick of `d8509ae`).
   Files: `Pipeline/TaskDecomposition/round_robin_decomposition.py`, `prompts.py`,
   `README.md`, `tests/author_correction_smoke_test.py` (new),
   `Pipeline/TaskReviewAgent/provider_budget.py`, `.github/workflows/d1b2-core-deterministic.yml`.
   Passing-after (run by nsc-aa on 573302b): `author_correction_smoke_test: PASS`,
   `round_robin_decomposition_smoke_test: PASS`, `pooled decomposition tests: PASS (17 tests)`,
   `round_invocation_id_smoke_test: PASS`, `provider_profiles_test` → `Ran 41 tests in 45.394s` / `OK`.
   Failing-before (nsc-aa, e90670d + the new suite file): `ImportError: cannot import name
   '_observed_contract_differences'`. nsc-f7 reproduced the five suites independently on a
   clean detached worktree of d8509ae.
   Review verdict: validator-agnostic (any `_validate_candidate` exception; the validator's
   exact text is the feedback), bounded (round 1 only, `author_corrections_used` guard,
   pooled runs excluded), fail-closed (correction only when the validation failure was the
   round's only rejection; source revalidation around the correction; second failure ends
   `rejected` with both failures retained; extra call outside `max_calls`, `calls_used` stays 2).

2. `9521f4e0e90c338e1d277879c23845ffec8bd51b` — AssistantControl: `_verify_review` admits the
   corrected three-round shape and nothing else.
   Files: `Pipeline/AssistantControl/decomposition.py` (+32/-3), `test_decomposition.py` (+235).
   Why: `apply_decomposition` required exactly two rounds, so every corrected proposal would
   have been refused with "Decomposition review must contain exactly one author and one
   reviewer round".
   Passing-after (nsc-aa): `python -m unittest Pipeline.AssistantControl.test_decomposition`
   → `Ran 11 tests in 28.946s` / `OK`. Failing-before (delegated agent, on 573302b with the
   final test file): `test_one_bounded_correction_between_the_rounds_verifies` →
   `ValueError: Decomposition review must contain exactly one author and one reviewer round`
   (`Ran 9 tests ... FAILED (failures=7, errors=1)`). Second read by nsc-f7: sound.

3. `bdc9a9236db4690cbc13506a0f2824a089a498f1` — AssistantControl: hold the Source lane while a
   decomposition proposal is in flight.
   Files: `Pipeline/AssistantControl/graph_controller.py` (+122/-3), `test_background_jobs.py`
   (+251), `Pipeline/AssistantControl/README.md` (+18), `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` (+9).
   Rule: while any `decompose` job index is active, `integrate` and `apply_decomposition` are
   held (`DECOMPOSITION_HELD_ACTION_KINDS`); at most one proposal in flight (a second
   `decompose` waits through `decomposition_proposal_in_flight`, then
   `decomposition_apply_pending`); a Source-moving action ready in the same cycle as a new
   launch goes first (`source_lane_action_ready`). `plan()` returns a `held` list and marks
   each held action with a `held` record; `_choose_run_action` filters held actions before its
   unchanged priority classes and waits on the blocking job instead of ending the run; each
   hold is journaled once per invocation as `source_lane_held` (a restart re-journals once
   under its own invocation id). Test helper `fake_foreground` gained an optional
   `on_source_move(kind, task_id)` hook; no existing caller affected.
   Passing-after (nsc-aa, on bdc9a92): `BackgroundJobLoopTests` + `test_graph_controller` +
   `test_decomposition` in one run → `Ran 72 tests in 271.161s` / `OK`. Delegated agent
   additionally: whole `test_background_jobs` → `Ran 60 tests in 240.300s` / `OK`.
   Failing-before (nsc-aa, clean detached worktree of 9521f4e + the final test file):
   `test_integrate_is_held_while_a_decomposition_proposal_is_in_flight` → `KeyError: 'held'`,
   same for `test_held_actions_become_eligible_when_the_proposal_ends` and
   `test_restarted_controller_rebuilds_the_hold_from_the_durable_index`;
   `test_every_other_action_continues_while_the_source_lane_is_held` and
   `test_second_decomposition_waits_for_the_first_proposal_and_its_apply` fail on ordering
   (`Ran 9 tests in 48.680s` / `FAILED (failures=2, errors=3)`).
   `test_ready_integrate_goes_first_and_the_decomposition_launches_next_cycle` passes on the
   base as well (the existing priority order already satisfied it).

4. `027e7879715633119cfc1b65179882d91843a361` — AssistantControl: bind the corrected review
   shape tighter, and test the author's provider (nsc-aa, from nsc-f7's two optional nits).
   Files: `Pipeline/AssistantControl/decomposition.py` (+11/-3), `test_decomposition.py` (+44).
   `author_corrections_used` must be an exact `int` (JSON booleans refused); the retained
   rejected round 1 must carry a non-empty list of non-empty `rejection_reasons`; a correction
   whose `requested_provider` is not `providers[0]` now has a test (already refused in code).
   Passing-after: `test_decomposition` → `Ran 14 tests in 34.232s` / `OK`.
   Failing-before (clean detached worktree of bdc9a92 + final test file):
   `BoundedAuthorCorrectionReviewTests` → `Ran 12 tests in 31.663s` / `FAILED (failures=6)`
   (the boolean test and every `rejection_reasons` subtest fail; the provider test passes as
   a regression guard).

`git diff e90670d 027e787 --check`: clean at every step. Tree clean. Nothing pushed.

## Residual risks and notes for the runner

- `Pipeline/TaskReviewAgent/decomposition_authorization.py` (upstream, Issue-driven human
  authorization path) still refuses a corrected run: `_call_accounting_valid` requires
  `len(rounds) == calls_used` and `_round_chain_invalid` walks rounds positionally. Not on
  the Gauntlet apply path (AssistantControl uses `decomposition.py`), but it must be repaired
  before the upstream port. `GauntletView/server.py` ~1812 reads `rounds/NN` by round number,
  so a correction entry shows round 1's file (cosmetic, legacy viewer only).
- The lane hold uses the durable job index status; the loop harvests before every plan, so
  a job that ended is released on the next cycle. A long proposal (bounded by the job wait,
  up to 3600+180 s) holds integrations for its whole duration by design.
- Fresh-root completeness: a new root has no integration records, so NSC-1141..1144 are not
  complete at 156ad4c; the run therefore starts from `4f46117` per Vincent's decision.
- Run-3 reference numbers for comparison (root `-Checkouts-4`, capacity 10, background-jobs 4):
  decomposition launched 3 s after start, four workers within 50 s, settlements 1.6–11 s after
  exit, approvals ~1–2.4 s, integrations 3–7 s, four independent tasks integrated in 11 min;
  NSC-1140's one-child proposal and NSC-1145's proposal (Source moved mid-call) were the two
  failures these commits address. Failed `NSC-<n>.decomposition.json` records block retries
  (they lived in root -4 only).
- Leftovers not mine: `C:\nscrev\decomp-fix` stash `lane-hold-partial` and the stale
  `before-37899ac` worktree registration in that clone; `C:\nscrev\staffing-repair`
  (37899ac + four uncommitted files) is preserved as evidence.
