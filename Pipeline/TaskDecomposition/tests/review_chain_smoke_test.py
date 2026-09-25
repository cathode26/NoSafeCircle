"""The three-call review chain verifier accepts exactly the admissible shapes.

Runs are real engine runs with test providers that report production-shaped
identities (claude-code, openai-codex). Each refusal starts from a valid
three-call chain, changes one thing, and must fail with its own code.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.config import RuntimeConfiguration  # noqa: E402
from TaskDecomposition.review_chain import ReviewChainError, verify_three_call_chain  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.tests.author_correction_smoke_test import missing_coverage_result  # noqa: E402
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    pass_review,
    revise_review,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import create_repository, decomposed_result  # noqa: E402

IDENTIFIERS = {"claude": "claude-code", "codex": "openai-codex"}


def factory(providers: dict[str, QueueProvider]):
    def build(provider_name: str, _source: Path, role: str):
        identifier = IDENTIFIERS[provider_name]
        key = f"{provider_name}-decomposition"
        queue = providers[provider_name]
        queue.provider_identifier = identifier
        configuration = RuntimeConfiguration({key: {"provider": identifier, "models": {
            "low_cost": "fixture-model", "standard": "fixture-model", "high_reasoning": "fixture-model"}}})
        return key, configuration, {identifier: queue}
    return build


class Scenario:
    """One real engine run in a temporary repository."""

    def __init__(self, base: Path, order: tuple[str, str], *, correct: bool, revise: bool) -> None:
        self.source = base / "source"
        self.tasks = create_repository(self.source)
        parent = self.tasks["NSC-010"]
        first, second = order
        initial = decomposed_result(parent)
        initial_hash = candidate_sha256(validated_candidate(initial, parent, self.tasks))
        revised = deepcopy(initial)
        revised["children"][0]["notes"] = "Independent reviewer revision."
        revised_hash = candidate_sha256(validated_candidate(revised, parent, self.tasks))
        outputs: dict[str, list[Any]] = {first: [], second: []}
        if correct:
            outputs[first].append(missing_coverage_result(parent))
        outputs[first].append(initial)
        if revise:
            outputs[second].append(revise_review(initial_hash, revised, round_number=2, suffix="a"))
            outputs[first].append(pass_review(revised_hash, resolutions=[
                {"finding_id": "round-02-a", "status": "resolved", "explanation": "Replaced."}]))
        else:
            outputs[second].append(pass_review(initial_hash))
        self.run_id = f"chain-{first}-{'c' if correct else 'n'}{'r' if revise else 'p'}"
        self.result = run_round_robin_decomposition(
            source=self.source, output_root=base / "output", task_id="NSC-010",
            provider_order=order, max_calls=3, run_id=self.run_id,
            provider_factory=factory({name: QueueProvider(items) for name, items in outputs.items()}),
            _require_physical_read_only_source=False,
        )
        self.run_dir = base / "output" / self.run_id
        self.order = order


def verify(scenario: Scenario, run_result: dict | None = None) -> dict:
    return verify_three_call_chain(
        run_dir=scenario.run_dir, run_result=run_result or scenario.result, providers=scenario.order)


def refused(action: Callable[[], Any], code: str) -> None:
    try:
        action()
    except ReviewChainError as exc:
        assert exc.code == code, f"expected {code}, got {exc}"
    else:
        raise AssertionError(f"expected {code}")


def test_every_admissible_shape_is_accepted_in_both_orders() -> None:
    for order in (("claude", "codex"), ("codex", "claude")):
        for correct in (False, True):
            for revise in (False, True):
                with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
                    scenario = Scenario(Path(text), order, correct=correct, revise=revise)
                    label = f"{order} correct={correct} revise={revise}"
                    assert scenario.result["run_status"] == "review_ready", (label, scenario.result["rejection_reasons"])
                    chain = verify(scenario)
                    assert chain["calls_used"] == (3 if revise else 2), label
                    assert chain["author_corrections_used"] == (1 if correct else 0), label
                    approver = order[0] if revise else order[1]
                    assert chain["approver_provider"] == approver, (label, chain)
                    assert chain["approved_candidate"]["author_provider"] != approver, label
                    assert set(chain["review_sha256"]) == {
                        f"rounds/{n:02d}/review.json" for n in range(2, chain["calls_used"] + 1)}, label


def test_each_broken_rule_is_refused_for_its_own_reason() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
        scenario = Scenario(Path(text), ("claude", "codex"), correct=False, revise=True)
        assert verify(scenario)["approver_provider"] == "claude"

        def mutated(change: Callable[[dict], None]) -> dict:
            result = deepcopy(scenario.result)
            change(result)
            return result

        def reviser_approves(result: dict) -> None:
            result["rounds"][2].update(requested_provider="codex", actual_provider="openai-codex")
        refused(lambda: verify(scenario, mutated(reviser_approves)), "D3_SELF_APPROVAL")

        def wrong_link(result: dict) -> None:
            result["rounds"][2]["candidate_before"] = dict(result["rounds"][1]["candidate_before"])
        refused(lambda: verify(scenario, mutated(wrong_link)), "D3_CANDIDATE_LINK")

        def pass_publishes(result: dict) -> None:
            result["rounds"][2]["candidate_after"] = dict(result["rounds"][2]["candidate_before"])
        refused(lambda: verify(scenario, mutated(pass_publishes)), "D3_PASS_MUTATES_CANDIDATE")

        def skipped_version(result: dict) -> None:
            result["rounds"][1]["candidate_after"]["version"] = 3
        refused(lambda: verify(scenario, mutated(skipped_version)), "D3_REVISION")

        def wrong_runtime(result: dict) -> None:
            result["rounds"][1]["actual_provider"] = "claude-code"
        refused(lambda: verify(scenario, mutated(wrong_runtime)), "D3_PROVIDER_IDENTITY")

        def counted_wrong(result: dict) -> None:
            result["calls_used"] = 2
        refused(lambda: verify(scenario, mutated(counted_wrong)), "D3_ACCOUNTING")

        def other_approver(result: dict) -> None:
            result["independent_approver_provider"] = "codex"
        refused(lambda: verify(scenario, mutated(other_approver)), "D3_FINAL_ARTIFACTS")


def test_a_final_pass_that_does_not_resolve_earlier_findings_is_refused() -> None:
    for status in (None, "still_blocking"):
        with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
            scenario = Scenario(Path(text), ("claude", "codex"), correct=False, revise=True)
            review_path = scenario.run_dir / "rounds" / "03" / "review.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            if status is None:
                review["prior_finding_resolutions"] = []
            else:
                review["prior_finding_resolutions"][0]["status"] = status
            review_path.write_text(json.dumps(review), encoding="utf-8")
            refused(lambda: verify(scenario), "D3_FINDING_RESOLUTION")


def test_a_two_provider_order_is_required() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
        scenario = Scenario(Path(text), ("claude", "codex"), correct=False, revise=True)
        refused(lambda: verify_three_call_chain(
            run_dir=scenario.run_dir, run_result=scenario.result, providers=("claude", "claude")), "D3_ROUND")


TESTS = (
    test_every_admissible_shape_is_accepted_in_both_orders,
    test_each_broken_rule_is_refused_for_its_own_reason,
    test_a_final_pass_that_does_not_resolve_earlier_findings_is_refused,
    test_a_two_provider_order_is_required,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition review chain smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
