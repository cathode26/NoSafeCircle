"""Stage the NSC-095 deliverables: selected PNGs, raw exports, source inventory and generation record.

Usage: python stage_delivery.py <stage_dir>

Nothing is committed. The Game Agent copies the staged tree into a clone and commits it, because the Art
Director never writes to main. Layout follows NSC-095 AC-002:
  Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/<key>/selected/standing/<dir>.png
  Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/<key>/selected/walk/<dir>/frame_000..005.png
  Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/source-inventory.json
  Docs/Art/Wizard/Raw128/<key>/...            (raw PixelLab frames, no .meta)
  Docs/Art/Wizard/PIXELLAB_128_GENERATION.md
"""
import hashlib
import json
import os
import shutil
import sys

from PIL import Image


def alpha_bottom(path):
    """The shipped file's own lowest opaque row, exclusive, as VAL-001 measures it."""
    return Image.open(path).convert("RGBA").getchannel("A").getbbox()[3]

ROOT = r"C:\nscrev\reports\art-director\wizard-128-remake"
DIRS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
SEL = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128"
RAW = "Docs/Art/Wizard/Raw128"

WALK_PROMPT = ("walking with a steady even stride, wide-brim pointed hat held level, coat hem swinging with each "
               "step, the small book at the belt staying in place, arms swinging naturally, boots alternating "
               "(per-wizard wording in the generation record)")

WIZARDS = {
    "masculine-light": {
        "aligned": "pixellab/masculine-light/aligned_v2",
        "character_id": "1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80",
        "character_note": "2026-09-16 density trial character, reused per NSC-095 AC-001; 0 new generations",
        "walk_groups": {"*": "f925b6a1-b6e1-419a-a474-bf2128114db4",
                        "south": "db177e25-3bcb-419a-9af1-deee64898373"},
        "raw_walk": {"*": "pixellab/masculine-light/walk",
                     "south": "pixellab/masculine-light/character_zip_v2/Idle/animations/wizard_ml_walk_128_south_r2/south"},
        "norm_walk": {"*": "pixellab/masculine-light/normalized128/walk",
                      "south": "pixellab/masculine-light/normalized128/walk_south_r2"},
        "raw_standing": "pixellab/masculine-light/standing_raw",
    },
    "masculine-dark": {
        "aligned": "pixellab/masculine-dark/aligned",
        "character_id": "02f0ec58-164f-428d-8b1b-7d5ad6c1ef6b",
        "character_note": "image_to_pixelart job c7ba1b8f-8fe6-4b0b-942a-11be1a907fed -> create_character v3",
        "walk_groups": {"*": "23a67b24-e1c9-4cb9-bab8-bc1145267cb9",
                        "south": "af5f597d-bd89-4ca7-a26c-e91ef7f76fcc"},
        "raw_walk": {"*": "pixellab/masculine-dark/character_zip/Idle/animations/wizard_md_walk_128",
                     "south": "pixellab/masculine-dark/character_zip_v2/Idle/animations/wizard_md_walk_128_south_r2/south"},
        "norm_walk": {"*": "pixellab/masculine-dark/normalized128/walk",
                      "south": "pixellab/masculine-dark/normalized128/walk_south_r2"},
        "raw_standing": "pixellab/masculine-dark/standing_raw",
    },
    "feminine-light": {
        "aligned": "pixellab/feminine-light/aligned_v2",
        "character_id": "53aebb62-452d-4228-bda3-3a873a42f9eb",
        "character_note": "image_to_pixelart job e0b19178-3425-4197-9af7-ea0e737a9c85 -> create_character v3",
        "walk_groups": {"*": "c92aa47d-7836-423f-a587-cac44dd24f20",
                        "north": "660311ba-196b-4dd6-b709-8217e0cf2b0c"},
        "raw_walk": {"*": "pixellab/feminine-light/walk",
                     "north": "pixellab/feminine-light/walk_north_r2"},
        "norm_walk": {"*": "pixellab/feminine-light/normalized128/walk",
                      "north": "pixellab/feminine-light/normalized128/walk_north_r2"},
        "raw_standing": "pixellab/feminine-light/standing_raw",
    },
    "feminine-dark": {
        "aligned": "pixellab/feminine-dark/aligned_v2",
        "character_id": "afabd47e-a66e-453d-beee-b90f9856f9e0",
        "character_note": "image_to_pixelart job 158d6bd2-5f36-404e-9ce1-514d7520c580 -> create_character v3",
        "walk_groups": {"*": "9114df33-56f0-4db8-bac8-66032b078374",
                        "north-east": "07d1e804-5203-4679-b8dd-f85e5bb4d8b1"},
        "raw_walk": {"*": "pixellab/feminine-dark/walk",  # the recorder downloads, whose names match the normalize reports
                     
                     "north-east": "pixellab/feminine-dark/character_zip/Idle/animations/wizard_fd_walk_128_ne_r2/north-east"},
        "norm_walk": {"*": "pixellab/feminine-dark/normalized128/walk",
                      "north-east": "pixellab/feminine-dark/normalized128/walk_northeast_r2"},
        "raw_standing": "pixellab/feminine-dark/standing_raw",
    },
}

EXCEPTIONS = {
    ("masculine-light", "west"): "no belt book; the v3 rotation dropped it. Vincent 2026-09-17: \"accept the gap\"",
    ("feminine-light", "east"): "no belt book; the v3 rotation dropped it. Vincent 2026-09-17: \"accept the gap\"",
    ("masculine-dark", "*"): ("no belt book in any facing; the approved 180 px south shows none, so the v3 rotation had "
                              "nothing to carry. Two masked inpaints and a prompt-led rebuild failed to add it"),
    ("feminine-dark", "*"): "hair shorter than the approved 180 px long hair. Vincent 2026-09-17: \"accept it\"",
}


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def pick(table, direction):
    return table.get(direction, table["*"])


def main():
    stage = sys.argv[1]
    planted = "--planted" in sys.argv[2:]
    inventory = {"task": "NSC-095", "recorded_utc": "2026-09-17", "canvas": [128, 128], "wizards": {}, "frames": []}
    for key, cfg in WIZARDS.items():
        aligned = os.path.join(ROOT, cfg["aligned"])
        gl = json.load(open(os.path.join(aligned, "ground_line.json"), encoding="utf-8"))
        plant_dir = os.path.join(ROOT, os.path.dirname(cfg["aligned"]), "planted")
        plant = {}
        if planted:
            prep = json.load(open(os.path.join(plant_dir, "plant_report.json"), encoding="utf-8"))
            plant = {(f["direction"], f["file"]): f for f in prep["frames"]}
            source_dir = plant_dir
        else:
            source_dir = aligned
        by_dst = {os.path.normcase(f["dst"]): f for f in gl["frames"]}
        inventory["wizards"][key] = {
            "character_id": cfg["character_id"],
            "character_note": cfg["character_note"],
            "ground_line_y_from_top": gl["ground_line_y_from_top"],
            "pivot": gl["pivot"],
            "max_dip_below_ground_line": 0 if planted else gl["max_dip_observed"],
            "walk_alignment": "per frame on the ground line (NSC-077 enemy precedent)" if planted else "per group",
            "dip_cap": gl["max_dip"],
            "groups": {},
        }
        for direction in DIRS:
            group_id = pick(cfg["walk_groups"], direction)
            g = gl["directions"][direction]
            inventory["wizards"][key]["groups"][direction] = {
                "animation_group_id": group_id,
                "standing": {k: g["still"][k] for k in ("reference_row", "dy", "deepest_row_after", "dip_below_ground_line")},
                "walk": ({"reference_row": g["walk"]["reference_row"], "dy": g["walk"]["dy"],
                          "deepest_row_after": gl["ground_line_row_inclusive"], "dip_below_ground_line": 0,
                          "deepest_frames": "all (every frame planted on the ground line)",
                          "alignment": "per frame, matching the NSC-077 enemy precedent"}
                         if planted else
                         {k: g["walk"][k] for k in ("reference_row", "dy", "deepest_row_after", "dip_below_ground_line", "deepest_frames")}),
            }
            # selected standing
            src = os.path.join(source_dir, "standing", direction + ".png")
            dst = os.path.join(stage, SEL, key, "selected", "standing", direction + ".png")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            raw_src = os.path.join(ROOT, cfg["raw_standing"], direction + ".png")
            raw_dst = os.path.join(stage, RAW, key, "standing", direction + ".png")
            os.makedirs(os.path.dirname(raw_dst), exist_ok=True)
            shutil.copy2(raw_src, raw_dst)
            rec = by_dst.get(os.path.normcase(src), {})
            inventory["frames"].append({
                "key": key, "group": "standing", "direction": direction, "frame_index": None,
                "character_id": cfg["character_id"], "animation_group_id": None,
                "prompt": "create_character v3 rotation (see the generation record)",
                "settings": {"mode": "v3", "size": 128, "view": "low top-down"},
                "selected_path": f"{SEL}/{key}/selected/standing/{direction}.png",
                "raw_path": f"{RAW}/{key}/standing/{direction}.png",
                "raw_size": [128, 128], "raw_alpha_bbox": rec.get("bbox_before"),
                "padding_offset": [0, rec.get("dy", 0)],
                "raw_sha256": sha256(raw_src), "selected_sha256": sha256(dst),
                "alpha_bottom_y_from_top": alpha_bottom(dst),
            })
            # selected walk
            wdir = os.path.join(source_dir, "walk", direction)
            files = sorted(f for f in os.listdir(wdir) if f.endswith(".png"))
            norm_dir = pick(cfg["norm_walk"], direction)
            norm_dir = os.path.join(ROOT, norm_dir, direction) if norm_dir.endswith("walk") else os.path.join(ROOT, norm_dir)
            nrep = json.load(open(os.path.join(norm_dir, "normalize_report.json"), encoding="utf-8"))
            nrep_by_name = {os.path.basename(r["selected_file"]): r for r in nrep}
            # Some sources hold one folder per direction, others are already the direction's folder.
            raw_dir = os.path.join(ROOT, pick(cfg["raw_walk"], direction))
            if os.path.isdir(os.path.join(raw_dir, direction)):
                raw_dir = os.path.join(raw_dir, direction)
            for i, fname in enumerate(files):
                src = os.path.join(wdir, fname)
                dst = os.path.join(stage, SEL, key, "selected", "walk", direction, f"frame_{i:03d}.png")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                n = nrep_by_name.get(fname, {})
                raw_name = n.get("frame") or fname
                raw_src = os.path.join(raw_dir, raw_name)
                raw_dst = os.path.join(stage, RAW, key, "walk", direction, raw_name)
                os.makedirs(os.path.dirname(raw_dst), exist_ok=True)
                if os.path.exists(raw_src):
                    shutil.copy2(raw_src, raw_dst)
                rec = by_dst.get(os.path.normcase(os.path.join(aligned, "walk", direction, fname)), {})
                norm_off = n.get("raw_origin_on_canvas") or [0, 0]
                inventory["frames"].append({
                    "key": key, "group": "walk", "direction": direction, "frame_index": i,
                    "character_id": cfg["character_id"],
                    "animation_group_id": pick(cfg["walk_groups"], direction),
                    "prompt": WALK_PROMPT,
                    "settings": {"mode": "v3", "frame_count": 6, "keep_first_frame": False, "size": 128},
                    "selected_path": f"{SEL}/{key}/selected/walk/{direction}/frame_{i:03d}.png",
                    "raw_path": f"{RAW}/{key}/walk/{direction}/{raw_name}" if os.path.exists(raw_src) else None,
                    "raw_size": n.get("raw_size"), "raw_alpha_bbox": n.get("raw_alpha_bbox"),
                    "padding_offset": [norm_off[0], norm_off[1] + rec.get("dy", 0) + plant.get((direction, fname), {}).get("dy", 0)],
                    "plant_dy": plant.get((direction, fname), {}).get("dy", 0) if planted else None,
                    "raw_sha256": n.get("raw_sha256"), "selected_sha256": sha256(dst),
                    "alpha_bottom_y_from_top": alpha_bottom(dst),
                })
    inventory["identity_exceptions"] = [
        {"key": k, "facing": d, "reason": r} for (k, d), r in EXCEPTIONS.items()
    ]
    inv_path = os.path.join(stage, SEL, "source-inventory.json")
    os.makedirs(os.path.dirname(inv_path), exist_ok=True)
    json.dump(inventory, open(inv_path, "w", encoding="utf-8"), indent=1)
    sel = sum(1 for f in inventory["frames"] if f["group"] == "walk") + sum(1 for f in inventory["frames"] if f["group"] == "standing")
    print("staged", sel, "selected frames;", len(inventory["frames"]), "inventory rows")
    missing = [f["selected_path"] for f in inventory["frames"] if not f["selected_sha256"]]
    print("missing sha:", len(missing))
    print("inventory:", inv_path)


main()
