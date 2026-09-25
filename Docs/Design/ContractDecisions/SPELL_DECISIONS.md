# Spell design decisions: NSC-007 Charged Fireball, NSC-008 Frost Field, NSC-009 Force Wave

GER Orchestrator (Claude), 2026-09-16, deciding the questions Vincent delegated on 2026-09-15 ("the remaining design questions (NSC-007, 008, 009, 030, 078) are delegated to Claude to decide"). Sources:
- GER packets `20260914-065058-NSC-007`, `20260914-065104-NSC-008` and `20260914-072739-NSC-009`;
- the question list `C:\nscrev\reports\ger-overnight-20260914.md`: Q10-12, 31-35, 45, 82, 83 and 86, plus the cross-spell note;
- the brief `C:\nscrev\ger-contract-revisions-20260916\briefs\spells-007-008-009.md`;
- local main `95492e43d`.

Guiding rules:
- **The GDD.** Doors buy time, not safety. Fireball punishes groups but is unsafe once enemies close. Frost Field creates an opening. Force Wave is the emergency answer to being surrounded.
- **What Vincent already plays.** The 9/16 playable build casts a fireball on right-click.
- **Consistency with NSC-054.** The Ranged Enemy projectile stops at non-trigger gameplay cover.

## Shared decisions (all three spells)

### S1. Controls (Q10, Q32, Q86; NSC-007 D1, NSC-008 #1, NSC-009 #2)
- **Three dedicated Actions** go in the `Player` map of `Assets/InputSystem_Actions.inputactions`, all Button type, Keyboard&Mouse control scheme only. Each spell adds its own Action:
  - `Fireball` on `<Mouse>/rightButton`. Press starts a charge, hold charges, release casts. A quick press and release is the tap cast.
  - `FrostField` on `<Keyboard>/q`. Press casts at the current pointer world target.
  - `ForceWave` on `<Keyboard>/space`. Press casts centered on the wizard. NSC-009 removes the `<Keyboard>/space` binding from the unused stock `Jump` action, so no keyboard path is shared.
- **No select-spell-then-Attack scheme.** The stock `Attack` action is left untouched. No gamepad binding now.
- **No hardware polling.** Each spell reads only its own Action; no `Mouse.current` or `Keyboard.current` polling. No spell binding path may also be bound to `MoveToCursor`, `Interact` or another spell's Action.

### S2. Casting never resets a door attempt (NSC-008 #2, NSC-009 #5, and Fireball)
- **Door attempts continue.** Casting or charging any spell never cancels or resets a door-opening attempt; the five-second timer continues. This follows GDD:76, where Frost Field "creates an opening to ... begin opening a door", and GDD:68/94, whose reset triggers are damage, moving away and a replacing command. A stationary cast is none of those.
- **No door or interaction calls.** Spells never call `PlayerInteractionController` or `DoorInteractable` methods.
- **One movement exception.** Fireball's charge may hold its own `PlayerMovement` movement restriction; that is the only movement call any spell makes.

### S3. Title screen and game entry (cross-spell gap; NSC-007 R-01/R-03, NSC-009 R-01)
Every spell uses the same pattern and keeps it inside its own contract, without reopening NSC-066 or NSC-068:
- **Optional references.** Add an optional serialized reference to the spell component on `TitleScreenController` and on `WizardGameEntryController`.
- **Suspend and re-enable.** `TitleScreenController.SuspendGameplayInput()` calls the spell's `SuspendGameplayInput()` when the reference is assigned. `WizardGameEntryController.EnterWorld` calls the spell's `EnableGameplayInput()` right after it enables `PlayerMovement` and `PlayerInteractionController`.
- **Missing references are fine.** A missing spell reference never makes `HasValidReferences()` fail.
- **Not in the behaviour array.** A spell is never added to `gameplayInputBehaviours`, whose entries are disabled with no re-enable path. The array keeps its two debug controls, so `TitleScreenSceneBuilderTests`' array-size assertion is unaffected.
- **Builder and tests.** The builder assigns the references. Each spell's Play Mode tests prove its Action does nothing before `EnterWorld` (no mana spent, no cast state) and works after it.
- **Resources.** Each spell claims `Assets/NoSafeCircle/DoorPrototype/Scripts/TitleScreenController.cs` and `.../WizardGameEntryController.cs`; resource groups are reconciled at commit.

### S4. Walls and closed doors block spells (NSC-007 D2, NSC-009 #1)
- **What blocks.** Solid gameplay colliders block both Fireball and Force Wave: walls, obstacle and prop colliders (shelves, pews, columns, rubble) and any door whose doorway blocker is enabled: sealed, locked and broken doors (a broken door keeps its one-way player blocker by design, DoorInteractable.Break). Only an open door the wizard has not yet crossed doesn't block. Revised 2026-09-17 after the drafter found Break() keeps the blocker.
- **How to test it.** A chest-height `Physics.Raycast` or sweep against non-trigger colliders that ignores the wizard's own `CharacterController`, as `EnemyFireballCaster` already does. No new layer, tag, collider or query API is invented.
- **How enemies are hit.** Enemies carry no colliders, so contact is a flat horizontal distance test against active, non-defeated `EnemyHealth` objects, as the playable build does. No task has to add enemy colliders, and NSC-007's INT-004 collider obligation is dropped.

### S5. Placeholder feedback is acceptable (NSC-007 D6, NSC-009 #4)
- **Placeholders are fine for the first playable.** Programmer-placeholder visuals are acceptable, as GDD:566 allows: a colored primitive or simple generated sprite for the charge, projectile and blast; a flat translucent area marker for Frost Field; a brief pulse plus the existing cooldown UI for Force Wave.
- **No new art.** No art assets beyond the files each contract lists. Real art comes later through the Art Director.
- **Force Wave extras.** The instant `NavMeshAgent.Warp` knockback and silent presses during cooldown are acceptable for the prototype; Vincent's review may ask for more.

### S6. Enemies the spells affect in the current scene (new; brief section 4.3)
- **Melee enemies get the status-effect component.** Frost Field and Force Wave act through NSC-013's `EnemyStatusEffectMovement`, which no scene enemy has today. NSC-008 and NSC-009 each make sure every `MeleeEnemy` built by `DoorPrototypeGlobalSceneBuilder.BuildChaseEnemy` has exactly one `EnemyStatusEffectMovement`: add it if absent, never twice. Whichever lands first adds it; the second finds it.
- **The Lantern Wraith is not affected.** It is stationary, has no `NavMeshAgent`, and `EnemyStatusEffectMovement` requires one. Neither spell affects it in the current scene. The later Ranged Enemy prefab (NSC-055) decides status effects for a moving ranged enemy.
- **Finding enemies.** Spells find candidates with `FindObjectsByType<EnemyStatusEffectMovement>` (active and enabled, `EnemyHealth.IsDefeated == false`) at cast time, and Frost Field also at a serialized refresh interval while active. No new registry or discovery API is required. This settles NSC-008 R-03's discovery half.

### S7. Graph edges (Q45)
- **No new dependency on the unfinished enemy prefabs.** No spell depends on NSC-015's or NSC-055's prefabs. Validation against assembled prefabs stays a downstream obligation, so each spell remains dispatchable on its own.
- **No dependency on NSC-066 or NSC-068.** Their controller code is on main, and S3 edits it directly.

## NSC-007 Charged Fireball
- **D3, aim and range.** Aim is direction-only: the direction from the wizard to the pointer world target on the gameplay plane. The projectile flies until it touches an enemy or a blocking collider (S4), then detonates. At its serialized maximum lifetime with no hit it fizzles and deals no damage. A cursor-destination detonation (Candidate B) is not added.
- **Detonation and damage.**
  - Detonation damages the contacted enemy and, for area tiers, every other active enemy within the tier's radius that has an unobstructed line from the detonation point (S4). Nothing behind a wall or a closed door is damaged.
  - Damage goes only through `EnemyHealth.TakeDamage`. The caster is never hit.
- **D4, mana; Q82/Q83, denial timing.**
  - **At press:** a charge starts only if `PlayerMana.CurrentMana` covers the tap cost. Otherwise the press calls `PlayerMana.Spend(tap cost)`, which returns false and raises `CastDenied`, and no charge, restriction or projectile state starts. Denial happens when charging starts.
  - **While charging:** the charge tier grows with hold time but is always capped at the highest tier `CurrentMana` can pay at that moment, so the charge visibly stops growing when mana runs short.
  - **At release:** Fireball calls `PlayerMana.Spend` exactly once, for the reached tier's cost. If that returns false (only possible if mana fell below the tap cost during the charge), `CastDenied` fires and nothing launches. Every cost is greater than zero.
- **D5, interruption.**
  - Taking damage (`PlayerHealth.Damaged`) cancels an active charge: no projectile, no mana spent, and Fireball's movement restriction is released exactly once.
  - Move clicks and door clicks during a charge don't cancel it. The wizard stays rooted until release or cancellation, and existing `PlayerMovement` behavior applies the latest destination afterwards.
  - There is no separate abort input.
  - A tap cast doesn't root the wizard.
  - "Loss of a valid pointer target" is not a cancellation (R-04 wording): a release that finds no valid pointer target casts nothing and spends nothing.
- **Tuning start.** The tap tier starts at the playable build's values so its feel doesn't regress: 20 mana, 25 damage, speed 12, lifetime 3 s, contact radius 0.9, cooldown 0.5 s. Charged tiers raise cost, damage and area monotonically, all serialized.
- **The playable build's fireball goes away.** NSC-007 replaces it. Remove `DemoRunFlow`'s right-click fireball (TryFireAtCursor, AdvanceFireballs, its Fireball struct, the fireball fields and its `Mouse.current` polling). Keep its enemy contact damage, health bars, win and death screens and R restart. NSC-007 claims `Assets/NoSafeCircle/DoorPrototype/Scripts/DemoRunFlow.cs`, so one Fireball exists.
- **Non-design fixes.** R-02 is no longer needed under S3. R-04, R-06 (VAL-004 rewritten with these outcomes), R-07 (Fireball.ResetFireball before PlayerMovement.ResetMovement) and R-08 (no NSC-066/068 dependency; S7) apply. R-05: decomposition_state returns to concrete, because the decisions are now written in.

## NSC-008 Frost Field
- **Recast (#3).** Only one Frost Field exists at a time. A new successful cast replaces the active field: the old field ends, releasing its slows immediately, and the new one starts. Each cast spends mana once.
- **Victory (#4).** Victory suspension clears an active field immediately and restores every slowed enemy's speed.
- **Membership.** An enemy is slowed while its horizontal position is inside the field. The field refreshes `EnemyStatusEffectMovement.ApplyFrostSlowdown(multiplier, duration)` at a serialized interval (default 0.2 s), with a duration a little longer than the interval, so the slow ends shortly after the enemy leaves or the field expires. NSC-013's reset and the pursuit path restore speed; no permanent slowdown remains.
- **Precondition removed.** The AC-005 precondition that NSC-003 must "restore" the Input Actions asset is dropped. The asset exists on main, and the claim came from a snapshot-scope artifact. Use the same read-only pre-dispatch check NSC-007 uses.
- **Non-design fixes.** R-01, R-02 (placeholders replaced with these rules and matching assertions), R-04, R-05, R-06 and R-07 apply. R-03's discovery half is settled by S6; its begin/refresh half already exists (`ApplyFrostSlowdown`, `ResetStatusEffects`).

## NSC-009 Force Wave
- **Geometry (#1).** Blocked (S4). Only eligible enemies within the radius that have an unobstructed chest-height line from the wizard are displaced.
- **Balance owner (#3).** INT-004 stays an explicit, unowned downstream obligation for now. No new task is created.
- **Feedback (#4).** As in S5.
- **Door timer (#5).** Confirmed: a cast never resets the door attempt (S2).
- **Non-design fixes.** R-01 (the S3 pattern, instead of INT-003), R-02, R-03, R-04 (resource-group reconciliation happens at commit), R-06 and R-07 apply. Space is removed from `Jump` (S1).
