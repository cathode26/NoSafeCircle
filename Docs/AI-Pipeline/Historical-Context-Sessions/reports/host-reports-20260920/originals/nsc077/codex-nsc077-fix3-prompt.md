You are continuing a Unity game task for No Safe Circle. The current directory, /workspace, is a standalone clone made for this job, on branch codex/nsc077-moving-enemy-art-20260917 at tip 79a22f350, based on local main d5037a354. You are running inside a Linux Docker container, so use `python3` where these instructions say `python`. The clone's git config already has core.autocrlf=true and core.filemode=false; keep them.

WHERE THINGS STAND
- NSC-077 (contract revision 10, Tasks/NSC-077.yaml) is otherwise finished: two Claude reviews approved it, and its Edit Mode filter passes 65/65 in Unity 6000.1.8f1.
- The Play Mode filter ran twice on the same runtime and test code:
  - the first run passed 107/107;
  - the second failed 1 of 107, a flaky timing failure in the VAL-006 test:

    NoSafeCircle.DoorPrototype.Tests.EnemyAnimationPlayModeTests.SavedSceneEnemiesUseProductionAnimationAndLanternWisp
      Expected: String starting with "MeleeEnemy_idle_"  But was: "MeleeEnemy_walk_south-east"
      at EnemyAnimationPlayModeTests.cs:452

ROOT CAUSE (verify it; don't take it on trust)
- After the brute walks, the test disables EnemyPursuitMovement, sets `agent.isStopped = true`, calls `agent.ResetPath()`, yields ONE frame, teleports the wizard, then calls `meleeAnimation.Tick(0.1f)` once and asserts idle.
- EnemyAnimationController.Tick computes speed from the displacement since the last Tick, the one from its LateUpdate the frame before. It stays walking while speed > StopWalkingSpeed (0.05).
- `yield return null` resumes after Update and before that frame's LateUpdate. The NavMeshAgent keeps sliding briefly after isStopped and ResetPath, because its velocity isn't zeroed.
- So the residual displacement between the last LateUpdate and the manual Tick can exceed 0.005 units: 0.05 u/s times 0.1 s. Whether it does depends on frame time. That makes the assertion flaky.

YOUR JOB
1. Make this VAL-006 stop-and-idle step deterministic, without weakening what it proves: on stopping, the MeleeEnemy plays idle facing the wizard.
   - Bring the agent to a real stop, for example `agent.velocity = Vector3.zero` together with isStopped and ResetPath.
   - Wait on real conditions with WaitForCondition and a clear deadline message, instead of a single yield plus a manual Tick. Examples: position stable across consecutive frames, then CurrentState starts with "MeleeEnemy_idle_" and LastDirection equals the expected target direction.
   - Keep the AreNotEqual guard that distinguishes target-facing idle from the retained movement facing.
   - Make sure the expected target direction is computed from the enemy's final stopped position, so a residual slide can't change the sector.
2. Audit every other step of this test, and the other EnemyAnimationPlayModeTests that load the saved scene or use NavMeshAgent, for the same class of frame-timing sensitivity. That means an assertion right after a single `yield return null`, or a manual Tick mixed with LateUpdate ticks while an agent may still be moving. Fix any you find the same way, and list what you changed and what you judged safe.
3. Do not change runtime code. Do not change gameplay settings (pursuit, NavMeshAgent settings, speeds) to make the test pass.

HARD RULES
- Work only on this branch. NEVER push. NEVER commit to main or move it. Never rebase, amend or rewrite existing commits; add one new commit on top. Never delete branches, tags or worktrees. Never touch any directory outside this clone.
- Commit as user.name "No Safe Circle Codex Worker", user.email "codex-worker@nosafecircle.invalid"; the clone's local config already has both. Stage exact paths with `git add -- <path>`; never `git add .` or `-A`.
- Unity is NOT available to you. Do not try to run it, and never claim anything compiled or passed. Re-read the changed file for compile errors.
- Out of bounds: every file except Assets/NoSafeCircle/DoorPrototype/Tests/EnemyAnimationPlayModeTests.cs. If a real fix needs another file, stop and report instead.
- Put temp files under `codex-tmp/` (git-ignored) and do not commit them.

FINAL MESSAGE (concise report)
1. The commit SHA and what it changes.
2. Whether you confirmed the root cause, and how.
3. Each timing-sensitive spot you changed, and each you judged safe, with the reason.
4. Anything the Game Agent should watch for when rerunning Play Mode.
