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
    //   - where the posts and shoulders sit: the committed room scenes' arithmetic, re-expressed in
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

        private readonly struct Shoulder
        {
            public readonly Room Room;
            public readonly WallEdge Edge;
            public readonly Vector3 Point;

            public Shoulder(Room room, WallEdge edge, Vector3 point)
            {
                Room = room;
                Edge = edge;
                Point = point;
            }

            /// Far (north/west) sides are the straight tile, near (south/east) sides the stub -
            /// the run's own tile, because the shoulder continues the run it interrupts.
            public bool Far => Edge == WallEdge.North || Edge == WallEdge.West;
        }

        // THE DOOR SHOULDERS. The visual opening is 4.000 units (a '++' cell pair at two units a
        // cell) and the contract-pinned collider gap is 3.000, so the leaf covers x[-1.5..1.5]
        // about its centre while the slot lattice cannot resume until the next integer - leaving
        // 0.500 units of bare wall line on each side. Vincent, twice: "The sides of the door still
        // have a gap" and "the brick around the door should be the same tiles of the wall".
        //
        // A 1.000-unit tile centred at centre +/- (half + 0.5) covers that 0.500 exactly and
        // overlaps the first run slot by the other 0.500. THE OVERLAP IS OUTWARD ON PURPOSE:
        // 1.000 of tile cannot fill 0.500 of hole without going somewhere, and the alternative is
        // inward, across the leaf - which is the fill-across-a-doorway that occluded a door once.
        //
        // Derived here from the layouts alone - door centre, DoorWidth, and which bound the centre
        // lies on - so it shares nothing with WallPiecePass.DoorShoulders but the arithmetic it is
        // meant to check. Deduplicated north-first at half-unit resolution, like the doors are
        // authored: a shared door is listed by both rooms and drawn once.
        private static List<Shoulder> ExpectedShoulders(List<Room> rooms)
        {
            var seen = new HashSet<(int, int)>();
            var shoulders = new List<Shoulder>();
            foreach (Room room in rooms)
            {
                foreach (Vector3 door in room.Doors)
                {
                    if (!seen.Add((Mathf.RoundToInt(door.x * 2f), Mathf.RoundToInt(door.z * 2f)))) continue;
                    WallEdge edge = room.EdgeOf(door);
                    bool alongX = AlongX(edge);
                    float line = room.Line(edge);
                    float centre = alongX ? door.x : door.z;
                    float reach = room.DoorWidth * 0.5f + 0.5f;
                    foreach (float along in new[] { centre - reach, centre + reach })
                    {
                        shoulders.Add(new Shoulder(room, edge,
                            alongX ? new Vector3(along, 0f, line) : new Vector3(line, 0f, along)));
                    }
                }
            }

            Assert.Greater(shoulders.Count, 0, "No door shoulders were expected, so every assertion about them is vacuous.");
            return shoulders;
        }

        // Every distinct layout corner across ALL rooms, independent of WallPiecePass's own
        // state.Posts bookkeeping - built straight from each room's own rectangle, the same
        // shape CornerPostsAndDoorShouldersReproduceTheApprovedPlacerArithmetic uses for posts.
        private static HashSet<(int, int)> AllCornerPoints(List<Room> rooms)
        {
            var points = new HashSet<(int, int)>();
            foreach (Room room in rooms)
            {
                foreach (float z in new[] { room.ZMax, room.ZMin })
                {
                    foreach (float x in new[] { room.XMin, room.XMax })
                    {
                        points.Add((Mathf.RoundToInt(x), Mathf.RoundToInt(z)));
                    }
                }
            }
            return points;
        }

        // NSC-127 AC-001's rhythm, re-derived: every fourth slot of a layout run (corner to door
        // collider edge), never the run's first or last slot, on far (straight) sides only.
        private static bool IsPilasterSlot(Slot slot, HashSet<(int, int)> corners)
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
            if (index % 4 != 0 || slot.Start <= runStart || slot.Start >= runLast) return false;

            // runStart/runLast only see THIS room's own rect and doors. Where a narrower room
            // shares this line and is drawn first (the shared-boundary rule), ITS corner post
            // can truncate the run this room actually renders well short of its own XMin/XMax -
            // a jog the room-local math above cannot see. A slot touching ANY room's corner on
            // this same line must never be a pilaster, whichever room the post belongs to.
            float line = slot.Line;
            (int, int) low = alongX
                ? (Mathf.RoundToInt(slot.Start), Mathf.RoundToInt(line))
                : (Mathf.RoundToInt(line), Mathf.RoundToInt(slot.Start));
            (int, int) high = alongX
                ? (Mathf.RoundToInt(slot.Start + 1f), Mathf.RoundToInt(line))
                : (Mathf.RoundToInt(line), Mathf.RoundToInt(slot.Start + 1f));
            return !corners.Contains(low) && !corners.Contains(high);
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

            // Every base piece's ROOT must stand on a lattice point OR a door shoulder, and every
            // expected point must hold exactly one. Both directions: no missing slot, no extra
            // piece. The shoulders are OFF the slot lattice by construction - a door centre is an
            // integer and a slot centre a half-integer - so the two sets cannot alias, and the
            // total below is their sum rather than a fudge factor.
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

            List<Shoulder> shoulders = ExpectedShoulders(rooms);
            foreach (Shoulder shoulder in shoulders)
            {
                if (!byPoint.TryGetValue(Key(shoulder.Point), out int n) || n != 1)
                {
                    missing.Add(shoulder.Room.Name + " " + shoulder.Edge + " door shoulder at "
                        + shoulder.Point.ToString("0.###") + " holds " + n + " piece(s)");
                }
            }

            Assert.IsEmpty(missing, "Slots and shoulders not filled exactly once:\n" + string.Join("\n", missing));
            Assert.AreEqual(expected.Count + shoulders.Count, byPoint.Values.Sum(),
                "The spawner placed " + byPoint.Values.Sum() + " base pieces for " + expected.Count
                + " wall slots plus " + shoulders.Count + " door shoulders. A surplus means a piece stands"
                + " where neither the lattice walk nor a door put one - an unclipped Final Room slot, a"
                + " duplicate on a shared line, or a phantom edge.");
        }

        [UnityTest]
        public IEnumerator FarSidesAreStraightOrPilasterAndNearSidesAreStubs()
        {
            WallSpawner spawner = CreateSpawner();
            List<Room> rooms = LayoutRooms();
            List<Slot> expected = ExpectedSlots(LoadMap(), rooms);
            HashSet<(int, int)> corners = AllCornerPoints(rooms);

            spawner.Spawn();
            yield return null;

            var spriteAt = BasePieceRenderers().ToDictionary(r => Key(r.transform.parent.position), r => r.sprite.name);
            var wrong = new List<string>();
            foreach (Slot slot in expected)
            {
                string actual = spriteAt[Key(slot.RootPoint)];
                bool far = slot.Edge == WallEdge.North || slot.Edge == WallEdge.West;
                string want = !far ? StubSprite : IsPilasterSlot(slot, corners) ? PilasterSprite : StraightSprite;
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
        public IEnumerator NoPilasterStandsAgainstAJoggedNeighbourRoomsCornerPost()
        {
            // NSC-126's gap-in-wall defect, reproduced and pinned: FinalRoom (narrower, XMin=-15)
            // sits inside LowerVault's wider XMin=-20..XMax=20 span at their shared Z=76 line. The
            // shared-boundary rule lets FinalRoom's corner post claim (-15,76) before LowerVault
            // places its own north-edge pilaster rhythm, but the OLD IsPilasterSlot only guarded
            // against LowerVault's OWN room-local run bounds (XMin=-20 to its own door), which
            // never sees a narrower neighbour's post cutting the run short - so the rhythm (every
            // 4th slot from XMin=-20) landed a pilaster in the run's last real slot, [-16,-15],
            // touching the post. This asserts the RELATION (no base piece ever seats a pilaster
            // sprite immediately against a corner post's own point) rather than the one coordinate
            // that happened to expose it, so it also catches the symmetric case anywhere else on
            // the map, today or after floor01.txt changes.
            WallSpawner spawner = CreateSpawner();
            List<Room> rooms = LayoutRooms();
            List<Slot> expected = ExpectedSlots(LoadMap(), rooms);
            HashSet<(int, int)> corners = AllCornerPoints(rooms);

            spawner.Spawn();
            yield return null;

            var spriteAt = BasePieceRenderers().ToDictionary(r => Key(r.transform.parent.position), r => r.sprite.name);
            var violations = new List<string>();
            foreach (Slot slot in expected)
            {
                if (spriteAt[Key(slot.RootPoint)] != PilasterSprite) continue;
                bool alongX = AlongX(slot.Edge);
                float line = slot.Line;
                (int, int) low = alongX
                    ? (Mathf.RoundToInt(slot.Start), Mathf.RoundToInt(line))
                    : (Mathf.RoundToInt(line), Mathf.RoundToInt(slot.Start));
                (int, int) high = alongX
                    ? (Mathf.RoundToInt(slot.Start + 1f), Mathf.RoundToInt(line))
                    : (Mathf.RoundToInt(line), Mathf.RoundToInt(slot.Start + 1f));
                if (corners.Contains(low) || corners.Contains(high))
                {
                    violations.Add(slot.Room.Name + " " + slot.Edge + " slot " + slot.Start
                        + " placed a pilaster touching a corner post at " + (corners.Contains(low) ? low : high));
                }
            }

            Assert.IsEmpty(violations, "A pilaster abuts a corner post - exactly the isolated-post "
                + "gap defect - at:\n" + string.Join("\n", violations));
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
                // TOLERANCE, NOT EQUALITY, AND THE REASON IS THE PROPERTY BEING READ. lossyScale is
                // COMPUTED by multiplying every parent's scale up the chain, so it accumulates
                // float error and arrives as 0.99999994 rather than 1. Assert.AreEqual compares
                // Vector3 with Equals(), which is exact per component, so this failed while
                // printing "Expected: (1.00, 1.00, 1.00) But was: (1.00, 1.00, 1.00)" - identical
                // to every digit shown. The claim worth keeping is "no wall is scaled", and the
                // durable way to state it is a magnitude bound, not bitwise equality.
                Assert.Less((renderer.transform.lossyScale - Vector3.one).magnitude, 1e-4f,
                    who + " is scaled to " + renderer.transform.lossyScale.ToString("F6")
                    + ". Wall sprites are never scaled.");
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
        public IEnumerator CornerPostsAndDoorShouldersReproduceTheApprovedPlacerArithmetic()
        {
            WallSpawner spawner = CreateSpawner();
            List<Room> rooms = LayoutRooms();
            Bounds corner = AuthoredSprite("WallCorner").bounds;

            spawner.Spawn();
            yield return null;

            // Posts: one per distinct layout corner, anchored so the sprite's outer edge is AT the
            // corner and its root ON the floor - (xMin + halfWidth, 0, zMax). The root is 0, not
            // -min.y: the pivot is authored on the drawn base, so -min.y (the committed scenes'
            // 0.25) lifted the post off the floor by its transparent padding.
            var expectedPosts = new HashSet<(int, int)>();
            var expectedPostPositions = new List<Vector3>();
            foreach (Room room in rooms)
            {
                foreach (float z in new[] { room.ZMax, room.ZMin })
                {
                    foreach ((float x, float sign) in new[] { (room.XMin, 1f), (room.XMax, -1f) })
                    {
                        if (!expectedPosts.Add((Mathf.RoundToInt(x), Mathf.RoundToInt(z)))) continue;
                        expectedPostPositions.Add(new Vector3(x + sign * corner.extents.x, 0f, z));
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

            // !!! THE JAMB IS NOT PLACED AT ALL ANY MORE, AND THAT ABSENCE IS THE ASSERTION. !!!
            // wall_door_jamb is a complete stone portal - two piers and a full lintel - and the
            // builder drew it twice, flanking a leaf that carries its own frame. Measured
            // 2026-09-27 in the live world: it floated 0.40625 (its own transparent bottom pad,
            // added back as height by the accent anchor), carried none of the 0.151 inward inset
            // its neighbours carry, and the stub run overlapped 75% of it.
            //
            // A COUNT IS THE ONLY WITNESS THAT CAN SEE A REMOVAL. Every other assertion in this
            // fixture checks that a piece is CORRECT, and a piece that should not exist is correct
            // by every one of them - which is how this suite asserted the intent in one test and
            // the defect in another and passed both.
            Assert.AreEqual(0, RenderersWithSprite(JambSprite).Count(),
                "wall_door_jamb is still being placed. The shoulder is filled with the wall's own "
                + "tile instead; nothing should draw a portal beside a door.");

            // The shoulders: two per distinct door, each a BASE piece - root ON the line, at the
            // base convention's own y of 0 - carrying the SIDE'S tile and the prefab's inward
            // inset. Read the sprite from the side, not from a literal: four of the five doors are
            // claimed on a SOUTH edge, where the run is the 2.797-unit stub, so a flat
            // wall_straight here would be the wrong art and the wrong height at 8 of 10 points.
            var shoulderByPoint = BasePieceRenderers().ToDictionary(r => Key(r.transform.parent.position), r => r);
            var wrongShoulders = new List<string>();
            List<Shoulder> doorShoulders = ExpectedShoulders(rooms);
            foreach (Shoulder shoulder in doorShoulders)
            {
                string who = shoulder.Room.Name + " " + shoulder.Edge + " shoulder " + shoulder.Point.ToString("0.###");
                if (!shoulderByPoint.TryGetValue(Key(shoulder.Point), out SpriteRenderer renderer))
                {
                    wrongShoulders.Add(who + ": no base piece stands there");
                    continue;
                }

                string want = shoulder.Far ? StraightSprite : StubSprite;
                if (renderer.sprite.name != want)
                {
                    wrongShoulders.Add(who + ": " + renderer.sprite.name + " should be " + want);
                }

                Transform root = renderer.transform.parent;
                if (Mathf.Abs(root.position.y) > 0.0001f)
                {
                    wrongShoulders.Add(who + ": root y is " + root.position.y + ", not 0 - the jamb's float, back again");
                }

                // THIS one is the real witness and the y above is nearly free: a base root's y is 0
                // by construction, but the inset is taken from the Inward vector the pass supplies.
                // The jamb's old call passed a direction ALONG the run, whose perpendicular
                // component is zero, so the same mistake here would leave the Visual sitting flat
                // on the line - and this is the line that would catch it.
                Vector3 offset = renderer.transform.position - root.position;
                float perpendicular = AlongX(shoulder.Edge) ? offset.z : offset.x;
                Vector3 toward = shoulder.Room.Center - shoulder.Point;
                float towardRoom = AlongX(shoulder.Edge) ? Mathf.Sign(toward.z) : Mathf.Sign(toward.x);
                if (Mathf.Abs(perpendicular - CarriedVisualInset * towardRoom) > 0.0001f)
                {
                    wrongShoulders.Add(who + ": the Visual is " + perpendicular + " off the line; expected "
                        + (CarriedVisualInset * towardRoom) + " toward the room");
                }
            }

            Assert.IsEmpty(wrongShoulders, doorShoulders.Count + " expected door shoulders, "
                + wrongShoulders.Count + " wrong:\n" + string.Join("\n", wrongShoulders));

            Assert.AreEqual(0, RenderersWithSprite(EndCapSprite).Count(),
                "floor01's rings leave no free run end, so no end cap should be placed.");
        }

        [UnityTest]
        public IEnumerator EveryCornerAndEndCapDrawnBaseRestsOnTheFloor()
        {
            WallSpawner spawner = CreateSpawner();
            spawner.Spawn();
            yield return null;

            // The witness is the sprite's TIGHT MESH, not sprite.bounds: bounds is the rect with its
            // transparent padding (corner 16px, end cap 18px below the art), and
            // subtracting it is exactly the defect this guards. A tight mesh hugs the alpha with a
            // dilation of at most 2px (1/32 at 64 PPU), so its lowest vertex is the drawn base.
            const float MeshDilation = 2f / 64f + 0.001f;
            // Jambs are not listed because none is placed: the arithmetic test asserts that count
            // is zero, and this one would pass vacuously on their absence rather than notice it.
            var overlays = RenderersWithSprite(CornerSprite).Concat(RenderersWithSprite(EndCapSprite)).ToList();
            Assert.Greater(overlays.Count, 0, "No overlay pieces were spawned, so this test would pass on nothing.");

            var floating = new List<string>();
            foreach (SpriteRenderer r in overlays)
            {
                Assert.AreEqual(SpriteMeshType.Tight, MeshTypeOf(r.sprite),
                    r.sprite.name + " is not a Tight mesh, so its vertices are the rect and cannot witness the drawn base.");
                float lowest = r.sprite.vertices.Min(v => v.y);
                float drawnBaseY = r.transform.position.y + lowest;
                if (drawnBaseY > 0.001f || drawnBaseY < -MeshDilation)
                {
                    floating.Add(r.sprite.name + " at " + r.transform.parent.position.ToString("0.###") + " drawn base y " + drawnBaseY.ToString("0.#####"));
                }
            }

            Assert.AreEqual(0, floating.Count, floating.Count + " of " + overlays.Count
                + " overlay pieces do not stand on the floor: " + string.Join("; ", floating));
        }

        private static SpriteMeshType MeshTypeOf(Sprite sprite)
        {
            var importer = (UnityEditor.TextureImporter)UnityEditor.AssetImporter.GetAtPath(UnityEditor.AssetDatabase.GetAssetPath(sprite));
            var settings = new UnityEditor.TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            return settings.spriteMeshType;
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
