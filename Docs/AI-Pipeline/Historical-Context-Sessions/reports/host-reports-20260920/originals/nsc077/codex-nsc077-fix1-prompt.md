You are continuing a Unity game task for No Safe Circle. The current directory, /workspace, is a standalone clone made for this job, on branch codex/nsc077-moving-enemy-art-20260917. You are running inside a Linux Docker container, so use `python3` where these instructions say `python`. The clone's git config already has core.autocrlf=true and core.filemode=false; keep them.

WHERE THINGS STAND
- The branch implements NSC-077 in four commits:
  - d69f054e6 implement;
  - 1092ce1f1 tests;
  - 3ec6f21bb rev 4 visuals;
  - be062f722 rev 4 tests.
- The Game Agent rebased it onto local main a58d21e31, which is NSC-077 contract **revision 7**, the authority. Earlier passes targeted revisions 3 and 4. Read what changed since then: `git diff 25fdc505d a58d21e31 -- Tasks/NSC-077.yaml`.
- The Game Agent ran it in Unity 6000.1.8f1:
  - it compiled cleanly, and the builder ran with the expected output;
  - EnemyArtIntegrationTests 3/3 and WizardArtIntegrationTests 3/3 passed;
  - DoorPrototypeSceneBuilderTests 56/58: its two failures predate NSC-077, and rev 7's VAL-007 accepts them. Ignore them.
  - Play Mode 103/104: the one failure is in this task's own VAL-006 test.
- A fresh Claude review returned FIX_FIRST. Two files are in this clone and git-ignored:
  - codex-tmp/claude-review-fce475b00.md: the full review. Its line numbers refer to the same code before the rebase; the code blobs are identical.
  - codex-tmp/failures-phaseC.md: the Unity failure with its stack.

YOUR JOB: one fix round. Verify each item against the code before you change anything. If a review finding is wrong, don't "fix" it; say why in your report.

1. **Rev 5 camera constant.**
   - `DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles` must again be an independent field: `internal static readonly Vector3 IsometricCameraEulerAngles = new Vector3(30f, -45f, 0f);`, exactly as on main. It must not forward to EnemyAnimationController.
   - EnemyAnimationController keeps its own runtime constant.
   - EnemyArtIntegrationTests' agreement check must read the builder FIELD by reflection (GetField, not GetProperty) and compare the two Vector3 values exactly. An angle tolerance of about 0.16 degrees is too loose.
   - The VAL-004 Play Mode checks compare the Visual's world rotation against the literal `Quaternion.Euler(30f, -45f, 0f)`, not against the controller's constant.
2. **VAL-006 gate test, EnemyAnimationPlayModeTests.SavedSceneEnemiesUseProductionAnimationAndLanternWisp (blocker).** It fails with "CharacterController.Move called on inactive controller".
   - The test disables the player's CharacterController and leaves it off across frames while PlayerMovement keeps running.
   - Teleport the wizard within one frame: disable the controller, set the position, re-enable it, then Physics.SyncTransforms. Or keep PlayerMovement from ticking while the wizard is parked. Don't change PlayerMovement.
   - The reviewer suspects a second failure hidden behind the first: the Bone Archive MeleeEnemy at (-6,0,10) spawns inside Shelf A's collider, so its sight line is blocked or it never gets onto the NavMesh.
     - Check it against the room scene files under Assets/Scenes/Rooms/ and the builder's layout data.
     - Choose enemies and wizard positions with a clear sight line and valid NavMesh. The reviewer suggests the Chapel of Ash MeleeEnemy at (7,0,31) with the wizard at (9,0,31), and for the LanternWraith one whose sight line is clear. The reviewer says the Chapel of Ash wraith is inside Column1.
   - Wait on real conditions such as NavMeshAgent.isOnNavMesh and the enemy acquiring the wizard, each with a time bound and a clear failure message, not a fixed 120 frames.
   - Don't move spawns: the contract forbids it.
3. **VAL-006 facing checks must be able to fail.**
   - Place the wizard off the enemy's movement axis, so that "idle facing the wizard after stopping" is a different facing from "kept the last movement facing".
   - Also show that a walking enemy faces its movement, not its target.
4. **LanternWraith out-of-range facing check.** Put the out-of-range wizard in a different screen sector from the in-range one, so the test can fail.
5. **VAL-005 pins its numbers.**
   - The 4-second projectile lifetime: still alive just before 4 s, gone just after. Don't check in the same frame as Destroy.
   - The 0.8-unit hit radius: a hit just inside 0.8, no hit just outside it.
   - 8 units per second.
   - 5 damage, 10 of 60 mana per cast, one cast per second, and no casts after six.
6. **VAL-004 for both enemy types.** The "facing matches WizardAnimationController.LastDirection for the same displacements" test must run for the MeleeEnemy AND the LanternWraith.
7. **AC-002 error messages.** Every missing or wrong source-art failure in EnemyAnimationAssetBuilder, idle stills and walk frames alike, must name the exact file.
8. **No per-frame allocations.** EnemyAnimationController must not build state-name strings, or allocate in any other way, every frame. Precompute state names or hashes once.
9. **Disable and re-enable.** Reset EnemyAnimationController's cached state in OnEnable, so a re-enabled enemy doesn't keep a stale state (INT-001 encounter admission will reuse this). Add a focused Play Mode check.
10. **VAL-003 has no missing scripts (rev 6 and 7).** The saved-scene test must fail if any GameObject in Assets/Scenes/DoorPrototype.unity has a missing script. Use `GameObjectUtility.GetMonoBehavioursWithMissingScriptCount` over every GameObject, or equivalent. Don't skip null components.
11. **Rev 7 VAL-007 and AC-007.**
    - EnemyLanternWispCaster.cs.meta must keep GUID 73b9fddab19c3f34e878119acd894458.
    - No EnemyFireballCaster.cs or .meta may remain anywhere.
    - Nothing may reference EnemyFireballCaster: grep code, tests, docs in scope, and prefabs or scenes if they are text.
    - Report what you found.

Also re-check any other rev 5 to rev 7 contract changes for implementation effects, and report them.

HARD RULES
- Work only on this branch. NEVER push. NEVER commit to main or move it. Never rebase, amend or rewrite existing commits; add new commits on top. Never delete branches, tags or worktrees. Never touch any directory outside this clone.
- Commit as user.name "No Safe Circle Codex Worker", user.email "codex-worker@nosafecircle.invalid"; the clone's local config already has both. Stage exact paths with `git add -- <path>`; never `git add .` or `-A`. Make small, logical commits with clear messages.
- Unity is NOT available to you. Do not try to run it, and never claim anything compiled or passed. The Game Agent runs the builder and the tests.
- Never hand-edit generated or serialized Unity files: .unity scenes, .anim, .controller, .prefab, .asset, or existing .meta files. A brand-new C# file gets a new .meta with `fileFormatVersion: 2` and a fresh 32-hex guid.
- Stay inside the contract's exclusive resources. Out of bounds: DoorPrototypeSceneBuilder.cs, WizardAnimationController.cs, PlayerMovement.cs, any .asmdef, ProjectSettings, DoorPrototypeSceneBuilderTests.cs (another change owns it), all source art and room scenes. If the work truly needs another file, stop and report instead of editing it.
- Do not change gameplay numbers or behaviour: pursuit, keep-distance, NavMeshAgent settings, the wisp's cast timing, range, damage and flight, health, registry, encounters and spawn positions.
- You may run Python checks, for example `python -B Pipeline/TaskGraph/taskcontrol.py validate`. Put temp files under `codex-tmp/`, which is git-ignored; do not commit them.
- Re-read every C# file you changed for compile errors, including usings, assembly boundaries and Unity 6000.1 API names, because nothing compiles it before the Game Agent does.
- Test filters are fixed by Pipeline/TaskReviewAgent/authoritative_validation_policy.json. Don't add new test classes that those filters wouldn't run; put new tests in the existing NSC-077 fixtures.

FINAL MESSAGE (concise report)
1. Every new commit SHA and what it changes.
2. For items 1 to 11: fixed (files and tests), or not a real problem (why).
3. The enemy and wizard positions the VAL-006 test now uses, and why the sight lines and NavMesh are valid, with evidence from the room data.
4. Anything you could not verify, and anything the Game Agent should watch for in Unity.
