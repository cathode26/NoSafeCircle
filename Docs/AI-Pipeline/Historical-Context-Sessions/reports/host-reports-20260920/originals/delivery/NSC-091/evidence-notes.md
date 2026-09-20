# NSC-091 delivery evidence: working notes

Game Agent, 2026-09-18. Contract revision 2, canonical main `2559514826e919bea243e1bf6fda4ad73462ac62`.
Policy filter (PlayMode only): `NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests`.

NSC-091's implementation has been on main for some time — `38904af15` ("Implement enemy target
knowledge and bounded search state") and `9a3d22c56` ("Playable build: chase enemy, fire-caster
enemy, fireball, win and death screens"). Only the record is missing, and **eight tasks are blocked
behind it**. This is evidence debt, not a defect.

## Preflight, done before spending the Unity run

- **Contract hash binds at HEAD.** `git show HEAD:Tasks/NSC-091.yaml | sha256sum` =
  `3ba557ed37174f0f5198efd263d034788cb45965cd35c259139b3bdedf8b35af`, which is exactly
  `task_contract_sha256` in `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`.
  (Hashed from the committed LF blob, not the CRLF worktree file — the worktree file gives a
  different value and fails the gate.)
- **The fixture exists, proved by declaration, not by filename.**
  `public class EnemyTargetKnowledgePlayModeTests` at
  `Assets/NoSafeCircle/DoorPrototype/Tests/EnemyTargetKnowledgePlayModeTests.cs:8`. Not `partial`.
  Namespace `NoSafeCircle.DoorPrototype.Tests` matches the filter exactly.
- **Tests counted before the run: 22 `[Test]`, no `[UnityTest]`, no `[TestCase]`.** A filter that
  resolves to a real but empty fixture passes vacuously, which is the same failure as a
  zero-selection run wearing a better disguise. The runner refuses `total=0`; it does not refuse a
  real fixture that happens to assert nothing.

## VAL-001 — the only gate

**Done.** `run_unity_tests_clean.ps1 -TestPlatform PlayMode -TestFilter <the policy filter>` at
`2559514826e919bea243e1bf6fda4ad73462ac62`: **22 tests, 22 passed, 0 failed, 0 skipped**, runner
exit 0, final line `VALIDATION PASSED`.

Counts read out of `test-results.xml`, not out of the console summary. Every one of the 22
`<test-case>` elements reports its declaring type as
`NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests` — the type the policy names.

Bound manifest `validated_state`: commit and post_commit both
`2559514826e919bea243e1bf6fda4ad73462ac62`, tree and post_tree both
`7ddb061ebe28e54eac6988b665c6b5fc6c5162fc`, `repository_clean_before` and
`repository_clean_after` both true. The run mutated nothing.

Artifacts: `C:\nscrev\reports\delivery\NSC-091\val-playmode-20260918\` —
`test-results.xml` (sha256 `1391c7a77e3ccd522fe3b14252c54d7d87be44201b0cec83081acd470b1ad99f`),
`unity.log`, `validation-manifest.json`, `run.txt`.

### The gate names eight behaviours. All eight are covered — mapped case by case

The gate is satisfied by the fixture's content, not by the pass count, so here is the mapping.

| Gate wording | Cases |
|---|---|
| strict threshold relationship | `ConfigureDistances_DetectionDistanceEqualToLoseTargetDistance_ThrowsArgumentException`, `..._GreaterThan..._ThrowsArgumentException`, `..._StrictlySmaller_UpdatesBothValues` |
| acquisition inside Detection Distance | `UpdateTargetKnowledge_WizardInsideDetectionDistance_AcquiresTargetAndEntersPursuing`, `..._WizardExactlyAtDetectionDistance_Acquires`, `..._WizardOutsideDetectionDistance_StaysIdle` |
| distance-only transition to the recorded last-known position | `..._PursuingWizardExceedsLoseTargetDistance_TransitionsToSearchingAndRecordsLastKnownPosition`, `..._PursuingWizardExactlyAtLoseTargetDistance_StaysPursuing`, `..._WizardPositionChangeWithinLoseTargetDistance_RetainsPursuit` |
| bounded search timing | `ReportArrivedAtLastKnownPosition_WhileSearching_EntersWanderingWithFullSearchDuration`, `..._WhileWanderingBeforeDurationElapses_StaysWandering`, `..._WanderingDurationFullyElapsesWithoutReacquisition_ClearsTargetAndReturnsToIdle` |
| reacquisition during search | `..._WizardReentersDetectionDistanceWhileSearchingBeforeArrival_ReacquiresAndReturnsToPursuing`, `..._WizardReentersDetectionDistanceWhileWandering_ReacquiresAndReturnsToPursuing`, `ResetTargetKnowledge_ThenWizardReentersDetectionDistance_CanAcquireAgain` |
| target clearing after search expires | `..._WanderingDurationFullyElapsesWithoutReacquisition_ClearsTargetAndReturnsToIdle`, `..._WizardDestroyedWhileWandering_StillExpiresAndClearsTarget` |
| persistence of the same enemy GameObject | `FullTargetLossAndExpiryCycle_DoesNotDestroyOrReplaceEnemyGameObject_AndAllowsReacquisitionLater` |
| `ResetTargetKnowledge()` | `ResetTargetKnowledge_WhilePursuing_ClearsTargetAndReturnsToIdle`, `..._WhileWandering_ClearsLastKnownPositionAndSearchTimer`, `..._ThenWizardReentersDetectionDistance_CanAcquireAgain` |

Three further cases are boundary and robustness coverage the gate does not name and does not
forbid: `InitialState_IsIdleWithoutTarget`, `ReportArrivedAtLastKnownPosition_WhileIdle_
DoesNotChangeState`, `UpdateTargetKnowledge_WithoutWizardWired_DoesNotThrowAndStaysIdle`.

## No human gate

NSC-091 has exactly one completion gate and it is a test gate. **Nothing here needs Vincent** until
the fast-forward of the finished evidence commit onto canonical `main`.

## Provenance to put in the record

The record binds `2559514826e919bea243e1bf6fda4ad73462ac62`, which is where Unity actually ran —
not the historical integration commit. `record_delivery` requires `HEAD == validated_commit`, and
main has moved since the implementation landed, so binding the historical commit would produce an
evidence commit that could never fast-forward main. Name `38904af15` and `9a3d22c56` in the notes
as the integration provenance instead.
