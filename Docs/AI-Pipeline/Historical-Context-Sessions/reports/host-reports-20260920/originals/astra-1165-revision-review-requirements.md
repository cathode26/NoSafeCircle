# NSC-1165 decomposition revision-review fix: Astra's required repairs

Relayed by Vincent on 2026-09-13 at about 17:25 UTC. He first paused it, then said to resume at about 18:30 UTC, so the work is authorized and underway. The binding implementation design is `C:\nscrev\reports\revision-review-design.md`.

## Where

- Worktree `C:\nscrev\revision-review-fix`, branch `throughput/decomposition-revision-review`, base `ade5bca`.
- An earlier agent's uncommitted draft is already in the worktree: about 844 insertions across 5 files, plus the new `Pipeline/TaskDecomposition/tests/revision_review_smoke_test.py`. It is not merge-ready. Continue from it or replace it.
- Do not touch any live Gauntlet project, Docker, providers, GitHub, or `C:\NSC`. Do not push or merge.

## Verdict

Astra independently reproduced the failure and agrees with the general design, but the current draft is not merge-ready. Implement both better author guidance and one bounded independent revision review.

## Required repairs

1. **Hard ceiling of three physical provider calls.**
   - With `max_calls == 2`, either `author_corrections_used == 1` or `revision_reviews_used == 1` may occur, never both.
   - No execution path may create four round records or four provider invocations.
   - Counters must be exact integers, not booleans.
   - Prove `total_provider_calls = calls_used + author_corrections_used + revision_reviews_used`.
2. **Pooled sessions stay excluded from the revision-review call.**
   - Do not reuse the original author conversation as the independent reviewer.
   - Fail closed if a pooled run reaches this shape.
   - Do not broaden pool leases or settlement authority in this commit.
3. **Bind round 3 to the exact revised candidate.**
   - The actual provider must differ from the latest candidate author.
   - Bind candidate version and SHA-256.
   - Authenticate the actual invocation and provider identity.
   - Require unchanged Source identity.
   - Require every outstanding blocking reviewer finding to be explicitly resolved or withdrawn.
   - `pass` may produce `review_ready`; `revise`, `reject`, provider failure, invalid output or Source drift must not.
   - Never permit a fourth call.
4. **Repair every accepting consumer.**
   - Update `Pipeline/TaskReviewAgent/decomposition_authorization.py` so D1C accepts the valid three-record shape while preserving every existing identity, policy, graph-plan, Source and candidate check.
   - Tighten `Pipeline/AssistantControl/decomposition.py::_review_ready_proof`.
   - Replay the complete ordered round history. Reject missing finding resolutions, a mismatched actual reviewer, impossible round numbers, changed candidate hashes, stale Source, or a retained Source-movement rejection.
   - Preserve `revision_reviews_used` in human-state records and in any authenticated or replayed result shape.
   - Audit every reader of `calls_used`, `max_calls`, `author_corrections_used`, round records and review evidence.
5. **Better decomposer guidance for synthetic Gauntlet children, with no Gauntlet-only bypass.**
   - When `selected_task_gdd_evidence` is empty, children must leave unsupported `gdd_evidence` empty.
   - Never cite `provenance.origin` as GDD evidence.
   - Completion gates must state exactly what their tests prove. A constant-value test does not prove that a class is public or static.
   - Preserve engineering requirements: public/static class shape, deterministic `.meta` ownership, exact resource partitioning, full parent-obligation coverage.
   - Apply conservatively; real game decompositions keep their actual GDD/RAG evidence.
6. **Failing-before regressions** for:
   - the reproduced NSC-1165 author, revise, independent-review path;
   - normal two-call independent approval;
   - author correction and revision review being mutually exclusive;
   - pooled-session exclusion;
   - Source movement;
   - malformed or invalid revision;
   - round-3 `pass`, `revise`, `reject` and provider failure;
   - incorrect reviewer identity;
   - missing prior-finding resolutions;
   - impossible round numbers;
   - changed candidate hashes;
   - physical call count never exceeding three;
   - D1C accepting only the exact valid three-record shape.

Do not reuse the retained NSC-1165 graph plan: its proposed child IDs now collide with NSC-1166's applied children. Preserve that evidence, and use a fresh run and plan only after this code is reviewed.

## Delivery

- Run focused tests, capture failing-before evidence from a detached worktree of the base, and commit the repair separately.
- Report the exact commit SHA and parent, files changed, tests and counts, how each requirement is enforced, residual risks, and confirmation that nothing live was touched.
- Post the report to Issue #36 and request Codex/Astra review of the exact commit.

## Estimate given to Vincent

About 5 hours to a review-ready commit posted on #36: about 4 hours to build and test (the draft covers roughly a third; D1C authorization, prior-finding resolutions and author guidance were not started), about 1 hour of independent verification and posting. Then Codex/Astra review, then about 30 minutes to re-run NSC-1165 on a fresh plan.
