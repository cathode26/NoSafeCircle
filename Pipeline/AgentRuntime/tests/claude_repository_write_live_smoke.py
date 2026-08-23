#!/usr/bin/env python3
"""Opt-in live smoke for bounded Claude edits in a disposable repository."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import AgentInvocationRequest, Budgets, WriteBoundaries
from Pipeline.AgentRuntime.providers import ClaudeCodeProvider


def source_state() -> tuple[str, str]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout
    status = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                            cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return head, status


def tree(path: Path) -> dict[str, str]:
    return {item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in path.rglob("*") if item.is_file() and ".git" not in item.parts}


def require_read_only_source_checkout() -> None:
    try:
        flags = os.statvfs(ROOT.resolve(strict=True)).f_flag
        read_only_flag = os.ST_RDONLY
    except (AttributeError, OSError, RuntimeError) as exc:
        raise RuntimeError("could not verify that the real source checkout is read-only") from exc
    if not flags & read_only_flag:
        raise RuntimeError("real source checkout must be mounted read-only for this live smoke")


def main() -> None:
    if os.environ.get("NSC_RUN_CLAUDE_WRITE_SMOKE") != "1":
        print("Claude repository write live smoke: SKIP (set NSC_RUN_CLAUDE_WRITE_SMOKE=1)")
        return
    require_read_only_source_checkout()
    source_before = source_state()
    with tempfile.TemporaryDirectory(prefix="nsc-claude-write-smoke-") as text:
        base = Path(text)
        repository = base / "repo"
        repository.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
        (repository / "allowed").mkdir()
        (repository / "allowed/target.txt").write_text("before\n", encoding="utf-8")
        (repository / "denied.txt").write_text("unchanged\n", encoding="utf-8")
        (repository / ".claude").mkdir()
        (repository / ".claude/settings.local.json").write_text(
            '{"permissions":{"allow":["Read(./allowed/target.txt)"]}}\n',
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=AgentRuntime Smoke", "-c",
                "user.email=agent-runtime-smoke@example.invalid", "commit", "--quiet",
                "-m", "Initial disposable fixture",
            ],
            cwd=repository,
            check=True,
        )
        initial = tree(repository)
        request = AgentInvocationRequest(
            "1.0", "claude-write-live-smoke", "implementer",
            "Change allowed/target.txt so its exact contents are: after\\n. Do not change anything else. Return JSON.",
            ("allowed/target.txt",),
            ("repository_read", "repository_search", "repository_write"),
            WriteBoundaries(("allowed/target.txt",), ("denied.txt",)),
            {"type": "object", "properties": {"message": {"type": "string"}},
             "required": ["message"], "additionalProperties": False},
            "low_cost", Budgets(5, 90), "claude-write-smoke",
        )
        model = os.environ.get("NSC_CLAUDE_MODEL", "claude-sonnet-5")
        configuration = RuntimeConfiguration({"claude-write-smoke": {
            "provider": "claude-code", "models": {
                "low_cost": model,
                "standard": model,
                "high_reasoning": model,
            }}})
        result = AgentRunner(base / "runs", configuration, {"claude-code": ClaudeCodeProvider(
            repository_root=repository, externally_isolated_writable_repository=True,
            temporary_directory_parent=base)}).run(request)
        if result.status != "succeeded":
            provider_log = base / "runs" / request.run_id / "provider.log"
            if provider_log.is_file():
                print("Preserved AgentRuntime provider.log:", file=sys.stderr)
                print(provider_log.read_text("utf-8"), file=sys.stderr)
        assert result.status == "succeeded", result.to_dict()
        after = tree(repository)
        assert (repository / "allowed/target.txt").read_bytes() == b"after\n"
        assert (repository / "denied.txt").read_bytes() == b"unchanged\n"
        assert set(after) == set(initial)
        assert {path for path in after if after[path] != initial[path]} == {"allowed/target.txt"}
        assert source_state() == source_before
    print("Claude repository write live smoke: PASS")


if __name__ == "__main__":
    main()
