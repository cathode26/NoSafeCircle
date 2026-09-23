using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>Proves the ASCII map parser against defects that were actually executed against it.</summary>
    /// <remarks>
    /// TWO ASTRA AUDIT ROUNDS PLANTED ELEVEN DEFECTS IN THIS PARSER AND THE SUITE MISSED ALL OF
    /// THEM AT LEAST ONCE. Round 1 introduced four -- remove the height-overflow check, return
    /// column zero for every world position, make Outside cells walkable, drop openings from the
    /// walkable count -- and the 12-test suite passed every time, because it asserted that things
    /// EXISTED rather than that they BEHAVED.
    /// <para>
    /// Round 2 found seven more, and three of those got through because REBUILDING THE SUITE
    /// DELETED COVERAGE: the width-overflow case and the larger-bound acceptance case were removed
    /// when a height case was added, and the RowsConsumed assertion went with them. Adding a test
    /// is not the same as replacing one. Those are restored below and named as restorations.
    /// </para>
    /// <para>
    /// Each test here names the defect it exists to catch. A test that cannot fail is worse than
    /// no test, because it reports safety.
    /// </para>
    /// </remarks>
    public sealed class AsciiRoomMapTests
    {
        private static AsciiRoomMap Parse(string text, int columns, int rows)
        {
            Assert.IsTrue(AsciiRoomMap.TryParse(text, columns, rows, out AsciiRoomMap map, out string error), error);
            return map;
        }

        [Test]
        public void ParsesGlyphsIntoCells()
        {
            AsciiRoomMap map = Parse("###\n#.+\n###", 3, 3);

            Assert.AreEqual(3, map.Width);
            Assert.AreEqual(3, map.Height);

            Assert.AreEqual(AsciiCell.Wall, map[0, 0]);
            Assert.AreEqual(AsciiCell.Floor, map[1, 1]);
            Assert.AreEqual(AsciiCell.Opening, map[2, 1]);
        }

        // ---- the declared grid: what round 2's first finding forced ----

        // "A tail is terminal" accepted a DAMAGED FINAL ROW: "###/#.#/#x#" returned a clean 3x2
        // map whose walkable count matched the intact room, and every validator passed. With the
        // grid declared, an unrecognised glyph anywhere inside it is an error instead of an end.
        [Test]
        public void AnUnknownGlyphAnywhereInTheDeclaredGridFails()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("###\n#.#\n#x#", 3, 3, out AsciiRoomMap last, out string lastError),
                "A damaged FINAL row must fail, not silently shorten the map.");
            Assert.IsNull(last);
            StringAssert.Contains("row 3", lastError);
            StringAssert.Contains("'x'", lastError);

            Assert.IsFalse(AsciiRoomMap.TryParse("###\n#x#\n###", 3, 3, out _, out string midError),
                "A damaged middle row must fail too.");
            StringAssert.Contains("row 2", midError);
        }

        // Fewer lines than declared is premature end of map, not a smaller map.
        [Test]
        public void FewerLinesThanDeclaredFailsRatherThanShrinkingTheGrid()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("###\n#.#", 3, 3, out _, out string error));
            StringAssert.Contains("Premature end of map", error);
        }

        // Everything after the declared rows is ignored, so a prose tail needs no heuristic --
        // and legitimate prose ending in "..." is no longer rejected as resumed geometry.
        [Test]
        public void ContentAfterTheDeclaredRowsIsIgnoredWhateverItLooksLike()
        {
            AsciiRoomMap map = Parse(
                "####\n#..#\n####\n" +
                "\n" +
                "grid  72 x 72 cells = 144 x 144 world units\n" +
                "...", 4, 3);

            Assert.AreEqual(3, map.Height);
            Assert.AreEqual(2, map.WalkableCellCount());
        }

        [Test]
        public void ContentWiderThanTheDeclaredGridFailsButTrailingSpacesDoNot()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("###\n#.##\n###", 3, 3, out _, out string error),
                "A row with content past the declared width must fail.");
            StringAssert.Contains("column 4", error);

            AsciiRoomMap padded = Parse("###   \n#.#   \n###   ", 3, 3);
            Assert.AreEqual(3, padded.Width, "Trailing spaces beyond the declared width are harmless.");
        }

        // ---- the four defects round 1 planted ----

        // RESTORED plus extended. The original width case was deleted when the height case was
        // added, and round 2 removed width-overflow rejection without any test failing.
        [Test]
        public void RequireBoundRejectsOverflowOnBothAxesAndAcceptsASmallerMap()
        {
            AsciiRoomMap wide = Parse("####\n####", 4, 2);
            Assert.IsFalse(wide.RequireBound(3, 2, out string tooWide), "RESTORED: width overflow.");
            StringAssert.Contains("does not fit", tooWide);

            AsciiRoomMap tall = Parse("##\n##\n##\n##", 2, 4);
            Assert.IsFalse(tall.RequireBound(2, 3, out string tooTall), "Height overflow.");

            // RESTORED: round 2 made RequireBound demand EXACT dimensions and nothing failed,
            // because no test asserted that a SMALLER map is accepted inside a larger bound.
            Assert.IsTrue(tall.RequireBound(72, 72, out string smaller), smaller);
            Assert.IsTrue(tall.RequireBound(2, 4, out string exact), exact);
        }

        [Test]
        public void ToCellMapsDistinctWorldXToDistinctColumns()
        {
            AsciiRoomMap map = Parse("####\n####", 4, 2);

            Assert.AreEqual(0, map.ToCell(0f, 0f, 0f, 0f).Column);
            Assert.AreEqual(1, map.ToCell(2f, 0f, 0f, 0f).Column,
                "One cell is two world units, so x=2 must be column 1.");
            Assert.AreEqual(3, map.ToCell(7f, 0f, 0f, 0f).Column);
        }

        // Round 2 made ToCell ignore originX and nothing failed, because every column assertion
        // used a zero origin.
        [Test]
        public void ToCellRespectsATranslatedOrigin()
        {
            AsciiRoomMap map = Parse("####\n####", 4, 2);

            Assert.AreEqual(0, map.ToCell(100f, 0f, 100f, 0f).Column, "originX was ignored.");
            Assert.AreEqual(2, map.ToCell(104f, 0f, 100f, 0f).Column);
            Assert.AreEqual(0, map.ToCell(50f, 50f, 50f, 50f).Row, "originZ was ignored.");
            Assert.AreEqual(1, map.ToCell(50f, 48f, 50f, 50f).Row);
        }

        // Round 2 replaced flooring with truncation and nothing failed, because no test used a
        // position WEST of the origin. Truncation puts the cells either side of zero together.
        [Test]
        public void ToCellFloorsRatherThanTruncatingSoNegativeOffsetsDoNotCollapse()
        {
            AsciiRoomMap map = Parse("####\n####", 4, 2);

            Assert.AreEqual(-1, map.ToCell(-1f, 0f, 0f, 0f).Column,
                "One unit west of the origin is column -1; truncation would report 0.");
            Assert.AreEqual(-1, map.ToCell(-0.5f, 0f, 0f, 0f).Column);
            Assert.AreEqual(0, map.ToCell(0.5f, 0f, 0f, 0f).Column);
        }

        [Test]
        public void OutsideIsNotWalkable()
        {
            AsciiRoomMap map = Parse("# #\n#.#", 3, 2);

            Assert.AreEqual(AsciiCell.Outside, map[1, 0], "Fixture: expected an Outside cell here.");
            Assert.IsFalse(map.IsWalkable(1, 0), "Outside must never be walkable.");
            Assert.IsFalse(map.IsWalkable(0, 0), "Wall must never be walkable.");
            Assert.IsTrue(map.IsWalkable(1, 1));
        }

        [Test]
        public void WalkableCellCountIncludesOpeningsAndExcludesWallsAndOutside()
        {
            AsciiRoomMap map = Parse("#+#\n#.#\n# #", 3, 3);

            Assert.AreEqual(2, map.WalkableCellCount(),
                "One opening plus one floor is two walkable cells.");
        }

        // Round 2 let column == Width through the range guard, throwing instead of returning
        // false, because the out-of-range tests used 99 rather than the FIRST invalid index.
        [Test]
        public void IsWalkableIsFalseAtTheFirstInvalidIndexRatherThanThrowing()
        {
            AsciiRoomMap map = Parse("#.#\n###", 3, 2);

            Assert.IsFalse(map.IsWalkable(3, 0), "Column == Width is the first invalid column.");
            Assert.IsFalse(map.IsWalkable(0, 2), "Row == Height is the first invalid row.");
            Assert.IsFalse(map.IsWalkable(-1, 0));
            Assert.IsFalse(map.IsWalkable(0, -1));
            Assert.IsFalse(map.IsWalkable(99, 99));
        }

        // ---- padding, which round 2's third finding sharpened ----

        // PaddedRowCount used to exclude BLANK short rows, so "###\n\n###" reported zero padded
        // rows while inventing three cells, and both validators passed. A blank row is the most
        // padded row there is.
        [Test]
        public void BlankAndShortRowsAreBothCountedAsPadded()
        {
            AsciiRoomMap blank = Parse("###\n\n###", 3, 3);
            Assert.AreEqual(1, blank.PaddedRowCount, "A blank row is entirely invented.");
            Assert.IsFalse(blank.RequireEveryRowWritten(out string blankError));
            StringAssert.Contains("Blank rows count", blankError);

            AsciiRoomMap whitespace = Parse("###\n \n###", 3, 3);
            Assert.AreEqual(1, whitespace.PaddedRowCount, "A whitespace-only short row is padded too.");

            AsciiRoomMap shortRow = Parse("###\n#.\n###", 3, 3);
            Assert.AreEqual(1, shortRow.PaddedRowCount);
            Assert.AreEqual(AsciiCell.Outside, shortRow[2, 1]);

            AsciiRoomMap full = Parse("###\n#.#\n###", 3, 3);
            Assert.AreEqual(0, full.PaddedRowCount);
            Assert.IsTrue(full.RequireEveryRowWritten(out _));
        }

        // ---- shapes measured on the real artifact ----

        // A period inside prose would read as floor if prose were ever parsed as map. With the
        // grid declared this is structural rather than heuristic, and the case is kept because it
        // is how the real file appears to hold one more walkable cell than it does.
        [Test]
        public void ProseBeyondTheDeclaredGridNeverBecomesFloor()
        {
            AsciiRoomMap map = Parse(
                "#.#\nSIGHTLINE CHECK PASSED: no unbroken run over 36 cells.", 3, 1);

            Assert.AreEqual(1, map.Height);
            Assert.AreEqual(1, map.WalkableCellCount());
        }

        [Test]
        public void ATrailingNewlineDoesNotChangeTheResult()
        {
            Assert.AreEqual(Parse("###\n#.#\n###", 3, 3).ToString(),
                            Parse("###\n#.#\n###\n", 3, 3).ToString(),
                            "A file-final newline is a split artifact, not a map row.");
        }

        [Test]
        public void AcceptsCrlfAndLfIdentically()
        {
            Assert.AreEqual(Parse("###\n#.#\n###", 3, 3).ToString(),
                            Parse("###\r\n#.#\r\n###", 3, 3).ToString());
        }

        // Round 2 serialized Outside cells as walls and nothing failed, because the round-trip
        // fixture contained no spaces.
        [Test]
        public void RoundTripsThroughTextIncludingOutsideCells()
        {
            const string source = "## ##\n#...#\n#.+.#\n## ##";

            Assert.AreEqual(source, Parse(source, 5, 4).ToString(),
                "Outside cells must serialize back to spaces, not to walls.");
        }

        // One cell is two world units, from the 2026-09-23 scale decision. That document's own
        // TITLE still says the withdrawn 128, so this pins the live figure rather than the title.
        [Test]
        public void OneCellIsTwoWorldUnits()
        {
            Assert.AreEqual(2f, AsciiRoomMap.WorldUnitsPerCell);
            Assert.AreEqual(144f, 72 * AsciiRoomMap.WorldUnitsPerCell,
                "72 cells must span the 144 world units the scale decision fixed.");
        }

        // Row 0 is the TOP of the map and the HIGHEST world z. Reversed, the level mirrors and
        // every room still looks plausible.
        [Test]
        public void RowZeroIsTheHighestWorldZ()
        {
            AsciiRoomMap map = Parse("###\n###\n###", 3, 3);

            Assert.AreEqual(0, map.ToCell(0f, 100f, 0f, 100f).Row);
            Assert.AreEqual(1, map.ToCell(0f, 98f, 0f, 100f).Row,
                "World z decreasing must move DOWN the map, not up.");
        }

        [Test]
        public void RefusesNullTextAndNonPositiveDimensions()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse(null, 3, 3, out _, out string nullError));
            Assert.IsNotEmpty(nullError);
            Assert.IsFalse(AsciiRoomMap.TryParse("###", 0, 3, out _, out string zeroError));
            StringAssert.Contains("positive", zeroError);
            Assert.IsFalse(AsciiRoomMap.TryParse("###", 3, -1, out _, out _));
        }

        // ---- round 3: seven more mutations that passed 20/20 ----

        // I had already RESTORED a RowsConsumed assertion -- on a 3x3 map, which cannot tell
        // rows from columns. Reporting one as the other still passed. A restored test with a
        // square fixture is a restored test that cannot fail.
        [Test]
        public void AsymmetricGridReportsRowsNotColumns()
        {
            AsciiRoomMap map = Parse("#####\n#...#", 5, 2);

            Assert.AreEqual(5, map.Width);
            Assert.AreEqual(2, map.Height);
            Assert.AreEqual(2, map.RowsConsumed, "RowsConsumed reported the column count.");
        }

        // Flooring was asserted on columns only, so truncating just the Z-to-row calculation
        // passed. Truncation puts the rows either side of the origin into the same one.
        [Test]
        public void ToCellFloorsTheRowAxisToo()
        {
            AsciiRoomMap map = Parse("###\n###", 3, 2);

            Assert.AreEqual(-1, map.ToCell(0f, 1f, 0f, 0f).Row,
                "One unit NORTH of the origin is row -1; truncation would report 0.");
            Assert.AreEqual(-1, map.ToCell(0f, 0.5f, 0f, 0f).Row);
            Assert.AreEqual(0, map.ToCell(0f, -0.5f, 0f, 0f).Row);
        }

        // Retaining the final newline's empty split element passed every test, because no case
        // combined a trailing newline with a row count that would then be satisfied by it.
        [Test]
        public void PrematureEndOfMapIsStillDetectedWhenTheTextEndsWithANewline()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("###\n#.#\n", 3, 3, out _, out string error),
                "A trailing newline must not stand in for the missing third row.");
            StringAssert.Contains("Premature end of map", error);
        }

        // EMPTY INPUT IS ZERO PHYSICAL LINES. "".Split() yields one empty element, so
        // TryParse("", 3, 1) SUCCEEDED with a 3x1 Outside grid -- a row invented from nothing
        // while the premature-EOF rule that exists to stop that reported no problem.
        [Test]
        public void EmptyTextIsZeroRowsButASingleNewlineIsOneExplicitBlankRow()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("", 3, 1, out _, out string error),
                "Empty text supplies no rows at all.");
            StringAssert.Contains("Premature end of map", error);

            AsciiRoomMap blankRow = Parse("\n", 3, 1);
            Assert.AreEqual(1, blankRow.Height, "A single newline is one explicit blank row.");
            Assert.AreEqual(1, blankRow.PaddedRowCount);
        }

        // Making RequireEveryRowWritten reject exactly ONE padded row passed, because no case
        // had two.
        [Test]
        public void RequireEveryRowWrittenRejectsMoreThanOnePaddedRow()
        {
            AsciiRoomMap two = Parse("###\n#.\n#", 3, 3);

            Assert.AreEqual(2, two.PaddedRowCount);
            Assert.IsFalse(two.RequireEveryRowWritten(out string error));
            StringAssert.Contains("2 row(s)", error);
        }

        // Inspecting only the FIRST character past the declared width passed, because the
        // surplus test had content immediately after the boundary rather than beyond a space.
        [Test]
        public void ContentBeyondTheDeclaredWidthFailsEvenAfterAnInterveningSpace()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("#.# +", 3, 1, out _, out string error),
                "A space then content past the declared width is still content past it.");
            StringAssert.Contains("column 5", error);
        }

        // Trimming LEADING spaces from each row passed, because no fixture began with one --
        // and a leading space is an Outside cell that positions everything after it.
        [Test]
        public void LeadingSpacesArePreservedAsOutsideCells()
        {
            AsciiRoomMap map = Parse(" #", 2, 1);

            Assert.AreEqual(AsciiCell.Outside, map[0, 0], "A leading space was trimmed away.");
            Assert.AreEqual(AsciiCell.Wall, map[1, 0], "Trimming shifted the row left.");
        }

        // Tabs and nonbreaking spaces used to pass as surplus padding because the check used
        // Trim(), which strips every Unicode whitespace. Only the ASCII space is Outside here.
        [Test]
        public void TabsAndNonBreakingSpacesAreNotAcceptedAsPadding()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("#.#\t", 3, 1, out _, out string tab),
                "A tab past the declared width is not an Outside cell.");
            StringAssert.Contains("column 4", tab);

            Assert.IsFalse(AsciiRoomMap.TryParse("#.#\u00A0", 3, 1, out _, out _),
                "A nonbreaking space past the declared width is not an Outside cell.");

            Assert.IsTrue(AsciiRoomMap.TryParse("#.#  ", 3, 1, out _, out _),
                "Plain ASCII spaces must still be accepted as padding.");
        }

        // Accepting zero declared ROWS passed: the existing case used a negative height and a
        // zero width, never a zero height.
        [Test]
        public void ZeroDeclaredRowsIsRejectedAsWellAsZeroColumns()
        {
            Assert.IsFalse(AsciiRoomMap.TryParse("###", 3, 0, out _, out string rows));
            StringAssert.Contains("positive", rows);
            Assert.IsFalse(AsciiRoomMap.TryParse("###", 0, 3, out _, out string columns));
            StringAssert.Contains("positive", columns);
        }
    }
}
