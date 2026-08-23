from __future__ import annotations

import json
from pathlib import Path
import tempfile

import architecture_review as shared
import architecture_review_claude as claude_review
import architecture_review_resume as resumable
from Pipeline.AgentRuntime.contracts import AgentInvocationRequest, AgentResult, Usage


class FakeProvider:
    provider_identifier = "claude-code"


class FakeRunner:
    requests: list[AgentInvocationRequest] = []
    roots: list[Path] = []
    selections: list[tuple[str, str]] = []
    fail = False

    def __init__(self, root: Path, configuration: object, registry: object) -> None:
        self.root, self.configuration, self.registry = root, configuration, registry
        type(self).roots.append(root)

    def run(self, request: AgentInvocationRequest) -> AgentResult:
        type(self).requests.append(request)
        selection = self.configuration.resolve(
            request.provider_configuration_key,
            request.model_capability_class,
            self.registry,
        )
        type(self).selections.append((selection.provider, selection.model))
        if type(self).fail:
            return AgentResult(
                "1.0", request.run_id, selection.provider, selection.model,
                request.role, "failed", "provider_error", "fake failure", None,
                (), 0.1, None, "provider.log", False, (),
            )
        return AgentResult(
            "1.0", request.run_id, selection.provider, selection.model,
            request.role, "succeeded", "none", None, {"message": "ok"},
            (), 0.1, Usage(1, 2, 3), "provider.log", False, (),
        )


def provider_factory() -> FakeProvider:
    return FakeProvider()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> int:
    assert len(shared.ROLE_SPECS) == 8
    assert shared.PROVIDER_NAMESPACE == "claude"
    assert shared.invoke_read_only_agent is claude_review.invoke_claude_agent
    assert callable(resumable.main)
    assert claude_review.MODEL_POOL == ["claude-sonnet-5"]
    assert claude_review.SYNTHESIS_MODEL == "claude-sonnet-5"
    assert claude_review.ADVERSARY_MODEL == "claude-sonnet-5"

    prompt = shared.common_review_prompt(
        role_name="Smoke Test Reviewer",
        role_focus="Test the review contract.",
        frozen_head="deadbeef",
    )
    assert "Inspect the repository directly using Read/Glob/Grep." in prompt
    assert "Experimental independence rule" in prompt
    assert "prior or other-provider" in prompt
    assert "read-only shell/file inspection" not in prompt

    old_provider = claude_review._provider_factory
    old_runner = claude_review._runner_factory
    claude_review._provider_factory = provider_factory
    claude_review._runner_factory = FakeRunner
    shared.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="stage4d-test-", dir=shared.OUTPUT_ROOT
        ) as temporary:
            run_dir = Path(temporary)
            claude_review.configure_invocation_run_root(run_dir)
            reviewer = claude_review.invoke_claude_agent(
                agent_name=shared.ROLE_SPECS[0]["name"],
                model="claude-review-model",
                prompt="review",
                schema={"type": "object"},
                max_turns=2,
            )
            synthesis = claude_review.invoke_claude_agent(
                agent_name="Architecture Synthesis",
                model="claude-synthesis-model",
                prompt="synthesize",
                schema={"type": "object"},
                max_turns=3,
            )
            adversary = claude_review.invoke_claude_agent(
                agent_name="Adversarial Synthesis Critic",
                model="claude-adversary-model",
                prompt="criticize",
                schema={"type": "object"},
                max_turns=4,
            )

            assert reviewer == {
                "agent": shared.ROLE_SPECS[0]["name"],
                "provider": "claude-code",
                "model": "claude-review-model",
                "duration_seconds": 0.1,
                "agent_runtime_run_id": reviewer["agent_runtime_run_id"],
                "agent_runtime_artifacts": reviewer["agent_runtime_artifacts"],
                "result": {"message": "ok"},
            }
            assert len({
                reviewer["agent_runtime_run_id"],
                synthesis["agent_runtime_run_id"],
                adversary["agent_runtime_run_id"],
            }) == 3
            review_request, synthesis_request, adversary_request = FakeRunner.requests[-3:]
            assert type(review_request) is AgentInvocationRequest
            assert set(review_request.allowed_capabilities) == {
                "repository_read", "repository_search"
            }
            assert "repository_write" not in review_request.allowed_capabilities
            assert "approved_command_execution" not in review_request.allowed_capabilities
            assert review_request.write_boundaries.allowed_paths == ()
            assert review_request.write_boundaries.denied_paths == ()
            assert review_request.model_capability_class == "standard"
            assert synthesis_request.model_capability_class == "high_reasoning"
            assert adversary_request.model_capability_class == "high_reasoning"
            assert review_request.budgets.turn_limit == 2
            assert review_request.budgets.timeout_seconds == shared.REVIEW_TIMEOUT
            assert review_request.budgets.token_limit is None
            assert FakeRunner.roots[-3:] == [run_dir / "agent_runtime"] * 3
            assert FakeRunner.selections[-3:] == [
                ("claude-code", "claude-review-model"),
                ("claude-code", "claude-synthesis-model"),
                ("claude-code", "claude-adversary-model"),
            ]

            FakeRunner.fail = True
            try:
                claude_review.invoke_claude_agent(
                    agent_name="Adversarial Synthesis Critic",
                    model="claude-adversary-model",
                    prompt="criticize",
                    schema={"type": "object"},
                    max_turns=1,
                )
            except RuntimeError as exc:
                assert "provider_error" in str(exc) and "artifacts:" in str(exc)
            else:
                raise AssertionError("failed AgentResult must enter resumable failure flow")
    finally:
        FakeRunner.fail = False
        claude_review._provider_factory = old_provider
        claude_review._runner_factory = old_runner

    original_output_root = shared.OUTPUT_ROOT
    original_git_head = shared.git_head
    with tempfile.TemporaryDirectory(prefix="stage4d-resume-") as temporary:
        shared.OUTPUT_ROOT = Path(temporary)
        shared.configure_provider_namespace("claude")
        mismatch = shared.provider_output_root() / "runs" / "codex-owned"
        _write_json(mismatch / "manifest.json", {
            "provider_namespace": "codex", "frozen_head": "deadbeef"
        })
        shared.git_head = lambda: "deadbeef"
        try:
            try:
                resumable.open_resumed_run("codex-owned")
            except RuntimeError as exc:
                assert "different provider namespace" in str(exc)
            else:
                raise AssertionError("Claude must not resume a Codex-owned run")
        finally:
            shared.OUTPUT_ROOT = original_output_root
            shared.git_head = original_git_head
            claude_review.configure_base_runner()

    adapter_source = Path(claude_review.__file__).read_text(encoding="utf-8")
    shared_source = Path(shared.__file__).read_text(encoding="utf-8")
    assert "TaskExecution" not in adapter_source
    assert "subprocess" not in adapter_source
    assert '"claude",\n        "-p"' not in shared_source
    print("architecture_review_claude_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
