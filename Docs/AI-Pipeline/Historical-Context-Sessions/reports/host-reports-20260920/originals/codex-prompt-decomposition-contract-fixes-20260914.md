# Codex: contract fixes so NSC-014, NSC-015 and NSC-033 can be decomposed, plus the NSC-025 handoff (2026-09-14)

> **Update (about 05:00 UTC, 2026-09-14): read this first.**
> - **Part B is superseded.** Vincent approved the exact corrected plan `GDP-07fb2284b1c4d47e036b49bed0d824f525b4e9c3626ae5afe1d30a3e3ef77824`, which Astra reviewed (`C:\nscrev\reports\run5-nsc025-corrected-preview-review-20260914.md`). Apply that plan, not the original Run 5 plan `GDP-320675f3…`.
> - **Proposed follow-up NSC-089 contract revision** (reviewed and validated like any contract edit): prefer a runtime NavMesh rebuild. If baked NavMesh data is saved with the scene, name the generated NavMesh `.asset` path.
> - **Research code for the NSC-014, NSC-015 and NSC-033 reruns** is now `c6f7981a` (production-path gate rule), not `e70b2fe4`. The coordinator verified it: failing-before and passing-after on six decomposition suites.
> - **Order:** apply NSC-025 first, then make the contract fixes in part A.
> - **No proof re-run:** Vincent chose not to spend a separate NSC-025 research run to test the new rule.

This prompt is self-contained and meant for a fresh Codex session. It was prepared by Claude (the decomposition coordinator) for Vincent.

**Goal (Vincent):**
1. Decompose every task that still needs decomposition.
2. Codex then merges the approved results into canonical main.

We stopped the provider runs for NSC-014, NSC-015 and NSC-033 because they have known contract blockers, and usage is limited. Please fix those contracts first.

**Constraints:**
- Edit canonical task contracts only for the tasks named below, using the same provenance and contract-transfer style as `27e1ae9ec`.
- Run graph validation after the edits, and get Astra's independent review before any research rerun.
- Do not modify research artifacts under `C:\nscrev`.
- Mark each statement in your reply as verified in canonical, or as reasoned.

## 0. Where things stand

- **Canonical main:** `3a565100697010e444e052dc008620509c0c0113` (NSC-025 revision 5). Graph: 87 tasks.
- **Pipeline code for research runs:** `e70b2fe4` on `codex/coverage-mapping-guidance-20260913`. It adds candidate-wide rules and the rule to name new paths; editing an existing `.asmdef` needs parent authority. Codex and Astra reviewed it.
- **NSC-025:** the fresh proposal is `review_ready` (Run 5). See part B.
- **Eligible decomposition parents on main** (active, concrete, `needs_execution_decomposition`): NSC-014, NSC-015 and NSC-033. NSC-025 is done as research.
- **Run 5 attempts for NSC-014, NSC-015 and NSC-033:** started at 04:40 UTC, then stopped at Vincent's request. Each ran only part of round 1's Claude author call: no candidate, no Codex call. Records are archived as `*.decomposition.json.stopped-by-operator-20260914T0443Z` under `C:\nscrev\realdecomp-Checkouts-r5\.assistant-control\`.
- **Astra's binding decisions** are in `C:\nscrev\reports\codex-astra-real-task-decomposition-policy-20260914.md`, section 9A:
  - **F3:** keep C1 now. C1 is exact partition: each parent exclusive resource goes to exactly one child. Design C3 later, where every child that mutates a shared surface keeps its lock and follows explicit acyclic ordering. C2 works only where one child really makes all the shared-file edits.
  - **F4:** D1, meaning explicit contract edits in canonical, owned by Codex and Vincent.
  - **Rerun order:** NSC-014 after the D1 transfer (done in `27e1ae9`), then NSC-015 after F3 is settled, then NSC-033 last, after its contract and upstream owners are settled.

## A. Contract fixes

### A1. NSC-033: Floor Run/Restart Persistent-Systems Closure (rev 4). Astra's D1 edit is specified but NOT applied

**Evidence:** Run 3, `run3-nsc-033-616ca98`, ended `needs_human` after 2 calls. Codex's round-2 blocking findings:
- **`round-02-unowned-shared-orchestrator-edits`:** the second child edits the Floor Run/Restart orchestrator, `DoorPrototypeSceneBuilder.cs` and `DoorPrototype.unity` without owning any of them. Exact partition gives each parent resource to exactly one child.
- **`round-02-missing-door-feedback-reset`:** the reset inventory omits `DoorInteractionFeedback`.
  - NSC-041 AC-004 requires hover, selection and approach feedback to return to the floor-initial or open state on cancel, interrupt, complete, suspend and reset.
  - `ResetFeedback` exists for use alongside `DoorInteractable.ResetDoor` and `PlayerInteractionController.ResetInteraction`.

**Current main (verified):**
- `depends_on` has 18 tasks, and NSC-041 is not among them.
- No mention of `DoorInteractionFeedback` or `ResetFeedback`.
- `exclusive_resources`: `logical:floor-run-restart-orchestrator`, `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`, `unity-scene:Assets/Scenes/DoorPrototype.unity`.

**Requested edit (Astra D1):**
1. Add NSC-041 to `depends_on`.
2. Include `DoorInteractionFeedback.ResetFeedback` in the reset inventory.
3. Extend restart validation to hover, selection, approach and opening feedback.
4. State in the contract that one integration child owns all shared orchestrator, builder and scene edits (C1).

**Also check:**
- NSC-025's pending proposal (part B) assigns `DoorPrototypeSceneBuilder.cs` and `DoorPrototype.unity` to its NavMesh child. NSC-033 reaches NSC-025 through NSC-014. Confirm the ordering and builder ownership still hold.
- Confirm NSC-033's other upstream owners are settled, as Astra requires before its rerun.

### A2. NSC-015: Melee Enemy Archetype (rev 1). Blocked on F3, the shared locomotion lock

**Evidence:** Run 3, `run3-nsc-015-616ca98`, was rejected after 3 calls.
- **Round 2 (Codex, `revise`), resolved by Codex's revised candidate:**
  - `round-02-stationary-prefab-ownership-conflict`: NSC-077 already owns the Melee Enemy presentation prefab, sprite import and sorting.
  - `round-02-missing-player-health-dependency`: the attack child uses `PlayerHealth.TakeDamage`, which NSC-004 owns. The analogous NSC-054 depends on NSC-004.
  - `round-02-restart-proof-not-local`: orchestrator wiring and integrated restart proof belong to NSC-033.
- **Round 3 (Claude revision review, `revise`), `round-03-melee-lock-parity-gap`:**
  - The movement, attack-execution and prefab-wiring children all need `logical:enemy-locomotion-behavior-surface`.
  - Reason given: parity with the Ranged Enemy decomposition, where NSC-053, NSC-054 and NSC-055 all hold that lock.
  - Exact partition then rejected the candidate: `extra=['logical:enemy-locomotion-behavior-surface', 'logical:enemy-locomotion-behavior-surface']`.

**Current main (verified):**
- `exclusive_resources` is only `logical:enemy-locomotion-behavior-surface`.
- `depends_on`: NSC-014, NSC-012, NSC-011, NSC-026. Neither NSC-004 nor NSC-077 is listed.
- Lock holders: NSC-013, NSC-014, NSC-015 and NSC-017 (children of NSC-010), plus NSC-053, NSC-054 and NSC-055 (children of NSC-016).

**Decision and edit needed under C1.** Please choose one and edit the contract to match:
- **(a) One mutating owner.** The contract states that only the movement child mutates the enemy locomotion behavior surface. Attack execution and prefab wiring consume it through a dependency on the movement child and hold no lock.
  - This is valid only if they truly make no locomotion edits.
  - In the same edit, add the dependencies Run 3 showed are required (NSC-004; NSC-077 for presentation-prefab ownership).
  - Word the restart gate so the component proves only its own reset method, and leave orchestrator wiring to NSC-033.
- **(b) Distinct resources.** If more than one child must mutate locomotion, split the parent resource into distinct contract resources that exact partition can assign one per child, and update `RESOURCE_GROUPS.yaml` as needed.
- **(c) No decomposition yet.** Keep NSC-015 as a single dispatch unit until C3 exists.

**Please also say** whether the NSC-053/054/055 precedent (all three children holding the lock) is correct canonical practice, since the reviewer treated it as the parity reference.

### A3. NSC-014: Enemy Detection, Pursuit, and Search/Reacquisition Foundation (rev 2). D1 transfer done; likely hits F3

**Evidence:** Run 3, `run3-nsc-014-616ca98`, ended `needs_human` after 3 calls.
- **`round-02-bone-archive-gate-not-local`:** fixed by `27e1ae9ec`, which moved VAL-002 to NSC-071 INT-001.
- **Round 1:** duplicate `dependent_task_id` values. The candidate-wide guidance (one rewrite per dependent) now covers this.
- **`round-02-overbroad-dependent-rewrites`:** a semantic candidate defect, not a contract defect.
  - NSC-053 needs only the current player target for keep-distance movement.
  - NSC-054 does not establish an active-target firing gate.
  - NSC-017 requires an enemy that is actively tracking or pursuing.

**Current main (verified):**
- `exclusive_resources` is only `logical:enemy-locomotion-behavior-surface`.
- `depends_on`: NSC-025.
- 8 ACs, gates VAL-001 and VAL-003, and INT-001 (to NSC-071).

**Request:**
1. **Locomotion owner:** state whether NSC-014 needs the same contract clarification you choose for NSC-015 before a run. Any split into detection, pursuit and search children that touch locomotion will raise the same parity question.
2. **Optional:** clarify in NSC-053, NSC-054 and NSC-017 which NSC-014 capability each consumes, so inbound rewrites are unambiguous.

## B. NSC-025: `review_ready` proposal to merge into main (after Astra's review)

**Where to look:**
- **Report:** `C:\nscrev\reports\run5-nsc-025-result-20260914.md`.
- **Artifacts:** `C:\nscrev\realdecomp-Checkouts-r5\.assistant-control\decomposition-runs\run5-nsc-025-f761c05bc291\`. The accepted candidate is `rounds\02\candidate.json`.

**Identity:**
- Candidate sha256 `520f30cbfac24339ef127c297d3b4b1ed6e6d8dbbb566c9a8ce9a95868b42c8b`.
- Plan `GDP-320675f3e272a0e1c41be1c731a77df676a5cad5fd75d4e27e70c0082eca09c3`.
- Reviewed on source `f761c05bc29172dd8e6ff825ffefec8db9ba9d24`, which is code `e70b2fe4` plus game `3a56510`.

**Rounds:**
1. Claude authored; the candidate passed validation.
2. Codex returned `revise` with 3 blocking findings and a revised candidate.
3. Claude's bounded revision review returned `pass` with 0 findings.

**Children and rewrites:**
- **Children:**
  - `navmesh-agent-configuration-foundation` owns the builder, the runtime `.asmdef`, `DoorPrototype.unity` and INT-001 for NSC-071.
  - `door-enemy-passability-interface` owns `logical:gameplay-walkability-surface` and has a local dependency on the first child.
- **Research-tree IDs:** NSC-089 and NSC-090. Re-allocate them against canonical.
- **Inbound rewrites:**

  | Dependent | Now depends on |
  |---|---|
  | NSC-013 | nav child |
  | NSC-014 | both children |
  | NSC-021 | passability child |
  | NSC-051 | passability child |
  | NSC-071 | nav child |
  | NSC-088 | nav child |

**Coordinator's minor finding:** child 1's new test path (`Tests/Editor/NavMeshAgentConfigurationTests.cs`) is named only in its completion gate VAL-001, not in an acceptance criterion. Decide whether to add it to an AC in the canonical edit.

**Requested:** once Astra approves, make the graph changes on main and validate them: the two children, the parent disposition, and the six inbound rewrites. This follows Vincent's milestone decision. The research pipeline port is not required.

**Sequencing note (reasoned):** applying NSC-025 first changes NSC-014's `depends_on` to the two new children. Consider applying it before editing or rerunning NSC-014, NSC-015 and NSC-033, so their fresh proposals are generated against the post-NSC-025 graph.

## C. Tasks that are not decomposition candidates (read-only triage; no edits without Vincent's approval)

Main has 14 tasks that are neither concrete nor decomposed:

| Kind | Tasks |
|---|---|
| Coarse organizational parents | NSC-001, NSC-002, NSC-006, NSC-010, NSC-018, NSC-022, NSC-027, NSC-031, NSC-034, NSC-036, NSC-056 |
| Coarse, design-pending | NSC-088 (Spectral Decoy) |
| `needs_future_decomposition` | NSC-030 |
| `proposed` | NSC-085 |

The pipeline's run gate only accepts active concrete decomposition candidates. Please confirm which of these need no D1B.2 decomposition, because they are organizational parents or design-first under the TaskDesignGER rescope rule. List any that should become decomposition candidates, with the design approval each needs.

## D. After your fixes

Send the new main commit or commits. Claude will then:
1. Rebuild a fresh research tree on that commit.
2. Run the zero-cost preflight.
3. Wait for Vincent's spend approval before any provider run, in Astra's order: NSC-014, then NSC-015, then NSC-033.

## Evidence (read-only)

- **Run 3 reviews:** `C:\nscrev\realdecomp-Checkouts-r3\.assistant-control\decomposition-runs\run3-nsc-014-616ca98\`, `run3-nsc-015-616ca98\`, `run3-nsc-033-616ca98\`. Each has `rounds\*\review.json` and `decomposition_run_result.json`.
- **Run 2:** `C:\nscrev\realdecomp-Checkouts\.assistant-control\decomposition-runs\run2-nsc-014-80a7537befae\` and `run2-nsc-015-80a7537befae\`. Both were rejected on coverage mapping, which the guidance has since fixed.
- **Astra's decisions:** `C:\nscrev\reports\codex-astra-real-task-decomposition-policy-20260914.md`, section 9A.
- **Pre-run checks for Run 5:** `C:\nscrev\reports\run5-readiness-guidance-e70b2fe4-20260914.md`.
