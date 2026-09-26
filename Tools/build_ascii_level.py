"""Generate the ASCII map of the ACTUAL level, from the authoritative *Layout.cs bounds.

Vincent, 2026-09-26: "Okay so i would do for step 1, is rebuild our scene in ascii." / "We need a
ascii map of our level."

WHY GENERATED FROM THE LAYOUTS AND NOT DRAWN BY HAND. Three ASCII floorplan drafts already exist at
C:/nscrev/reports/handoffs/DOC-20260923-nsc-floorplan-*.txt, but they are DRAFTS of a proposed floor.
This is the level that actually exists on main: every bound and every door centre below is read from
Scripts/World/Rooms/*Layout.cs, so the map and the game agree by construction rather than by
someone's eye.

THE GRID CONTRACT IS AsciiRoomMap'S, NOT A NEW ONE:
    '#' Wall, '.' Floor, '+' Opening, ' ' Outside      (AsciiRoomMap.WallGlyph etc.)
    WorldUnitsPerCell = 2                              (its own constant)
    row 0 is the FIRST line and maps to the HIGHEST world z, because a map reads top-down and
    world z increases northward. Its ToCell is floor((originZ - worldZ) / 2), which this inverts
    exactly: cell (col,row) has centre X = originX + col*2 + 1, Z = originZ - row*2 - 1.
    Getting that backwards mirrors the level and every room still looks plausible - its own warning.
"""
import os

CELL = 2.0  # AsciiRoomMap.WorldUnitsPerCell

# Every figure below is quoted from Scripts/World/Rooms/<Room>Layout.cs on main.
ROOMS = [
    # name,            minX,   maxX,   minZ,   maxZ,   source
    ("RuinedEntry",   -14.0,  14.0, -26.0,   0.0, "RuinedEntryLayout Minimum/MaximumX,Z"),
    ("BoneArchive",   -12.0,  12.0,   0.0,  20.0, "BoneArchiveLayout RoomBounds centre(0,10) size(24,20)"),
    ("ChapelOfAsh",   -18.0,  18.0,  20.0,  54.0, "ChapelOfAshLayout Minimum/MaximumX,Z"),
    ("LowerVault",    -20.0,  20.0,  54.0,  76.0, "LowerVaultLayout Minimum/MaximumX,Z"),
    ("FinalRoom",     -15.0,  15.0,  76.0, 104.0, "FinalRoomLayout MinimumX/MaximumX, D4Z..D4Z+28"),
]

# Door centres. Width 3.0 in every room (DoorOpeningWidth / DoorWidth / DoorWidth / DoorWidth / DoorOpeningWidth).
DOORS = [
    ("D1",  0.0,   0.0, 3.0, "RuinedEntryLayout DoorCenterX/Z; BoneArchiveLayout D1"),
    ("D2",  6.0,  20.0, 3.0, "BoneArchiveLayout D2; ChapelOfAshLayout D2"),
    ("D3", -8.0,  54.0, 3.0, "ChapelOfAshLayout D3; LowerVaultLayout D3"),
    ("D4",  4.0,  76.0, 3.0, "LowerVaultLayout D4; FinalRoomLayout D4"),
    ("D5",  0.0, 104.0, 3.0, "FinalRoomLayout D5"),
]

ORIGIN_X = min(r[1] for r in ROOMS)          # -20
MAX_X = max(r[2] for r in ROOMS)             #  20
MIN_Z = min(r[3] for r in ROOMS)             # -26
ORIGIN_Z = max(r[4] for r in ROOMS)          # 104

COLS = int(round((MAX_X - ORIGIN_X) / CELL))
ROWS = int(round((ORIGIN_Z - MIN_Z) / CELL))

WALL, FLOOR, OPENING, OUTSIDE = "#", ".", "+", " "

grid = [[OUTSIDE for _ in range(COLS)] for _ in range(ROWS)]


def cell_center(col, row):
    return (ORIGIN_X + col * CELL + CELL / 2.0,
            ORIGIN_Z - row * CELL - CELL / 2.0)


def col_row_rect(minx, maxx, minz, maxz):
    """Inclusive cell rectangle whose CENTRES fall inside the world rect."""
    cols = [c for c in range(COLS) if minx <= cell_center(c, 0)[0] <= maxx]
    rows = [r for r in range(ROWS) if minz <= cell_center(0, r)[1] <= maxz]
    return cols, rows


# ---- 1. lay every room down as a bordered rectangle -------------------------
placed = []
for name, minx, maxx, minz, maxz, src in ROOMS:
    cols, rows = col_row_rect(minx, maxx, minz, maxz)
    if not cols or not rows:
        raise SystemExit("room %s produced no cells" % name)
    c0, c1, r0, r1 = cols[0], cols[-1], rows[0], rows[-1]
    for r in rows:
        for c in cols:
            edge = (c == c0 or c == c1 or r == r0 or r == r1)
            # A shared boundary row already written as Wall by the neighbour stays Wall.
            if edge:
                grid[r][c] = WALL
            elif grid[r][c] != WALL:
                grid[r][c] = FLOOR
    placed.append((name, c0, c1, r0, r1, len(cols), len(rows), src))

# ---- 2. punch the doors ------------------------------------------------------
door_cells = []
for name, dx, dz, width, src in DOORS:
    half = width / 2.0
    cols = [c for c in range(COLS)
            if dx - half <= cell_center(c, 0)[0] <= dx + half]
    # PUNCH EVERY WALL ROW THE BOUNDARY TOUCHES, NOT JUST THE NEAREST ONE.
    #
    # The first version took the single nearest row and produced a LEVEL THAT IS NOT CONNECTED.
    # Adjacent rooms abut exactly (FinalRoom minZ 76 == LowerVault maxZ 76), so each boundary has
    # TWO wall rows - one per room, at cell centres z=77 and z=75. Punching one leaves a door
    # opening into the neighbour's solid wall. It looked completely plausible in the rendered map,
    # which is exactly why the flood fill below exists rather than an eyeball.
    rows_at = [r for r in range(ROWS) if abs(cell_center(0, r)[1] - dz) <= CELL]
    if not cols or not rows_at:
        raise SystemExit("door %s produced no cells" % name)
    punched = []
    for r in rows_at:
        for c in cols:
            if grid[r][c] == WALL:
                grid[r][c] = OPENING
                punched.append((r, c))
    door_cells.append((name, dx, dz, sorted(set(r for r, _ in punched)), cols, src))

text = "\n".join("".join(row).rstrip() for row in grid)

# ---- 3. report ---------------------------------------------------------------
print("GRID: %d columns x %d rows   (world X %.0f..%.0f, Z %.0f..%.0f at %.0f units/cell)"
      % (COLS, ROWS, ORIGIN_X, MAX_X, MIN_Z, ORIGIN_Z, CELL))
print("origin for AsciiRoomMap.ToCell: originX=%.0f originZ=%.0f" % (ORIGIN_X, ORIGIN_Z))
print("")
print("%-13s %-13s %-13s %-9s %s" % ("room", "cols", "rows", "cells", "source"))
for name, c0, c1, r0, r1, nc, nr, src in placed:
    print("%-13s %-13s %-13s %-9s %s"
          % (name, "%d..%d" % (c0, c1), "%d..%d" % (r0, r1), "%dx%d" % (nc, nr), src))
print("")
for name, dx, dz, rows_p, cols, src in door_cells:
    print("%-4s world(%.0f,%.0f) -> rows %-9s cols %-8s %s"
          % (name, dx, dz, ",".join(str(r) for r in rows_p),
             ",".join(str(c) for c in cols), src))

counts = {WALL: 0, FLOOR: 0, OPENING: 0, OUTSIDE: 0}
for row in grid:
    for ch in row:
        counts[ch] += 1
print("")
print("cells: wall=%d floor=%d opening=%d outside=%d   total=%d (expected %d)"
      % (counts[WALL], counts[FLOOR], counts[OPENING], counts[OUTSIDE],
         sum(counts.values()), COLS * ROWS))
print("walkable (floor+opening) = %d" % (counts[FLOOR] + counts[OPENING]))
print("")
# ---- CONNECTIVITY: the check an eyeball cannot do ---------------------------
# Flood fill from the player spawn. If every room is not reached, the level is not walkable and the
# map is wrong however convincing it looks.
SPAWN_X, SPAWN_Z = 0.0, -22.0   # RuinedEntryLayout PlayerStart neighbourhood, inside the first room
scol = int((SPAWN_X - ORIGIN_X) // CELL)
srow = int((ORIGIN_Z - SPAWN_Z) // CELL)
assert grid[srow][scol] in (FLOOR, OPENING),     "spawn cell (%d,%d) is '%s', not walkable" % (scol, srow, grid[srow][scol])

seen = set()
stack = [(scol, srow)]
while stack:
    c, r = stack.pop()
    if (c, r) in seen:
        continue
    if c < 0 or c >= COLS or r < 0 or r >= ROWS:
        continue
    if grid[r][c] not in (FLOOR, OPENING):
        continue
    seen.add((c, r))
    stack.extend([(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)])

walkable_total = counts[FLOOR] + counts[OPENING]
print("")
print("CONNECTIVITY from spawn cell (%d,%d): reached %d of %d walkable cells"
      % (scol, srow, len(seen), walkable_total))
unreached = walkable_total - len(seen)
per_room = []
for name, c0, c1, r0, r1, nc, nr, src in placed:
    inside = sum(1 for (c, r) in seen if c0 <= c <= c1 and r0 <= r <= r1)
    total = sum(1 for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
                if grid[r][c] in (FLOOR, OPENING))
    per_room.append((name, inside, total))
    print("  %-13s reached %4d of %4d walkable   %s"
          % (name, inside, total, "OK" if inside == total else "*** NOT REACHED ***"))
if unreached != 0 or any(i != t for _, i, t in per_room):
    print("")
    print("LEVEL IS NOT CONNECTED. %d walkable cell(s) unreachable from spawn." % unreached)
    raise SystemExit(1)
print("  ALL FIVE ROOMS REACHABLE FROM SPAWN.")

print("")
print("=" * COLS)
print(text)
print("=" * COLS)

# THE CLONE, NEVER CANONICAL. Writing under C:/NSC/NSC/NoSafeCircle dirties the canonical
# tree, and a dirty canonical blocks every merge and decompose for the whole fleet.
out = "C:/nscrev/doormeta/Assets/NoSafeCircle/DoorPrototype/Content/Levels"
os.makedirs(out, exist_ok=True)
p = os.path.join(out, "floor01.txt")
with open(p, "wb") as f:
    f.write(text.encode("ascii") + b"\n")
print("")
print("wrote %s  (%d bytes, LF)" % (p, os.path.getsize(p)))
