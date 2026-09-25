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
    _normalize_empty_artifact_placeholder,
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
from TaskDecomposition.tests.test_support import (  # noqa: E402
    create_repository,
    decomposed_result,
    needs_human_result,
)
from TaskDecomposition.policy import validate_decomposition_result  # noqa: E402
from graph_delta import plan_graph_delta  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402

TIMEOUTS = {"task_decomposer": 1440.0, "decomposition_reviewer": 1200.0}

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


def digest_for(source: Path):
    graph = load_persistent_work_graph(source)
    parent = graph.tasks_by_id["NSC-010"]

    def digest(raw):
        # The producer's own normalisation and validation, as AssistantControl uses.
        result = validate_decomposition_result(
            _normalize_empty_artifact_placeholder(dict(raw)), parent_task=parent,
            existing_reconciliation_keys=graph.plan.id_map.keys())
        plan_id = (plan_graph_delta(graph, result.parent_task, result).plan_id
                   if result.decision == "decomposed" else None)
        return candidate_sha256(result), plan_id
    return digest


def verify(scenario: Scenario, run_result: dict | None = None, *, timeouts=TIMEOUTS) -> dict:
    return verify_three_call_chain(
        run_dir=scenario.run_dir, run_result=run_result or scenario.result, providers=scenario.order,
        candidate_digest=digest_for(scenario.source), timeouts=timeouts)


def rewrite(path: Path, change: Callable[[dict], None]) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    change(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def runtime_file(scenario: Scenario, directory: str, name: str) -> Path:
    return next((scenario.run_dir / "rounds" / directory / "agent_runtime").glob(f"*/{name}"))


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
                    reviews = {f"rounds/{n:02d}/review.json" for n in range(2, chain["calls_used"] + 1)}
                    assert reviews <= set(chain["evidence_sha256"]), label
                    assert any(k.endswith("/result.json") for k in chain["evidence_sha256"]), label
                    assert any(k.endswith("candidate.json") for k in chain["evidence_sha256"]), label


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

        refused(lambda: verify(scenario, mutated(lambda r: r.update(max_calls=3.0))), "D3_ACCOUNTING")

        def boolean_round(result: dict) -> None:
            result["rounds"][0]["round_number"] = True
        refused(lambda: verify(scenario, mutated(boolean_round)), "D3_ROUND")

        def history_findings(result: dict) -> None:
            result["finding_history"][0]["findings"][0]["problem"] = "rewritten after the fact"
        refused(lambda: verify(scenario, mutated(history_findings)), "D3_FINDING_RESOLUTION")

        refused(lambda: verify(scenario, timeouts={**TIMEOUTS, "decomposition_reviewer": 600.0}), "D3_TIMEOUT")


def test_the_revision_bytes_and_execution_evidence_are_bound() -> None:
    cases: list[tuple[str, Callable[[Scenario], None], str]] = []

    def revised_notes_in_review_only(s: Scenario) -> None:
        def change(review: dict) -> None:
            review["revised_decomposition"]["children"][0]["notes"] = "Quietly different."
        rewrite(s.run_dir / "rounds" / "02" / "review.json", change)
        rewrite(runtime_file(s, "02", "result.json"), lambda r: change(r["structured_output"]))
    cases.append(("revision payload differs from the published candidate", revised_notes_in_review_only,
                  "D3_REVISION"))

    def published_candidate_edited(s: Scenario) -> None:
        rewrite(s.run_dir / "rounds" / "02" / "candidate.json",
                lambda c: c["children"][0].update(notes="Edited after publication."))
    cases.append(("published revision bytes edited", published_candidate_edited, "D3_CANDIDATE"))

    def coverage_removed(s: Scenario) -> None:
        def change(candidate: dict) -> None:
            candidate["parent_requirement_coverage"] = []
        rewrite(s.run_dir / "rounds" / "02" / "candidate.json", change)
    cases.append(("revision no longer covers the parent", coverage_removed, "D3_CANDIDATE"))

    def review_without_runtime(s: Scenario) -> None:
        rewrite(s.run_dir / "rounds" / "02" / "review.json", lambda r: r.update(summary="Swapped review."))
    cases.append(("review file is not the runtime output", review_without_runtime, "D3_PROVIDER_IDENTITY"))

    for field, value in (("provider", "claude-code"), ("run_id", "another-invocation"),
                         ("status", "failed"), ("model", "another-model")):
        def runtime_field(s: Scenario, field=field, value=value) -> None:
            rewrite(runtime_file(s, "02", "result.json"), lambda r: r.update({field: value}))
        cases.append((f"runtime result {field}", runtime_field, "D3_PROVIDER_IDENTITY"))

    def request_role(s: Scenario) -> None:
        rewrite(runtime_file(s, "03", "request.json"), lambda r: r.update(role="task_decomposer"))
    cases.append(("runtime request role", request_role, "D3_PROVIDER_IDENTITY"))

    def pass_with_replacement(s: Scenario) -> None:
        def change(review: dict) -> None:
            review["revised_decomposition"] = json.loads(
                (s.run_dir / "rounds" / "02" / "candidate.json").read_text(encoding="utf-8"))
        rewrite(s.run_dir / "rounds" / "03" / "review.json", change)
        rewrite(runtime_file(s, "03", "result.json"), lambda r: change(r["structured_output"]))
    cases.append(("PASS carrying a replacement", pass_with_replacement, "D3_PASS_MUTATES_CANDIDATE"))

    for label, mutate, code in cases:
        with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
            scenario = Scenario(Path(text), ("claude", "codex"), correct=False, revise=True)
            verify(scenario)
            mutate(scenario)
            try:
                verify(scenario)
            except ReviewChainError as exc:
                assert exc.code == code, f"{label}: expected {code}, got {exc}"
            else:
                raise AssertionError(f"{label}: expected {code}")


def test_a_final_pass_that_does_not_resolve_earlier_findings_is_refused() -> None:
    for status in (None, "still_blocking"):
        with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
            scenario = Scenario(Path(text), ("claude", "codex"), correct=False, revise=True)
            def change(review: dict, status=status) -> None:
                if status is None:
                    review["prior_finding_resolutions"] = []
                else:
                    review["prior_finding_resolutions"][0]["status"] = status
            # The runtime output is changed consistently, so the review policy's
            # own resolution rule is what refuses it.
            rewrite(scenario.run_dir / "rounds" / "03" / "review.json", change)
            rewrite(runtime_file(scenario, "03", "result.json"), lambda r: change(r["structured_output"]))
            refused(lambda: verify(scenario), "D3_FINDING_RESOLUTION")


def run_custom(base: Path, author_outputs, reviewer_outputs, run_id: str) -> tuple[Path, dict, Path]:
    source = base / "source"
    result = run_round_robin_decomposition(
        source=source, output_root=base / "output", task_id="NSC-010",
        provider_order=("claude", "codex"), max_calls=3, run_id=run_id,
        provider_factory=factory({"claude": QueueProvider(author_outputs),
                                  "codex": QueueProvider(reviewer_outputs)}),
        _require_physical_read_only_source=False,
    )
    return source, result, base / "output" / run_id


def test_producer_normalised_outputs_and_intermediate_proposals_are_accepted() -> None:
    # The author's empty artifact_proposal placeholder, which the producer
    # normalises to null before publishing, and a review summary with
    # surrounding whitespace, which the schema parser trims.
    with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
        base = Path(text)
        tasks = create_repository(base / "source")
        parent = tasks["NSC-010"]
        initial = decomposed_result(parent)
        placeholder = deepcopy(initial)
        placeholder["artifact_proposal"] = {"title": "", "purpose": "", "source_parent_obligations": [],
                                            "authorized_decisions_needed": [], "out_of_scope": []}
        initial_hash = candidate_sha256(validated_candidate(initial, parent, tasks))
        review = pass_review(initial_hash)
        review["summary"] = "   " + review["summary"] + "   "
        source, result, run_dir = run_custom(base, [placeholder], [review], "chain-normalised")
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        chain = verify_three_call_chain(run_dir=run_dir, run_result=result, providers=("claude", "codex"),
                                        candidate_digest=digest_for(source), timeouts=TIMEOUTS)
        assert chain["approver_provider"] == "codex"

    # A valid needs_human proposal revised by the reviewer into a
    # decomposition, then independently passed: the intermediate candidate
    # has no graph plan.
    with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
        base = Path(text)
        tasks = create_repository(base / "source")
        parent = tasks["NSC-010"]
        proposal = needs_human_result(parent)
        proposal_hash = candidate_sha256(validated_candidate(proposal, parent, tasks))
        revised = decomposed_result(parent)
        revised_hash = candidate_sha256(validated_candidate(revised, parent, tasks))
        source, result, run_dir = run_custom(
            base,
            [proposal, pass_review(revised_hash, resolutions=[
                {"finding_id": "round-02-a", "status": "resolved", "explanation": "Decomposed."}])],
            [revise_review(proposal_hash, revised, round_number=2, suffix="a")],
            "chain-transition")
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        assert result["rounds"][0]["candidate_after"]["graph_delta_plan_id"] is None
        chain = verify_three_call_chain(run_dir=run_dir, run_result=result, providers=("claude", "codex"),
                                        candidate_digest=digest_for(source), timeouts=TIMEOUTS)
        assert chain["approved_candidate"]["decision"] == "decomposed" and chain["calls_used"] == 3

        def meaning_changed(review: dict) -> None:
            review["summary"] = "A different review."
        rewrite(run_dir / "rounds" / "03" / "review.json", meaning_changed)
        refused(lambda: verify_three_call_chain(
            run_dir=run_dir, run_result=result, providers=("claude", "codex"),
            candidate_digest=digest_for(source), timeouts=TIMEOUTS), "D3_PROVIDER_IDENTITY")


def test_a_two_provider_order_is_required() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-chain-") as text:
        scenario = Scenario(Path(text), ("claude", "codex"), correct=False, revise=True)
        refused(lambda: verify_three_call_chain(
            run_dir=scenario.run_dir, run_result=scenario.result, providers=("claude", "claude"),
            candidate_digest=digest_for(scenario.source), timeouts=TIMEOUTS), "D3_ROUND")


TESTS = (
    test_every_admissible_shape_is_accepted_in_both_orders,
    test_each_broken_rule_is_refused_for_its_own_reason,
    test_the_revision_bytes_and_execution_evidence_are_bound,
    test_a_final_pass_that_does_not_resolve_earlier_findings_is_refused,
    test_producer_normalised_outputs_and_intermediate_proposals_are_accepted,
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
