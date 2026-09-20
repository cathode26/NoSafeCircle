# Codex decision: include the graph_delta test-fixture repair in the revision-review fix?

Prepared by the coordinating session on 2026-09-13 at about 21:00 UTC for Vincent to hand to Codex.

## Decision needed

Should a repair of the shared graph_delta **test fixture** ship with the bounded revision-review fix (the stack on `throughput/decomposition-revision-review-integration`), later as its own fix, or not at all?

**Recommendation: include it as its own test-only commit in the same stack, after finishing it.** Reason: Astra's requirement 4 says every existing D1C check must be preserved, and the existing D1C and local-apply regression suites only run with this fixture repaired.

## What graph_delta is

`Pipeline/TaskGraph/graph_delta.py` ("Pure deterministic Stage D1A incremental graph-delta planning") turns a validated decomposition result into the exact change to the persistent work graph:
- child task IDs and contracts;
- the parent rewrite;
- inbound dependency rewrites;
- resource-group changes, `updated` or `created` (around lines 232-256).

It calls `validate_decomposition_result`, including the exact child resource-partition rule added in `379685b` (2026-09-11), plus the graph-semantics checks.

Production callers:
- the producer: `round_robin_decomposition.py:270` and `live_decomposition.py:654`;
- `graph_apply_plan` recompute;
- AssistantControl's apply, through `apply_graph_delta` at `decomposition.py:644`.

**Production is not broken.** In the fixed-code Gauntlet on 2026-09-13, NSC-1160 and NSC-1166 were planned, independently approved and applied under that rule. Even NSC-1165's revised candidates received valid graph plan IDs.

## What is broken: test data only

The shared fixture in `Pipeline/TaskGraph/graph_delta_smoke_test.py` (`make_plan` and `validated_result`) gives the children `logical:new-shared`, a resource the parent does not own. Since `379685b`, `validate_decomposition_result` refuses that:

```
DecompositionPolicyError: Child exclusive_resources must exactly partition the parent exclusive_resources (missing=[], extra=['logical:new-shared', 'logical:new-shared'])
```

Every suite that builds on this fixture dies before running a test. All were proven failing at `027e787` or `ade5bca`:
- `Pipeline/TaskGraph/graph_delta_smoke_test.py`
- `graph_apply_plan_smoke_test.py`
- `graph_apply_smoke_test.py`
- `graph_apply_materialize_smoke_test.py`
- `graph_undo_smoke_test.py`
- `Pipeline/TaskReviewAgent/tests/decomposition_authorization_smoke_test.py` (at import)
- `local_decomposition_apply_test.py` (21 tests, 1 failure and 20 errors)
- `task_id_width_smoke_test.py`: 2 of its 3 failures. The third is a stale allocation expectation (`NSC-991..1006`) that no longer matches the branch's committed NSC-1001..1139 contracts.

## CI exposure

- **`d1b2-core-deterministic.yml`** lists graph_delta, graph_apply_plan, graph_apply_materialize, and graph_apply plus undo.
- **`task-review-agent-deterministic.yml`** lists task_id_width (two files) and decomposition_authorization (a pwsh step with a presence check).

The last GitHub runs of both workflows were 2026-09-08 and 09-09, before `379685b`, and all succeeded. Nothing has run since. The first CI run on this stack would be red in those steps regardless of the revision-review fix.

## The paused repair

It is uncommitted in `C:\nscrev\fixture-repair`: one file, `graph_delta_smoke_test.py`, +26/-4. That file is unchanged between `027e787` and `ade5bca`.

- **Parent resources:** parent NSC-042 now owns both `logical:shared` and `logical:new-shared`, with a new resource group for `logical:new-shared` owned by NSC-042.
- **Child resources:** child 0 gets `["logical:shared"]` and child 1 gets `["logical:new-shared"]`, an exact partition.
- **Assertions:**
  - `logical:shared` stays `updated`, from NSC-010 + NSC-042 to NSC-010 + NSC-043.
  - `logical:new-shared` changes from `created` (NSC-043 + NSC-044) to `updated`, a transfer from NSC-042 to NSC-044.
  - Both groups and the overlay groups are asserted.

## Evidence: repair applied to `ade5bca`

Run by the coordinating session in a throwaway worktree, since removed.

| Suite | Result with repair |
|---|---|
| `graph_apply_plan_smoke_test.py` | PASS |
| `graph_apply_smoke_test.py` | PASS (345 s) |
| `graph_apply_materialize_smoke_test.py` | PASS (19 s) |
| `decomposition_authorization_smoke_test.py` | PASS (59 tests) |
| `local_decomposition_apply_test.py` | Ran 21 tests in 705.092s, OK |
| `graph_delta_smoke_test.py` | still FAILS: later negative cases build results with `decomposed_result(parent)` without partitioning, so the partition error (`missing=['logical:new-shared', 'logical:shared']`) fires before the failure each case means to test |
| `task_id_width_smoke_test.py` | still FAILS: the same partition error, plus the stale `NSC-991..1006` allocation expectation |
| `graph_undo_smoke_test.py` | not run |

## Why it matters for this fix

- **The D1C consumer commit changes these exact files.** It changes `_call_accounting_valid`, adds `_revision_review_shape_invalid`, and changes `local_decomposition_apply._review_run_result`. The revived 59-test D1C suite and 21-test local-apply suite are the existing regression net for those files. Several tests target exactly what changes:
  - `test_impossible_bounded_call_accounting_never_authorizes`
  - `test_producer_shaped_revise_then_pass_authorizes`
  - `test_both_producer_round_chains_still_authorize`
  - `test_no_round_may_follow_an_independent_pass`
- **Current handling is throwaway only.** The D1C developer has been told to run those suites locally with the repair applied as non-regression evidence, and not to commit the fixture.
- **Path scope.** The D1C gate is used by the TaskReviewAgent local-rehearsal and Issue-workflow path (`local_decomposition_apply.py`, `local_rehearsal.py`), which real game decompositions take in production. The AssistantControl Gauntlet does not use it: it applies through `_verify_review` and then `apply_graph_delta`.
  - Leaving the fixture broken cannot make a Gauntlet run, or a live decomposition, fail.
  - The risk is an undetected regression in the production D1C path, going unnoticed locally and in CI.

## Risks of the repair as written

1. **Coverage change on the `created` branch.** The fixture no longer exercises the planner's `created` resource-group branch: a resource that ends with more than one owner and had no existing group. Under exact partitioning, each parent resource passes to exactly one child. So `created` appears unreachable for decomposition deltas unless the existing graph already has a shared resource without a group. Codex should confirm, and either accept dropping that expectation deliberately or require a direct unit test of the branch.
2. **Incomplete.** The later negative cases in `graph_delta_smoke_test.py` need partitioned children, and `task_id_width_smoke_test.py` needs its allocation expectation brought up to date, or the committed NSC-1001..1139 contracts filtered.
3. **History.** An earlier session was paused while repairing this fixture because it was changing canonical fixture semantics. This version is limited to the resource split and its assertions, but it still changes what the fixture proves.

## Options

| Option | Effect | Cost |
|---|---|---|
| **A. Include, finished, as a separate test-only commit in this stack** | The existing D1C, local-apply and graph-apply regression nets run against the fix locally and in CI; requirement 4's "preserved" becomes demonstrable | One more commit to review; about 30-45 minutes to finish both remaining cases |
| **B. Ship it as its own fix right after** | Keeps the revision-review fix narrow | The fix merges without its existing D1C regression net in CI; preservation rests on throwaway local evidence |
| **C. Local evidence only, never committed** | Current interim approach | CI stays red in those steps indefinitely; weakest assurance |

## Questions for Codex

1. A, B or C?
2. Is the `created` resource-group branch unreachable for decomposition deltas under the exact partition rule? If it is reachable, should a dedicated test replace the fixture's old `created` expectation?
3. For `task_id_width_smoke_test.py`: update the allocation expectation to the current committed IDs, or filter the committed NSC-1001..1139 contracts out of the test?
