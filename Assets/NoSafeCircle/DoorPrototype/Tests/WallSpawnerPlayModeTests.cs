using System.Collections;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    // Falsifies WallSpawner at Play, with NO bake and no scene mutation, against expectations that
    // come from somewhere OTHER than the thing under test:
    //
    //   - which slots hold a wall: a lattice walk along each LAYOUT edge that probes the map cell
    //     half a unit inside the line. It never looks at a neighbour, so it shares no logic with
    //     the 3x3 classification in WallPiecePass; if the two disagree, one of them is wrong.
    //   - which room owns a shared line: the same north-first rule, re-derived here from the
    //     layouts' own Z bounds.
    //   - where the posts and jambs sit: the committed room scenes' arithmetic, re-expressed in
    //     closed form from the layouts and the imported sprites' bounds (corner at x-min + half
    //     width, y = the sprite's transparent bottom margin), which the spawner reaches through the
    //     ported CreateAccent form instead.
    //   - the colliders: the layout constants, and NSC-048's relation that exactly one 2.5-unit
    //     collider stands along every part of a shared boundary outside its 3.0-unit gap.
    //
    // 444 IS NOT WRITTEN HERE, AND NEITHER IS 442. Fable's addendum names 444 as a check value for
    // a map with the Final Room at +/-16; the correction kept it at +/-15, which is 442. A frozen
    // literal would pass while the map said something else, which is this workspace's own named
    // failure, so every count below is recomputed from the map and the layouts on each run.
#if UNITY_EDITOR
    public sealed class WallSpawnerPlayModeTests
    {
        private const string SpawnerResourcePath = "Spawners/WallSpawner";
        private const string MapAssetPath = "Assets/NoSafeCircle/DoorPrototype/Content/Levels/floor01.txt";
        private const string EnvironmentFolder = "Assets/NoSafeCircle/DoorPrototype/Content/Environment/";

        // The declared grid of floor01.txt, exactly as Floor01AsciiMapTests declares it. The
        // parser insists the caller declares the grid; this fixture declares it independently of
        // the spawner's own derivation from the rooms.
        private const int Columns = 20;
        private const int Rows = 65;
        private const float OriginX = -20f;
        private const float OriginZ = 104f;

        // Sprite names as imported from Art/Environment/Source/walls. Pieces are identified by the
        // sprite their renderer carries, not by the name the spawner gave the object.
        private const string StraightSprite = "wall_straight";
        private const string StubSprite = "wall_broken_stub";
        private const string PilasterSprite = "wall_pilaster";
        private const string CornerSprite = "wall_corner";
        private const string JambSprite = "wall_door_jamb";
        private const string EndCapSprite = "wall_end_cap";

        // WallVisualOffset. Carried from every committed builder, never re-derived: the one number
        // the addendum says to carry, so it is the one literal this fixture keeps.
        private const float CarriedVisualInset = 0.151f;

        private GameObject spawnerObject;

        [TearDown]
        public void TearDown()
        {
            if (spawnerObject != null)
            {
                Object.Destroy(spawnerObject);
                spawnerObject = null;
            }
        }

        // ------------------------------------------------------------------------------------
        // The oracle: rooms from the LAYOUTS, slots from a lattice walk, colliders from constants.
        // ------------------------------------------------------------------------------------

        private sealed class Room
        {
            public string Name;
            public float XMin, XMax, ZMin, ZMax, DoorWidth, Thickness, Height;
            public Vector3[] Doors;

            public float Line(WallEdge edge) =>
                edge == WallEdge.North ? ZMax : edge == WallEdge.South ? ZMin : edge == WallEdge.West ? XMin : XMax;

            public WallEdge EdgeOf(Vector3 door) =>
                Mathf.Approximately(door.z, ZMax) ? WallEdge.North
                : Mathf.Approximately(door.z, ZMin) ? WallEdge.South
                : Mathf.Approximately(door.x, XMin) ? WallEdge.West : WallEdge.East;

            public Vector3 Center => new Vector3((XMin + XMax) * 0.5f, 0f, (ZMin + ZMax) * 0.5f);
        }

        // Built from the five *Layout.cs files directly, so a layout edit moves the expectation
        // and a WallRoom table edit does not. Northernmost first, by each room's own ZMax.
        private static List<Room> LayoutRooms()
        {
            var rooms = new List<Room>
            {
                new Room
                {
                    Name = "FinalRoom",
                    XMin = FinalRoomLayout.MinimumX, XMax = FinalRoomLayout.MaximumX,
                    ZMin = FinalRoomLayout.MinimumZ, ZMax = FinalRoomLayout.MaximumZ,
                    DoorWidth = FinalRoomLayout.DoorOpeningWidth, Thickness = FinalRoomLayout.WallThickness,
                    Height = FinalRoomLayout.GameplayWallColliderHeight,
                    Doors = new[]
                    {
                        new Vector3(FinalRoomLayout.D4X, 0f, FinalRoomLayout.D4Z),
                        new Vector3(FinalRoomLayout.D5X, 0f, FinalRoomLayout.D5Z)
                    }
                },
                new Room
                {
                    Name = "LowerVault",
                    XMin = LowerVaultLayout.MinimumX, XMax = LowerVaultLayout.MaximumX,
                    ZMin = LowerVaultLayout.MinimumZ, ZMax = LowerVaultLayout.MaximumZ,
                    DoorWidth = LowerVaultLayout.DoorWidth, Thickness = LowerVaultLayout.WallThickness,
                    Height = LowerVaultLayout.WallHeight,
                    Doors = new[] { LowerVaultLayout.D3, LowerVaultLayout.D4 }
                },
                new Room
                {
                    Name = "ChapelOfAsh",
                    XMin = ChapelOfAshLayout.MinimumX, XMax = ChapelOfAshLayout.MaximumX,
                    ZMin = ChapelOfAshLayout.MinimumZ, ZMax = ChapelOfAshLayout.MaximumZ,
                    DoorWidth = ChapelOfAshLayout.DoorWidth, Thickness = ChapelOfAshLayout.WallThickness,
                    Height = ChapelOfAshLayout.WallHeight,
                    Doors = new[] { ChapelOfAshLayout.D2, ChapelOfAshLayout.D3 }
                },
                new Room
                {
                    Name = "BoneArchive",
                    XMin = BoneArchiveLayout.RoomBounds.min.x, XMax = BoneArchiveLayout.RoomBounds.max.x,
                    ZMin = BoneArchiveLayout.RoomBounds.min.z, ZMax = BoneArchiveLayout.RoomBounds.max.z,
                    DoorWidth = BoneArchiveLayout.DoorWidth, Thickness = BoneArchiveLayout.WallThickness,
                    Height = BoneArchiveLayout.WallHeight,
                    Doors = new[] { BoneArchiveLayout.D1, BoneArchiveLayout.D2 }
                },
                new Room
                {
                    Name = "RuinedEntry",
                    XMin = RuinedEntryLayout.MinimumX, XMax = RuinedEntryLayout.MaximumX,
                    ZMin = RuinedEntryLayout.MinimumZ, ZMax = RuinedEntryLayout.MaximumZ,
                    DoorWidth = RuinedEntryLayout.DoorOpeningWidth, Thickness = RuinedEntryLayout.WallThickness,
                    Height = RuinedEntryLayout.WallHeight,
                    Doors = new[] { new Vector3(RuinedEntryLayout.DoorCenterX, 0f, RuinedEntryLayout.DoorCenterZ) }
                }
            };

            return rooms.OrderByDescending(r => r.ZMax).ToList();
        }

        private static readonly WallEdge[] Edges = { WallEdge.North, WallEdge.South, WallEdge.West, WallEdge.East };

        private static bool AlongX(WallEdge edge) => edge == WallEdge.North || edge == WallEdge.South;

        private static AsciiRoomMap LoadMap()
        {
            var asset = UnityEditor.AssetDatabase.LoadAssetAtPath<TextAsset>(MapAssetPath);
            Assert.IsNotNull(asset, MapAssetPath + " did not import as a TextAsset.");
            Assert.IsTrue(AsciiRoomMap.TryParse(asset.text, Columns, Rows, out AsciiRoomMap map, out string error),
                "floor01.txt did not parse as " + Columns + "x" + Rows + ": " + error);
            Assert.Greater(map.WalkableCellCount(), 0, "The map has no walkable cells, so every count here is vacuous.");
            return map;
        }

        private readonly struct Slot
        {
            public readonly Room Room;
            public readonly WallEdge Edge;
            public readonly float Start;

            public Slot(Room room, WallEdge edge, float start)
            {
                Room = room;
                Edge = edge;
                Start = start;
            }

            public float Line => Room.Line(Edge);

            /// The lattice point a base piece's root must stand on: the slot centre, on the line.
            public Vector3 RootPoint => AlongX(Edge)
                ? new Vector3(Start + 0.5f, 0f, Line)
                : new Vector3(Line, 0f, Start + 0.5f);
        }

        // THE LATTICE WALK. For each room (north first), each layout edge and each one-unit slot
        // along it, the slot holds a wall iff the map cell HALF A UNIT INSIDE the line at the slot
        // centre is a wall cell. Half a unit, not one: the Final Room's line sits one unit inside
        // its band cells' outer edge, and a probe a full unit in would land on the floor.
        private static List<Slot> ExpectedSlots(AsciiRoomMap map, List<Room> rooms)
        {
            var occupied = new HashSet<(int, int, int)>();
            var slots = new List<Slot>();
            foreach (Room room in rooms)
            {
                foreach (WallEdge edge in Edges)
                {
                    bool alongX = AlongX(edge);
                    float line = room.Line(edge);
                    float min = alongX ? room.XMin : room.ZMin;
                    float max = alongX ? room.XMax : room.ZMax;
                    float inward = edge == WallEdge.North || edge == WallEdge.East ? -0.5f : 0.5f;

                    for (float start = min; start + 1f <= max + 0.0001f; start += 1f)
                    {
                        float along = start + 0.5f;
                        float probeX = alongX ? along : line + inward;
                        float probeZ = alongX ? line + inward : along;
                        AsciiCellIndex cell = map.ToCell(probeX, probeZ, OriginX, OriginZ);
                        if (map[cell.Column, cell.Row] != AsciiCell.Wall) continue;
                        if (!occupied.Add((alongX ? 0 : 1, Mathf.RoundToInt(line), Mathf.RoundToInt(start)))) continue;
                        slots.Add(new Slot(room, edge, start));
                    }
                }
            }

            Assert.Greater(slots.Count, 0, "The lattice walk found no wall slots, so every assertion is vacuous.");
            return slots;
        }

        // NSC-127 AC-001's rhythm, re-derived: every fourth slot of a layout run (corner to door
        // collider edge), never the run's first or last slot, on far (straight) sides only.
        private static bool IsPilasterSlot(Slot slot)
        {
            if (slot.Edge != WallEdge.North && slot.Edge != WallEdge.West) return false;
            bool alongX = AlongX(slot.Edge);
            float runStart = alongX ? slot.Room.XMin : slot.Room.ZMin;
            float runLast = (alongX ? slot.Room.XMax : slot.Room.ZMax) - 1f;
            foreach (Vector3 door in slot.Room.Doors)
            {
                if (slot.Room.EdgeOf(door) != slot.Edge) continue;
                float centre = alongX ? door.x : door.z;
                float half = slot.Room.DoorWidth * 0.5f;
                if (slot.Start > centre) runStart = Mathf.Max(runStart, Mathf.Ceil(centre + half));
                else runLast = Mathf.Min(runLast, Mathf.Floor(centre - half) - 1f);
            }

            int index = Mathf.RoundToInt(slot.Start - runStart);
            return index % 4 == 0 && slot.Start > runStart && slot.Start < runLast;
        }

        private static (int, int) Key(Vector3 point) =>
            (Mathf.RoundToInt(point.x * 4f), Mathf.RoundToInt(point.z * 4f));

        private static Sprite AuthoredSprite(string prefabName)
        {
            var prefab = UnityEditor.AssetDatabase.LoadAssetAtPath<GameObject>(EnvironmentFolder + prefabName + ".prefab");
            Assert.IsNotNull(prefab, EnvironmentFolder + prefabName + ".prefab is missing.");
            var renderer = prefab.GetComponentInChildren<SpriteRenderer>(true);
            Assert.IsNotNull(renderer, prefabName + " carries no SpriteRenderer.");
            Assert.IsNotNull(renderer.sprite, prefabName + "'s SpriteRenderer has no sprite.");
            return renderer.sprite;
        }

        private WallSpawner CreateSpawner()
        {
            var prefab = Resources.Load<GameObject>(SpawnerResourcePath);
            Assert.IsNotNull(prefab, "No prefab at Resources/" + SpawnerResourcePath
                + ", so GameBootstrap would never find the walls lane.");
            spawnerObject = Object.Instantiate(prefab);
            spawnerObject.name = "WallSpawnerUnderTest";
            var spawner = spawnerObject.GetComponent<WallSpawner>();
            Assert.IsNotNull(spawner, "The Resources/" + SpawnerResourcePath + " prefab carries no WallSpawner.");
            return spawner;
        }

        private IEnumerable<SpriteRenderer> RenderersWithSprite(string spriteName) =>
            spawnerObject.GetComponentsInChildren<SpriteRenderer>(true)
                .Where(r => r.sprite != null && r.sprite.name == spriteName);

        private IEnumerable<SpriteRenderer> BasePieceRenderers() =>
            RenderersWithSprite(StraightSprite).Concat(RenderersWithSprite(StubSprite)).Concat(RenderersWithSprite(PilasterSprite));

        // ------------------------------------------------------------------------------------
        // Tests
        // ------------------------------------------------------------------------------------

        [UnityTest]
        public IEnumerator ThePrefabDoesNotSpawnOnAwake()
        {
            WallSpawner spawner = CreateSpawner();
            yield return null;

            Assert.AreEqual(-1, spawner.SpawnedCount,
                "Instantiating the spawner prefab spawned walls. GameBootstrap owns the build order; "
                + "a spawner that starts itself runs out of phase for every other lane.");
            Assert.AreEqual(0, spawnerObject.GetComponentsInChildren<SpriteRenderer>(true).Length);
        }

        [UnityTest]
        public IEnumerator Spawn_FillsExactlyTheWallSlotsTheMapAndLayoutsDefine()
        {
            WallSpawner spawner = CreateSpawner();
            List<Room> rooms = LayoutRooms();
            List<Slot> expected = ExpectedSlots(LoadMap(), rooms);

            spawner.Spawn();
            yield return null;

            // Every base piece's ROOT must stand on a lattice point, and every expected lattice
            // point must hold exactly one. Both directions: no missing slot, no extra piece.
            var byPoint = new Dictionary<(int, int), int>();
            foreach (SpriteRenderer renderer in BasePieceRenderers())
            {
                Transform root = renderer.transform.parent;
                Assert.IsNotNull(root, renderer.gameObject.name + " is a bare renderer; every base piece is a root with a Visual child.");
                (int, int) key = Key(root.position);
                byPoint[key] = byPoint.TryGetValue(key, out int n) ? n + 1 : 1;
            }

            var missing = new List<string>();
            foreach (Slot slot in expected)
            {
                if (!byPoint.TryGetValue(Key(slot.RootPoint), out int n) || n != 1)
                {
                    missing.Add(slot.Room.Name + " " + slot.Edge + " slot " + slot.Start + " holds " + n + " piece(s)");
                }
            }

            Assert.IsEmpty(missing, "Slots not filled exactly once:\n" + string.Join("\n", missing));
            Assert.AreEqual(expected.Count, byPoint.Values.Sum(),
                "The spawner placed " + byPoint.Values.Sum() + " base pieces for " + expected.Count
                + " wall slots. A surplus means a piece stands where the lattice walk found no wall - "
                + "an unclipped Final Room slot, a duplicate on a shared line, or a phantom edge.");
        }

        [UnityTest]
        public IEnumerator FarSidesAreStraightOrPilasterAndNearSidesAreStubs()
        {
            WallSpawner spawner = CreateSpawner();
            List<Slot> expected = ExpectedSlots(LoadMap(), LayoutRooms());

            spawner.Spawn();
            yield return null;

            var spriteAt = BasePieceRenderers().ToDictionary(r => Key(r.transform.parent.position), r => r.sprite.name);
            var wrong = new List<string>();
            foreach (Slot slot in expected)
            {
                string actual = spriteAt[Key(slot.RootPoint)];
                bool far = slot.Edge == WallEdge.North || slot.Edge == WallEdge.West;
                string want = !far ? StubSprite : IsPilasterSlot(slot) ? PilasterSprite : StraightSprite;
                if (actual != want)
                {
                    wrong.Add(slot.Room.Name + " " + slot.Edge + " slot " + slot.Start + ": " + actual + " should be " + want);
                }
            }

            Assert.IsEmpty(wrong, "Wrong sprite for side (north/west are the far 2.5u straight, "
                + "south/east are Vincent's 2.797u broken stub; there is no WallLow):\n" + string.Join("\n", wrong));

            // Non-vacuous: NSC-127's rhythm must actually place something on a 28-slot run.
            Assert.Greater(RenderersWithSprite(PilasterSprite).Count(), 0,
                "No pilaster was placed at all, so the rhythm check above passed on nothing.");
        }

        [UnityTest]
        public IEnumerator EveryWallRendererCarriesTheSortingConvention()
        {
            WallSpawner spawner = CreateSpawner();
            spawner.Spawn();
            yield return null;

            SpriteRenderer[] renderers = spawnerObject.GetComponentsInChildren<SpriteRenderer>(true);
            Assert.Greater(renderers.Length, 0, "Nothing spawned, so this passes vacuously.");

            foreach (SpriteRenderer renderer in renderers)
            {
                string who = renderer.transform.parent != null ? renderer.transform.parent.name : renderer.name;
                Assert.IsNotNull(renderer.sprite, who + " has a null sprite after Instantiate.");
                Assert.AreEqual(WorldSpriteConvention.SortingLayerName, renderer.sortingLayerName,
                    who + " is on sorting layer '" + renderer.sortingLayerName + "'; the LAYER is compared before the order.");
                Assert.AreEqual(WorldSpriteConvention.SortingOrder, renderer.sortingOrder,
                    who + " carries sortingOrder " + renderer.sortingOrder + "; any other value outranks position unconditionally.");
                Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint,
                    who + " sorts by Center rather than Pivot, which reads the sprite's middle instead of its ground contact.");
                Assert.AreEqual(Vector3.one, renderer.transform.lossyScale, who + " is scaled. Wall sprites are never scaled.");
            }
        }

        [UnityTest]
        public IEnumerator BasePiecesStandOnTheirLineAndInsetTheVisualTowardTheRoom()
        {
            WallSpawner spawner = CreateSpawner();
            List<Slot> expected = ExpectedSlots(LoadMap(), LayoutRooms());

            // The inset is the PREFAB's number. Read from the authored artifact, then held to the
            // carried value so nobody re-derives it.
            var straightPrefab = UnityEditor.AssetDatabase.LoadAssetAtPath<GameObject>(EnvironmentFolder + "WallStraight.prefab");
            Assert.IsNotNull(straightPrefab, EnvironmentFolder + "WallStraight.prefab is missing.");
            Transform authoredVisual = straightPrefab.transform.Find(WallSpawner.VisualChildName);
            Assert.IsNotNull(authoredVisual, "WallStraight.prefab has no '" + WallSpawner.VisualChildName + "' child.");
            float inset = Mathf.Abs(authoredVisual.localPosition.z);
            Assert.AreEqual(CarriedVisualInset, inset, 0.0001f,
                "The authored inset is " + inset + ", not the carried WallVisualOffset 0.151.");

            spawner.Spawn();
            yield return null;

            var byPoint = BasePieceRenderers().ToDictionary(r => Key(r.transform.parent.position), r => r);
            foreach (Slot slot in expected)
            {
                SpriteRenderer renderer = byPoint[Key(slot.RootPoint)];
                Transform root = renderer.transform.parent;
                string who = slot.Room.Name + " " + slot.Edge + " slot " + slot.Start;

                Assert.AreEqual(0f, root.position.y, 0.0001f, who + ": root y must be 0; the pivot is on the drawn base.");
                float yaw = root.rotation.eulerAngles.y;
                Assert.AreEqual(AlongX(slot.Edge) ? 0f : 90f, yaw, 0.01f, who + ": yaw " + yaw);

                // The Visual child sits 'inset' from the root, toward the room's centre, and
                // nowhere else: zero along the line and zero vertically.
                Vector3 offset = renderer.transform.position - root.position;
                Vector3 toward = (slot.Room.Center - slot.RootPoint);
                float perpendicular = AlongX(slot.Edge) ? offset.z : offset.x;
                float alongLine = AlongX(slot.Edge) ? offset.x : offset.z;
                float towardRoom = AlongX(slot.Edge) ? Mathf.Sign(toward.z) : Mathf.Sign(toward.x);
                Assert.AreEqual(inset * towardRoom, perpendicular, 0.0001f,
                    who + ": the Visual is " + perpendicular + " off the line; expected " + (inset * towardRoom) + " toward the room.");
                Assert.AreEqual(0f, alongLine, 0.0001f, who + ": the Visual slid along the line.");
                Assert.AreEqual(0f, offset.y, 0.0001f, who + ": the Visual is lifted.");
            }
        }

        [UnityTest]
        public IEnumerator CornerPostsAndJambsReproduceTheApprovedPlacerArithmetic()
        {
            WallSpawner spawner = CreateSpawner();
            List<Room> rooms = LayoutRooms();
            Bounds corner = AuthoredSprite("WallCorner").bounds;
            Bounds jamb = AuthoredSprite("WallDoorJamb").bounds;

            spawner.Spawn();
            yield return null;

            // Posts: one per distinct layout corner, anchored so the sprite's outer edge is AT the
            // corner and its bounds bottom on the floor - (xMin + halfWidth, -min.y, zMax) - which
            // is what the committed FinalRoom.unity holds at (+/-14, 0.25, 76|104).
            var expectedPosts = new HashSet<(int, int)>();
            var expectedPostPositions = new List<Vector3>();
            foreach (Room room in rooms)
            {
                foreach (float z in new[] { room.ZMax, room.ZMin })
                {
                    foreach ((float x, float sign) in new[] { (room.XMin, 1f), (room.XMax, -1f) })
                    {
                        if (!expectedPosts.Add((Mathf.RoundToInt(x), Mathf.RoundToInt(z)))) continue;
                        expectedPostPositions.Add(new Vector3(x + sign * corner.extents.x, -corner.min.y, z));
                    }
                }
            }

            List<Transform> posts = RenderersWithSprite(CornerSprite).Select(r => r.transform.parent).ToList();
            Assert.AreEqual(expectedPostPositions.Count, posts.Count,
                "Expected " + expectedPostPositions.Count + " corner posts (four per room, deduplicated by point); got " + posts.Count + ".");
            foreach (Vector3 want in expectedPostPositions)
            {
                Assert.IsTrue(posts.Any(p => (p.position - want).magnitude < 0.001f && p.rotation.eulerAngles.y < 0.01f),
                    "No corner post at " + want + " with yaw 0. Posts found: "
                    + string.Join(", ", posts.Select(p => p.position.ToString("0.###"))));
            }

            // Jambs: one pair per distinct door, each anchored at the collider gap edge
            // (centre +/- 1.5) and extending into its run: (centre -/+ (1.5 + halfWidth), -min.y, z).
            var expectedDoors = new HashSet<(int, int)>();
            var expectedJambPositions = new List<Vector3>();
            foreach (Room room in rooms)
            {
                foreach (Vector3 door in room.Doors)
                {
                    if (!expectedDoors.Add((Mathf.RoundToInt(door.x * 2f), Mathf.RoundToInt(door.z * 2f)))) continue;
                    Assert.IsTrue(AlongX(room.EdgeOf(door)), "floor01's doors all cut north/south lines; extend this oracle if that changes.");
                    float reach = room.DoorWidth * 0.5f + jamb.extents.x;
                    expectedJambPositions.Add(new Vector3(door.x - reach, -jamb.min.y, door.z));
                    expectedJambPositions.Add(new Vector3(door.x + reach, -jamb.min.y, door.z));
                }
            }

            List<SpriteRenderer> jambs = RenderersWithSprite(JambSprite).ToList();
            Assert.AreEqual(expectedJambPositions.Count, jambs.Count,
                "Expected " + expectedJambPositions.Count + " jambs (two per distinct door); got " + jambs.Count
                + ". Today's composed scene draws 18 at these 10 points; the pass draws each once.");
            foreach (Vector3 want in expectedJambPositions)
            {
                Assert.IsTrue(jambs.Any(j => (j.transform.parent.position - want).magnitude < 0.001f),
                    "No jamb at " + want + ". Jambs found: "
                    + string.Join(", ", jambs.Select(j => j.transform.parent.position.ToString("0.###"))));
            }

            foreach (SpriteRenderer j in jambs)
            {
                // Measured in all five committed room scenes: every one of the 18 jamb renderers has
                // m_FlipX 0. The addendum's "flipX on the east side as the placer does" describes a
                // placer that does not exist; a mirrored east jamb is an Art Director decision to
                // make deliberately, and this line is where it would be made.
                Assert.IsFalse(j.flipX, "A jamb is mirrored; the approved placer never set flipX.");
            }

            Assert.AreEqual(0, RenderersWithSprite(EndCapSprite).Count(),
                "floor01's rings leave no free run end, so no end cap should be placed.");
        }

        [UnityTest]
        public IEnumerator RunCollidersMatchTheLayoutsAndCoverEachSharedLineExactlyOnce()
        {
            WallSpawner spawner = CreateSpawner();
            List<Room> rooms = LayoutRooms();

            spawner.Spawn();
            yield return null;
            Physics.SyncTransforms();

            BoxCollider[] boxes = spawnerObject.GetComponentsInChildren<BoxCollider>(true);
            Assert.Greater(boxes.Length, 0, "No wall collider was spawned, so walls block nothing.");

            // Every box is a layout box: on one of its room's four lines, that room's thickness and
            // height, centred at half height, never a trigger. The room is the parent's name.
            foreach (BoxCollider box in boxes)
            {
                string roomName = box.transform.parent.name.Replace("Walls", "");
                Room room = rooms.Single(r => r.Name == roomName);
                Vector3 c = box.transform.position;
                bool onNorthSouth = Mathf.Approximately(c.z, room.ZMax) || Mathf.Approximately(c.z, room.ZMin);
                bool onWestEast = Mathf.Approximately(c.x, room.XMin) || Mathf.Approximately(c.x, room.XMax);
                Assert.IsTrue(onNorthSouth || onWestEast, box.name + " at " + c + " is on no line of " + roomName + ".");
                Assert.IsFalse(box.isTrigger, box.name + " is a trigger and stops nothing.");
                Assert.AreEqual(room.Height, box.size.y, 0.001f, box.name + " height");
                Assert.AreEqual(room.Height * 0.5f, c.y, 0.001f, box.name + " centre y");
                Assert.AreEqual(room.Thickness, onNorthSouth ? box.size.z : box.size.x, 0.001f, box.name + " thickness");
                Assert.AreEqual(Vector3.zero, box.center, box.name + " has an offset centre; the layouts centre every box on its object.");
            }

            // The contract-named pieces exist under each room: split names beside a door, the
            // whole-side name otherwise. NSC-048 AC-004 asserts SouthWallWestCollision by name.
            //
            // ONLY ON LINES THE ROOM OWNS FIRST. A line an earlier (more northern) room also has an
            // edge on is a shared line; the northern room's boxes are never clipped and keep their
            // names, while the southern room's are clipped to the jogs or away entirely - the
            // Chapel's north boxes lie wholly inside the Lower Vault's south boxes and do not exist.
            // The coverage relation below is what the southern room's geometry must satisfy.
            for (int i = 0; i < rooms.Count; i++)
            {
                Room room = rooms[i];
                Transform roomRoot = spawnerObject.transform.Find(room.Name + "Walls");
                Assert.IsNotNull(roomRoot, "No '" + room.Name + "Walls' root.");
                foreach (WallEdge edge in Edges)
                {
                    bool sharedWithNorthernRoom = rooms.Take(i).Any(northern => Edges.Any(e =>
                        AlongX(e) == AlongX(edge) && Mathf.Approximately(northern.Line(e), room.Line(edge))));
                    if (sharedWithNorthernRoom) continue;

                    bool doored = room.Doors.Any(d => room.EdgeOf(d) == edge);
                    string[] names = doored
                        ? new[] { edge + "WallWestCollision", edge + "WallEastCollision" }
                        : new[] { edge + "WallCollision" };
                    foreach (string name in names)
                    {
                        Assert.IsNotNull(roomRoot.Find(name), room.Name + " has no '" + name + "'. A room's boxes on a "
                            + "line it owns first are never clipped, so the contract-named object must exist.");
                    }
                }
            }

            // NSC-048's relation, sampled: along every edge of every room, outside the 3.0 gap,
            // EXACTLY ONE collider RUNNING ALONG THAT LINE covers each point - one on a perimeter
            // wall, and one (not two, not zero) on a shared line - while the gap itself is clear.
            // Perpendicular boxes are excluded on purpose: a room's north and west boxes overlap
            // in a 0.5 x 0.5 square at the corner, which is the builders' own geometry and is not
            // a doubled wall. Samples sit at k + 1/8 so none lands on a box edge, where Contains
            // would count two abutting boxes.
            var failures = new List<string>();
            foreach (Room room in rooms)
            {
                foreach (WallEdge edge in Edges)
                {
                    bool alongX = AlongX(edge);
                    float line = room.Line(edge);
                    float min = alongX ? room.XMin : room.ZMin;
                    float max = alongX ? room.XMax : room.ZMax;
                    List<float> gaps = room.Doors.Where(d => room.EdgeOf(d) == edge).Select(d => alongX ? d.x : d.z).ToList();
                    List<BoxCollider> onLine = boxes.Where(b => alongX
                        ? b.size.x >= b.size.z && Mathf.Approximately(b.transform.position.z, line)
                        : b.size.z >= b.size.x && Mathf.Approximately(b.transform.position.x, line)).ToList();

                    for (float t = min + 0.125f; t < max; t += 0.25f)
                    {
                        bool inGap = gaps.Any(g => Mathf.Abs(t - g) < room.DoorWidth * 0.5f);
                        Vector3 point = alongX ? new Vector3(t, room.Height * 0.5f, line) : new Vector3(line, room.Height * 0.5f, t);
                        int covering = onLine.Count(b => b.bounds.Contains(point));
                        int want = inGap ? 0 : 1;
                        if (covering != want)
                        {
                            failures.Add(room.Name + " " + edge + " at " + t + ": " + covering + " collider(s), expected " + want);
                        }
                    }
                }
            }

            Assert.IsEmpty(failures, "Wall coverage is not exactly-once:\n" + string.Join("\n", failures));

            // THE REAL PROOF: a chest-height ray, triggers ignored - FireballProjectile's shape -
            // fired at an unshared wall is stopped by a spawned wall collider.
            Room entry = rooms.Single(r => r.Name == "RuinedEntry");
            Vector3 origin = new Vector3(entry.Center.x, 1f, entry.ZMin + 6f);
            bool hit = Physics.Raycast(origin, Vector3.back, out RaycastHit info, 12f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
            Assert.IsTrue(hit, "A chest-height ray at the Ruined Entry's south wall hit nothing.");
            Assert.Contains(info.collider, boxes, "The ray was stopped by '" + info.collider.name + "', which is not a spawned wall.");
            Assert.AreEqual("SouthWallCollision", info.collider.name);
        }

        [UnityTest]
        public IEnumerator SpawningTwiceDoesNotDoubleTheWalls()
        {
            WallSpawner spawner = CreateSpawner();

            int first = spawner.Spawn();
            yield return null;
            int second = spawner.Spawn();
            yield return null;

            Assert.AreEqual(first, second, "A second Spawn() returned a different count.");
            int renderers = spawnerObject.GetComponentsInChildren<SpriteRenderer>(true).Length;
            int boxes = spawnerObject.GetComponentsInChildren<BoxCollider>(true).Length;
            Assert.AreEqual(first, renderers + boxes,
                "After two Spawn() calls the hierarchy holds " + (renderers + boxes) + " objects rather than "
                + first + ". Doubled walls read as a placement bug rather than a lifecycle bug, which is why Spawn() clears first.");
        }
    }
#endif
}
