# NSC-007 Charged Fireball — salvaged run, Unity results

Game Agent, 2026-09-18. Scratch clone: `C:/nscrev/nsc007-unity` (throwaway, HEAD `dd1d8b13`).
Registered candidate: `ce1e2283` on `assistant/NSC-007`, `kind: assistant_restored`, `crew_review: false`.

## Headline

The fireball works. **FINAL: EditMode 9/9, PlayMode 36/36 — all three failures fixed.**
Verified against the runner's own preserved artifacts, not an agent summary. Progression 33 -> 34 -> 36.
Fixes landed on `assistant/NSC-007` as `ac87fd00`. NSC-007 has since gone to decomposition, so this
is a record of what was measured, not a candidate for delivery.

## Tuning values the implementer chose

| | tap | full charge |
|---|---|---|
| mana | 20 | 40 |
| damage | 25 | 65 |
| radius | 0.9 contact | 2.5 area |

Charge time 1.5s past a 0.25s tap threshold. Projectile 12 units/s, 3s lifetime, 0.5s cooldown.
2.6x damage and 2x mana between tap and full — the health-bar and mana-bar difference will read on camera.

## The three PlayMode failures (ALL FIXED - causes below are the verified ones)

1. `SealedLockedAndBrokenDoors_BlockTheProjectile_ButAnUncrossedOpenDoorDoesNot`
   `A sealed door's doorway blocker must stop the projectile. Expected: 50.0 But was: 25.0`
   The enemy behind the sealed door took full tap damage.
   **CONFIRMED: the test's own fixture, two separate defects.** (a) `BuildDoor` made an unscaled
   `PrimitiveType.Cube` (1x1x1, y in [-0.5, +0.5]) while the real blocker is
   `new Vector3(2f, 2.5f, 0.3f)`. Chest height is `origin + Vector3.up`, i.e. y = 1.0, and `Fire()`
   zeroes `direction.y`, so the flight path cleared every test door. Now scaled to match the real
   blocker. (b) Found while fixing (a): `FireProjectileToward` aimed 500 units out, which crosses
   BEHIND the fixture camera at (0,10,-10) for the -Z directions, so the screen-point round trip
   failed and `Fire()` silently declined to cast — meaning the locked-door assertion had been
   passing vacuously with no projectile ever fired. Aim distance reduced to 20.
   The validator's separate claim that `BuildDoor` never calls `StartInteraction()` did NOT hold
   against the current file: all three calls were already present.
   Still says nothing about the real door geometry or Vincent's in-game report — that is NSC-097.

2. `ChargeTiers_ManaCostDamageAndAreaRadius_IncreaseMonotonically_FromTapToFullCharge`
   `Expected ManaSpent to fire. Expected: True But was: False`
   **CONFIRMED cause: the 0.5s `castCooldown`, not the validator's theory.** The test fired
   tap/partial/full back to back; `BeginPressAttempt()` refuses outright while `cooldownRemaining > 0`
   and never retries, so casts 2 and 3 were silently refused. Now waits 0.6s between casts, matching
   `SecondTap_WithinCooldown_...` which already proved that behaviour correct. Validator finding 3
   (holdDuration inflation) was a DEAD END: the increment is guarded by `isAttemptActive && isPressed`
   and `isPressed` is false on the release tick.

3. `SuspendGameplayInput_WhileCharging_ReleasesRestriction_AndRejectsInputUntilReEnabled`
   `Expected casting to work normally once re-enabled. Expected: 1 But was: 0`
   **A genuine PRODUCTION bug, found by no one but the test.** `Tick` early-returns while suspended,
   so `wasFireballPressed` went stale at whatever it was when the charge was interrupted; the next
   press then computed `isFreshPress = isPressed && !wasFireballPressed` as false and was swallowed.
   User-visible: hold right-click through a title or victory transition and the first click after is
   eaten. Fixed by resynchronizing `wasFireballPressed` to actual input state in
   `EnableGameplayInput()` — resynchronized, not cleared, so a button still held does not start a
   phantom charge. Null-guarded, since `WizardGameEntryController.EnterWorld` calls it optionally.

## The validator's three findings (recovered)

Recovered from
`C:/NSC/NoSafeCircle-AssistantCheckouts/NSC-007/Pipeline/ExecutionCrew/outputs/nsc-007-20260918t040502z/role_results/validator_1.json`
after the Pipeline Maintainer corrected my wrong search path. Status `needs_changes`.

1. **FireballProjectile.cs, AC-007** — **ALREADY FIXED, and my two claims about it were wrong.**
   The finding described the state BEFORE the repair cycle. `Tick` now calls
   `DetonateOnCollider(blockedContactPoint)`, which does exactly what the validator prescribed:

       private void DetonateOnCollider(Vector3 detonationPoint)
       {
           if (hasAreaDamage) { ApplyAreaDamage(detonationPoint, excludedEnemy: null); }
           Finish();
       }

   I twice told Vincent this defect was live, saying I had "confirmed" it when I had only repeated
   the validator without re-reading the code after the repair. I also claimed "no test covers this";
   `FullCharge_DetonatingAgainstAWall_StillSplashesNearbyUnobstructedEnemies` covers it at line ~999
   and passes. A subagent briefed on the false premise reached the same conclusion independently.
2. **FireballPlayModeTests.cs.** `BuildDoor` never calls `StartInteraction()`, so
   `DoorInteractable.Tick` early-returns while `IsInteracting` is false and the locked/broken/open
   sub-cases never open their doors. (Confirmed by failure 1.)
3. **Fireball.cs.** `HandleFireballInput` adds the current frame's deltaTime to `holdDuration`
   before checking `isFreshRelease`, so the release-detecting Tick inflates the reached tier by
   one step (~0.32 mana against a 0.05 tolerance). (Confirmed by failure 2.)

Implementer 2 fixed finding 1 COMPLETELY (contact point plus the area sweep) and was correctly
barred from finding 2 by write scope. Test Author 2 died 65s in without addressing it.

## CORRECTED: the PlayMode filter names a nonexistent type (the gate CATCHES it)

`authoritative_validation_policy.json` binds:

    PlayMode: NoSafeCircle.DoorPrototype.Tests.FireballPlayModeTests

**No such type exists.** The test author wrote five fixtures over an abstract base:
`FireballTapAndCooldownPlayModeTests`, `FireballChargeTierPlayModeTests`,
`FireballCancellationAndSuspensionPlayModeTests`, `FireballCollisionPlayModeTests`,
`FireballDoorInteractionPlayModeTests`.

**CORRECTION (2026-09-18).** An earlier version of this file said the runner prints
`VALIDATION PASSED` on a zero-selection filter. That was FALSE and it was my error. The runner
hard-fails. Its stderr, which I had on disk and did not open:

    RESULT FAILURE: Unity discovered zero tests for platform 'PlayMode' and filter
    'NoSafeCircle.DoorPrototype.Tests.FireballPlayModeTests'.

`run_unity_tests_clean.ps1:525` has guarded this unconditionally since 2026-09-03, and
`record_delivery.py:405` independently raises on `total == 0`. The `Result: Passed (total=0 ...)`
line is raw Unity's own output on stdout; the runner's verdict is the opposite. I read stdout
only, saw Unity's line, and asserted the rest. The Pipeline Maintainer re-derived it and caught me.

So what remains is an ordinary contract bug: the bound filter names a type that does not exist, so
a run selects zero tests and PARKS the candidate at a loud failure. It does not manufacture a
false pass. Fixing it is GER's, in whatever NSC-007 becomes after decomposition.

Two fixes, different owners:
- **Rename the tests** so `FireballPlayModeTests` exists as the VAL rows describe (Game Agent;
  means consolidating five fixtures into one 36-test class).
- **Change the policy** to cover the five fixtures (GER Agent; the policy binds the contract
  hash, so it needs a contract revision and a rebind in the same commit).
- ~~Recommended to the Pipeline Maintainer: make the runner refuse a zero-selection run.~~
  WITHDRAWN - it already does, and has since 2026-09-03.

## What I changed

One compile fix, in the scratch clone only:
`FireballCommittedSceneConformanceTests.cs` — `expected` was `new[]` of unnamed `(string, string)`
while `actual` was `List<(string path, string groups)>`, so `expected[i].path` did not compile
(`error CS1061` x2). Now `new (string path, string groups)[]`. **Nothing in the crew compiles its
own work**, so this was the first compile of any of it; production code was clean on the first try.

**The registered candidate `ce1e2283` still contains the non-compiling test.** Landing the fix
needs a deliberate step: `register-restored-candidate` refuses to replace a differing candidate
("an existing candidate differs; retained for inspection").

## Why the run died

`launch.config.json timeout_seconds: 3600`; measured elapsed **3604s**. The host worker was killed
mid Test Author 2. Role timings: Implementer 1 642.1s, Test Author 1 2138.6s, Validator 1 571.8s,
Implementer 2 59.7s, Test Author 2 ~65s. Per-role budgets are 3600s **each** while the worker's
whole lifetime is also 3600s, so a full crew plus a repair cycle cannot fit. Reported to the
Pipeline Maintainer, who has `fix/validator-wall-budget` a7d2fbc7b ready (unmerged, awaiting
Vincent's own go).

## Open items

- Registered candidate carries a non-compiling test (above).
- `materialize-candidate` refuses restored candidates: `only a crew-reviewed code candidate can be
  materialized`. So this candidate can never produce a delivery-grade manifest. A proper record
  needs a fresh crew run on a worker with a real timeout.
- NSC-046 still holds a stale admission; `settle-worker` refuses it because its reservation is
  owned by a run that was admitted and never started. Gate 5, Pipeline Maintainer's.
- AC-VR (Vincent's human Play Mode review) cannot be fully satisfied yet: it asks for Ruined
  Entry's rubble and Chapel's aisle, and those rooms do not exist.
