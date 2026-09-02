"""Exact policy for recoverable post-Unity ProjectSettings churn."""

from __future__ import annotations


SAFE_POST_UNITY_CHURN_PATHS = frozenset(
    {
        "ProjectSettings/EditorBuildSettings.asset",
        "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json",
        "ProjectSettings/ProjectSettings.asset",
    }
)


def classify_safe_post_unity_churn(raw_status: str) -> tuple[str, ...] | None:
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
        if (
            status != " M"
            or path not in SAFE_POST_UNITY_CHURN_PATHS
            or path in paths
        ):
            return None
        paths.append(path)
    return tuple(sorted(paths, key=str.casefold))
