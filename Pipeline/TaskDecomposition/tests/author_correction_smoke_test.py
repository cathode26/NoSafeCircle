"""Bounded author correction round: one extra author call, then a valid candidate or nothing.

Run exactly like the other D1B.2 deterministic suites:

    python Pipeline/TaskDecomposition/tests/author_correction_smoke_test.py

The mechanism under test is validator-agnostic. The correction is triggered by
any exception the deterministic candidate validation raises and carries that
validator's exact message as its primary feedback, so the rejection texts
exercised here (an exclusive-resource partition failure, a missing parent
coverage record, a graph-delta planning failure) are inputs, not behaviour.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.providers.fake import FakeProvider
from TaskDecomposition.round_robin_decomposition import (
    _observed_contract_differences,
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (
    QueueProvider,
    assert_json,
    git,
    pass_review,
    provider_factory,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import (
    create_repository,
    decomposed_result,
    protected_bytes,
)


def one_child_partial_resources(parent: dict[str, Any]) -> dict[str, Any]:
    """The NSC-1140 shape: a `reason` describing two children, one child returned."""

    value = decomposed_result(parent)
    value["reason"] = (
        "Split into an Alpha child and a Beta child so each owns one bounded surface."
    )
    value["children"][0]["exclusive_resources"] = ["repo-file:Assets/Shared.cs"]
    return value


def two_child_replacement(parent: dict[str, Any]) -> dict[str, Any]:
    """The complete replacement: both parent resources owned, every obligation traced."""

    value = decomposed_result(parent)
    base = value["children"][0]
    alpha = deepcopy(base)
    alpha["local_key"] = "bounded-child-alpha"
    alpha["title"] = "Alpha MonoBehaviour and its Edit Mode test"
    alpha["exclusive_resources"] = ["repo-file:Assets/Shared.cs"]
    alpha["downstream_integration_obligations"] = []
    beta = deepcopy(base)
    beta["local_key"] = "bounded-child-beta"
    beta["title"] = "Beta scene wiring and its Edit Mode test"
    beta["exclusive_resources"] = ["unity-scene:Assets/Synthetic.unity"]
    value["reason"] = (
        "Split into an Alpha child and a Beta child so each owns one bounded surface."
    )
    value["children"] = [alpha, beta]
    value["parent_requirement_coverage"] = [
        {
            "parent_entry_type": "acceptance_criteria",
            "parent_entry_id": "AC-001",
            "disposition": "assigned_to_child",
            "child_targets": [
                {
                    "local_key": "bounded-child-alpha",
                    "child_entry_type": "acceptance_criteria",
                    "child_entry_id": "AC-001",
                },
                {
                    "local_key": "bounded-child-beta",
                    "child_entry_type": "acceptance_criteria",
                    "child_entry_id": "AC-001",
                },
            ],
            "reason": "Both children carry one half of the parent acceptance.",
            "integration_rationale": "",
        },
        {
            "parent_entry_type": "completion_gates",
            "parent_entry_id": "VAL-001",
            "disposition": "assigned_to_child",
            "child_targets": [
                {
                    "local_key": "bounded-child-alpha",
                    "child_entry_type": "completion_gates",
                    "child_entry_id": "VAL-001",
                },
                {
                    "local_key": "bounded-child-beta",
                    "child_entry_type": "completion_gates",
                    "child_entry_id": "VAL-001",
                },
            ],
            "reason": "Each child runs its own Edit Mode validation.",
            "integration_rationale": "",
        },
        {
            "parent_entry_type": "downstream_integration_obligations",
            "parent_entry_id": "INT-001",
            "disposition": "assigned_to_child",
            "child_targets": [
                {
                    "local_key": "bounded-child-beta",
                    "child_entry_type": "downstream_integration_obligations",
                    "child_entry_id": "INT-001",
                }
            ],
            "reason": "The scene wiring child publishes the integration surface.",
            "integration_rationale": "",
        },
    ]
    value["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-012",
            "replacement_local_keys": ["bounded-child-beta"],
            "reason": "The direct dependent reads from the wired scene, not the shared script.",
        }
    ]
    return value


def missing_coverage_result(parent: dict[str, Any]) -> dict[str, Any]:
    """A rejection that is not about resources: one parent obligation is unmapped."""

    value = decomposed_result(parent)
    value["parent_requirement_coverage"].pop()
    return value


def run_case(
    *,
    source: Path,
    output_root: Path,
    run_id: str,
    providers: dict[str, QueueProvider],
    max_calls: int = 2,
) -> tuple[dict[str, Any], Path]:
    before_head = git(source, "rev-parse", "HEAD")
    before_protected = protected_bytes(source)
    result = run_round_robin_decomposition(
        source=source,
        output_root=output_root,
        task_id="NSC-010",
        provider_order=("codex", "claude"),
        max_calls=max_calls,
        run_id=run_id,
        provider_factory=provider_factory(providers),
        _require_physical_read_only_source=False,
    )
    assert git(source, "rev-parse", "HEAD") == before_head
    assert git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert protected_bytes(source) == before_protected
    run_dir = output_root / run_id
    assert assert_json(run_dir / "decomposition_run_result.json") == result
    return result, run_dir


def rounds_by_shape(result: dict[str, Any]) -> list[tuple[int, Any, str, str]]:
    return [
        (
            round_["round_number"],
            round_["correction_of_round"],
            round_["role"],
            round_["status"],
        )
        for round_ in result["rounds"]
    ]


def assert_corrected_pass(
    *,
    label: str,
    source: Path,
    output_root: Path,
    rejected_raw: dict[str, Any],
    replacement_raw: dict[str, Any],
    replacement_hash: str,
    expected_rejection_fragment: str,
    expected_differences: tuple[str, ...],
) -> None:
    """One deterministic rejection, one correction, one independent pass."""

    providers = {
        "codex": QueueProvider([rejected_raw, replacement_raw]),
        "claude": QueueProvider([pass_review(replacement_hash)]),
    }
    result, run_dir = run_case(
        source=source,
        output_root=output_root,
        run_id=label,
        providers=providers,
    )
    assert result["run_status"] == "review_ready", result["rejection_reasons"]
    # The correction is an extra author call outside the call limit: it never
    # consumes the independent reviewer's call and never changes `calls_used`.
    assert result["calls_used"] == 2
    assert result["max_calls"] == 2
    assert result["author_corrections_used"] == 1
    assert result["rejection_reasons"] == []
    assert result["independent_approver_provider"] == "claude"
    assert result["latest_candidate"]["sha256"] == replacement_hash
    assert result["latest_candidate"]["author_provider"] == "codex"
    assert rounds_by_shape(result) == [
        (1, None, "task_decomposer", "rejected"),
        (1, 1, "task_decomposer", "correction_candidate_valid"),
        (2, None, "decomposition_reviewer", "independent_pass"),
    ]

    # The initial deterministic failure is retained in full on its own round.
    first, correction, review = result["rounds"]
    assert len(first["rejection_reasons"]) == 1
    assert expected_rejection_fragment in first["rejection_reasons"][0]
    assert first["candidate_after"] is None
    assert correction["rejection_reasons"] == []
    assert correction["requested_provider"] == "codex"
    assert correction["candidate_before"] is None
    assert correction["candidate_after"]["sha256"] == replacement_hash
    assert review["candidate_before"]["sha256"] == replacement_hash

    # The correction owns its own round directory and never overwrites round 1.
    correction_dir = run_dir / "rounds" / "01-correction"
    assert (correction_dir / "round_result.json").is_file()
    assert (correction_dir / "candidate.json").is_file()
    assert (correction_dir / "candidate_graph_delta.json").is_file()
    assert not (run_dir / "rounds" / "01" / "candidate.json").exists()
    request = assert_json(run_dir / "rounds" / "01-correction-request.json")
    assert request["correction_of_round"] == 1
    assert expected_rejection_fragment in request["corrected_rejection_reason"]
    assert request["observed_contract_differences"] == list(expected_differences)
    assert request["role"] == "task_decomposer"
    correction_result = assert_json(correction_dir / "round_result.json")
    assert correction_result == correction
    assert correction_result["agent_runtime_result_path"].startswith(
        "rounds/01-correction/agent_runtime/"
    )
    assert (run_dir / correction_result["agent_runtime_result_path"]).is_file()
    assert (run_dir / correction_result["task_execution_request_path"]).is_file()

    # The correction call carries the rejection, the rejected output and one
    # instruction; the reviewer only ever saw the corrected candidate.
    assert providers["codex"].calls == 2
    correction_prompt = providers["codex"].requests[1].prompt
    assert providers["codex"].requests[1].role == "task_decomposer"
    assert "BEGIN BOUNDED AUTHOR CORRECTION REQUEST" in correction_prompt
    assert expected_rejection_fragment in correction_prompt
    assert "complete replacement result in the same output schema" in correction_prompt
    # The author's own rejected structured output, verbatim.
    assert (
        json.dumps(rejected_raw, ensure_ascii=False, indent=2, sort_keys=True)
        in correction_prompt
    )
    if expected_differences:
        for difference in expected_differences:
            assert difference in correction_prompt
    else:
        assert "(no differences observed)" in correction_prompt
    reviewer_prompt = providers["claude"].requests[0].prompt
    assert replacement_hash in reviewer_prompt
    progress = (run_dir / "progress.jsonl").read_text(encoding="utf-8")
    assert correction_prompt not in progress
    events = [json.loads(line) for line in progress.splitlines()]
    started = [row for row in events if row["event"] == "author_correction_started"]
    completed = [row for row in events if row["event"] == "author_correction_completed"]
    assert len(started) == 1 and len(completed) == 1
    assert started[0]["correction_of_round"] == 1
    assert expected_rejection_fragment in started[0]["rejection_reason"]
    assert started[0]["observed_differences"] == list(expected_differences)
    assert completed[0]["status"] == "correction_candidate_valid"
    assert [
        row["event"] for row in events if row["event"] == "run_completed"
    ] == ["run_completed"]
    assert next(
        row for row in events if row["event"] == "run_completed"
    )["author_corrections_used"] == 1

    # Nothing was applied and the review-ready proposal is the corrected one.
    published = assert_json(run_dir / "decomposition_result.json")
    assert [child["local_key"] for child in published["children"]] == [
        child["local_key"] for child in replacement_raw["children"]
    ]
    assert (run_dir / "graph_delta.json").is_file()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nsc-d1b2-author-correction-") as base_text:
        base = Path(base_text)
        source = base / "source"
        output_root = base / "output"
        tasks = create_repository(source)
        parent = tasks["NSC-010"]

        valid_raw = decomposed_result(parent)
        valid_hash = candidate_sha256(validated_candidate(valid_raw, parent, tasks))
        partition_raw = one_child_partial_resources(parent)
        two_child_raw = two_child_replacement(parent)
        two_child_hash = candidate_sha256(
            validated_candidate(two_child_raw, parent, tasks)
        )
        uncovered_raw = missing_coverage_result(parent)
        unplannable_raw = decomposed_result(parent, missing_dependency=True)

        # 0. The observed-difference helper describes, and degrades to silence.
        assert _observed_contract_differences(partition_raw, parent) == (
            "parent exclusive_resources entry 'unity-scene:Assets/Synthetic.unity' "
            "is named by no child in your result",
        )
        assert _observed_contract_differences(uncovered_raw, parent) == (
            "parent downstream_integration_obligations/INT-001 has no "
            "parent_requirement_coverage record in your result",
        )
        assert _observed_contract_differences(unplannable_raw, parent) == ()
        assert _observed_contract_differences(valid_raw, parent) == ()
        assert _observed_contract_differences("not an object", parent) == ()
        assert _observed_contract_differences({"children": "not a list"}, parent) != ()
        assert _observed_contract_differences({}, {}) == ()

        # 1. NSC-1140 exactly: one child returned for a two-child `reason`, an
        #    exclusive-resource partition rejection, one correction, then pass.
        assert_corrected_pass(
            label="partition-corrected",
            source=source,
            output_root=output_root,
            rejected_raw=partition_raw,
            replacement_raw=two_child_raw,
            replacement_hash=two_child_hash,
            expected_rejection_fragment=(
                "Child exclusive_resources must exactly partition the parent "
                "exclusive_resources (missing=['unity-scene:Assets/Synthetic.unity'], extra=[])"
            ),
            expected_differences=(
                "parent exclusive_resources entry 'unity-scene:Assets/Synthetic.unity' "
                "is named by no child in your result",
            ),
        )

        # 2. A rejection that has nothing to do with resources: one parent
        #    obligation left unmapped. Same mechanism, different validator rule.
        assert_corrected_pass(
            label="uncovered-obligation-corrected",
            source=source,
            output_root=output_root,
            rejected_raw=uncovered_raw,
            replacement_raw=valid_raw,
            replacement_hash=valid_hash,
            expected_rejection_fragment=(
                "Missing parent requirement coverage: "
                "downstream_integration_obligations/INT-001"
            ),
            expected_differences=(
                "parent downstream_integration_obligations/INT-001 has no "
                "parent_requirement_coverage record in your result",
            ),
        )

        # 3. A graph-delta planning rejection, where the candidate differs from
        #    the parent contract in no way this enrichment can describe. The
        #    correction still runs and the prompt says so plainly.
        assert_corrected_pass(
            label="graph-delta-corrected",
            source=source,
            output_root=output_root,
            rejected_raw=unplannable_raw,
            replacement_raw=valid_raw,
            replacement_hash=valid_hash,
            expected_rejection_fragment=(
                "Child 'bounded-child' references missing existing dependencies: ['NSC-999']"
            ),
            expected_differences=(),
        )

        # 4. A second deterministic failure ends the run after exactly one
        #    correction, with both failures retained and nothing applied.
        second_failure_raw = deepcopy(partition_raw)
        second_failure_raw["children"][0]["notes"] = "Still one child."
        providers = {
            "codex": QueueProvider([partition_raw, second_failure_raw]),
            "claude": QueueProvider([]),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="correction-also-invalid",
            providers=providers,
        )
        assert result["run_status"] == "rejected"
        assert result["author_corrections_used"] == 1
        assert result["calls_used"] == 1
        assert result["latest_candidate"] is None
        assert providers["codex"].calls == 2
        assert providers["claude"].calls == 0
        assert rounds_by_shape(result) == [
            (1, None, "task_decomposer", "rejected"),
            (1, 1, "task_decomposer", "rejected"),
        ]
        reasons = result["rejection_reasons"]
        assert len(reasons) == 2, reasons
        assert reasons[0].startswith(
            "round 1: initial candidate deterministic validation failed: "
        )
        assert reasons[1].startswith(
            "round 1 correction: corrected candidate deterministic validation failed: "
        )
        assert all("must exactly partition" in reason for reason in reasons)
        assert not (run_dir / "decomposition_result.json").exists()
        assert not (run_dir / "graph_delta.json").exists()
        assert not (run_dir / "rounds" / "01-correction" / "candidate.json").exists()
        assert not (run_dir / "rounds" / "02").exists()
        assert result["human_next_step"].startswith("Inspect rejection_reasons")

        # 5. A deterministically valid first candidate never triggers a
        #    correction: same call count, same rounds, same artifacts as before.
        providers = {
            "codex": QueueProvider([valid_raw]),
            "claude": QueueProvider([pass_review(valid_hash)]),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="valid-first-candidate",
            providers=providers,
        )
        assert result["run_status"] == "review_ready"
        assert result["calls_used"] == 2
        assert result["author_corrections_used"] == 0
        assert result["rejection_reasons"] == []
        assert providers["codex"].calls == 1
        assert rounds_by_shape(result) == [
            (1, None, "task_decomposer", "candidate_valid"),
            (2, None, "decomposition_reviewer", "independent_pass"),
        ]
        assert not (run_dir / "rounds" / "01-correction").exists()
        assert not (run_dir / "rounds" / "01-correction-request.json").exists()
        progress = (run_dir / "progress.jsonl").read_text(encoding="utf-8")
        assert "author_correction_started" not in progress

        # 6. A provider failure in the correction call is an agent failure, and
        #    the initial deterministic rejection is still retained.
        providers = {
            "codex": QueueProvider([partition_raw, FakeProvider(scenario="provider_error")]),
            "claude": QueueProvider([]),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="correction-provider-failed",
            providers=providers,
        )
        assert result["run_status"] == "agent_failed"
        assert result["author_corrections_used"] == 1
        assert result["latest_candidate"] is None
        assert providers["claude"].calls == 0
        assert result["rejection_reasons"][0].startswith(
            "round 1: initial candidate deterministic validation failed: "
        )
        assert any(
            reason.startswith("round 1 correction: AgentResult failed")
            for reason in result["rejection_reasons"]
        )
        assert not (run_dir / "decomposition_result.json").exists()

        # 7. Source revalidation binds the correction call exactly as it binds
        #    any round: a source that moves under the correction fails closed.
        original_head = git(source, "rev-parse", "HEAD")
        parent_head = git(source, "rev-parse", "HEAD^")
        protected = protected_bytes(source)

        def move_head(call_number: int) -> None:
            if call_number == 2:
                (source / ".git" / "refs" / "heads" / "main").write_text(
                    parent_head + "\n", encoding="ascii"
                )

        providers = {
            "codex": QueueProvider(
                [partition_raw, two_child_raw], mutate=move_head
            ),
            "claude": QueueProvider([]),
        }
        mutated = run_round_robin_decomposition(
            source=source,
            output_root=output_root,
            task_id="NSC-010",
            provider_order=("codex", "claude"),
            max_calls=2,
            run_id="correction-source-mutated",
            provider_factory=provider_factory(providers),
            _require_physical_read_only_source=False,
        )
        assert mutated["run_status"] == "rejected"
        assert mutated["author_corrections_used"] == 1
        assert mutated["latest_candidate"] is None
        assert providers["claude"].calls == 0
        assert any(
            "source HEAD changed" in reason for reason in mutated["rejection_reasons"]
        )
        assert mutated["rejection_reasons"][0].startswith(
            "round 1: initial candidate deterministic validation failed: "
        )
        assert not (
            output_root / "correction-source-mutated" / "decomposition_result.json"
        ).exists()
        assert protected_bytes(source) == protected
        (source / ".git" / "refs" / "heads" / "main").write_text(
            original_head + "\n", encoding="ascii"
        )
        assert git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""

    print("author_correction_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
