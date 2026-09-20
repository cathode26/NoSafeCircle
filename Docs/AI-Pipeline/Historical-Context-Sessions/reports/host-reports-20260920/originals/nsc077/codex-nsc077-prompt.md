You are implementing a Unity game task for No Safe Circle. The current directory, /workspace, is a standalone clone made for this job, on branch codex/nsc077-moving-enemy-art-20260917 at local main 95492e43d. You are running inside a Linux Docker container, so use `python3` where these instructions say `python`. The clone's git config already has core.autocrlf=true and core.filemode=false; keep them.

READ FIRST
1. AGENTS.md, CLAUDE.md, Docs/Engineering/ENGINEERING_STANDARDS.md and Docs/Engineering/UNITY_TESTING_POLICY.md.
2. The task contract, which is the authority for everything below: `python -B Pipeline/TaskGraph/taskcontrol.py show NSC-077`. The file is Tasks/NSC-077.yaml (JSON), revision 3, "Enemy Art Integration for the Existing Moving Enemies". Implement exactly what it requires. Where these instructions and the contract differ, the contract wins; report the difference.
3. The NSC-075 eight-direction wizard is the working pattern to follow. Study:
   - Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs. Screen direction uses camera Euler (30, -45, 0): screen right = X+Z, screen up = Z-X, with switch-margin hysteresis and deterministic ties.
   - Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs, especially BuildWizardAnimationAssets, ImportWizardSprite and ClearCookieImportDefaults. The builder sets Texture2D shape and resets m_ApplyGammaDecoding and m_CookieLightType, because a texture imported without a full importer block becomes a point-light cubemap cookie.
   - Tests/Editor/WizardArtIntegrationTests.cs and Tests/WizardAnimationPlayModeTests.cs.
4. The enemy art inputs:
   - Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source (16 idle PNGs, 128x128);
   - Source/Walk (96 walk PNGs, 176x176, feet normalized; see Source/Walk/inventory.json);
   - Docs/Art/Enemies/PIXELLAB_GENERATION.md and PIXELLAB_WALK_GENERATION.md.
   The melee north-east idle and walk frames were just corrected to a single cleaver. Do not change any art.

HARD RULES
- Work only on this branch. NEVER push. NEVER commit to main or move it. Never delete branches, tags or worktrees. Never touch C:\NSC\NSC\NoSafeCircle or any directory outside this clone.
- Commit as user.name "No Safe Circle Codex Worker", user.email "codex-worker@nosafecircle.invalid". Stage exact paths with `git add -- <path>`; never `git add .` or `-A`. Make small, logical commits with clear messages.
- Unity is NOT available to you. Do not try to run it. Never claim anything compiled or passed in Unity. The Game Agent runs the builder and the Unity tests after you finish.
- Never hand-edit generated or serialized Unity files: .unity scenes, .anim, .controller, .prefab and .asset files, or existing .meta files. The builder creates and updates generated content.
  - Two exceptions. A file rename the contract requires (for example EnemyFireballCaster.cs to EnemyLanternWispCaster.cs) must carry its existing .meta with `git mv`, so the GUID is kept. A brand-new C# file gets a new .meta with `fileFormatVersion: 2` and a fresh 32-hex guid.
  - If the contract requires removing a generated asset (FireCasterEnemySprite.asset), do what the contract says. If it assigns that removal to the builder, implement it in the builder; don't delete the file by hand.
- Stay inside the contract's exclusive resources. The contract names out-of-bounds files; do not touch those (DoorPrototypeSceneBuilder.cs, WizardAnimationController.cs, any .asmdef, ProjectSettings). If the work truly needs another file, stop and report instead of editing it.
- Do not change gameplay numbers or behaviour beyond what the contract requires: pursuit, keep-distance, navigation, attacks, projectiles, damage, health, registry and encounters.
- You may run Python checks, for example `python -B Pipeline/TaskGraph/taskcontrol.py validate`. Put any temp files under a `codex-tmp/` folder in this clone and do not commit them.
- If reality contradicts the contract or these rules, stop and report. Do not guess.

WORK
Implement NSC-077 rev 3: runtime scripts, the Editor builder, and the focused Edit Mode and Play Mode tests the contract names, with every acceptance criterion and completion gate covered where code and tests can cover them. Re-read every C# file you changed for compile errors, because nothing will compile it before the Game Agent does.

FINAL MESSAGE (concise report)
1. Every commit SHA and what it changes.
2. A table of NSC-077 AC-001..AC-008 and VAL-001..VAL-008, naming the file and test that covers each, plus which gates need the Game Agent (Unity) or Vincent.
3. The exact builder command(s) the Game Agent must run (menu path and batchmode -executeMethod), and the generated files expected afterwards.
4. The exact fully qualified Unity test filters, one line for Edit Mode and one for Play Mode, with entries separated by semicolons. Include the existing fixtures the contract says must still pass.
5. Anything you could not verify, any contract ambiguity and how you resolved it, and anything you did not do.
