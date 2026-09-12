#!/usr/bin/env python3
"""Local, regression-only poll timing; preserves its disposable source and run."""
import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_rehearsal_view_test as fixture_module
from Pipeline.TaskReviewAgent import local_rehearsal


def main():
    fixture = fixture_module.LocalRehearsalViewTests()
    fixture.setUp()
    task_ids = ["NSC-1001", "NSC-1003", "NSC-1004", "NSC-1005", "NSC-1007", "NSC-1008", "NSC-898", "NSC-899"]
    for task_id in task_ids:
        task = fixture_module.FAST.contract()
        task["id"] = task_id
        (fixture.source / "Tasks" / (task_id + ".yaml")).write_text(json.dumps(task) + "\n", encoding="utf-8")
    fixture.git("add", "--", "Tasks")
    fixture.git("commit", "-m", "Prepare disposable eight-task viewer measurement")
    context = fixture.create_run("eight-task-timing", task_ids)
    view = fixture.view(context)
    measurements = []
    real_run = local_rehearsal.subprocess.run
    for poll in range(4):
        started = time.perf_counter()
        with mock.patch.object(local_rehearsal.subprocess, "run", wraps=real_run) as calls:
            observed = view.build()
        commands = [list(call.args[0]) for call in calls.call_args_list if call.args and call.args[0][0] == "git"]
        measurements.append({"poll": poll, "seconds": time.perf_counter() - started,
                             "git_calls": len(commands), "git_commands": commands,
                             "tasks": len(observed["tasks"])})
    print(json.dumps({"fixture": str(fixture.root), "source_head": fixture.git("rev-parse", "HEAD"),
                      "source_status_after": fixture.git("status", "--porcelain=v1", "--untracked-files=all"),
                      "measurements": measurements}, indent=2))


if __name__ == "__main__":
    main()
