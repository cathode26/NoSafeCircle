#!/usr/bin/env python3
"""Deterministic smoke test for unity_workspace_hygiene.py."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("unity_workspace_hygiene.py")


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise AssertionError(f"command failed {args}:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nsc-unity-hygiene-") as td:
        root = Path(td) / "repo"
        root.mkdir()
        run("git", "init", cwd=root)
        run("git", "config", "user.email", "smoke@example.invalid", cwd=root)
        run("git", "config", "user.name", "Smoke Test", cwd=root)

        write(root, "Tasks/NSC-999.yaml", json.dumps({
            "id": "NSC-999",
            "exclusive_resources": ["unity-scene:Assets/Scenes/Example.unity"],
        }))
        write(root, "Assets/Scenes/Example.unity", "scene-base\n")
        write(root, "Assets/TaskSource.cs", "source-base\n")
        write(root, "Assets/UnexpectedTracked.asset", "unexpected-base\n")
        write(root, "ProjectSettings/EditorBuildSettings.asset", "settings-base\n")
        write(root, "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json", "{}\n")
        write(root, "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/FloorTile.asset", "tile-base\n")
        run("git", "add", ".", cwd=root)
        run("git", "commit", "-m", "baseline", cwd=root)

        write(root, "Assets/TaskSource.cs", "source-candidate\n")
        snapshot = Path(td) / "snapshot.json"
        run(
            sys.executable,
            str(SCRIPT),
            "--repo", str(root),
            "snapshot",
            "--task-id", "NSC-999",
            "--output", str(snapshot),
            cwd=root,
        )

        write(root, "Assets/Scenes/Example.unity", "scene-built\n")
        write(root, "ProjectSettings/EditorBuildSettings.asset", "settings-unity-churn\n")
        write(root, "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/FloorTile.asset", "tile-reserialized\n")
        write(root, "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WizardSprite.asset", "generated\n")
        write(root, "Assets/UnexpectedTracked.asset", "unexpected-semantic-change\n")

        blocked = run(
            sys.executable, str(SCRIPT), "--repo", str(root), "inspect", "--snapshot", str(snapshot), cwd=root, check=False
        )
        assert blocked.returncode == 2
        assert "UNEXPECTED TRACKED CHANGES" in blocked.stdout
        run("git", "restore", "--", "Assets/UnexpectedTracked.asset", cwd=root)

        inspect = run(
            sys.executable, str(SCRIPT), "--repo", str(root), "inspect", "--snapshot", str(snapshot), cwd=root
        )
        assert "KNOWN UNITY CHURN" in inspect.stdout
        assert "TASK RESOURCE CHANGES TO KEEP" in inspect.stdout
        assert "NEW GENERATED UNITY ASSETS" in inspect.stdout

        clean = run(
            sys.executable,
            str(SCRIPT),
            "--repo", str(root),
            "clean",
            "--snapshot", str(snapshot),
            "--remove-new-untracked",
            cwd=root,
        )
        assert "UNITY WORKSPACE HYGIENE COMPLETE" in clean.stdout
        assert (root / "Assets/TaskSource.cs").read_text() == "source-candidate\n"
        assert (root / "Assets/Scenes/Example.unity").read_text() == "scene-built\n"
        assert (root / "ProjectSettings/EditorBuildSettings.asset").read_text() == "settings-base\n"
        assert (root / "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/FloorTile.asset").read_text() == "tile-base\n"
        assert not (root / "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WizardSprite.asset").exists()

        write(root, "Unexpected.txt", "base\n")
        run("git", "add", "Unexpected.txt", cwd=root)
        run("git", "commit", "-m", "advance head", cwd=root)
        stale = run(
            sys.executable, str(SCRIPT), "--repo", str(root), "inspect", "--snapshot", str(snapshot), cwd=root, check=False
        )
        assert stale.returncode == 2
        assert "HEAD changed" in stale.stderr

    print("unity_workspace_hygiene smoke test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
