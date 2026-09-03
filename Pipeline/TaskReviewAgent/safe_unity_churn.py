"""Exact policy for recoverable post-Unity ProjectSettings churn."""

from __future__ import annotations

import subprocess
from pathlib import Path


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
        if path in SAFE_TRAILING_WHITESPACE_CHURN_PATHS:
            allowed = repository is not None and _is_trailing_whitespace_only(
                Path(repository).resolve(), path
            )
        if status != " M" or not allowed or path in paths:
            return None
        paths.append(path)
    return tuple(sorted(paths, key=str.casefold))
