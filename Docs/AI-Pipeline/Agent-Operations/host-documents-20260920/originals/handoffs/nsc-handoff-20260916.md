# No Safe Circle: handoff for a new local Claude Code session (2026-09-16)

Repository: `C:\NSC\NSC\NoSafeCircle`. Start the session in `C:\NSC`.

## Where things stand

- Local `main` is at `9a3d22c56`, "Playable build: chase enemy, fire-caster enemy, fireball, win and death screens". It has not been pushed.
- 36 wizard `.anim`, `.controller` and tile `.asset` files show as modified, but their content is identical to HEAD; only line endings differ. Leave them alone: don't commit or revert them, and stage only by exact path.
- 118 local branches are not merged into main. 17 branch tips are saved under `refs/archive/`.
- Context from the 9/15 session:
  - Journal: `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`
  - Memory: `C:\Users\VincentLiguori\.claude\projects\C--NSC\memory\` (see `branch-recovery-state.md` and `MEMORY.md`)
  - Trimmed transcript: `merge-session-sep15.txt` on the Desktop
- WebGL compression is now Disabled (`webGLCompressionFormat: 2`), which is what GitHub Pages needs. The old build in `F:\Portfolio\cathode26.github.io\NoSafeCircleFinal\Build` still has `.gz` files from the previous setting.

## Branch recovery: done

- Waves 1-3 are finished:
  - NSC-053 and NSC-017 were merged, each with a one-line fix.
  - The wave 3 pipeline branches were merged.
  - The door-crossing fix was merged.
  - NSC-093 enemy walk art was merged, and its `.meta` files were committed.
  - The superseded branches (NSC-054, NSC-042, NSC-089/090, NSC-050/052, the contract fixes, the NSC-051/052 door branches and NSC-032) were closed and archived.

## Branch recovery: next

The full list is in `C:\nscrev\reports\branch-recovery\waves45-inventory.md`.

1. **Wave 4: art branches.** Vincent picks each one visually.
   - **NSC-073 wizard hat fix.** The seven branches split into two versions of frame_005 (`ebcece952` or `805cb0e16`). Each branch changes 2 PNGs, `source-inventory.json` and `Docs/Art/Wizard/PIXELLAB_GENERATION.md`, and no `.meta` files. Vincent said to wait on Codex for this one.
   - **NSC-074 cardinal wizard walk.** Find the branch with a complete set; the four candidates differ. `assistant/nsc-074-cardinal-art` contains no art.
   - **NSC-077 stationary enemies.** `codex/nsc077-stationary-enemies` contains everything the other two branches have. All three conflict on `DoorPrototype.unity`; rebuild that scene from its builder instead of merging the scene file.
   - **NSC-065 doors.** `codex/nsc065-retained-art-review-20260914` has 8 door PNGs that main doesn't have.
   - **NSC-064 and NSC-063.** Visual picks.
2. **Branches the sweep marked safe to merge:** `codex/nsc061-source-review-20260914`, `assistant/nsc-075-integration-prep`, `assistant/integrate-background-plus-decomp`, `assistant/restored-meta-companion-fix`.
3. **Wave 5.** About 12 branches that are probably already covered by main; confirm each one.
4. **Spot-check `assistant/room-nsc-045`** before closing it. It edits contracts that were revised on 9/15.
5. **Pending cleanup:**
   - the NSC-053 and NSC-017 Codex branches and their worktrees;
   - GitHub copies of 5 closed branches (only after Vincent pushes);
   - the `wizard-art/codex-20260915` and `verify/*` branches.

## Rules

- Work one branch at a time. Show Vincent what a branch adds before merging, then wait for his go.
- Verify merges in the `C:\nscrev\branch-verify` worktree, never directly on main.
- Save each tip under `refs/archive/<branch>` before deleting the branch.
- Never push unless Vincent says so.
- Scenes are binary, so don't grep them to count objects.
- Unity test filters are separated by semicolons, not commas.
- Give Codex as much of the bulk work as possible.
- Keep replies short and lead with what Vincent needs to do.

## Other open items

- NSC-015 decomposition: the reviewer returned "revise", because the candidate weakened the parent's validation gates.
- Before implementing NSC-066 (the title screen), its contract needs an owner revision:
  - Point it at `DoorPrototypeGlobalSceneBuilder.cs`.
  - Specs: chase backdrop cycling each wizard with each enemy; keep the taglines; no solid panel; use `C:\NSC\SpaceInvaders` as the reference.
- Floor visuals are wrong, and door sorting is broken (owned by NSC-039). Fix both when the levels are rebuilt, and use the NSC-065 door art.
- Vincent approved NSC-085 (side-chamber wing) and NSC-088 (Spectral Decoy), and dropped NSC-004. Claude decides the design questions for NSC-007, 008, 009, 030 and 078; the evidence pack is in `C:\nscrev\reports\`.
