"""Fill NSC-069's delivery review truthfully. Edits only the fields the procedure allows."""
import io
import json

PATH = r'C:\nscrev\reports\delivery\NSC-069\review.json'

# NSC-069's own exclusive_resources, minus the abstract one, plus their .meta companions.
OWNED = {
    'Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs': 'Foundation builder that creates the visual Tilemaps and the composed-room roots',
    'Assets/NoSafeCircle/DoorPrototype/Editor/World/RoomSceneCatalog.cs': 'Shared catalog type recording the five stable room identities and scene paths',
    'Assets/NoSafeCircle/DoorPrototype/Editor/World/RoomSceneComposer.cs': 'Deterministic Editor-time composition and room-scene validation',
    'Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs': 'Global scene builder the foundation extraction produced',
    'Assets/NoSafeCircle/DoorPrototype/Generated/World/RoomSceneCatalog.asset': 'Generated catalog asset carrying the five stable room scene paths',
    'Assets/NoSafeCircle/DoorPrototype/Scripts/World/RoomAuthoringContract.cs': 'Runtime authoring contract markers the composer validates against',
    'Assets/NoSafeCircle/DoorPrototype/Tests/Editor/World/RoomSceneComposerTests.cs': 'Half of the RoomSceneCompositionFoundationTests partial fixture: composer validation',
    'Assets/NoSafeCircle/DoorPrototype/Tests/Editor/World/RoomSceneContractTests.cs': 'Half of the RoomSceneCompositionFoundationTests partial fixture: catalog and anchor contracts',
    'Assets/Scenes/DoorPrototype.unity': 'The canonical scene the foundation builder materializes and Vincent checked',
}

GATES = {
    'VAL-001': (
        ['unity_01_results', 'unity_01_log'],
        'Authoritative EditMode run at the validated commit through '
        'run_unity_tests_clean.ps1: 26 tests, 26 passed, 0 failed, 0 skipped. The bound manifest '
        'records the same commit 01620a96d and tree e22cebe02 before and after the run, so the run '
        'mutated nothing. Every case in the XML reports its declaring type as '
        'NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests, the '
        'partial class that RoomSceneComposerTests.cs and RoomSceneContractTests.cs each declare '
        'half of, which is what the policy filter names. The fixture covers catalog completeness '
        'and order, root and anchor contracts, source-scene immutability, local-reference '
        'ownership, build-settings exclusion, and composition failure before canonical save. '
        'Sorting is deliberately outside this gate per revision 8.'),
    'VAL-002': (
        ['unity_01_results'],
        'Verified from the committed tree at the validated commit. '
        'Assets/NoSafeCircle/DoorPrototype/Generated/World/RoomSceneCatalog.asset and its .meta are '
        'both committed, and the meta carries a stable GUID e29ec0c6941d9dc489d1560b67557c92 under '
        'NativeFormatImporter rather than a GUID-only stub. The catalog records exactly the five '
        'stable room scene paths in fixed order: RuinedEntry, BoneArchive, ChapelOfAsh, LowerVault, '
        'FinalRoom under Assets/Scenes/Rooms/. The fixture asserts the order and the distinct '
        'stable paths (CanonicalRooms_MatchFixedFiveRoomOrder, '
        'CanonicalRooms_RecordDistinctStableScenePaths). Per-room asset creation and identity '
        'belong to NSC-044 through NSC-048, which this gate defers to.'),
    'VAL-003': (
        ['unity_01_results'],
        'Two consecutive foundation builds were run at the validated commit and compared '
        'semantically, because a rebuild is never byte-identical: recreated objects receive fresh '
        'random fileIDs. Both builds produced 1261 objects across 66 distinct (class, script) keys '
        'with no count differences and no size differences, and a component/value snapshot of the '
        'generated-root hierarchy after each build was identical. No duplicates appeared. The '
        'checkout was restored afterwards and reported 0 changes. The fixture proves the '
        'composer-level half separately: TryComposeRoom_RunTwice_ReplacesComposedRoomWithout'
        'Duplicating and TryComposeRoom_ValidSourceScene_ClonesContentAndClosesSourceWithoutSaving.'),
    'VAL-004': (
        ['unity_01_results'],
        'Build-settings exclusion is proven by the fixture: '
        'AreRoomScenesExcludedFromBuild_CatalogRoomPaths_AreNotRegisteredInBuildSettings. On scene '
        'load/unload APIs the honest statement is narrower than "none exist": production code '
        'contains exactly one call, Scripts/DemoRunFlow.cs:296, '
        'SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex), reachable only from the '
        '"Press R to play again" end-screen handler. It reloads the active scene by its own build '
        'index, which is a run restart, not a room transition, so the gate\'s requirement - that no '
        'room-transition code calls scene load/unload APIs - holds. Playability is covered by '
        'VAL-005. Final content composition remains deferred to NSC-049.'),
    'VAL-005': (
        ['unity_01_results'],
        'Vincent opened Assets/Scenes/DoorPrototype.unity in the editor on canonical at HEAD '
        '01620a96d, the exact validated commit, confirmed unmoved before and after he looked, and '
        'said: "The game looks fine." He was in Play mode with the HUD and the health and mana bars '
        'live. The Hierarchy in his screenshot showed exactly one each of Player, Main Camera, '
        'Canvas, DoorRoot, EventSystem, World and GameplayNavigation, with no duplicate roots; '
        'floor and wall content sits under the single World root. Reported by the GER Agent, who '
        'launched the editor for him; his quoted words are his own.'),
}

APPROVAL_NOTES = (
    'Vincent Liguori, 2026-09-17, with Assets/Scenes/DoorPrototype.unity open in the editor on '
    'canonical at HEAD 01620a96d - the exact validated commit, confirmed unmoved before he looked '
    'and still unmoved when the record was written. His words: "The game looks fine." He was in '
    'Play mode with the HUD and the health and mana bars live. His Hierarchy showed exactly one '
    'each of Player, Main Camera, Canvas, DoorRoot, EventSystem, World and GameplayNavigation, so '
    'no duplicate Player, camera, UI, door, floor or wall roots exist. The editor was launched for '
    'him by the GER Agent; the quoted words are his own.'
)

data = json.load(io.open(PATH, encoding='utf-8'))

data['review_status'] = 'approved'

selected = 0
for surface in data['surface_candidates']:
    role = OWNED.get(surface['path'])
    if role:
        surface['selected'] = True
        surface['role'] = role
        selected += 1
    else:
        surface['selected'] = False
        surface['role'] = ''

for gate in data['gates']:
    evidence, notes = GATES[gate['gate_id']]
    gate['evidence'] = list(evidence)
    gate['notes'] = notes
    gate['result'] = 'pass'

data['human_approval']['decision'] = 'approved'
data['human_approval']['approved_by'] = 'Vincent Liguori'
data['human_approval']['notes'] = APPROVAL_NOTES

io.open(PATH, 'w', encoding='utf-8').write(json.dumps(data, indent=2) + '\n')
print('selected surfaces: %d of %d' % (selected, len(data['surface_candidates'])))
print('gates filled     : %s' % ', '.join(g['gate_id'] for g in data['gates']))
missing = [p for p in OWNED if p not in {s['path'] for s in data['surface_candidates']}]
print('owned paths not offered as candidates: %s' % (missing or 'none'))
