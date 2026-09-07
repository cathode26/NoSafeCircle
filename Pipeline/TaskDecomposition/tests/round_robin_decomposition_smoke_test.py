from __future__ import annotations

from copy import deepcopy
import json
import os
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

from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.providers.fake import FakeProvider
from TaskDecomposition.context_builder import DecompositionPreflightError
from TaskDecomposition.policy import validate_decomposition_result
from TaskDecomposition.round_robin_decomposition import (
    candidate_sha256,
    run_round_robin_decomposition,
    validate_provider_order,
)
from TaskDecomposition.tests.test_support import (
    create_repository,
    decomposed_result,
    protected_bytes,
)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def assert_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert b"NaN" not in raw and b"Infinity" not in raw
    value = json.loads(raw.decode("utf-8"))
    assert isinstance(value, dict)
    return value


class QueueProvider:
    provider_identifier = "fake"

    def __init__(self, outputs: list[Any], *, mutate=None) -> None:
        self.outputs = list(outputs)
        self.mutate = mutate
        self.calls = 0
        self.requests = []

    def invoke(self, request, model):
        self.calls += 1
        self.requests.append(request)
        if self.mutate is not None:
            self.mutate(self.calls)
        if not self.outputs:
            raise AssertionError("QueueProvider was invoked more times than configured")
        output = self.outputs.pop(0)
        if isinstance(output, FakeProvider):
            return output.invoke(request, model)
        if callable(output):
            output = output()
        return FakeProvider(structured_output=output).invoke(request, model)


def provider_factory(providers: dict[str, QueueProvider]):
    def factory(provider_name: str, _source: Path, role: str):
        assert role in {"task_decomposer", "decomposition_reviewer"}, role
        key = f"{provider_name}-decomposition"
        configuration = RuntimeConfiguration(
            {
                key: {
                    "provider": "fake",
                    "models": {
                        "low_cost": "deterministic-fake-model",
                        "standard": "deterministic-fake-model",
                        "high_reasoning": "deterministic-fake-model",
                    },
                }
            }
        )
        return key, configuration, {"fake": providers[provider_name]}

    return factory


def validated_candidate(raw: dict[str, Any], parent: dict[str, Any], tasks) -> Any:
    return validate_decomposition_result(
        raw,
        parent_task=parent,
        existing_reconciliation_keys=(
            task["reconciliation_key"] for task in tasks.values()
        ),
    )


def pass_review(candidate_hash: str, *, resolutions=()) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "reviewed_candidate_sha256": candidate_hash,
        "verdict": "pass",
        "summary": "Independent review found no remaining blocking semantic defects.",
        "findings": [],
        "prior_finding_resolutions": list(resolutions),
        "revised_decomposition": None,
    }


def revise_review(
    candidate_hash: str,
    revised: dict[str, Any],
    *,
    round_number: int,
    suffix: str,
    category: str = "duplicate_responsibility",
    resolutions=(),
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "reviewed_candidate_sha256": candidate_hash,
        "verdict": "revise",
        "summary": "The reviewed candidate contains a blocking semantic defect and has been replaced.",
        "findings": [
            {
                "finding_id": f"round-{round_number:02d}-{suffix}",
                "severity": "blocking",
                "category": category,
                "affected_contracts": ["NSC-010", "proposed:bounded-child"],
                "problem": "Synthetic blocking ownership defect.",
                "required_resolution": "Replace the candidate with a distinct bounded ownership shape.",
            }
        ],
        "prior_finding_resolutions": list(resolutions),
        "revised_decomposition": revised,
    }


def needs_human_review(candidate_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "reviewed_candidate_sha256": candidate_hash,
        "verdict": "needs_human",
        "summary": "Current approved authority does not support a safe dependency ownership decision.",
        "findings": [
            {
                "finding_id": "round-02-authority-gap",
                "severity": "blocking",
                "category": "authority_conflict",
                "affected_contracts": ["NSC-010", "NSC-012"],
                "problem": "Synthetic authority gap.",
                "required_resolution": "Human authority must choose the owning capability.",
            }
        ],
        "prior_finding_resolutions": [],
        "revised_decomposition": None,
    }


def run_case(
    *,
    source: Path,
    output_root: Path,
    run_id: str,
    providers: dict[str, QueueProvider],
    max_calls: int = 4,
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


def expect_preflight(callable_, fragment: str) -> None:
    try:
        callable_()
    except DecompositionPreflightError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"expected preflight failure containing {fragment!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nsc-d1b2-round-robin-") as base_text:
        base = Path(base_text)
        source = base / "source"
        output_root = base / "output"
        tasks = create_repository(source)
        parent = tasks["NSC-010"]
        initial_raw = decomposed_result(parent)
        initial = validated_candidate(initial_raw, parent, tasks)
        initial_hash = candidate_sha256(initial)
        revised_raw = deepcopy(initial_raw)
        revised_raw["children"][0]["notes"] = "Independent reviewer revision."
        revised = validated_candidate(revised_raw, parent, tasks)
        revised_hash = candidate_sha256(revised)
        finding_id = "round-02-duplicate-child-ownership"
        resolved = {
            "finding_id": finding_id,
            "status": "resolved",
            "explanation": "The current revised candidate has distinct bounded ownership.",
        }

        # 1. Common two-call case: generator candidate receives independent PASS.
        providers = {
            "codex": QueueProvider([initial_raw]),
            "claude": QueueProvider([pass_review(initial_hash)]),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="pass-first-review",
            providers=providers,
        )
        assert result["run_status"] == "review_ready"
        assert result["calls_used"] == 2
        assert result["latest_candidate"]["author_provider"] == "codex"
        assert result["independent_approver_provider"] == "claude"
        assert result["unresolved_findings"] == []
        assert (run_dir / "decomposition_result.json").is_file()
        assert (run_dir / "graph_delta.json").is_file()
        assert providers["codex"].requests[0].role == "task_decomposer"
        assert providers["claude"].requests[0].role == "decomposition_reviewer"
        reviewer_prompt = providers["claude"].requests[0].prompt
        assert "The provider that most recently authored a candidate may not approve" in reviewer_prompt
        assert "duplicate responsibility" in reviewer_prompt
        assert initial_hash in reviewer_prompt
        progress = (run_dir / "progress.jsonl").read_text(encoding="utf-8")
        assert reviewer_prompt not in progress

        # 2. Genuine round robin: Claude revises, then Codex independently passes.
        providers = {
            "codex": QueueProvider(
                [initial_raw, pass_review(revised_hash, resolutions=[resolved])]
            ),
            "claude": QueueProvider(
                [
                    revise_review(
                        initial_hash,
                        revised_raw,
                        round_number=2,
                        suffix="duplicate-child-ownership",
                    )
                ]
            ),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="revise-then-pass",
            providers=providers,
        )
        assert result["run_status"] == "review_ready"
        assert result["calls_used"] == 3
        assert result["latest_candidate"]["sha256"] == revised_hash
        assert result["latest_candidate"]["author_provider"] == "claude"
        assert result["independent_approver_provider"] == "codex"
        assert [round_["requested_provider"] for round_ in result["rounds"]] == [
            "codex",
            "claude",
            "codex",
        ]
        assert result["finding_history"][0]["findings"][0]["finding_id"] == finding_id
        assert result["unresolved_findings"] == []
        assert assert_json(run_dir / "decomposition_result.json")["children"][0]["notes"] == "Independent reviewer revision."

        # 3. PASS cannot silently omit resolution of a prior blocking finding.
        providers = {
            "codex": QueueProvider([initial_raw, pass_review(revised_hash)]),
            "claude": QueueProvider(
                [
                    revise_review(
                        initial_hash,
                        revised_raw,
                        round_number=2,
                        suffix="duplicate-child-ownership",
                    )
                ]
            ),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="unresolved-pass-rejected",
            providers=providers,
        )
        assert result["run_status"] == "rejected"
        assert any("exactly cover" in reason for reason in result["rejection_reasons"])
        assert not (run_dir / "decomposition_result.json").exists()

        # 4. Circuit breaker: a revision on the final call cannot self-approve.
        providers = {
            "codex": QueueProvider([initial_raw]),
            "claude": QueueProvider(
                [
                    revise_review(
                        initial_hash,
                        revised_raw,
                        round_number=2,
                        suffix="duplicate-child-ownership",
                    )
                ]
            ),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="revision-at-limit",
            providers=providers,
            max_calls=2,
        )
        assert result["run_status"] == "needs_human"
        assert result["latest_candidate"]["author_provider"] == "claude"
        assert result["independent_approver_provider"] is None
        assert result["unresolved_findings"][0]["finding_id"] == finding_id
        assert not (run_dir / "decomposition_result.json").exists()

        # 5. Reviewer may stop at an explicit human authority boundary.
        providers = {
            "codex": QueueProvider([initial_raw]),
            "claude": QueueProvider([needs_human_review(initial_hash)]),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="reviewer-needs-human",
            providers=providers,
        )
        assert result["run_status"] == "needs_human"
        assert result["unresolved_findings"][0]["category"] == "authority_conflict"
        assert not (run_dir / "decomposition_result.json").exists()

        # 6. A structurally valid review with a semantically invalid replacement is rejected.
        invalid_revised = deepcopy(revised_raw)
        invalid_revised["parent_requirement_coverage"].pop()
        providers = {
            "codex": QueueProvider([initial_raw]),
            "claude": QueueProvider(
                [
                    revise_review(
                        initial_hash,
                        invalid_revised,
                        round_number=2,
                        suffix="invalid-replacement",
                    )
                ]
            ),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="invalid-revision",
            providers=providers,
        )
        assert result["run_status"] == "rejected"
        assert any("Missing parent requirement coverage" in reason for reason in result["rejection_reasons"])
        assert not (run_dir / "decomposition_result.json").exists()

        # 7. Finding IDs are round-owned and may not be reused with a stale prefix.
        second_revised_raw = deepcopy(revised_raw)
        second_revised_raw["children"][0]["notes"] = "Second independent revision."
        providers = {
            "codex": QueueProvider(
                [
                    initial_raw,
                    revise_review(
                        revised_hash,
                        second_revised_raw,
                        round_number=2,
                        suffix="duplicate-child-ownership",
                        resolutions=[resolved],
                    ),
                ]
            ),
            "claude": QueueProvider(
                [
                    revise_review(
                        initial_hash,
                        revised_raw,
                        round_number=2,
                        suffix="duplicate-child-ownership",
                    )
                ]
            ),
        }
        result, _ = run_case(
            source=source,
            output_root=output_root,
            run_id="finding-id-reuse",
            providers=providers,
        )
        assert result["run_status"] == "rejected"
        assert any("round-03" in reason or "reuses prior" in reason for reason in result["rejection_reasons"])

        # 8. Provider failure in an independent review remains agent_failed.
        providers = {
            "codex": QueueProvider([initial_raw]),
            "claude": QueueProvider([FakeProvider(scenario="provider_error")]),
        }
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="review-provider-failed",
            providers=providers,
        )
        assert result["run_status"] == "agent_failed"
        assert not (run_dir / "decomposition_result.json").exists()

        # 9. A provider-induced source mutation is detected after the exact call.
        original_head = git(source, "rev-parse", "HEAD")
        parent_head = git(source, "rev-parse", "HEAD^")
        protected = protected_bytes(source)

        def move_head(call_number: int) -> None:
            assert call_number == 1
            (source / ".git" / "refs" / "heads" / "main").write_text(
                parent_head + "\n", encoding="ascii"
            )

        providers = {
            "codex": QueueProvider([initial_raw], mutate=move_head),
            "claude": QueueProvider([]),
        }
        mutated = run_round_robin_decomposition(
            source=source,
            output_root=output_root,
            task_id="NSC-010",
            provider_order=("codex", "claude"),
            max_calls=4,
            run_id="source-mutated",
            provider_factory=provider_factory(providers),
            _require_physical_read_only_source=False,
        )
        assert mutated["run_status"] == "rejected"
        assert any("source HEAD changed" in reason for reason in mutated["rejection_reasons"])
        assert protected_bytes(source) == protected
        (source / ".git" / "refs" / "heads" / "main").write_text(
            original_head + "\n", encoding="ascii"
        )
        assert git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""

        # 10. Provider rotation and call limits fail closed before invocation.
        for providers in (("codex",), ("codex", "codex"), ("codex", "bogus")):
            expect_preflight(
                lambda providers=providers: validate_provider_order(providers),
                "provider",
            )
        expect_preflight(
            lambda: run_round_robin_decomposition(
                source=source,
                output_root=output_root,
                task_id="NSC-010",
                provider_order=("codex", "claude"),
                max_calls=1,
                run_id="bad-call-limit",
                provider_factory=provider_factory(
                    {
                        "codex": QueueProvider([]),
                        "claude": QueueProvider([]),
                    }
                ),
                _require_physical_read_only_source=False,
            ),
            "between 2 and 12",
        )

        # Compose must provide one source-read-only service with both auth volumes.
        compose_text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        assert "round-robin-decompose:" in compose_text
        service = compose_text.split("  round-robin-decompose:", 1)[1]
        assert "- .:/workspace:ro" in service
        assert "- claude-config:/home/agent/.claude" in service
        assert "- codex-config:/home/agent/.codex" in service
        assert "NSC_DECOMPOSITION_OUTPUT_ROOT: /decomposition-output" in service

    print("round_robin_decomposition_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
