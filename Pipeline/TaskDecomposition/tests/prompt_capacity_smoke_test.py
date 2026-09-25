"""An author prompt that cannot fit the model's window is refused before any call."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.config import RuntimeConfiguration  # noqa: E402
import TaskDecomposition.round_robin_decomposition as round_robin  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    prompt_capacity_problem,
    run_round_robin_decomposition,
)
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    pass_review,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import (  # noqa: E402
    create_repository,
    decomposed_result,
)
from TaskDecomposition.round_robin_decomposition import candidate_sha256  # noqa: E402


class ClaudeCodeQueueProvider(QueueProvider):
    provider_identifier = "claude-code"


def claude_code_factory(providers: dict[str, QueueProvider], model: str):
    def factory(provider_name: str, _source: Path, role: str):
        key = f"{provider_name}-decomposition"
        identifier = "claude-code" if provider_name == "claude" else "fake"
        configuration = RuntimeConfiguration({
            key: {
                "provider": identifier,
                "models": {"low_cost": model, "standard": model, "high_reasoning": model},
            }
        })
        return key, configuration, {identifier: providers[provider_name]}

    return factory


def run(source: Path, output_root: Path, run_id: str, providers, model: str) -> dict:
    return run_round_robin_decomposition(
        source=source,
        output_root=output_root,
        task_id="NSC-010",
        provider_order=("claude", "codex"),
        max_calls=2,
        run_id=run_id,
        provider_factory=claude_code_factory(providers, model),
        _require_physical_read_only_source=False,
    )


def test_the_estimate_and_its_scope() -> None:
    nsc088 = "x" * 724_011  # the measured NSC-088 author prompt size
    problem = prompt_capacity_problem("claude-code", "claude-opus-5-5", nsc088)
    assert problem is not None and "claude-opus-5-5[1m]" in problem, problem
    assert prompt_capacity_problem("claude-code", "claude-opus-5-5[1m]", nsc088) is None
    huge = prompt_capacity_problem("claude-code", "claude-opus-5-5[1m]", "x" * 3_000_000)
    assert huge is not None and "reduce the decomposition context" in huge, huge
    assert "[1m]" not in huge.split("To proceed")[1], huge
    nsc066 = "x" * 300_636  # the measured NSC-066 context that fit claude-opus-5
    assert prompt_capacity_problem("claude-code", "claude-opus-5", nsc066) is None
    assert prompt_capacity_problem("openai-codex", "gpt-5.6-sol", nsc088 * 4) is None
    multibyte = "\u00e9" * 300_000  # counted in UTF-8 bytes, not characters
    assert prompt_capacity_problem("claude-code", "claude-opus-5", multibyte) is not None


def test_an_oversized_prompt_makes_no_provider_call() -> None:
    saved = round_robin.CLAUDE_CONTEXT_WINDOW_TOKENS
    with tempfile.TemporaryDirectory(prefix="nsc-d1b2-capacity-") as text:
        base = Path(text)
        source = base / "source"
        create_repository(source)
        author = ClaudeCodeQueueProvider([])
        try:
            round_robin.CLAUDE_CONTEXT_WINDOW_TOKENS = 100
            result = run(source, base / "output", "capacity-refused",
                         {"claude": author, "codex": QueueProvider([])}, "claude-sonnet-5")
        finally:
            round_robin.CLAUDE_CONTEXT_WINDOW_TOKENS = saved
        assert author.calls == 0, author.calls
        assert result["run_status"] == "agent_failed", result["run_status"]
        reasons = " ".join(result["rejection_reasons"])
        assert "PromptCapacityError" in reasons and "no provider call was made" in reasons, reasons


def test_a_reviewer_refusal_follows_a_completed_author() -> None:
    saved = round_robin.CLAUDE_CONTEXT_WINDOW_TOKENS
    with tempfile.TemporaryDirectory(prefix="nsc-d1b2-capacity-") as text:
        base = Path(text)
        source = base / "source"
        tasks = create_repository(source)
        author = QueueProvider([decomposed_result(tasks["NSC-010"])])
        reviewer = ClaudeCodeQueueProvider([])
        try:
            round_robin.CLAUDE_CONTEXT_WINDOW_TOKENS = 100
            result = run_round_robin_decomposition(
                source=source, output_root=base / "output", task_id="NSC-010",
                provider_order=("codex", "claude"), max_calls=2,
                run_id="capacity-reviewer-refused",
                provider_factory=claude_code_factory(
                    {"codex": author, "claude": reviewer}, "claude-sonnet-5"),
                _require_physical_read_only_source=False,
            )
        finally:
            round_robin.CLAUDE_CONTEXT_WINDOW_TOKENS = saved
        assert (author.calls, reviewer.calls) == (1, 0), (author.calls, reviewer.calls)
        assert result["run_status"] == "agent_failed", result["run_status"]
        assert "PromptCapacityError" in " ".join(result["rejection_reasons"]), result


def test_a_prompt_that_fits_is_unaffected() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-d1b2-capacity-") as text:
        base = Path(text)
        source = base / "source"
        tasks = create_repository(source)
        raw = decomposed_result(tasks["NSC-010"])
        candidate_hash = candidate_sha256(validated_candidate(raw, tasks["NSC-010"], tasks))
        author = ClaudeCodeQueueProvider([raw])
        reviewer = QueueProvider([pass_review(candidate_hash)])
        result = run(source, base / "output", "capacity-fits",
                     {"claude": author, "codex": reviewer}, "claude-sonnet-5")
        assert (author.calls, reviewer.calls) == (1, 1), (author.calls, reviewer.calls)
        assert result["run_status"] == "review_ready", result


TESTS = (
    test_the_estimate_and_its_scope,
    test_an_oversized_prompt_makes_no_provider_call,
    test_a_reviewer_refusal_follows_a_completed_author,
    test_a_prompt_that_fits_is_unaffected,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition prompt capacity smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
