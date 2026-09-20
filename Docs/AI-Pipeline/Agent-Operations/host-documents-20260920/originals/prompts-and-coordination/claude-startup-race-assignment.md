## Assignment: fix the AssistantControl first-launch registry race

A fresh `--checkout-root` can fail with `assistant admission registry identity or schema differs` when `viewer` and `run-graph` start at nearly the same time. Reproduction: launch both commands concurrently against the same empty checkout root. The viewer is read-only from the operator's perspective, but both processes race during AssistantControl/checkout or admission initialization.

Please work in your existing isolated clone and report the commit and focused test results here. Do not push, merge, launch providers, or touch live run directories.

Scope:
- Diagnose the exact competing writes in `Pipeline/AssistantControl/`.
- Make first-use initialization atomic and idempotent, or ensure the read-only viewer never creates/mutates admission state.
- Preserve exact project/source identity checks: a genuinely different source or incompatible schema must still fail closed.
- Add a focused concurrency regression test that starts the relevant initialization paths together against one empty temporary root and proves both observe the same valid registry.
- Keep the patch small. Do not redesign controller ownership, task reset, or provider execution.

Acceptance:
1. Concurrent fresh `viewer` + `run-graph` initialization cannot produce a partial/mismatched registry.
2. Same-identity repeated initialization succeeds.
3. Different source identity and incompatible schema remain rejected.
4. Existing focused AssistantControl viewer/admission tests pass.
