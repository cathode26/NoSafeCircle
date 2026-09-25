# Enemy eight-direction attack source art - PixelLab generation record

Provenance for NSC-104. Written by the Art Director Agent, 2026-09-25.

**Every value here is read from the tool or measured from the committed frames. Where PixelLab
does not expose a value, this record says so rather than estimating it** - the convention
NSC-078 set for the same problem.

## The two characters, and no others

AC-001 and VAL-002 bind this task to exactly two already-selected characters. **No new
character was created by this run.**

    melee   Melee Candidate A - Dungeon Brute    3db4582d-8b48-4486-be1a-19d1a8c6b9d2
    ranged  Ranged Candidate B - Lantern Wraith  361131dd-8c48-4b99-8b81-c79bd30078dc

Both render at **180x180**, `low top-down`, 8 directions, matching their NSC-063 selection.

## Calls

One call per character animated all eight directions; PixelLab queues one job per direction.

### Melee Candidate A - Dungeon Brute - `cross-punch` template, `template` mode

    character_id  3db4582d-8b48-4486-be1a-19d1a8c6b9d2
    group_id      a83bd29c-55f0-4bc7-adf1-98b8e076e08c
    template      cross-punch
    mode          template
    directions    8 (south, south-east, east, north-east, north, north-west, west, south-west)
    frames        6 per direction, 48 total
    seed          not exposed by PixelLab metadata
    per-call cost not exposed by PixelLab metadata (see the aggregate below)

### Ranged Candidate B - Lantern Wraith - `fireball` template, `skeleton-v3` mode

    character_id  361131dd-8c48-4b99-8b81-c79bd30078dc
    group_id      f9d811d2-eb19-4aba-93d7-302d8ec79ba3
    template      fireball
    mode          skeleton-v3
    directions    8 (south, south-east, east, north-east, north, north-west, west, south-west)
    frames        6 per direction, 48 total
    seed          not exposed by PixelLab metadata
    per-call cost not exposed by PixelLab metadata (see the aggregate below)

## The rejected first ranged run, recorded so the totals reconcile

**The Lantern Wraith was generated TWICE.** The first run used `template` mode
(group `631b2359-243c-4789-aedd-5bfd99959dbd`) and **the Art Director rejected it and deleted
it.** Its generations are still spent and are included in the aggregate below; its frames are
NOT committed and it holds no group on the character any more.

**Why it was rejected, from the 8x6 contact sheet:**

1. **Identity drifted WITHIN a single direction** - south frames 0-2 carried a pink scarf and
   a green helm, frames 3-5 a plain dark hood. Not the same character frame to frame.
2. **South-west frames 0-1 were nearly empty** - the character reduced to a dot at the edge.
3. **The projectile rendered as an untextured white box** in several directions.

**The remedy is the one the tool documents:** `template` mode redraws the character each frame;
`skeleton-v3` moves it, for *"steadier identity and colours"*, at 2-4 generations per
direction and requiring a tier 1 subscription (this account is Tier 2).

## Cost, read from the tool - AND THE CONTRACT'S STATED MODEL IS WRONG

**AC-003 states TEMPLATE mode at 180 px is ONE generation per direction, so eight per enemy
and sixteen for both. Measured, it is not.**

    get_balance before, queue empty   1392 used   3607 remaining
    get_balance after,  queue empty   1454 used   3545 remaining
    total generations consumed        62

**The 16 template-mode directions alone consumed 38 generations (1392 -> 1430), about 2.4x the
stated model.** The remainder is the skeleton-v3 re-run, which the tool documents at 2-4
generations per direction rather than 1.

**This is AC-003's own instruction paying out:** it requires the cost to be *"read from the
tool rather than estimated"*, and an estimate against the stated model would have under-
reported by more than half.

## FINDING: these characters are NOT the ones the committed WALK art was made from

**Measured, and it is a cross-task conflict rather than a defect in this delivery.**
`Docs/Art/Enemies/PIXELLAB_WALK_GENERATION.md` names EIGHT character ids for NSC-093's walk
frames, and **neither of NSC-104's two bound ids appears among them.** Both of mine are named
in NSC-063's `PIXELLAB_GENERATION.md`, the selection record.

**The art shows it.** Side by side at true pixel scale, feet on a common baseline:
the walk melee is a dark-hooded figure with an amber face glow carrying a cleaver, while the
attack melee has a pale exposed face; the walk ranged is a purple-caped wraith with a magenta
face and a cyan-orb staff, while the attack ranged is a dark figure with a large teal mask and
no cape. **The enemies will change appearance when they attack.**

**THIS DELIVERY IS CORRECT AND THAT IS THE PROBLEM.** AC-001 binds this task to
`3db4582d-...` and `361131dd-...` *"and from no others"*, and VAL-002 asserts exactly those
two. Obeying the contract is what produces the mismatch; generating from the walk characters
would have violated it. **Resolving it is a contract question for GER, not a pick the Art
Director may make unilaterally.**

**Two proxies that are insensitive to a raised weapon, for whoever picks this up:** opaque
area walk 3875 -> attack 4689 (melee, +21%) and 3915 -> 4378 (ranged, +12%); lower-third
stance width 57 -> 44 (melee) and 75 -> 77 (ranged). **So the character is NOT dramatically
rescaled** - an early bbox-height reading suggested +41% and was wrong, because a raised
cleaver inflates the bounding box without the body growing.

## Pivot: the committed relationship preserved, not the committed number

The walk metas use `spritePivot {x: 0.5, y: 0.25}`. **That is not arbitrary: every committed
walk frame has exactly 44 transparent rows under the figure on a 176 canvas, and 44/176 =
0.25, so the pivot sits precisely on the feet.** Zero variance across all of them.

These canvases differ (melee 180, ranged 192 - PixelLab grows the canvas to fit the
silhouette), so copying 0.25 literally would put the pivot ABOVE the feet and the enemy would
float. **The pivot is therefore derived from the NEUTRAL pose (frame 00, before any projectile
exists) so the relationship is preserved:**

    melee   canvas 180   frame-00 feet gap median 23 px   spritePivot y = 0.1278
    ranged  canvas 192   frame-00 feet gap median 32 px   spritePivot y = 0.1667

**A first attempt anchored on the minimum gap across all 48 frames and was wrong** - the alpha
bbox includes the fireball and the spark particles, so a projectile reaching downward was being
read as the character's feet.

## Frame inventory - every committed frame, with its call

VAL-001 requires this in both directions: no committed frame without a recorded call, and no
recorded call without its committed frames. Generated from the landed files, not typed.

    file                               arch     dir    sha256 (first 16)
    enemy_melee_s_attack_00.png        melee    s      a83f060a200696bb
    enemy_melee_s_attack_01.png        melee    s      6a60ddc21405697d
    enemy_melee_s_attack_02.png        melee    s      2e1b28f903c47389
    enemy_melee_s_attack_03.png        melee    s      0bd87414c2dcd7aa
    enemy_melee_s_attack_04.png        melee    s      eaab51c4f26433c6
    enemy_melee_s_attack_05.png        melee    s      08271619e96eed07
    enemy_melee_se_attack_00.png       melee    se     726350d5c2f0d476
    enemy_melee_se_attack_01.png       melee    se     29c3fc53abceb64c
    enemy_melee_se_attack_02.png       melee    se     8321a47c54f210e1
    enemy_melee_se_attack_03.png       melee    se     c73113a79547f04d
    enemy_melee_se_attack_04.png       melee    se     6f66b385a0279f6b
    enemy_melee_se_attack_05.png       melee    se     ce0a4519f98b7074
    enemy_melee_e_attack_00.png        melee    e      2d3050d0734d06cc
    enemy_melee_e_attack_01.png        melee    e      516d8eb3c5af7693
    enemy_melee_e_attack_02.png        melee    e      b20d07635260d5e8
    enemy_melee_e_attack_03.png        melee    e      e275ed99a6e7990f
    enemy_melee_e_attack_04.png        melee    e      6b3dafa3e0913bf5
    enemy_melee_e_attack_05.png        melee    e      b5a2fcbe35d42878
    enemy_melee_ne_attack_00.png       melee    ne     b56a5f5b7065a648
    enemy_melee_ne_attack_01.png       melee    ne     1100dca40c436467
    enemy_melee_ne_attack_02.png       melee    ne     e2e3c3371d41c628
    enemy_melee_ne_attack_03.png       melee    ne     4e09cbf824af84f4
    enemy_melee_ne_attack_04.png       melee    ne     6c5f730846b15555
    enemy_melee_ne_attack_05.png       melee    ne     d3e3bc4c236a80dc
    enemy_melee_n_attack_00.png        melee    n      f71009b9c9c35c60
    enemy_melee_n_attack_01.png        melee    n      2fc3a8e1e06572b7
    enemy_melee_n_attack_02.png        melee    n      ac5475f7afb974ec
    enemy_melee_n_attack_03.png        melee    n      f91f697990e55195
    enemy_melee_n_attack_04.png        melee    n      e2820e3a5aac390e
    enemy_melee_n_attack_05.png        melee    n      a084a83aa95d748e
    enemy_melee_nw_attack_00.png       melee    nw     1b0ff8e74c86363a
    enemy_melee_nw_attack_01.png       melee    nw     71529e4783e02ddb
    enemy_melee_nw_attack_02.png       melee    nw     9b8743ad54ad3093
    enemy_melee_nw_attack_03.png       melee    nw     d4f4ca67912ee26d
    enemy_melee_nw_attack_04.png       melee    nw     1b541a85adb3918c
    enemy_melee_nw_attack_05.png       melee    nw     9ee47c66f4878569
    enemy_melee_w_attack_00.png        melee    w      bba9494c86c8b33c
    enemy_melee_w_attack_01.png        melee    w      3494804867c49042
    enemy_melee_w_attack_02.png        melee    w      08ed45c3bf3bafe5
    enemy_melee_w_attack_03.png        melee    w      b1704d8ca1223b9b
    enemy_melee_w_attack_04.png        melee    w      3a1954adf60055b4
    enemy_melee_w_attack_05.png        melee    w      dbac188e33fa2168
    enemy_melee_sw_attack_00.png       melee    sw     9e43b142b9ae1702
    enemy_melee_sw_attack_01.png       melee    sw     e3d08d53ae7a4ab1
    enemy_melee_sw_attack_02.png       melee    sw     faf56ca31baa4630
    enemy_melee_sw_attack_03.png       melee    sw     8fa409507fed18c6
    enemy_melee_sw_attack_04.png       melee    sw     218fa1fa6aff8fc9
    enemy_melee_sw_attack_05.png       melee    sw     c1f364a0d8020b8c
    enemy_ranged_s_attack_00.png       ranged   s      50a4a7676d9b5dcb
    enemy_ranged_s_attack_01.png       ranged   s      f3629153580a5c90
    enemy_ranged_s_attack_02.png       ranged   s      7b71c0f54933b30e
    enemy_ranged_s_attack_03.png       ranged   s      a1f87c5faee9047a
    enemy_ranged_s_attack_04.png       ranged   s      7f305c1c184d22d9
    enemy_ranged_s_attack_05.png       ranged   s      c69597c08a3146e9
    enemy_ranged_se_attack_00.png      ranged   se     f738f03bd00875f8
    enemy_ranged_se_attack_01.png      ranged   se     bffb83f0f4e89e9b
    enemy_ranged_se_attack_02.png      ranged   se     df16e0ec674bc993
    enemy_ranged_se_attack_03.png      ranged   se     7da882946176691f
    enemy_ranged_se_attack_04.png      ranged   se     1241736e9f814b5d
    enemy_ranged_se_attack_05.png      ranged   se     e1a5b5236fd0b45d
    enemy_ranged_e_attack_00.png       ranged   e      d249654260fba6da
    enemy_ranged_e_attack_01.png       ranged   e      1299f1527bdbb1cc
    enemy_ranged_e_attack_02.png       ranged   e      66ac4d77933f426d
    enemy_ranged_e_attack_03.png       ranged   e      9f9f0f4e55f3f626
    enemy_ranged_e_attack_04.png       ranged   e      98a788141ba4e564
    enemy_ranged_e_attack_05.png       ranged   e      419d9fc7a44ec4e6
    enemy_ranged_ne_attack_00.png      ranged   ne     b6b3dd76137bfdf4
    enemy_ranged_ne_attack_01.png      ranged   ne     82f1fff7205053b3
    enemy_ranged_ne_attack_02.png      ranged   ne     52384404c5915423
    enemy_ranged_ne_attack_03.png      ranged   ne     cbbd44bd876cc032
    enemy_ranged_ne_attack_04.png      ranged   ne     bca0633196fc175a
    enemy_ranged_ne_attack_05.png      ranged   ne     5128ca5d6be68940
    enemy_ranged_n_attack_00.png       ranged   n      be630460eb26d068
    enemy_ranged_n_attack_01.png       ranged   n      abcf292ecbaf294a
    enemy_ranged_n_attack_02.png       ranged   n      f09baf57f56d53db
    enemy_ranged_n_attack_03.png       ranged   n      831942f35e2bd878
    enemy_ranged_n_attack_04.png       ranged   n      0eb69b59be6064fc
    enemy_ranged_n_attack_05.png       ranged   n      db23a1009c362b75
    enemy_ranged_nw_attack_00.png      ranged   nw     2f1269ee8aabfe10
    enemy_ranged_nw_attack_01.png      ranged   nw     93316a9a0ba484f3
    enemy_ranged_nw_attack_02.png      ranged   nw     3d516d424e0624ba
    enemy_ranged_nw_attack_03.png      ranged   nw     0069f7d96417e1cc
    enemy_ranged_nw_attack_04.png      ranged   nw     dbf00a25f8d357b0
    enemy_ranged_nw_attack_05.png      ranged   nw     794a11c4f41aef25
    enemy_ranged_w_attack_00.png       ranged   w      90edc2571f8b898d
    enemy_ranged_w_attack_01.png       ranged   w      7726c751e63266e4
    enemy_ranged_w_attack_02.png       ranged   w      2ceb0c7abbdc9e43
    enemy_ranged_w_attack_03.png       ranged   w      2ecbe1e6b5a36111
    enemy_ranged_w_attack_04.png       ranged   w      3411fcdfa28917ce
    enemy_ranged_w_attack_05.png       ranged   w      9e624b7fd93c35dc
    enemy_ranged_sw_attack_00.png      ranged   sw     5628c0ea4233a49c
    enemy_ranged_sw_attack_01.png      ranged   sw     7a783c75f8a2f815
    enemy_ranged_sw_attack_02.png      ranged   sw     7b57fa84a9f9d7d6
    enemy_ranged_sw_attack_03.png      ranged   sw     67f802951005dcde
    enemy_ranged_sw_attack_04.png      ranged   sw     6ab3ff6c6058d06b
    enemy_ranged_sw_attack_05.png      ranged   sw     2b2e6363361c4a84

**Totals: 16 directions, 96 frames.**

## What this record does not claim

- **No seed, and no per-call cost.** Neither is exposed by PixelLab for these modes. The
  aggregate cost above is a before/after balance subtraction taken with the job queue empty.
- **Nothing about in-Unity appearance.** This task delivers source art; it does not build
  Tile or animation assets, touch a scene, or change gameplay geometry.
- **Vincent has not reviewed this art.** He granted PixelLab use without permission being
  needed; that is not a review of the result.
