# Restart, victory and decoy cascade (GER Orchestrator decisions, 2026-09-17)

Sources:
- Codex contract checks: NSC-033 rev 8 (blocking: DemoRunFlow death state), NSC-030 rev 9 (4 major), NSC-009 rev 5 (NSC-033 stale), NSC-088 rev 4 (INT-001 stale).
- NSC-055 revision 4 INT-003.
- GDD "Loss": reaching zero health restarts the floor. There is no death screen or manual reload.

## DemoRunFlow retirement (NSC-033 blocking finding)
DemoRunFlow (Assets/NoSafeCircle/DoorPrototype/Scripts/DemoRunFlow.cs) is playable-build glue. Its pieces go to real owners.

**Cursor fireball:** NSC-007 AC-011 removes it (unchanged).

**Stays in DemoRunFlow for now, owned by no task yet:**
- enemy contact damage (ApplyEnemyContactDamage);
- enemy health bars (DrawEnemyHealthBars);
- the player status HUD (DrawPlayerStatus).

**Death path:** NSC-033's integration child retires it.
- It removes the PlayerHealth.Died subscription, the lost flag, the "YOU DIED" end-screen text and the "Press R to play again" SceneManager.LoadScene reload.
- It claims repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DemoRunFlow.cs (a shared resource group with NSC-007 and NSC-086).
- Zero health now restarts the floor through the orchestrator only.

**Win path:** NSC-086 retires it.
- It removes the final-door CrossedForward subscription, the won flag and the "YOU ESCAPED" end-screen text.
- NSC-086's You Escaped overlay and victory suspension replace them.
- It claims DemoRunFlow.cs in the same group.
- If NSC-086 lands first, the end screen and R reload stay for the death path until NSC-033 removes them. If NSC-033 lands first, the end screen and R reload stay for the win path until NSC-086 removes them. Whichever lands second removes DrawEndScreen, the R reload and the won/lost early return in Update entirely.

**NSC-007 revision 5 (AC-011 wording only):** keep enemy contact damage, enemy health bars, the player status HUD, the win and death screens and R-to-restart unchanged within NSC-007. Add that NSC-086 later retires the win path and NSC-033 later retires the death path.

## NSC-033 revision 9
Keep everything in revision 8, then add the following.
- **R1. DemoRunFlow death path** (above).
  - AC: the integration child removes it.
  - Gate: a production-scene zero-health restart test (in Assets/Scenes/DoorPrototype.unity) proves all of:
    - no DemoRunFlow lost/death state or R-reload gate remains; verify by reflection that DemoRunFlow declares no lost field and no HandlePlayerDied method, and by a source check that DemoRunFlow.cs contains no "YOU DIED";
    - the floor restarts automatically;
    - in the next run, enemy contact damage still applies and the HUD still draws.
- **R2. New participants** (append to AC-004; keep attribution style):
  - SpectralDecoy.ResetSpectralDecoy() (NSC-088 INT-001);
  - LanternWraithDefeatResponse.ResetDefeatResponse() (NSC-055 INT-003);
  - ForceWave.ResetForceWave(), whose NSC-009 INT-001 scenario now includes an active pulse.
- **R3. Order.** AC-005 already puts spell resets before PlayerMovement.ResetMovement. Include SpectralDecoy.ResetSpectralDecoy() among the spell resets. It must also run before the enemy-owned EnemyTargetKnowledge/EnemyPursuitMovement resets, so every redirected enemy leaves its decoy redirect through the owner API before its pursuit state resets.
- **R4. Scenarios in the integration proof** (extend VAL-002; keep IDs), each through the production zero-health path:
  - Force Wave with an active pulse and cooldown at zero health: after restart IsPulseActive is false, the cooldown is clear and Force Wave is enabled.
  - An active Spectral Decoy phantom with redirected enemies at zero health: after restart the phantom is gone, the cooldown is clear, no spell feedback remains, and no enemy keeps a decoy target, redirect flag or saved switch position.
  - A defeated Lantern Wraith at zero health: after restart its keep-distance movement and attack are re-enabled and its NavMeshAgent resumes.
- **R5. depends_on:** add NSC-055 and NSC-088. Decomposition narrows each to its integration child.

## NSC-086 revision 3
- AC: retire DemoRunFlow's win path (above) and claim DemoRunFlow.cs.
- VAL-001 adds: after final-door victory, only the You Escaped overlay shows; DemoRunFlow declares no won field and no final-door CrossedForward handler (reflection); and DemoRunFlow.cs contains no "YOU ESCAPED" (source check).

## NSC-030 revision 10 (from the NSC-030 rev 9 check)
- **C1. Scope of AC-005 (INT-005 only).**
  - The canonical-scene materialization child proves that each encounter-admitted Lantern Wraith scene instance carries exactly one EnemyTargetKnowledge, EnemyPursuitMovement, RangedEnemyKeepDistanceMovement, RangedEnemyAttack, NavMeshAgent and EnemyHealth. The proof is a committed-scene Edit Mode conformance check with exact counts.
  - The same child adds a committed-scene Play Mode check: one placed Lantern Wraith, redirected with EnemyTargetKnowledge.TryRedirectToSpectralDecoy to a test decoy Transform, approaches it and launches its next projectile toward it.
  - Prefab-level redirected-target behavior stays with NSC-055 (NSC-088 INT-004), not NSC-030.
  - The materialization child's dependency on NSC-088 narrows to NSC-088's enemy-redirect child.
- **C2. Decoy-safe melee.** NSC-015 revision 11 (5a6b29cd4) makes MeleeEnemyAttack safe against a target without PlayerHealth. Record in notes that VAL-007's review child depends on NSC-015's split 1 (the attack child) through the existing NSC-015 dependency.
- **C3. Automated cover proof.** Add a committed-scene Play Mode assertion to VAL-007's automated part, owned by the review child or materialization child, whichever runs committed-scene Play Mode tests:
  - In Chapel of Ash, a Lantern Wraith redirected to a test decoy positioned so a column or pew collider blocks the line fires.
  - The projectile is stopped by that collider.
  - The wraith's CurrentTarget stays the decoy and IsRedirectedToSpectralDecoy stays true.
  - Vincent's human review keeps route quality and cooldown dominance.
- **C4.** NSC-006, NSC-086, NSC-087 and NSC-015 are already revised (commits 187706c6c, 661ce495b, a34c52211, 5a6b29cd4). NSC-033 is revised in the section above.
