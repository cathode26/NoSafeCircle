# Deterministic source-art inventory — NSC-063

This inventory supports completion gate VAL-001. It lists every selected
source file, its archetype, facing, dimensions, transparency, and the exact
PixelLab generation identifier it came from. No file listed below is missing,
duplicated, or ambiguously named.

## Selected source (`Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/`)

| File | Archetype | Facing | Frame | Size | Mode | Transparent (alpha min) | SHA-256 | PixelLab `character_id` |
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

Completeness check: both required archetypes present; all eight gameplay
facings (`n`, `ne`, `e`, `se`, `s`, `sw`, `w`, `nw`) present for each; every
file is 180x180 RGBA with a fully transparent minimum alpha value (0); one
idle/standing frame per facing (no animation frames, matching the "no movement
or attack animations" boundary); no duplicate or ambiguous filenames.

## Raw candidate exports (`Docs/Art/Enemies/Candidates/`, comparison evidence only — not authorized Unity-integration input)

| Folder | Candidate | Archetype | Files | PixelLab `character_id` | PixelLab `group_id` |
|---|---|---|---|---|---|
| `melee_a/` | Melee Candidate A (selected) | Melee | `north.png`, `north-east.png`, `east.png`, `south-east.png`, `south.png`, `south-west.png`, `west.png`, `north-west.png` | `3db4582d-8b48-4486-be1a-19d1a8c6b9d2` | `a9d1ee9f-090f-4df8-9534-a44bba438c12` |
| `melee_b/` | Melee Candidate B | Melee | `north-east.png`, `north-west.png`, `south-east.png`, `south-west.png` (diagonals only) | `8d329296-ab6d-4372-a93c-b67319fb964a` | `66c29cda-4417-4258-993a-05eb84080077` |
| `ranged_a/` | Ranged Candidate A | Ranged | `north-east.png`, `north-west.png`, `south-east.png`, `south-west.png` (diagonals only) | `21bfad3b-86ab-43f9-94f2-a03cb3ed5ba4` | `fc968dcb-eaf5-4bc8-a1a6-44fedbd6a196` |
| `ranged_b/` | Ranged Candidate B (selected) | Ranged | `north.png`, `north-east.png`, `east.png`, `south-east.png`, `south.png`, `south-west.png`, `west.png`, `north-west.png` | `361131dd-8c48-4b99-8b81-c79bd30078dc` | `f8421090-c9f3-42e9-aaae-262ee997238c` |

The selected-source files above are byte-identical copies of the matching
`melee_a/` and `ranged_b/` raw exports (verified by matching SHA-256 values).
`melee_b/` and `ranged_a/` are retained only as rejected-candidate comparison
evidence per `generation-plan.md`; they are outside
`Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/` and are not authorized
inputs for a future Unity-integration task.

## Contact sheet

`Docs/Art/Enemies/contact_sheet.png` — both selected enemies across all eight
facings, assembled locally with Pillow from the raw PixelLab exports above.

## Full generation record

See `PIXELLAB_GENERATION.md` in this folder for exact prompts, tool settings,
selection reasoning, and remaining human visual-review questions.
