CONTINUE TRIAL.

No reviewed finding is a **STOP THE TRIAL** defect for the supplied live-run topology. Exact commit **027e7879715633119cfc1b65179882d91843a361: GO**. Overall branch head **027e787: GO for this live Gauntlet trial**, with the seven findings below classified **FIX AFTER**. The two earlier P2 findings remain real, but neither can make the current single-controller trial perform an unsafe or unauthorized action through normal producer output.

| Commit | Verdict for this live trial |
| --- | --- |
| 573302bcbf02597ee5fd3db3729c9ed5d2b72e8a | **GO** — bounded correction production is fail-closed and validator-agnostic. |
| 9521f4e0e90c338e1d277879c23845ffec8bd51b | **GO / FIX AFTER** — its verifier accepts malformed histories that producer 573302b cannot emit. |
| bdc9a9236db4690cbc13506a0f2824a089a498f1 | **GO / FIX AFTER** — a pre-mutation apply refusal can cause retry starvation, but it stops the controller without mutating Source. |
| 027e7879715633119cfc1b65179882d91843a361 | **GO** — the two tightenings match producer output and the provider refusal test covers an existing guard. |

The operator decision is based only on the reviewed code and the supplied live-trial topology. Nothing under `C:\NSC` was accessed.

## Fourth-commit assessment

Commit **027e787** has the stated parent, **bdc9a9236db4690cbc13506a0f2824a089a498f1**, and changes only `Pipeline/AssistantControl/decomposition.py` and `Pipeline/AssistantControl/test_decomposition.py`.

All three claims hold:

1. The three-entry shape now requires `type(author_corrections_used) is int` and value `1`. The two-entry shape accepts a missing field, explicit `None`, or exact integer `0`; it rejects both JSON Boolean values. Existing positive tests exercise the missing and integer-zero cases, and the new test exercises both Booleans.
2. The retained rejected first round must carry a non-empty list whose elements are non-empty strings. Missing, `None`, empty list, non-list, and empty-string-containing forms are refused.
3. A correction from another requested provider was already rejected by the shared author check at `Pipeline/AssistantControl/decomposition.py:247`. The new test makes that guard explicit.

Neither tightening rejects a legitimate shape from producer commit **573302b**. The producer initializes `author_corrections_used = 0`, changes it to exact integer `1` only on the eligible correction path, and always publishes that integer in the final run result. Its ordinary two-entry PASS therefore carries `0`. For a corrected PASS, eligibility requires `round_rejections == [initial_validation_failure]`; `initial_validation_failure` is a non-empty deterministic-validation string, and `_round_summary` receives that list as the rejected first round’s `rejection_reasons`. The correction itself then publishes its own separate rejection list.

The branch-wide reader audit found only one runtime reader of `author_corrections_used`: AssistantControl’s `_verify_review`. The producer and tests write/assert it, and the README documents it. `provider_budget.observe_decomposition_result` does not read the count; it uses each entry’s `correction_of_round` to select `rounds/NN-correction` and keeps ordinary ordinals unchanged. The host launcher passes the run result into `_verify_review` and has no competing interpretation. The AssistantControl and legacy viewers ignore the count. The upstream authorization reader also does not use the count and retains its separate corrected-round incompatibility described in finding 3. There is therefore no new count-reader inconsistency.

The refusal messages are fail-closed but not field-specific. Invalid three-entry counts and malformed first-round rejection lists both report “does not prove exactly one bounded author correction”; a wrong correction provider reports the broader “does not prove the exact independent author/reviewer pass.” That is a diagnostic weakness recorded as finding 7, not an acceptance or trial-safety defect.

The failing-before claims for **bdc9a92** are supported directly by its parent code and the fourth-commit diff: `corrections == 1` accepts `True`; `corrections not in (0, None)` treats `False` as zero; and no first-round rejection-list check exists. The wrong-provider case already fails through the shared author-provider check. I did not switch the new detached worktree to the parent or rerun the parent suite.

## Findings

### 1. P2 — FIX AFTER — Corrected-run verification admits disallowed initial histories and contradictory ordinals

Commit: **9521f4e**, still present at **027e787**. Locations: `Pipeline/AssistantControl/decomposition.py:221`, `:250`, and `:264`.

**Trigger:** A malformed or externally altered run result presents an otherwise matching corrected PASS but gives the rejected first round a Source-change/read-only rejection, missing or contradictory `round_number` values, or Boolean `correction_of_round: true`.

**Present live-run reachability:** Not reachable from normal output of reviewed producer **573302b**. Its correction eligibility excludes Source movement, read-only violations, provider failure, and additional rejection reasons, and its summaries emit deterministic integer ordinals. Reaching this flaw during the supplied live trial requires malformed, spliced, or externally modified artifacts. No such condition is stated, and live state was not inspected.

**Impact:** If such evidence were introduced, AssistantControl could authenticate and apply a candidate whose retained history could not have been produced by the claimed correction circuit. Candidate, parent, Source ancestry, graph-plan, and reviewer hashes still have to match, which limits the defect to proof-chain integrity rather than arbitrary graph content.

A narrow probe at exact **027e787** confirmed all four malformed variants are accepted:

```text
DISALLOWED_SOURCE_HISTORY: ACCEPTED
DISALLOWED_READ_ONLY_HISTORY: ACCEPTED
CONTRADICTORY_ORDINALS: ACCEPTED
BOOLEAN_CORRECTION_REFERENCE: ACCEPTED
```

**Smallest repair:** Require the rejected first round to contain exactly the producer’s single initial deterministic-validation rejection and no Source/read-only failure; require exact integer ordinals `1, 1, 2`; require exact integer `correction_of_round: 1`; require empty correction/reviewer rejection lists; and bind the sole reviewer history entry to round 2 and the reviewed candidate. Use producer metadata prefixes without encoding any Gauntlet-specific validator rule.

**Needed evidence:** Failing-before tests for Source-change and read-only initial histories, missing/wrong ordinals, Boolean correction references, correction/reviewer rejection lists, and mismatched reviewer-history ordinal. Preserve a producer-generated corrected PASS as the positive fixture.

**Trial classification:** **FIX AFTER**. The reviewed producer cannot emit the trigger, and ordinary live execution does not synthesize or reinterpret these fields.

### 2. P2 — FIX AFTER — A pre-mutation apply refusal remains pending and blocks later decompositions after restart

Commit: **bdc9a92**, unchanged at **027e787**. Locations: `Pipeline/AssistantControl/graph_controller.py:739` and `:746`; supporting paths `Pipeline/AssistantControl/decomposition.py:479` and `Pipeline/AssistantControl/graph_controller.py:1766`.

**Trigger:** Parent A has a retained `review_ready` proposal, parent B is ready to decompose, and A’s application raises before Source mutation because freshness, artifact, branch, or TaskGraph verification refuses.

**Present live-run reachability:** The refusal path is executable, but normal single-controller scheduling removes the known Run-3 race: Source-moving work is held while a proposal runs, then the proposal is harvested before application. A refusal can still occur if another actor changes relevant state or retained evidence is invalid. Under the supplied one-controller ownership, neither condition is reported. If it occurs, the controller exits blocked before launching B.

**Impact:** A’s decomposition record stays `review_ready`. On restart, A is selected for `apply_decomposition` again and B remains held as `decomposition_apply_pending`. This is a liveness and repeated-retry defect. The observed refusal does not mutate Source or launch another provider.

The narrow restart probe at exact **027e787** produced:

```text
APPLY_REFUSAL: fixture pre-mutation apply refusal
RETAINED_STATUS: review_ready
RESTART_ACTION: apply_decomposition
LATER_DECOMPOSITION: decompose held=decomposition_apply_pending
```

**Smallest repair:** For a proven pre-mutation refusal, persist a task-local terminal application failure with the exact run and error, block only that parent, and allow unrelated planning to continue. A failure after possible Source movement needs a separate reconciliation state and must not be treated as a safe pre-mutation refusal.

**Needed evidence:** A failing-before loop test with proposal A and ready parent B that forces a freshness refusal, restarts, proves Source unchanged, proves A is durably failed without another apply attempt, and proves B becomes eligible against current Source.

**Trial classification:** **FIX AFTER**. It is fail-closed and cannot perform an unsafe action; at worst it stops this run and requires operator recovery.

### 3. P2 — FIX AFTER — Upstream human authorization rejects corrected runs

Producer commit: **573302b**; present through **027e787**. Locations: `Pipeline/TaskReviewAgent/decomposition_authorization.py:836` and `:925`.

**Trigger:** A valid corrected PASS is sent through the upstream TaskReviewAgent human-authorization path.

**Present live-run reachability:** Unreachable in the supplied AssistantControl Gauntlet apply path. It matters for a later upstream port.

**Impact:** A valid corrected result has three round entries and `calls_used: 2`; upstream accounting requires `len(rounds) == calls_used`, and its positional chain validator requires the first round to be `candidate_valid` with no rejection. It refuses the run as bounded-call-accounting/round-sequence inconsistency.

**Smallest repair:** Teach upstream accounting and chain validation the same single optional correction while preserving ordinary reviewer ordinals, invocation/artifact bindings, and independent approval.

**Needed evidence:** Pass a real producer-generated corrected PASS through the upstream authorization binder and require exact success; malformed correction histories must remain refused.

**Trial classification:** **FIX AFTER**. The live Gauntlet does not invoke this reader.

### 4. P3 — FIX AFTER — Legacy Gauntlet viewer combines correction timing with original-author usage

Introduced by **573302b**. Producer location: `Pipeline/TaskDecomposition/round_robin_decomposition.py:1177`. Reader locations: `Pipeline/TaskReviewAgent/GauntletView/server.py:1778`, `:1791`, and `:1811`.

**Trigger:** A correction emits a second set of progress events using round number 1.

**Present live-run reachability:** Reachable if the live proposal uses a correction and this legacy agent projection is used. The AssistantControl task projection reviewed here does not depend on this result for action authority.

**Impact:** The viewer keys progress by `round_number`, overwrites round 1 timing with correction timing, then reads `rounds/01/round_result.json`. It can display correction duration with original-author token/model/cost data and omit a separate correction row. This is display attribution only.

**Smallest repair:** Key displayed calls by invocation identity or round plus correction marker and resolve correction artifacts from `01-correction`.

**Needed evidence:** A viewer test with distinct author, correction, and reviewer timing/usage artifacts that requires three correctly attributed rows.

**Trial classification:** **FIX AFTER**. It cannot select, authorize, apply, integrate, or move Source.

### 5. P3 — FIX AFTER — Held reasons are absent from the AssistantControl viewer projection

Introduced by **bdc9a92**. Locations: `Pipeline/AssistantControl/graph_controller.py:926`; affected reader `Pipeline/AssistantControl/viewer.py:349` and `:379`.

**Trigger:** A preflight or running plan contains a held integration or decomposition.

**Present live-run reachability:** Likely during ordinary proposal/integration overlap in this trial, but the hold itself remains enforced by the controller.

**Impact:** `graph-plan` contains the exact blocking reason/task/job, while the viewer can display the action merely as ready. The operator loses useful waiting context; action selection is unaffected.

**Smallest repair:** Retain current hold facts in controller state and project them into the affected task’s waiting reason, while preserving Source/scope verification.

**Needed evidence:** Viewer tests that project held integrate/decompose actions with exact blocker identity and clear the explanation when the hold disappears.

**Trial classification:** **FIX AFTER**. This is observability only.

### 6. P3 — FIX AFTER — Hold journaling is scoped to controller-object lifetime instead of invocation

Introduced by **bdc9a92**. Locations: `Pipeline/AssistantControl/graph_controller.py:285` and `:1162`.

**Trigger:** The same `GraphController` object runs a second bounded invocation while an identical hold persists, or a null-job blocker changes task identity without changing reason.

**Present live-run reachability:** The supplied trial describes one owned controller. Normal CLI invocations construct fresh controller objects, so the first trigger is not expected in that run. A fresh-process restart does journal the hold once.

**Impact:** The second invocation can lack its own `source_lane_held` event. The signature also omits `blocking_task_id`, so one pending-apply blocker can replace another without a new event. Scheduling remains enforced.

**Smallest repair:** Clear the in-memory hold cache when a new invocation is acquired and include blocking task identity in the signature.

**Needed evidence:** Reuse one controller object across two invocations with an unchanged hold and require one event per invocation; separately replace a null-job blocker and require a new event.

**Trial classification:** **FIX AFTER**. It affects audit completeness, not action gating.

### 7. P3 — FIX AFTER — Fourth-commit refusal messages group distinct malformed fields

Introduced/retained by **027e787**. Locations: `Pipeline/AssistantControl/decomposition.py:234` and `:263`.

**Trigger:** A malformed three-entry count, malformed initial rejection list, or wrong correction provider is refused.

**Present live-run reachability:** Only when run evidence is malformed. Every case fails closed before application.

**Impact:** Logs do not identify whether the count, first-round rejection evidence, or shared author/provider shape caused refusal. Recovery takes more inspection, but no invalid shape is accepted because of the message.

**Smallest repair:** Split the grouped predicates into field-specific checks and messages without weakening the aggregate verifier.

**Needed evidence:** Targeted refusal tests asserting a distinct message for Boolean count, missing/empty rejection list, wrong provider, and wrong correction status.

**Trial classification:** **FIX AFTER**. Diagnostic precision does not affect ownership or Source safety.

## Supporting attack-surface conclusions

- Correction eligibility remains limited to round 1, no candidate, one exact deterministic-validation failure, zero prior corrections, and no pooled session. Provider failure, partial/failed result, read-only claims, and Source changes prevent eligibility.
- The correction repeats invocation-identity, provider-status, read-only, Source-revalidation, and deterministic-candidate checks before review. Its invocation ID and `01-correction` directory are distinct and published with no-overwrite helpers.
- The correction prompt carries exact validator text, rejected output, original context, and descriptive observations. Its reason/children consistency sentence does not restate the Gauntlet exclusive-resource partition rule.
- Deferred first-round rejection text is restored for all non-`review_ready` outcomes. Inspected consumers either require `review_ready` with empty run-level rejections or retain those strings as diagnostics.
- The apply verifier still binds run, task, Source, contract, candidate digest, graph plan, provider order, fixed `max_calls: 2`, fixed `calls_used: 2`, and independent reviewer PASS.
- The scheduler ordering remains narrow. Completed, failed, died, and cancelled jobs are harvested before replanning. An unreadable index refuses startup. An unverifiable job cannot be safely released. The bounded wait observes active jobs and stop requests.
- A proposal’s own apply is no longer held after its job is harvested. Pending apply prevents another proposal from launching, and an already-ready Source move precedes a new proposal.
- `local_decomposition_apply.py` remains pooled-only; corrections are excluded from pooled runs.

## Commands and exact results

The original three-commit review ran these focused suites in its detached worktree:

| Command | Exact result |
| --- | --- |
| `python Pipeline/TaskDecomposition/tests/author_correction_smoke_test.py` | `author_correction_smoke_test: PASS` |
| `python Pipeline/TaskDecomposition/tests/round_robin_decomposition_smoke_test.py` | `round_robin_decomposition_smoke_test: PASS` |
| `python Pipeline/TaskDecomposition/tests/round_invocation_id_smoke_test.py` | `round_invocation_id_smoke_test: PASS` |
| `python Pipeline/TaskDecomposition/tests/pooled_decomposition_smoke_test.py` | `pooled decomposition tests: PASS (17 tests)` |
| `python Pipeline/TaskDecomposition/tests/decomposition_contracts_smoke_test.py` | `decomposition_contracts_smoke_test: PASS` |
| `python -m unittest Pipeline.AssistantControl.test_decomposition` at bdc9a92 | `Ran 11 tests in 35.779s` / `OK` |
| `python -m unittest Pipeline.AssistantControl.test_background_jobs.BackgroundJobLoopTests` | `Ran 28 tests in 210.948s` / `OK` |
| `python -m unittest Pipeline.AssistantControl.test_graph_controller` | `Ran 33 tests in 100.591s` / `OK` |
| `python -m unittest Pipeline.AssistantControl.test_decomposition` at 027e787 during the original review | `Ran 14 tests in 34.041s` / `OK` |

The original sandboxed attempts failed only because Windows TEMP fixture creation was denied; approved reruns above passed. Their exact failed summaries were:

```text
author_correction_smoke_test: PermissionError: [WinError 5] Access is denied; no PASS
Ran 11 tests in 0.030s
FAILED (errors=22)
Ran 28 tests in 0.066s
FAILED (errors=56)
Ran 33 tests in 0.069s
FAILED (errors=66)
```

This fourth-commit addendum used a new detached worktree at exact **027e787** and ran:

```text
python -m unittest Pipeline.AssistantControl.test_decomposition
..............
----------------------------------------------------------------------
Ran 14 tests in 56.996s

OK
```

It also ran one inline `python -c` probe using only existing unittest fixtures to test four malformed histories and one pre-mutation apply-refusal restart. Exact output:

```text
DISALLOWED_SOURCE_HISTORY: ACCEPTED
DISALLOWED_READ_ONLY_HISTORY: ACCEPTED
CONTRADICTORY_ORDINALS: ACCEPTED
BOOLEAN_CORRECTION_REFERENCE: ACCEPTED
APPLY_REFUSAL: fixture pre-mutation apply refusal
RETAINED_STATUS: review_ready
RESTART_ACTION: apply_decomposition
LATER_DECOMPOSITION: decompose held=decomposition_apply_pending
```

No additional broad suite was run. `git diff --check HEAD^ HEAD` exited 0 with no output.

## Detached-worktree cleanup

The addendum worktree was created with:

```text
git -C C:\nscrev\throughput worktree add --detach C:\nscrev\astra-trial-027e787 027e7879715633119cfc1b65179882d91843a361
```

Before removal, its resolved absolute path, exact HEAD, detached state, and clean tracked/untracked status were verified:

```text
VERIFIED_REVIEW_PATH=C:\nscrev\astra-trial-027e787
VERIFIED_REVIEW_HEAD=027e7879715633119cfc1b65179882d91843a361
VERIFIED_REVIEW_TREE=CLEAN
```

It was removed and pruned with:

```text
git -C C:\nscrev\throughput worktree remove --force C:\nscrev\astra-trial-027e787
git -C C:\nscrev\throughput worktree prune
```

Final verification returned `REVIEW_PATH_EXISTS=False`. The active `C:\nscrev\throughput` worktree remained on `throughput/background-decomposition`; the active `C:\nscrev\trial` worktree remained on `throughput/gauntlet-trial`. No branch was moved.

No implementation file was edited. No Docker, provider, GitHub, push, merge, or Issue action occurred. The live-trial tree under `C:\NSC` was not accessed.
