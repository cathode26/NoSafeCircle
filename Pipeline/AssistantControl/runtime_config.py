"""Per-run Compose credential-volume mapping, without reading credential bytes."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


def compose_environment(checkout: Path, run_root: Path, *, provider: str,
                        credential_volume: str) -> dict[str, str]:
    if provider not in {"claude", "codex"}:
        raise ValueError("Unsupported worker provider")
    if (not isinstance(credential_volume, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", credential_volume)):
        raise ValueError("Explicit existing credential volume name is required")
    checkout = checkout.resolve()
    base = checkout / "compose.yaml"
    if not base.is_file():
        raise ValueError("Task checkout lacks compose.yaml")
    paths = [base]
    ordinary_override = checkout / "compose.override.yaml"
    if ordinary_override.is_file():
        paths.append(ordinary_override)
    run_root.mkdir(parents=True, exist_ok=True)
    override = run_root / "credential-volume.compose.json"
    content = json.dumps({"volumes": {
        f"{provider}-config": {"external": True, "name": credential_volume}
    }}, indent=2) + "\n"
    if override.exists():
        if override.read_text(encoding="utf-8") != content:
            raise ValueError("Existing run credential mapping differs; retained unchanged")
    else:
        with override.open("x", encoding="utf-8") as stream:
            stream.write(content)
    paths.append(override.resolve())
    return {"COMPOSE_FILE": os.pathsep.join(str(path) for path in paths),
            "COMPOSE_PATH_SEPARATOR": os.pathsep}
