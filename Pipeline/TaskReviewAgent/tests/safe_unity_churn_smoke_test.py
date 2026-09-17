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
EDITOR_BUILD_SETTINGS = "ProjectSettings/EditorBuildSettings.asset"
PROJECT_SETTINGS = "ProjectSettings/ProjectSettings.asset"
ENEMY_META = "Assets/Art/Enemies/Foo.png.meta"
ENEMY_CONTROLLER = "Assets/Animation/Enemy.controller"
UPPERCASE_MATERIAL = "Assets/Materials/Wall.MAT"
PACKAGE_ASSET = "Packages/com.example.enemies/Runtime/EnemyConfig.asset"
DOCUMENT = "Docs/Foo.md"
ASSETS_TEXT = "Assets/Foo.txt"


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


def write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def build_fixture(root: Path, files: dict[str, str]) -> str:
    """Commit an exact fixture tree and return its commit SHA."""

    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Safe Unity Churn Test")
    git(root, "config", "user.email", "safe-unity-churn@example.invalid")
    for relative, text in files.items():
        write(root, relative, text)
    git(root, "add", ".")
    git(root, "commit", "-m", "Create fixture")
    return git(root, "rev-parse", "HEAD")


GENERATED_UNITY_FIXTURE = {
    ENEMY_META: "fileFormatVersion: 2\nguid: 0123456789abcdef\n",
    ENEMY_CONTROLLER: "%YAML 1.1\nAnimatorController:\n  m_Name: Enemy\n",
    UPPERCASE_MATERIAL: "Material:\n  m_Name: Wall\n",
    PACKAGE_ASSET: "MonoBehaviour:\n  m_Name: EnemyConfig\n",
}


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


def test_generated_unity_files_accept_trailing_whitespace_churn() -> None:
    """Unity-serialized generated files are recoverable without a hand-listed path."""

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        head = build_fixture(root, GENERATED_UNITY_FIXTURE)

        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n")
        write(root, ENEMY_CONTROLLER, "%YAML 1.1\t\nAnimatorController:\n  m_Name: Enemy  \n")
        write(root, UPPERCASE_MATERIAL, "Material:   \n  m_Name: Wall\n")
        write(root, PACKAGE_ASSET, "MonoBehaviour: \n  m_Name: EnemyConfig  \n")

        expected = (ENEMY_CONTROLLER, ENEMY_META, UPPERCASE_MATERIAL, PACKAGE_ASSET)
        raw = status(root)
        assert classify_safe_post_unity_churn(raw, root) == expected
        assert classify_safe_post_unity_churn(raw) is None

        assert recover_safe_post_unity_churn(root, head, apply=False) == expected
        assert status(root)
        assert recover_safe_post_unity_churn(root, head, apply=True) == expected
        assert status(root) == ""
        for relative, text in GENERATED_UNITY_FIXTURE.items():
            assert (root / relative).read_text(encoding="utf-8") == text


def test_generated_unity_files_refuse_real_content_change() -> None:
    """A real content difference in the same generated files stays refused."""

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        head = build_fixture(root, GENERATED_UNITY_FIXTURE)

        # Trailing whitespace alone is recoverable, so the refusals below isolate
        # the real content difference rather than the file itself.
        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\n")
        assert classify_safe_post_unity_churn(status(root), root) == (ENEMY_META,)

        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: fedcba9876543210\n")
        assert classify_safe_post_unity_churn(status(root), root) is None

        git(root, "restore", "--worktree", "--", ENEMY_META)
        write(root, ENEMY_CONTROLLER, "%YAML 1.1\nAnimatorController:\n  m_Name: Boss\n")
        assert classify_safe_post_unity_churn(status(root), root) is None
        try:
            recover_safe_post_unity_churn(root, head, apply=True)
        except SafeUnityChurnError:
            pass
        else:
            raise AssertionError("a real generated-file content change was restored")
        assert "m_Name: Boss" in (root / ENEMY_CONTROLLER).read_text(encoding="utf-8")


def test_documentation_whitespace_churn_is_refused() -> None:
    """A Markdown file is not Unity-serialized, so whitespace churn stays refused."""

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        fixture = dict(GENERATED_UNITY_FIXTURE)
        fixture[DOCUMENT] = "# Foo\n\nBody\n"
        build_fixture(root, fixture)

        # The same churn shape in a Unity-serialized file is recoverable.
        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n")
        assert classify_safe_post_unity_churn(status(root), root) == (ENEMY_META,)

        write(root, DOCUMENT, "# Foo  \n\nBody\t\n")
        assert classify_safe_post_unity_churn(status(root), root) is None
        assert classify_safe_post_unity_churn(f" M {DOCUMENT}\n", root) is None


def test_non_unity_suffix_under_assets_is_refused() -> None:
    """A file under Assets/ with a suffix Unity does not serialize stays refused."""

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        fixture = dict(GENERATED_UNITY_FIXTURE)
        fixture[ASSETS_TEXT] = "note\n"
        build_fixture(root, fixture)

        # Same folder, same churn: only the suffix decides.
        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n")
        assert classify_safe_post_unity_churn(status(root), root) == (ENEMY_META,)

        write(root, ASSETS_TEXT, "note   \n")
        assert classify_safe_post_unity_churn(status(root), root) is None
        assert classify_safe_post_unity_churn(f" M {ASSETS_TEXT}\n", root) is None


def test_untracked_added_and_deleted_generated_files_are_refused() -> None:
    """Only an unstaged modification of an existing generated file is recoverable."""

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        build_fixture(root, GENERATED_UNITY_FIXTURE)

        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n")
        assert classify_safe_post_unity_churn(status(root), root) == (ENEMY_META,)

        write(root, "Assets/Art/Enemies/Bar.png.meta", "fileFormatVersion: 2\n")
        assert classify_safe_post_unity_churn(status(root), root) is None
        assert (
            classify_safe_post_unity_churn("?? Assets/Art/Enemies/Bar.png.meta\n", root)
            is None
        )

        git(root, "add", "--", "Assets/Art/Enemies/Bar.png.meta")
        assert classify_safe_post_unity_churn(status(root), root) is None
        git(root, "rm", "--cached", "--", "Assets/Art/Enemies/Bar.png.meta")
        (root / "Assets/Art/Enemies/Bar.png.meta").unlink()
        git(root, "restore", "--worktree", "--", ENEMY_META)

        (root / ENEMY_CONTROLLER).unlink()
        assert classify_safe_post_unity_churn(status(root), root) is None
        assert classify_safe_post_unity_churn(f" D {ENEMY_CONTROLLER}\n", root) is None
        assert classify_safe_post_unity_churn(f" M {ENEMY_META}\n M {ENEMY_META}\n", root) is None


def test_existing_safe_churn_paths_remain_allowed() -> None:
    """The hand-listed sets keep their exact behaviour under the generated-file policy."""

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        fixture = dict(GENERATED_UNITY_FIXTURE)
        fixture[SCENE] = "root:\n  value: one\n"
        fixture[COVERAGE] = "{}\n"
        fixture[EDITOR_BUILD_SETTINGS] = "EditorBuildSettings:\n  m_Scenes: []\n"
        fixture[PROJECT_SETTINGS] = "PlayerSettings:\n  productName: NoSafeCircle\n"
        head = build_fixture(root, fixture)

        # The unconditional set still tolerates a real content change.
        write(root, COVERAGE, '{"enabled": true}\n')
        write(root, EDITOR_BUILD_SETTINGS, "EditorBuildSettings:\n  m_Scenes: [main]\n")
        write(root, PROJECT_SETTINGS, "PlayerSettings:\n  productName: Renamed\n")
        # The trailing-whitespace set still requires a proven whitespace-only diff.
        write(root, SCENE, "root:   \n  value: one\t\n")
        # A generated enemy file joins the same recoverable batch.
        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\n")

        expected = (
            ENEMY_META,
            SCENE,
            EDITOR_BUILD_SETTINGS,
            PROJECT_SETTINGS,
            COVERAGE,
        )
        assert classify_safe_post_unity_churn(status(root), root) == tuple(
            sorted(expected, key=str.casefold)
        )
        assert recover_safe_post_unity_churn(root, head, apply=True) == tuple(
            sorted(expected, key=str.casefold)
        )
        assert status(root) == ""

        # The trailing-whitespace set still refuses a real content change.
        write(root, SCENE, "root:\n  value: two\n")
        assert classify_safe_post_unity_churn(status(root), root) is None


def main() -> int:
    tests = (
        test_scene_requires_proven_trailing_whitespace_only_diff,
        test_generated_unity_files_accept_trailing_whitespace_churn,
        test_generated_unity_files_refuse_real_content_change,
        test_documentation_whitespace_churn_is_refused,
        test_non_unity_suffix_under_assets_is_refused,
        test_untracked_added_and_deleted_generated_files_are_refused,
        test_existing_safe_churn_paths_remain_allowed,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"safe Unity churn smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
