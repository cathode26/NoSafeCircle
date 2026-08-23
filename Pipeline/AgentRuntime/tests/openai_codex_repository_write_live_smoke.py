#!/usr/bin/env python3
"""Opt-in live smoke for bounded Codex edits in a disposable repository."""

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
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider


def source_state() -> tuple[str, str]:
    commands = (["git", "rev-parse", "HEAD"],
                ["git", "status", "--porcelain=v1", "--untracked-files=all"])
    return tuple(subprocess.run(command, cwd=ROOT, check=True, capture_output=True,
                                text=True).stdout for command in commands)  # type: ignore[return-value]


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
    if os.environ.get("NSC_RUN_OPENAI_CODEX_WRITE_SMOKE") != "1":
        print("OpenAI Codex repository write live smoke: SKIP (set NSC_RUN_OPENAI_CODEX_WRITE_SMOKE=1)")
        return
    require_read_only_source_checkout()
    source_before = source_state()
    with tempfile.TemporaryDirectory(prefix="nsc-codex-write-smoke-") as text:
        base = Path(text)
        repository = base / "repo"
        repository.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
        (repository / "allowed").mkdir()
        (repository / "allowed/target.txt").write_text("before\n", encoding="utf-8")
        (repository / "denied.txt").write_text("unchanged\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        initial = tree(repository)
        request = AgentInvocationRequest(
            "1.0", "codex-write-live-smoke", "implementer",
            "Change allowed/target.txt so its exact contents are: after\\n. Do not change anything else. Return JSON.",
            ("allowed/target.txt",),
            ("repository_read", "repository_search", "repository_write"),
            WriteBoundaries(("allowed/target.txt",), ("denied.txt",)),
            {"type": "object", "properties": {"message": {"type": "string"}},
             "required": ["message"], "additionalProperties": False},
            "low_cost", Budgets(3, 90), "codex-write-smoke",
        )
        model = os.environ.get("NSC_OPENAI_CODEX_MODEL", "gpt-5.6-sol")
        configuration = RuntimeConfiguration({"codex-write-smoke": {
            "provider": "openai-codex", "models": {
                "low_cost": model,
                "standard": model,
                "high_reasoning": model,
            }}})
        provider = OpenAICodexProvider(
            reasoning_effort="low", repository_root=repository,
            externally_isolated_writable_repository=True, temporary_directory_parent=base)
        result = AgentRunner(base / "runs", configuration,
                             {"openai-codex": provider}).run(request)
        assert result.status == "succeeded", result.to_dict()
        after = tree(repository)
        assert (repository / "allowed/target.txt").read_bytes() == b"after\n"
        assert (repository / "denied.txt").read_bytes() == b"unchanged\n"
        assert set(after) == set(initial)
        assert {path for path in after if after[path] != initial[path]} == {"allowed/target.txt"}
        assert source_state() == source_before
    print("OpenAI Codex repository write live smoke: PASS")


if __name__ == "__main__":
    main()
