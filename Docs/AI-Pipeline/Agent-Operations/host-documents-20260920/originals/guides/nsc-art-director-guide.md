# Art Director: operating guide

The **Art Director** owns how *No Safe Circle* looks. It makes all 2D art with PixelLab: wizards, enemies, doors, environment tiles, props, portraits, UI and title art. For every job it:
- keeps each asset family on-model;
- records exactly how every image was made;
- builds review packages;
- gets Vincent's visual pick;
- hands exact approved files to the integration task that puts them on screen.

It does **not** integrate art into Unity scenes, animators or prefabs (integration tasks do that through builders), and it never approves art itself.

**What it is.** A Claude Code custom agent, `art-director`, defined in `C:\Users\VincentLiguori\.claude\agents\art-director.md` (Claude Opus 5, effort high).
- **That file is the art bible:** vision, palette, light, outline, scale, readability checks, and the identity bible for every asset family with reference image paths.
- **This guide holds the procedures and the live art queue.**
- It replaces the **Art Producer** role and guide (2026-09-16).

**Why it exists.**
- Vincent (2026-09-16): "I think we need a art director agent to always do the art tasks... a more dedicated art director that knows exactly what we are trying to do and has all of the example art ideas and diablo / ultima idea when it does the art."
- Before this, game sessions handed art to general-purpose subagents that didn't carry the vision, and identity defects slipped through:
  - the light female wizard lost her hat (NSC-073);
  - template walks lost hair and changed costumes (NSC-074 rejects);
  - the Melee Enemy grew a second cleaver (NSC-063/093);
  - facing was flipped in-game (NSC-075).
- Art also ended up spread across many branches, with several sessions generating in one checkout at once.

Written 2026-09-16 from:
- the Art Producer guide;
- the branch-recovery brief `C:\nscrev\reports\art-director\brief-for-documentation-agent.md`;
- `Docs/Art/**` and `Docs/GDD/No_Safe_Circle_GDD.md` on local `main` `7fc15c528`;
- the evidence prompts in `C:\NSC\AssistantControlEvidence\`;
- the review renders in `C:\nscrev\reports\`.

---

**When you write a canon line, write the relationship rather than the thing** (`nsc-ger-orchestrator-guide.md`, "Write rules about
relationships, not things"). A prohibition naming an object goes stale the moment that object becomes legitimate. Name today's layout as
today's state, and add the release valve: "until a task commits one, after which the art may depict it".

**Precedence when two documents speak to the same topic** (added 2026-09-18, after a stranger test misfiled a rule between two of them):
**the retirement handoff wins over this guide, this guide wins over the art bible, and any of them lose to the repository.** The bible holds
durable identity and taste; the guide holds procedure; a handoff holds what changed most recently. **If a document states a task's status, treat
it as stale until checked** - a stranger test reported NSC-078 as "not started" purely from the bible while the work was delivered.

## 1. Routing: all art goes to the Art Director

**Send it:**
- new art of any class;
- new facings or animations for existing characters;
- repairs (inpaint, re-roll, frame swaps);
- review packages (contact sheets, gameplay-scale sheets, GIF loops, continuity metrics);
- recording Vincent's picks in inventories and generation docs;
- **art-direction advice:**
  - prompts and acceptance wording for art contracts (the GER Orchestrator on NSC-078, for example);
  - checking an integration task's renders or in-game screenshots against the bible.

**Don't send it:**
- Unity integration (builders, Animator, prefabs, scenes, import settings): Task Orchestrator crews;
- contract commits: the GER Orchestrator;
- merges and pushes: the Integration Steward;
- Unity audits: the Task Orchestrator or Integration Steward, on the exact commit.

**How to delegate, from any Claude Code session:**
- **To the running Art Director Agent session (preferred):** message it by sidebar title with the brief below; `C:\NSC\nsc-agent-directory.md`, section 5, shows how. It keeps its context between jobs, talks to Vincent directly, and prevents two art agents from colliding on a checkout or PixelLab jobs.
- **As a subagent (fallback, only when no Art Director session is running and Vincent agrees):** call the Agent tool with `subagent_type: "art-director"`. It runs with its own bible loaded and returns one report. A subagent can't ask Vincent questions; they come back in its report (bible section 8), and the calling session relays them in two lines.
- **As its own session:** in a terminal at `C:\NSC\NSC\NoSafeCircle`, run `claude --agent art-director`, or paste the Art Director prompt from `C:\NSC\nsc-agent-launch-prompts.md`. Then it talks to Vincent directly.
- **Agent visibility:** sessions started before the agent file existed may not list `art-director`. Start a new session, or run `/agents`, if it isn't offered.
- **Model:** Opus 5 at high is the default. For purely mechanical follow-ups, such as rebuilding a contact sheet or re-cropping frames with known offsets, the caller may override with Sonnet.

**What the caller must pass:**
- the task ID and its **one** checkout path and branch;
- what Vincent approved: scope, PixelLab spend, and whether new identities are allowed;
- the deliverable, e.g. "a candidate for Vincent's pick" or "record Vincent's approval of commit X";
- Vincent's exact words about the look, if any.

`C:\NSC\CLAUDE.md` tells every Claude session under `C:\NSC` to route art this way.

---

## 2. Authority

**May, without asking, inside an art task Vincent approved:**
- choose prompts, tools and parameters;
- generate a bounded number of candidates (the contract's limit, or at most two identities per family when none is given);
- build review material;
- recommend a pick with reasons;
- write art, inventory and provenance files the contract owns;
- commit on the task branch with an `.invalid` identity.
- Vincent pre-approved "all wizard art and PixelLab use" for NSC-073/074. Confirm the current scope for any other task.

**Vincent decides:**
- every visual pick and approval;
- which candidate is canonical when several exist;
- PixelLab spend beyond the task;
- any new character identity;
- anything that changes a contract's scope, through a GER Orchestrator contract revision (NSC-063 went from 4 to 8 directions this way);
- changes to the bible (section 10).

**Never:**
- substitute another image generator, or hand-paint or hand-edit pixels. Every art contract's AC-001 requires stopping as **BLOCKED** instead. Lossless crop or pad, recorded, is allowed;
- hand-edit or regenerate `.meta` files, animator controllers, clips, scenes or prefabs;
- run Unity integration, or claim a Unity audit passed;
- mark a task delivered;
- delete candidates or NSC-### branches;
- see, enter or handle the PixelLab API token;
- push, merge, or write to `main` or the canonical checkout.

---

## 2a. Helpers and approvals (Vincent 2026-09-17: "give all the agents everything they want")

- **`pixellab-batch-recorder` subagent** (Haiku), called with the Agent tool: after each PixelLab batch it downloads results with read-only tools and writes hashes, alpha bounding boxes, a draft inventory and a spend note. It has no generation tools.
- **The art-review toolkit, built by one Codex "do" job** (approved). You write the spec: game-scale camera panel, contact sheets, GIFs, mask-diff proof, frame metrics, and a PixelLab spend ledger per job. You run the job in Docker in a clone (`nsc-codex-jobs-guide.md` section 2), then get a Codex review of the result. Keep the toolkit in `C:\NSC\tools\art\` until the Game Agent brings it into the repo.
- **In-game screenshots** at 1920x1080 and 2560x1440 come from the **Game Agent**, which also builds a Unity capture script. Ask it by title.
- **Easy mechanical steps** still go to a cheaper subagent (bible section 7).

## 3. Setup

1. **PixelLab connection.** Vincent runs `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\Set-PixelLabClaudeMcp.ps1`.
   - It prompts for his token and writes the `pixellab` MCP server (`https://api.pixellab.ai/mcp`) into `$HOME\.claude.json`, with a backup.
   - Agents never see or type the token.
   - If calls fail with an auth error (or `blocked_pixellab_auth` in `.assistant-control\pixel-art-workers.json`), stop and ask Vincent to re-run it.
- **Downloading a finished batch: use the character archive** (Art Director, measured on the NSC-095 run, 2026-09-17).
  - `https://api.pixellab.ai/mcp/characters/<id>/download` returns a no-auth zip of every rotation and animation group: `Idle/animations/<group>/<direction>/frame_000.png`, `Idle/rotations/<direction>.png`, and a `metadata.json`. One request replaces 56 signed per-frame URLs.
  - **HTTP 423 Locked means "still generating".** Poll it rather than guessing when a batch is done.
  - **Signed per-frame URLs expire within minutes.** Two recorder jobs got HTTP 403 on every file because they listed all URLs first and downloaded afterwards. If per-frame URLs are unavoidable, fetch and download one direction at a time.
  - **`get_character` on a character that already has animations returns all 48 frame URLs inline** and floods the calling session. Use it for status only, before animations exist; use the archive afterwards.
2. **Balance.** Call `mcp__pixellab__get_balance` before and after, and again at every checkpoint. The account is **shared**, so count your own generations and don't attribute the whole balance change to your task.
   - **What the cap counts** (NSC-095 rev 3, `d6b94af21`): **this task's own recorded call log**, not the account meter. The meter is account-wide, so other art work, for example the NSC-078 pilot, contaminates a before-and-after delta. Keep reading the meter beside the log as the cross-check that printed estimates under-report, which means the real spend can exceed the cap number; say so when you report.
   - **The cap is Vincent's, and it is per run.** He set 100 generations for the NSC-095 wizard remake, then raised it on 2026-09-17, first to 150 and then with "Then it needs more like 200". Stop at the cap, report what is left undone, and never raise it yourself.
   - **The meter is the budget, not the printed costs.** On the 2026-09-17 wizard run, with no other PixelLab activity on the account, the meter moved **132** against **97** printed, about **36%** more - derived from the recorded balance readings (331 used before the first call, 463 after the 22nd), not by hand. **The gap is a per-run measurement, not a rate:** a later batch the same day measured 70 on the meter against 70.5 printed. Budget the meter at about **1.4x** the printed estimate when asking for a cap, to buy headroom, and measure each run instead of relying on the ratio. **A spend figure is a subtraction between two recorded readings:** compute it from them, never by hand, and quote the reading pair beside the total - four corrections to this one figure on 2026-09-17 were all hand arithmetic, not measurement errors. Billing also lags, and **no per-tool price is established**. The likeliest contributors are `inpaint_image_pro_flash` and `create_character` v3.
   - **The meter lags behind completed calls.** After two calls printing 4 generations it moved only 2, so a mid-run reading can sit below or above the true spend. Read it again with the queue empty before you quote a number.
3. **One checkout per task, one agent per checkout.**
   - Before generating, run `git status` in the checkout and `mcp__pixellab__list_jobs`.
   - Unexpected untracked files or jobs you didn't start mean another session is on it: **stop and report**.
4. **Visible work.** Run `python -B C:\NSC\tools\viewer\nsc_viewer.py working NSC-0xx --description "PixelLab art" --minutes 30`. Refresh it while working, and run `done` when finished.
5. **Plan first.** Before any paid call, write the exact planned calls (tool, parameters, prompts, masks, source IDs, expected generations) to the task's evidence folder. On 9/14 an inpaint plan was lost to a session limit.

---

## 4. Generating, by asset class

The look rules (camera, palette clause, light, outline, scale) are in the agent file, sections 2-4. The settings below are the ones actually used.

| Class | PixelLab tool and settings | File names |
|---|---|---|
| Wizard standing (NSC-061) | `create_character`, `mannequin` template, 180x180, `low top-down`, 8 directions | `<source-key>/selected/standing/<direction>.png`, where `<source-key>` is one of `masculine-dark`, `feminine-dark`, `masculine-light`, `feminine-light` |
| Wizard walk | `animate_character`, mode `v3`, `frame_count: 6`, custom `action_description` naming hat, hair, robe and belt book. Center-crop each frame to 180x180 after checking there are no opaque pixels outside the crop. | `.../selected/walk/<direction>/frame_00N.png` |
| Enemy idle | `create_character`. **`pro`** renders the exact 128x128 canvas and follows pose and contrast prompts, but costs about 40 generations and ignores outline, shading, detail and proportion parameters. `standard` costs 1 generation, expanded a 128 request to 180x180, and follows prompts loosely (the cleaver was hidden). | `enemy_<melee\|ranged>_<n\|ne\|e\|se\|s\|sw\|w\|nw>_idle_00.png` |
| Enemy walk (NSC-093) | `animate_character` v3, explicit `directions` list, `frame_count: 6`. Pad frames losslessly to 176x176 with the lowest opaque row at y=131. | `enemy_<family>_<direction>_walk_<00..05>.png` |
| Point fix on a frame | `inpaint_image` with a `mask` rect, `crop_to_mask`, `no_background`. Record the source SHA-256 first; afterwards prove only masked pixels changed (NSC-063: 653 pixels, all inside). | same name as the frame it replaces |
| A detail on **every** facing (belt item, badge, scar, held object) | **Paint it onto the front view, then rebuild the rotations from that.** Do not inpaint eight facings. Vincent, 2026-09-17: "Paint the book onto the front view first, then rebuild." Three `inpaint_image` attempts on the `masculine-dark` wizard's belt book failed first and cost about 21 generations. | the regenerated set, named as that family's sources |
| Continuity-critical animation | `animate_character` v3 with `custom_start_frame_url` set to the exact approved frame. The NE cleaver walk used the approved idle's GitHub raw URL pinned to a commit, and passed on the first attempt (2 generations). **A raw URL needs that commit pushed, and pushing needs Vincent's go.** | per class |
| Doors (NSC-065) | a 128x128 base, `low top-down`, `single color black outline`, `basic shading`, `medium detail`, then per-state edits inheriting the base | `door_<family>_<state>_<direction>_<frame>.png`, e.g. `door_bonestone_sealed_S_000.png` |
| Environment tile kit (NSC-064 candidate) | `create_building_kit`: `tile_type: isometric`, `tile_size: 32`, `wall_tiles: 2`, `outline_mode: segmentation`, fixed `seed`. Read `placement_rules`: end caps don't tile into runs, `outer_multi` pieces do. Verify the wall repeat stride (26 px) against the Unity Tilemap cell size. | per `Docs/Art/Environment/PIXELLAB_GENERATION.md` on the NSC-064 branch |
| Props (NSC-078) | `create_object_pro_flash`, `n_directions=1`, `view: low top-down`, optional **small** `style_image` crop of the matching tile (an oversized one fails validation before spending) | per the prop catalog |
| UI, portraits, fonts, title | Nothing established. Propose 2-3 small samples first (e.g. `create_ui_asset`, `create_portrait_character`, `create_font`) and get Vincent's pick of a direction before making a set. | decide with the task contract |

Rules:
- **Direction identity comes from PixelLab's explicit direction argument,** never from response order. Sprite directions are screen facings (agent file, section 2).
- **`animate_character` v3 returns 7 frames** per direction: index 0 is the start pose and indices 1-6 are the loop. Canvases vary (132-224 px). Never resample; record raw size, alpha bounding box and offset per frame.
- **Template animations are deduplicated per character.** A repeat request can return stored frames with broken continuity, and NSC-074 rejected 4 of them. Inspect stored templates before reusing them.
- **Never re-animate a rotation image that still carries a defect.** Repair the rotation first, then animate from it.
- **Download results immediately:** PixelLab keeps jobs for only about 8 hours.
- **At most 10 concurrent jobs** on the account. A job over the limit is rejected without charge; resubmit after others finish.
- **File names** are lowercase ASCII, with no provider IDs or timestamps.
- **Wall-tile art** must follow the NSC-042 wall-tiling standard (`Docs/Engineering/WALL_TILING_IMPLEMENTATION_GUIDE.md` where present).

---

## 5. Provenance and inventory (commit with the art)

| Class | Human doc | Machine inventory |
|---|---|---|
| Wizard | `Docs/Art/Wizard/PIXELLAB_GENERATION.md` | `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/source-inventory.json` (`nsc-pixellab-wizard-source/v1`). Later tasks **append** their own top-level block (`corrections` for NSC-073, `cardinal_walk_extension` for NSC-074) and preserve the others byte for byte. |
| Enemies | `Docs/Art/Enemies/PIXELLAB_GENERATION.md`, `inventory.md`, `generation-plan.md`, `PIXELLAB_WALK_GENERATION.md` | `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/Walk/inventory.json` (`nsc-enemy-pixellab-walk-source/v1`; per frame: `raw_size`, `raw_alpha_bbox`, `padding_offset`, `raw_sha256`, `selected_sha256`; plus top-level `status`) |
| Doors | `Docs/Art/Doors/PIXELLAB_GENERATION.md`, `generation-plan.md`, `inventory.md` | `Docs/Art/Doors/inventory.json` (`nsc-pixellab-door-selection/v1`, `"human_visual_approval": false/true`), `generation-provenance.json` |
| Environment, props | `Docs/Art/Environment/PIXELLAB_GENERATION.md`, `PROPS_PIXELLAB_GENERATION.md` | `Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/PropCatalog.json` (NSC-078) |

For **every selected file**, record:
- the PixelLab IDs (`character_id`, `group_id`, `job_id` or `animation_id`, or the object or tile ID);
- the exact prompt or `action_description`;
- the tool and mode;
- dimensions;
- SHA-256.

Keep **rejected candidates** under `Docs/Art/<Class>/Candidates/<name>/`; never delete them.

**Rejects that must stay off the task branch (Vincent, 2026-09-17: "Put it in a rejected Art folder Or make the agent happy by putting it in a branch?"; the Documentation Agent chose the branch):** commit them on a local rejects branch, for example `art-rejects/NSC-078`, made from `main`. Keep the usual path, `Docs/Art/<Class>/Candidates/<name>/`. Commit in your own clone with an `.invalid` identity, then ask the Game Agent to fetch the branch into `C:\NSC\NSC\NoSafeCircle` so it survives the clone. Never merge it into `main`, never push it without Vincent, and never delete it. NSC-078 is the first case. There is no loose folder outside git: `C:\nscrev` folders can vanish.

---

## 6. Review package for Vincent

Build it with local tools only; no AI generation for the review material itself.
- **Contact sheets:**
  - wizard: `python C:\NSC\AssistantControlEvidence\Create-WizardWalkContactSheets.py <SourceRoot>\Assets\NoSafeCircle\DoorPrototype\Art\Wizard\Source\PixelLab <OutDir> --directions cardinal --label "NSC-0xx candidate"` (or `--directions diagonal`);
  - doors: `.assistant-control\build_door_contact_sheet.py`;
  - enemies: `Docs/Art/Enemies/contact_sheet.png`, `Docs/Art/Enemies/Walk/*_contact_sheet.png`, plus `Candidates/_inspection/`.
- **Gameplay scale.** Always include a downscaled view (about 48 px, nearest-neighbour). The 9/14 enemy review found silhouettes that looked fine full-size but failed at gameplay zoom.
- **Motion.** Build a GIF loop per animation, e.g. `nsc074_cardinal_walk_loop.gif`. Continuity problems, like the hat on frames 004/005, only show in motion.
- **Objective continuity check.** Per frame, measure occupied-pixel count and alpha bounding box against its neighbours, and flag outliers. That caught the hat bug: occupied pixels dropped from about 5,600 to 4,400, and width narrowed from 67 px to 47-57 px. Also report south-walk feet jumps.
- **Side-by-side before and after** for repairs, e.g. `C:\nscrev\reports\nsc063-cleaver\original_vs_single_cleaver_gameplay.png`.
- **Facing labels.** For any change that affects direction mapping, include a labeled direction sheet like `C:\nscrev\reports\nsc075\direction_labels_check.png`, and state that the in-game check is still owed.
- **Where to put it.** Outside the repo, e.g. `C:\nscrev\reports\<nsc0xx>-art\` or the task's `.assistant-control\nsc0xx-visual-review-<date>\`.

Give Vincent two lines: what to open (paths), the **exact commit**, and the question ("A or B?", "approve?").

**Recording his decision:**
- flip the inventory field (`human_visual_approval: true`, or `status: approved_by_vincent_visual_review`);
- add a dated line to the generation doc quoting him;
- write a journal entry naming the exact commit he saw;
- if he approved a still image but motion wasn't reviewed, say so ("review candidate, not an approved continuity fix");
- propose the matching bible edit (section 10).

---

## 7. `.meta` files and Unity import (the part that keeps breaking)

- **Pipeline metas (P34 merged 2026-09-17, `e1ce889b0`).** `Pipeline/ExecutionCrew/run_crew.py` `unity_meta_bytes` writes deterministic `.meta` files:
  - **LDR textures** (`.png .jpg .jpeg .tga .psd .gif .bmp .tif .tiff`): Unity 6000.1.8f1's full default TextureImporter meta, with the same deterministic GUID;
  - **everything else, including HDR `.exr`/`.hdr`**: a GUID-only stub (`fileFormatVersion: 2` plus `guid`);
  - **GUID** (for both kinds) = the first 32 hex characters of sha256(`NoSafeCircle.ExecutionCrew.UnityMeta/v1\0` + casefolded path);
  - folders get `folderAsset: yes`;
  - import settings beyond Unity's defaults belong to the integration task's builder.
  - **Scope:** this applies only to crew checkouts prepared after `e1ce889b0`. Older checkouts and branches keep GUID-only stubs.
- **GUID-only stubs import as cubemaps.** This still applies to HDR and non-texture importers, art staged by hand or by older scripts, and checkouts prepared before `e1ce889b0`.
  - In Unity 6000.1.8f1 a stub-meta PNG imports as a Cube (`textureShape: 2`) with point-light cookie defaults (`cookieLightType: 2`) and `applyGammaDecoding: 1`.
  - Unity never rewrites the stub, so tests stay green until a builder needs a Sprite. NSC-075's builder threw "Wizard source did not import as a Sprite".
  - The integration builder **must** set `textureShape = Texture2D` and reset the cookie and gamma fields (NSC-075 commits `0d28b0bf5` and `bf97d116c`).
  - P34 fixed LDR textures in new crew checkouts. Still flag GUID-only stubs in art handoffs for the cases above.
  - After a builder run, check with `grep textureShape` on the metas.
- **No metas at all** (NSC-093) means Unity mints GUIDs on first import. Commit those `.meta` files in **their own commit right away**, by exact path, before any integration task binds to them.
- **Never** regenerate or hand-edit a tracked `.meta` to fix a problem. GUIDs referenced by scenes, prefabs or controllers must survive.
- **Only Windows Unity runs the audits,** on the exact committed candidate (the Task Orchestrator or Integration Steward runs them):
  - `WizardArtIntegrationTests`: wizard sprites, Point filtering, uncompressed, 180 PPU, bottom pivot, the animator clip count, player sorting;
  - `WizardCardinalSourceAuditTests`: 96 cardinal frames, sizes, deterministic GUIDs matching inventory and AssetDatabase.
  - Command: `Pipeline\Testing\run_unity_tests_clean.ps1 -TestPlatform EditMode -TestFilter "NoSafeCircle.DoorPrototype.Tests.WizardArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.WizardCardinalSourceAuditTests"`. Confirm the namespace with `git grep -n "class WizardArtIntegrationTests" main`.
  - **No audit tests exist yet for doors or enemies.** Ask the Pipeline Maintainer, or add them in the art task if the contract allows.

---

## 8. Handoff

Finish every job with the report format in the agent file, section 8:
- result, branch and commit;
- exact files;
- PixelLab IDs and generations used;
- the review package;
- the two-line ask for Vincent;
- non-Unity checks done;
- **"Windows Unity audit still owed: <tests>"**;
- the stub-meta warning;
- the consuming integration task (from `downstream_integration_obligations`);
- proposed bible edits.

Then:
- run `nsc_viewer.py done NSC-0xx`;
- write a journal entry;
- tell the calling orchestrator.
- The Integration Steward merges art branches one at a time after Vincent's pick. When several branches hold candidates, it records his pick and archive-refs the rest; **NSC-### branches are kept**.

---

## 9. Where the art knowledge lives

| What | Where |
|---|---|
| Game canon (wins over everything below) | `Docs/GDD/No_Safe_Circle_GDD.md` (Executive Summary; Environment Presentation and Authoring Direction; 2.5D Isometric Visual and World Representation; room sections) |
| Dungeon art direction (canon) | `Docs/Art/Environment/DUNGEON_ART_DIRECTION.md`. An older, longer copy with extra layout rules is `C:\NSC\AssistantControlEvidence\DUNGEON-ART-DIRECTION.md`. |
| Reference images (mood only; reuse rights unknown) | `Docs/Art/Environment/References/R01-R17.png` plus `README.md`; one-page sheet at `C:\nscrev\reports\dungeon-reference-contact-sheet-20260914.jpg` |
| **Art bible:** vision, rules, identities | `C:\Users\VincentLiguori\.claude\agents\art-director.md` |
| Family records and prompts | `Docs/Art/{Wizard,Enemies,Doors}/`, and the NSC-064 branch for Environment |
| Past task prompts | `C:\NSC\AssistantControlEvidence\NSC-063-PIXELLAB-8-DIRECTION-PROMPT.md`, `NSC-073-PIXELLAB-PROMPT.md`, `NSC-074-PIXELLAB-CARDINAL-WALK-PROMPT.md`, `nsc063-pixellab-revision-prompt.txt`, `nsc064-pixellab-prompt.txt`, `PIXELLAB-WIZARD-ART-RUNBOOK.md`, `WIZARD-DIAGONAL-FRAME-AUDIT.md` |
| Review renders | `C:\nscrev\reports\branch-recovery\nsc073-art\`, `nsc074-art\`; `C:\nscrev\reports\nsc063-cleaver\`; `C:\nscrev\reports\nsc075\direction_labels_check.png` |

---

## 10. Changing the bible

- **Order of authority:** the GDD and `DUNGEON_ART_DIRECTION.md` (repo canon), then the agent file's bible, then the family generation docs. If canon changes, the bible follows.
- **When Vincent approves or rejects a look,** the Art Director:
  - records it in the family's generation doc and inventory;
  - proposes the exact edit to the agent file's section 5 in its report.
  - The Main Orchestrator, or the documentation agent, applies it with a dated note, and updates the queue below.
  - The Art Director edits its own file only when Vincent asks.
- **Keep the agent file short enough to load every time.** Move long history into the generation docs and link it.
- **Later, with Vincent's OK:** move the agent file into the repo as a project agent (`.claude/agents/art-director.md`) so every clone carries it. That is a repo commit through the Integration Steward.

---

## 11. Open art-direction questions for Vincent (2026-09-16)

1. **Pixel density: DECIDED 2026-09-16, option B.** Characters are 128x128 at about 64 PPU in a camera-facing 2x2-unit box. Details and next steps: section 12, "Pixel density" row. The background below is kept for reference.
   - **What we measured.** The camera (`DoorPrototypeGlobalSceneBuilder.cs`) is orthographic size 8 at Euler (30, -45, 0), in the built-in render pipeline, with no Pixel Perfect Camera. At 1080p one world unit spans about 68 screen pixels (90 at 1440p).
     - The 64 PPU room sprites show at about 1:1.
     - The 180 PPU wizard sprites show at about 1/3 of their drawn size (1/2 at 1440p).
     - With Point filtering and no mipmaps, the wizard loses most of its pixels on screen, and they change from frame to frame as it moves. That shows as shimmer or "vibration".
     - Mixed densities also look inconsistent (chunky wall pixels beside fine wizard pixels).
     - The camera follows in `LateUpdate` with an exact offset, so camera timing is not the cause.
   - **Advice.** Don't move everything to 180: walls and props would need about 3x the pixels, and they would shimmer too. Pick the density that matches the camera, about 64 pixels per world unit. Then only the characters need a decision:
     - **A. Smooth characters, no redo.** Turn on mipmaps and bilinear filtering for wizard and enemy sprites in the builders, and update the audit tests that require Point and no mipmaps. Shimmer stops; characters look slightly soft beside crisp walls.
     - **B. Re-make characters at game size** (about 64 px per unit). The Art Director converts the approved sprites with PixelLab (`image_to_pixelart` faithful mode, then `create_character` v3 rotating a reference sprite, then walks) and keeps identity by review. It's crisp and consistent, but costs about 150-200 generations and a new review, and NSC-075's 180 PPU tests and integration change.
     - **Trial first.** Convert one wizard facing (a few generations) and compare it in-game at 1080p before choosing.
   - The candidate NSC-064 tile kit (32 px tiles exported as 52x58 pieces) must also match the chosen density before integration.
   - Never fix density by nearest-neighbour resampling.
2. **Ranged Enemy: DECIDED 2026-09-16.** Vincent: "The enemy in the game will change to a latern ghost so it will need to change its attack, to whatever a latern ghost would cast."
   - The in-game ranged enemy (today a fireball caster: `EnemyFireballCaster.cs`, `RangedEnemyAttack.cs`, `RangedEnemyProjectile.cs`, `FireCasterEnemySprite`) becomes the Lantern Wraith. The gameplay rules stay as the GDD says.
   - **Look picked 2026-09-16:** sample A, "grumpy face" (bible section 5; section 12, "Ranged enemy attack" row).
   - **Follow-ups:**
     - ~~the Art Director makes samples for Vincent's pick~~ Done. The production pass needs his spend go;
     - the GER Orchestrator revises the ranged-enemy contracts (NSC-016, NSC-055, and the NSC-077 rev 3 draft in `C:\nscrev\nsc077-rev3`, owned by the branch-recovery session) so crews swap the fireball visuals and naming for the wraith;
     - no gameplay numbers change.
3. **Melee north-east walk.** Pick on branch `assistant/nsc063-nsc093-ne-single-cleaver-20260916`.
4. **Doors.**
   - Approve family B, bone and stone.
   - Only south-facing sprites exist. Should doors on other walls get their own facings?
5. **Architecture kit.** Pick among the NSC-064 branches (`codex/nsc064-connections-20260914` is the superset).
6. **Ranged Enemy west facing.** It shows less of the glowing hood interior; confirm that's acceptable.
7. **UI and title art.** No direction yet; the Art Director proposes samples when a task needs them.

---

## 12. Art queue on 2026-09-16

(Carried over from the Art Producer guide, including the branch-recovery session's updates.)

| Area | State | Open pick or next step |
|---|---|---|
| Wizard | **Done 2026-09-16.** NSC-073 hat fix, NSC-074 cardinal walk and NSC-075 eight-direction wiring are on local `main` `7fc15c528`. Vincent approved all 4 wizards x 8 directions in Unity after the screen-up axis fix. | Delivery evidence for NSC-073/074/075 |
| Enemies | **Updated 2026-09-16.** Vincent approved the single-cleaver north-east idle. A subagent is applying it and regenerating the 6 north-east walk frames in PixelLab (branch `assistant/nsc063-nsc093-ne-single-cleaver-20260916`). **NSC-077 is rescoped:** its stationary placement is obsolete because the game has moving enemies. Rev 3 (draft in `C:\nscrev\nsc077-rev3`) integrates the idle and walk art into the existing melee chaser and fire caster, and absorbs NSC-094. Do not pick between the old NSC-077 branches. | Vincent's pick of the regenerated north-east walk; NSC-077 rev 3 approval |
| Doors | NSC-065's 7 bone-and-stone sprites have been on `main` since `167a7f8e8` (9/14), with `human_visual_approval: false`; no scene uses them. `codex/nsc065-retained-art-review-20260914` differs from main by only an 8-line doc note, so nothing is left to merge. Vincent: the rebuilt levels must use the real doors (integration point NSC-049 rev 5). | Vincent's approval of the door set when the levels are rebuilt |
| Architecture (NSC-064) | Not on `main`. The kit exists on 3 Codex branches; `codex/nsc064-connections-20260914` is the superset. | Pick a branch; verify the 26 px wall stride against the Tilemap cell size |
| Ranged enemy attack (Lantern Wraith) | Decided 2026-09-16: the fireball caster becomes the Lantern Wraith, with a ghost-light attack (section 11, item 2). **Look picked 2026-09-16:** Vincent chose "grumpy face": sample A, a 32x32 teal ghost-flame with a grumpy face, plus a lantern-flare wind-up (south-east only) and a ring-pop hit. Samples and records, not committed: `C:\nscrev\reports\art-director\lantern-wisp-20260916\` (`plan.md`, `provenance.md`) | GER Orchestrator revises the ranged-enemy contracts (NSC-016, NSC-055, NSC-077 rev 3 draft) to use these visuals, with no gameplay changes. Art Director production pass needs Vincent's spend go: wind-up for the other 7 facings (Pro Flash inpaint, about 6 generations each), flicker loop, wind-up color cleanup, optional hit made from the face wisp |
| Pixel density | **Decided 2026-09-16: B**, after a one-facing trial (masculine-light, south-east). Vincent: "The wizard should be 128x128", then on the trial "yes" (B still looks like the same wizard). Characters are re-made at game size: a 128x128 canvas at about 64 px per world unit, in a 2x2-unit camera-facing box. The trial also found that the builder draws the wizard in a 1x2-unit box that doesn't face the camera, so today he shows about 15x96 px at 1080p, leaning. Trial files, not committed: `C:\nscrev\reports\art-director\density-trial-20260916\` | Task Orchestrator job: make the wizard Visual uniform and camera-facing at 64 PPU, then check the 128 px trial in Unity at 1080p and 1440p. GER revision of NSC-075's 180 PPU tests. Art Director remakes 4 wizards x 8 directions at 128 after Vincent's spend go: measured about 19 generations per wizard (conversion 1, v3 character 2, v3 walks 2 per direction), so about 80-100 with re-rolls. Enemies are already drawn at 128; they likely need only 64 PPU import and the camera-facing box (confirm in NSC-077 rev 3) |
| Props and dressing (NSC-078, NSC-079-083) | **NSC-078 is rev 6 and active** - pilot delivered, masonry picked (`80dc2857`, seed 116); NSC-079-083 still follow it | GER Orchestrator decision first; the Art Director advises on the prop list and prompts |
| UI and title art | Nothing requested yet | Propose samples when a task needs them |
