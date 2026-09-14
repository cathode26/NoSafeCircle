"""Update the display-only GER markers in the live AssistantControl root.

This never edits TaskGraph contracts or changes dispatch eligibility. The
graph-lead journal remains the operational hold record.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


SCHEMA = "assistant-viewer-held-tasks/v1"
FILENAME = "held-task-ids.json"


def change_marker(checkout_root: Path, action: str, task_id: str,
                  ready_children: tuple[str, ...] = ()) -> dict:
    task_id = validate_task_id(task_id)
    children = tuple(validate_task_id(child) for child in ready_children)
    if len(set(children)) != len(children) or task_id in children:
        raise ValueError("Ready children must be unique and distinct from the parent")
    if action != "finish" and children:
        raise ValueError("Ready children are allowed only with finish")
    records = checkout_root.resolve() / ".assistant-control"
    path = records / FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Viewer hold file is missing: {path}")
    with _exclusive_file_lock(records / "ger-viewer-overlay.lock", timeout_seconds=10):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
            raise ValueError("Viewer hold file has an unsupported schema")
        def id_set(name: str) -> set[str]:
            ids = value.get(name, [])
            if (not isinstance(ids, list)
                    or any(not isinstance(item, str) for item in ids)
                    or len(ids) != len(set(ids))):
                raise ValueError(f"Invalid {name} in viewer hold file")
            return {validate_task_id(item) for item in ids}

        held = id_set("task_ids")
        active = id_set("active_ger_task_ids")
        released = id_set("released_ger_task_ids")
        if not active <= held or held & released:
            raise ValueError("Viewer GER marker sets overlap incorrectly")
        if action == "start":
            if task_id not in held:
                raise ValueError(f"{task_id} must be held before GER starts")
            active.add(task_id)
            released.discard(task_id)
        elif action == "pause":
            if task_id not in active:
                raise ValueError(f"{task_id} has no active GER marker")
            active.remove(task_id)
        elif action == "finish":
            if task_id not in held:
                raise ValueError(f"{task_id} has no GER hold to release")
            held.remove(task_id)
            active.discard(task_id)
            released.add(task_id)
            for child in children:
                if child in held:
                    raise ValueError(f"{child} is still held; do not mark it ready")
                released.add(child)
        else:
            raise ValueError(f"Unknown GER marker action: {action}")
        value["task_ids"] = sorted(held)
        value["active_ger_task_ids"] = sorted(active)
        value["released_ger_task_ids"] = sorted(released)
        write_record(path, value)
        return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "pause", "finish"))
    parser.add_argument("task_id")
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--ready-child", action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(change_marker(args.checkout_root, args.action, args.task_id,
                                   tuple(args.ready_child))))


if __name__ == "__main__":
    main()
