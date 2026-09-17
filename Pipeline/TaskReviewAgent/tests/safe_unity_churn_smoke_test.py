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
    UNITY_SERIALIZED_ROOTS,
    UNITY_SERIALIZED_SUFFIXES,
    SafeUnityChurnError,
    _is_trailing_whitespace_only,
    _is_unity_serialized,
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
DOCUMENT_META = "Docs/Foo.meta"
ASSETS_TEXT = "Assets/Foo.txt"
GAMEPLAY_SCRIPT = "Assets/NoSafeCircle/Gameplay/Runtime/EnemyHealth.cs"


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


def git_exit(root: Path, *args: str) -> int:
    """Run Git for its exit code, for predicates such as ``diff --quiet``."""

    return subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    ).returncode


def git_bytes(root: Path, *args: str) -> bytes:
    """Run Git and return exact stdout bytes, for blob content."""

    result = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def status(root: Path) -> str:
    return git(root, "status", "--porcelain=v1", "--untracked-files=all")


def write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def strip_trailing_whitespace(data: bytes) -> bytes:
    """Drop spaces, tabs and CR from the end of every line, keeping the newlines."""

    return b"\n".join(line.rstrip(b" \t\r") for line in data.split(b"\n"))


def write_bytes(root: Path, relative: str, data: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def build_fixture(
    root: Path,
    files: dict[str, str],
    binaries: dict[str, bytes] | None = None,
) -> str:
    """Commit an exact fixture tree and return its commit SHA."""

    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Safe Unity Churn Test")
    git(root, "config", "user.email", "safe-unity-churn@example.invalid")
    # These tests compare exact bytes, and they are about trailing whitespace, not line
    # endings. Windows' global core.autocrlf=true would restore CRLF into the worktree and
    # break that comparison, so every fixture repository pins it off.
    git(root, "config", "core.autocrlf", "false")
    for relative, text in files.items():
        write(root, relative, text)
    for relative, data in (binaries or {}).items():
        write_bytes(root, relative, data)
    git(root, "add", ".")
    git(root, "commit", "-m", "Create fixture")
    return git(root, "rev-parse", "HEAD")


GENERATED_UNITY_FIXTURE = {
    ENEMY_META: "fileFormatVersion: 2\nguid: 0123456789abcdef\n",
    ENEMY_CONTROLLER: "%YAML 1.1\nAnimatorController:\n  m_Name: Enemy\n",
    UPPERCASE_MATERIAL: "Material:\n  m_Name: Wall\n",
    PACKAGE_ASSET: "MonoBehaviour:\n  m_Name: EnemyConfig\n",
}

# The exact post-import churn the accepting test replays: every difference from
# GENERATED_UNITY_FIXTURE is at a line end.
GENERATED_UNITY_CHURN = {
    ENEMY_META: "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n",
    ENEMY_CONTROLLER: "%YAML 1.1\t\nAnimatorController:\n  m_Name: Enemy  \n",
    UPPERCASE_MATERIAL: "Material:   \n  m_Name: Wall\n",
    PACKAGE_ASSET: "MonoBehaviour: \n  m_Name: EnemyConfig  \n",
}

# A binary Unity scene, as Unity's binary serializer writes it: NUL bytes, no
# lines, and a fileID table that is re-emitted wholesale on import.
BINARY_SCENE_HEAD = b"UnityFS\x00\x05\x00\x00\x00sceneA\x00\x11\x22\x33\x44\x00"
BINARY_SCENE_REIMPORTED = b"UnityFS\x00\x05\x00\x00\x00sceneA\x00\x55\x66\x77\x88\x00"


def test_scene_requires_proven_trailing_whitespace_only_diff() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        git(root, "init", "--initial-branch=main")
        git(root, "config", "user.name", "Safe Unity Churn Test")
        git(root, "config", "user.email", "safe-unity-churn@example.invalid")
        # These tests compare exact bytes, and they are about trailing whitespace, not line
        # endings. Windows' global core.autocrlf=true would restore CRLF into the worktree and
        # break that comparison, so every fixture repository pins it off.
        git(root, "config", "core.autocrlf", "false")
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

        for relative, text in GENERATED_UNITY_CHURN.items():
            write(root, relative, text)

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


def test_accepted_churn_agrees_with_an_independent_byte_signal() -> None:
    """Two independent signals must agree that the accepted churn is EOL-only.

    A cheap proof can measure the wrong thing, so the exact fixture the accepting
    test recovers is also checked by hand: HEAD's blob and the worktree file must
    be byte-identical once trailing whitespace is stripped from every line. If the
    policy's Git proof and this byte comparison ever disagree, the accepting test
    is passing for a reason nobody has read.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        build_fixture(root, GENERATED_UNITY_FIXTURE)
        for relative, text in GENERATED_UNITY_CHURN.items():
            write(root, relative, text)

        for relative in GENERATED_UNITY_FIXTURE:
            # Signal one: the policy's own per-file `--ignore-space-at-eol` proof.
            assert _is_trailing_whitespace_only(root, relative) is True

            # Signal two: HEAD's committed blob against the worktree bytes, with
            # trailing whitespace stripped from each line of both. This never
            # consults Git's diff machinery, so it cannot inherit its mistakes.
            committed = git_bytes(root, "show", f"HEAD:{relative}")
            current = (root / relative).read_bytes()
            assert committed != current
            assert strip_trailing_whitespace(committed) == strip_trailing_whitespace(
                current
            )


def test_binary_scene_churn_is_refused_and_must_not_be_hand_listed() -> None:
    """A binary Unity scene stays refused, and widening the policy to admit it is wrong.

    `Assets/Scenes/DoorPrototype.unity` is saved with Unity's binary serializer in
    this project. Its churn is fileID regeneration, not trailing whitespace, so no
    diff of it is ever whitespace-only and restoring it from HEAD would silently
    discard a re-serialized scene. The `.unity` suffix is already in the allowed
    Unity-serialized family and the path is already in
    SAFE_TRAILING_WHITESPACE_CHURN_PATHS, so the per-file `--ignore-space-at-eol`
    proof is the only thing keeping this file out of the recoverable set. Do not
    "fix" this refusal by hand-listing the path or by trusting the suffix; the
    refusal is the policy working.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        fixture = dict(GENERATED_UNITY_FIXTURE)
        fixture[".gitattributes"] = f"{SCENE} binary\n"
        head = build_fixture(root, fixture, {SCENE: BINARY_SCENE_HEAD})

        write_bytes(root, SCENE, BINARY_SCENE_REIMPORTED)
        assert (root / SCENE).read_bytes() != BINARY_SCENE_HEAD
        assert classify_safe_post_unity_churn(f" M {SCENE}\n", root) is None

        # A text-serialized sibling with the same allowed suffix family is still
        # recoverable, so the refusal above is the per-file proof and not the
        # fixture failing to register as churn at all.
        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n")
        assert classify_safe_post_unity_churn(f" M {ENEMY_META}\n", root) == (ENEMY_META,)
        assert classify_safe_post_unity_churn(status(root), root) is None

        try:
            recover_safe_post_unity_churn(root, head, apply=True)
        except SafeUnityChurnError:
            pass
        else:
            raise AssertionError("a re-serialized binary scene was restored from HEAD")
        assert (root / SCENE).read_bytes() == BINARY_SCENE_REIMPORTED


def test_whitespace_change_away_from_the_line_end_is_refused() -> None:
    """Indentation-only churn stays refused: the stricter EOL signal is deliberate.

    `git diff -w` ignores whitespace everywhere and would report this file as
    unchanged, which would let the review agent throw away a real re-indentation.
    The policy proves churn with `--ignore-space-at-eol` instead, which only
    forgives difference at a line end. The narrower signal is the design; do not
    relax it to `-w` or `--ignore-all-space` to make a dirty tree go away.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        head = build_fixture(root, GENERATED_UNITY_FIXTURE)

        # Four spaces instead of two, and no trailing-whitespace difference at all.
        write(root, ENEMY_CONTROLLER, "%YAML 1.1\nAnimatorController:\n    m_Name: Enemy\n")

        # The two signals disagree on purpose: `-w` sees nothing, the policy does.
        assert git_exit(root, "diff", "-w", "--quiet", "HEAD", "--", ENEMY_CONTROLLER) == 0
        assert (
            git_exit(
                root,
                "diff",
                "--ignore-space-at-eol",
                "--quiet",
                "HEAD",
                "--",
                ENEMY_CONTROLLER,
            )
            == 1
        )

        assert _is_trailing_whitespace_only(root, ENEMY_CONTROLLER) is False
        assert classify_safe_post_unity_churn(status(root), root) is None
        assert classify_safe_post_unity_churn(f" M {ENEMY_CONTROLLER}\n", root) is None

        try:
            recover_safe_post_unity_churn(root, head, apply=True)
        except SafeUnityChurnError:
            pass
        else:
            raise AssertionError("an indentation-only change was restored from HEAD")
        assert (
            (root / ENEMY_CONTROLLER).read_text(encoding="utf-8")
            == "%YAML 1.1\nAnimatorController:\n    m_Name: Enemy\n"
        )


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


def test_unity_serialized_suffixes_are_pinned() -> None:
    """The suffix inventory is frozen here on purpose, not merely sampled.

    Every suffix below is written by Unity's own text serializer, which is the
    only reason a file carrying it may differ from HEAD at its line ends and
    still be thrown away and restored from HEAD. A suffix authored by a human or
    an agent -- `.cs`, `.asmdef`, `.json`, `.md` -- has no such guarantee: its
    trailing whitespace is content, and recovery would silently discard real
    uncommitted work while reporting the tree clean.

    So widening this set is a deliberate act that must edit both the policy and
    this assertion, with a stated reason for why Unity writes the new suffix. It
    must never be a quiet append made to get a dirty tree past the review agent.
    """

    assert UNITY_SERIALIZED_SUFFIXES == frozenset(
        {
            ".meta",
            ".asset",
            ".anim",
            ".controller",
            ".overridecontroller",
            ".prefab",
            ".unity",
            ".mat",
            ".physicmaterial",
            ".physicsmaterial2d",
            ".mask",
            ".playable",
            ".signal",
            ".spriteatlas",
            ".terrainlayer",
            ".rendertexture",
            ".cubemap",
            ".flare",
            ".fontsettings",
            ".guiskin",
            ".mixer",
            ".preset",
        }
    )

    # What the pin buys: a gameplay script is a hand-authored file that happens
    # to live under Assets/, so trailing-whitespace churn in it stays refused.
    assert _is_unity_serialized(GAMEPLAY_SCRIPT) is False

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        fixture = dict(GENERATED_UNITY_FIXTURE)
        fixture[GAMEPLAY_SCRIPT] = "public sealed class EnemyHealth\n{\n}\n"
        build_fixture(root, fixture)

        # A human edit that also happens to be trailing-whitespace-only: were
        # `.cs` in the set above, recovery would restore HEAD over it.
        write(root, GAMEPLAY_SCRIPT, "public sealed class EnemyHealth  \n{\n}\t\n")
        assert _is_trailing_whitespace_only(root, GAMEPLAY_SCRIPT) is True
        assert classify_safe_post_unity_churn(status(root), root) is None
        assert classify_safe_post_unity_churn(f" M {GAMEPLAY_SCRIPT}\n", root) is None


def test_unity_suffix_outside_the_unity_roots_is_refused() -> None:
    """The root guard is pinned, and proven with a Unity suffix in the wrong folder.

    `Docs/Foo.meta` carries an allowed Unity suffix, so the only thing refusing
    it is the root guard. A file outside `Assets/`, `ProjectSettings/` and
    `Packages/` is never touched by the Unity Editor's importer, so its trailing
    whitespace is authored content whatever it is named. Widening the roots --
    to `("",)`, to `Docs/`, to `Pipeline/` -- would let recovery restore HEAD
    over a hand-written file, so the tuple is asserted exactly here.
    """

    assert UNITY_SERIALIZED_ROOTS == ("Assets/", "ProjectSettings/", "Packages/")
    assert _is_unity_serialized(DOCUMENT_META) is False

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        fixture = dict(GENERATED_UNITY_FIXTURE)
        fixture[DOCUMENT_META] = "fileFormatVersion: 2\nguid: 0123456789abcdef\n"
        build_fixture(root, fixture)

        # The identical suffix and the identical churn under an allowed root is
        # recoverable, so the refusal below is the root and not the suffix.
        write(root, ENEMY_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n")
        assert classify_safe_post_unity_churn(status(root), root) == (ENEMY_META,)

        write(root, DOCUMENT_META, "fileFormatVersion: 2  \nguid: 0123456789abcdef\t\n")
        assert _is_trailing_whitespace_only(root, DOCUMENT_META) is True
        assert classify_safe_post_unity_churn(status(root), root) is None
        assert classify_safe_post_unity_churn(f" M {DOCUMENT_META}\n", root) is None


def test_a_lost_final_newline_is_deliberately_accepted_as_end_of_line_churn() -> None:
    """A generated file that lost its final newline is recoverable, on purpose.

    `--ignore-space-at-eol` forgives the "\\ No newline at end of file" marker,
    so HEAD's `"...guid: 0123456789abcdef\\n"` against a worktree
    `"...guid: 0123456789abcdef"` classifies as end-of-line churn even though no
    trailing space or tab is involved. This is recorded rather than fixed
    because the direction is safe: recovery restores the file from HEAD, so the
    missing newline is put back and nothing authored is lost. The refusal that
    matters -- a real content difference -- is unaffected.

    If this test ever starts failing, the policy's EOL signal changed. Re-read
    it before widening anything; do not delete this test to make it green.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-safe-unity-churn-") as temporary:
        root = Path(temporary)
        head = build_fixture(root, GENERATED_UNITY_FIXTURE)
        committed = GENERATED_UNITY_FIXTURE[ENEMY_META]
        assert committed.endswith("\n")

        write(root, ENEMY_META, committed.rstrip("\n"))
        assert (root / ENEMY_META).read_bytes() == committed.rstrip("\n").encode("utf-8")

        # Git sees a real difference; the policy's EOL-tolerant proof does not.
        assert git_exit(root, "diff", "--quiet", "HEAD", "--", ENEMY_META) == 1
        assert _is_trailing_whitespace_only(root, ENEMY_META) is True
        assert classify_safe_post_unity_churn(status(root), root) == (ENEMY_META,)

        # Recovery repairs the file from HEAD, which is why this is tolerable.
        assert recover_safe_post_unity_churn(root, head, apply=True) == (ENEMY_META,)
        assert (root / ENEMY_META).read_bytes() == committed.encode("utf-8")
        assert status(root) == ""


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
        test_accepted_churn_agrees_with_an_independent_byte_signal,
        test_binary_scene_churn_is_refused_and_must_not_be_hand_listed,
        test_whitespace_change_away_from_the_line_end_is_refused,
        test_generated_unity_files_refuse_real_content_change,
        test_documentation_whitespace_churn_is_refused,
        test_non_unity_suffix_under_assets_is_refused,
        test_unity_serialized_suffixes_are_pinned,
        test_unity_suffix_outside_the_unity_roots_is_refused,
        test_a_lost_final_newline_is_deliberately_accepted_as_end_of_line_churn,
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
