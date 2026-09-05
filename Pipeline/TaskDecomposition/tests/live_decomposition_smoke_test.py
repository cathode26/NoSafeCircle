from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.providers.fake import FakeProvider
from TaskDecomposition.context_builder import (
    DecompositionPreflightError,
    require_output_disjoint,
)
from TaskDecomposition.live_decomposition import (
    _real_provider_bundle,
    publish_json_no_overwrite,
    provider_configuration,
    run_live_decomposition,
)
from TaskDecomposition.run_decomposition import default_output_root
from TaskDecomposition.tests.test_support import (
    already_concrete_result,
    create_repository,
    decomposed_result,
    fake_factory,
    needs_artifact_result,
    needs_human_result,
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


class CountingProvider:
    provider_identifier = "fake"

    def __init__(self, output: dict[str, Any], *, mutate=None) -> None:
        self.output = output
        self.mutate = mutate
        self.calls = 0

    def invoke(self, request, model):
        self.calls += 1
        if self.mutate is not None:
            self.mutate()
        return FakeProvider(structured_output=self.output).invoke(request, model)


def assert_source_unchanged(
    source: Path, expected_head: str, expected_protected: dict[str, str]
) -> None:
    assert git(source, "rev-parse", "HEAD") == expected_head
    assert git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert protected_bytes(source) == expected_protected


def assert_json_artifact(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert b"NaN" not in raw and b"Infinity" not in raw
    return json.loads(raw.decode("utf-8"))


def run_case(
    *,
    source: Path,
    output_root: Path,
    run_id: str,
    provider: Any,
) -> tuple[dict[str, Any], Path]:
    before_head = git(source, "rev-parse", "HEAD")
    before_protected = protected_bytes(source)
    result = run_live_decomposition(
        source=source,
        output_root=output_root,
        task_id="NSC-010",
        provider_name="codex",
        run_id=run_id,
        provider_factory=fake_factory(provider),
        _require_physical_read_only_source=False,
    )
    assert_source_unchanged(source, before_head, before_protected)
    run_dir = output_root / run_id
    assert assert_json_artifact(run_dir / "decomposition_run_result.json") == result
    return result, run_dir


def expect_blocked(callable_, fragment: str) -> None:
    try:
        callable_()
    except DecompositionPreflightError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"expected preflight blocker containing {fragment!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nsc-d1b-live-") as base_text:
        base = Path(base_text)
        source = base / "source"
        output_root = base / "output"
        tasks = create_repository(source)
        parent = tasks["NSC-010"]

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NSC_DECOMPOSITION_OUTPUT_ROOT", None)
            direct_default = default_output_root(source)
        assert direct_default == source.resolve().parent / "NoSafeCircle-DecompositionOutputs"
        assert not direct_default.is_relative_to(source.resolve())
        assert require_output_disjoint(source, direct_default) == direct_default.resolve()
        configured_default = base / "configured-output"
        with patch.dict(
            os.environ,
            {"NSC_DECOMPOSITION_OUTPUT_ROOT": str(configured_default)},
        ):
            assert default_output_root(source) == configured_default

        compose_text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        external_mount = (
            "${NSC_DECOMPOSITION_HOST_OUTPUT_ROOT:-../NoSafeCircle-DecompositionOutputs}"
            ":/decomposition-output:rw"
        )
        assert compose_text.count(external_mount) == 3
        assert "Pipeline/TaskDecomposition/outputs:/decomposition-output" not in compose_text
        assert compose_text.count(
            "NSC_DECOMPOSITION_OUTPUT_ROOT: /decomposition-output"
        ) == 3

        # Production provider construction is exact and is never invoked here.
        claude_key, claude_configuration = provider_configuration("claude")
        codex_key, codex_configuration = provider_configuration("codex")
        assert claude_key == "claude-decomposition"
        assert codex_key == "codex-decomposition"
        assert (
            claude_configuration.to_dict()["provider_configurations"][claude_key]["provider"]
            == "claude-code"
        )
        assert (
            codex_configuration.to_dict()["provider_configurations"][codex_key]["provider"]
            == "openai-codex"
        )
        _, _, claude_registry = _real_provider_bundle("claude", source, "task_decomposer")
        _, _, codex_registry = _real_provider_bundle("codex", source, "task_decomposer")
        assert claude_registry["claude-code"].repository_root == source
        assert not claude_registry["claude-code"].externally_isolated_writable_repository
        assert codex_registry["openai-codex"].repository_root == source.resolve()
        assert codex_registry["openai-codex"].externally_enforced_read_only_repository
        assert not codex_registry["openai-codex"].externally_isolated_writable_repository

        # 1. Valid decomposition: one TaskExecution invocation plus accepted D1A artifacts.
        valid_provider = CountingProvider(decomposed_result(parent))
        result, run_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="valid-decomposed",
            provider=valid_provider,
        )
        assert valid_provider.calls == 1
        assert result["run_status"] == "review_ready"
        assert result["decision"] == "decomposed"
        assert result["authority"] == "review_only_not_applied"
        assert result["actual_provider"] == "fake"
        assert result["actual_model"] == "deterministic-fake-model"
        assert result["decomposition_result_path"] == "decomposition_result.json"
        assert result["graph_delta_path"] == "graph_delta.json"
        assert (run_dir / "decomposition_result.json").is_file()
        delta = assert_json_artifact(run_dir / "graph_delta.json")
        assert delta["authority"] == "review_only_not_applied"
        assert delta["allocated_local_key_to_task_id"] == {"bounded-child": "NSC-1001"}
        invocation_id = Path(result["agent_runtime_result_path"]).parent.name
        task_request_path = run_dir / "task_execution" / invocation_id / "task_request.json"
        runtime_request_path = run_dir / "agent_runtime" / invocation_id / "request.json"
        runtime_result_path = run_dir / "agent_runtime" / invocation_id / "result.json"
        assert task_request_path.is_file() and runtime_request_path.is_file()
        assert runtime_result_path.is_file() and (runtime_result_path.parent / "provider.log").is_file()
        task_request = assert_json_artifact(task_request_path)
        runtime_request = assert_json_artifact(runtime_request_path)
        assert task_request["task_id"] == "NSC-010"
        assert task_request["task_contract_identity"] == result["task_execution_contract_identity"]
        assert runtime_request["role"] == "task_decomposer"
        assert runtime_request["model_capability_class"] == "high_reasoning"
        assert runtime_request["allowed_capabilities"] == ["repository_read", "repository_search"]
        assert runtime_request["write_boundaries"] == {"allowed_paths": [], "denied_paths": []}
        assert runtime_request["budgets"]["token_limit"] is None
        assert runtime_request["provider_configuration_key"] == "codex-decomposition"
        outer_request = assert_json_artifact(run_dir / "decomposition_request.json")
        context_raw = (run_dir / "context.json").read_bytes()
        assert context_raw.endswith(b"\n") and not context_raw.endswith(b"\n\n")
        context = json.loads(context_raw.decode("utf-8"))
        assert outer_request["context_sha256"] == result["context_sha256"]
        assert outer_request["authority"] == "review_only_not_applied"
        semantic_hash = result["d1a_semantic_parent_identity"]["contract_sha256"]
        byte_hash = result["task_execution_contract_identity"]["sha256"]
        assert semantic_hash != byte_hash
        prompt = runtime_request["prompt"]
        identity_instruction = prompt.split(
            "Output parent identity — copy this exact D1A semantic identity into `parent_task`:", 1
        )[1].split("The following distinct TaskExecution identity", 1)[0]
        assert semantic_hash in identity_instruction
        assert byte_hash not in identity_instruction
        assert byte_hash in prompt
        assert "BEGIN DETERMINISTIC COMMITTED CONTEXT" in prompt
        assert "Historical coursework, prior agent outputs, generated reviews" in prompt
        assert "cannot override this Decomposer" in prompt
        normalized_prompt = " ".join(prompt.lower().split())
        assert "^[a-z0-9]+(?:-[a-z0-9]+)*$" in prompt
        assert (
            "underscores, spaces, uppercase letters, leading/trailing hyphens, and "
            "repeated hyphens are forbidden"
            in normalized_prompt
        )
        assert (
            "a `local_key` becomes a proposed durable `reconciliation_key`; use a stable "
            "descriptive domain name"
            in normalized_prompt
        )
        assert "`door-lock-break-lifecycle`" in prompt
        assert "`nsc021_lifecycle_core`" in prompt
        assert "generated decomposition output is review-only evidence" in normalized_prompt
        assert "not current design authority" in prompt
        assert normalized_prompt.count("set `artifact_proposal` to null") == 3
        assert "omit `artifact_proposal`" not in normalized_prompt
        assert "do not emit it as null" not in normalized_prompt
        encoded_gdd = json.dumps(
            context["canonical_gdd"]["full_committed_utf8_text"], ensure_ascii=False
        )[1:-1]
        assert encoded_gdd in prompt
        progress = (run_dir / "progress.jsonl").read_text(encoding="utf-8")
        assert prompt not in progress
        assert "fake provider log" not in progress

        # 2-4. Every valid non-decomposed decision is review-ready without a graph delta.
        decision_cases = (
            ("already-concrete", already_concrete_result(parent), "already_concrete"),
            ("needs-artifact", needs_artifact_result(parent), "needs_artifact"),
            ("needs-human", needs_human_result(parent), "needs_human"),
        )
        for run_id, payload, decision in decision_cases:
            case, case_dir = run_case(
                source=source,
                output_root=output_root,
                run_id=run_id,
                provider=FakeProvider(structured_output=payload),
            )
            assert case["run_status"] == "review_ready"
            assert case["decision"] == decision
            assert (case_dir / "decomposition_result.json").is_file()
            assert not (case_dir / "graph_delta.json").exists()
            assert case["graph_delta_path"] is None
        artifact_final = assert_json_artifact(output_root / "needs-artifact" / "decomposition_run_result.json")
        assert "no artifact has been authorized or generated" in artifact_final["human_next_step"]

        # 5. Structural schema failure remains an AgentRuntime schema_error.
        structural, structural_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="structural-invalid",
            provider=FakeProvider(scenario="malformed_structured_output"),
        )
        assert structural["run_status"] == "agent_failed"
        assert structural["agent_failure_classification"] == "schema_error"
        assert not (structural_dir / "decomposition_result.json").exists()
        assert not (structural_dir / "graph_delta.json").exists()
        raw_structural = assert_json_artifact(
            structural_dir / structural["agent_runtime_result_path"]
        )
        assert raw_structural["failure_classification"] == "schema_error"

        # 6. Structurally valid but semantically incomplete coverage is rejected.
        semantic_bad = already_concrete_result(parent)
        semantic_bad["parent_requirement_coverage"].pop()
        semantic, semantic_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="semantic-invalid",
            provider=FakeProvider(structured_output=semantic_bad),
        )
        assert semantic["run_status"] == "rejected"
        assert any("Missing parent requirement coverage" in reason for reason in semantic["rejection_reasons"])
        assert (semantic_dir / semantic["agent_runtime_result_path"]).is_file()
        assert not (semantic_dir / "decomposition_result.json").exists()
        assert not (semantic_dir / "graph_delta.json").exists()

        # 7. The exact semantic parent identity is mandatory.
        wrong_identity = already_concrete_result(parent)
        wrong_identity["parent_task"]["contract_sha256"] = "0" * 64
        wrong, wrong_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="wrong-parent-identity",
            provider=FakeProvider(structured_output=wrong_identity),
        )
        assert wrong["run_status"] == "rejected"
        assert any("semantic contract SHA-256" in reason for reason in wrong["rejection_reasons"])
        assert not (wrong_dir / "decomposition_result.json").exists()

        # 8. Provider failures retain normalized AgentRuntime classification.
        failed, failed_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="provider-failed",
            provider=FakeProvider(scenario="provider_error"),
        )
        assert failed["run_status"] == "agent_failed"
        assert failed["agent_failure_classification"] == "provider_error"
        assert assert_json_artifact(failed_dir / failed["agent_runtime_result_path"])["status"] == "failed"

        # 9. Read-only role rejects all incompatible provider claims after schema success.
        claims, claims_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="provider-claims",
            provider=FakeProvider(
                structured_output=already_concrete_result(parent),
                claimed_changed_paths=("Assets/Shared.cs",),
                claims_execution_occurred=True,
                claimed_test_commands=("python3 forbidden.py",),
            ),
        )
        assert claims["run_status"] == "rejected"
        assert len(claims["rejection_reasons"]) == 3
        assert not (claims_dir / "decomposition_result.json").exists()

        # 10. A semantically valid result that cannot plan emits no partial delta.
        planner, planner_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="planner-failed",
            provider=FakeProvider(structured_output=decomposed_result(parent, missing_dependency=True)),
        )
        assert planner["run_status"] == "rejected"
        assert any("missing existing dependencies" in reason for reason in planner["rejection_reasons"])
        assert not (planner_dir / "decomposition_result.json").exists()
        assert not (planner_dir / "graph_delta.json").exists()

        # 11. Dirty source is blocked before any provider invocation.
        dirty_provider = CountingProvider(already_concrete_result(parent))
        dirty_path = source / "untracked-dirty.txt"
        dirty_path.write_text("dirty\n", encoding="utf-8")
        expect_blocked(
            lambda: run_live_decomposition(
                source=source,
                output_root=output_root,
                task_id="NSC-010",
                provider_name="codex",
                run_id="dirty-source",
                provider_factory=fake_factory(dirty_provider),
                _require_physical_read_only_source=False,
            ),
            "completely clean",
        )
        assert dirty_provider.calls == 0
        dirty_path.unlink()

        # 12. A provider-induced HEAD mutation is detected before acceptance.
        original_head = git(source, "rev-parse", "HEAD")
        parent_head = git(source, "rev-parse", "HEAD^")
        protected_before_mutation = protected_bytes(source)

        def move_head() -> None:
            (source / ".git" / "refs" / "heads" / "main").write_text(
                parent_head + "\n", encoding="ascii"
            )

        mutating = CountingProvider(already_concrete_result(parent), mutate=move_head)
        mutated = run_live_decomposition(
            source=source,
            output_root=output_root,
            task_id="NSC-010",
            provider_name="codex",
            run_id="source-mutated",
            provider_factory=fake_factory(mutating),
            _require_physical_read_only_source=False,
        )
        mutated_dir = output_root / "source-mutated"
        assert mutated["run_status"] == "rejected"
        assert any("source HEAD changed" in reason for reason in mutated["rejection_reasons"])
        assert not (mutated_dir / "decomposition_result.json").exists()
        assert protected_bytes(source) == protected_before_mutation
        (source / ".git" / "refs" / "heads" / "main").write_text(
            original_head + "\n", encoding="ascii"
        )
        assert_source_unchanged(source, original_head, protected_before_mutation)

        # 13. All overlapping output-root relationships are rejected.
        for label, candidate in (
            ("equal", source),
            ("inside", source / "generated"),
            ("containing", base),
        ):
            expect_blocked(
                lambda candidate=candidate, label=label: run_live_decomposition(
                    source=source,
                    output_root=candidate,
                    task_id="NSC-010",
                    provider_name="codex",
                    run_id=f"bad-output-{label}",
                    provider_factory=fake_factory(FakeProvider(structured_output=already_concrete_result(parent))),
                    _require_physical_read_only_source=False,
                ),
                "filesystem-disjoint",
            )

        # 14. Outer run identity collisions never overwrite or reinvoke.
        collision_provider = CountingProvider(already_concrete_result(parent))
        collision, collision_dir = run_case(
            source=source,
            output_root=output_root,
            run_id="collision",
            provider=collision_provider,
        )
        collision_bytes = (collision_dir / "decomposition_run_result.json").read_bytes()
        expect_blocked(
            lambda: run_live_decomposition(
                source=source,
                output_root=output_root,
                task_id="NSC-010",
                provider_name="codex",
                run_id="collision",
                provider_factory=fake_factory(collision_provider),
                _require_physical_read_only_source=False,
            ),
            "already exists",
        )
        assert collision_provider.calls == 1
        assert (collision_dir / "decomposition_run_result.json").read_bytes() == collision_bytes
        assert collision["run_status"] == "review_ready"

        # 15. Injected factory/configuration mismatches fail closed before invocation.
        mismatch_provider = CountingProvider(already_concrete_result(parent))

        def mismatch_factory(provider_name: str, source_root: Path, role: str):
            key, configuration, registry = fake_factory(mismatch_provider)(provider_name, source_root, role)
            return "wrong-decomposition", configuration, registry

        expect_blocked(
            lambda: run_live_decomposition(
                source=source,
                output_root=output_root,
                task_id="NSC-010",
                provider_name="codex",
                run_id="factory-mismatch",
                provider_factory=mismatch_factory,
                _require_physical_read_only_source=False,
            ),
            "configuration key",
        )
        assert mismatch_provider.calls == 0

        # 16. Final artifact publication is atomic and no-overwrite.
        atomic = base / "atomic" / "result.json"
        publish_json_no_overwrite(atomic, {"value": 1})
        original = atomic.read_bytes()
        try:
            publish_json_no_overwrite(atomic, {"value": 2})
        except FileExistsError:
            pass
        else:
            raise AssertionError("atomic publication overwrote an existing artifact")
        assert atomic.read_bytes() == original
        assert not list(atomic.parent.glob(".*.tmp"))

        # 17-19. Prompt identity was checked above; protected sources remain exact,
        # and every provider used by this suite is deterministic and local.
        assert_source_unchanged(source, original_head, protected_before_mutation)
        assert all(
            not path.name.startswith("candidate.patch")
            for path in output_root.rglob("*")
        )
        assert not any(path.name == "candidate.patch" for path in output_root.rglob("*"))

    print("live_decomposition_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
