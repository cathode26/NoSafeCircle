# AssistantControl A2 (Codex blockers 2 and 5): implementing agent's report

Received 2026-09-13 at about 22:35 UTC and recorded in substance by the coordinating session. The coordinator has checked the commit identity and whitespace.

## Commit

`ff5bdc6736e58c1f466efe51790b16ab83f78632`, parent `fce5398`, on `throughput/decomposition-ac-consumer` in `C:\nscrev\ac-consumer-fix`. `diff --check` is clean and CRLF line endings are kept.

| File | Change |
|---|---|
| `decomposition.py` | +111/-32 |
| `test_decomposition.py` | +99 |
| `test_decomposition_needs_human.py` | +181 |

## Blocker 2: advisory-only pass

**Producer rule cited.**
- `review_policy.validate_decomposition_review` (`review_policy.py:81-99`) lets a `pass` carry advisory findings.
- The same rule refuses a `revised_decomposition`, any new blocking finding, or any unresolved prior blocking finding.
- `round_robin_decomposition.py:1268-1297` writes every finding into the history entry and into the round's `new_finding_ids`. Only blocking findings stay unresolved.

**What AssistantControl now accepts**, the same thing for all three shapes:
- **Pair and correction proof.** A pass is refused only when its findings are not all advisory. The existing "does not end with a clean pass" message is kept.
- **Replay.** Any blocking finding on the approving review is refused.
- **Other B3 rules, all kept:**
  - exact finding form and round prefix;
  - no reused or duplicate id;
  - round new/unresolved ids;
  - resolution coverage;
  - structured output equal to the history entry.

## Blocker 5: needs_human runs with `revision_reviews_used == 1`

This creates no new status, and `apply` still refuses such runs.

- **Run level.** The M7 run Source branch check applies.
- **Every round** goes through the shared review-ready check: requested provider, runtime identity from `RUNTIME_PROVIDER_IDENTIFIERS`, succeeded, review-only, non-pooled.
- **Round 3.** Its actual provider must differ from round 2's.
- **Earlier rounds.** The author round carries no findings or rejections, and the reviser carries no rejections.
- **Replay.** The SHA chain and B3 replay run as before.
- **Paths.** Every round's recorded paths must always be the exact invocation paths.
- **Artifact files.** M6 file authentication runs whenever the run directory keeps a rounds directory, and a partial deletion is refused. With no rounds directory at all (evidence retained without artifacts), only the paths are proven and no file is read.
- **Unchanged.** Runs counting no revision review, including records retained before `ade5bca`, behave exactly as before.

## Suites on `ff5bdc6` (sequential)

| Suite | Result |
|---|---|
| test_decomposition | Ran 62 tests in 462.768s, OK |
| test_decomposition_needs_human | Ran 41 tests in 487.056s, OK |
| test_graph_controller | Ran 33 tests in 322.727s, OK |
| test_decomposition_revision_review_integration | Ran 7 tests in 290.295s, OK |

## Failing-before at `fce5398`

This ran in a detached worktree with the A2 test files copied in; the worktree has since been removed and pruned.

| Suite | Result at `fce5398` |
|---|---|
| test_decomposition | Ran 62, FAILED (failures=6, errors=3) |
| test_decomposition_needs_human | Ran 41, FAILED (failures=15) |

**Strong evidence** (the base refuses a valid run or accepts a forgery):
- advisory-only pass for the pair and corrected shapes (2 errors);
- advisory-only revision-review pass through verify and apply (1 error);
- needs_human identity (9 subtests, all accepted at base);
- partial artifact deletion (accepted at base);
- tampered round artifacts (5 subtests, accepted at base).

**Weak evidence.** "Advisory findings still replay" (6 subtests): the base does refuse these, but with the old clean-pass message.

**Controls that pass at base:**
- a pass with a blocking finding is refused (pair, corrected and revision review);
- the needs_human golden run with artifacts authenticates, and `apply` refuses it;
- every pre-existing test.

## Next

A3a: cherry-pick T `008d1df` onto `ff5bdc6`, then add the whole-stack tests that do not need developer E's work.

## Final report: A2, A3a and A3b (received about 00:00 UTC, 2026-09-14)

### Commits

The branch is `throughput/decomposition-ac-consumer`, head `e7d2b788f175d42a5f7595b4ee4ae686dde287b6`, and its worktree is clean. Cherry-picks were made with `-x` and applied without conflicts. `diff --check` is clean and CRLF is kept throughout.

| Commit | SHA | Parent | Content |
|---|---|---|---|
| A2 | `ff5bdc6` | fce5398 | decomposition.py +111/-32; test_decomposition.py +99; test_decomposition_needs_human.py +181 |
| T | `4449fb8` (from 008d1df) | ff5bdc6 | cherry-pick |
| T2 | `e25b53e` (from c245deb) | 4449fb8 | cherry-pick |
| A3a | `01f2660` | e25b53e | new test_decomposition_whole_stack.py +356 |
| E | `efc498a` (from 3c64631) | 01f2660 | cherry-pick |
| A3b | `e7d2b78` | efc498a | decomposition.py +22; test_decomposition.py +19/-4; test_decomposition_needs_human.py +2/-2; IT +22/-2; whole-stack +212 |

### Suites on `e7d2b78`, one at a time

| Suite | Result |
|---|---|
| test_decomposition | 62 OK |
| test_decomposition_needs_human | 41 OK |
| IT | 7 OK |
| test_graph_controller | 33 OK |
| test_decomposition_triage | 18 OK |
| test_decomposition_whole_stack | 16 OK |

Earlier heads also passed: A2 (62/41/33/7) and A3a (62/41/33/7/18/10).

### Failing-before evidence

**A2 at fce5398:** test_decomposition FAILED (6 failures, 3 errors); needs_human FAILED (15 failures).
- Strong:
  - advisory-only pass for the pair, corrected and revision-review shapes;
  - needs_human identity (9 subtests);
  - partial artifact deletion;
  - tampered artifacts (5 subtests).
- Weak: advisory findings still replay (6 subtests, which fail at base only because the message differs).

**A3a whole-stack at fce5398:** FAILED (5 failures, 2 errors).
- Strong:
  - both advisory applies;
  - the default limit (4680.0, where base uses 3600);
  - the override limit (7601.0, where base uses 3600);
  - an invalid override (base starts the container).
- Controls that pass at base: both three-call shapes, both blocking-pass refusals, and the tamper test.

**A3b whole-stack at efc498a** (E present, not wired): FAILED (18 failures, 8 errors).
- Strong: at base, the forged bypass run, a legacy context over children with no evidence, and a stored-policy mismatch are each accepted and applied. Later subtests cascade from the applied parent.
- Weak: missing keys only (`artifact_sha256["context.json"]`, `child_gdd_evidence`).
- Controls that pass at base: E's producer refusal, derived limits, tamper, and blocking passes.

### Notes

- A3a's commit message says 5500.5 s for the override. The test correctly asserts 2000 + 2500.5 + 2500.5 + 600 = 7601.0 s. The commit message was deliberately not amended.
- A3b reads `context_sha256` with `run_result.get` (accepted by the coordinator).

### Residual risks

1. A retained, unapplied review_ready record whose children fail E's rule is now refused at inspect or apply. This holds even for a legacy 1.0 context, because legacy only skips the stored-policy comparison.
2. The evidence check runs `git show` at the reviewed commit on every inspect or apply. If that commit cannot be read, the proof refuses.
3. A needs_human run with no rounds directory has only its recorded invocation paths checked. A needs_human record grants nothing.
4. needs_human runs that count no revision review keep their earlier checks.
5. Advisory acceptance mirrors today's `review_policy`. A change to severities or verdicts needs a matching AssistantControl change.
6. The whole-stack tests emulate the compose `--env` handoff in-process; no real container is run.
7. Each suite takes 1-8 minutes.

Nothing was written under `C:\NSC`. No Docker, providers, GitHub, push, merge, CI or docs were touched.
