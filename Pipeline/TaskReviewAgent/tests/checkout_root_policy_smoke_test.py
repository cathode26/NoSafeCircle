#!/usr/bin/env python3
"""Regression tests for the canonical short Windows checkout root.

The active operator convention is C:\\NSC\\NSC. The obsolete operational root
must not reappear in current code, tests, or documentation. Historical
pipeline evidence and the independently-configured ReferenceProjects policy
legitimately keep the old root and are allowlisted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.real_checkout import default_checkout_root  # noqa: E402


# Concatenated so this test file never matches its own forbidden token.
OBSOLETE_CHECKOUT_ROOT_TOKEN = "NoSafeCircle" + "AgentCrew"
CANONICAL_CHECKOUT_ROOT = Path(r"C:\NSC\NSC")

# Historical artifacts record where past runs actually occurred; the
# ReferenceProjects host root is governed by its own independent policy.
ALLOWED_PATH_PREFIXES = (
    "Pipeline/TaskGraph/evidence/",
    "Pipeline/ArchitectureReview/outputs/",
    "Pipeline/Reconciliation/outputs/",
)
ALLOWED_EXACT_PATHS = (
    "Docs/Engineering/REFERENCE_PROJECTS.md",
    "Pipeline/ReferenceSources/README.md",
    "Pipeline/ReferenceSources/reference_sources.json",
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _is_allowed(path: str) -> bool:
    if path in ALLOWED_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def test_default_checkout_root_is_canonical() -> None:
    saved = os.environ.pop("NSC_TASK_CHECKOUT_ROOT", None)
    try:
        require(
            default_checkout_root() == CANONICAL_CHECKOUT_ROOT,
            f"default checkout root must be {CANONICAL_CHECKOUT_ROOT}, "
            f"got {default_checkout_root()}",
        )
        os.environ["NSC_TASK_CHECKOUT_ROOT"] = r"D:\Elsewhere"
        require(
            default_checkout_root() == Path(r"D:\Elsewhere"),
            "NSC_TASK_CHECKOUT_ROOT override must win over the default root",
        )
    finally:
        if saved is None:
            os.environ.pop("NSC_TASK_CHECKOUT_ROOT", None)
        else:
            os.environ["NSC_TASK_CHECKOUT_ROOT"] = saved


def test_obsolete_checkout_root_is_absent_from_current_files() -> None:
    result = subprocess.run(
        ("git", "grep", "-l", "--fixed-strings", OBSOLETE_CHECKOUT_ROOT_TOKEN),
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=300.0,
    )
    require(
        result.returncode in (0, 1),
        "git grep failed: " + result.stderr.decode("utf-8", "replace").strip(),
    )
    matches = [
        line
        for line in result.stdout.decode("utf-8", "replace").splitlines()
        if line.strip()
    ]
    # Sanity: the allowlisted historical evidence still proves the scan works.
    require(
        any(_is_allowed(path) for path in matches),
        "scan found no occurrences at all; the forbidden-token scan is broken",
    )
    offenders = [path for path in matches if not _is_allowed(path)]
    require(
        not offenders,
        "obsolete checkout root "
        + OBSOLETE_CHECKOUT_ROOT_TOKEN
        + " appears outside allowlisted historical/independent areas: "
        + ", ".join(sorted(offenders)),
    )


def main() -> int:
    test_default_checkout_root_is_canonical()
    test_obsolete_checkout_root_is_absent_from_current_files()
    print("checkout_root_policy_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
