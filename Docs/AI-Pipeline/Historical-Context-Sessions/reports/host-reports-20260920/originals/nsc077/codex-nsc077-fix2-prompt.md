You are continuing a Unity game task for No Safe Circle. The current directory, /workspace, is a standalone clone made for this job, on branch codex/nsc077-moving-enemy-art-20260917. You are running inside a Linux Docker container, so use `python3` where these instructions say `python`. The clone's git config already has core.autocrlf=true and core.filemode=false; keep them.

WHERE THINGS STAND
- The branch implements NSC-077 and is rebased onto local main d5037a354, which holds contract **revision 10**, the authority. Its tip is 2a072e855.
- A fresh Claude review of the last fix round returned APPROVE with no findings.
- In Unity 6000.1.8f1, the previous tip compiled, built twice with stable output, and is in its test run now.

YOUR JOB: one small change for revision 10. See `git diff 643016721 d5037a354 -- Tasks/NSC-077.yaml`.

VAL-003 in revision 10 adds an exact-count requirement. The EnemyArtIntegrationTests saved-scene test must prove that under the Enemies root there is:
- exactly one MeleeEnemy per entry of DoorPrototypeGlobalSceneBuilder's melee spawn-position array (EnemySpawnPositions);
- exactly one LanternWraith per entry of its Lantern Wraith spawn-position array (LanternWraithSpawnPositions);
- both arrays read by reflection (GetField, NonPublic | Static), each with at least one entry;
- no FireCasterEnemy.

Read the builder for the exact field names and types. Use the same reflection pattern the test already uses for IsometricCameraEulerAngles.

If it is cheap and clearly right, also check that each enemy's position matches a distinct entry of its array (within 0.001 on X and Z). Report whether you added that; it isn't required.

Nothing else is in scope. Do not change runtime code, the builder, other tests, or anything the review approved.

HARD RULES
- Work only on this branch. NEVER push. NEVER commit to main or move it. Never rebase, amend or rewrite existing commits; add one new commit on top. Never delete branches, tags or worktrees. Never touch any directory outside this clone.
- Commit as user.name "No Safe Circle Codex Worker", user.email "codex-worker@nosafecircle.invalid"; the clone's local config already has both. Stage exact paths with `git add -- <path>`; never `git add .` or `-A`.
- Unity is NOT available to you. Do not try to run it, and never claim anything compiled or passed. Re-read the changed file for compile errors: usings, reflection types, LINQ.
- Never hand-edit generated or serialized Unity files. Out of bounds: every file except Assets/NoSafeCircle/DoorPrototype/Tests/Editor/EnemyArtIntegrationTests.cs.
- Put temp files under `codex-tmp/` (git-ignored) and do not commit them.
- If reality contradicts these instructions, stop and report.

FINAL MESSAGE (concise report)
1. The commit SHA and what it changes.
2. The exact assertions added, and the field names and types read.
3. Anything you could not verify.
