# NSC-069 delivery evidence: working notes

Game Agent, 2026-09-17. Contract revision 9, main `70645a036`.
Policy filter (EditMode only): `NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests`.

All five room tasks (NSC-044 through NSC-048) depend on NSC-069 and nothing else, so this record
is what unblocks them. NSC-069's implementation has been on main for some time; only the record is
missing.

## VAL-001 - the Edit Mode fixture

**Done, pending a bound manifest.** Raw batchmode run at `70645a036`: **26 tests, 26 passed, 0
failed**. Every case reports its declaring type as
`NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests` - a partial
class declared across `RoomSceneComposerTests.cs` and `RoomSceneContractTests.cs`.

Must be re-run through `run_unity_tests_clean.ps1` once the runner fix merges, because the
delivery procedure requires that wrapper's bound `validation-manifest.json`, which a raw run does
not produce. Results so far: `C:\nscrev\reports\nav-coverage-probe\nsc069-results.xml`.

## VAL-002 - deterministic identities, catalog records the five paths

**Verified from the committed tree, no Unity needed.**

- `Assets/NoSafeCircle/DoorPrototype/Generated/World/RoomSceneCatalog.asset` and its `.meta` are
  both committed. The meta carries a stable GUID, `e29ec0c6941d9dc489d1560b67557c92`, under
  `NativeFormatImporter` - not a GUID-only stub.
- The catalog records exactly the five stable room scene paths, in order:
  `Assets/Scenes/Rooms/{RuinedEntry,BoneArchive,ChapelOfAsh,LowerVault,FinalRoom}.unity`.
- Per-room asset creation and identity belong to NSC-044 through NSC-048, as the gate says, so
  nothing else is owed here.

## VAL-003 - two consecutive foundation builds are identical

**Outstanding, and the only remaining Unity work besides the VAL-001 re-run.** Needs two
consecutive foundation builds compared semantically - not byte-wise, because every rebuild gives
recreated objects new random fileIDs (see `scene_shape_compare.py` from the NSC-077 pass, and the
door-scene-rebuild memory). Compare generated-root hierarchy, component values, catalog contents
and object counts, and prove no duplicates.

The fixture already proves the composer half: `TryComposeRoom_RunTwice_ReplacesComposedRoomWithout
Duplicating` and `TryComposeRoom_ValidSourceScene_ClonesContentAndClosesSourceWithoutSaving`.

## VAL-004 - single enabled scene, no room-transition scene loads

**Verified, with one honest caveat that must appear in the record.**

- Build-settings exclusion is covered by the fixture's
  `AreRoomScenesExcludedFromBuild_CatalogRoomPaths_AreNotRegisteredInBuildSettings`.
- Production code is **not** free of scene-load calls, and the record must not claim it is. There
  is exactly one, `Scripts/DemoRunFlow.cs:296`:
  `SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex)`, reached only from the "Press
  R to play again" end-screen handler. It reloads the *active* scene by its own build index, which
  is a run restart, not a room transition. The gate's claim - that no room-transition code calls
  scene load/unload APIs - holds; the blanket claim "no production code calls LoadScene" would be
  false.
- Note for whoever writes the record: NSC-007 is currently editing `DemoRunFlow.cs` (AC-011
  removes its embedded fireball). That does not affect this line, but re-check it if NSC-007 lands
  before this evidence does.

## VAL-005 - Vincent's own check

**His, and not delegable.** He opens the exact candidate's `Assets/Scenes/DoorPrototype.unity` and
confirms the prototype is visible, correctly sorted and playable after the global-builder
extraction, with no duplicate Player, camera, UI, door, floor or wall roots. His words get quoted
verbatim into `human_approval.notes` with the date.

## Blocked on

`run_unity_tests_clean.ps1` crashes before producing a manifest: P18 (`576807669`) added an
absolute `Pipeline.` import to `safe_unity_churn.py`, which the wrapper invokes by path, so the
repository root is never on `sys.path`. Fix reviewed and verified at
`fix/unity-whitespace-churn-policy` @ `fde64a97b` (14/14 and 12/12 on Windows), awaiting Vincent's
merge go.
