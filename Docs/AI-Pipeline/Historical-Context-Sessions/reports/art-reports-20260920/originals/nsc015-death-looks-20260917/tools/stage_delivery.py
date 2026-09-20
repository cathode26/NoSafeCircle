"""Stage the twelve approved death looks with an inventory, named for the look rather than the generation round.

Vincent, 2026-09-18: shown both rounds of the two contested brute looks he chose **all four**, then "So we want
all of the art" - so nothing is rejected and each enemy has **six** looks. The two upright-cloak wraith sprites
that I had rejected ship as their own looks, because for a spectral enemy a cloak that keeps its shape is a
legitimate death: the cloak IS the creature.

Names use _a / _b for two variants of the same look, never r1 / r2 - a round number implies one of them lost.
"""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

from PIL import Image

O = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(O, "aligned")
DST_REL = "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/Death"
DST = os.path.join(O, "staged", *DST_REL.split("/"))

# ship name -> (source file, enemy, look, object id, seed, prompt note)
SHIP = [
    ("death_brute_blasted", "brute_blasted", "dungeon_brute", "blasted",
     "4423f1d2-08ee-44d8-ba0a-c81abeeb95f0", 40001, "on its back, limbs splayed, cleaver thrown clear"),
    ("death_brute_burned", "brute_burned", "dungeon_brute", "burned",
     "a102f7b2-29c4-4747-8d08-687a2e71bce0", 40002, "curled, charcoal cloak, embers, one smoke wisp"),
    ("death_brute_decapitated_a", "brute_decapitated_r1", "dungeon_brute", "decapitated",
     "693166c8-0c4e-471f-84a1-bd7faf8a13e1", 40003, "face down, hood lying beside it, dark pool at the collar"),
    ("death_brute_decapitated_b", "brute_decapitated_r2", "dungeon_brute", "decapitated",
     "083e969b-85ca-4491-aa4a-e13000fd57d9", 40013, "crumpled, neck end a dark hollow, hood lying beside it"),
    ("death_brute_dismembered_a", "brute_dismembered_r1", "dungeon_brute", "dismembered",
     "1a791813-e690-4431-a7b8-49959eeee6ea", 40004, "on its side, severed arm a few pixels away gripping the cleaver"),
    ("death_brute_dismembered_b", "brute_dismembered_r2", "dungeon_brute", "dismembered",
     "5831dfc8-15f6-4a6b-b169-3332bc88aa0b", 40014, "flat, empty sleeve, cleaver thrown clear"),
    ("death_wraith_dissipated", "wraith_dissipated", "lantern_wraith", "dissipated",
     "56059dfa-96a2-4529-8606-14004efd373d", 40005, "empty cloak collapsing, teal wisp scattering from the collar"),
    ("death_wraith_snuffed", "wraith_snuffed_r2", "lantern_wraith", "snuffed",
     "c6af695d-437a-4ee7-848f-55ad79a30c30", 40015, "cloak collapsed flat, lantern fallen and dark"),
    ("death_wraith_shattered", "wraith_shattered", "lantern_wraith", "shattered",
     "6da672cb-9ad2-427a-9473-60f124c686d2", 40007, "lantern burst open, teal flame in separate shards"),
    ("death_wraith_unravelled", "wraith_unravelled_r2", "lantern_wraith", "unravelled",
     "168245b2-4730-46a8-b056-b699ea1cdf51", 40016, "cloak torn open, teal draining low across the ground"),
    # Vincent 2026-09-18: "So we want all of the art" - the two upright cloaks ship as their own looks rather
    # than as rejects. For a SPECTRAL enemy an empty cloak that keeps its shape is defensible: the cloak IS the
    # creature, so it can die standing. Renamed for what they show, not for the round they came from.
    ("death_wraith_hollowed", "wraith_snuffed_r1", "lantern_wraith", "hollowed",
     "e8c7d38f-3a15-4386-b5cb-23ef8a835577", 40006,
     "cloak still standing but empty and slack, lantern fallen dark at its feet"),
    ("death_wraith_draining", "wraith_unravelled_r1", "lantern_wraith", "draining",
     "89f40548-a7dc-48c6-aba9-520158027751", 40008,
     "caught upright mid-dissolve, teal spirit pouring out of the collar, lantern still in a limp sleeve"),
]
REJECTS = []


def info(path):
    data = open(path, "rb").read()
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    al = a.load()
    rows = [y for y in range(im.height) if any(al[x, y] > 8 for x in range(im.width))]
    return {
        "canvas": list(im.size),
        "alpha_bbox": list(a.getbbox()),
        "alpha_bottom_y_from_top": rows[-1],
        "opaque_px": sum(1 for c in im.getdata() if c[3] > 8),
        "colours": len({c for c in im.getdata() if c[3] > 8}),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def main():
    shutil.rmtree(os.path.join(O, "staged"), ignore_errors=True)
    os.makedirs(DST, exist_ok=True)
    frames, rows = [], set()
    for ship, src, enemy, look, oid, seed, note in SHIP:
        s = os.path.join(SRC, src + ".png")
        dstf = os.path.join(DST, ship + ".png")
        shutil.copyfile(s, dstf)
        rec = info(dstf)
        rows.add(rec["alpha_bottom_y_from_top"])
        H = rec["canvas"][1]
        frames.append({
            "key": ship, "enemy": enemy, "look": look, "variant": ship[-2:] if ship[-2] == "_" else None,
            "object_id": oid, "seed": seed, "silhouette": note,
            "selected_path": f"{DST_REL}/{ship}.png",
            "pixels_per_unit": 64, "filter_mode": "Point",
            "pivot": [0.5, round((H - (rec["alpha_bottom_y_from_top"] + 1)) / H, 6)],
            **rec,
        })
        print(f"{ship:30s} ground {rec['alpha_bottom_y_from_top']}  colours {rec['colours']:3d}  {enemy}/{look}")
    assert len(rows) == 1, f"ground rows must agree across the set, got {rows}"
    inv = {
        "task": "NSC-015 (Dungeon Brute looks) and the Lantern Wraith task",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "family": "enemy_death_looks",
        "canvas": [144, 96],
        "pixels_per_unit": 64,
        "filter_mode": "Point",
        "ground_row_inclusive": sorted(rows)[0],
        "pivot": [0.5, round((96 - (sorted(rows)[0] + 1)) / 96, 6)],
        "alignment_note": "every sprite's lowest opaque row is on one row by whole-pixel shifts only; opaque "
                          "counts unchanged and nothing clipped (tools/align_ground.py, report in "
                          "aligned/ground_line_report.json). One pivot serves the whole set.",
        "palette": {"colours": 48, "note": "all twelve generated sprites were quantized together in one "
                                           "reduce_colors call, so the union across the set is exactly 48."},
        "selection": {
            "decision": "Vincent 2026-09-18: all four contested brutes ship, then \"So we want all of the art\".",
            "selection_rule": "Vincent 2026-09-18, verbatim: \"you get killed with 1 shot, then you are decapitated\" and \"if you need multiple shots to kill you, you lose an arm\". So selection is driven by the kill's hit count, not random - one shot picks decapitated, more than one picks dismembered, and the two variants of each give variety inside the rule. Burned stays gated to a fire kill and blasted is the default when no rule matches. The wraith has no head or arm, so its equivalent pair is shattered for one shot and unravelled or draining for multiple. Confirmation of the contracted wording is with the GER Agent, who had the rule from Vincent directly.",
            "consequence": "SIX looks per enemy. Brute: blasted, burned, decapitated a and b, dismembered "
                           "a and b. Wraith: dissipated, snuffed, shattered, unravelled, hollowed, draining. "
                           "Nothing is rejected, so the rejects branch gets nothing from this batch.",
            "style_note": "decapitated_a keeps a small wound spiral at the collar. Vincent chose it with the "
                          "sprite in front of him, so a wound read is inside the approved family from now on - "
                          "recorded so nobody 'fixes' it later by citing the stylised-not-gore direction.",
        },
        "spend": {"before": {"remaining": 4381, "used": 618}, "after": {"remaining": 4309, "used": 690},
                  "metered": 72, "cap": 90,
                  "note": "690 - 618 = 72 and 4381 - 4309 = 72; both columns agree, queue empty at both readings."},
        "authority": "Vincent's direction and cap relayed by the GER Agent 2026-09-18: stylised-violent rather "
                     "than literal gore, batch approved, cap 90 generations.",
        "byte_warning": "sha256 values are of THESE files. Copy them verbatim; a re-export changes every hash.",
        "sprites": frames,
        "rejects": [{"key": k, "object_id": o, "seed": s, "reason": r,
                     "branch": "art-rejects/NSC-015"} for k, o, s, r in REJECTS],
    }
    json.dump(inv, open(os.path.join(O, "staged", "death-inventory.json"), "w"), indent=2)
    print(f"\nstaged {len(frames)} sprites, ground row {sorted(rows)[0]} for all of them, "
          f"pivot {inv['pivot']}, {len(REJECTS)} rejects")


main()
