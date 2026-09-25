# NSC-055 revision 4: Lantern Wraith gameplay prefab (GER Orchestrator decisions, 2026-09-17)

Inputs:
- Codex check of revision 3: C:/nscrev/codex-jobs/codex-contract-check-NSC-055-rev3-20260917.report.md ("revise": 3 blocking, 2 major, 1 minor).
- NSC-077 revision 10 check: NSC-055 lacks the Lantern Wraith animation binding.
- Vincent, 2026-09-16: the Ranged Enemy is the Lantern Wraith, its projectile is a teal lantern wisp, gameplay is unchanged, and art-director guide section 11 applies.

Mirror NSC-015's prefab pattern (MeleeEnemyGameplayPrefabBuilder, Generated/MeleeEnemyGameplay.prefab, MeleeEnemyGameplayPrefabTests) so both enemies are assembled the same way.

## E1. Registration is proven in a harness; production wiring stays with NSC-030 (blocking 1)
- **Why.** EnemyHealth.Initialize only stores the registry reference, and production registration happens at encounter admission (NSC-030).
- **VAL-001's Play Mode test.** Instantiate the generated prefab, call EnemyHealth.Initialize(registry), then call ActiveEnemyRegistry.Register explicitly, as NSC-015 VAL-006 does. Assert:
  - exactly one registration;
  - lethal damage through EnemyHealth stops movement and attacks;
  - active projectiles are cleared;
  - exactly one unregistration.
- **Downstream obligation.** Point to NSC-030 AC-005, which wires every production enemy's EnemyHealth to the scene registry and admits enemies through EncounterAdmissionController. NSC-055 adds no prefab self-registration.

## E2. NSC-055 owns the exact production assets NSC-054 INT-003 requires (blocking 2)
**Assets and components NSC-055 creates**, each with its .meta as an exclusive resource:
- **Builder:** Assets/NoSafeCircle/DoorPrototype/Editor/LanternWraithGameplayPrefabBuilder.cs, an Editor menu command plus a deterministic in-memory seam for tests, following MeleeEnemyGameplayPrefabBuilder.
- **Gameplay prefab:** Assets/NoSafeCircle/DoorPrototype/Generated/LanternWraithGameplay.prefab, builder output only.
- **Projectile template:** Assets/NoSafeCircle/DoorPrototype/Generated/LanternWispProjectile.prefab, builder output. It is compatible with RangedEnemyProjectile (E5) and is assigned to RangedEnemyAttack's projectile-template field.
- **Projectile origin:** a child Transform named WispOrigin at the lantern's height and offset, assigned to RangedEnemyAttack's origin field.
- **Wind-up feedback:** a child GameObject named LanternFlare. Its SpriteRenderer is a placeholder teal flare using a builder-generated sprite asset. It is assigned to RangedEnemyAttack's wind-up feedback field and is visible only during wind-up.
  - If the builder needs a sprite asset, it creates Assets/NoSafeCircle/DoorPrototype/Generated/LanternFlareSprite.asset (+ .meta) as an NSC-055 resource.
- **Defeat response:** Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/LanternWraithDefeatResponse.cs. On EnemyHealth's defeat transition it:
  - disables RangedEnemyKeepDistanceMovement;
  - disables RangedEnemyAttack, whose cleanup clears its projectiles and wind-up;
  - stops the NavMeshAgent;
  - does not unregister a second time (EnemyHealth already unregisters);
  - exposes ResetDefeatResponse() for floor restart, which NSC-033 AC-004 needs.

**Field names:** use RangedEnemyAttack's real serialized field names at HEAD. Read the delivered RangedEnemyAttack.cs and RangedEnemyProjectile.cs.

**Tests** (+ .meta):
- Edit Mode: Assets/NoSafeCircle/DoorPrototype/Tests/Editor/LanternWraithGameplayPrefabTests.cs
- Play Mode: Assets/NoSafeCircle/DoorPrototype/Tests/LanternWraithGameplayPrefabPlayModeTests.cs

**Keep** logical:enemy-locomotion-behavior-surface. The RESOURCE_GROUPS reconciliation happens at commit.

**Add a validation-policy entry** with exactly these two fixtures:
- EditMode: NoSafeCircle.DoorPrototype.Tests.Editor.LanternWraithGameplayPrefabTests
- PlayMode: NoSafeCircle.DoorPrototype.Tests.LanternWraithGameplayPrefabPlayModeTests

## E3. Locked-door behavior is out of scope until Vincent decides (blocking 3)
NSC-017 INT-001 says Vincent decides how the Ranged Enemy's keep-distance movement yields to a locked-door approach, and what attack form it uses. That decision is not made.
- **This revision:** NSC-055 does NOT attach EnemyLockedDoorAttack and does not add an NSC-017 dependency. State this explicitly.
- **New downstream obligation:** once Vincent decides the Lantern Wraith's locked-door behavior, a follow-up revision of NSC-055 (or an approved replacement owner) adds the NSC-017 dependency, the wiring, and the prefab-conformance proof. Until then, a Lantern Wraith that loses sight of the wizard behind a locked door uses its existing target-loss and search behavior.
- **To Vincent:** the GER Orchestrator asks him separately and recommends that Lantern Wraiths do not attack doors. They hold range and search, then follow through a door a Dungeon Brute has broken. Brutes are the breachers and wraiths are the zoners. The contract does not assume this answer.

## E4. The presentation is a criterion with gates (major 1)
The prefab presents the Lantern Wraith using NSC-077's delivered assets read-only:
- A Visual child whose SpriteRenderer follows the NSC-039 world-sprite sorting and ground-contact pivot convention, in NSC-077's uniform camera-facing Visual box (64 PPU, 2x2 world units, uniform scale 1, camera-facing rotation). It shows the south idle still.
- An Animator on the prefab using NSC-077's LanternWraithAnimator.controller, and EnemyAnimationController on the root.
- No copied clip, controller or sprite.

**Gates:**
- The Edit Mode prefab test asserts every item above, including that the Animator references the exact NSC-077 controller asset path and GUID and that nothing is duplicated.
- A Play Mode test asserts the walk state plays while the instance moves and idle plays when it stops.
- Vincent's human review looks at the prefab in Play Mode at gameplay-camera scale. Record it as a completion gate: the lantern is visible, the wisp reads teal with no fire colors, and the wind-up flare reads before the shot.

## E5. The Lantern Wisp template (major 2)
- **Placeholder look.** LanternWispProjectile.prefab is a glowing teal ghost-light orb: unlit or emissive, art-bible teal #30e0cb, at the size of NSC-077's scene stand-in orb, with no fire colors. It is compatible with RangedEnemyProjectile's required components and fields.
- **Gameplay unchanged:** speed, damage, lifetime and hit radius stay RangedEnemyAttack/RangedEnemyProjectile's delivered values and ownership.
- **Downstream obligation.** The production wisp art replaces this placeholder in a later art task, keeping the template's path and GUID. That art is Vincent's 2026-09-16 pick recorded in NSC-077 INT-002: the "grumpy face" sample A wisp, a lantern-flare wind-up and a ring-pop hit. Reference NSC-077 INT-002.

## E6. Minor
NSC-093 INT-001 is already fixed in NSC-093 revision 2. The walk-generation doc goes to the Art Director Agent (sent 2026-09-17). If NSC-094's superseded notes still claim ownership, do not edit NSC-094 in this revision; report it.

## Unchanged
Title may become "Lantern Wraith Gameplay Prefab, Presentation, and Defeat Wiring". Execution scope stays single_agent. Placement and encounter rules stay outside (NSC-030).

# NSC-055 revision 5 (GER Orchestrator decisions, 2026-09-17)

Input: Codex check of revision 4, C:/nscrev/codex-jobs/codex-contract-check-NSC-055-rev4-20260917.report.md ("revise": 2 blocking, 5 major). All findings are accepted.

## G1. Separate, mandatory prefab checks (blocking)
VAL-003 is split into two mandatory Edit Mode checks. Neither may run the production builder.
1. **Builder seam.** The isolated non-saving builder seam produces an object that meets AC-001 through AC-004.
2. **Committed assets.** The committed Generated/LanternWraithGameplay.prefab and Generated/LanternWispProjectile.prefab, each opened read-only, meet the same invariants.

Both production-builder runs (materialize, then rerun) belong only to the Windows controller in VAL-005.

## G2. Defeat stops pursuit participation (blocking; NSC-053 INT-001)
- **On defeat,** LanternWraithDefeatResponse also:
  - disables EnemyPursuitMovement (or the component's own pursuit-participation switch, if NSC-053 INT-001 names one);
  - clears the NavMeshAgent path (ResetPath);
  - still disables RangedEnemyKeepDistanceMovement and RangedEnemyAttack, and still stops the agent.
- **ResetDefeatResponse()** re-enables all of them.
- **VAL-001 adds** that after defeat:
  - no pursuit, keep-distance or attack update moves or re-paths the enemy;
  - a partial reset of other owners, for example EnemyPursuitMovement.ResetPursuit alone, does not reactivate it;
  - only ResetDefeatResponse() does.

Read NSC-053 INT-001 at HEAD and match its wording.

## G3. Redirected-target behavior (major; NSC-088 INT-004)
- **Dependency.** Add NSC-088 to depends_on. Decomposition narrows it to NSC-088's enemy-redirect child.
- **Play Mode test.** Add a case to LanternWraithGameplayPrefabPlayModeTests:
  1. Redirect the prefab instance's EnemyTargetKnowledge with TryRedirectToSpectralDecoy(decoyTransform) to a test decoy placed away from the wizard.
  2. Verify the instance approaches or retreats relative to the decoy.
  3. Verify its next wind-up and launched projectile aim at the decoy, not the wizard.
- NSC-055 still does not reimplement redirect eligibility or return state.

## G4. Idle facing for the production Lantern Wraith (major)
**Problem:** NSC-077's EnemyAnimationController resolves Lantern Wraith idle facing through the legacy EnemyLanternWispCaster, which this production prefab omits. To avoid disturbing NSC-077's final validation, NSC-055 fixes it:
- **Resource.** NSC-055 claims repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyAnimationController.cs. A resource group with NSC-077 is reconciled at commit; NSC-055 already depends on NSC-077, so it runs after it.
- **Fallback.** Add a minimal idle-facing fallback. When the root has no legacy EnemyLanternWispCaster but has an EnemyTargetKnowledge with a non-null CurrentTarget, idle facing turns toward CurrentTarget. Legacy behavior is unchanged.
- **Tests:**
  - A Play Mode idle-facing test: the retreated instance idles facing its target.
  - Add NSC-077's EnemyAnimationPlayModeTests to NSC-055's regression run in VAL-005 (not to its policy filters), to prove the legacy path is unchanged.
- **Scope.** Replace AC-003's "EnemyAnimationController.cs is not edited" with this single scoped edit. NSC-077's generated clips, controllers and sprites still are not edited.

## G5. Projectile template conformance (major)
The committed-asset check (G1, item 2) asserts on LanternWispProjectile.prefab:
- exactly the components RangedEnemyProjectile requires;
- an enabled SpriteRenderer (or renderer) whose color is #30e0cb, within 1/255 per channel;
- a scale matching NSC-077's stand-in orb size;
- a collision setup compatible with RangedEnemyProjectile's delivered hit detection;
- RangedEnemyProjectile's serialized speed, damage, lifetime and hit radius equal to their delivered defaults.

It also asserts RangedEnemyAttack's serialized windUpSeconds and cooldownSeconds on the gameplay prefab equal their delivered defaults, and the WispOrigin local position.

## G6. One output contract for the builder (major)
AC-001 says the production command exclusively owns and materializes all three generated assets with their .meta files: LanternWraithGameplay.prefab, LanternWispProjectile.prefab and LanternFlareSprite.asset. None is hand-authored. Replace the "exclusively materializes Generated/LanternWraithGameplay.prefab" wording.

## G7. NSC-033 (major)
NSC-033 revision 9 (in drafting) adds LanternWraithDefeatResponse.ResetDefeatResponse(). No NSC-055 change.

## Deferred stale dependent
NSC-077 INT-002 should name NSC-055's LanternWispProjectile.prefab as a production template the later wisp art replaces. It is deferred until NSC-077 is integrated, because an obligation-only change after delivery keeps conformance, and changing NSC-077's contract hash now would disturb its delivery evidence.
