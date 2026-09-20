You are continuing a Unity game task for No Safe Circle. The current directory, /workspace, is a standalone clone made for this job, on branch codex/nsc077-moving-enemy-art-20260917. You are running inside a Linux Docker container, so use `python3` where these instructions say `python`. The clone's git config already has core.autocrlf=true and core.filemode=false; keep them.

WHERE THINGS STAND
- An earlier Codex pass implemented NSC-077 contract revision 3 in two commits:
  - 1099419f3 "Implement enemy art animation integration";
  - 3e90e78c6 "Add focused enemy art integration tests".
- The Game Agent then rebased those two commits onto local main 25fdc505d, so HEAD is 3e90e78c6. Their pre-rebase SHAs were cc4ff8899 and 139e37795.
- 25fdc505d is NSC-077 contract revision 4. It changes only Tasks/NSC-077.yaml, and it is now the authority.
- Nothing has been compiled or run in Unity yet.

YOUR JOB
Bring the branch from revision 3 to revision 4. Change only what revision 4 changed. Everything else from the first pass stays as it is unless revision 4 forces a change.

READ FIRST
1. AGENTS.md, CLAUDE.md, Docs/Engineering/ENGINEERING_STANDARDS.md and Docs/Engineering/UNITY_TESTING_POLICY.md.
2. The exact contract change: `git diff 95492e43d 25fdc505d -- Tasks/NSC-077.yaml`. Then read the full revision 4 contract with `python -B Pipeline/TaskGraph/taskcontrol.py show NSC-077`, or Tasks/NSC-077.yaml, which is JSON. Where these instructions and the contract differ, the contract wins; report the difference.
3. The first pass: `git diff 25fdc505d HEAD`, especially:
   - Assets/NoSafeCircle/DoorPrototype/Editor/World/EnemyAnimationAssetBuilder.cs
   - Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs
   - Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyAnimationController.cs
   - the EnemyArtIntegrationTests and EnemyAnimationPlayModeTests fixtures.
4. DoorPrototypeSceneBuilder.CreateWorldSpriteVisual in Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs. Read its signature, including the rotation and world-size parameters. You call it; you never edit that file.

WHAT REVISION 4 CHANGED (Vincent's pixel-density decision B)
1. AC-002, AC-003 and VAL-001: pixel density.
   - All 112 enemy sprites import at one named pixels-per-unit constant of 64, with FilterMode.Point and no mipmaps. The first pass used 128 with the wizard importer's filter and mipmap settings; replace that everywhere.
   - At 64, a 128x128 idle still is 2x2 world units and a 176x176 walk frame is 2.75x2.75 units. The character stays the same pixel size, so an enemy does not change size between idle and walk.
   - Ground-line pivots do not change.
   - VAL-001's importer audit must check the shared 64 constant, Point filter and no mipmaps on every enemy importer.
   - If Vincent later wants a different enemy size, the contract says only this constant changes. Nothing else may encode the enemy size: no hard-coded 128, no 1x2 or 2x2 world-size numbers in the builder, and a test may assert the constant's value once.
2. AC-003 and AC-008: the Visual transform.
   - Each enemy Visual is still created through DoorPrototypeSceneBuilder.CreateWorldSpriteVisual. Pass world size (1, 1) so its scale is uniform, and keep the NSC-039 ground-contact position and sorting.
   - The Visual's WORLD rotation always equals the fixed isometric camera rotation, Euler (30, -45, 0), which is DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles. At build time, pass it as the Visual's rotation.
   - At runtime, NavMeshAgent rotates the MeleeEnemy root while it moves. EnemyAnimationController must restore the Visual's world rotation every frame after movement has been applied, so the sprite never leans, thins or turns edge-on. Choose the Unity callback and ordering that actually run after the NavMeshAgent's rotation update, and explain the choice in a short code comment.
   - Also check whether anything rotates the LanternWraith root, for example facing the wizard. The restore must hold for both enemy types.
   - Do NOT change NavMeshAgent settings (for example updateRotation) to achieve this. Do not change any gameplay component.
   - EnemyAnimationController is a runtime script, so it cannot reference an Editor-assembly constant. Keep one source of truth for the camera rotation where the assembly boundaries allow it. If you need a runtime copy of (30, -45, 0), add a test that fails when the runtime value and DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles differ.
3. VAL-003 (saved scene, Edit Mode): every MeleeEnemy and LanternWraith Visual has a uniform scale of 1 and the camera-facing world rotation, in addition to the first pass's checks. Compare rotations with a small angle tolerance.
4. VAL-004 (Play Mode): for both enemy types, after the enemy root is rotated as NavMeshAgent does while moving, the Visual's world rotation still equals the camera rotation. Make the test fail against a controller that does not restore the rotation.
5. AC-007 and INT-002 only record that Vincent picked the "grumpy face" lantern wisp look. Its production art comes in a later task. The teal orb stand-in stays exactly as the first pass made it. Add no new wisp art, sprites or effects.
6. VAL-008 is Vincent's in-game check, which now also covers size and lean. There is nothing to code for it.

Also update code comments, test names and messages that still describe the 128 stand-in, the 1x2 Visual size or the wizard filter and mipmap settings.

If an existing test OUTSIDE this contract's exclusive resources asserts the old enemy Visual size or rotation, do not edit it. Name the test and the assertion in your report.

HARD RULES
- Work only on this branch. NEVER push. NEVER commit to main or move it. Never rebase, amend or rewrite the existing commits; add new commits on top. Never delete branches, tags or worktrees. Never touch any directory outside this clone.
- Commit as user.name "No Safe Circle Codex Worker", user.email "codex-worker@nosafecircle.invalid". The clone's local config already has both. Stage exact paths with `git add -- <path>`; never `git add .` or `-A`. Make small, logical commits with clear messages.
- Unity is NOT available to you. Do not try to run it, and never claim anything compiled or passed in Unity. The Game Agent runs the builder and the Unity tests after you finish.
- Never hand-edit generated or serialized Unity files: .unity scenes, .anim, .controller, .prefab and .asset files, or existing .meta files. The builder creates and updates generated content. A brand-new C# file gets a new .meta with `fileFormatVersion: 2` and a fresh 32-hex guid.
- Stay inside the contract's exclusive resources. Out of bounds: DoorPrototypeSceneBuilder.cs, WizardAnimationController.cs, any .asmdef, ProjectSettings, and all source art (PNGs, inventory.json, art docs). If the work truly needs another file, stop and report instead of editing it.
- Do not change gameplay numbers or behaviour: pursuit, keep-distance, NavMeshAgent settings, attacks, the wisp's cast timing, range, damage and flight, health, registry, encounters and spawn positions.
- You may run Python checks, for example `python -B Pipeline/TaskGraph/taskcontrol.py validate`. Put temp files under `codex-tmp/`, which git ignores for this clone, and do not commit them.
- If reality contradicts the contract or these rules, stop and report. Do not guess.
- Re-read every C# file you changed for compile errors, including using directives and assembly boundaries, because nothing compiles it before the Game Agent does.

FINAL MESSAGE (concise report)
1. Every new commit SHA and what it changes.
2. For each revision 4 change above (1 to 6): the files and tests that implement or cover it.
3. The runtime rotation restore: which callback it uses, why that runs after NavMeshAgent's rotation, and how the camera rotation is kept to one source of truth.
4. The exact builder command, and the generated files expected to change compared with the first pass. For example: 112 .png.meta files now at 64 PPU with Point filter and no mipmaps, and scene Visual transforms.
5. The exact fully qualified Unity test filters, one line for Edit Mode and one for Play Mode, with entries separated by semicolons. Write each line out in full. Include the existing fixtures the contract says must still pass.
6. Anything you could not verify, any out-of-bounds test that asserts old values, any contract ambiguity and how you resolved it, and anything you did not do.
