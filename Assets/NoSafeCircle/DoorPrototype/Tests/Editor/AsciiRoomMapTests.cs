using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>Proves the ASCII map parser against the shapes the real artifacts actually have.</summary>
    /// <remarks>
    /// Every case here is one I hit while measuring DOC-20260923-nsc-floorplan-spine.txt, not a
    /// hypothetical. Read naively as a grid that file reports 81 rows, 92 columns and 2,017 floor
    /// cells; the truth is 73 map-shaped rows, 72 columns and 2,016 walkable cells inside a
    /// declared 72x72 bound. Every wrong number looks like a plausible map, which is why the
    /// prose tail and the blank margins get tests rather than comments.
    /// </remarks>
    public sealed class AsciiRoomMapTests
    {
        private static AsciiRoomMap Parse(string text)
        {
            Assert.IsTrue(AsciiRoomMap.TryParse(text, out AsciiRoomMap map, out string error), error);
            return map;
        }

        [Test]
        public void ParsesGlyphsIntoCells()
        {
            AsciiRoomMap map = Parse("###\n#.+\n###");

            Assert.AreEqual(3, map.Width);
            Assert.AreEqual(3, map.Height);
            Assert.AreEqual(AsciiCell.Wall, map[0, 0]);
            Assert.AreEqual(AsciiCell.Floor, map[1, 1]);
            Assert.AreEqual(AsciiCell.Opening, map[2, 1]);
        }

        // The defect this parser exists to avoid: the real floorplan is a map followed by a prose
        // summary, and reading the file as a grid silently invents rows, columns and floor cells.
        [Test]
        public void StopsAtTheFirstLineThatIsNotMapShaped()
        {
            AsciiRoomMap map = Parse(
                "####\n" +
                "#..#\n" +
                "####\n" +
                "grid            72 x 72 cells = 144 x 144 world units\n" +
                "walkable        2016 cells");

            Assert.AreEqual(3, map.Height, "The prose tail was counted as map rows.");
            Assert.AreEqual(4, map.Width, "A prose line widened the grid.");
            Assert.AreEqual(3, map.RowsConsumed);
            Assert.AreEqual(2, map.WalkableCellCount());
        }

        // A prose line containing a period would otherwise read as floor. This is exactly how the
        // real file reports one more walkable cell than it has.
        [Test]
        public void ProseContainingAPeriodDoesNotBecomeFloor()
        {
            AsciiRoomMap map = Parse(
                "#.#\n" +
                "SIGHTLINE CHECK PASSED: no unbroken run over 36 cells.");

            Assert.AreEqual(1, map.Height);
            Assert.AreEqual(1, map.WalkableCellCount(),
                "A period inside prose was counted as a floor cell.");
        }

        // THE PARSER GUESSES NOTHING ABOUT BLANK ROWS, and that is the decision this test pins.
        // A blank line is all spaces and therefore map-shaped, so it cannot be told apart from a
        // margin row inside the declared bound -- and margin rows are real, the bound being 72x72
        // while the geometry spans 70. Every stripping rule measured against the real artifact
        // gave a different wrong answer: both ends 69, tail only 70, neither 73, declared 72.
        [Test]
        public void BlankRowsAreReportedRatherThanStripped()
        {
            AsciiRoomMap map = Parse("\n\n###\n#.#\n###\n\n");

            Assert.AreEqual(7, map.Height, "Blank rows were stripped; the parser must not guess.");
            Assert.AreEqual(AsciiCell.Outside, map[0, 0], "Row 0 must still be the leading blank.");
            Assert.AreEqual(AsciiCell.Wall, map[0, 2], "The first wall row moved, shifting world z.");
        }

        // Trailing spaces pad the map out to its bound. Trimming them narrows the grid to the
        // widest row holding geometry -- 63 columns against a declared 72 on the real artifact.
        [Test]
        public void TrailingSpacesAreOutsideCellsInsideTheBoundNotAbsentOnes()
        {
            AsciiRoomMap map = Parse("##   \n#.#  \n##   ");

            Assert.AreEqual(5, map.Width, "Padding out to the bound was trimmed away.");
            Assert.AreEqual(AsciiCell.Outside, map[4, 0]);
        }

        // The bound comes from the CALLER because the file cannot supply it.
        [Test]
        public void RequireBoundAcceptsAMapThatFitsAndRejectsOneThatDoesNot()
        {
            AsciiRoomMap map = Parse("####\n#..#\n####");

            Assert.IsTrue(map.RequireBound(72, 72, out string fits), fits);
            Assert.IsTrue(map.RequireBound(4, 3, out string exact), exact);
            Assert.IsFalse(map.RequireBound(3, 3, out string tooWide));
            StringAssert.Contains("does not fit", tooWide);
            StringAssert.Contains("world units", tooWide);
        }

        [Test]
        public void AcceptsCrlfAndLfIdentically()
        {
            AsciiRoomMap lf = Parse("###\n#.#\n###");
            AsciiRoomMap crlf = Parse("###\r\n#.#\r\n###");

            Assert.AreEqual(lf.Width, crlf.Width);
            Assert.AreEqual(lf.Height, crlf.Height);
            Assert.AreEqual(lf.ToString(), crlf.ToString());
        }

        [Test]
        public void RoundTripsThroughText()
        {
            const string source = "#####\n#...#\n#.+.#\n#####";

            Assert.AreEqual(source, Parse(source).ToString());
        }

        [Test]
        public void OpeningsAreWalkableAndWallsAreNot()
        {
            AsciiRoomMap map = Parse("#+#\n#.#");

            Assert.IsTrue(map.IsWalkable(1, 0), "An opening must stay walkable.");
            Assert.IsTrue(map.IsWalkable(1, 1));
            Assert.IsFalse(map.IsWalkable(0, 0));
            Assert.IsFalse(map.IsWalkable(-1, 0), "Out of range must not throw or report walkable.");
            Assert.IsFalse(map.IsWalkable(0, 99));
        }

        // One cell is two world units, from the 2026-09-23 scale decision. Getting this wrong
        // scales the whole level, and the decision document's own title still says the withdrawn
        // 128, so the number is pinned here against the live figure rather than the title.
        [Test]
        public void OneCellIsTwoWorldUnits()
        {
            Assert.AreEqual(2f, AsciiRoomMap.WorldUnitsPerCell);
            Assert.AreEqual(144f, 72 * AsciiRoomMap.WorldUnitsPerCell,
                "72 cells must span the 144 world units the scale decision fixed.");
        }

        // Row 0 is the TOP of the map and the HIGHEST world z. Reversed, the level mirrors and
        // every room still looks plausible, so it gets an assertion rather than a comment.
        [Test]
        public void RowZeroIsTheHighestWorldZ()
        {
            AsciiRoomMap map = Parse("###\n###\n###");

            AsciiCellIndex top = map.ToCell(0f, 100f, 0f, 100f);
            AsciiCellIndex below = map.ToCell(0f, 98f, 0f, 100f);

            Assert.AreEqual(0, top.Row);
            Assert.AreEqual(1, below.Row, "World z decreasing must move DOWN the map, not up.");
        }

        [Test]
        public void RefusesTextWithNoMapAtAll()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("grid 72 x 72\nwalkable 2016", out _, out string error));
            Assert.IsNotEmpty(error);
        }
    }
}
