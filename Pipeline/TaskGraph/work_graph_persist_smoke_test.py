from __future__ import annotations

import json
import tempfile
from pathlib import Path

from work_graph_persist import WorkGraphPersistenceError, persist_work_graph, stage_work_graph_bundle, validate_staged_bundle
from work_graph_transform import build_work_graph_plan
from work_graph_transform_smoke_test import make_inputs


def main() -> int:
    inputs = make_inputs()
    plan = build_work_graph_plan(inputs)
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp)
        hashes = stage_work_graph_bundle(plan, inputs, staging)
        validate_staged_bundle(plan, inputs, staging, hashes)
        first = staging / "Tasks" / "NSC-001.yaml"
        payload = json.loads(first.read_text(encoding="utf-8"))
        payload["title"] = "tampered"
        first.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            validate_staged_bundle(plan, inputs, staging, hashes)
        except WorkGraphPersistenceError:
            pass
        else:
            raise AssertionError("Expected staged tampering rejection.")

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "Pipeline" / "TaskGraph").mkdir(parents=True)
        paths = persist_work_graph(plan, inputs, root=root)
        marker = json.loads(paths.persisted_marker_path.read_text(encoding="utf-8"))
        assert marker["task_contract_schema_version"] == "2.0"
        assert len(list(paths.tasks_dir.glob("NSC-*.yaml"))) == len(plan.tasks)
        try:
            persist_work_graph(plan, inputs, root=root)
        except WorkGraphPersistenceError as exc:
            assert "already complete" in str(exc)
        else:
            raise AssertionError("Expected reseed refusal.")

    print("work_graph_persist_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
