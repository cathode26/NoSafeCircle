from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import uuid

import architecture_review as base
import architecture_review_resume as resumable

if str(base.ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(base.ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import AgentInvocationRequest, Budgets, WriteBoundaries
from Pipeline.AgentRuntime.providers.claude_code import ClaudeCodeProvider


MODEL_POOL = [
    value.strip()
    for value in os.environ.get("ARCH_REVIEW_MODELS", "claude-sonnet-5").split(",")
    if value.strip()
]
SYNTHESIS_MODEL = (
    os.environ.get("ARCH_REVIEW_SYNTHESIS_MODEL", "claude-sonnet-5").strip()
    or "claude-sonnet-5"
)
ADVERSARY_MODEL = (
    os.environ.get("ARCH_REVIEW_ADVERSARY_MODEL", "claude-sonnet-5").strip()
    or "claude-sonnet-5"
)
PROVIDER_CONFIGURATION_KEY = "architecture-review-claude"

if not MODEL_POOL:
    raise RuntimeError("ARCH_REVIEW_MODELS must contain at least one model.")

_architecture_run_dir: Path | None = None
_provider_factory = ClaudeCodeProvider
_runner_factory = AgentRunner


def configure_invocation_run_root(run_dir: Path) -> None:
    global _architecture_run_dir
    _architecture_run_dir = Path(run_dir)


def role_key_for(agent_name: str) -> str:
    if agent_name == "Architecture Synthesis":
        return "architecture_synthesis"
    if agent_name == "Adversarial Synthesis Critic":
        return "adversarial_synthesis_critic"
    for role in base.ROLE_SPECS:
        if role["name"] == agent_name:
            return str(role["key"])
    return "architecture_review_agent"


def _configuration(model: str) -> RuntimeConfiguration:
    return RuntimeConfiguration({
        PROVIDER_CONFIGURATION_KEY: {
            "provider": "claude-code",
            "models": {
                "low_cost": model,
                "standard": model,
                "high_reasoning": model,
            },
        }
    })


def invoke_claude_agent(
    *,
    agent_name: str,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    max_turns: int,
) -> dict[str, Any]:
    if _architecture_run_dir is None:
        raise RuntimeError("ArchitectureReview AgentRuntime artifact root is not configured.")

    role = role_key_for(agent_name)
    run_id = f"{role.replace('_', '-')}-{uuid.uuid4().hex[:16]}"
    capability_class = (
        "high_reasoning"
        if agent_name in {"Architecture Synthesis", "Adversarial Synthesis Critic"}
        else "standard"
    )
    request = AgentInvocationRequest(
        "1.0",
        run_id,
        role,
        prompt,
        tuple(base.ARCHITECTURE_DOCS),
        ("repository_read", "repository_search"),
        WriteBoundaries((), ()),
        schema,
        capability_class,
        Budgets(max_turns, base.REVIEW_TIMEOUT, None),
        PROVIDER_CONFIGURATION_KEY,
    )
    provider = _provider_factory()
    artifact_root = _architecture_run_dir / "agent_runtime"
    runner = _runner_factory(
        artifact_root,
        _configuration(model),
        {"claude-code": provider},
    )
    print(f"Starting: {agent_name} [{model}, invocation={run_id}]")
    result = runner.run(request)
    artifact_path = (artifact_root / run_id).relative_to(base.ROOT).as_posix()
    if result.status != "succeeded":
        raise RuntimeError(
            f"{agent_name} [{model}] AgentRuntime invocation {run_id} failed "
            f"({result.failure_classification}): {result.failure_message}; "
            f"artifacts: {artifact_path}"
        )
    print(f"Completed: {agent_name} [{model}] in {result.duration_seconds:.2f}s")
    return {
        "agent": agent_name,
        "provider": result.provider,
        "model": result.model,
        "duration_seconds": round(result.duration_seconds, 2),
        "agent_runtime_run_id": run_id,
        "agent_runtime_artifacts": artifact_path,
        "result": result.to_dict()["structured_output"],
    }


def configure_base_runner() -> None:
    base.configure_provider_namespace("claude")
    base.MODEL_POOL = MODEL_POOL
    base.SYNTHESIS_MODEL = SYNTHESIS_MODEL
    base.ADVERSARY_MODEL = ADVERSARY_MODEL
    base.invoke_read_only_agent = invoke_claude_agent
    base.configure_invocation_run_root = configure_invocation_run_root


def main() -> int:
    configure_base_runner()
    return resumable.main()


configure_base_runner()

if __name__ == "__main__":
    raise SystemExit(main())
