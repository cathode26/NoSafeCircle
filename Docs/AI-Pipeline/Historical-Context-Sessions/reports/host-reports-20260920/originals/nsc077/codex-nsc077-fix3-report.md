codex
1. Commit `b16938d01045b6f4ae7caa8466cfb6533012ee78` — updated only [EnemyAnimationPlayModeTests.cs](/workspace/Assets/NoSafeCircle/DoorPrototype/Tests/EnemyAnimationPlayModeTests.cs:412). The branch is clean; nothing was pushed.

2. Root cause confirmed statically: `LateUpdate` calls `Tick`, which derives speed from cached positional displacement. The original single-frame yield could leave residual `NavMeshAgent` movement for the manual `Tick`, preserving the walk state.

3. Timing audit:

   - Stop/idle: clears `agent.velocity`, waits for two stable frames, captures the final position, retains the `AreNotEqual` guard, and waits for production `LateUpdate` to select target-facing idle without drift.
   - Walk: waits until animation direction agrees with observed NavMesh displacement.
   - Wraith: waits explicitly for visible-target idle facing before checking its wisp.
   - Judged safe: scene loading, NavMesh admission, target acquisition, wisp spawning, and scene unloading already use asynchronous operations or deadline-based waits. All other manual `Tick` tests are synchronous, isolated, and use no live `NavMeshAgent` or yielded frames. No other test in this fixture loads the saved scene or drives a live agent.

4. Unity was not available, so nothing was compiled or executed. Rerun the authoritative 107-test Play Mode filter on this exact commit with Unity 6000.1.8f1—preferably twice—and watch for the new stop-stability or target-facing deadline messages. Confirm the repository remains clean afterward.
