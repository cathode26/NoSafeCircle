#!/usr/bin/env python3
"""Regression tests for narrowly recoverable post-Unity worktree churn."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.safe_unity_churn import (  # noqa: E402
    SafeUnityChurnError,
    classify_safe_post_unity_churn,
    recover_safe_post_unity_churn,
)


SCENE = "Assets/Scenes/DoorPrototype.unity"
COVERAGE = "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json"
GENERATED_TILE = (
    "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WallTile.asset"
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.rstrip()


def status(root: Path) -> str:
    return git(root, "status", "--porcelain=v1", "--untracked-files=all")


def test_scene_requires_proven_trailing_whitespace_only_diff() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        git(root, "init", "--initial-branch=main")
        git(root, "config", "user.name", "Safe Unity Churn Test")
        git(root, "config", "user.email", "safe-unity-churn@example.invalid")
        scene = root / SCENE
        coverage = root / COVERAGE
        generated_tile = root / GENERATED_TILE
        scene.parent.mkdir(parents=True)
        coverage.parent.mkdir(parents=True)
        generated_tile.parent.mkdir(parents=True)
        (root / ".gitattributes").write_text(
            "*.asset text\n",
            encoding="utf-8",
            newline="\n",
        )
        scene.write_text("root:\n  value: one\n", encoding="utf-8", newline="\n")
        coverage.write_text("{}\n", encoding="utf-8", newline="\n")
        generated_tile.write_text(
            "root:\n  value: one\n",
            encoding="utf-8",
            newline="\n",
        )
        git(root, "add", ".")
        git(root, "commit", "-m", "Create fixture")

        scene.write_text("root:   \n  value: one\t\n", encoding="utf-8", newline="\n")
        raw = status(root)
        assert classify_safe_post_unity_churn(raw, root) == (SCENE,)
        assert classify_safe_post_unity_churn(raw) is None

        scene.write_text("root:   \n  value: two\t\n", encoding="utf-8", newline="\n")
        assert classify_safe_post_unity_churn(status(root), root) is None

        scene.write_text("root:\n value: one   \n", encoding="utf-8", newline="\n")
        assert classify_safe_post_unity_churn(status(root), root) is None

        git(root, "restore", "--worktree", "--", SCENE)
        coverage.write_text('{"enabled": true}\n', encoding="utf-8", newline="\n")
        assert classify_safe_post_unity_churn(status(root), root) == (COVERAGE,)
        head = git(root, "rev-parse", "HEAD")
        assert recover_safe_post_unity_churn(root, head, apply=False) == (COVERAGE,)
        assert status(root)
        assert recover_safe_post_unity_churn(root, head, apply=True) == (COVERAGE,)
        assert status(root) == ""

        generated_tile.write_bytes(b"root:\r\n  value: one\r\n")
        assert classify_safe_post_unity_churn(
            f" M {GENERATED_TILE}\n", root
        ) == (GENERATED_TILE,)

        generated_tile.write_text(
            "root:\n  value: two\n",
            encoding="utf-8",
            newline="\n",
        )
        assert classify_safe_post_unity_churn(f" M {GENERATED_TILE}\n", root) is None
        try:
            recover_safe_post_unity_churn(root, head, apply=True)
        except SafeUnityChurnError:
            pass
        else:
            raise AssertionError("unsafe Unity churn was restored")
        assert "value: two" in generated_tile.read_text(encoding="utf-8")


def main() -> int:
    test_scene_requires_proven_trailing_whitespace_only_diff()
    print("PASS test_scene_requires_proven_trailing_whitespace_only_diff")
    print("safe Unity churn smoke tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
