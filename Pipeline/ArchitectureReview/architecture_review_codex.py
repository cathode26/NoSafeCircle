from __future__ import annotations

import os
from pathlib import Path
import uuid
from typing import Any

import architecture_review as base
import architecture_review_resume as resumable

if str(base.ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(base.ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import AgentInvocationRequest, Budgets, WriteBoundaries
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider

_shared_common_review_prompt = base.common_review_prompt
MODEL_POOL = [v.strip() for v in os.environ.get("ARCH_REVIEW_MODELS", "gpt-5.6-sol").split(",") if v.strip()]
SYNTHESIS_MODEL = os.environ.get("ARCH_REVIEW_SYNTHESIS_MODEL", "gpt-5.6-sol").strip() or "gpt-5.6-sol"
ADVERSARY_MODEL = os.environ.get("ARCH_REVIEW_ADVERSARY_MODEL", "gpt-5.6-sol").strip() or "gpt-5.6-sol"
REVIEW_REASONING_EFFORT = os.environ.get("ARCH_REVIEW_REASONING_EFFORT", "high").strip() or "high"
SYNTHESIS_REASONING_EFFORT = os.environ.get("ARCH_REVIEW_SYNTHESIS_REASONING_EFFORT", "max").strip() or "max"
ADVERSARY_REASONING_EFFORT = os.environ.get("ARCH_REVIEW_ADVERSARY_REASONING_EFFORT", "max").strip() or "max"
VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
PROVIDER_CONFIGURATION_KEY = "architecture-review-openai"

if not MODEL_POOL:
    raise RuntimeError("ARCH_REVIEW_MODELS must contain at least one model.")
for name, value in {"ARCH_REVIEW_REASONING_EFFORT": REVIEW_REASONING_EFFORT,
                    "ARCH_REVIEW_SYNTHESIS_REASONING_EFFORT": SYNTHESIS_REASONING_EFFORT,
                    "ARCH_REVIEW_ADVERSARY_REASONING_EFFORT": ADVERSARY_REASONING_EFFORT}.items():
    if value not in VALID_REASONING_EFFORTS:
        raise RuntimeError(f"{name} must be one of {sorted(VALID_REASONING_EFFORTS)}, got {value!r}.")

_architecture_run_dir: Path | None = None
_provider_factory = OpenAICodexProvider
_runner_factory = AgentRunner


def configure_invocation_run_root(run_dir: Path) -> None:
    global _architecture_run_dir
    _architecture_run_dir = Path(run_dir)


def reasoning_effort_for(agent_name: str) -> str:
    if agent_name == "Architecture Synthesis":
        return SYNTHESIS_REASONING_EFFORT
    if agent_name == "Adversarial Synthesis Critic":
        return ADVERSARY_REASONING_EFFORT
    return REVIEW_REASONING_EFFORT


def role_key_for(agent_name: str) -> str:
    if agent_name == "Architecture Synthesis":
        return "architecture_synthesis"
    if agent_name == "Adversarial Synthesis Critic":
        return "adversarial_synthesis_critic"
    for role in base.ROLE_SPECS:
        if role["name"] == agent_name:
            return str(role["key"])
    return "architecture_review_agent"


def codex_common_review_prompt(*, role_name: str, role_focus: str, frozen_head: str) -> str:
    return _shared_common_review_prompt(role_name=role_name, role_focus=role_focus, frozen_head=frozen_head).replace(
        "Inspect the repository directly using Read/Glob/Grep.",
        "Inspect the repository directly using read-only shell/file inspection commands such as cat, sed, find, rg, and git show/log/diff as needed.",
    )


def _configuration(model: str) -> RuntimeConfiguration:
    return RuntimeConfiguration({PROVIDER_CONFIGURATION_KEY: {
        "provider": "openai-codex",
        "models": {"low_cost": model, "standard": model, "high_reasoning": model},
    }})


def invoke_codex_agent(*, agent_name: str, model: str, prompt: str,
                       schema: dict[str, Any], max_turns: int) -> dict[str, Any]:
    if _architecture_run_dir is None:
        raise RuntimeError("ArchitectureReview AgentRuntime artifact root is not configured.")
    role = role_key_for(agent_name)
    run_id = f"{role.replace('_', '-')}-{uuid.uuid4().hex[:16]}"
    capability_class = "high_reasoning" if agent_name in {
        "Architecture Synthesis", "Adversarial Synthesis Critic"
    } else "standard"
    request = AgentInvocationRequest(
        "1.0", run_id, role, prompt, tuple(base.ARCHITECTURE_DOCS),
        ("repository_read", "repository_search"), WriteBoundaries((), ()), schema,
        capability_class, Budgets(max_turns, base.REVIEW_TIMEOUT, None),
        PROVIDER_CONFIGURATION_KEY,
    )
    effort = reasoning_effort_for(agent_name)
    provider = _provider_factory(reasoning_effort=effort,
        externally_enforced_read_only_repository=True, repository_root=base.ROOT)
    runner = _runner_factory(_architecture_run_dir / "agent_runtime", _configuration(model),
                             {"openai-codex": provider})
    print(f"Starting: {agent_name} [{model}, reasoning={effort}, invocation={run_id}]")
    result = runner.run(request)
    artifact_path = (_architecture_run_dir / "agent_runtime" / run_id).relative_to(base.ROOT).as_posix()
    if result.status != "succeeded":
        raise RuntimeError(f"{agent_name} [{model}] AgentRuntime invocation {run_id} failed "
                           f"({result.failure_classification}): {result.failure_message}; artifacts: {artifact_path}")
    print(f"Completed: {agent_name} [{model}] in {result.duration_seconds:.2f}s")
    return {"agent": agent_name, "provider": result.provider, "model": result.model,
            "reasoning_effort": effort, "duration_seconds": round(result.duration_seconds, 2),
            "agent_runtime_run_id": run_id, "agent_runtime_artifacts": artifact_path,
            "result": result.to_dict()["structured_output"]}


def configure_base_runner() -> None:
    base.configure_provider_namespace("codex")
    base.MODEL_POOL = MODEL_POOL
    base.SYNTHESIS_MODEL = SYNTHESIS_MODEL
    base.ADVERSARY_MODEL = ADVERSARY_MODEL
    base.common_review_prompt = codex_common_review_prompt
    base.invoke_read_only_agent = invoke_codex_agent
    base.configure_invocation_run_root = configure_invocation_run_root


def main() -> int:
    configure_base_runner()
    return resumable.main()


configure_base_runner()

if __name__ == "__main__":
    raise SystemExit(main())
