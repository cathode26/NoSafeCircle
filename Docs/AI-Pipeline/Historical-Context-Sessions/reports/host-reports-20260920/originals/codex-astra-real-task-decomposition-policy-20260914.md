# Codex / Astra: real-task decomposition decisions after the coverage-mapping fix

Prepared by the coordinating session at about 01:50 UTC on 2026-09-14, for Vincent to send. Fresh agent(s). This is a read-only review and a set of decisions; item A may be implemented once approved (section 7).

## 1. Where we are

- **Reliability stack is complete and verified.** Final integration head `4fd54b8` (`throughput/decomposition-final-integration`) closes all six mid-review blockers. Coordinator verification: 33 of 34 suites pass; the one failure is a pre-existing `test_viewer` timing test. See `C:\nscrev\reports\final-integration-verification-20260914.md`.
- **Coverage-mapping fix is committed.** `616ca980` (Astra approved) plus docs-only README correction `b1952a3`, both on `codex/coverage-mapping-guidance-20260913` in `C:\nscrev\coverage-mapping-guidance-fix`.
- **Live synthetic Gauntlet passed.** NSC-1165 split via the three-call path, and the family completed with no human actions.
- **Real game tasks, review-only runs (nothing applied).** Every run is a proposal on a combined tree: our pipeline code plus the canonical game's `Tasks/`, GDD and TaskGraph state at game HEAD `886bb81`.
  - **Run 2:** combined tree `80a7537`, code `9dee4a6`, before the coverage fix.
  - **Run 3:** combined tree `8da6ec4`, code exactly `616ca980`.
  - **Setup details:** `C:\nscrev\reports\run2-real-task-decomposition-feasibility.md`.

## 2. Evidence

**Run 2, before the fix.**
- **No task split.** 7 of 9 drafts broke one of the two coverage-mapping rules the prompts never stated (same-kind; one owner per child entry), from both the Claude author and the Codex reviewer.
- **Evidence and proposal:** `codex-prompt-coverage-mapping-fix.md`.

**Run 3, after the fix** (artifacts in `C:\nscrev\realdecomp-Checkouts-r3\.assistant-control\`):

| Task | Outcome | Round 1 (Claude author) | Correction | Round 2 (Codex reviewer) | Round 3 |
|---|---|---|---|---|---|
| NSC-035 | **review_ready** (first real task) | valid | not used | `revise`; revision valid | Claude revision review PASS |
| NSC-015 | **rejected** | valid | not used | `revise`; revision valid (in Run 2 Codex's revision broke the one-owner rule) | Claude `revise`, blocking `round-03-melee-lock-parity-gap`: Codex's revision dropped the shared `logical:enemy-locomotion-behavior-surface` lock from the attack-execution and prefab children. Claude's replacement gave that lock to both and was rejected: "Child exclusive_resources must exactly partition the parent exclusive_resources (missing=[], extra=['logical:enemy-locomotion-behavior-surface', 'logical:enemy-locomotion-behavior-surface'])." |
| NSC-033 | **needs_human** | valid (in Run 2 it broke the one-owner rule) | not used | `needs_human`, see F3 | — |
| NSC-014 | **needs_human** | rejected: "decomposition_result.inbound_dependency_rewrites contains duplicate dependent_task_id values." | valid | `needs_human`, see F4/F5 | — (no revision review after a correction, by design) |
| NSC-025 | **rejected** (no Codex call) | rejected: "Child exclusive_resources must exactly partition the parent exclusive_resources (missing=[], extra=['repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/Navigation/DoorPassabilityInterface.cs', 'repo-file:Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPassabilityInterfaceTests.cs'])." | rejected: "Untraced child obligation navmesh-walkable-locomotion-layer/downstream_integration_obligations/INT-001." | — | — |

**The coverage fix worked.**
- **Zero rejections on coverage rules.** No Run 3 draft or revision was rejected on the same-kind or one-owner rules.
- **Codex revisions now pass validation**, for both NSC-035 and NSC-015.
- **NSC-035's approved proposal has two children:**
  - `victory-trigger-overlay-integration` owns `DoorPrototypeSceneBuilder.cs` and `DoorPrototype.unity`;
  - `victory-gameplay-suspension-coordination` owns no resources.

**The remaining stops come from five other policy points.**

- **F1: new files versus exact partition.**
  - Real child tasks create new files, but the rule forbids a child from declaring any resource the parent does not list.
  - **Rule:** `policy.py:~150-170` (message at 162). **Author prompt:** `prompts.py:192-196`, which says "the child-resource union must equal the parent list" but never "do not list new files".
  - **Seen in:** NSC-025 round 1.
  - Under exact partition, `graph_delta.py:254`'s `created` resource-group branch is unreachable (F asserts this).
- **F2: child integration obligations without a parent INT entry.**
  - A child `downstream_integration_obligations` entry must be traced by coverage (`policy.py:287`). Only parent INT records may target child INT entries, and NSC-025's parent has 4 AC, 2 VAL and 0 INT, so no child INT can ever be traced.
  - The `coverage_mapping_rules()` block implies this but does not say it.
  - **Seen in:** NSC-025's correction.
- **F3: a shared mutable surface that two children must edit.**
  - **Codex's NSC-033 findings:**
    - `round-02-unowned-shared-orchestrator-edits`: "Its owner-group split requires both children to edit one exactly partitioned orchestrator/scene surface".
    - `round-02-missing-door-feedback-reset`: the closure inventory omits the implemented `DoorInteractionFeedback` reset participant.
  - **Codex's summary:** "Human clarification of the integration boundary or parent resource model is required."
  - **Related, NSC-035:** exact partition left one approved child owning nothing even though it coordinates gameplay suspension.
  - **Also NSC-015 (Run 3's last result, final at about 01:52 UTC):** Claude's round-3 review required both children that touch enemy locomotion to hold the shared `logical:enemy-locomotion-behavior-surface` lock, which about 7 active canonical tasks declare. Its replacement did exactly that, and exact partition rejected it. Both providers treat shared logical locks as contention tokens that several children may hold; the validator treats them as 1:1 ownership. This is the clearest F3 case.
  - **Background:** in canonical NoSafeCircle, `exclusive_resources` acts as a contention/serialisation token; the DoorPrototype builder and scene are each declared by about 26 active tasks. In the Gauntlet it is 1:1 ownership.
- **F4: a parent gate that needs future content.**
  - **Codex's NSC-014 finding `round-02-bone-archive-gate-not-local`:** "NSC-014 VAL-002 requires future Bone Archive content and duplicates NSC-071, while the mandatory same-kind coverage rule prevents moving that parent completion gate to a child downstream integration obligation."
  - For `decomposed`, allowed dispositions are only `assigned_to_child` and `shared_integration` (`policy.py:184`).
  - The run ended `needs_human`, as designed, to get human contract authority.
- **F5: inbound dependency rewrites.**
  - **Duplicate dependents:** duplicate `dependent_task_id` is refused at `contracts.py:578` (NSC-014 round 1).
  - **Overbroad rewrites:** Codex finding `round-02-overbroad-dependent-rewrites` (NSC-014).
  - **Existing guidance:** `prompts.py:225` and `287` ("exactly one mapping for every active direct dependent").
- **F6: one correction versus rules failing in sequence.**
  - NSC-025 used its single bounded correction to fix F1, then failed F2.
  - The correction prompt only shows the rule family that failed. Coverage defects are now aggregated (616ca980), but partition, untraced-child and rewrite checks still raise one at a time.

## 3. Proposal A: guidance only, low risk (the same pattern as 616ca980)

Add to the shared rules the author, correction and reviewer prompts receive (`coverage_mapping_rules()` or a sibling block):

1. Never add an `exclusive_resources` entry the parent does not list, including new files a child will create. Name new files in the owning child's acceptance criteria instead.
2. Give a child `downstream_integration_obligations` entries only when the parent has `downstream_integration_obligations` entries whose coverage records target them. Otherwise keep the proof as a locally provable same-kind acceptance criterion or completion gate.
3. Write exactly one inbound rewrite per dependent task, and rewrite a dependent only to the child capabilities it actually uses.
4. Extend the pre-return self-check to the resource partition (union equals the parent list, no additions) and to untraced child obligations.

Tests should follow 616ca980's pattern: all three prompts render the block, failing-before at `b1952a3`, no validator change.

**Expected effect:** likely fixes NSC-025 (F1, F2) and NSC-014's round 1 (F5). It does not resolve F3 or F4, which need decisions.

## 4. Proposal B: new files (F1). Needs your decision.

- **B1. Keep exact partition** and apply A only. New files stay undeclared; nothing in the scheduler protects them, but no other task can touch a file that does not exist yet.
- **B2. Allow additive new resources.** A child may declare a `repo-file:` resource the parent does not list, if all of these hold:
  - the path does not exist at the Source commit;
  - no active task declares it;
  - exactly one child declares it.

  Every parent resource must still be assigned. This makes graph_delta's `created` branch reachable, and it has implications for D1C, graph apply and the scheduler.
- **B3. Resource-kind-aware rule.** Every parent resource is assigned to at least one child, each resource has at most one mutating owner, and any other child that reads or wires it declares a dependency on the owner. This is the rule previously noted as the safe form for canonical semantics, and it also addresses F3.

## 5. Proposal C: shared mutable surfaces (F3). Needs your decision.

- **C1. Keep exact partition.** NSC-033-style splits end `needs_human`, so a person redraws the integration boundary or parent resources.
- **C2. Adopt B3.** One child owns the mutation and the others depend on it. NSC-033's reviewer asked exactly for a clarified boundary or resource model.
- **C3. Allow explicit serialized shared mutation**, with ordering enforced through dependencies.

Also decide: is NSC-035's approved shape, where one child owns no resources although it coordinates gameplay suspension, acceptable as it is?

## 6. Proposal D: deferred proofs (F4) and the correction budget (F6). Needs your decision.

**Deferred proofs:**
- **D1. Keep `needs_human` and fix the contract.** Vincent edits NSC-014: move VAL-002 to NSC-071, or reword it into a locally provable gate. Please give the exact recommended contract change; Codex owns canonical main.
- **D2. Allow `retained_by_parent` for specific parent gates in a `decomposed` result.** The aggregate parent keeps the gate until its dependents land. This is a design change.
- **D3. Allow `shared_integration` deferral** to a named existing downstream task.

**Correction budget:**
- **E1. Keep today's behaviour.** The three-call cap and single correction stay unchanged; A may be enough.
- **E2. Collect all deterministic violations** across every rule family (partition, coverage, untraced obligations, rewrites) into the one rejection the correction receives. This extends 616ca980's aggregation beyond coverage.
- **E3. In-session self-validation.** The author runs the deterministic validator before returning. It is not an extra provider call.

## 7. Decisions requested

Mark each answer as verified in code or evidence, or as reasoned.

1. **Approve proposal A?** If so, a developer implements it as one commit on top of `b1952a3` in `C:\nscrev\coverage-mapping-guidance-fix`, with failing-before tests and the existing suites.
2. **F1:** B1, B2 or B3? For B2 or B3, what changes in `policy.py`, `graph_delta.py` and D1C/graph apply, and must this be ported to canonical before any real apply?
3. **F3:** C1, C2 or C3? And is NSC-035's resource-less coordination child acceptable?
4. **F4:** D1, D2 or D3? If D1, what exact NSC-014 contract edit should Vincent make, and does NSC-033 need a similar edit (integration boundary, DoorInteractionFeedback reset)?
5. **F6:** E1, E2 or E3?
6. **NSC-035's review_ready proposal.**
   - Is it acceptable as a design?
   - What is the sanctioned path into canonical main? It was produced on a combined tree with our pipeline code, child IDs are allocated from NSC-086 against the `886bb81` graph, and our fixes are not yet ported to canonical.
   - Astra's approval so far covers testing, not applying.
7. **Rerun plan** (provider usage is limited): which tasks, after which decisions, and in what order? Our suggestion: NSC-025 alone after A; NSC-014 and NSC-033 after the contract or policy decisions; NSC-015 after the F3 decision.
8. **Anything in the evidence you read differently**, or any defect in how the runs were set up (combined tree, TaskControl removed, CLI `decompose` without dependency gating).

## 8. Evidence and pointers (read-only)

- **Run 3 records:** `C:\nscrev\realdecomp-Checkouts-r3\.assistant-control\NSC-0XX.decomposition.json`
- **Run 3 run folders:** `...\decomposition-runs\run3-nsc-0XX-616ca98\`, with `decomposition_run_result.json`, `progress.jsonl`, `rounds\NN\review.json`, `round_result.json`, and `agent_runtime\...\result.json` holding raw structured output. NSC-035 also has `decomposition_result.json` and `graph_delta.json`.
- **Run 2:** `C:\nscrev\realdecomp-Checkouts\.assistant-control\` (`run2-nsc-0XX-80a7537befae`)
- **Combined source:** `C:\nscrev\realdecomp-run2-src`, HEAD `8da6ec4` (code `616ca980` plus game `886bb81`). Rebuild tool: `C:\nscrev\realdecomp-tools\rebuild_combined.py`.
- **Code at `b1952a3`:** `Pipeline/TaskDecomposition/policy.py`, `contracts.py`, `prompts.py`, `review_prompts.py`, `Pipeline/TaskGraph/graph_delta.py`
- **Reports in `C:\nscrev\reports\`:**
  - `fix-coverage-mapping-guidance-agent-report.md`
  - `codex-prompt-coverage-mapping-fix.md`
  - `run2-real-task-decomposition-feasibility.md`
  - `final-integration-verification-20260914.md`
  - `codex-status-2-20260913.md`
  - `fix-1165-evidence-context-agent-report.md`

## 9A. Astra's decisions (relayed by Vincent at about 02:05 UTC, 2026-09-14)

This was a read-only review; Astra implemented nothing.

1. **A: approved.**
   - Build the guidance-only change on top of `b1952a3`, with failing-before tests and the existing suites afterwards.
   - Verified: exact partition is checked before coverage, and NSC-025 hit sequential policy failures.
   - Binding condition: the guidance must preserve the requirement for real, same-kind gate evidence. A fixture cannot substitute for future content.
   - Success on NSC-025 is not yet proven.
2. **F1: B1 during the A experiment; B2 designed separately.** B2 would allow a new repo-file path only when all of the following hold:
   - the path is absent from the pinned Source;
   - no active task claims it;
   - exactly one child is assigned it.

   It would need checks in `policy.py`, `graph_delta.py` and the final graph-apply path, and must be ported and verified in canonical before any real apply.

   **Corrections to this report:**
   - Two tasks can independently create the same nonexistent path.
   - A single-owner new file would not reach the `created` resource-group branch, because `graph_delta.py:221` skips single-owner resources.
3. **F3: keep C1 now; design C3 for shared mutation.**
   - **C3** requires every child that mutates a shared surface to retain its lock, plus explicit acyclic ordering.
   - **C2** works only where one child really makes all the shared-file edits.
   - **NSC-035's resource-less coordinator** is an acceptable design: it owns its new component and tests, while the dependent assembly child owns the builder and scene edits. Its new paths still need reservation before execution.
4. **F4: D1, explicit contract edits** in canonical, owned by Codex and Vincent.
   - **NSC-014:**
     - Remove VAL-002 and keep the other gates.
     - Add an integration obligation that assigns the committed Bone Archive lane proof, including the BA-1 2.5-unit pinch, to NSC-071.
     - Make NSC-071 depend on NSC-014 and test its delivered movement foundation.
     - Record the transfer in both revised contracts.
   - **NSC-033:**
     - Depend on NSC-041.
     - Include `DoorInteractionFeedback.ResetFeedback` in the reset inventory.
     - Extend restart validation to hover, selection, approach and opening feedback.
     - Its integration child owns all shared orchestrator, builder and scene edits, under C1.
5. **F6: E2, as a separate change.** Aggregate independently evaluable deterministic defects in a stable order, still reject malformed structure immediately, and keep the provider-call budget. E2 need not delay the first A-only experiment.
6. **NSC-035: architecture accepted; the saved apply artifact is not.**
   - Before a fresh proposal: resolve the invented `CrossedForward` interface name and reserve the new paths.
   - Port the selected pipeline policy to canonical, then generate and independently review a fresh canonical-bound proposal.
   - The scratch approval and the NSC-086/087 IDs cannot carry over as canonical authorization.
7. **Rerun order** (usage is limited):
   1. NSC-025 alone, after A.
   2. If another sequential deterministic correction fails, do E2 before broader reruns.
   3. NSC-014 after the D1 transfer.
   4. NSC-015 after F3 is settled.
   5. NSC-033 last, after its contract and upstream owners are settled.

   Do not rerun NSC-035 just to raise the success count.
8. **Run setup: suitable for proposal research, not execution clearance.**
   - Verified: the combined tree matches the declared substitutions, `TASKCONTROL_CURRENT.json` is absent, and direct `decompose` bypasses the controller's dependency-ready gate (`graph_controller.py:885`).
   - Not independently reproduced: the complete controller-conformance result.
   - Current canonical main is `c45a2355`.
   - Cautions: `calls_used` omits separately recorded correction and review rounds, and early partition failures may hide later coverage defects.

## 9B. Proposal A: implemented (about 02:35 UTC, 2026-09-14)

**Commit and scope**
- **Commit:** `a988b5b774bb0568aa90d30a0351915c88b5259f`, parent `b1952a3`, on `codex/coverage-mapping-guidance-20260913`, with the `.invalid` identity.
- **Changes:**
  - `prompts.py` +55: new block `candidate_wide_rules()`, "Candidate-wide rules and pre-return self-check:", at 144-178. It is rendered after the coverage block; the correction prompt inherits it.
  - `review_prompts.py` +16/-1: renders the block, plus a replacement invariant and an introduction.
  - `README.md:425` +1/-1: fixtures never substitute for required real content; future-content proof goes to `needs_human` with an explicit contract transfer.
  - New `candidate_wide_rules_guidance_smoke_test.py`.
- **Validator untouched:** `policy.py`, `contracts.py`, `round_robin_decomposition.py` and `graph_delta.py` are unchanged.

**Tests**
- **New test file:** the 3 prompt tests fail at `b1952a3` and pass after. The 8-case validator pin passes on both commits.
- **Developer run:** all 21 suites pass.
- **Coordinator check:** identity, parent, unchanged validator files, and clean whitespace.

**Rule 3 examples**
- The rule 3 example is generic and does not name NSC-014, VAL-002 or NSC-071, so it will not go stale after the D1 transfer.

**Conflicting older wording (flagged, not yet changed)**
- **`review_prompts.py:136-137`, reviewer replacement invariant, not pinned by any test:** "A child completion gate must be locally completable. A proof that requires later authored content belongs in a downstream integration obligation owned by the appropriate later task." This contradicts rule 3 (future-content proof goes to `needs_human` with a contract transfer), and it can steer a reviewer's revision straight into F2.
- **`prompts.py:110-111`, the 616ca980 same-kind bullet, pinned by the coverage test:** "... or part of its proof is deferred to a child `downstream_integration_obligations` entry." This is softer: it presupposes deferral into a child integration obligation.
- **`README.md`:** the paragraph still ends "map it to a locally provable same-kind child entry instead". This is consistent with rule 3 when the child can really prove the gate.

## 9. Constraints

- **Read-only unless implementing an approved item.** Never write under `C:\NSC`; the game repository `C:\NSC\NSC\NoSafeCircle` is read-only.
- **No push, merge, provider or Docker commands.** No real-task reruns; the coordinator runs those with Vincent's approval.
- **When implementing:**
  - use a non-attributable `.invalid` identity (`AGENTS.md`);
  - CRLF via autocrlf, never `sed -i`, and `git diff --check`;
  - failing-before tests;
  - never run the TaskReviewAgent local suites that write under `C:\NSC` (`local_candidate_source_integration`, `local_source_wait_completion`, `immutable_crew_manifest`); redirect `NSC_DECOMP_PENDING_TEMP`, `NSC_REVISION_RACE_TEMP` and `NSC_DECOMP_WAKE_TEMP` for the others.
