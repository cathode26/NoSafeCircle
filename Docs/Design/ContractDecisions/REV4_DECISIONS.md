# Spell contract follow-ups: NSC-007, NSC-008, NSC-009 revision 4 (GER Orchestrator decisions, 2026-09-17)

Inputs: Codex contract checks of revision 3 (all "revise"):
- C:/nscrev/codex-jobs/codex-contract-check-NSC-007-rev3-20260917.report.md
- C:/nscrev/codex-jobs/codex-contract-check-NSC-008-rev3-20260917.report.md
- C:/nscrev/codex-jobs/codex-contract-check-NSC-009-rev3-20260917.report.md
Settled rules stay as in SPELL_DECISIONS.md (S1-S7). Vincent delegated spell design ("Yes you can decide everything yourself on spells").
Every finding below is accepted unless a decision says otherwise. Gameplay does not change; these are ownership fixes, a contradiction fix and missing proof.

## Shared decisions (apply to all three contracts)

**SP4-1 Binding proof on the committed project asset.** An Edit Mode test in a test file the contract already claims loads Assets/InputSystem_Actions.inputactions and asserts, for its own spell action in the Player map:
- action type Button;
- exactly one binding, with path `<Mouse>/rightButton` (Fireball), `<Keyboard>/q` (FrostField) or `<Keyboard>/space` (ForceWave), whose groups contain only Keyboard&Mouse (split on ';', ignore empty entries);
- no gamepad, joystick, touch or XR binding on the spell action;
- that path is bound by no other Player action (MoveToCursor, Interact, Attack, Jump, the other two spells, or any other);
- Attack still has exactly its six base bindings: `<Gamepad>/buttonWest` (;Gamepad), `<Mouse>/leftButton` (;Keyboard&Mouse), `<Touchscreen>/primaryTouch/tap` (;Touch), `<Joystick>/trigger` (Joystick), `<XRController>/{PrimaryAction}` (XR), `<Keyboard>/enter` (Keyboard&Mouse);
- NSC-009 also: Jump no longer has `<Keyboard>/space` and keeps `<Gamepad>/buttonSouth` (Gamepad) and `<XRController>/secondaryButton` (XR).
Base facts (main 32c6223d3): keyboard/mouse Player bindings today are Move WASD+arrows (composite parts), Attack leftButton+enter, Next 2, Sprint leftShift, Jump space, Previous 1, Interact e, Crouch c, PointerPosition position, MoveToCursor leftButton. Q is unbound; right mouse is unbound.

**SP4-2 Door attempts continue (behavioral proof).** Each spell's Play Mode tests start a real door-opening attempt through the production path (a DoorInteractable in range, PlayerInteractionController.BeginInteraction or its approach flow), advance it with DoorInteractable.Tick so Progress > 0, then cast through the spell's Input Action (Fireball: a tap and a separate charge-and-release; FrostField: a cast; ForceWave: a cast), keep ticking, and assert the same attempt continues: DoorInteractable.IsInteracting stays true, PlayerInteractionController.PendingDoor is the same door, and Progress never drops and keeps increasing. The existing "never calls a door/interaction method" wording stays.

**SP4-3 Optional references are proven optional.** Each spell's title/entry tests add a missing-reference case: with the spell's optional reference unassigned on TitleScreenController and WizardGameEntryController, WizardGameEntryController.HasValidReferences() stays true and the entry flow completes. The committed-scene/builder test asserts TitleScreenController's gameplayInputBehaviours array does not contain the spell and still holds exactly its two debug controls (DebugDamageControl, DebugManaSpendControl), as DoorPrototypeGlobalSceneBuilder.BuildTitleScreen assigns today.

**SP4-4 Enemy discovery (NSC-008, NSC-009).** Candidates come from `FindObjectsByType<EnemyStatusEffectMovement>(FindObjectsSortMode.None)` at cast time (and, for Frost Field, at each refresh), keeping only components that are enabled, on active GameObjects, and whose EnemyHealth (when present) has IsDefeated false. No cached list from initialization. Tests cover an inactive, a disabled and a defeated candidate (never affected) and a candidate created after the spell initialized (affected: Force Wave at its next cast, Frost Field at its next refresh).

**SP4-5 Ranged enemies carry no status-effect component (NSC-008, NSC-009).** The builder-wiring test asserts each MeleeEnemy has exactly one EnemyStatusEffectMovement and that every ranged enemy (GameObject named LanternWraith once NSC-077 lands, FireCasterEnemy before; the test accepts whichever exists) has zero EnemyStatusEffectMovement and zero NavMeshAgent.

## NSC-007 Charged Fireball (revision 4)

1. **"Caster" wording.** Replace every "caster" that means the wizard with "the wizard who cast the Fireball" / "the wizard's CharacterController". State explicitly that ranged enemies are valid targets: the Lantern Wraith (EnemyLanternWispCaster, EnemyFireballCaster before NSC-077) carries EnemyHealth and takes Fireball damage like any enemy. VAL-004 places an EnemyHealth target that also carries the ranged caster component (whichever name exists at the candidate's base) and asserts it is damaged.
2. **VAL-005 binding proof:** SP4-1.
3. **Mana proof.** Play Mode cases counting PlayerMana.ManaSpent and PlayerMana.CastDenied events:
   - a press below the tap cost: CastDenied exactly once, no ManaSpent, no charge, no restriction, no projectile;
   - mana between tiers: normalized charge progress stops at the highest affordable tier while held;
   - mana falling during a charge (the test calls PlayerMana.Spend directly mid-charge): the cap drops; if mana is below the tap cost at release, CastDenied exactly once, no projectile, restriction released once;
   - a normal release: exactly one ManaSpent event, with the reached tier's cost.
4. **Tap values and cooldown.** Assert the six starting values through observable outcomes: ManaSpent(20); EnemyHealth loses 25; the projectile moves 12 units per second of Tick; it fizzles with no damage after 3 seconds; flat contact at 0.85 units hits and at 0.95 units does not (contact radius 0.9); a second tap within 0.5 seconds of a cast spends nothing, raises no CastDenied and creates no projectile, and a tap after Tick advances 0.5 seconds casts normally.
5. **Damage cancels a charge.** A real PlayerHealth.TakeDamage during a charge cancels it immediately: zero ManaSpent, zero projectiles, and Fireball's restriction released exactly once. Prove "exactly once" with a second restriction the test itself holds: after the cancel IsMovementRestricted stays true, and after the test releases its own it becomes false. Also a case without the test's restriction, where IsMovementRestricted is false right after the cancel.
6. **Door attempt:** SP4-2.
7. **Legacy DemoRunFlow fireball removed.** Proof is an Edit Mode reflection test plus a source check, not a committed-scene Play Mode right-click test:
   - the reflection test finds no TryFireAtCursor or AdvanceFireballs method, no nested Fireball type, no fireballSpeed, fireballLifetime, fireballHitRadius, fireballDamage, fireballManaCost, fireballCooldown, fireballs or castCooldown field on DemoRunFlow;
   - DemoRunFlow.cs contains no `Mouse.current`;
   - the committed-scene conformance test finds exactly one Fireball component in Assets/Scenes/DoorPrototype.unity.
8. **Height does not matter.** A contact case and an area case with an enemy raised 1.5 units above the projectile but inside the horizontal radius are both damaged.
9. **In-flight cleanup.** Separate VAL-003 cases for ResetFireball, SuspendGameplayInput, disable and destroy, each with a projectile already in flight: the projectile is removed and further Ticks cause no damage.
10. **Wiring gap (found by the GER Orchestrator).** AC-005 needs PlayerHealth.Damaged, so AC-009's BuildPlayer wiring also assigns the Player's PlayerHealth to Fireball, and VAL-005 asserts that reference.
11. **Stale dependents (not edited in this revision).** NSC-033's reset order (INT-002) and NSC-015's stale target-discovery note get their own follow-ups by the GER Orchestrator. Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md goes to the Documentation Agent.

## NSC-008 Frost Field (revision 4)

1. **Slow strength ownership (blocking #1): FrostField owns it.** The delivered NSC-013 API is `EnemyStatusEffectMovement.ApplyFrostSlowdown(float speedMultiplier, float duration)`, so the caller supplies the multiplier. This matches SPELL_DECISIONS membership ("refreshes ApplyFrostSlowdown(multiplier, duration)"); NSC-013 needs no revision.
   - FrostField serializes the slow multiplier (starting value 0.4; nonbinding tuning range 0.25-0.5) and passes it on every refresh.
   - EnemyStatusEffectMovement (NSC-013) owns applying, refreshing, counting down, restoring baseline speed and ResetStatusEffects.
   - Remove "NSC-013 is the sole owner of enemy slow strength" from execution_reason and notes.
   - A test asserts FrostSpeedMultiplier equals FrostField's configured multiplier on a member after a refresh.
2. **Lingering bound (blocking #2).** Replace "no lingering slow beyond one refresh interval after exit" with a measurable bound:
   - the slowdown duration is serialized, greater than the refresh interval and at most twice it (defaults 0.2 s interval, 0.3 s duration);
   - an enemy that leaves the field, or whose field expires naturally, stays slowed at most one slowdown duration after its last refresh;
   - recast, suspension and reset end slows immediately (item 3);
   - a test measures the tail: slowed on the refresh before exit, and IsFrostSlowdownActive false no later than one duration after the last refresh.
3. **Recipients in the tail (major).** FrostField keeps every enemy it has refreshed whose slowdown can still be active (refreshed within the last slowdown duration), not only current members. Recast, SuspendGameplayInput and ResetFrostField call EnemyStatusEffectMovement.ResetStatusEffects() on every such recipient. Tests: exit-then-recast, exit-then-suspend and exit-then-reset each end the tail slow immediately.
   - ResetStatusEffects clears only Frost state; displacement is an instantaneous warp with no state, so this never interrupts Force Wave.
4. **Binding proof:** SP4-1 with `<Keyboard>/q`.
5. **A failed recast changes nothing.** Mana is spent before the old field is touched; a refused Spend leaves it untouched. Test: an active field and a recast whose Spend fails leave the original field, its feedback, its members' slows and its remaining lifetime unchanged, with CastDenied raised exactly once.
6. **Door attempt:** SP4-2.
7. **Ranged enemies excluded:** SP4-5.
8. **Candidate exclusion and late entry:** SP4-4.
9. **Exact API:** `FindObjectsByType<EnemyStatusEffectMovement>(FindObjectsSortMode.None)` plus the SP4-4 filtering.
10. **Optional references:** SP4-3.

## NSC-009 Force Wave (revision 4)

1. **Discovery:** SP4-4 (cast-time FindObjectsByType, late-created enemy test).
2. **Scope contradiction.** Remove "menu-flow" from the notes' list of forbidden owner files. Say instead that AC-011's optional ForceWave references in TitleScreenController.cs and WizardGameEntryController.cs are the only edits to those files, and that no other menu-flow behavior changes.
3. **Binding proof:** SP4-1 with `<Keyboard>/space`, including the Jump checks. It lives in ForceWaveSceneBuilderTests (or the Edit Mode test file this contract already claims).
4. **Optional references:** SP4-3.
5. **Cast pulse proof.** ForceWave exposes a read-only pulse state (for example IsPulseActive and a serialized pulse duration). A Play Mode test casts, sees the pulse active, and sees it end after its duration. A refused cast during cooldown starts no pulse and gives the cooldown-refusal feedback AC-008 names. The human no-target cast review (VAL-004 or INT-004) must see the pulse and the refusal feedback.
6. **Duplicate obligations.** Delete INT-003 and fold its checks into INT-004, which stays assigned to NSC-030 VAL-007's full-kit play review:
   - surround escape and clearing door blockers;
   - a weak answer to distant ranged pressure that does not stop projectiles;
   - distance-based pursuit and search preserved;
   - about one meaningful use per encounter space;
   - spending it mid-room versus saving it for the five-second door attempt.
7. **Door attempt:** SP4-2 (for consistency with the settled rule).
8. **Ranged enemies excluded:** SP4-5.
9. **Stale dependent:** NSC-017 VAL-003 gets a separate mechanical follow-up by the GER Orchestrator.
