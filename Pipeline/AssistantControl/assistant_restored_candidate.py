"""Register a committed assistant-restored Unity candidate for human testing."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan, validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


class AssistantRestoredCandidateError(ValueError):
    """The committed restored candidate is not safe to expose for review."""


_SHA = re.compile(r"^[0-9a-f]{40}$")
_TERMINAL_WORKER = {"succeeded", "failed", "stopped", "spawn_failed"}
_ART_SUFFIXES = {".gif", ".json", ".md", ".png", ".zip"}
_MAX_ART_PATHS = 512


def _read_owned(checkouts: Checkouts, task_id: str) -> tuple[Path, dict[str, Any]]:
    task_id = validate_task_id(task_id)
    path = checkouts.records / f"{task_id}.json"
    if not path.is_file():
        raise AssistantRestoredCandidateError("owned task checkout record does not exist")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssistantRestoredCandidateError("owned task checkout record is unreadable") from exc
    checkout = checkouts.root / task_id
    if (record.get("source") != str(checkouts.source) or record.get("task_id") != task_id
            or record.get("checkout") != str(checkout)):
        raise AssistantRestoredCandidateError("task checkout record identity differs")
    checkouts.observe(task_id)
    return path, record


def _require_settled(checkouts: Checkouts, record: Mapping[str, Any], task_id: str) -> None:
    # Once a worker record exists it is the durable successor to the launch
    # handoff.  The launcher entry may intentionally retain its earlier
    # ready_pending state for diagnosis and must not override final settlement.
    worker = record.get("worker") if record.get("worker") is not None else record.get("launch")
    if worker is not None and (
            not isinstance(worker, Mapping)
            or worker.get("status") not in _TERMINAL_WORKER
            or worker.get("capacity_released") is not True):
        raise AssistantRestoredCandidateError("worker is not settled; restored candidate was not registered")
    lock_path, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(lock_path, timeout_seconds=10):
        registry = _read_registry(registry_path, checkouts.source)
        if any(item.get("task_id") == task_id and item.get("checkout_root") == str(checkouts.root)
               for item in registry["reservations"]):
            raise AssistantRestoredCandidateError("active admission reservation remains; restored candidate was not registered")


def _paths(value: Sequence[str], field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AssistantRestoredCandidateError(f"{field} must be a list of repository paths")
    result = tuple(value)
    if not result or any(type(item) is not str or not item or "\\" in item
                         or PurePosixPath(item).is_absolute()
                         or any(part in {"", ".", ".."} for part in PurePosixPath(item).parts)
                         for item in result):
        raise AssistantRestoredCandidateError(f"{field} must contain non-empty relative paths")
    if len({item.casefold() for item in result}) != len(result):
        raise AssistantRestoredCandidateError(f"{field} must not contain duplicate paths")
    return tuple(sorted(result, key=str.casefold))


def _provenance(value: Any, field: str) -> Any:
    if not isinstance(value, (Mapping, list, tuple)) or not value:
        raise AssistantRestoredCandidateError(f"{field} must contain explicit provenance")
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AssistantRestoredCandidateError(f"{field} must be JSON-serializable") from exc


def _inside(path: str, root: str) -> bool:
    folded = path.casefold()
    base = root.rstrip("/").casefold()
    return folded == base or folded.startswith(base + "/")


def _verify_art_candidate(
    checkout: Path, task: Mapping[str, Any], paths: Sequence[str],
) -> dict[str, Any]:
    """Verify a bounded, inventory-backed art-acquisition candidate.

    ExecutionScopePlan deliberately describes code and tests.  Art selection has
    a different deterministic boundary: committed repo-file roots, a bounded
    media/provenance allowlist, and an inventory that authenticates every
    selected PNG and retained raw export.
    """
    if task.get("type") != "art-acquisition":
        raise AssistantRestoredCandidateError(
            "candidate requires a registered execution scope"
        )
    if len(paths) > _MAX_ART_PATHS:
        raise AssistantRestoredCandidateError(
            f"art candidate exceeds the {_MAX_ART_PATHS}-path limit"
        )
    roots = tuple(
        resource[len("repo-file:"):].rstrip("/")
        for resource in task.get("exclusive_resources", [])
        if isinstance(resource, str) and resource.startswith("repo-file:")
    )
    if not roots:
        raise AssistantRestoredCandidateError(
            "art candidate task has no repository resource roots"
        )
    outside = [path for path in paths if not any(_inside(path, root) for root in roots)]
    if outside:
        raise AssistantRestoredCandidateError(
            "art candidate diff is outside task repository resources: " + ", ".join(outside)
        )
    unsupported = [
        path for path in paths if PurePosixPath(path).suffix.casefold() not in _ART_SUFFIXES
    ]
    if unsupported:
        raise AssistantRestoredCandidateError(
            "art candidate contains unsupported file types: " + ", ".join(unsupported)
        )

    inventory_paths = [path for path in paths if path.endswith("/source-inventory.json")]
    if len(inventory_paths) != 1:
        raise AssistantRestoredCandidateError(
            "art candidate requires exactly one committed source-inventory.json"
        )
    inventory_path = inventory_paths[0]
    try:
        inventory = json.loads((checkout / Path(inventory_path)).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssistantRestoredCandidateError("art source inventory is unreadable") from exc
    if (not isinstance(inventory, Mapping)
            or inventory.get("schema_version") != "nsc-pixellab-wizard-source/v1"
            or inventory.get("task_id") != task.get("id")):
        raise AssistantRestoredCandidateError("art source inventory identity differs")
    sources = inventory.get("sources")
    if not isinstance(sources, list) or not sources:
        raise AssistantRestoredCandidateError("art source inventory has no selected sources")

    inventory_root = PurePosixPath(inventory_path).parent
    authorized: set[str] = set()
    raw_exports: set[str] = set()
    source_keys: set[str] = set()

    def verify_file(item: Any, *, expected_suffix: str | None = None) -> str:
        if not isinstance(item, Mapping):
            raise AssistantRestoredCandidateError("art inventory file entry is malformed")
        relative = item.get("path")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or PurePosixPath(relative).is_absolute()
                or any(part in {"", ".", ".."} for part in PurePosixPath(relative).parts)
                or not isinstance(size, int) or size < 0
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise AssistantRestoredCandidateError("art inventory file identity is malformed")
        full = (inventory_root / PurePosixPath(relative)).as_posix()
        if expected_suffix and PurePosixPath(full).suffix.casefold() != expected_suffix:
            raise AssistantRestoredCandidateError("authorized art entry is not a PNG")
        file_path = checkout / Path(full)
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            raise AssistantRestoredCandidateError(
                f"art inventory file is missing: {full}"
            ) from exc
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise AssistantRestoredCandidateError(
                f"art inventory hash or size differs: {full}"
            )
        if full not in paths:
            raise AssistantRestoredCandidateError(
                f"art inventory references a file outside the candidate diff: {full}"
            )
        return full

    for source in sources:
        if not isinstance(source, Mapping):
            raise AssistantRestoredCandidateError("art source inventory entry is malformed")
        key = source.get("source_key")
        if not isinstance(key, str) or not key or key in source_keys:
            raise AssistantRestoredCandidateError("art source key is missing or duplicated")
        source_keys.add(key)
        files = source.get("authorized_files")
        if not isinstance(files, list) or not files:
            raise AssistantRestoredCandidateError(
                f"art source {key} has no authorized files"
            )
        for item in files:
            full = verify_file(item, expected_suffix=".png")
            if full in authorized:
                raise AssistantRestoredCandidateError("authorized art path is duplicated")
            authorized.add(full)
        raw = verify_file(source.get("raw_export"))
        if raw in raw_exports:
            raise AssistantRestoredCandidateError("raw art export path is duplicated")
        raw_exports.add(raw)

    selected_on_disk = {
        path for path in paths
        if "/selected/" in path and PurePosixPath(path).suffix.casefold() == ".png"
    }
    if selected_on_disk != authorized:
        raise AssistantRestoredCandidateError(
            "selected PNG files do not exactly match the authorized art inventory"
        )
    return {
        "schema_version": inventory["schema_version"],
        "inventory_path": inventory_path,
        "inventory_sha256": hashlib.sha256(
            (checkout / Path(inventory_path)).read_bytes()
        ).hexdigest(),
        "source_count": len(source_keys),
        "authorized_png_count": len(authorized),
        "raw_export_count": len(raw_exports),
        "resource_roots": list(roots),
    }


def register_assistant_restored_candidate(
    checkouts: Checkouts,
    task_id: str,
    *,
    base_commit: str,
    candidate_commit: str,
    candidate_tree: str,
    task_contract_sha256: str,
    changed_paths: Sequence[str],
    evidence: Any,
    reference_provenance: Any,
) -> dict[str, Any]:
    """Record a committed restored result without claiming crew review or approval."""
    task_id = validate_task_id(task_id)
    for value, label in ((base_commit, "base_commit"), (candidate_commit, "candidate_commit"),
                         (candidate_tree, "candidate_tree")):
        if type(value) is not str or not _SHA.fullmatch(value):
            raise AssistantRestoredCandidateError(f"{label} must be an exact full Git SHA")
    if type(task_contract_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", task_contract_sha256):
        raise AssistantRestoredCandidateError("task_contract_sha256 must be an exact SHA-256")
    paths = _paths(changed_paths, "changed_paths")
    evidence = _provenance(evidence, "evidence")
    reference_provenance = _provenance(reference_provenance, "reference_provenance")

    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        record_path, record = _read_owned(checkouts, task_id)
        _require_settled(checkouts, record, task_id)
        checkout = Path(record["checkout"])
        if record.get("source_commit") != base_commit:
            raise AssistantRestoredCandidateError("candidate base differs from the pinned checkout commit")
        if git(checkout, "branch", "--show-current").decode().strip() != record.get("branch"):
            raise AssistantRestoredCandidateError("task checkout branch changed")
        if git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            raise AssistantRestoredCandidateError(
                "task checkout has uncommitted changes; commit or preserve them before review"
            )
        if git(checkout, "rev-parse", "HEAD").decode().strip() != candidate_commit:
            raise AssistantRestoredCandidateError("candidate commit is not the checkout HEAD")
        parents = git(checkout, "rev-list", "--parents", "-n", "1", candidate_commit).decode().split()
        if len(parents) != 2 or parents[1] != base_commit:
            raise AssistantRestoredCandidateError("candidate commit parent differs from the pinned base")
        if git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != candidate_tree:
            raise AssistantRestoredCandidateError("candidate tree differs from the exact committed tree")
        if record.get("task_contract_sha256") != task_contract_sha256:
            raise AssistantRestoredCandidateError("candidate contract hash differs from the owned task record")
        task = load_committed_task(checkout, task_id, commit=candidate_commit,
                                   expected_sha256=task_contract_sha256)
        raw_scope = record.get("scope")
        art_inventory = None
        if isinstance(raw_scope, Mapping):
            plan = ExecutionScopePlan.from_dict(raw_scope["plan"])
            allowed = set(plan.existing_implementation_paths + plan.new_implementation_paths
                          + plan.existing_test_paths + plan.new_test_paths)
            if not set(paths).issubset(allowed):
                raise AssistantRestoredCandidateError("candidate diff is outside the registered path scope")
            plan_id = raw_scope.get("plan_id")
            lease_id = raw_scope.get("lease_id")
            candidate_kind = "assistant_restored"
        else:
            art_inventory = _verify_art_candidate(checkout, task, paths)
            plan_id = "assistant-art-" + hashlib.sha256(
                json.dumps(art_inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:24]
            lease_id = None
            candidate_kind = "assistant_restored_art"
        actual = tuple(sorted((line for line in git(checkout, "diff", "--name-only",
                                                     f"{base_commit}..{candidate_commit}", "--")
                               .decode().splitlines() if line), key=str.casefold))
        if actual != paths:
            raise AssistantRestoredCandidateError("registered changed_paths do not match the committed diff")
        candidate = {
            "kind": candidate_kind, "crew_review": False,
            "base_commit": base_commit, "commit": candidate_commit, "tree": candidate_tree,
            "parent": base_commit, "task_contract_sha256": task_contract_sha256,
            "source_base": base_commit, "candidate_commit": candidate_commit,
            "candidate_tree": candidate_tree, "candidate_parent": base_commit,
            "plan_id": plan_id, "lease_id": lease_id,
            "changed_paths": list(paths),
            "evidence": evidence, "reference_provenance": reference_provenance,
            "art_inventory": art_inventory,
        }
        previous = record.get("candidate")
        if previous is not None and previous != candidate:
            raise AssistantRestoredCandidateError("an existing candidate differs; retained for inspection")
        if previous is None:
            record["candidate"] = candidate
            record["approval"] = None
            record["status"] = "awaiting_human"
            write_record(record_path, record)
        return record


register = register_assistant_restored_candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--task-contract-sha256", required=True)
    parser.add_argument("--changed-paths", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--reference-provenance", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = register_assistant_restored_candidate(
            Checkouts(args.source, args.checkout_root), args.task,
            base_commit=args.base_commit, candidate_commit=args.candidate_commit,
            candidate_tree=args.candidate_tree,
            task_contract_sha256=args.task_contract_sha256,
            changed_paths=json.loads(args.changed_paths.read_text(encoding="utf-8-sig")),
            evidence=json.loads(args.evidence.read_text(encoding="utf-8-sig")),
            reference_provenance=json.loads(args.reference_provenance.read_text(encoding="utf-8-sig")),
        )
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"status": "command_failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
