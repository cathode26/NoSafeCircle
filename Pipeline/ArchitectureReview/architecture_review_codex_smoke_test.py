from __future__ import annotations

import tempfile
from pathlib import Path

import architecture_review as shared
import architecture_review_codex as codex_review
import architecture_review_resume as resumable
from Pipeline.AgentRuntime.contracts import AgentInvocationRequest, AgentResult, Usage


class FakeProvider:
    provider_identifier = "openai-codex"


class FakeRunner:
    requests: list[AgentInvocationRequest] = []
    selections: list[tuple[str, str]] = []
    fail = False

    def __init__(self, root: Path, configuration: object, registry: object) -> None:
        self.root, self.configuration, self.registry = root, configuration, registry

    def run(self, request: AgentInvocationRequest) -> AgentResult:
        type(self).requests.append(request)
        selection = self.configuration.resolve(request.provider_configuration_key,
                                               request.model_capability_class, self.registry)
        type(self).selections.append((selection.provider, selection.model))
        if type(self).fail:
            return AgentResult("1.0", request.run_id, selection.provider, selection.model,
                request.role, "failed", "provider_error", "fake failure", None, (), 0.1,
                None, "provider.log", False, ())
        return AgentResult("1.0", request.run_id, selection.provider, selection.model,
            request.role, "succeeded", "none", None, {"message": "ok"}, (), 0.1,
            Usage(1, 2, 3), "provider.log", False, ())


def provider_factory(**_: object) -> FakeProvider:
    return FakeProvider()


def main() -> int:
    assert len(shared.ROLE_SPECS) == 8
    assert shared.invoke_read_only_agent is codex_review.invoke_codex_agent
    assert callable(resumable.main)
    assert codex_review.REVIEW_REASONING_EFFORT == "high"
    assert codex_review.SYNTHESIS_REASONING_EFFORT == "max"
    assert codex_review.ADVERSARY_REASONING_EFFORT == "max"
    assert codex_review.reasoning_effort_for("Architecture Synthesis") == "max"

    sample = shared.common_review_prompt(role_name="Smoke Test Reviewer",
        role_focus="Test the review contract.", frozen_head="deadbeef")
    assert "read-only shell/file inspection" in sample

    old_provider, old_runner = codex_review._provider_factory, codex_review._runner_factory
    codex_review._provider_factory, codex_review._runner_factory = provider_factory, FakeRunner
    shared.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="stage4c-test-", dir=shared.OUTPUT_ROOT) as text:
            codex_review.configure_invocation_run_root(Path(text))
            reviewer = codex_review.invoke_codex_agent(agent_name=shared.ROLE_SPECS[0]["name"],
                model="gpt-review-model", prompt="review", schema={"type": "object"}, max_turns=2)
            synthesis = codex_review.invoke_codex_agent(agent_name="Architecture Synthesis",
                model="gpt-synthesis-model", prompt="synthesize", schema={"type": "object"}, max_turns=3)
            assert reviewer["provider"] == "openai-codex"
            assert reviewer["model"] == "gpt-review-model"
            assert reviewer["result"] == {"message": "ok"}
            assert reviewer["agent_runtime_run_id"] != synthesis["agent_runtime_run_id"]
            review_request, synthesis_request = FakeRunner.requests[-2:]
            assert type(review_request) is AgentInvocationRequest
            assert set(review_request.allowed_capabilities) == {"repository_read", "repository_search"}
            assert not hasattr(review_request, "task_id")
            assert review_request.model_capability_class == "standard"
            assert synthesis_request.model_capability_class == "high_reasoning"
            assert FakeRunner.selections[-2:] == [
                ("openai-codex", "gpt-review-model"),
                ("openai-codex", "gpt-synthesis-model"),
            ]
            FakeRunner.fail = True
            try:
                codex_review.invoke_codex_agent(agent_name="Adversarial Synthesis Critic",
                    model="gpt-adversary", prompt="criticize", schema={"type": "object"}, max_turns=1)
            except RuntimeError as exc:
                assert "provider_error" in str(exc) and "artifacts:" in str(exc)
            else:
                raise AssertionError("failed AgentResult must enter resumable failure flow")
    finally:
        FakeRunner.fail = False
        codex_review._provider_factory, codex_review._runner_factory = old_provider, old_runner

    source = Path(codex_review.__file__).read_text(encoding="utf-8")
    assert "TaskExecution" not in source and "subprocess.run" not in source
    print("architecture_review_codex_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
