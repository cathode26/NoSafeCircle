#!/usr/bin/env python3
"""Deterministic smoke tests for the isolated history identity rewrite."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.HistoryMigration.history_identity import (  # noqa: E402
    DEFAULT_REPLACEMENTS,
    HistoryIdentityError,
    REPORT_NAME,
    dry_run,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> str:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        list(args),
        cwd=cwd,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def commit(repo: Path, message: str, email: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "Synthetic Agent",
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": "Synthetic Agent",
        "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": "2026-08-29T00:00:00-0500",
        "GIT_COMMITTER_DATE": "2026-08-29T00:00:00-0500",
    }
    run(repo, "git", "commit", "-m", message, env=env)
    return run(repo, "git", "rev-parse", "HEAD")


def test_isolated_tree_preserving_rewrite() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-history-identity-") as raw:
        root = Path(raw)
        repo = root / "repo"
        repo.mkdir()
        run(repo, "git", "init", "-b", "main")
        run(repo, "git", "config", "user.name", "Synthetic Human")
        run(repo, "git", "config", "user.email", "human@example.invalid")

        (repo / "state.txt").write_text("base\n", encoding="utf-8")
        run(repo, "git", "add", "state.txt")
        base = commit(repo, "base", "human@example.invalid")

        (repo / "state.txt").write_text("base\nresilience\n", encoding="utf-8")
        run(repo, "git", "add", "state.txt")
        bad_resilience = commit(
            repo,
            "unsafe resilience identity",
            "resilience@users.noreply.github.com",
        )

        run(repo, "git", "checkout", "-b", "side")
        (repo / "side.txt").write_text("side\n", encoding="utf-8")
        run(repo, "git", "add", "side.txt")
        bad_pipeline = commit(
            repo,
            "unsafe pipeline identity",
            "pipeline@users.noreply.github.com",
        )

        run(repo, "git", "checkout", "main")
        (repo / "main.txt").write_text("main\n", encoding="utf-8")
        run(repo, "git", "add", "main.txt")
        normal_descendant = commit(repo, "normal descendant", "human@example.invalid")
        run(
            repo,
            "git",
            "merge",
            "--no-ff",
            "side",
            "-m",
            "merge side",
            env={
                "GIT_AUTHOR_NAME": "Synthetic Human",
                "GIT_AUTHOR_EMAIL": "human@example.invalid",
                "GIT_COMMITTER_NAME": "Synthetic Human",
                "GIT_COMMITTER_EMAIL": "human@example.invalid",
                "GIT_AUTHOR_DATE": "2026-08-29T00:05:00-0500",
                "GIT_COMMITTER_DATE": "2026-08-29T00:05:00-0500",
            },
        )
        source_head = run(repo, "git", "rev-parse", "HEAD")
        source_tree = run(repo, "git", "rev-parse", "HEAD^{tree}")

        output = root / "dry-run"
        report = dry_run(
            source=repo,
            output=output,
            replacements=DEFAULT_REPLACEMENTS,
        )
        require(report["source_main"] == source_head, "source main identity changed")
        require(report["source_main_tree"] == source_tree, "source tree was recorded incorrectly")
        require(report["target_main_tree"] == source_tree, "target main tree was not preserved")
        require(report["trees_preserved"] is True, "tree preservation was not asserted")
        require(report["target_main"] != source_head, "rewritten main unexpectedly kept old SHA")
        require(run(repo, "git", "rev-parse", "HEAD") == source_head, "source HEAD was mutated")

        mapping = {row["old_commit"]: row for row in report["commit_map"]}
        require(base not in mapping, "unaffected ancestor should retain its exact SHA")
        require(bad_resilience in mapping, "resilience commit was not rewritten")
        require(bad_pipeline in mapping, "pipeline commit was not rewritten")
        require(normal_descendant in mapping, "descendant of rewritten commit was not rewritten")
        require(
            mapping[bad_resilience]["new_author_email"]
            == "resilience-fix@nosafecircle.invalid",
            "resilience author email was not sanitized",
        )
        require(
            mapping[bad_pipeline]["new_committer_email"]
            == "pipeline@nosafecircle.invalid",
            "pipeline committer email was not sanitized",
        )
        require(
            mapping[normal_descendant]["parent_changed"]
            and not mapping[normal_descendant]["author_identity_changed"],
            "normal descendant should change only because its parent changed",
        )

        mirror = output / "mirror.git"
        target_emails = run(
            mirror,
            "git",
            "log",
            "--format=%ae%n%ce",
            "refs/heads/main",
        ).splitlines()
        require(
            "resilience@users.noreply.github.com" not in target_emails,
            "rewritten main still contains the resilience identity",
        )
        require(
            "pipeline@users.noreply.github.com" not in target_emails,
            "rewritten main still contains the pipeline identity",
        )
        require((output / REPORT_NAME).exists(), "dry-run report was not written")
        parsed = json.loads((output / REPORT_NAME).read_text(encoding="utf-8"))
        require(
            parsed["report_sha256"] == report["report_sha256"],
            "persisted report changed after serialization",
        )

        try:
            dry_run(source=repo, output=output, replacements=DEFAULT_REPLACEMENTS)
        except HistoryIdentityError as exc:
            require("already exists" in str(exc), f"unexpected no-overwrite error: {exc}")
        else:
            raise AssertionError("dry-run output unexpectedly allowed overwrite")


def main() -> int:
    test_isolated_tree_preserving_rewrite()
    print("PASS test_isolated_tree_preserving_rewrite")
    print("History identity migration smoke tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
