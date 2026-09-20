"""Fill the NSC-089 and NSC-091 delivery reviews truthfully and emit delivery specs.

Path B of the delivery-evidence guide (hand spec), deliberately, for one reason:
`generate_delivery_spec.py finalize` accepts `human_approval.required: false` only with notes
matching exactly "Automated validation event <64 hex>; committed validation policy <64 hex>.",
and that event id comes from the machine-authorized issue-workflow store (delivery_review.py ->
downstream_pipeline), which is a different workflow from this manual evidence pass. The only other
branch finalize offers is `required: true`, which would claim a human approval that did not happen.
Neither task's contract contains a human gate, so `required: false` with honest prose is the
truthful shape - and it is precedented: DEL-NSC-054, DEL-NSC-063 and DEL-NSC-065 are all committed
records with `required: false`, `decision: not_required`, blank approved_by and free-prose notes.
`record_delivery.py:231-248,622-638` accepts exactly that, with no regex on the notes.

Surfaces: ONLY each task's own exclusive_resources. A 1590-path `committed_diff` arrives
pre-selected because the base commit is far behind main; selecting those would claim NSC-091
delivered a year of unrelated files.

Writes, per task: review.filled.json (the reasoning, kept for the record) and delivery-spec.json.
"""
import json
import pathlib

ROOT = pathlib.Path(r"C:\nscrev\reports\delivery")

# ---------------------------------------------------------------- NSC-089

NSC089_SURFACES = {
    "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs":
        "Editor builder that creates the persistent builder-owned GameplayNavigation GameObject "
        "after room composition and removes any previous one (AC-001)",
    "Assets/NoSafeCircle/DoorPrototype/NoSafeCircle.DoorPrototype.asmdef":
        "Runtime assembly definition that carries the Unity.AI.Navigation reference AC-002 "
        "confines to it, which is why the test assembly reads NavMeshSurface by reflection",
    "Assets/NoSafeCircle/DoorPrototype/Scripts/World/GameplayNavigationSurface.cs":
        "Runtime owner of the NavMeshSurface: bakes with the project's single configured agent "
        "type from physics colliders, and clears baked data before a rebuild (AC-002)",
    "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/NavMeshAgentConfigurationTests.cs":
        "The EditMode fixture the committed validation policy names for this task",
    "Assets/Scenes/DoorPrototype.unity":
        "The canonical scene whose committed state the fixture validates and the builder "
        "re-materializes",
}

NSC089_ARTIFACTS = [
    {"id": "unity_01_results", "type": "unity_test_results", "name": "Unity-EditMode-01",
     "source_path": str(ROOT / "NSC-089" / "val-editmode-20260918" / "test-results.xml")},
    {"id": "unity_01_log", "type": "unity_log", "name": "Unity-EditMode-01",
     "source_path": str(ROOT / "NSC-089" / "val-editmode-20260918" / "unity.log")},
    {"id": "rebuild_recheck_01_results", "type": "unity_test_results",
     "name": "Unity-EditMode-AfterBuilderRun-01",
     "source_path": str(ROOT / "NSC-089" / "val001-rebuild-recheck" / "recheck1.xml")},
    {"id": "rebuild_recheck_02_results", "type": "unity_test_results",
     "name": "Unity-EditMode-AfterBuilderRun-02",
     "source_path": str(ROOT / "NSC-089" / "val001-rebuild-recheck" / "recheck2.xml")},
    {"id": "rebuild_recheck_transcript", "type": "other",
     "name": "VAL-001-rebuild-recheck-transcript.txt",
     "source_path": str(ROOT / "NSC-089" / "val001-rebuild-recheck.out")},
]

NSC089_GATE_NOTES = (
    "VAL-001 has three parts and each is evidenced separately.\n\n"
    "(1) The EditMode fixture at the validated commit, through run_unity_tests_clean.ps1: "
    "2 tests, 2 passed, 0 failed, 0 skipped, runner exit 0, final line VALIDATION PASSED. Counts "
    "read from test-results.xml, not from the console summary. Both cases report their declaring "
    "type as NoSafeCircle.DoorPrototype.Tests.Editor.NavMeshAgentConfigurationTests, which is the "
    "type the committed policy names; the fixture is a sealed, non-partial class, so the filter "
    "cannot silently select a subset. The bound manifest records commit and post_commit both "
    "2559514826e919bea243e1bf6fda4ad73462ac62 and tree and post_tree both "
    "7ddb061ebe28e54eac6988b665c6b5fc6c5162fc, clean before and after: the run mutated nothing.\n\n"
    "CommittedScene_HasSingleGameplayNavigationOwner_AndComposedFloorSupportsCompletePath is the "
    "case that carries the canonical-scene half of this gate. Against the committed scene it "
    "asserts the legacy Floor is absent from the root names, that exactly one GameplayNavigation "
    "root and exactly one GameplayNavigationSurface survive, that the surface uses the project's "
    "single configured agent type with collectObjects=All and useGeometry=PhysicsColliders (the "
    "composed FloorCollision and obstacle colliders, never the visual Tilemap renderers, which "
    "carry no collider), that the composed RuinedEntry FloorCollision exists, and that a "
    "test-owned NavMeshAgent configured with that same agent type computes a PathComplete between "
    "two sampled points inset on opposite sides of that floor. It closes the scene without saving "
    "and byte-compares the file, so validation does not modify the committed canonical scene.\n\n"
    "(2) and (3) The gate also requires the same check after the authorized builder materializes "
    "the scene, and again after repeating it. Both were run: builder exit 0, then the EditMode "
    "filter against the BUILT scene returned total=2 passed=2 failed=0 - twice, recorded as "
    "rebuild_recheck_01_results and rebuild_recheck_02_results. The scene's sha256 differs after "
    "each build (819f30eb committed -> 4673deda -> d971c0bb) and that is expected, not a defect: "
    "a rebuild is never byte-identical because recreated objects receive fresh random fileIDs. The "
    "gate asks that exactly one navigation owner survives and the composed-floor path still works, "
    "which both rechecks prove. The checkout was restored afterwards - 0 changes, scene sha256 back "
    "to 819f30eb, HEAD unmoved.\n\n"
    "Honest scope note: those two rechecks ran through raw batchmode Unity rather than "
    "run_unity_tests_clean.ps1, because a builder run dirties the committed scene on purpose and "
    "that wrapper refuses a dirty worktree. The BOUND manifest is the clean run in (1). The "
    "rebuild rechecks are supplementary evidence of the same fixture at the same commit, the same "
    "shape NSC-069's VAL-003 two-builds pass used, and their full transcript is recorded as "
    "rebuild_recheck_transcript."
)

NSC089_APPROVAL_NOTES = (
    "NSC-089 has exactly one completion gate, VAL-001, and it is an automated Unity gate; the "
    "contract contains no human gate, so no human approval is claimed. Delivery evidence recorded "
    "by the Game Agent (Integration Steward) on 2026-09-18 at canonical main "
    "2559514826e919bea243e1bf6fda4ad73462ac62, which is where Unity actually ran. That is not the "
    "historical integration commit: the implementation landed earlier in cadf65213 (Implement "
    "NSC-089) and 0468f92d6 (Use static NavMesh path query in EditMode), and main has moved since. "
    "record_delivery requires HEAD == validated_commit, so binding the historical commit would "
    "produce an evidence commit that could never fast-forward main. This record is evidence debt "
    "being paid on merged work, not a claim that the work landed today. The task's "
    "assistant-control record from a superseded 2026-09-14 run is not the validated state and is "
    "not relied on here. Scene visuals, enemy behaviour and room-level navigation lanes belong to "
    "NSC-090, NSC-092 and NSC-071 and are not claimed."
)

# ---------------------------------------------------------------- NSC-091

NSC091_SURFACES = {
    "Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyTargetKnowledge.cs":
        "Runtime component under test: detection and lose-target thresholds, target acquisition, "
        "last-known-position recording, bounded search timing and ResetTargetKnowledge()",
    "Assets/NoSafeCircle/DoorPrototype/Tests/EnemyTargetKnowledgePlayModeTests.cs":
        "The PlayMode fixture the committed validation policy names for this task",
}

NSC091_ARTIFACTS = [
    {"id": "unity_01_results", "type": "unity_test_results", "name": "Unity-PlayMode-01",
     "source_path": str(ROOT / "NSC-091" / "val-playmode-20260918" / "test-results.xml")},
    {"id": "unity_01_log", "type": "unity_log", "name": "Unity-PlayMode-01",
     "source_path": str(ROOT / "NSC-091" / "val-playmode-20260918" / "unity.log")},
]

NSC091_GATE_NOTES = (
    "Authoritative PlayMode run at the validated commit through run_unity_tests_clean.ps1: "
    "22 tests, 22 passed, 0 failed, 0 skipped, runner exit 0, final line VALIDATION PASSED. Counts "
    "read from test-results.xml, not from the console summary. All 22 cases report their declaring "
    "type as NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests, the type the "
    "committed policy names; it is a sealed-shaped, non-partial class, so the filter cannot "
    "silently select a subset. The bound manifest records commit and post_commit both "
    "2559514826e919bea243e1bf6fda4ad73462ac62 and tree and post_tree both "
    "7ddb061ebe28e54eac6988b665c6b5fc6c5162fc, clean before and after: the run mutated nothing.\n\n"
    "The gate names eight behaviours, and the pass count alone does not show they are covered, so "
    "each is mapped to its cases. Strict threshold relationship: "
    "ConfigureDistances_DetectionDistanceEqualToLoseTargetDistance_ThrowsArgumentException, "
    "ConfigureDistances_DetectionDistanceGreaterThanLoseTargetDistance_ThrowsArgumentException, "
    "ConfigureDistances_DetectionDistanceStrictlySmaller_UpdatesBothValues. Acquisition inside "
    "Detection Distance: UpdateTargetKnowledge_WizardInsideDetectionDistance_AcquiresTargetAnd"
    "EntersPursuing, UpdateTargetKnowledge_WizardExactlyAtDetectionDistance_Acquires, "
    "UpdateTargetKnowledge_WizardOutsideDetectionDistance_StaysIdle. Distance-only transition to "
    "the recorded last-known position: UpdateTargetKnowledge_PursuingWizardExceedsLoseTarget"
    "Distance_TransitionsToSearchingAndRecordsLastKnownPosition, UpdateTargetKnowledge_Pursuing"
    "WizardExactlyAtLoseTargetDistance_StaysPursuing, UpdateTargetKnowledge_WizardPositionChange"
    "WithinLoseTargetDistance_RetainsPursuit. Bounded search timing: ReportArrivedAtLastKnown"
    "Position_WhileSearching_EntersWanderingWithFullSearchDuration, UpdateTargetKnowledge_While"
    "WanderingBeforeDurationElapses_StaysWandering, UpdateTargetKnowledge_WanderingDurationFully"
    "ElapsesWithoutReacquisition_ClearsTargetAndReturnsToIdle. Reacquisition during search: "
    "UpdateTargetKnowledge_WizardReentersDetectionDistanceWhileSearchingBeforeArrival_Reacquires"
    "AndReturnsToPursuing, UpdateTargetKnowledge_WizardReentersDetectionDistanceWhileWandering_"
    "ReacquiresAndReturnsToPursuing, ResetTargetKnowledge_ThenWizardReentersDetectionDistance_"
    "CanAcquireAgain. Target clearing after search expires: the wandering-expiry case above and "
    "UpdateTargetKnowledge_WizardDestroyedWhileWandering_StillExpiresAndClearsTarget. Persistence "
    "of the same enemy GameObject: FullTargetLossAndExpiryCycle_DoesNotDestroyOrReplaceEnemy"
    "GameObject_AndAllowsReacquisitionLater. ResetTargetKnowledge(): ResetTargetKnowledge_While"
    "Pursuing_ClearsTargetAndReturnsToIdle, ResetTargetKnowledge_WhileWandering_ClearsLastKnown"
    "PositionAndSearchTimer, and the reacquire-after-reset case above. Three further cases are "
    "boundary and robustness coverage the gate neither names nor forbids: InitialState_IsIdle"
    "WithoutTarget, ReportArrivedAtLastKnownPosition_WhileIdle_DoesNotChangeState, and "
    "UpdateTargetKnowledge_WithoutWizardWired_DoesNotThrowAndStaysIdle."
)

NSC091_APPROVAL_NOTES = (
    "NSC-091 has exactly one completion gate, VAL-001, and it is an automated PlayMode gate; the "
    "contract contains no human gate, so no human approval is claimed. Delivery evidence recorded "
    "by the Game Agent (Integration Steward) on 2026-09-18 at canonical main "
    "2559514826e919bea243e1bf6fda4ad73462ac62, which is where Unity actually ran. That is not the "
    "historical integration commit: the implementation landed earlier in 38904af15 (Implement "
    "enemy target knowledge and bounded search state) and 9a3d22c56 (Playable build), and main has "
    "moved since. record_delivery requires HEAD == validated_commit, so binding the historical "
    "commit would produce an evidence commit that could never fast-forward main. This record is "
    "evidence debt being paid on merged work, not a claim that the work landed today. Enemy "
    "NavMesh pursuit movement, door traversal and prefab wiring belong to NSC-092, NSC-015 and "
    "NSC-016 and are not claimed."
)

# ---------------------------------------------------------------- driver

PLAN = {
    "NSC-089": (NSC089_SURFACES, NSC089_ARTIFACTS, NSC089_GATE_NOTES, NSC089_APPROVAL_NOTES,
                ["unity_01_results", "unity_01_log", "rebuild_recheck_01_results",
                 "rebuild_recheck_02_results", "rebuild_recheck_transcript"]),
    "NSC-091": (NSC091_SURFACES, NSC091_ARTIFACTS, NSC091_GATE_NOTES, NSC091_APPROVAL_NOTES,
                ["unity_01_results", "unity_01_log"]),
}

for task_id, (owned, artifacts, gate_notes, approval_notes, evidence_ids) in PLAN.items():
    review_path = ROOT / task_id / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))

    # Every surface the task owns must actually be offered; a typo here would silently drop one.
    offered = {c["path"] for c in review["surface_candidates"]}
    missing = sorted(set(owned) - offered)
    if missing:
        raise SystemExit("%s: owned paths not offered as candidates: %s" % (task_id, missing))

    for candidate in review["surface_candidates"]:
        selected = candidate["path"] in owned
        candidate["selected"] = selected
        candidate["role"] = owned.get(candidate["path"], "")

    if len(review["gates"]) != 1:
        raise SystemExit("%s: expected exactly one gate, found %d" % (task_id, len(review["gates"])))
    review["gates"][0]["evidence"] = list(evidence_ids)
    review["gates"][0]["notes"] = gate_notes

    review["human_approval"] = {"required": False, "decision": "not_required",
                                "approved_by": "", "notes": approval_notes}
    review["review_status"] = "approved"
    (ROOT / task_id / "review.filled.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    spec = {
        "schema_version": "1.0",
        "task_id": task_id,
        "validated_commit": review["validated_commit"],
        "base_commit": review["base_commit"],
        "candidate_commit": review["candidate_commit"],
        "surfaces": [{"path": p, "role": owned[p]} for p in sorted(owned)],
        "artifacts": artifacts,
        "gates": [{"gate_id": review["gates"][0]["gate_id"],
                   "evidence": list(evidence_ids), "notes": gate_notes}],
        "human_approval": {"required": False, "decision": "not_required",
                           "approved_by": "", "notes": approval_notes},
    }
    spec_path = ROOT / task_id / "delivery-spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    selected_count = sum(1 for c in review["surface_candidates"] if c["selected"])
    print("%s: %d/%d surfaces selected, %d artifacts, gate %s -> %s"
          % (task_id, selected_count, len(review["surface_candidates"]), len(artifacts),
             spec["gates"][0]["gate_id"], spec_path))
    for artifact in artifacts:
        exists = pathlib.Path(artifact["source_path"]).is_file()
        print("    %-30s %s %s" % (artifact["id"], "OK " if exists else "MISSING", artifact["source_path"]))
