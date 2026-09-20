# NSC-089 delivery evidence: working notes

Game Agent, 2026-09-18. Contract revision 2, canonical main `2559514826e919bea243e1bf6fda4ad73462ac62`.
Policy filter (EditMode only): `NoSafeCircle.DoorPrototype.Tests.Editor.NavMeshAgentConfigurationTests`.

Implementation has been on main since `cadf65213` ("Implement NSC-089") and `0468f92d6` ("Use
static NavMesh path query in EditMode"). Only the record was missing, and **nine tasks depend on
it**. Evidence debt, not a defect.

## Preflight, done before spending the Unity run

- **Contract hash binds at HEAD.** `git show HEAD:Tasks/NSC-089.yaml | sha256sum` =
  `deb4d69bfa32162e21cbfa3ea29825de9ac99b1d60811b811e6b800f4ed0c9bd`, matching
  `task_contract_sha256` in `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`.
  (Note the path — **TaskReviewAgent**, not TaskGraph. My first look went to the wrong directory.)
- **Fixture proved by declaration:** `public sealed class NavMeshAgentConfigurationTests` at
  `Tests/Editor/NavMeshAgentConfigurationTests.cs:20`. Not `partial`. Namespace
  `NoSafeCircle.DoorPrototype.Tests.Editor` matches the filter exactly.
- **Tests counted before the run: 2 `[Test]`.** Both ran.

## VAL-001 is three checks, not one. This is the part that is easy to under-read

The gate's own wording asks for the EditMode fixture, **then** the same check after the authorized
`No Safe Circle/Build Door Prototype Scene` command materializes the scene, **then** a repeat of
the builder and another recheck. The fixture's comment says so too. A record that shipped only the
clean 2/2 run would be claiming a third of the gate.

### (1) The bound manifest run — the record's authoritative evidence

`run_unity_tests_clean.ps1 -TestPlatform EditMode -TestFilter <policy filter>` at the validated
commit: **2 tests, 2 passed, 0 failed, 0 skipped**, runner exit 0, `VALIDATION PASSED`. Counts read
from `test-results.xml`. `validated_state`: commit and post_commit both `2559514826e9…`, tree and
post_tree both `7ddb061ebe…`, clean before and after.

`CommittedScene_HasSingleGameplayNavigationOwner_AndComposedFloorSupportsCompletePath` is the case
carrying the canonical-scene half: legacy `Floor` absent from root names, exactly one
`GameplayNavigation` root, exactly one `GameplayNavigationSurface`, surface on the project's single
configured agent type with `collectObjects=All` and `useGeometry=PhysicsColliders`, composed
`Room_RuinedEntry/GameplayGeometry/FloorCollision` present, and a test-owned `NavMeshAgent` on that
same agent type computing `PathComplete` between two points inset on opposite sides of that floor.
It closes without saving and byte-compares the scene file afterwards.

**Why `PhysicsColliders` is the interesting assertion:** it is what makes "navigation uses the
composed FloorCollision and obstacle colliders rather than visual Tilemaps" a checkable claim.
Visual Tilemap renderers carry no collider, so a surface baking from physics colliders cannot be
reading them.

### (2) and (3) The builder rechecks

`val001-rebuild-recheck.sh`, output in `val001-rebuild-recheck.out`:

| step | result |
|---|---|
| builder materialization 1 | exit 0, scene `819f30eb…` → `4673deda…`, 312 paths dirty |
| recheck 1 (EditMode, against the **built** scene) | total=2 passed=2 failed=0 |
| builder materialization 2 | exit 0, scene → `d971c0bb…`, 312 paths dirty |
| recheck 2 | total=2 passed=2 failed=0 |
| restore | 0 changes, scene sha256 back to `819f30eb…`, HEAD unmoved |

**The scene hash differs after every build and that is correct, not a defect.** A rebuild is never
byte-identical — recreated objects receive fresh random fileIDs. The gate asks that exactly one
navigation owner survives and the composed-floor path still works, which is what the rechecks
assert, not that the file is unchanged.

**Honest scope note, written into the gate notes as well:** those two rechecks ran through raw
batchmode Unity, not `run_unity_tests_clean.ps1`, because a builder run dirties the committed scene
on purpose and that wrapper refuses a dirty worktree. The **bound** manifest is (1). The rechecks
are supplementary evidence of the same fixture at the same commit — the shape NSC-069's VAL-003
two-builds pass used.

## One trap this pass hit, worth not repeating

The first attempt at the recheck script invoked Unity as
`-batchmode -quit -nographics … -runTests …`. **Unity honours `-quit` first and exits before the
test runner executes**: exit code 0, no XML written, nothing to read. It looked like a pass until
the XML parse failed. `run_unity_tests_clean.ps1:402-410` passes `-batchmode` with **no `-quit` and
no `-nographics`** for test runs; the fixed script copies that argument list and says why in a
comment. This is the same shape as the older lesson about reading stdout without stderr: the run
reported success and produced no evidence.

## No human gate

NSC-089 has exactly one completion gate and it is automated. The record uses
`human_approval.required: false`, `decision: not_required`, blank `approved_by`, with prose saying
why — the shape DEL-NSC-054, DEL-NSC-063 and DEL-NSC-065 already use. See
`C:\nscrev\reports\delivery\fill_and_spec.py` for why `generate_delivery_spec.py finalize` could
not be used for the last step.

## What this record does and does not unblock

NSC-089 has **9** direct dependents and NSC-091 has **8**, but that is 17 *blocking links*, not 17
tasks freed. Counted from the committed contracts at HEAD, **exactly one task becomes fully
unblocked: NSC-090** (`depends_on: [NSC-089]` and nothing else). Everything else still waits on
something.

The real shape is a chain, and it is worth knowing before planning the next pass:

```
NSC-089 ─→ NSC-090 ─→ NSC-092 ─→ NSC-013/015/016/017/053/054/071/077/088 …
NSC-091 ─┘            (NSC-014 = aggregate of NSC-091 + NSC-092)
```

**And NSC-090 and NSC-092 are the same kind of evidence debt.** Verified at HEAD: both have policy
entries whose contract hashes bind, and every named fixture exists by declaration —
`DoorEnemyPassabilityPlayModeTests` (5 `[UnityTest]`), and for NSC-092 both
`EnemyPursuitPlayModeTests` (7) and `EnemyPursuitDoorCrossingPlayModeTests` (3), the two filters its
policy entry joins with `;`. So the next two evidence passes are known-cheap, need no Vincent time,
and finishing them makes **NSC-014 conformant** as well, since NSC-014 is an aggregate of NSC-091
and NSC-092.
