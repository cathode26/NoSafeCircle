# Codex / Astra follow-up after the NSC-025 research run (2026-09-14, about 03:20 UTC)

Fresh agent(s). This is a read-only review with decisions; nothing is to be implemented without explicit approval. It follows your decisions in section 9A of `C:\nscrev\reports\codex-astra-real-task-decomposition-policy-20260914.md`.

## 1. What changed since your decisions

**Proposal A** is implemented on `codex/coverage-mapping-guidance-20260913` (worktree `C:\nscrev\coverage-mapping-guidance-fix`) as two commits, both guidance only.

1. **`a988b5b774bb0568aa90d30a0351915c88b5259f`** (parent `b1952a3`) adds `prompts.candidate_wide_rules()`, "Candidate-wide rules and pre-return self-check".
   - **Where the rules appear:** in the author and correction prompts, and explicitly in the reviewer prompt.
   - **The rules:**
     - no resources the parent does not list, with new files named in the owning child's acceptance criteria (B1/C1);
     - child integration obligations only under a parent INT entry;
     - real, same-kind proof: a fixture never substitutes for future content, which goes to `needs_human` with a contract transfer;
     - one inbound rewrite per dependent;
     - a pre-return self-check in validator order.
   - **Tests:** 3 prompt tests fail before the change, and an 8-case validator pin shows validation behaviour is unchanged.
2. **`3a0645350f522e653d04c6ec6b04291967ea1e8b`** (parent `a988b5b`) is an alignment fix that Vincent approved before the run. **Please review it.**
   - **`review_prompts.py:136-140`:** the replacement invariant used to say "A proof that requires later authored content belongs in a downstream integration obligation owned by the appropriate later task." It now says to choose `needs_human` and state the contract transfer.
   - **`prompts.py:109-111`:** the same-kind bullet lost the clause "or part of its proof is deferred to a child `downstream_integration_obligations` entry". This deliberately updates the 616ca980 pin in `coverage_mapping_guidance_smoke_test.py`, which now has 13 tests.
   - **`README.md:425`:** one sentence aligned.
   - **Unchanged:** the validator and orchestration.
   - **Tests:** 21 suites pass. The changed test file fails 4 tests at `a988b5b`.

The coordinator verified both commits: `.invalid` identity, correct parents, `policy.py`/`contracts.py`/`round_robin_decomposition.py`/`graph_delta.py` unchanged, and whitespace clean.

## 2. NSC-025 research run: result

**Setup**
- Combined tree `fbdcd4338b54d631de5927cef77b2fcb49a03647`: code `3a06453` plus the old game snapshot `886bb81`.
- Run `run4-nsc-025-3a06453`, checkout root `C:\nscrev\realdecomp-Checkouts-r4`, review-only.
- The result can never be applied: NSC-086/087 are now allocated on canonical main.

**Outcome: `needs_human` after 2 calls, with no correction and no revision review.**
- **Round 1 (Claude author) passed every deterministic check.** In Runs 2 and 3 NSC-025's drafts failed validation: first on coverage mapping, then on the partition (new files) and on an untraced child INT.
- **Round 2 (Codex reviewer) returned `needs_human`** with two blocking findings:
  - `round-02-future-bone-archive-proof`: "It substitutes a synthetic corridor for a completion gate requiring real Bone Archive geometry, despite NSC-071 already owning that proof".
  - `round-02-unreserved-navigation-files`: "it requires unreserved assembly-definition and unnamed script/test-file work".
  - Codex's summary: "The candidate cannot be corrected safely within the current parent contract."

**Reading the result (coordinator)**
- **A worked at the validation level.** NSC-025 stopped failing deterministic rules.
- **The reviewer applied rule 3 as intended.** It refused a fixture standing in for future content and stopped for contract authority rather than inventing a fix.
- **The author still broke rule 3,** which confirms your caution that rule 3 depends on the models.
- **The second finding is the B1 gap in practice.** New files, including an assembly definition, were neither fully named nor reserved.
- **Not triggered:** no sequential deterministic correction failure happened, so E2 was not triggered by your rerun rule.

## 3. Questions

1. **NSC-025 contract transfer.**
   - Do you agree NSC-025 needs a D1-style edit? Move the completion-gate proof that requires real Bone Archive geometry to NSC-071, which Codex says already owns that proof, and make NSC-071 depend on NSC-025 as needed.
   - Please give the exact edit, as you did for NSC-014.
   - Should NSC-014 and NSC-025 transfer into NSC-071 in one coordinated contract change?
2. **Who makes the D1 contract edits in canonical main** (NSC-014, NSC-071, NSC-033, and now NSC-025): Codex or Vincent? What review and validation should they pass before the next research runs?
3. **New files under B1** (NSC-025's second finding).
   - Should rule 1 require naming every new path explicitly, including `.asmdef` assembly definitions, new scripts and new tests, in the owning child's acceptance criteria?
   - Should the reviewer treat unnamed new-file work as blocking, as Codex did?
   - Is there, or should there be, a canonical reservation mechanism for new paths outside `exclusive_resources` before execution?
   - Or does this move B2 up the priority list?
4. **Alignment commit `3a06453`.** Approve, or request changes? Residual risk: rule 3's routing now appears in two places (the reviewer invariant and the candidate-wide block) with slightly different wording ("later authored content" versus "future content").
5. **Where research runs happen next.** Should further review-only runs stay on the old snapshot `886bb81` for comparability, or move to a combined tree on current canonical main (`c45a2355` or later)? Our pipeline is still not ported there, so any proposal meant for application still needs the canonical port and a fresh review, per your decision 6.
6. **Order and ownership, not prerequisites for this milestone** (per Vincent):
   - When and by whom should the canonical pipeline port, B2 (new-file resources and reservation), C3 (shared mutation with ordering) and E2 (aggregating all deterministic defects) be done?
   - Does NSC-025's result change the rerun order you gave: NSC-014 after D1, NSC-015 after F3, NSC-033 last?
7. **`calls_used` accounting.** You noted it omits correction and revision-review rounds. Is that a documentation caution, or should run results and the viewer report a total provider-call count?

## 4. Evidence (read-only)

- **Run artifacts:** `C:\nscrev\realdecomp-Checkouts-r4\.assistant-control\`, containing:
  - `NSC-025.decomposition.json`;
  - `decomposition-runs\run4-nsc-025-3a06453\` with `decomposition_run_result.json`, `progress.jsonl`, `rounds\01\` (candidate, round result, raw agent result) and `rounds\02\review.json`.
- **Earlier NSC-025 runs:**
  - Run 2: `C:\nscrev\realdecomp-Checkouts\...\run2-nsc-025-80a7537befae`
  - Run 3: `C:\nscrev\realdecomp-Checkouts-r3\...\run3-nsc-025-616ca98`
- **Code:** `C:\nscrev\coverage-mapping-guidance-fix` at `3a06453`, in `Pipeline/TaskDecomposition/prompts.py`, `review_prompts.py`, `README.md` and `tests/`.
- **Combined source:** `C:\nscrev\realdecomp-run2-src` at `fbdcd43`.

## 5. Constraints

- **No writes under `C:\NSC`.** The game repository is read-only.
- **No push, merge, provider runs, Docker or task reruns.**
- **Implement nothing unless your answer explicitly approves it.** Mark each answer as verified in code or evidence, or as reasoned.
