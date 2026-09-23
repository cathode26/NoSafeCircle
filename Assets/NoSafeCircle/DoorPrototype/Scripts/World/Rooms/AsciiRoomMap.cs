using System;
using System.Collections.Generic;
using System.Text;

namespace NoSafeCircle.DoorPrototype.World.Rooms
{
    /// <summary>What a single ASCII cell means.</summary>
    public enum AsciiCell
    {
        /// <summary>Outside the level. Space in the source text.</summary>
        Outside,
        /// <summary>Solid wall. '#'.</summary>
        Wall,
        /// <summary>Walkable floor. '.'.</summary>
        Floor,
        /// <summary>A gap in a wall run that stays walkable. '+'.</summary>
        Opening
    }

    /// <summary>A parsed ASCII floor map: a rectangular grid of cells and nothing more.</summary>
    /// <remarks>
    /// Five room builders hand-author 2,502 lines of C# geometry between them and a sixth costs
    /// another few hundred. This is the input side of making that a text file instead.
    /// <para>
    /// THE CALLER DECLARES THE GRID. That is the whole design, and two audit rounds were needed to
    /// arrive at it. The parser previously INFERRED its dimensions from whatever the text
    /// contained, and every rule for doing so was wrong in a different way. Measured against
    /// DOC-20260923-nsc-floorplan-spine.txt, whose declared bound is 72x72:
    /// </para>
    /// <code>
    ///   read the file as a grid   81 rows, 92 cols, 2,017 floor   all three wrong
    ///   strip blanks both ends    69 rows
    ///   strip the trailing only   70 rows
    ///   strip nothing             73 rows, 72 cols, 2,016 walkable
    /// </code>
    /// <para>
    /// The file is a map plus a prose tail, padded with trailing spaces and carrying blank margin
    /// rows, and HOW MANY OF THOSE BLANKS ARE MARGIN IS NOT WRITTEN IN IT. A later attempt to
    /// separate map from prose by "a tail is terminal" -- corruption resumes, prose does not --
    /// failed in both directions: "###/#.#/#x#" returned a clean 3x2 map because the damaged row
    /// was last, and legitimate prose ending in "..." was rejected because "..." is map-shaped.
    /// </para>
    /// <para>
    /// With declared dimensions all of that disappears. A short row is unambiguously padded to the
    /// declared width with Outside; a missing row is premature end of map; an unknown glyph inside
    /// the declared region is an error rather than a terminator. Ambiguity was never in the text,
    /// it was in asking the text a question it could not answer.
    /// </para>
    /// <para>
    /// ONE CELL IS TWO WORLD UNITS (<see cref="WorldUnitsPerCell"/>), from the scale decision of
    /// 2026-09-23: agentRadius 0.5 gives a 1.0-unit player, and a 1-unit cell would leave no
    /// clearance either side of a walking agent.
    /// </para>
    /// </remarks>
    public sealed class AsciiRoomMap
    {
        /// <summary>World units spanned by one ASCII cell on each axis.</summary>
        public const float WorldUnitsPerCell = 2f;

        public const char WallGlyph = '#';
        public const char FloorGlyph = '.';
        public const char OpeningGlyph = '+';
        public const char OutsideGlyph = ' ';

        private readonly AsciiCell[,] cells;

        private AsciiRoomMap(AsciiCell[,] cells, int rowsConsumed, int paddedRowCount)
        {
            this.cells = cells;
            RowsConsumed = rowsConsumed;
            PaddedRowCount = paddedRowCount;
        }

        /// <summary>Columns in the grid. Always the declared width.</summary>
        public int Width => cells.GetLength(0);

        /// <summary>Rows in the grid. Always the declared height.</summary>
        public int Height => cells.GetLength(1);

        /// <summary>How many source lines were consumed. Equals <see cref="Height"/>.</summary>
        public int RowsConsumed { get; }

        /// <summary>Source rows shorter than the declared width, padded out with Outside.</summary>
        /// <remarks>
        /// Includes blank rows, which an earlier version excluded -- so "###\n\n###" became a
        /// 3x3 grid reporting ZERO padded rows and passed every check while inventing three
        /// cells. A blank row is the MOST padded row there is.
        /// </remarks>
        public int PaddedRowCount { get; }

        /// <summary>Cell at a column and row, row 0 being the FIRST line of the map text.</summary>
        public AsciiCell this[int column, int row] => cells[column, row];

        /// <summary>True when the cell is walkable: floor or an opening.</summary>
        public bool IsWalkable(int column, int row)
        {
            if (column < 0 || column >= Width || row < 0 || row >= Height)
            {
                return false;
            }

            AsciiCell cell = cells[column, row];
            return cell == AsciiCell.Floor || cell == AsciiCell.Opening;
        }

        /// <summary>Counts walkable cells: floor plus openings.</summary>
        public int WalkableCellCount()
        {
            int count = 0;
            for (int column = 0; column < Width; column++)
            {
                for (int row = 0; row < Height; row++)
                {
                    if (IsWalkable(column, row))
                    {
                        count++;
                    }
                }
            }
            return count;
        }

        /// <summary>Parses exactly <paramref name="columns"/> by <paramref name="rows"/> cells.</summary>
        /// <param name="text">The source text. Accepts CRLF or LF.</param>
        /// <param name="columns">The declared grid width. The caller knows it; the text does not.</param>
        /// <param name="rows">The declared grid height.</param>
        /// <param name="map">The parsed grid, or null.</param>
        /// <param name="error">Why parsing failed, or null.</param>
        /// <remarks>
        /// Everything after the declared rows is ignored, so a prose tail needs no detection and
        /// no heuristic. Inside the declared region an unrecognised character is an ERROR: it can
        /// no longer end the map early, which is how a damaged final row previously produced a
        /// smaller map that passed every validator with a walkable count matching the intact one.
        /// </remarks>
        public static bool TryParse(
            string text, int columns, int rows, out AsciiRoomMap map, out string error)
        {
            map = null;

            if (text == null)
            {
                error = "Map text was null.";
                return false;
            }
            if (columns <= 0 || rows <= 0)
            {
                error = "Declared grid must be positive; got " + columns + "x" + rows + ".";
                return false;
            }

            string normalized = text.Replace("\r\n", "\n").Replace('\r', '\n');

            // A file-final newline is a split artifact, not a row. Without this the same physical
            // map parsed as N or N+1 rows depending only on the author's editor.
            // EMPTY INPUT IS ZERO PHYSICAL LINES, NOT ONE BLANK ROW. "".Split() yields a
            // single empty element, so TryParse("", 3, 1) used to SUCCEED with a 3x1 Outside
            // grid -- inventing a row out of nothing, while the premature-EOF rule that exists
            // to prevent exactly that reported no problem.
            var source = normalized.Length == 0
                ? new List<string>()
                : new List<string>(normalized.Split('\n'));
            if (source.Count > 0 && source[source.Count - 1].Length == 0 &&
                normalized.EndsWith("\n", StringComparison.Ordinal))
            {
                source.RemoveAt(source.Count - 1);
            }

            if (source.Count < rows)
            {
                error = "Declared " + rows + " rows but the text has only " + source.Count +
                        " line(s). Premature end of map.";
                return false;
            }

            var parsed = new AsciiCell[columns, rows];
            int padded = 0;
            for (int row = 0; row < rows; row++)
            {
                string line = source[row];

                if (line.Length > columns)
                {
                    // Trailing spaces beyond the declared width are harmless padding; anything
                    // else means the row really is wider than the caller declared.
                    // CHECKED AGAINST THE GLYPH, NOT Trim(). Trim() strips tabs, nonbreaking
                    // spaces and every other Unicode whitespace, so "#.#<tab>" and
                    // "#.#<nbsp>" parsed as clean 3x1 maps reporting zero padding. Only the
                    // ASCII space this grammar defines as Outside is surplus padding.
                    int offending = -1;
                    for (int extra = columns; extra < line.Length; extra++)
                    {
                        if (line[extra] != OutsideGlyph)
                        {
                            offending = extra;
                            break;
                        }
                    }

                    if (offending >= 0)
                    {
                        error = "Row " + (row + 1) + " has content at column " + (offending + 1) +
                                " but the declared grid is " + columns + " wide.";
                        return false;
                    }
                    line = line.Substring(0, columns);
                }

                if (line.Length < columns)
                {
                    padded++;
                }

                for (int column = 0; column < columns; column++)
                {
                    if (column >= line.Length)
                    {
                        parsed[column, row] = AsciiCell.Outside;
                        continue;
                    }

                    char glyph = line[column];
                    if (!TryClassify(glyph, out AsciiCell cell))
                    {
                        error = "Unrecognised character '" + glyph + "' at row " + (row + 1) +
                                ", column " + (column + 1) + ". Valid glyphs are '" + WallGlyph +
                                "', '" + FloorGlyph + "', '" + OpeningGlyph + "' and space.";
                        return false;
                    }
                    parsed[column, row] = cell;
                }
            }

            map = new AsciiRoomMap(parsed, rows, padded);
            error = null;
            return true;
        }

        /// <summary>Fails when any source row was shorter than the declared width.</summary>
        /// <remarks>
        /// Padding is accepted by <see cref="TryParse"/> because editors strip trailing whitespace
        /// and the real artifact pads out to its bound. A caller authoring a map by hand, where
        /// every cell should be written explicitly, asserts the stricter rule here.
        /// </remarks>
        public bool RequireEveryRowWritten(out string error)
        {
            if (PaddedRowCount > 0)
            {
                error = PaddedRowCount + " row(s) were shorter than the declared " + Width +
                        " columns and were padded with Outside cells. Blank rows count: an empty " +
                        "row is entirely invented. Write those cells explicitly if they are meant " +
                        "to be Outside.";
                return false;
            }

            error = null;
            return true;
        }

        /// <summary>Checks the grid fits a bound. A maximum-size check, not a source-extent one.</summary>
        /// <remarks>
        /// This cannot establish where the source map ends -- <see cref="TryParse"/>'s declared
        /// dimensions do that. It only answers whether the grid fits the world budget.
        /// </remarks>
        public bool RequireBound(int boundColumns, int boundRows, out string error)
        {
            if (Width > boundColumns || Height > boundRows)
            {
                error = "Map is " + Width + "x" + Height + " cells, which does not fit the " +
                        boundColumns + "x" + boundRows + " bound (" +
                        (boundColumns * WorldUnitsPerCell) + "x" + (boundRows * WorldUnitsPerCell) +
                        " world units).";
                return false;
            }

            error = null;
            return true;
        }

        /// <summary>The cell containing a world position, given the map's world origin.</summary>
        /// <remarks>
        /// Row 0 is the map's FIRST line and maps to the HIGHEST world z, because a map reads
        /// top-down on screen and world z increases northward. Getting this backwards mirrors the
        /// level and every room still looks plausible.
        /// <para>
        /// Flooring rather than truncation, so a position half a cell west of the origin lands in
        /// column -1 rather than column 0. Truncation puts the two cells either side of the origin
        /// into the same one.
        /// </para>
        /// </remarks>
        public AsciiCellIndex ToCell(float worldX, float worldZ, float originX, float originZ)
        {
            int column = (int)Math.Floor((worldX - originX) / WorldUnitsPerCell);
            int row = (int)Math.Floor((originZ - worldZ) / WorldUnitsPerCell);
            return new AsciiCellIndex(column, row);
        }

        private static bool TryClassify(char glyph, out AsciiCell cell)
        {
            switch (glyph)
            {
                case WallGlyph: cell = AsciiCell.Wall; return true;
                case FloorGlyph: cell = AsciiCell.Floor; return true;
                case OpeningGlyph: cell = AsciiCell.Opening; return true;
                case OutsideGlyph: cell = AsciiCell.Outside; return true;
                default: cell = AsciiCell.Outside; return false;
            }
        }

        /// <summary>Renders the grid back to text, so a round trip can be asserted.</summary>
        public override string ToString()
        {
            var builder = new StringBuilder();
            for (int row = 0; row < Height; row++)
            {
                for (int column = 0; column < Width; column++)
                {
                    switch (cells[column, row])
                    {
                        case AsciiCell.Wall: builder.Append(WallGlyph); break;
                        case AsciiCell.Floor: builder.Append(FloorGlyph); break;
                        case AsciiCell.Opening: builder.Append(OpeningGlyph); break;
                        default: builder.Append(OutsideGlyph); break;
                    }
                }
                if (row < Height - 1)
                {
                    builder.Append('\n');
                }
            }
            return builder.ToString();
        }
    }

    /// <summary>A column and row pair, free of UnityEngine so the parser can be exercised
    /// without an Editor.</summary>
    /// <remarks>
    /// NOT called Vector2Int. UnityEngine.Vector2Int exists, and a same-named type in a namespace
    /// that room code imports alongside UnityEngine makes every use of the name ambiguous in files
    /// importing both -- a compile break in code that never mentioned this type.
    /// </remarks>
    public readonly struct AsciiCellIndex : IEquatable<AsciiCellIndex>
    {
        public readonly int Column;
        public readonly int Row;

        public AsciiCellIndex(int column, int row)
        {
            Column = column;
            Row = row;
        }

        public bool Equals(AsciiCellIndex other) => Column == other.Column && Row == other.Row;
        public override bool Equals(object obj) => obj is AsciiCellIndex other && Equals(other);
        public override int GetHashCode() => (Column * 397) ^ Row;
        public override string ToString() => "(" + Column + ", " + Row + ")";
    }
}
