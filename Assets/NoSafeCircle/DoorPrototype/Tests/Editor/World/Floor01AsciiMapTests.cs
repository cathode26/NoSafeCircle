using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
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

        [Test]
        public void MapRectContainsEachRoomsLayoutRectAndDiffersByLessThanOneCell()
        {
            // THIS TEST REPLACES A DESIGN STEP THAT WAS GOING TO MOVE A DELIVERED ROOM.
            //
            // The walls addendum (2A) found that the map's Final Room rectangle is X [-16,+16] while
            // FinalRoomLayout says X [-15,+15], and proposed snapping the room to +/-16 because 15 is
            // not on the 2-unit cell lattice. Measured cost of that snap: NSC-048 is `conformant`
            // with an approved delivery record, and its AC-001 requirement text names "X [-15,+15]"
            // literally, as do AC-003 (the wall runs and the -14.849 Tilemap inset), AC-004 (the
            // split collider spans) and NSC-049's INT-001 (the shared Z 76 reconciliation over
            // X [-15,+15] and the Lower Vault jog over X [-20,-15] and [+15,+20]). Editing a
            // delivered task's requirement voids its delivery record, so a 1-unit cosmetic
            // alignment would have un-delivered the only delivered room work in the sprint.
            //
            // IT COSTS NOTHING TO LEAVE IT, because 2A's own decision 1 already says the layouts -
            // never the map - are authoritative for "exact wall-collider lines". The spawner takes
            // each room's collider line and run extent from its *Layout.cs and takes only the
            // TOPOLOGY (which cells are band, floor, opening, outside) from the map, so the wall the
            // wizard sees stands on the line he collides with and there is no 1-unit gap to close.
            //
            // WHAT THIS ASSERTS IS THEREFORE A RELATION, NOT A COORDINATE: a 2-unit grid cannot
            // place a boundary on an odd world coordinate, so the map's rectangle CONTAINS the
            // layout's and differs from it by strictly less than one cell on every edge. That is
            // true of any room anyone adds later. The per-room insets are pinned as well so a map
            // edit cannot silently widen one - four rooms are exact and only the Final Room's two X
            // edges carry the half-cell, which is a property of the GRID and not a defect in the room.
            AsciiRoomMap map = ParseOrFail();

            // Every room exposes RoomBounds; only four of five expose Minimum/MaximumX, so the
            // bounds accessor is the one that works uniformly and keeps this table symmetric.
            // name, layout bounds, expected west inset, expected east inset
            var rooms = new[]
            {
                new object[] { "RuinedEntry", RuinedEntryLayout.RoomBounds, 0f, 0f },
                new object[] { "BoneArchive", BoneArchiveLayout.RoomBounds, 0f, 0f },
                new object[] { "ChapelOfAsh", ChapelOfAshLayout.RoomBounds, 0f, 0f },
                new object[] { "LowerVault", LowerVaultLayout.RoomBounds, 0f, 0f },
                new object[] { "FinalRoom", FinalRoomLayout.RoomBounds, 1f, 1f },
            };

            foreach (object[] room in rooms)
            {
                var name = (string)room[0];
                var layout = (Bounds)room[1];
                float layoutMinX = layout.min.x;
                float layoutMaxX = layout.max.x;
                float layoutMinZ = layout.min.z;
                float layoutMaxZ = layout.max.z;
                float expectedWestInset = (float)room[2];
                float expectedEastInset = (float)room[3];

                // Rows are derived from the room's own Z bounds and the map origin, so a room that
                // moves in Z is read at its new rows rather than at a frozen row number.
                int firstRow = (int)((MaximumZ - layoutMaxZ) / AsciiRoomMap.WorldUnitsPerCell);
                int lastRow = (int)((MaximumZ - layoutMinZ) / AsciiRoomMap.WorldUnitsPerCell) - 1;

                int firstColumn = int.MaxValue;
                int lastColumn = int.MinValue;
                for (int row = firstRow; row <= lastRow; row++)
                {
                    for (int column = 0; column < Columns; column++)
                    {
                        if (map[column, row] == AsciiCell.Outside)
                        {
                            continue;
                        }

                        firstColumn = column < firstColumn ? column : firstColumn;
                        lastColumn = column > lastColumn ? column : lastColumn;
                    }
                }

                Assert.AreNotEqual(int.MaxValue, firstColumn,
                    name + " occupies rows " + firstRow + ".." + lastRow
                    + " of the map and every cell in them is Outside. The room is missing from the map.");

                float mapMinX = MinimumX + (AsciiRoomMap.WorldUnitsPerCell * firstColumn);
                float mapMaxX = MinimumX + (AsciiRoomMap.WorldUnitsPerCell * (lastColumn + 1));

                // Containment, in the only direction a coarser grid can err.
                Assert.LessOrEqual(mapMinX, layoutMinX,
                    name + ": the map's west edge " + mapMinX + " is inside the layout's "
                    + layoutMinX + ", so part of the room has no cell to be drawn in.");
                Assert.GreaterOrEqual(mapMaxX, layoutMaxX,
                    name + ": the map's east edge " + mapMaxX + " is inside the layout's "
                    + layoutMaxX + ", so part of the room has no cell to be drawn in.");

                // Less than one cell, which is what makes the inset a rounding artifact rather
                // than a disagreement about where the room is.
                Assert.Less(layoutMinX - mapMinX, AsciiRoomMap.WorldUnitsPerCell,
                    name + ": the map's west edge is a whole cell or more outside the layout's.");
                Assert.Less(mapMaxX - layoutMaxX, AsciiRoomMap.WorldUnitsPerCell,
                    name + ": the map's east edge is a whole cell or more outside the layout's.");

                // And exactly the inset we measured, so nobody widens a room by editing the map.
                Assert.AreEqual(expectedWestInset, layoutMinX - mapMinX, 0.001f,
                    name + ": west inset changed. Map " + mapMinX + ", layout " + layoutMinX
                    + ". If the room really moved, move it in its *Layout.cs and revise its contract;"
                    + " if the map is wrong, fix the map.");
                Assert.AreEqual(expectedEastInset, mapMaxX - layoutMaxX, 0.001f,
                    name + ": east inset changed. Map " + mapMaxX + ", layout " + layoutMaxX + ".");
            }
        }
    }
}
