from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.providers.fake import FakeProvider
from TaskDecomposition.context_builder import DecompositionPreflightError
from TaskDecomposition.policy import validate_decomposition_result
from TaskDecomposition.round_robin_decomposition import candidate_sha256
from TaskDecomposition.run_reviewer_replay_ab import run_reviewer_replay_ab
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
    value = json.loads(raw.decode("utf-8"))
    assert isinstance(value, dict)
    return value


class QueueProvider:
    provider_identifier = "fake"

    def __init__(self, outputs: list[Any]) -> None:
        self.outputs = list(outputs)
        self.calls = 0
        self.requests = []

    def invoke(self, request, model):
        self.calls += 1
        self.requests.append(request)
        if not self.outputs:
            raise AssertionError("QueueProvider was invoked more times than configured")
        output = self.outputs.pop(0)
        return FakeProvider(structured_output=output).invoke(request, model)


def provider_factory(provider: QueueProvider):
    def factory(provider_name: str, _source: Path):
        assert provider_name == "claude"
        key = "claude-decomposition"
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
        return key, configuration, {"fake": provider}

    return factory


class FakeRetriever:
    def __init__(self) -> None:
        self.data = {"source": {"sha256": "f" * 64}}
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        self.calls.append((query, top_k))
        return [
            {
                "chunk_id": "nsc-gdd-001",
                "title": "Synthetic Canon",
                "section": "Synthetic",
                "subsection": None,
                "score": 50.0,
                "source": {
                    "file": "Docs/GDD/No_Safe_Circle_GDD.md",
                    "start_line": 1,
                    "end_line": 4,
                },
                "text": "Bounded deterministic canon for replay testing.",
            }
        ][:top_k]


def pass_review(candidate_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "reviewed_candidate_sha256": candidate_hash,
        "verdict": "pass",
        "summary": "Independent review found no blocking semantic defects.",
        "findings": [],
        "prior_finding_resolutions": [],
        "revised_decomposition": None,
    }


def expect_preflight(callable_, fragment: str) -> None:
    try:
        callable_()
    except DecompositionPreflightError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"expected preflight failure containing {fragment!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nsc-reviewer-replay-") as temp_text:
        base = Path(temp_text)
        source = base / "source"
        output_root = base / "output"
        tasks = create_repository(source)
        parent = tasks["NSC-010"]
        raw_candidate = decomposed_result(parent)
        candidate = validate_decomposition_result(
            raw_candidate,
            parent_task=parent,
            existing_reconciliation_keys=(
                task["reconciliation_key"] for task in tasks.values()
            ),
        )
        expected_hash = candidate_sha256(candidate)
        candidate_path = base / "candidate.json"
        candidate_path.write_text(
            json.dumps(
                raw_candidate,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        provider = QueueProvider(
            [pass_review(expected_hash), pass_review(expected_hash)]
        )
        retriever = FakeRetriever()
        before_head = git(source, "rev-parse", "HEAD")
        before_protected = protected_bytes(source)

        result = run_reviewer_replay_ab(
            source=source,
            output_root=output_root,
            task_id="NSC-010",
            candidate_path=candidate_path,
            expected_candidate_sha256=expected_hash,
            candidate_author_provider="codex",
            reviewer_provider="claude",
            arm_order=("full", "rag"),
            run_id="controlled-replay",
            provider_factory=provider_factory(provider),
            retriever=retriever,
            _require_physical_read_only_source=False,
        )

        assert result["run_status"] == "comparison_ready"
        assert result["candidate"]["sha256"] == expected_hash
        assert result["arm_order"] == ["full", "rag"]
        assert set(result["arms"]) == {"full", "rag"}
        assert result["arms"]["full"]["verdict"] == "pass"
        assert result["arms"]["rag"]["verdict"] == "pass"
        assert result["comparison"]["same_provider"] is True
        assert result["comparison"]["same_model"] is True
        assert result["comparison"]["same_reviewed_candidate_sha256"] is True
        assert result["comparison"]["verdicts_match"] is True
        assert provider.calls == 2
        assert len(provider.requests) == 2
        assert all(
            request.role == "decomposition_reviewer"
            for request in provider.requests
        )
        full_prompt = provider.requests[0].prompt
        rag_prompt = provider.requests[1].prompt
        assert "BEGIN DETERMINISTIC GDDRAG REVIEW HINTS" not in full_prompt
        assert "BEGIN DETERMINISTIC GDDRAG REVIEW HINTS" in rag_prompt
        assert expected_hash in full_prompt
        assert expected_hash in rag_prompt
        assert result["arms"]["full"]["prompt"]["utf8_bytes"] == len(
            full_prompt.encode("utf-8")
        )
        assert result["arms"]["rag"]["prompt"]["utf8_bytes"] == len(
            rag_prompt.encode("utf-8")
        )
        assert retriever.calls
        assert git(source, "rev-parse", "HEAD") == before_head
        assert git(
            source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ) == ""
        assert protected_bytes(source) == before_protected

        run_dir = output_root / "controlled-replay"
        assert assert_json(run_dir / "reviewer_replay_result.json") == result
        assert (run_dir / "replay_request.json").is_file()
        assert (run_dir / "reviewed_candidate.json").is_file()
        assert (
            run_dir
            / "arms"
            / "rag"
            / "gdd_rag_review_context.json"
        ).is_file()
        assert (run_dir / "arms" / "full" / "review.json").is_file()
        assert (run_dir / "arms" / "rag" / "review.json").is_file()
        assert not (run_dir / "decomposition_result.json").exists()

        calls_before_preflight = provider.calls
        expect_preflight(
            lambda: run_reviewer_replay_ab(
                source=source,
                output_root=output_root,
                task_id="NSC-010",
                candidate_path=candidate_path,
                expected_candidate_sha256="0" * 64,
                provider_factory=provider_factory(provider),
                retriever=retriever,
                run_id="wrong-candidate",
                _require_physical_read_only_source=False,
            ),
            "candidate semantic sha-256 mismatch",
        )
        assert provider.calls == calls_before_preflight

        expect_preflight(
            lambda: run_reviewer_replay_ab(
                source=source,
                output_root=output_root,
                task_id="NSC-010",
                candidate_path=candidate_path,
                expected_candidate_sha256=expected_hash,
                arm_order=("full", "full"),
                provider_factory=provider_factory(provider),
                retriever=retriever,
                run_id="bad-arm-order",
                _require_physical_read_only_source=False,
            ),
            "exactly `full` and `rag`",
        )
        assert provider.calls == calls_before_preflight

    print("reviewer_replay_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
