"""Stage the fireball sprites in the exact shape NSC-098 revision 2 AC-001 asks for.

AC-001 wants the 28 files under Assets/NoSafeCircle/DoorPrototype/Art/Spells/Fireball/Source with a
source-inventory.json in the shape NSC-095's PixelLab128 inventory uses: key, frame index, PixelLab id, prompt,
canvas size, alpha bounding box and the sha256 of the committed bytes.

The crew has no way to know the PixelLab ids, the animation group ids, the seeds or the prompts - those live only
in this session's run record - so this file hands them over rather than leaving the crew to invent them. The
sha256 values are of THESE bytes: copy the files verbatim, do not re-export, or every selected_sha256 changes.
"""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

from PIL import Image

O = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(O, "final48")
DST_REL = "Assets/NoSafeCircle/DoorPrototype/Art/Spells/Fireball/Source"
DST = os.path.join(O, "staged-nsc098", *DST_REL.split("/"))

CORE = "54bfd8ab-ba92-4a8d-a5c4-a4231cde2987"
SPARK = "b5eaf332-4d08-4412-9956-366235d6a8ee"
IMPACT = "d3b8f8cf-ea03-4bfb-a2af-9a7c93647e5b"
SCORCH = "3863630f-080b-47f0-89c7-d082996243e7"

P_CORE = ("a charged fireball orb hanging in mid-air: a compact spinning ball of fire with a white-hot core, "
          "saffron inner flame and deep crimson outer tongues, three or four short flame tongues curling off the "
          "top and sides, radially symmetric so it reads the same from any heading, no hands, no wizard, no "
          "staff, no stick. [self-lit VFX clause]")
P_SPARK = ("a tiny ember spark gathering in mid-air: one small bright mote of fire no wider than a third of the "
           "canvas, centred, with two or three short sparks flicking off it and nothing else around it, no "
           "hands, no wizard, no staff. [self-lit VFX clause]")
P_IMPACT = ("a fireball impact burst on a dungeon floor: a wide flat explosion of flame spreading outward, a "
            "white-hot centre with saffron and orange flame lobes rolling out sideways and a few dark smoke "
            "curls above, twice as wide as it is tall so it reads as a burst on the ground seen from a low "
            "isometric camera, no crater, no floor, no stones, no wizard. [self-lit VFX clause]")
P_SCORCH = ("a scorch mark burned into a dungeon floor, seen from a low isometric camera so it reads as a flat "
            "oval twice as wide as it is tall: charred black centre fading to dark soot grey at the ragged edge, "
            "a few small cracked embers still glowing dull orange in it, completely flat on the ground with no "
            "height and no flame. [dungeon prop clause]")
P_PROJ = ("a fireball in flight: the ball of flame stays the same size and in the same place while its flame "
          "tongues flicker and curl, the white-hot core pulses brighter and dimmer, and small embers flick "
          "outward. the silhouette stays radially symmetric so it reads the same from any heading")
P_HOLD = ("a fully charged fireball held ready: the ball hovers in place and swells very slightly as the "
          "white-hot core pulses, flame tongues lick upward and curl back, a few embers rise off the top. it "
          "stays centred and does not travel")
P_GATHER = ("a spell charging up: the ember mote pulses and grows brighter, small sparks spiral inward toward it "
            "and are swallowed, the flame flickers upward. the mote stays centred and does not travel")
P_BURST = ("a fireball impact playing out once: the flame bursts up and outward at its widest and brightest, "
           "then the lobes roll down and shrink while the smoke curls drift upward and thin, ending as low "
           "guttering flame. the burst stays centred on the point of impact")

# name -> (key, group, frame_index, object_id, animation_group_id, prompt, seed, call)
SPEC = {}
SPEC["core_still"] = ("fireball", "still", None, CORE, None, P_CORE, 30001, "create_object_pro_flash")
SPEC["spark_still"] = ("fireball", "still", None, SPARK, None, P_SPARK, 30002, "create_object_pro_flash")
SPEC["impact_still"] = ("fireball", "still", None, IMPACT, None, P_IMPACT, 30003, "create_object_pro_flash")
SPEC["scorch"] = ("fireball", "decal", None, SCORCH, None, P_SCORCH, 30004, "create_object_pro_flash")
for i in range(4):
    SPEC[f"projectile_{i}"] = ("fireball", "projectile", i, CORE,
                               "76bd3529-7edf-4111-8a75-7bfbd13ce53f", P_PROJ, None, "animate_object v3")
for i in range(6):
    SPEC[f"hold_{i}"] = ("fireball", "charge_hold", i, CORE,
                         "9d3b9c1f-8e30-452b-b077-8aafa34a3e74", P_HOLD, None, "animate_object v3")
for i in range(6):
    SPEC[f"gather_{i}"] = ("fireball", "charge_gather", i, SPARK,
                           "0bad33ad-29da-4f5c-941d-015bc8efdd80", P_GATHER, None, "animate_object v3")
for i in range(8):
    SPEC[f"impact_{i}"] = ("fireball", "impact_burst", i, IMPACT,
                           "711eb02a-8868-481f-91a1-3f956323d5c5", P_BURST, None, "animate_object v3")

PIVOTS = {"charge_gather": [0.5, 0.5], "charge_hold": [0.5, 0.5], "projectile": [0.5, 0.5],
          "impact_burst": [0.5, 0.15625], "decal": [0.5, 0.5], "still": [0.5, 0.5]}


def main():
    assert len(SPEC) == 28, len(SPEC)
    shutil.rmtree(os.path.join(O, "staged-nsc098"), ignore_errors=True)
    os.makedirs(DST, exist_ok=True)
    frames = []
    for name in sorted(SPEC):
        key, group, idx, oid, gid, prompt, seed, call = SPEC[name]
        src = os.path.join(SRC, name + ".png")
        dst = os.path.join(DST, name + ".png")
        shutil.copyfile(src, dst)
        data = open(dst, "rb").read()
        im = Image.open(dst).convert("RGBA")
        a = im.getchannel("A")
        bbox = a.getbbox()
        rows = [y for y in range(im.height) if any(a.load()[x, y] > 8 for x in range(im.width))]
        frames.append({
            "key": key,
            "group": group,
            "frame_index": idx,
            "object_id": oid,
            "animation_group_id": gid,
            "prompt": prompt,
            "settings": {"call": call, "mode": "v3", "canvas": list(im.size), "view": "low top-down",
                         "seed": seed, "keep_first_frame": False if gid else None},
            "selected_path": f"{DST_REL}/{name}.png",
            "canvas": list(im.size),
            "alpha_bbox": list(bbox),
            "alpha_bottom_y_from_top": rows[-1],
            "selected_sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "colours": len({c for c in im.getdata() if c[3] > 8}),
            "pixels_per_unit": 64,
            "filter_mode": "Point",
            "pivot": PIVOTS[group],
        })
    inv = {
        "task": "NSC-098",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "family": "fireball",
        "pixels_per_unit": 64,
        "filter_mode": "Point",
        "palette": {"colours": 48, "note": "every frame except scorch uses only these 48 colours; scorch has its "
                                           "own 32. The 18 charge and projectile frames were quantized together "
                                           "in one reduce_colors call and the 9 impact frames were locked to "
                                           "that palette, so the union is exactly 48 and the impact set is a "
                                           "strict subset - verified."},
        "spend": {"before": {"remaining": 4408, "used": 591}, "after": {"remaining": 4381, "used": 618},
                  "metered": 27, "cap": 100,
                  "note": "618 - 591 = 27 and 4408 - 4381 = 27; both columns agree. Queue empty at both readings."},
        "authority": "Vincent 2026-09-17: \"Tell it to make me some fireball art with out a task right now, make "
                     "the task after when we can.\" Cap: \"100 for the fireball, they wont need that much.\" "
                     "NSC-098 revision 2 is that task.",
        "byte_warning": "selected_sha256 is the sha256 of THESE files. Copy them verbatim into the repo; a "
                        "re-export or any re-encode changes every hash and fails the AC-001 audit.",
        "frames": frames,
    }
    out = os.path.join(O, "staged-nsc098", *DST_REL.split("/"), "source-inventory.json")
    json.dump(inv, open(out, "w"), indent=2)
    print(f"staged {len(frames)} PNGs + source-inventory.json under {os.path.join(O, 'staged-nsc098')}")
    canv = {}
    for f in frames:
        canv.setdefault(tuple(f["canvas"]), []).append(f["group"])
    for c, gs in canv.items():
        print(f"  canvas {c}: {len(gs)} files ({sorted(set(gs))})")


main()
