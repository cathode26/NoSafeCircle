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
    /// Five room builders hand-author 2,502 lines of C# geometry between them, and a sixth costs
    /// another few hundred. This is the input side of making that a text file instead.
    /// <para>
    /// THE PARSER DOES NOT ASSUME THE FILE IS THE GRID, and that is not defensive programming --
    /// it is what the real artifact looks like. DOC-20260923-nsc-floorplan-spine.txt is 81 lines:
    /// a 72x72 map followed by a prose summary. Reading the whole file as a grid yields 81 rows,
    /// 92 columns and 2,017 floor cells against a true 72, 72 and 2,016, and every one of those
    /// wrong numbers looks like a plausible map. So parsing stops at the first line that is not
    /// map-shaped, and the caller is told how many rows were consumed.
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

        private AsciiRoomMap(AsciiCell[,] cells, int rowsConsumed)
        {
            this.cells = cells;
            RowsConsumed = rowsConsumed;
        }

        /// <summary>Columns in the parsed grid.</summary>
        public int Width => cells.GetLength(0);

        /// <summary>Rows in the parsed grid.</summary>
        public int Height => cells.GetLength(1);

        /// <summary>How many source lines were map-shaped. Less than the file's line count when
        /// the file carries a prose tail, which the real floorplan artifacts do.</summary>
        public int RowsConsumed { get; }

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

        /// <summary>Every walkable cell, so a caller can count them without walking the grid.</summary>
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

        /// <summary>Parses map text, stopping at the first line that is not map-shaped.</summary>
        /// <param name="text">The source text. Accepts CRLF or LF.</param>
        /// <param name="map">The parsed grid, or null.</param>
        /// <param name="error">Why parsing failed, or null.</param>
        /// <remarks>
        /// A line is map-shaped when every character is one of the four glyphs. The first line
        /// that is not ends the map; anything after it is the caller's prose and is ignored.
        /// Trailing blank lines before the prose are NOT treated as map rows, because a blank
        /// line is indistinguishable from a row of Outside and silently adding empty rows would
        /// shift every world coordinate below it.
        /// </remarks>
        public static bool TryParse(string text, out AsciiRoomMap map, out string error)
        {
            map = null;
            if (text == null)
            {
                error = "Map text was null.";
                return false;
            }

            string[] lines = text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
            var mapLines = new List<string>();
            foreach (string line in lines)
            {
                if (!IsMapShaped(line))
                {
                    break;
                }
                mapLines.Add(line);
            }

            // NO BLANK-LINE STRIPPING AT EITHER END, and that is a decision rather than an
            // omission. A blank line is all spaces and therefore map-shaped, so it is
            // indistinguishable from a margin row inside the declared bound -- and margin rows
            // are real: the bound is 72x72 while the geometry spans 70.
            //
            // Every stripping rule I measured against DOC-20260923-nsc-floorplan-spine.txt
            // produced a DIFFERENT wrong answer: strip both ends -> 69 rows, strip the tail
            // only -> 70, strip nothing -> 73, declared bound -> 72. The file cannot yield its
            // own bound, because how many of its blank rows are margin is not written in it.
            //
            // So this reports exactly the map-shaped region and guesses nothing. A caller that
            // knows the bound asserts it with RequireBound; a caller that infers one from
            // whatever the file happens to contain will be wrong in a way that still looks like
            // a map.
            if (mapLines.Count == 0)
            {
                error = "Map text contained no map-shaped lines. Valid glyphs are '" +
                        WallGlyph + "', '" + FloorGlyph + "', '" + OpeningGlyph + "' and space.";
                return false;
            }

            int width = 0;
            foreach (string line in mapLines)
            {
                // RAW length, not trimmed. The map is padded with trailing spaces out to its
                // bound, and trimming narrows the grid to the widest row that happens to hold
                // geometry -- 63 columns against a declared 72 on the real artifact. Those
                // trailing spaces are Outside cells INSIDE the bound, not absent ones.
                width = Math.Max(width, line.Length);
            }

            if (width == 0)
            {
                error = "Map text had rows but no content.";
                return false;
            }

            var parsed = new AsciiCell[width, mapLines.Count];
            for (int row = 0; row < mapLines.Count; row++)
            {
                string line = mapLines[row];
                for (int column = 0; column < width; column++)
                {
                    char glyph = column < line.Length ? line[column] : OutsideGlyph;
                    parsed[column, row] = Classify(glyph);
                }
            }

            map = new AsciiRoomMap(parsed, mapLines.Count);
            error = null;
            return true;
        }

        /// <summary>Checks the parsed grid against a bound the CALLER knows, not one inferred.</summary>
        /// <remarks>
        /// The parser deliberately cannot work out its own bound -- see TryParse. This is how a
        /// caller states the one it was designed to: the map must FIT inside the bound and may
        /// be smaller, because blank margin rows and columns are part of the bound and are not
        /// distinguishable from absence in the text.
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

        /// <summary>The world-space centre of a cell, given the map's world origin.</summary>
        /// <remarks>
        /// Row 0 is the map's FIRST line and maps to the HIGHEST world z, because a map reads
        /// top-down on screen and world z increases northward. Getting this backwards mirrors the
        /// level and every room still looks plausible, so it is stated here rather than inferred
        /// at each call site.
        /// </remarks>
        public AsciiCellIndex ToCell(float worldX, float worldZ, float originX, float originZ)
        {
            int column = (int)Math.Floor((worldX - originX) / WorldUnitsPerCell);
            int row = (int)Math.Floor((originZ - worldZ) / WorldUnitsPerCell);
            return new AsciiCellIndex(column, row);
        }

        private static bool IsMapShaped(string line)
        {
            foreach (char glyph in line)
            {
                if (glyph != WallGlyph && glyph != FloorGlyph &&
                    glyph != OpeningGlyph && glyph != OutsideGlyph)
                {
                    return false;
                }
            }
            return true;
        }

        private static AsciiCell Classify(char glyph)
        {
            switch (glyph)
            {
                case WallGlyph: return AsciiCell.Wall;
                case FloorGlyph: return AsciiCell.Floor;
                case OpeningGlyph: return AsciiCell.Opening;
                default: return AsciiCell.Outside;
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

    /// <summary>A column and row pair. Deliberately not UnityEngine.AsciiCellIndex so the parser
    /// stays free of UnityEngine and can be exercised without an Editor.</summary>
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
