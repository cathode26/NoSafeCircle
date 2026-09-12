# Current handoff — 2026-09-10

Vincent controls task work through conversation. Use `python -m Pipeline.AssistantControl`;
the viewer is read-only. `README.md` describes commands. `STATUS.md` is a historical
development log; earlier limitations there may have been fixed by later entries.

## Implemented and focused-tested

- Inspect committed tasks, dependencies, capacity and resource conflicts.
- Prepare independent Git/Unity task projects and register explicit scopes.
- Launch explicitly authorized workers; stop exact worker trees; settle capacity.
- Verify crew artifacts, commit candidates, and preserve separate receipts per run.
- Authenticate and summarize retained crew result/patch bytes without mutation.
- Materialize Door Prototype assets and run the committed task-specific Unity
  validation before asking Vincent to inspect the exact resulting commit.
- Chain candidate registration and, where a Unity builder is registered,
  materialization into one bounded `post-crew` command for the orchestrator,
  returning `NEEDS_MATERIALIZATION` or `validation_failed` with the exact next
  command instead of retrying or approving anything itself.
- Record Vincent's exact-commit approval or rejection. Re-observation keeps decisions.
- Revise rejected work without discarding it, including fresh feedback after a merge.
- Synchronize Source into candidates repeatedly, preserve history and recover interrupted
  publication. Every changed candidate needs a new test decision.
- Integrate approved commits locally, preserve existing edits, and retain successful
  task projects. No automatic push or production publication.
- Plan and resume an explicit bounded task graph through the existing checkout,
  worker, candidate, validation, decomposition, review, and local-integration
  components. Transitive prerequisites and decomposition descendants are included.
- Auto-approve only authenticated synthetic Gauntlet candidates after their exact
  focused validations pass. NSC-042 always stops for Vincent's visual approval.
- Run a restricted `--delegate-safe` subset for cheaper helpers. It permits only
  portable checkout preparation/refresh and exact scoping, stopping before
  reservation, provider/Docker/Unity work, receipt processing, graph mutation,
  approval, synchronization, or integration.

The tests use disposable real Git repositories, fixture providers, and some real
Windows child processes. They do not prove paid-provider behavior or Unity visuals.
The post-crew, materialization and viewer path has 23 passing focused tests,
including unavailable-Unity recovery without a second crew candidate. The existing
production candidate-integration suite has 6 passing smoke tests.
Failed materialization tests now block approval and can enter the existing fresh
revision path with their exact failure text; the 13 admission/revision tests pass.
Recent parent results: synchronization 12 passed; fresh-feedback bridge 4 passed;
revision completion 2 passed; separate receipt/re-observation 2 passed. Exact timings
and fixture boundaries are in the final sections of `STATUS.md`.

## Actual project state

Source: `C:/NSC/TenTaskFinalIntegration-20260905`. Vincent's uncommitted generator,
architectural tiles and scene changes must remain untouched.

Task checkout: `C:/NSC/TenTaskFinalIntegration-20260905-AssistantCheckouts/NSC-042`,
branch `assistant/NSC-042`. Its current committed Source binding is
`57b32e84b020bd4c54b70aa8948c4409680ae4ee`. A real Claude crew was launched through
the assistant controller and rejected after reaching its turn limit. That worker is
settled and retained. The known-good restoration was mechanically synchronized with
the latest committed controller history. The exact candidate is
`1fdb2918af4daaf478232b9790b39fa8bb7989cd`; it retains the restored candidate as
lineage, is marked `crew_review: false`, and awaits Vincent's visual test. It is not
approved, integrated or published.

Known good reference: `C:/NSC/SuccessfullTasks/NSC-042`. Preserve it. Read
`Docs/AI-Pipeline/GAME_TASK_LESSONS_LEARNED.md` before creating or revising game tasks.

## Finish the goal

1. The actual launcher/runtime and rejected result have been demonstrated in a
   separate Unity checkout. Keep later provider work explicitly authorized.
2. Vincent tests exact candidate `1fdb2918af4daaf478232b9790b39fa8bb7989cd`
   and explicitly approves or rejects it. Integrate
   only an approved commit after resolving any Source working edits with him.

Retaining a conflicting merge safely is supported. An automatic conflict resolver,
decomposition is an explicit assistant operation: a two-role proposal remains
read-only until its exact independently reviewed plan is applied locally. GitHub
publication remains outside this controller.
Do not mark the goal complete from fixture approvals or add these as new blockers.

## Budget pause and Claude handoff — 2026-09-10

Vincent requested conservation of Codex usage and more work by Claude. Do not launch comparison crews or more helpers automatically. Both comparison setups under C:/NSC/AssistantControlEvidence/042-ab-20260910 remain unlaunched; comparison heartbeat is PAUSED. Vincent has the read-only log-analysis prompt to pass to Claude. Await that report before another experiment.

Observed: successful and recent implementer starting generator blobs are identical (SHA256 7c741147a4479102e0b5ced706afa2a60d3f5b334c4d156e33d60a9c54a0e498). Successful implementer made 21 calls; recent made 99, 90 aimed at WallTile.asset, ending error_max_turns. Historical one-attempt receipt does not prove first-ever success; earlier implementation 2a486123 is mentioned in preserved historical notes but its object was not found in the recovered clone. Do not infer model degradation or missing configured roles from this.

Separate demonstration checkout now contains reference generator/tests plus Unity-regenerated wall/scene. Three focused Unity tests passed; regenerated Texture2D pixels match recovered reference. This is an assistant restoration, NOT an independent crew success. See AssistantControlEvidence/crew-comparison/042-restored-verification.md. Incidental Unity changes were subsequently archived to 042-unity-incidental and excluded; four intended paths remain changed. No approval/integration/publication.

Controller repairs now include named Windows-job handle handoff, JSON provider-list conversion, and rejected-crew status and settlement. Real rejected run assistant-042-demo-20260910-four is settled, status failed, and capacity released. `register-restored-candidate` is wired into the common CLI and the viewer distinguishes `assistant_restored` from crew-reviewed work. Focused restored-candidate, settlement, launcher and Windows-job tests pass. Do not fabricate a reviewed-crew receipt.

Full AssistantControl audit: 145 tests passed in one discovery run. Four recovery
tests exposed a Windows-only fixture error that embedded CR as trailing whitespace
in generated patches; production correctly rejected those patches. The fixtures
now write LF-normalized bytes, and all four affected workflows pass on rerun. No
provider or GitHub operation was invoked by this audit.

Candidate synchronization also accepts an exact unreviewed `awaiting_human`
candidate when Source advances before Vincent's first test. It creates a mechanical
merge, grants no approval, and presents the new exact SHA for testing. Rejected or
otherwise advanced candidates remain ineligible. The source-sync suite and focused
authorization/recovery reruns pass.

The NSC-042 authoritative validation policy previously selected the unrelated
`GauntletTests` class. It now selects `DoorPrototypeSceneBuilderTests`, including
the repeating-pattern and stale-texture checks. Running the builder alone is not
acceptance: these tests judge deterministic behavior, and Vincent judges appearance.

The `readiness TASK` command now gives the assistant one compact, read-only answer
for dependencies, checkout/scope state, capacity, resource owners, and conflicting
Source edits. Its eight focused admission tests pass. On the current NSC-042 it
correctly refuses another worker because the candidate already awaits Vincent and
Source has edits to the builder and scene; it did not mutate either project.

## Windows materialization experiment — 2026-09-10

The controlled project `C:/NSC/NSC-042-BuildComparison` retained the fixed
generator/tests while its `WallTile.asset` and `DoorPrototype.unity` were restored
to the pre-fix commit. Vincent observed the bad wall, manually ran
`DoorPrototypeSceneBuilder.Build`, and then observed the fixed wall. The Build
changed 3,180 of 10,240 texture pixels; the resulting texture payload had zero
pixel differences from the preserved correct payload. Evidence is retained under
`C:/NSC/AssistantControlEvidence/NSC-042-build-comparison`.

Raw files did not compare byte-for-byte because Unity reassigned local YAML object
IDs and serialization order. Build also touched registered and incidental generated
files. The owned materializer must continue restoring unregistered tracked output
and judging semantic results/focused tests instead of using raw Unity YAML hashes.

The intended operating loop is now explicit: a Linux crew changes source and
focused tests; the assistant invokes Windows `materialize-candidate`; Windows Unity
runs the builder and exact-commit tests; source failures become compact retained
feedback for a bounded crew revision; Unity availability failures stop at
materialization; Vincent sees the exact candidate only after automated checks pass.
No retry launches implicitly, and no Build result grants human approval.

The individual commands already implement these stages. `post-crew` now joins
authenticated candidate registration and, when a Unity builder is registered,
materialization into one bounded step for the orchestrator to call after a crew
run ends, while preserving the existing explicit provider, review, integration
and publication boundaries. See its entry in `README.md`.

## Bounded graph controller — 2026-09-11

`graph-plan` and `run-graph` now provide the missing outer loop while reusing the
existing AssistantControl components. The controller executes one durable action,
re-reads Source and task records, and plans again. It stops on unknown failures,
never pushes, and writes viewer-visible state to
`<checkout-root>/.assistant-control/graph-controller.json`.

Focused verification passed: 29 review/controller/viewer tests, followed by seven
controller tests after dependency-closure and fresh-state fixes. A disposable
real-project smoke test proved NSC-1010 brings NSC-1015/1016, NSC-1013/1014, and
NSC-1001 into scope. A `--delegate-safe` smoke run prepared and scoped NSC-042,
then returned `handoff_required` before reservation. No provider, Unity, GitHub,
or live task-graph work ran during these checks.
