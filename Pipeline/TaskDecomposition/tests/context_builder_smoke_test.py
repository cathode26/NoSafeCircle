from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.contracts import validate_repository_path
from TaskDecomposition.context_builder import build_context, capture_clean_source
from TaskDecomposition.policy import semantic_json_sha256
from TaskDecomposition.tests.test_support import create_repository


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nsc-d1b-context-source-") as source_text:
        source = Path(source_text)
        tasks = create_repository(source)
        identity = capture_clean_source(source)
        first, _ = build_context(identity, "NSC-010")
        second, _ = build_context(identity, "NSC-010")
        assert first.canonical_json().encode("utf-8") == second.canonical_json().encode("utf-8")
        assert first.semantic_sha256 == second.semantic_sha256
        assert first.semantic_sha256 == hashlib.sha256(
            first.canonical_json().encode("utf-8")
        ).hexdigest()

        payload = first.to_dict()
        selected_raw = (source / "Tasks" / "NSC-010.yaml").read_bytes()
        selected = payload["selected_task"]
        assert selected["exact_byte_sha256"] == hashlib.sha256(selected_raw).hexdigest()
        assert selected["semantic_contract_sha256"] == semantic_json_sha256(tasks["NSC-010"])
        assert selected["task_execution_identity"] == {
            "path": "Tasks/NSC-010.yaml",
            "revision": 2,
            "sha256": hashlib.sha256(selected_raw).hexdigest(),
        }
        assert selected["d1a_semantic_parent_identity"] == {
            "task_id": "NSC-010",
            "contract_revision": 2,
            "contract_sha256": semantic_json_sha256(tasks["NSC-010"]),
        }
        assert selected["task_execution_identity"]["sha256"] != selected["d1a_semantic_parent_identity"]["contract_sha256"]

        assert [item["id"] for item in payload["task_catalog"]] == [
            "NSC-001", "NSC-002", "NSC-003", "NSC-004",
            "NSC-010", "NSC-011", "NSC-012", "NSC-1000",
        ]
        neighborhood = payload["graph_neighborhood"]
        assert neighborhood["immediate_parent_contract"]["id"] == "NSC-002"
        assert [item["id"] for item in neighborhood["direct_child_contracts"]] == ["NSC-011"]
        assert [item["id"] for item in neighborhood["dependency_contracts"]] == ["NSC-003"]
        assert [item["id"] for item in neighborhood["direct_dependent_contracts"]] == ["NSC-012"]
        assert [item["id"] for item in neighborhood["sibling_contracts"]] == ["NSC-004"]

        assert payload["relevant_resource_groups"] == [
            {
                "resource_key": "repo-file:Assets/Shared.cs",
                "work_ids": ["NSC-003", "NSC-010"],
                "reconciliation_keys": ["dependency-runtime", "selected-parent"],
            }
        ]
        gdd_bytes = (source / "Docs" / "GDD" / "No_Safe_Circle_GDD.md").read_bytes()
        assert payload["canonical_gdd"]["full_committed_utf8_text"] == gdd_bytes.decode("utf-8")
        assert payload["canonical_gdd"]["exact_byte_sha256"] == hashlib.sha256(gdd_bytes).hexdigest()
        assert payload["selected_task_gdd_evidence"] == tasks["NSC-010"]["gdd_evidence"]
        historical = payload["historical_bootstrap_observations"]
        assert "Historical bootstrap" in historical["authority_label"]
        assert "not current repository truth" in historical["authority_label"]
        assert historical["repository_state_at_bootstrap"] == "missing"
        assert historical["repository_evidence_at_bootstrap"] == tasks["NSC-010"]["repository_evidence_at_bootstrap"]
        assert payload["approved_artifacts"] == []
        assert "not implemented" in payload["approved_artifacts_authority_note"]
        assert "unapproved drafts" in payload["approved_artifacts_authority_note"]

        expected_paths = [
            "Tasks/NSC-010.yaml",
            "Docs/GDD/No_Safe_Circle_GDD.md",
            "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml",
            "Tasks/NSC-002.yaml",
            "Tasks/NSC-011.yaml",
            "Tasks/NSC-003.yaml",
            "Assets/Shared.cs",
            "Assets/Synthetic.unity",
            "Assets/Evidence.cs",
        ]
        assert payload["context_paths"] == expected_paths
        for path in payload["context_paths"]:
            assert validate_repository_path(path, field="test context path") == path

        canonical = first.canonical_json()
        assert str(source) not in canonical
        assert "timestamp_utc" not in canonical
        assert "duration_seconds" not in canonical
        assert "run_id" not in canonical
        assert "decomposition-output" not in canonical
        assert payload["source_identity"] == {
            "head_commit": identity.head,
            "head_tree": identity.tree,
            "branch": "main",
        }
        json.loads(canonical)

        detached = first.to_dict()
        detached["selected_task"]["contract"]["title"] = "mutated"
        detached["context_paths"].append("Tasks/NSC-999.yaml")
        assert first.to_dict()["selected_task"]["contract"]["title"] != "mutated"
        assert "Tasks/NSC-999.yaml" not in first.to_dict()["context_paths"]

    print("context_builder_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
