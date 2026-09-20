"""Add or drop a GER display hold in held-task-ids.json.

Fills two gaps in Pipeline/TaskDesignGER/ger_viewer_marker.py (start|pause|finish):
  hold   -- put a task in task_ids (grey "Outside Current Run") so `start` and
            ger_node.py's confirm_held() accept it; removes it from released.
  unhold -- drop a task from task_ids and active_ger_task_ids WITHOUT adding it
            to released_ger_task_ids (task returns to its derived state).

Uses the same lock file, schema check, invariants and atomic write_record as the
marker CLI. Display only: it never edits task contracts or dispatch eligibility.
The graph-lead journal remains the operational hold record.

Run from the repository root so the Pipeline imports resolve:
  cd C:\\NSC\\NSC\\NoSafeCircle
  python -B C:\\nscrev\\ger-tools\\hold_ger_task.py hold NSC-080 --checkout-root C:\\NSC\\NoSafeCircle-AssistantCheckouts

`hold` refuses an ID that is not a committed Tasks/<ID>.yaml at the Source HEAD
(--source, default: the current directory), because the viewer rejects an overlay
naming unknown tasks. `unhold` accepts any held ID so a bad entry can be removed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from Pipeline.AssistantControl.checkouts import write_record  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock  # noqa: E402

SCHEMA = "assistant-viewer-held-tasks/v1"
FILENAME = "held-task-ids.json"


def committed_task_ids(source: Path) -> set[str]:
    # Same authority as C:\nscrev\viewer-tools\nsc_viewer.py committed_task_ids.
    result = subprocess.run(
        ["git", "-C", str(source), "ls-tree", "--name-only", "HEAD", "Tasks/"],
        capture_output=True, text=True, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {Path(line).stem for line in result.stdout.splitlines() if line.endswith(".yaml")}


def change(checkout_root: Path, action: str, task_id: str, source: Path | None = None) -> dict:
    task_id = validate_task_id(task_id)
    if action == "hold" and task_id not in committed_task_ids(source or Path.cwd()):
        raise ValueError(f"{task_id} is not committed at Source HEAD; the viewer would reject the overlay")
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
            if (not isinstance(ids, list) or any(not isinstance(item, str) for item in ids)
                    or len(ids) != len(set(ids))):
                raise ValueError(f"Invalid {name} in viewer hold file")
            return {validate_task_id(item) for item in ids}

        held = id_set("task_ids")
        active = id_set("active_ger_task_ids")
        released = id_set("released_ger_task_ids")
        if not active <= held or held & released:
            raise ValueError("Viewer GER marker sets overlap incorrectly")
        if action == "hold":
            held.add(task_id)
            released.discard(task_id)
        elif action == "unhold":
            if task_id not in held:
                raise ValueError(f"{task_id} is not held")
            held.remove(task_id)
            active.discard(task_id)
        else:
            raise ValueError(f"Unknown action: {action}")
        if not active <= held or held & released:
            raise ValueError("Refusing to write overlapping marker sets")
        value["task_ids"] = sorted(held)
        value["active_ger_task_ids"] = sorted(active)
        value["released_ger_task_ids"] = sorted(released)
        write_record(path, value)
        return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("hold", "unhold"))
    parser.add_argument("task_id")
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path.cwd(),
                        help="Source repository whose HEAD Tasks/ define valid IDs (default: current directory)")
    args = parser.parse_args()
    print(json.dumps(change(args.checkout_root, args.action, args.task_id, args.source)))


if __name__ == "__main__":
    main()
