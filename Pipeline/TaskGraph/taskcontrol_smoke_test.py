from __future__ import annotations

import json
import tempfile
from pathlib import Path

from persistent_work_graph import PersistentWorkGraphError, load_persistent_work_graph
from taskcontrol import ready_tasks
from work_graph_persist import persist_work_graph
from work_graph_transform import build_work_graph_plan
from work_graph_transform_smoke_test import make_inputs


def write_json(path: Path, value: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> int:
    inputs = make_inputs()
    plan = build_work_graph_plan(inputs)

    with tempfile.TemporaryDirectory(prefix="taskcontrol-smoke-") as temp_dir:
        root = Path(temp_dir)
        persist_work_graph(plan, inputs, root=root)

        graph = load_persistent_work_graph(root=root)
        assert graph.validation.task_count == 4
        assert graph.validation.root_id == "NSC-001"
        assert [task["id"] for task in ready_tasks(graph)] == ["NSC-003"]

        movement_path = root / "Tasks" / "NSC-003.yaml"
        movement = json.loads(movement_path.read_text(encoding="utf-8"))

        # Live edits must continue to obey the persistent schema contract.
        movement["status"] = "banana"
        write_json(movement_path, movement)
        try:
            load_persistent_work_graph(root=root)
        except PersistentWorkGraphError as exc:
            assert "invalid status" in str(exc)
        else:
            raise AssertionError("Expected invalid live task status to be rejected.")

        # Live task state is allowed to evolve after bootstrap. The bootstrap marker hashes are a
        # historical baseline, so changing a valid task status must not make the loader reject it.
        movement["status"] = "complete"
        write_json(movement_path, movement)

        graph_after_completion = load_persistent_work_graph(root=root)
        assert graph_after_completion.tasks_by_id["NSC-003"]["status"] == "complete"
        assert [task["id"] for task in ready_tasks(graph_after_completion)] == ["NSC-004"]

        # Bootstrap baseline files may change legitimately, but they may not silently disappear.
        movement_path.unlink()
        try:
            load_persistent_work_graph(root=root)
        except PersistentWorkGraphError as exc:
            assert "baseline output is missing" in str(exc)
        else:
            raise AssertionError("Expected deletion of a bootstrap task to be rejected.")

    print("taskcontrol_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
