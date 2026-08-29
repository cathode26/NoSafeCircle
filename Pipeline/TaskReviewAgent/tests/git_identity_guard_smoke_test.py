#!/usr/bin/env python3
"""Regression tests for non-attributable automated Git identities."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.candidate_integration import CandidateIntegrator  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_pipeline import DownstreamTaskController  # noqa: E402
from Pipeline.TaskReviewAgent.git_identity_guard import (  # noqa: E402
    DEFAULT_AGENT_GIT_EMAIL,
    DEFAULT_AGENT_GIT_NAME,
    GitIdentityGuardError,
    validated_agent_git_identity,
)


GITHUB_USER_NOREPLY_DOMAIN = "users." + "noreply.github.com"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


@contextmanager
def agent_identity_environment(*, name: str | None, email: str | None) -> Iterator[None]:
    old_name = os.environ.get("NSC_AGENT_GIT_NAME")
    old_email = os.environ.get("NSC_AGENT_GIT_EMAIL")
    try:
        if name is None:
            os.environ.pop("NSC_AGENT_GIT_NAME", None)
        else:
            os.environ["NSC_AGENT_GIT_NAME"] = name
        if email is None:
            os.environ.pop("NSC_AGENT_GIT_EMAIL", None)
        else:
            os.environ["NSC_AGENT_GIT_EMAIL"] = email
        yield
    finally:
        if old_name is None:
            os.environ.pop("NSC_AGENT_GIT_NAME", None)
        else:
            os.environ["NSC_AGENT_GIT_NAME"] = old_name
        if old_email is None:
            os.environ.pop("NSC_AGENT_GIT_EMAIL", None)
        else:
            os.environ["NSC_AGENT_GIT_EMAIL"] = old_email


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git command failed: {' '.join(args)}\n"
            f"{result.stdout.decode('utf-8', 'replace')}\n"
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout.decode("utf-8", "replace").strip()


def test_default_identity_is_reserved_and_non_attributable() -> None:
    with agent_identity_environment(name=None, email=None):
        name, email = validated_agent_git_identity()
    require(name == DEFAULT_AGENT_GIT_NAME, "unexpected default automation name")
    require(email == DEFAULT_AGENT_GIT_EMAIL, "unexpected default automation email")
    require(email.endswith(".invalid"), "default automation email must use a reserved .invalid domain")
    require(not email.casefold().endswith("@" + GITHUB_USER_NOREPLY_DOMAIN), "default email maps to GitHub user namespace")


def test_github_user_noreply_override_fails_closed() -> None:
    dangerous = "invented-bot@" + GITHUB_USER_NOREPLY_DOMAIN
    with agent_identity_environment(name="Invented Bot", email=dangerous):
        try:
            validated_agent_git_identity()
        except GitIdentityGuardError as exc:
            require("noreply" in str(exc).casefold(), "rejection did not explain noreply risk")
        else:
            raise AssertionError("GitHub user noreply automation identity was accepted")


def test_installed_guard_overrides_stale_checkout_identity() -> None:
    require(
        CandidateIntegrator._ensure_git_identity.__module__.endswith("git_identity_guard"),
        "CandidateIntegrator identity guard is not installed",
    )
    require(
        DownstreamTaskController._ensure_git_identity.__module__.endswith("git_identity_guard"),
        "DownstreamTaskController identity guard is not installed",
    )

    with tempfile.TemporaryDirectory(prefix="nsc-git-identity-") as temporary:
        repo = Path(temporary) / "repo"
        repo.mkdir()
        git(repo, "init")
        git(repo, "config", "user.name", "Stale Automation")
        git(repo, "config", "user.email", "resilience@" + GITHUB_USER_NOREPLY_DOMAIN)

        with agent_identity_environment(name=None, email=None):
            CandidateIntegrator._ensure_git_identity(SimpleNamespace(checkout=repo))

        require(git(repo, "config", "user.name") == DEFAULT_AGENT_GIT_NAME, "stale Git name was not replaced")
        require(git(repo, "config", "user.email") == DEFAULT_AGENT_GIT_EMAIL, "stale Git email was not replaced")


def test_workflows_do_not_invent_github_noreply_identities() -> None:
    forbidden = ("@" + GITHUB_USER_NOREPLY_DOMAIN).encode("utf-8")
    workflow_root = ROOT / ".github" / "workflows"
    paths = sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
    require(bool(paths), "workflow policy test found no workflows")
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in paths
        if forbidden.casefold() in path.read_bytes().lower()
    ]
    require(not offenders, "workflow contains account-attributable GitHub noreply identity: " + ", ".join(offenders))


def main() -> int:
    test_default_identity_is_reserved_and_non_attributable()
    test_github_user_noreply_override_fails_closed()
    test_installed_guard_overrides_stale_checkout_identity()
    test_workflows_do_not_invent_github_noreply_identities()
    print("git_identity_guard_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
