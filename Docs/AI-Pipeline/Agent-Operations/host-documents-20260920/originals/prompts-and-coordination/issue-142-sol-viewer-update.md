OpenAI GPT-5.6 Sol — viewer candidate and NSC-898 result

An isolated viewer candidate now keeps each active node's task ID, contract title, explicit `[DECOMPOSITION]` or `[IMPLEMENTATION]` tag, current stage, and elapsed time. The work-type tag prefers the scheduler's selected `work_type`, then the active decomposition phase, then the contract's `execution_scope`; it does not infer decomposition from provider or from `kind: implementation`. Per-card `LOCAL REHEARSAL` text was removed because the run banner already supplies that context. No live Source or viewer was changed or restarted.

Candidate files:

- `C:\NSC\GauntletConvergenceIntegration-20260908\Pipeline\TaskReviewAgent\GauntletView\server.py`
- `C:\NSC\GauntletConvergenceIntegration-20260908\Pipeline\TaskReviewAgent\GauntletView\index.html`
- `C:\NSC\GauntletConvergenceIntegration-20260908\Pipeline\TaskReviewAgent\GauntletView\tests\gauntlet_view_smoke_test.py`

Validation: all 147 `gauntlet_view_smoke_test.py` tests pass.

NSC-898 completed successfully at 03:27:07.849Z as `local_review_ready` / `local_rehearsal_only`; this is a review handoff, not a failure and not a human PASS. Its decomposition result is `review_ready`, `decomposed`, `review_only_not_applied`, with two calls and no findings, unresolved findings, or rejection reasons. A Claude task-decomposer session authored candidate SHA-256 `12a2fcac6b203b800b2ff430bc92db04a7e8ceb20783d0f685b5df34ac0a5839`; a distinct Claude decomposition-reviewer session returned independent PASS. Graph plan ID: `GDP-807d329f573d370f488a2ef2bbfe13b4ba2705c4ce2588f288935195aeef3798`. Human review is required before any apply.
