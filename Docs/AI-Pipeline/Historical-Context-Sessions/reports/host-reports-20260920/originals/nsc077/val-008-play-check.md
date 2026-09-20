# NSC-077 in-game check (VAL-008) for Vincent

## What to open
- Unity 6000.1.8f1, project `C:\nscrev\branch-verify`.
  - It sits at the exact candidate commit `74c1923e8`: the NSC-077 code `6b0d255dc` on main `7698abac0`, plus its builder output.
  - Verified: two builds (185 non-scene generated files byte-identical), Edit Mode 65/65, Play Mode 107/107 twice.
  - Close any other Unity on that folder first.
- Scene: `Assets/Scenes/DoorPrototype.unity`. Press Play.

## Which enemies to use
- **Dungeon Brute (MeleeEnemy):** the Chapel of Ash one at world (7, 0, 31). It has a clear spawn.
- **Lantern Wraith:** the Bone Archive one at world (7, 0, 13). It has a clear sight line.
- Avoid three enemies whose spawns overlap room colliders (a separate fix is queued):
  - the Bone Archive brute (inside Shelf A);
  - the Chapel of Ash wraith (inside a column);
  - the Lower Vault brute (edge of a low wall).

## What to confirm
1. Both enemies show their approved art in all eight facings.
   - The Dungeon Brute has exactly one cleaver, including when facing north-east.
   - The lantern is visible on the wraith.
2. An enemy moving up the screen shows its back.
3. The walk plays only while an enemy moves. The idle plays when it stops, and it keeps its last facing.
4. Feet stay on the floor with no jump between idle and walk, including when the south walk loop restarts.
5. The Lantern Wraith turns toward you and throws teal lantern wisps, not fireballs.
6. Sprites face the camera without leaning or thinning while enemies turn.
7. Sorting against walls, doors and the wizard is correct.
8. Size: each enemy looks right in its 2x2-unit box. The wizard may still use its older art until its 128x128 remake lands.

Pixel density is settled at 64 PPU. Any leftover sprite shimmer is a note for the Art Director, not a reason to reject.

## Reply
- "approve 74c1923e8", or
- what's wrong (which enemy, which facing), and a screenshot if you can.
