# Run 5 readiness: guidance commits 404d330 + e70b2fe4 and the combined preflight (2026-09-14)

**Status: all three pre-run checks PASS.**
- **Developer's 21 suites** on `e70b2fe4`: section 5.
- **Coordinator's independent check:** commits in section 3, failing-before in section 4, passing-after in section 6.
- **Combined Run 5 preflight:** section 7.

**Run 5:** launched on Vincent's go at 04:13 UTC, review-only (section 8). No graph application; any `needs_human` findings are preserved.

## 1. Commits under check

- **Branch and worktree:** `codex/coverage-mapping-guidance-20260913`, worktree `C:\nscrev\coverage-mapping-guidance-fix`.
- **`404d330a81db9ea8be34fd7c28cf518bb7f3c597`** (parent `3a06453`): "TaskDecomposition: name planned paths and require parent authority for .asmdef edits".
- **`e70b2fe4f0a497d240d67fe648ebfe23fc9f810b`** (parent `404d330`): "TaskDecomposition: require parent authority only for editing an existing .asmdef".
  - It narrows the coordinator's own brief wording, "editing or depending on", to "editing".
  - Reason: referencing an existing assembly from a new, named `.asmdef` does not edit the existing file.
  - Run 4's blocking finding was exactly such an edit: adding an AI Navigation reference to `NoSafeCircle.DoorPrototype.asmdef`.
- **Codex review:** both commits reviewed, no blocker.

## 2. Final guidance text at e70b2fe4

Rule 1 of `prompts.candidate_wide_rules()`, used in the author and correction prompts and rendered in the reviewer prompt:

> No resources the parent does not list: never add an `exclusive_resources` entry that the parent does not list, including a new file that a child will create. Name every proposed new file path explicitly in the owning child's acceptance criteria instead, including each new script, test, and `.asmdef` assembly definition; never leave new-file work unnamed, such as `a new test file` or `an assembly definition`. Admission checks planned paths for collisions when work starts, so every planned path must be named. Editing an existing `.asmdef` needs authority from the parent contract, for example because the parent lists it in `exclusive_resources` or in its requirements. Without that authority, do not plan that edit; if the child cannot work without it, choose `needs_human` and state the authority that is needed. The child-resource union must equal the parent's `exclusive_resources` list exactly, with no additions and no duplicates, so a parent resource that several children touch still belongs to exactly one child.

New reviewer rubric item in `review_prompts.py`:

> a new script, test, or `.asmdef` file whose path the owning child's acceptance criteria do not name, or an edit to an existing `.asmdef` that the parent contract does not authorize;

## 3. Coordinator's independent static commit check: PASS

- **Chain and identity:**
  - The chain is `3a06453` → `404d330` → `e70b2fe4`, and HEAD is `e70b2fe4`.
  - Both commits have author and committer `No Safe Circle Coverage Mapping Fix <coverage-mapping-fix@nosafecircle.invalid>`.
  - Both carry the `Co-Authored-By: Claude Opus 5` trailer.
- **Files changed** (`3a06453..e70b2fe4`), 103 insertions and 9 deletions:
  - `Pipeline/TaskDecomposition/prompts.py`: +9/-3
  - `review_prompts.py`: +2
  - `tests/candidate_wide_rules_guidance_smoke_test.py`: +92/-6
- **Guarded paths unchanged:** `policy.py`, `contracts.py`, `round_robin_decomposition.py`, `revision_review_fixtures.py`, `Pipeline/TaskGraph`, `Pipeline/AssistantControl`, `Pipeline/TaskReviewAgent`.
- **Hygiene:**
  - `git diff --check` is clean.
  - EOL is `i/lf w/crlf`, matching the repository convention.
  - The worktree is clean.
- **Retired phrases:** none remain in either prompt module at HEAD ("reservation before execution", "depending on an existing", "dependency on an existing", "edit to or dependency").

## 4. Failing-before (coordinator runs, final test file from e70b2fe4, detached worktrees since removed)

| Code under the final test file | Result |
|---|---|
| `3a06453` (before both commits) | FAIL, 4 of 5 tests. The decomposer, correction and reviewer prompts differ from the pinned rules. The rule-1 test reports "the old reservation wording is still present". `test_validator_error_texts_and_precedence_are_unchanged` PASS. |
| `404d330` (before the narrowing) | FAIL, 4 of 5 tests. The three prompt pins fail, and the rule-1 test reports "only editing an existing `.asmdef` needs parent authority: 'depending on an existing'". The validator pin PASS. |
| `e70b2fe4` | See section 6. |

## 5. Developer's full 21-suite run on e70b2fe4: PASS

**Setup:** the run recorded HEAD as `e70b2fe4` with a clean tree. All 21 suites exited 0, and no log contains FAIL, ERROR or Traceback. Logs are in `C:\nscrev\test-temp\asm2-suite-logs`.

| # | Suite | Result |
|---|---|---|
| 1 | candidate_wide_rules_guidance | PASS (5) |
| 2 | coverage_mapping_guidance | PASS (13) |
| 3 | round_robin_decomposition | PASS |
| 4 | author_correction | PASS |
| 5 | live_decomposition | PASS |
| 6 | revision_review | PASS (21 cases) |
| 7 | child_gdd_evidence | PASS (17) |
| 8 | decomposition_evidence_guidance | PASS (11) |
| 9 | decomposition_contracts | PASS |
| 10 | review_contracts | PASS |
| 11 | pooled_decomposition | PASS (17) |
| 12 | revision_review_fixtures | PASS (12) |
| 13 | round_invocation_id | PASS |
| 14 | context_builder | PASS |
| 15 | reviewer_replay | PASS |
| 16 | gdd_rag_review_context | PASS |
| 17 | AssistantControl test_decomposition | Ran 62, OK |
| 18 | AssistantControl test_decomposition_whole_stack | Ran 16, OK |
| 19 | AssistantControl test_decomposition_revision_review_integration | Ran 7, OK |
| 20 | TaskReviewAgent decomposition_authorization_smoke_test | PASS (59) |
| 21 | TaskGraph graph_delta_smoke_test | PASS |

**Hygiene the developer reported:**
- **No writes under `C:\NSC`:** the default temp dirs still carry their pre-session timestamps.
- **Temp overrides:** the empty override directories were removed.
- **No providers or Docker** were used.
- **No pushes:** the branch has no upstream.

**README:** no change needed; the only "reserv" matches are unrelated.

**Residual risks the developer reported:**
1. **Guidance only.** No deterministic check that planned paths are named or that `.asmdef` edits are authorized. Admission's collision check can only catch named paths.
2. **Authority may be read loosely.** "Lists it … in its requirements" could be over-read as authority.
3. **Referencing is permitted only by omission.** The prompt doesn't say outright that referencing an existing assembly from a new, named `.asmdef` is allowed.
4. **Reviewers get stricter.** More `needs_human` outcomes are likely, which is intended.
5. **Not in CI.** The suites are local only.

## 6. Coordinator passing-after suites on e70b2fe4: PASS

The coordinator ran these separately, after the developer's run finished, using `C:\nscrev\final-verify\nsp\verify_nsp.sh`. Output is in `verify_nsp.out` and the per-suite logs in `C:\nscrev\final-verify\nsp\`.

| Suite | Result |
|---|---|
| candidate_wide_rules_guidance (final test file) | PASS (5 tests) |
| coverage_mapping_guidance | PASS (13 tests) |
| decomposition_contracts | PASS |
| round_robin_decomposition | PASS |
| author_correction | PASS |
| revision_review | PASS (21 cases, 132 s) |
| TaskGraph graph_delta | PASS |
| AssistantControl test_decomposition_whole_stack | Ran 16, OK (174 s) |

- **Failing-before repeated:** the same run reproduced section 4's result at `3a06453`: 4 of 5 tests fail and the validator pin passes.
- **Phrase grep:** the script searched all of `Pipeline/TaskDecomposition` for "reservation before execution". It appears only in the test file itself, as the `OLD_RESERVATION_PHRASE` constant and in a comment. Neither prompt module contains it (section 3).
- **Clean up:** the guidance worktree stayed clean, and the detached verification worktrees were removed.

## 7. Run 5 research tree and zero-cost preflight: PASS

- **Combined commit:** `f761c05bc29172dd8e6ff825ffefec8db9ba9d24`.
  - Code: `e70b2fe4`.
  - Game: `3a565100697010e444e052dc008620509c0c0113`, canonical local main with NSC-025 revision 5.
- **Location:**
  - Branch: `realdecomp/run5-e70b2fe4f0a4-3a56510`.
  - Standalone clone: `C:\nscrev\realdecomp-r5-src` (clean).
  - Checkout root: `C:\nscrev\realdecomp-Checkouts-r5` (no decomposition records).
- **Split:**
  - Game-owned paths equal `3a56510`; every other path equals `e70b2fe4`.
  - Only `Pipeline/TaskGraph/TASKCONTROL_CURRENT.json` was removed, and no code-stack edits to game-owned paths were overwritten.
  - Separately, the tree's `Packages/` and `ProjectSettings/` match canonical, which has `com.unity.ai.navigation` 2.0.14.
- **Graph:** 87 tasks and 84 resource groups load.
- **NSC-025:** context build ok, run gate ok, decomposition preflight ok. In the tree:
  - `contract_revision` 5.
  - Completion gates: `VAL-002` only. `VAL-001` was transferred to NSC-071 by `27e1ae9`.
  - Integration obligation: `INT-001`, NSC-071's Bone Archive navigation proof on committed room geometry.
  - `exclusive_resources`: `logical:gameplay-walkability-surface`, `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`, `repo-file:Assets/NoSafeCircle/DoorPrototype/NoSafeCircle.DoorPrototype.asmdef`, `unity-scene:Assets/Scenes/DoorPrototype.unity`.
- **Other tasks:** NSC-014, NSC-015 and NSC-033 pass the same checks. NSC-035 is refused as already decomposed (expected).
- **Zero-spend smoke:**
  - `decompose` without the spend flag is refused.
  - No files were created in the checkout root, and the source is clean after the probe.
- **Guidance present:** the tree's `prompts.py` and `review_prompts.py` contain the new text from section 2.

## 8. Run 5: launched on Vincent's "start 25"

- **Scope:** one bounded, review-only NSC-025 run with providers `claude,codex`.
- **Launch:**
  - Started at 04:13:04 UTC as run `run5-nsc-025-f761c05bc291`, launcher PID 32660.
  - Source `C:\nscrev\realdecomp-r5-src` at HEAD `f761c05bc29172dd8e6ff825ffefec8db9ba9d24`, checked before launch; the tree was clean.
  - Checkout root `C:\nscrev\realdecomp-Checkouts-r5`.
  - Container `nosafecircle-round-robin-decompose-run-e18cd4e4140d` came up.
  - Read-only viewer: http://localhost:8825.
- **First launch attempt refused, no spend:** the launch script's own `C:\NSC` guard used the pattern `C:\NSC*`, which also matched `C:\nscrev`. The guard now compares the full path against `C:\NSC\*`, and the second attempt started.
- **Timing:** launched while the coordinator's passing-after rerun (section 6) was still running, in a separate worktree. The developer's full 21-suite result (section 5) and the preflight (section 7) had already passed.
- **Checks when reviewing the proposal, per Codex:**
  - **Existing Editor and Tests `.asmdef` files are not claimed by NSC-025.** Check them separately:
    - `Assets/NoSafeCircle/DoorPrototype/Editor/NoSafeCircle.DoorPrototype.Editor.asmdef`
    - `Assets/NoSafeCircle/DoorPrototype/Tests/NoSafeCircle.DoorPrototype.Tests.asmdef`
    - `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/NoSafeCircle.DoorPrototype.Tests.Editor.asmdef`
  - **New file paths:** every new script, test or `.asmdef` path must be named in its owning child's acceptance criteria.
- **Outcome handling:** preserve any `needs_human` findings; never apply the proposal.
- **Outcome:** `review_ready` at 04:30:37 UTC after 3 provider calls, with no rejection reasons. It was not applied. See `C:\nscrev\reports\run5-nsc-025-result-20260914.md`.

## 9. Not included

- **`total_provider_calls` reporting:** separate branch `codex/total-provider-calls-20260914`, still in development and not in the Run 5 tree.
