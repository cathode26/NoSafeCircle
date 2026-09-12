"""Keep the exact approved, integrated project without moving an open checkout."""
import json
import uuid
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import ReviewGate, now
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


DEFAULT_SUCCESS_ROOT = Path("C:/NSC/SuccessfullTasks")


def preserve_success(checkouts: Checkouts, task_id: str, root: Path = DEFAULT_SUCCESS_ROOT) -> dict:
    task_id = validate_task_id(task_id)
    root = root.resolve()
    for protected in (checkouts.source, checkouts.root):
        if root.is_relative_to(protected) or protected.is_relative_to(root):
            raise ValueError("Successful projects must have a separate destination directory")
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        record = ReviewGate(checkouts)._read(task_id)
        approval = record.get("approval") or {}
        commit = approval.get("commit")
        candidate = record.get("candidate") or {}
        integration = record.get("integration") or {}
        if (record["status"] != "integrated" or approval.get("decision") != "approve"
                or not commit or candidate.get("commit") != commit or integration.get("candidate") != commit):
            raise ValueError("Only Vincent-approved and integrated candidates belong in SuccessfullTasks")
        source_branch = git(checkouts.source, "branch", "--show-current").decode().strip()
        if source_branch != integration.get("branch"):
            raise ValueError("Source branch differs from the integration record")
        git(checkouts.source, "merge-base", "--is-ancestor", commit, "HEAD")
        destination = root / task_id
        state_root = root / ".assistant-control"
        state_root.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(state_root / "success.lock", timeout_seconds=10):
            receipt_path = state_root / f"{task_id}.json"
            expected = {"source": str(checkouts.source), "task_id": task_id,
                        "commit": commit, "tree": candidate["tree"], "path": str(destination)}
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if any(receipt.get(key) != value for key, value in expected.items()):
                    raise ValueError("Successful task folder is reserved for a different version; preserved unchanged")
            else:
                if destination.exists():
                    raise ValueError(f"Existing successful project is preserved; no overwrite: {destination}")
                receipt = {**expected, "status": "preparing", "created_at": now(),
                           "staging": str(root / f".{task_id}-{uuid.uuid4().hex}")}
                write_record(receipt_path, receipt)
            if not destination.exists():
                staging = Path(receipt["staging"])
                if staging.resolve().parent != root or not staging.name.startswith(f".{task_id}-"):
                    raise ValueError("Successful project staging path changed")
                if staging.exists():
                    raise ValueError(f"Interrupted copy retained for inspection: {staging}")
                git(checkouts.source, "clone", "--no-local", "--no-checkout",
                    str(checkouts.source), str(staging), timeout_seconds=180)
                git(staging, "config", "core.hooksPath", "/dev/null")
                git(staging, "config", "core.longpaths", "true")
                git(staging, "remote", "remove", "origin")
                git(staging, "checkout", "-b", f"successful/{task_id}", commit)
                if destination.exists():
                    raise ValueError("Successful project appeared during copy; both copies preserved")
                staging.rename(destination)
            if destination.resolve() != destination:
                raise ValueError("Successful project folder was redirected")
            if Path(git(destination, "rev-parse", "--show-toplevel").decode().strip()).resolve() != destination:
                raise ValueError("Successful project is not an independent Git root")
            if git(destination, "rev-parse", "HEAD").decode().strip() != commit:
                raise ValueError("Successful project commit changed; existing work preserved")
            if git(destination, "rev-parse", "HEAD^{tree}").decode().strip() != candidate["tree"]:
                raise ValueError("Successful project tree differs")
            if git(destination, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
                raise ValueError("Successful project contains local edits; existing work preserved")
            receipt["status"] = "preserved"
            receipt["completed_at"] = receipt.get("completed_at") or now()
            write_record(receipt_path, receipt)
            record["successful_project"] = expected
            write_record(checkouts.records / f"{task_id}.json", record)
            return record
