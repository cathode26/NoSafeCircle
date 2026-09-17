# Deterministic source-art inventory — NSC-063

This inventory supports completion gate VAL-001. It lists every selected
source file, its archetype, facing, dimensions, transparency, and the exact
PixelLab generation identifier it came from. No file listed below is missing,
duplicated, or ambiguously named.

**2026-09-14 update:** Vincent chose REVISE on the original selection (cleaver
not visible on the Melee Enemy, Ranged Enemy silhouette too dark). The table
below now reflects the 2026-09-14 revision candidates (`melee_c`/`ranged_c`),
which replaced the original selection as the retained source. The original
selection's inventory (180x180, `melee_a`/`ranged_b`) is preserved further
below as superseded review history.

**2026-09-16 update:** Vincent approved a single-cleaver correction for the
Melee Enemy's north-east idle only (`enemy_melee_ne_idle_00.png`), which had
shown a duplicate second cleaver above the screen-left shoulder. The row
below now records the corrected SHA-256
(`e714d5e5d4222982f79597099261f7a20e19c7b7986e55a6588dd056e2537e57`,
replacing `0bb2b4602048e04094e5bdf06e768e7706d83efb3334b0eb90cdbcfa6b8e458e`).
Dimensions, mode, and `character_id` are unchanged. See
"North-east single-cleaver correction (2026-09-16)" in
`PIXELLAB_GENERATION.md` for full provenance. This is the only row this
update changes; all seven other melee facings and all eight ranged facings
are untouched.

## Selected source (`Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/`) — current, 2026-09-14 revision

| File | Archetype | Facing | Frame | Size | Mode | Transparent (alpha min) | SHA-256 | PixelLab `character_id` |
|---|---|---|---|---|---|---|---|---|
| `enemy_melee_n_idle_00.png` | Melee | north | idle (standing) | 128x128 | RGBA | 0 | `7c3e9594e149a4da8b82703334c5fe6ba818f842a972c2e8c4724856756ef5d9` | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_melee_ne_idle_00.png` | Melee | north-east | idle (standing) | 128x128 | RGBA | 0 | `e714d5e5d4222982f79597099261f7a20e19c7b7986e55a6588dd056e2537e57` (2026-09-16 single-cleaver correction; was `0bb2b4602048e04094e5bdf06e768e7706d83efb3334b0eb90cdbcfa6b8e458e`) | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_melee_e_idle_00.png` | Melee | east | idle (standing) | 128x128 | RGBA | 0 | `23ac1bc0940d63f47ca263eef0bd9a956b89f2820bec7434e7602d5a11efbd65` | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_melee_se_idle_00.png` | Melee | south-east | idle (standing) | 128x128 | RGBA | 0 | `5d2b83a5628b8adde41bd937abb62025cce849d4f3b9d33f9323623e23b83df0` | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_melee_s_idle_00.png` | Melee | south | idle (standing) | 128x128 | RGBA | 0 | `394c2ab9b7b240036e882976f87e14b0fc1565a81d7531371f88f589527efbd6` | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_melee_sw_idle_00.png` | Melee | south-west | idle (standing) | 128x128 | RGBA | 0 | `e5f2083fb77bf409743ab73218ad2be9e7a904555ae2224363513df97790274c` | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_melee_w_idle_00.png` | Melee | west | idle (standing) | 128x128 | RGBA | 0 | `695eb819b4c3f35cc4f66dbb6917b1f2d74530259410f74fdbf6c41564c4d6f9` | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_melee_nw_idle_00.png` | Melee | north-west | idle (standing) | 128x128 | RGBA | 0 | `11428ed589e90671c51397045fe2a0c8ab35985a4be5b5f94c297a68c60fad13` | `070592db-d334-4e7d-b5c9-5dad404d7f98` |
| `enemy_ranged_n_idle_00.png` | Ranged | north | idle (standing) | 128x128 | RGBA | 0 | `ad18696ab24c35d5b7bf4ed688457fdfe19498e26faefd1d2bf42c370582f027` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |
| `enemy_ranged_ne_idle_00.png` | Ranged | north-east | idle (standing) | 128x128 | RGBA | 0 | `313c9ceaf3942377d7fcb7155a16345fbdf799aa2386b03d107ce6dbe39ddce7` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |
| `enemy_ranged_e_idle_00.png` | Ranged | east | idle (standing) | 128x128 | RGBA | 0 | `04730f5b718bff803b51705c98451a557f625a146333390474864a22e93c3669` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |
| `enemy_ranged_se_idle_00.png` | Ranged | south-east | idle (standing) | 128x128 | RGBA | 0 | `33a6bb9dba7c8d678c0c82e20aa0b9bd51235643ba113c6db63650b41d7d209d` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |
| `enemy_ranged_s_idle_00.png` | Ranged | south | idle (standing) | 128x128 | RGBA | 0 | `13ac0b0cc28a4f5240ba1592203ed814bd80e504d7f3cd0afa4ad5a1caa7fecc` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |
| `enemy_ranged_sw_idle_00.png` | Ranged | south-west | idle (standing) | 128x128 | RGBA | 0 | `14feaf1a2751a8e6d411d768fdef93c5788f51b1a8ab24954d2f7dfc1a6805a3` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |
| `enemy_ranged_w_idle_00.png` | Ranged | west | idle (standing) | 128x128 | RGBA | 0 | `31d909b5a98d2a75b7e813f91506e572aa59a0a3932e2f24cef7b7b70a40bb0c` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |
| `enemy_ranged_nw_idle_00.png` | Ranged | north-west | idle (standing) | 128x128 | RGBA | 0 | `1c94e8c8733d8f83a9e11b409b86933bc8d1d411e05eba2f632822f39656ca62` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` |

Completeness check: both required archetypes present; all eight gameplay
facings (`n`, `ne`, `e`, `se`, `s`, `sw`, `w`, `nw`) present for each; every
file is 128x128 RGBA with a fully transparent minimum alpha value (0); one
idle/standing frame per facing (no animation frames, matching the "no movement
or attack animations" boundary); no duplicate or ambiguous filenames; each
revised file verified byte-identical (via `cmp`) to its raw export in
`Docs/Art/Enemies/Candidates/melee_c/` or `Docs/Art/Enemies/Candidates/ranged_c/`,
**except** `enemy_melee_ne_idle_00.png`, which since 2026-09-16 is instead
byte-identical to the approved single-cleaver correction candidate,
`Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/idle_single_cleaver.png`
(see "North-east single-cleaver correction (2026-09-16)" in
`PIXELLAB_GENERATION.md`).

## Revision raw candidate exports (`Docs/Art/Enemies/Candidates/`, current selection)

| Folder | Candidate | Archetype | Files | PixelLab `character_id` | PixelLab `group_id` |
|---|---|---|---|---|---|
| `melee_c/` | Melee revision (selected) | Melee | `north.png`, `north-east.png`, `east.png`, `south-east.png`, `south.png`, `south-west.png`, `west.png`, `north-west.png` | `070592db-d334-4e7d-b5c9-5dad404d7f98` | `9e547e77-e1f7-4e2e-a55e-9d913d054134` |
| `ranged_c/` | Ranged revision (selected) | Ranged | `north.png`, `north-east.png`, `east.png`, `south-east.png`, `south.png`, `south-west.png`, `west.png`, `north-west.png` | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` | `51e771fd-7269-4c7f-9822-c3f2b34cd91d` |

The selected-source files above are byte-identical copies of the matching
`melee_c/` and `ranged_c/` raw exports (verified with `cmp` on all 16 pairs).

## Contact sheet

`Docs/Art/Enemies/contact_sheet.png` — both currently-selected (revised)
enemies across all eight facings, assembled locally with Pillow from the raw
PixelLab exports in `melee_c/`/`ranged_c/` above.
`Docs/Art/Enemies/Candidates/_inspection/` holds additional full-resolution
and downscaled gameplay-scale comparison sheets used for this revision's
visual review; they are supporting evidence, not part of this deterministic
inventory.

## Full generation record

See `PIXELLAB_GENERATION.md` in this folder for exact prompts, tool settings,
selection reasoning, and remaining human visual-review questions, for both
the original selection and the 2026-09-14 revision.

---

## Superseded: original selection inventory (2026-09-12, 180x180, no longer retained source)

This section is preserved as review history only. These files are **not**
the current content of
`Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/`; they describe what
was selected before the 2026-09-14 revision replaced it.

| File (original) | Archetype | Facing | Frame | Size | Mode | Transparent (alpha min) | SHA-256 | PixelLab `character_id` |
|---|---|---|---|---|---|---|---|---|
| `enemy_melee_n_idle_00.png` | Melee | north | idle (standing) | 180x180 | RGBA | 0 | `de1fffef5cf3a2b9270b16be69cbfdc5d9a04804aed701448a927abb3c1c6ad4` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_melee_ne_idle_00.png` | Melee | north-east | idle (standing) | 180x180 | RGBA | 0 | `6644bf4e844833fc1e60c8477ebe351d9295ec2fff35f2aa199cb60b2f969ef8` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_melee_e_idle_00.png` | Melee | east | idle (standing) | 180x180 | RGBA | 0 | `8d1a05fab89e49c2063c44647b707acf3d0b26c147394caab7c1df3d8cf66abe` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_melee_se_idle_00.png` | Melee | south-east | idle (standing) | 180x180 | RGBA | 0 | `a382b818678aa6ae02c37b5276e54d30ea380c4d3b46a4541c75cf7fefbb77c7` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_melee_s_idle_00.png` | Melee | south | idle (standing) | 180x180 | RGBA | 0 | `e83f4313eff7c8a6bfa7d880936b6b3d5d79f89023babb15443aafad14a02258` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_melee_sw_idle_00.png` | Melee | south-west | idle (standing) | 180x180 | RGBA | 0 | `32f177e18ae9ed0069e6fb94323cf0a91686d590c709c1620a08a139ddc439f8` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_melee_w_idle_00.png` | Melee | west | idle (standing) | 180x180 | RGBA | 0 | `c32d6f3d5600c2d32b5791445f8a92f9fb3b840a8243c8c2353034dc687aa12e` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_melee_nw_idle_00.png` | Melee | north-west | idle (standing) | 180x180 | RGBA | 0 | `e618d47957b758437cd55c0c027f8c3b1048b80f94b0ffaf8675f51e5bea50b8` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` |
| `enemy_ranged_n_idle_00.png` | Ranged | north | idle (standing) | 180x180 | RGBA | 0 | `25fc8ea9663f532774880687913c52f1838baf2bd7dccdabe8f805af5aba63f1` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |
| `enemy_ranged_ne_idle_00.png` | Ranged | north-east | idle (standing) | 180x180 | RGBA | 0 | `2a993e2def723ef947f6f3fd21ede0a0e5ea41ae899dc12158aa130feb946d36` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |
| `enemy_ranged_e_idle_00.png` | Ranged | east | idle (standing) | 180x180 | RGBA | 0 | `2b954ba872f7eea74e398b85a6175079d5231772ad3efce02149469fd4f90da7` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |
| `enemy_ranged_se_idle_00.png` | Ranged | south-east | idle (standing) | 180x180 | RGBA | 0 | `42a53e9796567657fd34256b3a59b174200caef636264e7eb0a25174737375e7` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |
| `enemy_ranged_s_idle_00.png` | Ranged | south | idle (standing) | 180x180 | RGBA | 0 | `4ce6409c94927f3902fecb18925fd2a387f509596f296d783bb7ba317c23e1c8` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |
| `enemy_ranged_sw_idle_00.png` | Ranged | south-west | idle (standing) | 180x180 | RGBA | 0 | `16bcc71c696154504391cc9682c259a7ca39de355b10364b436877bc574913f9` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |
| `enemy_ranged_w_idle_00.png` | Ranged | west | idle (standing) | 180x180 | RGBA | 0 | `e54d298062bd08782ee2b37948bb2ac3d502b85f7fc9420a7158035693e399ac` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |
| `enemy_ranged_nw_idle_00.png` | Ranged | north-west | idle (standing) | 180x180 | RGBA | 0 | `21d53985b6c17dce180a86550e676c2a744bfd62f36833cd226acf7b3d902337` | `361131dd-8c48-4b99-8b81-c79bd30078dc` |

| Folder | Candidate | Archetype | Files | PixelLab `character_id` | PixelLab `group_id` |
|---|---|---|---|---|---|
| `melee_a/` | Melee Candidate A (originally selected, superseded) | Melee | `north.png`, `north-east.png`, `east.png`, `south-east.png`, `south.png`, `south-west.png`, `west.png`, `north-west.png` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` | `a9d1ee9f-090f-4df8-9534-a44bba438c12` |
| `melee_b/` | Melee Candidate B | Melee | `north-east.png`, `north-west.png`, `south-east.png`, `south-west.png` (diagonals only) | `8d329296-ab6d-4372-a93c-b67319fb964a` | `66c29cda-4417-4258-993a-05eb84080077` |
| `ranged_a/` | Ranged Candidate A | Ranged | `north-east.png`, `north-west.png`, `south-east.png`, `south-west.png` (diagonals only) | `21bfad3b-86ab-43f9-94f2-a03cb3ed5ba4` | `fc968dcb-eaf5-4bc8-a1a6-44fedbd6a196` |
| `ranged_b/` | Ranged Candidate B (originally selected, superseded) | Ranged | `north.png`, `north-east.png`, `east.png`, `south-east.png`, `south.png`, `south-west.png`, `west.png`, `north-west.png` | `361131dd-8c48-4b99-8b81-c79bd30078dc` | `f8421090-c9f3-42e9-aaae-262ee997238c` |

All four original candidates and their folders remain intact as review
history per `generation-plan.md`; none are authorized Unity-integration
inputs now that the 2026-09-14 revision has replaced the retained source.
