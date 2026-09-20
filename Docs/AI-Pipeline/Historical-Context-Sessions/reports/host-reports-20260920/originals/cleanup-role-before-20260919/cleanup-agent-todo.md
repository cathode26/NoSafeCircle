# Cleanup Agent: work queue (authority for what is next)

Created 2026-09-18 (host clock 21:16 CDT) when this session was repurposed as the Cleanup Agent. Updated 21:27. Order follows guide section 10.2: worktrees first.
The team pause applies: nothing new starts until Vincent asks or an agent hands over hygiene work.

## Done tonight (2026-09-18)
- Read-only worktree inventory, sizes, `MOVE-NSC-FOLDERS.ps1` review, safety scan re-run: `C:/nscrev/reports/cleanup/worktree-inventory-20260918.md`.

## Waiting on Vincent (asked in the 21:27 report)
1. Task-named worktrees (79, 49.0 GB): his archive decision with the Game Agent. Do not plan removal before it.
2. The 4 churn-only worktrees (D4-Grounding, Door-UI-Sorting, FiveRoom, Game-Candidate): OK to reset `Settings.json` and remove?
3. D4-Opening-Hotfix, Room-Composition-B, ClaudeGuidancePort: per-folder go or keep.
4. `MOVE-NSC-FOLDERS.ps1`: fix (skip `.git` file) before any run.

## Queue
0. Ledger of owner keeps and releases: `C:/nscrev/reports/cleanup/owner-replies-20260918.md`. Next plannable batch from it: the 7 released `C:\nscrev` folders (~1.3 GB). Skip junctions (`LinkType`); `tmp-ga`, `review-tmp`, `branch-verify` stay. Ask Vincent before writing the script.
1. When Vincent says go on item 2 (Release Agent has answered; its folders are not among the four): write `cleanup-worktrees-<date>.md/.ps1` for the 4 churn-only + 4 clean detached worktrees (archive-ref each HEAD first, `git worktree remove` without `--force`, then `git worktree prune`; dry run by default).
2. Corrected copy of `MOVE-NSC-FOLDERS.ps1` under `C:/nscrev/reports/cleanup/` (skip worktrees; route `ProviderSmokeVerify-20260906` through `git worktree remove`), reviewed before it is offered.
3. Re-run `C:/nscrev/reports/cleanup-safety-scan.py` before each batch (wrapper: `C:/nscrev/reports/cleanup/data-20260918/run_scan_nowin.py`).
4. Classify the 3 detached HEADs on no ref (nsc058-exact-unity, nsc065-unity-import, NSC069-Review): archive refs first in any script.
5. Clone-only branches: 198 in 109 clones (both roots, 2026-09-18 21:25), not "~60". Vincent decides refs vs lapse.
6. The 330 "ask" directories from the `C:/NSC` inventory (a decision queue, not a backlog).
7. Tools extraction out of `C:/nscrev`: confirm Vincent's approval directly first; needs a junction at each old path; doc sweep is the Documentation Agent's.
8. Review `C:/NSC-History-20260918` on 2026-10-09: if `RESTORES.md` is empty, propose deleting it wholesale.
