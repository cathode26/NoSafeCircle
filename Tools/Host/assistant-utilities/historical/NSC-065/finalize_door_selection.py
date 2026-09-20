from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


CHECKOUT = Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-065")
DOCS = CHECKOUT / "Docs/Art/Doors"
CANDIDATES = DOCS / "Candidates"
SELECTED = CHECKOUT / "Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source"

JOBS = {
    "sealed": ("99f204e7-c2e6-4b79-96bf-91f1aab741b9", 20001),
    "opening": ("fc4d13cf-85e4-4bd3-a52f-1e98cc1d8ac9", 20002),
    "open": ("fd2b98a0-8f82-49ad-8117-c85bc9d1e7ba", 20006),
    "locked": ("f1f290b0-28c0-4b90-8bf6-eddbb6a6f09b", 20003),
    "damaged": ("2fc55322-5674-4e3e-9196-4c206bdb91d1", 20004),
    "broken": ("8002b0e8-6d4a-491c-afdf-53febab10109", 20007),
    "final": ("8fc65029-99cb-4113-979c-9944c3e897e0", 20005),
}

SELECTED.mkdir(parents=True, exist_ok=True)
inventory = []
for state, (job_id, seed) in JOBS.items():
    source = CANDIDATES / "family_b" / f"{state}.png"
    destination = SELECTED / f"door_bonestone_{state}_S_000.png"
    shutil.copyfile(source, destination)
    payload = destination.read_bytes()
    inventory.append(
        {
            "filename": destination.relative_to(CHECKOUT).as_posix(),
            "state": state,
            "direction": "S",
            "frame": 0,
            "pixel_dimensions": [128, 128],
            "pixel_format": "RGBA",
            "pixellab_job_id": job_id,
            "seed": seed,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )

manifest = {
    "schema": "nsc-pixellab-door-selection/v1",
    "task_id": "NSC-065",
    "provider": "PixelLab MCP",
    "selected_family": "family_b_bone_and_stone",
    "human_visual_approval": False,
    "assistant_selection_authority": "operator-authorized unattended continuation",
    "selection_reason": (
        "Family B has the stronger fixed isometric read, clearer open passage, "
        "more coherent stone threshold, and the requested dark-but-cute horror-comedy character."
    ),
    "files": inventory,
}
(DOCS / "inventory.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

rows = "\n".join(
    f"| `{item['state']}` | `{item['filename']}` | `{item['pixellab_job_id']}` | `{item['sha256']}` |"
    for item in inventory
)
(DOCS / "inventory.md").write_text(
    "# Selected door source inventory\n\n"
    "Selected family: **Family B — bone and stone**.\n\n"
    "The operator authorized unattended continuation and assistant selection. This is source-art selection only; "
    "it does not claim Unity integration or in-game validation.\n\n"
    "| State | Selected source | PixelLab job | SHA-256 |\n|---|---|---|---|\n"
    + rows
    + "\n",
    encoding="utf-8",
)

(DOCS / "PIXELLAB_GENERATION.md").write_text(
    "# PixelLab door generation record\n\n"
    "NSC-065 generated two bounded seven-state families through the authenticated PixelLab MCP. "
    "The comparison is retained in `contact_sheet.png`; raw exports remain under `Candidates/`.\n\n"
    "Family B was selected because its stone frame, threshold, perspective, and opening remain visually coherent across states. "
    "The open and broken images expose an unmistakable passage, the lock is readable at gameplay scale, and the palette fits the "
    "dark-but-cute horror-comedy direction. Family A remains a useful rejected comparison but has a flatter front-facing read.\n\n"
    "No animation, Unity import, scene change, runtime behavior, commit, push, or human visual approval is claimed here.\n",
    encoding="utf-8",
)

print(json.dumps({"selected": len(inventory), "family": manifest["selected_family"]}))
