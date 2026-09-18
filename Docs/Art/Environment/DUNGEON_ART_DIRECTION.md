# No Safe Circle Dungeon Art Direction

## Core feeling

Fuse Ultima Online's lived-in isometric world with Diablo's dramatic gothic
dungeon language. The world should feel handmade, dense, explorable, dangerous,
and occasionally charming or funny. It must remain original and must not copy
source-game assets, layouts, textures, icons, or characters.

## Reference principles

**Ultima Online:** recognizable props at gameplay scale; curated clutter;
modular floors, walls, corners, stairs, bridges, doors, and roof edges; branching
exploration; and clear walking routes through visually dense places.

**Diablo:** strong gothic silhouettes; arches, gates, pillars, bone motifs, and
ritual geometry; memorable landmarks; contrast between safe floor and hazards;
layered elevation; framed thresholds; and restrained colored light guiding the
eye.

**No Safe Circle:** dark-but-cute horror comedy. Exaggerate readable proportions
for characters, doors, furniture, candles, and enemies. Put human or cozy clutter
beside supernatural corruption, and offset a frightening focus with one odd,
playful, or endearing detail.

## Composition and implementation rules

- Every room has one unmistakable focal landmark, at least two supporting prop
  clusters, and a readable primary route.
- Concentrate clutter at walls, corners, alcoves, and focal areas. Protect door
  approaches and movement lanes.
- Vary density deliberately: alternate crowded exploratory rooms with sparse
  ceremonial or encounter chambers.
- Use floor variation, trails, lighting pools, elevation, and architectural
  rhythm to guide the player.
- Hazards such as lava, slime, corrupted ground, and chasms must shape readable
  safe islands and crossing routes, or remain clearly non-walkable background;
  they cannot be flat decoration that obscures traversal.
- Use selective symmetry only for ritual rooms and major encounters. Exploration
  spaces should remain irregular.
- Preserve isometric pivots, sorting anchors, door apertures, camera-scale
  readability, and deterministic tile alignment. Decorative props may omit
  collision; major furniture and route-shaping objects need intentional collision.
- The fixed isometric camera follows the wizard, so a room may be larger than one
  screen. Review rooms with several gameplay-camera shots rather than one framing.
- Near (south and east, camera-facing) walls use a low cutaway stub, initially about
  0.5 world units high and tuned during gameplay-camera review, so they never hide
  the wizard, floor routes, or cursor targets. Far (north and west) walls keep full
  visual height, door frames stay readable, and gameplay colliders keep full height.
- Each room uses an Isometric Tilemap for its walls. Wall tiles may differ per room,
  and each room's blockout task owns its wall Tilemap.
- Use only original assets, palettes, shapes, and layouts. Reference material is
  mood and design language, never a source to copy or trace.

## First-wing room identities

- **Ruined Entry:** broken masonry, webs, vegetation or slime, debris, and an
  introductory landmark.
- **Bone Archive:** shelf banks, bone piles, collapsed furniture, archival
  clutter, and alternate readable lanes.
- **Chapel of Ash:** pews, altar or ritual focus, candles, ash accents, sigils,
  gothic vertical shapes, and selective symmetry.
- **Lower Vault:** water or slime channels, bridges or raised routes, barrels and
  crates, rails, cliffs, platforms, and an alternate route. **Art must not
  out-promise the geometry.** It never implies walkable ground, a safe island, a
  crossing or a change of elevation that the room's committed layout does not
  have. As of NSC-047 revision 4 the Lower Vault commits none of those, so a
  painted bridge, ledge or platform is scenery **until a task commits one with
  collision** - after which the art may depict it, because it states a fact
  rather than an implication. Lava, chasms and horn trim stay FutureExpansion
  vocabulary until a task owns them.
- **Final Room:** dramatic focal structure, recognizable benches and furniture,
  ritual details, candles, bounded hazard framing, and an open encounter area.

## Connecting and expanding the dungeon

Connect rooms with authored corridors, thresholds, junctions, and small
transition spaces. The first five rooms form one playable wing. Future work may
add constructed gothic wings, irregular cavern branches, infernal or corrupted
zones, side chambers, dead-end rewards, loops, elevation changes, and landmark
junctions.

Build clusters of small, medium, and large rooms joined mostly by short passages;
use only a few long corridors or central axes as orientation landmarks. Reconnect
branches into loops and shortcuts, vary footprints and outer silhouette, reveal
the dungeon incrementally at gameplay camera scale, and sequence landmarks so a
player can describe where they are: entrance wing, central set piece or hub,
branching middle, and distinct destination.
