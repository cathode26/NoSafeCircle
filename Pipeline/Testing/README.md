# Clean Unity Test Execution

`Docs/Engineering/UNITY_TESTING_POLICY.md` defines the provider-neutral safety and evidence policy. `run_unity_tests_clean.ps1` is the authoritative deterministic Windows wrapper for a clean Unity test run. They exist because test assertions alone cannot establish that a run was safe or that the repository state being reported was preserved.

The immediate incident was a destructive camera-related Edit Mode test run. `DoorPrototypeSceneBuilderTests` passed all 11 assertions while calling the production `DoorPrototypeSceneBuilder.Build()` entry point. That entry point opens, clears, rebuilds, and saves the tracked canonical `DoorPrototype.unity` scene, so a nominally passing run rewrote a production asset.

## Authority boundary

The selected task contract and current approved GDD define required behavior. The testing policy defines how it may be proven safely. Neither this directory, the runner, nor an agent's assessment is game-design canon. The runner reports deterministic Unity and Git facts; it does not create conformance, readiness, delivery, or execution authorization.

## Running tests on Windows

From the repository root in Windows PowerShell:

```powershell
& .\Pipeline\Testing\run_unity_tests_clean.ps1 -TestPlatform EditMode -TestFilter "NoSafeCircle.DoorPrototype.Tests.Editor"
```

```powershell
& .\Pipeline\Testing\run_unity_tests_clean.ps1 -TestPlatform PlayMode -TestFilter "NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests"
```

Use `-UnityExecutable` to override the Unity Hub-derived executable path or `-ProjectPath` to select the Unity project. The project must begin completely clean, including untracked files. The runner fails if Unity changes HEAD or leaves any working-tree change, even when all assertions pass. It never restores or hides the changes.

## Artifacts and later evidence

XML results and the Unity log are initially written to a unique operating-system temporary directory outside the repository. This prevents the evidence mechanism itself from dirtying the checkout and preserves failed-run diagnostics for human inspection.

A later, separately reviewed Phase 3 workflow may select an XML artifact, copy it into the approved evidence location, and commit it as part of a record bound to the exact tested Git objects. This runner does not perform that copy, create a Phase 3 record, or imply that the artifact is sufficient evidence by itself.
