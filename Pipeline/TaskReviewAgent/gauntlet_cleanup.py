"""Hash-bound whole-gauntlet retention/reset plan using canonical task resets.

No branch, Issue, checkout, claim or delivered file is deleted by this module.
Selected operations delegate to reset_task; unspecified contracts and all delivered
code are retained. A plan records the entire initial and expanded task scope.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as generation
from Pipeline.TaskReviewAgent.reset_task import AbandonedRehearsalTaskReset, DecompositionUndoReset
from Pipeline.TaskReviewAgent.polling_orchestrator import SchedulerLock


class CleanupError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(generation._json_bytes(value)).hexdigest()


def sealed(value):
    return {**value, "sha256": digest(value)}


def verify(value):
    if not isinstance(value, dict) or value.get("sha256") != digest({key: item for key, item in value.items() if key != "sha256"}):
        raise CleanupError("cleanup artifact hash mismatch")


def plan_cleanup(manifest, tasks, inventory, *, source, checkout_root, expected_head):
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    try:
        repository = generation.authorized_repository(manifest.get("target_repository"))
    except generation.SyntheticGauntletError as exc:
        raise CleanupError(str(exc)) from exc
    if (manifest.get("manifest_sha256") != digest(unsigned) or manifest.get("schema_version") != "2.0"
            or manifest.get("profile") != "thousand" or manifest.get("target_repository") != repository
            or manifest.get("excluded_task_ids") != ["NSC-042"]
            or manifest.get("target_task_ids") != [f"NSC-{number}" for number in range(2000, 3000)]):
        raise CleanupError("cleanup requires the exact thousand private-rehearsal manifest")
    if re.fullmatch(r"[0-9a-f]{40}", expected_head) is None:
        raise CleanupError("cleanup requires an exact expected HEAD")
    scope = set(manifest["target_task_ids"])
    for task_id in tuple(scope):
        if task_id not in tasks:
            raise CleanupError("initial gauntlet contract is missing")
        for child_id in tasks[task_id].get("decomposition_children", []):
            child = tasks.get(child_id, {})
            if child_id == "NSC-042" or child.get("parent") != task_id or child.get("provenance", {}).get("parent_task_id") != task_id:
                raise CleanupError("dynamic child identity is not bound to its parent")
            scope.add(child_id)
    if not isinstance(inventory, dict) or not set(inventory) <= scope or "NSC-042" in inventory:
        raise CleanupError("cleanup selection is outside the immutable synthetic scope")
    steps = []
    for task_id in sorted(scope, reverse=True):
        item = deepcopy(inventory.get(task_id, {"mode": "retain", "reason": "Preserve committed contracts, delivered code and audit history."}))
        if item.get("mode") not in {"retain", "abandon", "undo"}:
            raise CleanupError("unsupported cleanup mode; delivered-code reverts are excluded")
        if item["mode"] == "undo" and not item.get("graph_delta"):
            raise CleanupError("undo requires the exact stored graph delta")
        if set(item) - {"mode", "reason", "graph_delta"}:
            raise CleanupError("cleanup inventory contains unsupported authority fields")
        steps.append({**item, "task_id": task_id, "contract_sha256": digest(tasks[task_id])})
    return sealed({"schema_version": "1.0", "operation": "thousand_cleanup_plan",
        "repository": repository, "manifest_sha256": manifest["manifest_sha256"],
        "source": str(Path(source).resolve()), "checkout_root": str(Path(checkout_root).resolve()),
        "expected_head": expected_head, "excluded_task_ids": ["NSC-042"], "steps": steps})


def operation_for(plan, step):
    common = dict(source=Path(plan["source"]), checkout_root=Path(plan["checkout_root"]), task_id=step["task_id"])
    if step["mode"] == "abandon":
        return AbandonedRehearsalTaskReset(**common, archive_repository=plan["repository"] + "-Archive")
    if step["mode"] == "undo":
        return DecompositionUndoReset(**common, graph_delta=Path(step["graph_delta"]))
    raise CleanupError("retention has no reset operation")


def verify_plan_source(plan):
    """Rebind the reviewed scope to the actual repository before reset/resume."""
    source = Path(plan["source"])
    repository = generation.authorized_repository(generation._repository_from_origin(
        generation._run(source, "git", "remote", "get-url", "origin")))
    if repository != plan["repository"]:
        raise CleanupError("cleanup source repository differs from its reviewed plan")
    manifest = json.loads(generation._run(source, "git", "show", f"HEAD:{generation.MANIFEST_RELATIVE.as_posix()}"))
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if (manifest.get("manifest_sha256") != plan["manifest_sha256"]
            or manifest.get("manifest_sha256") != digest(unsigned)
            or manifest.get("target_repository") != repository):
        raise CleanupError("cleanup committed manifest differs from its reviewed plan")


def execute(plan, progress_path, *, expected_progress_sha256=None, factory=operation_for, guard=None,
            source_guard=verify_plan_source):
    """Resume partial success, reserving each canonical receipt before side effects."""
    verify(plan)
    try:
        repository = generation.authorized_repository(plan.get("repository"))
    except generation.SyntheticGauntletError as exc:
        raise CleanupError(str(exc)) from exc
    if plan.get("schema_version") != "1.0" or plan.get("operation") != "thousand_cleanup_plan" or plan.get("repository") != repository or plan.get("excluded_task_ids") != ["NSC-042"]:
        raise CleanupError("unsupported cleanup plan")
    if any(step.get("task_id") == "NSC-042" or step.get("mode") not in {"retain", "abandon", "undo"} for step in plan["steps"]):
        raise CleanupError("cleanup scope or mode refused")
    ids = [step["task_id"] for step in plan["steps"]]
    if len(set(ids)) != len(ids) or not {f"NSC-{number}" for number in range(2000, 3000)} <= set(ids):
        raise CleanupError("cleanup plan omitted or duplicated initial scope")
    if any(re.fullmatch(r"NSC-[1-9][0-9]{3,8}", key) is None or int(key[4:]) < 2000 for key in ids):
        raise CleanupError("cleanup task is outside synthetic numeric scope")
    progress_path = Path(progress_path)
    source = Path(plan["source"])
    if progress_path.resolve().is_relative_to(source.resolve()) or progress_path.is_symlink():
        raise CleanupError("cleanup progress must be outside the controller checkout")
    guard = guard or (lambda head: generation._preflight_mutation(source, expected_head=head, confirmed_repository=plan["repository"]))
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = progress_path.with_suffix(".lock")
    if lock_path.is_symlink():
        raise CleanupError("cleanup lock must not be a symlink")
    lock = SchedulerLock(lock_path)
    lock.acquire()
    try:
        if progress_path.exists():
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            verify(progress)
            if progress.get("plan_sha256") != plan["sha256"] or progress.get("sha256") != expected_progress_sha256:
                raise CleanupError("progress identity or expected old hash changed")
            completed = progress.get("completed")
            if (progress.get("schema_version") != "1.0" or not isinstance(completed, list)
                    or any(not isinstance(key, str) for key in completed)
                    or len(set(completed)) != len(completed) or not set(completed) <= set(ids)
                    or progress.get("inflight") not in {None, *ids}
                    or progress.get("inflight") in completed
                    or re.fullmatch(r"[0-9a-f]{40}", str(progress.get("head"))) is None):
                raise CleanupError("unsupported or inconsistent cleanup progress")
        else:
            if expected_progress_sha256 is not None:
                raise CleanupError("expected progress does not exist")
            progress = {"schema_version": "1.0", "plan_sha256": plan["sha256"], "head": plan["expected_head"], "completed": [], "inflight": None}

        def save():
            progress.pop("sha256", None)
            progress.update(sealed(progress))
            generation._write_atomic(progress_path, generation._json_bytes(progress))

        completed_before = tuple(progress["completed"])
        source_verified = False
        for step in plan["steps"]:
            task_id = step["task_id"]
            if task_id in progress["completed"]:
                continue
            if step["mode"] == "retain":
                progress["completed"].append(task_id)
                continue
            source_guard(plan)
            source_verified = True
            operation = factory(plan, step)
            receipt = Path(plan["checkout_root"]) / ".task-review-agent/reset-runs" / task_id / f"gauntlet-{plan['sha256'][:32]}.json"
            if progress["inflight"] is not None and progress["inflight"] != task_id:
                raise CleanupError("another exact reset is still in flight")
            if receipt.exists():
                if progress["inflight"] != task_id:
                    raise CleanupError("unexpected preexisting canonical reset receipt")
                result = operation.resume(receipt)
            else:
                guard(progress["head"])
                exact = operation.preflight()
                if exact.get("main_head", exact.get("apply_commit")) != progress["head"]:
                    raise CleanupError("canonical reset expected old HEAD differs")
                progress["inflight"] = task_id
                save()
                result = operation.apply(exact, receipt_path=receipt)
            if result.get("status") != "complete" or result.get("task_id") != task_id or result.get("repository") != plan["repository"]:
                raise CleanupError("canonical reset did not prove exact completion")
            progress["head"] = result.get("undo_commit", progress["head"])
            progress["completed"].append(task_id)
            progress["inflight"] = None
            save()
        if not source_verified and tuple(progress["completed"]) != completed_before:
            source_guard(plan)
        save()
        return progress
    finally:
        lock.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--expected-progress-sha256")
    parser.add_argument("--confirm-repository")
    parser.add_argument("--confirm-plan-sha256")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.plan.resolve().is_relative_to(args.source.resolve()):
        raise CleanupError("cleanup plan must be outside the controller checkout")
    if args.apply:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if (args.confirm_repository != plan.get("repository") or args.confirm_plan_sha256 != plan.get("sha256")
                or args.progress is None or str(args.source.resolve()) != plan.get("source")
                or str(args.checkout_root.resolve()) != plan.get("checkout_root")
                or args.expected_head != plan.get("expected_head")):
            raise CleanupError("apply requires exact repository, reviewed plan hash and progress path")
        print(json.dumps(execute(plan, args.progress, expected_progress_sha256=args.expected_progress_sha256), indent=2))
        return
    manifest = json.loads((args.source / generation.MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    repository = generation.authorized_repository(manifest.get("target_repository"))
    if args.confirm_repository is not None and args.confirm_repository != repository:
        raise CleanupError("confirmed repository differs from the manifest")
    generation._preflight_mutation(args.source, expected_head=args.expected_head, confirmed_repository=repository)
    graph = generation.load_persistent_work_graph(args.source)
    plan = plan_cleanup(manifest, {task["id"]: task for task in graph.plan.tasks},
        json.loads(args.inventory.read_text(encoding="utf-8")), source=args.source,
        checkout_root=args.checkout_root, expected_head=args.expected_head)
    verify_plan_source(plan)
    with args.plan.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"status": "ready_dry_run", "plan_sha256": plan["sha256"], "steps": len(plan["steps"])}))


if __name__ == "__main__":
    main()
