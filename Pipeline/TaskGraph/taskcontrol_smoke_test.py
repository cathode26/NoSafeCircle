from __future__ import annotations

import json
import tempfile
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from persistent_work_graph import PersistentWorkGraphError, load_persistent_work_graph
from taskcontrol import (
    advisory_ready_tasks,
    build_parser,
    command_authorize,
    command_ready,
    command_show,
    command_states,
)
from work_graph_persist import persist_work_graph
from work_graph_transform import build_work_graph_plan
from work_graph_transform_smoke_test import make_inputs


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class FakeConformanceState:
    task_id: str
    title: str
    state: str

    def to_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "state": self.state,
        }


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
        assert "Evidence-derived current conformance has been proven on at least one real task" in ready_output
        assert "A conformant result does not establish dependency readiness" in ready_output
        assert "Dependency-readiness policy has not been implemented or approved" in ready_output
        assert "Dispatch authorization policy has not been implemented or approved" in ready_output
        assert "State inspection and a conformant result never authorize autonomous execution" in ready_output
        assert "Zero tasks are authorized for autonomous dispatch" in ready_output

        output = StringIO()
        with redirect_stdout(output):
            assert command_authorize(graph, "NSC-003") == 2
        authorize_output = output.getvalue()
        assert "reason_code: evidence_derived_dispatch_policy_not_enabled" in authorize_output
        assert "State inspection and a conformant result never authorize autonomous execution" in authorize_output

        output = StringIO()
        with redirect_stdout(output):
            assert command_show(graph, "NSC-003") == 0
        show_output = output.getvalue()
        assert "Evidence-derived current-state inspection: available" in show_output
        assert "dispatch authorization policy is not enabled" in show_output
        assert "State inspection alone never authorizes execution" in show_output

        context_instances = []

        class FakeConformanceContext:
            def __init__(self):
                self.evaluated: list[str] = []
                context_instances.append(self)

            def evaluate(self, selector: str):
                self.evaluated.append(selector)
                task = graph.tasks_by_id[selector]
                state = "conformant" if selector == "NSC-003" else "not_delivered"
                return FakeConformanceState(selector, task["title"], state)

        output = StringIO()
        with patch("taskcontrol.ConformanceEvaluationContext", FakeConformanceContext):
            with redirect_stdout(output):
                assert command_states(graph) == 0
        assert len(context_instances) == 1
        assert context_instances[0].evaluated == [
            task["id"] for task in sorted(graph.plan.tasks, key=lambda task: int(task["id"].split("-", 1)[1]))
        ]
        states_output = output.getvalue()
        assert "ID       DERIVED_STATE" in states_output
        assert "NSC-003  conformant" in states_output
        assert "not_delivered" in states_output
        assert "Conformant means current committed evidence proves the task contract at HEAD." in states_output
        assert "needs_testing means prior evidence exists but later tracked changes may require retesting." in states_output
        assert "These states do not establish dependency readiness or execution authorization." in states_output

        output = StringIO()
        with patch("taskcontrol.ConformanceEvaluationContext", FakeConformanceContext):
            with redirect_stdout(output):
                assert command_states(graph, state_filter="conformant") == 0
        assert len(context_instances) == 2
        filtered_output = output.getvalue()
        assert "NSC-003  conformant" in filtered_output
        assert "not_delivered" not in filtered_output
        assert "1 task state(s) shown." in filtered_output

        output = StringIO()
        with patch("taskcontrol.ConformanceEvaluationContext", FakeConformanceContext):
            with redirect_stdout(output):
                assert command_states(graph, as_json=True, state_filter="conformant") == 0
        assert len(context_instances) == 3
        json_output = json.loads(output.getvalue())
        assert json_output == [
            {
                "state": "conformant",
                "task_id": "NSC-003",
                "title": graph.tasks_by_id["NSC-003"]["title"],
            }
        ]

        parsed = build_parser().parse_args(["states", "--state", "needs_testing"])
        assert parsed.command == "states"
        assert parsed.state_filter == "needs_testing"

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
