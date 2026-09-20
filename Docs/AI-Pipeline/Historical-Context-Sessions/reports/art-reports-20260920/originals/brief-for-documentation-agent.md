# Brief for the documentation agent: a dedicated Art Director agent

From the branch-recovery session (nsc-33), 2026-09-16. Vincent asked for this, and asked that the documentation agent do it.

## What Vincent asked for

> "I think we need a art director agent to always do the art tasks. Like I have this game agent and it is creating a sub agent to do the art. But I think we need a more dedicated art director that knows exactly what we are trying to do and has all of the example art ideas and diablo / ultima idea when it does the art."

He expects:
- **An Art Director Claude Code agent.** Existing custom agents are user-level, in `C:\Users\VincentLiguori\.claude\agents\`; `gauntlet-observer.md` shows the frontmatter (name, description, model as a full ID, effort, tools).
- **A description** that makes every orchestrator route all 2D art work to it: generation, repair, extension, review packaging, and wizard/enemy/door/environment/prop/UI/title art.
- **A system prompt that carries the vision itself:** dark-but-cute horror-comedy isometric dungeon, Diablo II and Ultima Online inspired. Include concrete palette, lighting, outline, shading, detail and scale rules, and an identity bible for every approved asset family with reference image paths.
- **Routing updates** so the game, main and task orchestrators always delegate art to it. This supersedes or merges the Art Producer role (`C:\NSC\nsc-art-producer-guide.md`, and its prompt in `nsc-agent-launch-prompts.md`).

## Facts verified in the branch-recovery session (not yet in your doc set)

**Camera and facing.**
- The game camera is Euler (30, -45, 0). Screen right = world X+Z; screen up = world Z-X.
- PixelLab direction names are screen facings: north = back view walking up the screen; south = face; north-east = rear three-quarter facing up-right.
- NSC-075 shipped with the vertical axis flipped, and main's older four-direction wizard code had the same flip. Vincent caught it in Unity; the tests had encoded the same inverted mapping. The fix is commit `7fc15c528`.
- Rule: always verify facing in-game, not only in tests.

**Stub metas.**
- GUID-only `.meta` files from `run_crew.py unity_meta_bytes` import in Unity 6000.1 as a Cube with point-light cookie defaults (`textureShape: 2`, `cookieLightType: 2`, `applyGammaDecoding: 1`).
- Builders must set Texture2D shape and reset those fields. See NSC-075 commits `0d28b0bf5` and `bf97d116c`.
- Unity never rewrites a stub meta, so the problem stays invisible until a builder needs a Sprite.

**Identity defects already fixed.**
- NSC-073: the light female wizard's north-east walk frames 004-005 lost the hat and turned toward the camera. Merge `18089b060` uses version C (frame 005 is PixelLab index 6).
- NSC-074 cardinal rejects: lost long hair, a trouser-leg walk, and a changed tunic or face.
- NSC-063/093 melee brute: the duplicate cleaver facing north-east is fixed on branch `assistant/nsc063-nsc093-ne-single-cleaver-20260916`, awaiting Vincent's pick. The approved identity is ONE cleaver in the right hand, on the screen-right side.
  - The idle was repaired with `inpaint_image`.
  - The walk was regenerated with `animate_character` v3 using `custom_start_frame_url` = the approved idle's GitHub raw URL pinned to a commit. The first attempt passed at 2 generations.
  - Never re-animate a character record whose rotation image still carries a defect.

**Canvas conventions.**
- Wizard sources: 180x180, 180 PPU, feet pivot (0.5, 0), point filter, uncompressed.
- Enemy idles: 128x128.
- Enemy walks: losslessly padded to 176x176, with the true lowest opaque row at 131 (exclusive bound 132).
- PixelLab v3 canvases vary, so record raw size, bounding box and offsets.
- PixelLab keeps image jobs for only 8 hours: download immediately.

**Game state.**
- The game has moving enemies (a melee chaser and a fire caster) drawn with placeholder silhouettes (`MeleeEnemySprite` / `FireCasterEnemySprite`).
- NSC-077 is being rescoped to rev 3, "Enemy Art Integration for the Existing Moving Enemies", which absorbs NSC-094. A contract draft is in progress in worktree `C:\nscrev\nsc077-rev3`.

**Doors and architecture.**
- The NSC-065 bone-and-stone door sprites have been on main since `167a7f8e8`, unwired.
- NSC-064 architecture is unpicked; `codex/nsc064-connections-20260914` is the superset branch.

**Vincent's rules from today.**
- Never delete NSC-### branches.
- Successful (conformant) tasks are archived as usable projects under `C:\NSC\SuccessfullTasks\<ID>`. NSC-003, 005, 011 and 028 were added today.

## Heads-up about your files

- The branch-recovery session edited `C:\NSC\nsc-art-producer-guide.md` section 8 (the art queue): the Wizard, Enemies and Doors rows were updated to the state above.
- No Art Director drafts were written. The branch-recovery session's attempt was stopped after about a minute, so nothing conflicts.

## Sources worth reading

- The repo, on local main `7fc15c528`:
  - `Docs/Art/Environment/DUNGEON_ART_DIRECTION.md`;
  - `Docs/Art/**/PIXELLAB_GENERATION*.md`;
  - `Docs/Art/Enemies/generation-plan.md` and `inventory.md`;
  - the GDD art sections.
- `C:\NSC\AssistantControlEvidence\PIXELLAB-WIZARD-ART-RUNBOOK.md` and the other `*PIXELLAB*` prompts there.
- `C:\nscrev\reports\dungeon-reference-contact-sheet-20260914.jpg` and the approved contact sheets under `Docs/Art/`.
- Review renders from today:
  - `C:\nscrev\reports\branch-recovery\nsc073-art\` and `nsc074-art\`;
  - `C:\nscrev\reports\nsc063-cleaver\`;
  - `C:\nscrev\reports\nsc075\direction_labels_check.png`.
