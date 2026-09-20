# NSC-1165 requirement 5 (author guidance): implementing agent's final report

Received 2026-09-13 at about 20:05 UTC and recorded in substance by the coordinating session. Independent verification by the coordinating session will be recorded separately.

## 1. Commit

- `13618d8ca80e19085c07f90cb3a0ae9c56627511`, parent `ade5bca50d452b276a32f31a7ad8baeb770b2404`, branch `throughput/decomposition-author-guidance`, worktree `C:\nscrev\author-guidance-fix` (clean). Not pushed.
- `Pipeline/TaskDecomposition/prompts.py` +66, `Pipeline/TaskDecomposition/review_prompts.py` +15, new `Pipeline/TaskDecomposition/tests/decomposition_evidence_guidance_smoke_test.py` +553. Stored LF, checked out CRLF; `git diff --check` clean.
- `contracts.py` untouched: validation already accepts an empty child `gdd_evidence` (test 11 proves it through schema, policy and graph-delta planning).

## 2. Guidance added

`prompts.child_evidence_and_gate_rules(context)` renders one block, "Child evidence and completion-gate rules:", between "Human-facing Unity language" and "Output parent identity". The author-correction prompt carries it verbatim, and the reviewer prompt renders the identical block before "Semantic rubric".

- **Provenance rule, always rendered.** A child's `gdd_evidence` cites only committed design evidence that supports that child's own requirements. Pipeline provenance is never GDD evidence: do not cite `provenance` or any of its fields (such as `provenance.origin`, `gauntlet_id`, `migration_id` or run identifiers), and do not cite bootstrap observations from the selected or any other supplied contract. Task notes and test files are not GDD evidence either.
- **Empty-evidence rule, only when `selected_task_gdd_evidence` is exactly `[]`.** Every child's `gdd_evidence` stays an empty array; do not fill it from the GDD, other contracts, provenance, notes, tests or any other source. Ground each child in the selected contract's own requirements and committed tests.
- **Recorded-evidence rule, only when the list is non-empty.** Keep citing it: each child cites the recorded GDD passages that support its own requirements, and no child drops evidence its requirements rely on.
- **Absent or non-list key.** Neither conditional rule renders. The context builder always emits a list, so production contexts always get one of the two.
- **Completion-gate rule, always rendered.** A gate states exactly what its named test, filter or check proves and nothing more. Read the named test when available; otherwise restate the parent gate's claim without strengthening it. A test that only checks a constant `Value` proves that value, not that the class is public or static.
- **Engineering rule, always rendered.** These rules never remove an engineering requirement. Where the parent requires a public or static class shape, exact names, namespaces, constant values or deterministic `.meta` GUIDs, keep it in the owning child's acceptance criteria even when no test proves it. Keep each listed `.meta` file on the same child as its asset, partition the parent's `exclusive_resources` exactly, and cover every parent AC/VAL/INT entry.
- **Reviewer additions.** Intro: "The decomposer instruction gives candidate authors exactly these rules. Judge the candidate by them, and follow them in any replacement candidate you author." Replacement invariant: "A replacement candidate follows the child evidence and completion-gate rules below." Three rubric items: provenance or unrecorded GDD evidence cited; gates claiming more than their tests prove; a required class shape, name, constant value or `.meta` GUID missing from the owning child's acceptance criteria. Nothing in the reviewer prompt was removed or reworded.
- On both retained NSC-1165 contexts, the new prompts with these additions removed are byte-identical to the round-1 and round-2 prompts those runs sent; the empty-evidence rule renders there. The additions are +1,746 bytes (author) and +2,385 bytes (reviewer).

## 3. Pin audit

No identity, authorization or replay check hashes or compares prompt text, so retained and future authentication are unaffected.

- `context_sha256` excludes prompts; retained contexts re-hash to their recorded values. Invocation IDs are `sha256("run_id:scope:role")`, recomputed by D1C at `decomposition_authorization.py:1112`. `candidate_sha256`, the D1C record and review-evidence hashes, graph-delta plan IDs and replay hashes take no prompt input.
- `request.json` and `task_request.json` embed the prompt verbatim, but nothing hashes them. AssistantControl `request_sha256` covers job launch files, which contain no prompt.
- `run_reviewer_replay_ab.py` records prompt bytes and SHA-256 as report data only, so new A/B hashes differ from older reports.
- The unique end marker "Return only the structured object required by the supplied output schema." is still unique and last, and a test enforces it.
- No prompt-version or prompt-hash constant or policy exists. No whole-prompt snapshot tests exist. Substring assertions still pass in `live_decomposition_smoke_test.py:216-262`, `author_correction_smoke_test.py:266-284`, `round_robin_decomposition_smoke_test.py:265-270`, `pooled_decomposition_smoke_test.py:265-306, 940-946` and `reviewer_replay_smoke_test.py:200-210`.

## 4. Failing-before and passing-after

Base: a detached `ade5bca` worktree with only the test file copied in; the runner confirmed it imported base `prompts.py` and `review_prompts.py`. No test imports a new name, so every base failure is an `AssertionError` on absent text (strong proof).

| # | Test | Base `ade5bca` | After `13618d8` |
|---|---|---|---|
| 1 | test_empty_selected_evidence_leaves_child_gdd_evidence_empty | FAIL, strong | PASS |
| 2 | test_pipeline_provenance_is_never_gdd_evidence | FAIL, strong | PASS |
| 3 | test_completion_gates_claim_only_what_their_tests_prove | FAIL, strong | PASS |
| 4 | test_engineering_requirements_stay_required | FAIL, strong | PASS |
| 5 | test_recorded_gdd_evidence_is_still_cited | FAIL, strong | PASS |
| 6 | test_rules_key_off_context_evidence_not_gauntlet_provenance | FAIL, strong | PASS |
| 7 | test_reviewer_judges_by_the_identical_rules | FAIL, strong | PASS |
| 8 | test_reviewer_strictness_is_not_loosened | PASS, guard | PASS |
| 9 | test_author_correction_prompt_carries_the_same_rules | FAIL, strong | PASS |
| 10 | test_gddrag_reviewer_context_renders_the_same_rules | FAIL, strong | PASS |
| 11 | test_empty_child_gdd_evidence_passes_deterministic_validation | PASS, guard | PASS |

Base: 2 passed, 9 failed. After: 11 passed. The fixture is one synthetic repo with the parent re-committed in four evidence/provenance shapes; test 6 shows the rule follows the evidence list, not provenance.

## 5. Suites on `13618d8`, sequential

All 11 TaskDecomposition smoke tests passed, none skipped: author_correction, context_builder, decomposition_contracts, gdd_rag_review_context, live_decomposition, review_contracts, reviewer_replay, round_invocation_id, round_robin_decomposition (each PASS), decomposition_evidence_guidance PASS (11 tests), pooled_decomposition PASS (17 tests).

Extra suites, with the Docker, `gh`, `claude` and `codex` directories removed from the child `PATH` and verified unreachable:

| Suite | Result |
|---|---|
| decomposition_session_pool_smoke_test | PASS (10 tests) |
| host_decomposition_launcher_smoke_test | PASS (20 tests) |
| provider_profiles_test.DecompositionProfileTests | Ran 2 tests, OK |
| AssistantControl.test_decomposition | Ran 26 tests in 251.264s, OK |
| AssistantControl.test_decomposition_needs_human | Ran 19 tests in 149.001s, OK |
| AssistantControl.test_background_jobs | Ran 81 tests in 691.984s, OK |
| decomposition_authorization_smoke_test | exit 1 at import: `DecompositionPolicyError: Child exclusive_resources must exactly partition the parent exclusive_resources (missing=[], extra=['logical:new-shared', 'logical:new-shared'])` |
| task_id_width_smoke_test | exit 1: 3 regressions (two partition errors; allocation NSC-1140..1155 where NSC-991..1006 is expected) |
| local_decomposition_apply_test | Ran 21 tests, FAILED (failures=1, errors=20), all the partition error |

The three failures are pre-existing, proven at base with identical signatures. Cause: `Pipeline/TaskGraph/graph_delta_smoke_test.py:116-117` gives children `logical:new-shared`, which the parent lacks; that fixture dates from `08ebfd4` (2026-08-23), while the exact-partition rule came in `379685b` (2026-09-11), an ancestor of `ade5bca`. The allocation expectation is stale because committed tasks now reach NSC-1139. No branch after `ade5bca` fixes these. Consequence: D1C's smoke suite and the local apply test give no coverage at base.

## 6. Residual risks and corrections

Risks:
- Guidance only, not deterministic enforcement: the retained round-1 candidates (one citing provenance, one with overstated gates) both passed deterministic validation.
- A verdict change is likely but unproven: both observed revise triggers map to rules the reviewer now shares, but no provider ran, and a reviewer can revise for other reasons. The bounded revision review (requirement 3) is still needed.
- The reviewer becomes stricter on real decompositions; a child dropping evidence it relies on may now draw a revise.
- The empty-evidence rule applies to every task with `[]` evidence (47 committed tasks today, all engineering guidance), matching existing practice: all 8 committed children of such parents already have `[]`.
- `basis` is unguided: a child could claim `direct_gdd` with empty evidence and no validator checks it; neither retained run did.
- Replaying old candidates makes the reviewer's intro sentence not literally true.

Corrections and clarifications for Astra:
- **Needs Astra's confirmation.** "Leave unsupported `gdd_evidence` empty" is implemented as ALL children empty when the list is `[]`, which also forbids real GDD sections (run 2 cited "Section 4 - Development Agent Ownership Invariants").
- "Never cite `provenance.origin`" is broadened to every provenance field, bootstrap observations, notes and tests, deliberately not "repository files" or "only the GDD", because three committed `human_approved_artifact` entries cite `Design/Approved/Platform/Desktop_WebGL_Publishing_Target.md`.
- Children narrow parent evidence rather than copy it (all 15 committed GDD-backed children have 0 verbatim copies), so the rule says "cites the recorded passages".
- The overstated gate was introduced by the author: NSC-1165's own VAL gates only say `proves Gauntlet1165Alpha.Value == 1165`.
- The fabricated origin came from sibling contracts: `human_approved_synthetic_gauntlet` appears only on 9 siblings; NSC-1165 is `assistant_control_local_gauntlet_replay` with no `gdd_evidence` key.

## 7. Proposed documentation (`Pipeline/TaskDecomposition/README.md`, not edited)

(a) Add to the rubric list under "Structured findings":

```
- child `gdd_evidence` that cites pipeline provenance or GDD evidence the selected contract does not record;
- child completion gates that claim more than their named tests prove;
- a required class shape, name, constant value, or deterministic `.meta` GUID missing from the owning child's acceptance criteria;
```

(b) New subsection:

```
### Child evidence and completion-gate rules

The decomposer, bounded author-correction and reviewer prompts render one identical rules block
(`TaskDecomposition.prompts.child_evidence_and_gate_rules`). The GDD-evidence rule keys only off the
context's `selected_task_gdd_evidence`, never provenance, task-ID ranges or Gauntlet membership:

- An empty list means the selected contract records no GDD evidence; every child's `gdd_evidence` stays empty.
- A non-empty list means children keep citing the recorded passages that support their own requirements.
- `provenance` and its fields, bootstrap observations, task notes and test files are never GDD evidence.
- A completion gate states only what its named test proves; a constant-value test does not prove a class is
  public or static, so shape requirements stay in acceptance criteria.
- The rules never relax `.meta` ownership, exact `exclusive_resources` partitioning or complete coverage.

These rules are guidance, not deterministic validation: validators accept an empty child `gdd_evidence` but
cannot detect an unsupported citation, so the independent reviewer judges by the same block. Prompt text is
not part of any identity (`context_sha256`, invocation IDs, candidate hashes and D1C records exclude it).
```

## 8. Nothing live touched

`C:\NSC` was read only (retained NSC-1165 run files); nothing there was executed or modified. No `docker`, `gh`, `claude` or `codex` command ran; no push, merge or GitHub post; no remote branch contains `13618d8`. The other developer's worktree was only read. The base worktree `C:\nscrev\author-guidance-base` was removed and pruned. No documentation files were edited.
