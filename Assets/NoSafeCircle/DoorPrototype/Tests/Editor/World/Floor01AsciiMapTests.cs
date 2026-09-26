using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    // The committed ASCII map of the actual floor, checked against the parser that consumes it.
    //
    // WHY THIS EXISTS. Vincent, 2026-09-26: "Okay so i would do for step 1, is rebuild our scene in
    // ascii." / "We need a ascii map of our level." The map is
    // Content/Levels/floor01.txt, generated from the authoritative *Layout.cs bounds and door
    // centres rather than drawn by eye, so the map and the game agree by construction.
    //
    // AND WHY IT MATTERS THAT THE PARSER HAD NO CALLER. AsciiRoomMap is 357 lines of runtime code
    // with its own unit tests and ZERO production callers - the same shape as
    // GameplayNavigationSurface.ConfigureAndBuild(), which also existed, also had tests, and also
    // never ran in the game. A parser nothing parses with is a parser nobody has proved can read
    // the real artifact. This fixture is the first thing that feeds it one.
    public sealed class Floor01AsciiMapTests
    {
        private const string MapPath =
            "Assets/NoSafeCircle/DoorPrototype/Content/Levels/floor01.txt";

        // DECLARED BY THE CALLER, which is the parser's whole design: it refuses to infer its own
        // dimensions because every rule for doing so was wrong in a different way (see its own
        // remarks). These two numbers come from the floor's world extent divided by
        // AsciiRoomMap.WorldUnitsPerCell, and the first test proves that arithmetic rather than
        // trusting it.
        private const int Columns = 20;
        private const int Rows = 65;

        // World extent of the floor, from Scripts/World/Rooms/*Layout.cs on main:
        // X from LowerVaultLayout.MinimumX (-20) to MaximumX (+20);
        // Z from RuinedEntryLayout.MinimumZ (-26) to FinalRoomLayout.MaximumZ (104).
        private const float MinimumX = -20f;
        private const float MaximumX = 20f;
        private const float MinimumZ = -26f;
        private const float MaximumZ = 104f;

        private static string ReadMap()
        {
            Assert.IsTrue(File.Exists(MapPath),
                MapPath + " does not exist. The ASCII map is the level's source of truth for "
                + "walkability; without it this fixture proves nothing.");
            return File.ReadAllText(MapPath);
        }

        private static AsciiRoomMap ParseOrFail()
        {
            Assert.IsTrue(
                AsciiRoomMap.TryParse(ReadMap(), Columns, Rows, out AsciiRoomMap map, out string error),
                "floor01.txt did not parse as " + Columns + "x" + Rows + ": " + error);
            return map;
        }

        [Test]
        public void DeclaredGridMatchesTheFloorsWorldExtentAtTheParsersOwnCellSize()
        {
            // The two literals above are derived, not chosen. If someone widens a room and forgets
            // the map, this fails before any walkability claim is made.
            float cell = AsciiRoomMap.WorldUnitsPerCell;
            Assert.AreEqual(Columns, (int)((MaximumX - MinimumX) / cell),
                "Declared column count disagrees with the floor's X extent at "
                + cell + " units per cell.");
            Assert.AreEqual(Rows, (int)((MaximumZ - MinimumZ) / cell),
                "Declared row count disagrees with the floor's Z extent at "
                + cell + " units per cell.");
        }

        [Test]
        public void TheCommittedMapParses()
        {
            AsciiRoomMap map = ParseOrFail();
            Assert.AreEqual(Columns, map.Width);
            Assert.AreEqual(Rows, map.Height);
            Assert.AreEqual(Rows, map.RowsConsumed);

            Assert.IsTrue(map.RequireBound(Columns, Rows, out string boundError), boundError);

            // Trailing spaces are stripped in the committed file, so rows shorter than the declared
            // width are padded with Outside. That is explicitly allowed by TryParse, and
            // RequireEveryRowWritten is the STRICTER rule for a hand-authored map where every cell
            // should be typed. This map is generated and kept free of trailing whitespace, because
            // trailing whitespace in a committed text file is churn every editor fights over.
            // Asserting the padding is EXPECTED rather than silently tolerated.
            Assert.Greater(map.PaddedRowCount, 0,
                "No row was padded, which means the committed file carries trailing spaces. That is "
                + "not wrong, but it contradicts how this map is generated - check which changed.");
        }

        [Test]
        public void EveryWalkableCellIsReachableFromThePlayerSpawn()
        {
            // THE LOAD-BEARING TEST, and the one an eyeball cannot do. The first generated map had
            // every door punched through exactly ONE of the two wall rows each room boundary has -
            // rooms abut exactly, so each boundary is two rows, one per room - and the rendered map
            // looked completely correct while the level was in five disconnected pieces.
            AsciiRoomMap map = ParseOrFail();

            // Spawn inside the first room. Row/column from the parser's own ToCell, so this test
            // cannot disagree with the mapping the game will use.
            AsciiCellIndex spawn = map.ToCell(0f, -22f, MinimumX, MaximumZ);
            Assert.IsTrue(map.IsWalkable(spawn.Column, spawn.Row),
                "Spawn cell " + spawn + " is not walkable; the flood fill would prove nothing.");

            var seen = new HashSet<long>();
            var stack = new Stack<AsciiCellIndex>();
            stack.Push(spawn);
            while (stack.Count > 0)
            {
                AsciiCellIndex at = stack.Pop();
                if (!map.IsWalkable(at.Column, at.Row)) continue;
                long key = ((long)at.Column << 32) ^ (uint)at.Row;
                if (!seen.Add(key)) continue;
                stack.Push(new AsciiCellIndex(at.Column + 1, at.Row));
                stack.Push(new AsciiCellIndex(at.Column - 1, at.Row));
                stack.Push(new AsciiCellIndex(at.Column, at.Row + 1));
                stack.Push(new AsciiCellIndex(at.Column, at.Row - 1));
            }

            int walkable = map.WalkableCellCount();
            Assert.Greater(walkable, 0, "The map has no walkable cells at all.");
            Assert.AreEqual(walkable, seen.Count,
                "The floor is NOT connected: " + (walkable - seen.Count) + " of " + walkable
                + " walkable cells cannot be reached from the spawn. A door punched through only "
                + "one of a boundary's two wall rows produces exactly this, and looks correct.");
        }

        [Test]
        public void EveryDoorCentreLandsOnAnOpeningInBothRoomsWalls()
        {
            // Each door is authored once per room, so a boundary has two wall rows and the opening
            // must exist in both. Checked against the layout constants rather than the map's own
            // glyphs, so the map cannot certify itself.
            AsciiRoomMap map = ParseOrFail();
            float cell = AsciiRoomMap.WorldUnitsPerCell;

            (string name, float x, float z, bool outerEdge)[] doors =
            {
                ("D1", 0f, 0f, false),
                ("D2", 6f, 20f, false),
                ("D3", -8f, 54f, false),
                ("D4", 4f, 76f, false),
                ("D5", 0f, 104f, true),   // the floor's northern boundary: one wall row, not two
            };

            foreach ((string name, float x, float z, bool outerEdge) in doors)
            {
                // The rows either side of the boundary. An interior boundary has both; the outer
                // edge has only the one inside the floor.
                var rowsToCheck = new List<int>();
                foreach (float probeZ in new[] { z + cell / 2f, z - cell / 2f })
                {
                    AsciiCellIndex idx = map.ToCell(x, probeZ, MinimumX, MaximumZ);
                    if (idx.Row >= 0 && idx.Row < map.Height && !rowsToCheck.Contains(idx.Row))
                    {
                        rowsToCheck.Add(idx.Row);
                    }
                }

                Assert.AreEqual(outerEdge ? 1 : 2, rowsToCheck.Count,
                    name + " straddles " + rowsToCheck.Count + " row(s); expected "
                    + (outerEdge ? 1 : 2) + ".");

                foreach (int row in rowsToCheck)
                {
                    AsciiCellIndex at = map.ToCell(x, z, MinimumX, MaximumZ);
                    Assert.IsTrue(map.IsWalkable(at.Column, row),
                        name + " at world (" + x + "," + z + ") is blocked at column "
                        + at.Column + ", row " + row + ". A door that opens into the neighbouring "
                        + "room's solid wall renders perfectly and cannot be walked through.");
                }
            }
        }

        [Test]
        public void TheMapRoundTripsThroughTheParser()
        {
            // ToString exists so a round trip can be asserted; nothing asserted it against a real
            // artifact until now. Compared per row with trailing Outside stripped, because the
            // committed file carries no trailing whitespace while ToString pads to the full width.
            AsciiRoomMap map = ParseOrFail();
            string[] original = ReadMap().Replace("\r\n", "\n").TrimEnd('\n').Split('\n');
            string[] rendered = map.ToString().Split('\n');

            Assert.AreEqual(original.Length, rendered.Length,
                "Round trip changed the row count.");
            for (int i = 0; i < original.Length; i++)
            {
                Assert.AreEqual(original[i].TrimEnd(' '), rendered[i].TrimEnd(' '),
                    "Row " + (i + 1) + " did not survive the round trip.");
            }
        }
    }
}
