OpenAI GPT-5.6 Sol — merge feature team handoff

Vincent assigned the merge feature to the team. The NSC-898 live continuation bug remains under Astra's live ownership; Fable's existing local-decomposition candidate remains relevant evidence, but nobody should create a competing NSC-898 implementation or disrupt either active run.

Merge feature requested behavior:

1. Operator selects exactly two finished, mergeable branches in GauntletView and clicks Merge. Cheap enablement checks keep selection responsive; press performs full validation. The approval is single-use and bound to both candidates' exact SHA, workflow state version, and event ID, so movement of either candidate rejects it as stale.
2. Autonomous merge handling observes closeout-queue additions, claims compatible candidates, greedily folds them, and returns a composed train that can fold again: `(A+B)+C`. Failure, conflict, abandonment, restart, and undo must preserve every original member. Undo persists a veto for the exact SHA pair, while deliberate operator selection may override that veto.

Existing implementation to reuse: the full 12-commit merge-agent series through canonical `06993734c332e3912008d9d760a636d5cdf3df0c` is present unchanged in integration `9ed1a4305e868d2b692ead7aaa6e6625779276e3` and both frozen Sources. It includes train construction, fold eligibility/primitive, pair-veto/durability, publication-head substitution, train CI authority, and train closeout. Do not duplicate those primitives.

Representation constraint from the corrected Phase-2 authority spec: the durable integration gate is keyed by `task_id`, rejects reservation widening, and cannot withdraw a still-ready candidate B. Therefore the train rides candidate A through a durable binding while both original task waiters remain authoritative; B closes through `close_out_merged_by_train`. A literal new combined gate row would require a separately reviewed gate-schema/authority change. The UI may present the composed queue result while preserving this underlying representation.

Team ownership request:

- Fable: implement the bounded manual two-selection approval/UI path in an isolated candidate, reusing `GauntletApprovalController`'s token and double-revalidation patterns. Include exact dual-subject stale rejection, operator veto override visibility, full press-time fold checks, and pre-publication undo only.
- Sonnet: independently audit and implement the autonomous scheduler/queue seam from `C:\nscrev\scratch\MERGE_AGENT_UNIT6_PLAN.md`, reusing `fold_pair`, `TrainCiAuthority`, and `close_out_merged_by_train`. Cover event unregister/drain/re-register plus final reconcile, recursive fold, durable recovery, and lossless conflict/abandon/undo paths.
- Sol: reconcile both candidates against the authority plan, current gate/downstream contracts, and acceptance matrix; report overlaps, missing seams, and focused test evidence here.

Acceptance must preserve exact CI and gate authority, both candidates' delivery records, the train's ordered members and refs, restart recovery, and unchanged publication fencing. It must not grant new main-publication authority or widen LOCAL rehearsal publication. No live Source edits/restarts, commits, pushes, resets, or provider launches. Please acknowledge ownership with exact candidate path, base SHA, changed paths, and focused tests.

Sol's clean coordination worktree is `C:\NSC\SolMergeAgentUnit6Candidate-20260908`, branch `sol/merge-agent-unit6-candidate`, exact base `9ed1a4305e868d2b692ead7aaa6e6625779276e3`; it is currently unmodified and waiting for team candidates.
