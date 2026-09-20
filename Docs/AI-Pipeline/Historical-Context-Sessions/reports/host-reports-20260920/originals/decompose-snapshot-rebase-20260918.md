Rebase complete and verified. Summary:

- **Tip:** `65b8377de`, 4 commits ahead of `origin/main` (`255951482` full sha `2559514826e9...`). No conflicts — rebase applied cleanly.
- **Tests:** `test_decomposition` 50/50 OK, `test_decomposition_transport` 9/9 OK, `decomposition_session_pool_smoke_test.py` 10/10 pass, `pooled_decomposition_smoke_test.py` 18/18 pass. All green.
- **Merge-tree vs main:** 0 conflicts (3-arg `git merge-tree`, confirmed HEAD's rebase base is exactly current main tip).
- **Identity flag (not fixed, reporting only):** committer is correctly `pipeline-maintainer@nosafecircle.invalid` on all 4 commits, but *author* is `task-review-agent@nosafecircle.invalid` on all 4 — that's pre-existing from before the rebase (checked against the original `221e59cdb` tip), not introduced here, and both are synthetic agent addresses, not a real person's leaked email. Rebase behaved correctly (preserves author, only re-stamps committer). Left as-is per instructions not to guess-fix identity issues.

Branch `fix/decompose-on-a-snapshot` in `C:/nscrev/decomp-snapshot` is rebased, green, and conflict-free against current main — ready for whoever does the handoff. Nothing merged/pushed/deleted; `ci-134-fix` and the canonical checkout untouched beyond the specified read fetches.
