from __future__ import annotations

import json
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from persistent_work_graph import PersistentWorkGraphError, load_persistent_work_graph
from taskcontrol import advisory_ready_tasks, command_authorize, command_ready, command_show
from work_graph_persist import persist_work_graph
from work_graph_transform import build_work_graph_plan
from work_graph_transform_smoke_test import make_inputs


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    inputs = make_inputs()
    plan = build_work_graph_plan(inputs)
    with tempfile.TemporaryDirectory(prefix="taskcontrol-v2-") as temp:
        root = Path(temp)
        persist_work_graph(plan, inputs, root=root)
        graph = load_persistent_work_graph(root=root)
        assert graph.validation.task_schema_version == "2.0"
        assert advisory_ready_tasks(graph) == []
        output = StringIO()
        with redirect_stdout(output):
            assert command_ready(graph) == 0
        ready_output = output.getvalue()
        assert "TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED" in ready_output
        assert "Evidence-derived current-state inspection exists" in ready_output
        assert "Dependency readiness is not derived" in ready_output
        assert "State inspection alone never authorizes execution" in ready_output
        assert "Zero tasks are authorized for autonomous dispatch" in ready_output

        output = StringIO()
        with redirect_stdout(output):
            assert command_authorize(graph, "NSC-003") == 2
        authorize_output = output.getvalue()
        assert "reason_code: evidence_derived_dispatch_policy_not_enabled" in authorize_output
        assert "State inspection alone never authorizes execution" in authorize_output

        output = StringIO()
        with redirect_stdout(output):
            assert command_show(graph, "NSC-003") == 0
        show_output = output.getvalue()
        assert "Evidence-derived current-state inspection: available" in show_output
        assert "dispatch authorization policy is not enabled" in show_output
        assert "State inspection alone never authorizes execution" in show_output

        movement_path = root / "Tasks" / "NSC-003.yaml"
        movement = json.loads(movement_path.read_text(encoding="utf-8"))
        assert "status" not in movement

        # A top-level operational status edit is rejected by schema v2.
        movement["status"] = "complete"
        write_json(movement_path, movement)
        try:
            load_persistent_work_graph(root=root)
        except PersistentWorkGraphError as exc:
            assert "legacy field 'status'" in str(exc)
        else:
            raise AssertionError("Expected schema-v2 status injection to be rejected.")

    print("taskcontrol_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
