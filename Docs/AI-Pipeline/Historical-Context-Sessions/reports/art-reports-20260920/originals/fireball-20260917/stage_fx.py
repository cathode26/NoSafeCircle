"""Stage the fireball VFX as a tree the Game Agent can drop into the repo, with the import settings written down.

Camera-facing sprites at 64 PPU, point filter. Pivots:
  charge_gather / charge_hold / projectile - mid-air, centred: (0.5, 0.5)
  impact - sits on the floor: (0.5, y) with y from the burst's base row, ONE value for the whole set so it
    cannot hop between frames
  scorch - a flat floor decal, centred: (0.5, 0.5)
"""
import hashlib, json, os, shutil
from PIL import Image

O = "C:/nscrev/reports/art-director/fireball-20260917"
F = f"{O}/final48"
S = f"{O}/staged/Source/PixelLabFX/Fireball"

SETS = {
    "charge_gather": [f"gather_{i}" for i in range(6)],
    "charge_hold": [f"hold_{i}" for i in range(6)],
    "projectile": [f"projectile_{i}" for i in range(4)],
    "impact": [f"impact_{i}" for i in range(8)],
}
STILLS = {"core": "core_still", "spark": "spark_still", "impact_base": "impact_still"}


def info(path):
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    data = open(path, "rb").read()
    rows = [y for y in range(im.height) if any(a.load()[x, y] > 8 for x in range(im.width))]
    return {
        "canvas": list(im.size),
        "bbox": list(a.getbbox()),
        "lowest_opaque_row": rows[-1],
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "colours": len({c for c in im.convert("RGBA").getdata() if c[3] > 8}),
    }


def main():
    shutil.rmtree(f"{O}/staged", ignore_errors=True)
    inv = {"schema": "nsc-pixellab-fx/v1", "family": "fireball", "task_id": None,
           "authority": "Vincent, 2026-09-17: \"Tell it to make me some fireball art with out a task right now, "
                        "make the task after when we can.\" Cap 100 generations.",
           "pixels_per_unit": 64, "filter_mode": "Point", "sets": {}, "stills": {}}
    for name, frames in SETS.items():
        d = f"{S}/{name}"
        os.makedirs(d, exist_ok=True)
        recs = []
        for i, fr in enumerate(frames):
            dst = f"{d}/frame_{i:03d}.png"
            shutil.copyfile(f"{F}/{fr}.png", dst)
            recs.append({"file": f"Source/PixelLabFX/Fireball/{name}/frame_{i:03d}.png", **info(dst)})
        H = recs[0]["canvas"][1]
        if name == "impact":
            base = max(r["lowest_opaque_row"] for r in recs[:1] + recs[1:])
            # one pivot for the set, from the most common base row
            rows = [r["lowest_opaque_row"] for r in recs]
            base = max(set(rows), key=rows.count)
            pivot = [0.5, round((H - (base + 1)) / H, 6)]
            note = (f"floor-sitting set: one pivot for all frames from the modal base row {base} of {H}; "
                    f"per-frame rows {rows}")
        else:
            pivot = [0.5, 0.5]
            note = "mid-air set: centred pivot, position is the emitter's job"
        inv["sets"][name] = {"frames": len(recs), "canvas": recs[0]["canvas"], "pivot": pivot,
                             "pivot_note": note, "world_size_units": round(recs[0]["canvas"][0] / 64, 4),
                             "files": recs}
        print(f"{name:14s} {len(recs)} frames  canvas {recs[0]['canvas']}  pivot {pivot}")
    os.makedirs(f"{S}/stills", exist_ok=True)
    for out, src in STILLS.items():
        dst = f"{S}/stills/{out}.png"
        shutil.copyfile(f"{F}/{src}.png", dst)
        inv["stills"][out] = {"file": f"Source/PixelLabFX/Fireball/stills/{out}.png", **info(dst)}
    sc = f"{S}/scorch.png"
    shutil.copyfile(f"{F}/scorch.png", sc)
    inv["sets"]["scorch"] = {"frames": 1, "canvas": info(sc)["canvas"], "pivot": [0.5, 0.5],
                             "pivot_note": "flat floor decal, centred; 136x68 is the 2:1 ground ellipse at 1.5 units",
                             "world_size_units": 2.125, "files": [{"file": "Source/PixelLabFX/Fireball/scorch.png",
                                                                   **info(sc)}]}
    shutil.copyfile(f"{O}/fire_palette.png", f"{S}/fire_palette.png")
    inv["palette"] = {"file": "Source/PixelLabFX/Fireball/fire_palette.png", "colours": 48,
                      "note": "every frame except the scorch uses only these 48 colours; the scorch has its own 32"}
    json.dump(inv, open(f"{O}/staged/fx-inventory.json", "w"), indent=2)
    n = sum(len(v["files"]) for v in inv["sets"].values()) + len(inv["stills"])
    print(f"\nstaged {n} PNGs + palette + fx-inventory.json under {O}/staged")


main()
