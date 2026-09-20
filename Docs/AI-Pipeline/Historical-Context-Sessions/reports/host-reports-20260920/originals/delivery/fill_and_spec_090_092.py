"""Fill the NSC-090 and NSC-092 delivery reviews truthfully and emit delivery specs.

Same path B as fill_and_spec.py, for the same reason: neither task has a human gate, and
`generate_delivery_spec.py finalize` offers only `required: true` (which would claim a human
approval that did not happen) or `required: false` with notes bound to a machine-authorized
validation event id this manual pass does not have. `record_delivery.py` accepts
`required: false` with honest prose, as DEL-NSC-054/063/065 already do.

Surfaces: ONLY each task's own exclusive_resources. `logical:` resources are not files and are
not surfaces. A ~1600-path committed_diff arrives pre-selected because the base commit is far
behind the validated commit; selecting those would claim these tasks delivered unrelated files.

NSC-092 has TWO gates satisfied by ONE Unity run: its policy filter joins two fixtures with a
semicolon, and the run selected both (7 + 3 = 10, verified per declaring type in the XML). Both
gates therefore cite the same artifacts, and the notes say which cases carry which gate.
"""
import json
import pathlib

ROOT = pathlib.Path(r"C:\nscrev\reports\delivery")

# ---------------------------------------------------------------- NSC-090

NSC090_SURFACES = {
    "Assets/NoSafeCircle/DoorPrototype/Scripts/World/DoorEnemyPassability.cs":
        "Runtime component under test: owns one NavMeshObstacle sized to the doorway and carves "
        "or releases it from the baked walkable NavMesh according to the semantic door state",
    "Assets/NoSafeCircle/DoorPrototype/Tests/DoorEnemyPassabilityPlayModeTests.cs":
        "The PlayMode fixture the committed validation policy names for this task",
}

NSC090_ARTIFACTS = [
    {"id": "unity_01_results", "type": "unity_test_results", "name": "Unity-PlayMode-01",
     "source_path": str(ROOT / "NSC-090" / "val-playmode-20260918" / "test-results.xml")},
    {"id": "unity_01_log", "type": "unity_log", "name": "Unity-PlayMode-01",
     "source_path": str(ROOT / "NSC-090" / "val-playmode-20260918" / "unity.log")},
]

NSC090_GATES = {
    "VAL-001": (
        ["unity_01_results", "unity_01_log"],
        "Authoritative PlayMode run at the validated commit through run_unity_tests_clean.ps1: "
        "5 tests, 5 passed, 0 failed, 0 skipped, runner exit 0, final line VALIDATION PASSED. "
        "Counts read from test-results.xml, not from the console summary. All 5 cases report their "
        "declaring type as NoSafeCircle.DoorPrototype.Tests.DoorEnemyPassabilityPlayModeTests, the "
        "type the committed policy names; it is a public sealed, non-partial class, so the filter "
        "cannot silently select a subset. The bound manifest records commit and post_commit both "
        "161982676b2cafbfd48c9aae1eba9d92e9fec55f and tree and post_tree both "
        "c83562cf735d1d7a4d6828bd880ee0f72c21c8ff, clean before and after: the run mutated "
        "nothing.\n\n"
        "The gate asks for all four semantic states, and all four are covered by name: "
        "SetDoorState_Sealed_BlocksCompletePath and SetDoorState_Locked_BlocksCompletePath prove "
        "sealed and locked prevent a complete path through the opening; "
        "SetDoorState_Open_AllowsCompletePath and SetDoorState_Broken_AllowsCompletePath prove "
        "open and broken allow one. SetDoorState_AcrossAllFourStatesInSequence_MatchesEach"
        "ExpectedPassability additionally walks all four in sequence on one doorway, which is what "
        "shows the obstacle is released and re-carved rather than only being correct on first "
        "application. The fixture builds its own NavMesh floor, doorway and GameplayNavigationSurface "
        "from temporary scene objects; the manifest's clean-before/clean-after pair is the evidence "
        "that Assets/Scenes/DoorPrototype.unity was not saved or modified, as the gate requires."),
}

NSC090_APPROVAL = (
    "NSC-090 has exactly one completion gate, VAL-001, and it is an automated PlayMode gate; the "
    "contract contains no human gate, so no human approval is claimed. Delivery evidence recorded "
    "by the Game Agent (Integration Steward) on 2026-09-18 at "
    "161982676b2cafbfd48c9aae1eba9d92e9fec55f, which is where Unity actually ran - the tip of the "
    "evidence branch that also carries the NSC-089 and NSC-091 records, and which differs from "
    "canonical main 2559514826e9 only by files under Pipeline/TaskGraph/evidence/. That is not the "
    "historical integration commit: the implementation landed earlier in c5b40974b and 68eb0d0ca "
    "(\"Disable open door NavMesh obstacle for physical traversal\"), and main has moved since. "
    "record_delivery requires HEAD == validated_commit, so binding a historical commit would "
    "produce an evidence commit that could never fast-forward main. This record pays evidence debt "
    "on merged work; it does not claim the work landed today. Noted for the record because the "
    "wording invites a wrong reading: c5b40974b's subject calls the implementation \"provisional\", "
    "but nothing in the committed DoorEnemyPassability.cs or its fixture is marked provisional "
    "today - the file carries full AC-001/AC-002 citations - so the word describes that commit's "
    "moment, not the validated state. Door art, door interaction wiring and per-door obstacle "
    "sizing belong to NSC-051, NSC-097 and the door tasks, and are not claimed."
)

# ---------------------------------------------------------------- NSC-092

NSC092_SURFACES = {
    "Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyPursuitMovement.cs":
        "Runtime component under test: NavMesh pursuit, last-known-position movement, bounded "
        "wander on navigable points, reacquisition, return to idle, and ResetPursuit()",
    "Assets/NoSafeCircle/DoorPrototype/Tests/EnemyPursuitPlayModeTests.cs":
        "First of the two PlayMode fixtures the committed validation policy names; carries VAL-001",
    "Assets/NoSafeCircle/DoorPrototype/Tests/EnemyPursuitDoorCrossingPlayModeTests.cs":
        "Second of the two PlayMode fixtures the committed validation policy names; carries VAL-002",
}

NSC092_ARTIFACTS = [
    {"id": "unity_01_results", "type": "unity_test_results", "name": "Unity-PlayMode-01",
     "source_path": str(ROOT / "NSC-092" / "val-playmode-20260918" / "test-results.xml")},
    {"id": "unity_01_log", "type": "unity_log", "name": "Unity-PlayMode-01",
     "source_path": str(ROOT / "NSC-092" / "val-playmode-20260918" / "unity.log")},
]

NSC092_RUN_PREAMBLE = (
    "Authoritative PlayMode run at the validated commit through run_unity_tests_clean.ps1: "
    "10 tests, 10 passed, 0 failed, 0 skipped, runner exit 0, final line VALIDATION PASSED. "
    "Counts read from test-results.xml, not from the console summary. This task's policy filter "
    "joins TWO types with a semicolon, and the run selected both - the XML's declaring types are "
    "EnemyPursuitPlayModeTests (7 cases) and EnemyPursuitDoorCrossingPlayModeTests (3), which is "
    "the count checked against the [UnityTest] methods declared in each file. A mishandled "
    "semicolon would have produced 7 or 3, not 10. Both are public sealed, non-partial classes. "
    "The bound manifest records commit and post_commit both 161982676b2cafbfd48c9aae1eba9d92e9fec55f "
    "and tree and post_tree both c83562cf735d1d7a4d6828bd880ee0f72c21c8ff, clean before and after. "
    "One run covers both gates of this task; this gate is carried by "
)

NSC092_GATES = {
    "VAL-001": (
        ["unity_01_results", "unity_01_log"],
        NSC092_RUN_PREAMBLE + "EnemyPursuitPlayModeTests, and its 7 cases map onto the six "
        "behaviours the gate names. Pursuit after acquisition: Pursuing_AcquiredTarget_SetsAgent"
        "DestinationTowardTarget_AndAgentMovesCloser. Last-known-position movement after "
        "distance-based target loss: SearchingLastKnownPosition_ReachesRecordedPosition_Reports"
        "Arrival_AndEntersWanderingWithValidNavMeshPoint. Bounded randomized movement on navigable "
        "points: Wandering_AfterReachingChosenPoint_SelectsANewBoundedNavMeshPoint. Reacquisition: "
        "Wandering_WizardReentersDetectionDistance_ReacquiresAndResumesPursuing, and after a reset, "
        "ResetPursuit_ThenWizardReentersDetectionDistance_CanPursueAgain. Return to idle after the "
        "search expires: SearchExpiresWithoutReacquisition_ClearsTargetAndStopsAgentPath. Complete "
        "reset through ResetPursuit(): ResetPursuit_WhilePursuing_ClearsKnowledgeStopsAgentAnd"
        "ReturnsToSpawnPosition. The fixture uses a temporary NavMesh-baked scene and the "
        "production EnemyTargetKnowledge and EnemyPursuitMovement components, as the gate requires."),
    "VAL-002": (
        ["unity_01_results", "unity_01_log"],
        NSC092_RUN_PREAMBLE + "EnemyPursuitDoorCrossingPlayModeTests, whose 3 cases are "
        "SetDoorState_Open_PursuingEnemyCrossesDoorway_WithoutLosingTarget, "
        "SetDoorState_Broken_PursuingEnemyCrossesDoorway_WithoutLosingTarget, and "
        "SetDoorState_Open_SearchingEnemyCrossesDoorwayTowardLastKnownPosition_WithoutLosingTarget. "
        "Together they exercise NSC-089's GameplayNavigationSurface and NSC-090's "
        "DoorEnemyPassability from temporary scene objects, and each asserts the enemy keeps its "
        "target across the crossing rather than clearing it because of the crossing.\n\n"
        "Honest coverage note, so nobody reads more into this gate than it proves: the gate says "
        "\"a pursuing or searching enemy ... through an open or broken doorway\", and the fixture "
        "covers three of the four state/behaviour combinations - pursuing through open, pursuing "
        "through broken, and searching through open. **Searching through a BROKEN doorway has no "
        "case.** Reading the gate as the union of the two pairs, which is how it is written, the "
        "coverage is complete; reading it as the full cross product, one combination is missing. "
        "Nothing here claims the fourth. If that combination matters, it is a contract question "
        "for the GER Agent, not a defect in this record.\n\n"
        "Assets/Scenes/DoorPrototype.unity was not saved or modified: the manifest records the tree "
        "unchanged before and after the run."),
}

NSC092_APPROVAL = (
    "NSC-092 has two completion gates, VAL-001 and VAL-002, and both are automated PlayMode gates; "
    "the contract contains no human gate, so no human approval is claimed. Delivery evidence "
    "recorded by the Game Agent (Integration Steward) on 2026-09-18 at "
    "161982676b2cafbfd48c9aae1eba9d92e9fec55f, which is where Unity actually ran - the tip of the "
    "evidence branch that also carries the NSC-089, NSC-090 and NSC-091 records, and which differs "
    "from canonical main 2559514826e9 only by files under Pipeline/TaskGraph/evidence/. That is not "
    "the historical integration commit: the implementation landed earlier across 4926802b0 "
    "(\"Implement enemy NavMesh pursuit and search movement\"), 10507d66b, e4a84347c and 10dc2204d, "
    "and main has moved since. record_delivery requires HEAD == validated_commit, so binding a "
    "historical commit would produce an evidence commit that could never fast-forward main. This "
    "record pays evidence debt on merged work; it does not claim the work landed today. Melee "
    "close-range attack, ranged keep-distance behaviour, locked-door breach and enemy prefab "
    "wiring belong to NSC-015, NSC-016, NSC-017 and NSC-053, and are not claimed. VAL-002's "
    "searching-through-broken-doorway coverage note is recorded in that gate's own notes."
)

# ---------------------------------------------------------------- driver

PLAN = {
    "NSC-090": (NSC090_SURFACES, NSC090_ARTIFACTS, NSC090_GATES, NSC090_APPROVAL),
    "NSC-092": (NSC092_SURFACES, NSC092_ARTIFACTS, NSC092_GATES, NSC092_APPROVAL),
}

for task_id, (owned, artifacts, gate_plan, approval_notes) in PLAN.items():
    review_path = ROOT / task_id / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))

    offered = {c["path"] for c in review["surface_candidates"]}
    missing = sorted(set(owned) - offered)
    if missing:
        raise SystemExit("%s: owned paths not offered as candidates: %s" % (task_id, missing))

    for candidate in review["surface_candidates"]:
        candidate["selected"] = candidate["path"] in owned
        candidate["role"] = owned.get(candidate["path"], "")

    draft_gate_ids = [g["gate_id"] for g in review["gates"]]
    if draft_gate_ids != sorted(gate_plan):
        raise SystemExit("%s: draft gates %s do not match planned %s"
                         % (task_id, draft_gate_ids, sorted(gate_plan)))
    for gate in review["gates"]:
        evidence, notes = gate_plan[gate["gate_id"]]
        gate["evidence"] = list(evidence)
        gate["notes"] = notes

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
        "gates": [{"gate_id": g["gate_id"], "evidence": g["evidence"], "notes": g["notes"]}
                  for g in review["gates"]],
        "human_approval": {"required": False, "decision": "not_required",
                           "approved_by": "", "notes": approval_notes},
    }
    spec_path = ROOT / task_id / "delivery-spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("%s: %d/%d surfaces, %d artifacts, gates %s -> %s"
          % (task_id, sum(1 for c in review["surface_candidates"] if c["selected"]),
             len(review["surface_candidates"]), len(artifacts),
             [g["gate_id"] for g in spec["gates"]], spec_path))
    for artifact in artifacts:
        print("    %-18s %s %s" % (artifact["id"],
                                   "OK " if pathlib.Path(artifact["source_path"]).is_file() else "MISSING",
                                   artifact["source_path"]))
