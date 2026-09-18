"""Exact policy for recoverable post-Unity ProjectSettings churn.

Also exposes the ``refresh-identical`` subcommand (problem P18), which refreshes
Git's stale index stat cache for content-identical worktree churn outside the
named ProjectSettings/scene list handled by this module. See
:mod:`Pipeline.TaskReviewAgent.refresh_identical_churn` for that policy and why
it is a separate module.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

# This file is run by path as well as imported: run_unity_tests_clean.ps1 invokes
# `& python <path>/safe_unity_churn.py`, and the guides tell people to do the same. Python
# then puts this file's folder on sys.path, never the repository root, so the absolute
# import below cannot resolve without this bootstrap. The by-path regression test in
# tests/safe_unity_churn_smoke_test.py exists because that is how this broke.
_REPOSITORY_ROOT = str(Path(__file__).resolve().parents[2])
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from Pipeline.TaskReviewAgent.refresh_identical_churn import main as _refresh_identical_main  # noqa: E402


SAFE_POST_UNITY_CHURN_PATHS = frozenset(
    {
        "ProjectSettings/EditorBuildSettings.asset",
        "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json",
        "ProjectSettings/ProjectSettings.asset",
    }
)

SAFE_TRAILING_WHITESPACE_CHURN_PATHS = frozenset(
    {
        "Assets/Scenes/DoorPrototype.unity",
    }
)

# Only these three folders hold files the Unity Editor imports and rewrites.
# Anything else in the repository (Docs, Pipeline, CI, tooling) is authored by a
# human or an agent, so its trailing whitespace is content and never churn.
UNITY_SERIALIZED_ROOTS = ("Assets/", "ProjectSettings/", "Packages/")

# Suffixes the Unity text serializer writes. Unity emits YAML with trailing
# spaces on some mapping keys and re-emits them on every import, so a file with
# one of these suffixes can legitimately differ from HEAD at its line ends.
# Suffixes are matched case-insensitively because Unity and Windows both treat
# asset extensions that way (`Wall.MAT` is the same importer as `Wall.mat`).
UNITY_SERIALIZED_SUFFIXES = frozenset(
    {
        ".meta",  # importer settings Unity writes beside every asset
        ".asset",  # ScriptableObject and generated settings assets
        ".anim",  # AnimationClip
        ".controller",  # AnimatorController
        ".overridecontroller",  # AnimatorOverrideController
        ".prefab",  # prefab asset
        ".unity",  # scene asset
        ".mat",  # Material
        ".physicmaterial",  # 3D PhysicMaterial
        ".physicsmaterial2d",  # 2D PhysicsMaterial2D
        ".mask",  # AvatarMask
        ".playable",  # PlayableAsset / Timeline
        ".signal",  # Timeline SignalAsset
        ".spriteatlas",  # SpriteAtlas
        ".terrainlayer",  # TerrainLayer
        ".rendertexture",  # RenderTexture asset
        ".cubemap",  # Cubemap asset
        ".flare",  # LensFlare
        ".fontsettings",  # legacy Font asset settings
        ".guiskin",  # legacy IMGUI GUISkin
        ".mixer",  # AudioMixer
        ".preset",  # Preset asset
    }
)


class SafeUnityChurnError(RuntimeError):
    """Raised when exact post-Unity recovery cannot be proven safe."""


def _is_unity_serialized(path: str) -> bool:
    """Report whether Unity's text serializer owns this generated file.

    This is never sufficient on its own: a matching path still has to prove a
    trailing-whitespace-only difference before it becomes recoverable churn.
    """

    if not path.startswith(UNITY_SERIALIZED_ROOTS):
        return False
    return PurePosixPath(path).suffix.casefold() in UNITY_SERIALIZED_SUFFIXES


def _is_trailing_whitespace_only(root: Path, path: str) -> bool:
    """Prove that HEAD and the worktree differ only at line ends."""

    try:
        result = subprocess.run(
            (
                "git",
                "-C",
                str(root),
                "diff",
                "--ignore-space-at-eol",
                "--quiet",
                "HEAD",
                "--",
                path,
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return False
    return result.returncode == 0


def _is_index_equivalent(root: Path, path: str) -> bool:
    """Prove that Git would stage the worktree path as its existing index blob."""

    try:
        index = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "--verify", f":{path}"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        worktree = subprocess.run(
            (
                "git",
                "-C",
                str(root),
                "hash-object",
                "--path",
                path,
                "--",
                path,
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return False
    return (
        index.returncode == 0
        and worktree.returncode == 0
        and index.stdout.strip() == worktree.stdout.strip()
    )


def classify_safe_post_unity_churn(
    raw_status: str,
    repository: Path | str | None = None,
) -> tuple[str, ...] | None:
    """Return exact recoverable paths, or ``None`` for any unsafe status entry."""

    if type(raw_status) is not str:
        return None
    if raw_status == "":
        return ()

    paths: list[str] = []
    for line in raw_status.splitlines():
        if len(line) < 4 or line[2] != " ":
            return None
        status = line[:2]
        path = line[3:]
        allowed = path in SAFE_POST_UNITY_CHURN_PATHS
        if repository is not None and _is_index_equivalent(
            Path(repository).resolve(), path
        ):
            allowed = True
        if path in SAFE_TRAILING_WHITESPACE_CHURN_PATHS:
            allowed = repository is not None and _is_trailing_whitespace_only(
                Path(repository).resolve(), path
            )
        # Unity rewrites trailing whitespace into its own generated files on
        # every import, so prove that churn per file instead of hand-listing the
        # hundreds of metas, controllers and clips it touches. This only ever
        # widens the allowed set: a path already allowed above keeps its exact
        # existing disposition.
        if (
            not allowed
            and repository is not None
            and _is_unity_serialized(path)
            and _is_trailing_whitespace_only(Path(repository).resolve(), path)
        ):
            allowed = True
        if status != " M" or not allowed or path in paths:
            return None
        paths.append(path)
    return tuple(sorted(paths, key=str.casefold))


def _git_text(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *args),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SafeUnityChurnError("Git could not be invoked") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SafeUnityChurnError(
            f"Git command failed ({result.returncode}): {' '.join(args)}"
            + (f": {detail}" if detail else "")
        )
    return result.stdout.decode("utf-8", errors="strict").rstrip("\r\n")


def recover_safe_post_unity_churn(
    repository: Path | str,
    expected_head: str,
    *,
    apply: bool,
) -> tuple[str, ...]:
    """Inspect or restore only proven-safe worktree churn at an exact HEAD."""

    root = Path(repository).resolve()
    if not root.is_dir():
        raise SafeUnityChurnError(f"repository does not exist: {root}")
    actual_head = _git_text(root, "rev-parse", "HEAD")
    if actual_head != expected_head:
        raise SafeUnityChurnError(
            f"repository HEAD {actual_head!r} differs from expected {expected_head!r}"
        )
    raw = _git_text(
        root,
        "-c",
        "core.quotepath=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    paths = classify_safe_post_unity_churn(raw, root)
    if paths is None:
        raise SafeUnityChurnError(
            "repository contains post-Unity changes outside the exact safe-churn policy"
        )
    if paths and apply:
        _git_text(
            root,
            "restore",
            f"--source={expected_head}",
            "--worktree",
            "--",
            *paths,
        )
        # Git for Windows can retain a racy-stat modified marker after checkout
        # wrote the exact normalized index blob (notably for coverage Settings.json).
        # Re-hashing only the exact restored paths refreshes their index stat data;
        # the cached-diff check proves this did not stage a content change.
        _git_text(root, "add", "--", *paths)
        staged = _git_text(root, "diff", "--cached", "--name-only", "HEAD", "--")
        if staged:
            raise SafeUnityChurnError(
                f"exact-source recovery unexpectedly staged content: {staged!r}"
            )
        if _git_text(root, "rev-parse", "HEAD") != expected_head:
            raise SafeUnityChurnError("repository HEAD changed during safe-churn recovery")
        remaining = _git_text(
            root,
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if remaining:
            raise SafeUnityChurnError(
                "repository remained dirty after exact safe-churn recovery: "
                f"{remaining!r}"
            )
    return paths


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    if raw_argv[:1] == ["refresh-identical"]:
        return _refresh_identical_main(raw_argv[1:])

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(raw_argv)
    try:
        paths = recover_safe_post_unity_churn(
            args.repository,
            str(args.expected_head),
            apply=bool(args.apply),
        )
    except (SafeUnityChurnError, UnicodeError) as exc:
        print(f"SAFE UNITY CHURN: ERROR: {exc}")
        return 2
    print(
        json.dumps(
            {
                "status": "recovered" if paths and args.apply else "recoverable" if paths else "clean",
                "paths": list(paths),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
