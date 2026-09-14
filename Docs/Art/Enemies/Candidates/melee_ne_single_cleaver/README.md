# NSC-063 melee northeast single-cleaver review candidate

This is a **separate, unapproved source-art candidate** for the northeast idle.
It does not replace `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_melee_ne_idle_00.png`, change the PixelLab character record, or change NSC-093 walk frames.

The checked-in source has a second bright cleaver above the screen-left shoulder.
`idle_single_cleaver.png` removes that blade and its hilt, leaving only the
screen-right, right-hand cleaver. Compare the original and candidate in
`original_vs_single_cleaver_gameplay.png`; its lower row shows both reduced to
48-pixel gameplay sprites and enlarged with nearest-neighbor sampling for review.
Vincent's visual decision remains open.

## Provenance

- Original source SHA-256: `0bb2b4602048e04094e5bdf06e768e7706d83efb3334b0eb90cdbcfa6b8e458e`.
  The PixelLab northeast rotation URL was verified byte-identical before editing.
- Source PixelLab project: `d045108f-d37a-40ec-b505-a74f42800cc9`;
  character: `070592db-d334-4e7d-b5c9-5dad404d7f98`;
  rotation: `north-east`.
- Tool: PixelLab MCP `inpaint_image`, transparent 128×128 PNG, masked edit.
  No `create_character` or `animate_character` call was made.
- First job `3834cd04-96b4-4911-bce9-65979529bd60`, mask `(16,16,34,52)`,
  output SHA-256 `4f540c1d097699c95ea81fbf888c8f62dc962e1df9a578b2fdfb36940947ae13`.
  Rejected: it altered the arm but left the extra blade. Raw result is retained
  as `rejected_first_inpaint.png`.
- Second job `1486257a-cbd8-4446-810d-36d134054429`, mask `(14,12,36,57)`,
  `crop_to_mask=true`, `no_background=true`.
  The prompt explicitly identified the duplicate at x20–36/y20–49 and its
  handle at x34–43/y45–62, required transparent background and an empty left
  hand, and required the existing screen-right cleaver to remain unchanged.
  Output SHA-256 `e714d5e5d4222982f79597099261f7a20e19c7b7986e55a6588dd056e2537e57`.
  This raw output is `idle_single_cleaver.png`.

## Verification and remaining work

The candidate is 128×128 RGBA. Exactly 653 pixels differ from the source; all
are inside the second mask, and **zero** pixels outside it differ. Bright
blade-colored pixels in the extra-blade region fell from 124 to zero. The
right-hand cleaver is outside the mask and pixel-for-pixel unchanged. Visual
inspection of the 128-pixel source and 48-pixel gameplay comparison finds one
readable cleaver and no new prop.

This image is not yet the PixelLab character's northeast rotation. A future
NSC-093 walk correction must use an approved single-cleaver identity, rather
than animate the unchanged original character record again. Do not regenerate
the walk or promote this candidate until Vincent accepts the idle image.
