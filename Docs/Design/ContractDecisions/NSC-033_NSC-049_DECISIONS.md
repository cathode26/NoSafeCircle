# NSC-033 revision 8, NSC-049 revision 6 and obligation wording fixes (GER Orchestrator decisions, 2026-09-17)

Sources: Codex contract checks of NSC-007 rev 3 and NSC-030 rev 5/6, which flagged NSC-033 and NSC-049 as stale dependents (C:/nscrev/codex-jobs/*.report.md); NSC-030 revision 6 INT-001 and INT-006; nsc-33's NSC-077 review (fixed enemy spawns inside room colliders).

## NSC-033 revision 8: Floor Run/Restart Persistent-Systems Closure
NSC-033 has execution_scope needs_execution_decomposition and no children yet, so its own contract must carry every consumer requirement for the decomposer.

**N1. Participants.** One acceptance criterion lists every reset entry point that another task's downstream_integration_obligations assign to NSC-033, each naming its owner task. Grep Tasks/ for obligations naming NSC-033. At HEAD these are:
- NSC-007 Fireball.ResetFireball
- NSC-008 FrostField.ResetFrostField
- NSC-009 ForceWave.ResetForceWave
- NSC-015 MeleeEnemyAttack.ResetAttack and MeleeEnemyDefeatResponse.ResetDefeatResponse
- NSC-017 EnemyPursuitMovement.ResetPursuit and EnemyLockedDoorAttack.ResetAttack
- NSC-020 DoorInteractable.ResetDoor
- NSC-030 the encounter activation reset method, ActivatedEnemies, ActiveEnemyRegistry.ResetRegistry and EncounterAdmissionController.ResetAdmissionState
- NSC-053 RangedEnemyKeepDistanceMovement.ResetKeepDistanceMovement
- NSC-054 RangedEnemyAttack.ResetAttack
- EnemyHealth.ResetHealth and EnemyStatusEffectMovement.ResetStatusEffects (NSC-013)
- NSC-041 DoorInteractionFeedback.ResetFeedback, already in AC-001

Keep existing criteria. Add, don't duplicate.

**N2. Order constraints** (a new acceptance criterion):
1. **Spell resets come first.** Fireball.ResetFireball, FrostField.ResetFrostField and ForceWave.ResetForceWave run before PlayerMovement.ResetMovement, because ResetMovement zeroes the shared movement-restriction counter (NSC-007 INT-002).
2. **Enemy-owned resets apply only to activated enemies.** Health, pursuit, locked-door attack, melee attack and defeat response, ranged attack and keep-distance, and status effects apply only to persistent enemies whose GameObject was activated during the failed run. For encounter-admitted enemies that is exactly the members of their activation component's ActivatedEnemies record. A never-activated enemy, pending or cancelled, receives no reset call and keeps its authored transform, because EnemyPursuitMovement.Awake never captured its spawn position (NSC-030 INT-001).
3. **Encounter order**, per NSC-030 INT-001:
   1. the enemy-owned resets above for ActivatedEnemies;
   2. each encounter activation component's reset method, which deactivates every configured enemy;
   3. ActiveEnemyRegistry.ResetRegistry;
   4. EncounterAdmissionController.ResetAdmissionState.

**N3. Dependency.**
- Add NSC-030 to depends_on: restart closure needs the encounter activation owner.
- Record in notes that decomposition narrows this to the integration child depending on NSC-030's encounter activation child (NSC-030 INT-001).
- If the validator reports a cycle, stop and report it instead of working around it.

**N4. Gates.** The integration-child proof (the existing VAL-002 or equivalent) must add two things:
- an order check: Fireball's restriction is released before ResetMovement, observable when a charge is active at zero health;
- the mixed activated/never-activated enemy case: never-activated enemies keep authored transforms and stay inactive.

Keep existing gate IDs; extend their requirement text.

## NSC-017 and NSC-053: mechanical obligation wording
Their obligations say NSC-033 calls EnemyPursuitMovement.ResetPursuit for "every persistent enemy". Qualify that to "every persistent enemy activated during the failed run (never-activated encounter enemies receive no reset call; NSC-030 INT-001)". Wording only; nothing else changes.
- NSC-017: next revision number.
- NSC-053: next revision number, if active.

## NSC-049 revision 6: Five-Room Continuity and Door Sequence Integration
**F1. The fixed squad follows the rooms** (NSC-030 INT-006). NSC-049 recomposes Bone Archive through Final Room to the 2026-09-15 approved bounds and already claims DoorPrototypeGlobalSceneBuilder.cs. The approved bounds are:
- Bone Archive X[-12,12] Z[0,20]
- Chapel of Ash X[-18,18] Z[20,54]
- Lower Vault X[-20,20] Z[54,76]
- Final Room X[-15,15] Z[76,104]

If the builder still builds the fixed enemy squad (EnemySpawnPositions, and LanternWraithSpawnPositions or its pre-NSC-077 name EnemyCasterSpawnPositions) when NSC-049 lands, NSC-049 moves each fixed spawn into its intended room under the approved bounds. Today's intended rooms:
- Melee: Bone Archive, Chapel of Ash, Lower Vault, and two in the Final Room.
- Ranged: Bone Archive, Chapel of Ash, Lower Vault, Final Room.

Each spawn keeps its placement intent: melee mid-room between the room's doors; a ranged enemy on the opposite side of the room from its melee partner, with a sight line to the room's main route. The Final Room ranged enemy covers the approach from D4.

If NSC-030's canonical-scene materialization child has already replaced the fixed squad with encounter-admitted enemies, this criterion needs no change.

**F2. Clear placement.** Every fixed spawn point must:
- lie inside its intended room's approved bounds, at least 1.5 units inside the room's walls;
- sample the baked NavMesh within 0.1 units;
- be clear of colliders: Physics.CheckSphere centered 1 unit above the point with radius 0.5 hits no non-trigger collider.

A builder test in a test file NSC-049 already claims (FiveRoomCompositionTests or its Play Mode fixture, whichever can reach a baked NavMesh) asserts all three for every fixed spawn. This carries forward the rule from nsc-33's NSC-077 review, which found spawns inside Bone Archive's Shelf A, Chapel of Ash's Column1 and the edge of Lower Vault's LV-W1.

**F3. Policy.** NSC-049 keeps its validation policy filters (FiveRoomCompositionTests; FiveRoomDoorSequencePlayModeTests). The commit tool rebinds the policy hash.
