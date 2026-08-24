"""Deterministic committed-source context for one Stage D1B.1 decomposition."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.AgentRuntime.contracts import validate_repository_path
from TaskDecomposition.policy import semantic_json_sha256
from persistent_work_graph import (
    PersistentWorkGraph,
    PersistentWorkGraphError,
    load_persistent_work_graph,
)


TASK_ID_RE = re.compile(r"^NSC-[0-9]{3}$")
GDD_PATH = "Docs/GDD/No_Safe_Circle_GDD.md"
RESOURCE_GROUPS_PATH = "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml"
_RESOURCE_PATH_PREFIXES = ("repo-file:", "unity-scene:", "unity-prefab:")


class DecompositionPreflightError(RuntimeError):
    """Raised when committed source cannot safely support a live proposal."""


@dataclass(frozen=True)
class SourceIdentity:
    root: Path
    head: str
    tree: str
    branch: str

    def to_context_dict(self) -> dict[str, str]:
        return {"head_commit": self.head, "head_tree": self.tree, "branch": self.branch}


@dataclass(frozen=True)
class ContextPackage:
    """Canonical immutable snapshot; accessors always return detached data."""

    _canonical: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ContextPackage":
        if type(payload) is not dict:
            raise DecompositionPreflightError("context payload must be an exact JSON object")
        try:
            canonical = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            detached = json.loads(canonical)
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise DecompositionPreflightError(f"context payload is not strict finite JSON: {exc}") from exc
        if type(detached) is not dict:
            raise DecompositionPreflightError("context payload must remain an object")
        return cls(canonical)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._canonical)

    def canonical_json(self) -> str:
        return self._canonical

    @property
    def semantic_sha256(self) -> str:
        return hashlib.sha256(self._canonical.encode("utf-8")).hexdigest()


def _git(root: Path, *args: str, text: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        env=environment,
    )


def capture_clean_source(source: Path) -> SourceIdentity:
    """Resolve a clean repository and bind it to exact HEAD/tree/branch state."""

    try:
        root_text = _git(Path(source), "rev-parse", "--show-toplevel").stdout.strip()
        root = Path(root_text).resolve(strict=True)
        head = _git(root, "rev-parse", "--verify", "HEAD").stdout.strip()
        tree = _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
        branch_result = _git(
            root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False
        )
        if branch_result.returncode not in (0, 1):
            raise DecompositionPreflightError("source branch could not be resolved")
        branch = branch_result.stdout.strip()
        if branch_result.returncode == 0 and not branch:
            raise DecompositionPreflightError("attached source checkout has an empty branch")
        status = _git(
            root, "status", "--porcelain=v1", "--untracked-files=all"
        ).stdout
        if status:
            raise DecompositionPreflightError(
                "source working tree must be completely clean, including untracked files"
            )
    except DecompositionPreflightError:
        raise
    except (OSError, subprocess.CalledProcessError) as exc:
        raise DecompositionPreflightError("source repository identity could not be resolved") from exc
    return SourceIdentity(root, head, tree, branch)


def source_revalidation_reasons(identity: SourceIdentity) -> list[str]:
    reasons: list[str] = []
    try:
        if _git(identity.root, "rev-parse", "HEAD").stdout.strip() != identity.head:
            reasons.append("source HEAD changed during provider invocation")
        if _git(identity.root, "rev-parse", "HEAD^{tree}").stdout.strip() != identity.tree:
            reasons.append("source tree changed during provider invocation")
        branch_result = _git(
            identity.root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False
        )
        if branch_result.returncode not in (0, 1):
            reasons.append("source branch could not be revalidated")
        elif branch_result.stdout.strip() != identity.branch:
            reasons.append("source branch changed during provider invocation")
        if _git(
            identity.root, "status", "--porcelain=v1", "--untracked-files=all"
        ).stdout:
            reasons.append("source working tree changed during provider invocation")
    except (OSError, subprocess.CalledProcessError):
        reasons.append("source identity could not be revalidated")
    return reasons


def require_output_disjoint(source_root: Path, output_root: Path) -> Path:
    source = source_root.resolve(strict=True)
    output = Path(output_root).resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise DecompositionPreflightError(
            "output_root must be filesystem-disjoint from the source repository"
        )
    return output


def require_physical_read_only(source_root: Path) -> None:
    try:
        read_only_flag = getattr(os, "ST_RDONLY", 1)
        if not (os.statvfs(source_root).f_flag & read_only_flag):
            raise DecompositionPreflightError(
                "production source checkout must be physically mounted read-only"
            )
    except DecompositionPreflightError:
        raise
    except OSError as exc:
        raise DecompositionPreflightError(
            "production source read-only mount could not be inspected"
        ) from exc


def committed_bytes(identity: SourceIdentity, path: str) -> bytes:
    validate_repository_path(path, field="committed path")
    try:
        result = _git(
            identity.root, "show", f"{identity.head}:{path}", text=False, check=False
        )
    except OSError as exc:
        raise DecompositionPreflightError(f"committed path cannot be read: {path}") from exc
    if result.returncode:
        raise DecompositionPreflightError(f"committed path cannot be read: {path}")
    return result.stdout


def committed_path_exists(identity: SourceIdentity, path: str) -> bool:
    validate_repository_path(path, field="context path")
    try:
        return _git(
            identity.root, "cat-file", "-e", f"{identity.head}:{path}", check=False
        ).returncode == 0
    except OSError:
        return False


def _parse_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DecompositionPreflightError(f"{label} is not valid UTF-8 JSON-subset YAML") from exc
    if type(value) is not dict:
        raise DecompositionPreflightError(f"{label} must contain an object")
    return value


def _task_number(task: dict[str, Any]) -> int:
    match = re.fullmatch(r"NSC-([0-9]+)", str(task.get("id", "")))
    if match is None:
        raise DecompositionPreflightError(f"validated graph contains invalid task ID: {task.get('id')!r}")
    return int(match.group(1))


def _ordered(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tasks, key=lambda task: (_task_number(task), task["id"]))


def _catalog_entry(task: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id", "reconciliation_key", "title", "kind", "type",
        "contract_disposition", "execution_scope", "decomposition_state",
        "parent", "depends_on", "exclusive_resources",
    )
    return {field: deepcopy(task.get(field)) for field in fields}


def validate_task_selection(task_id: str, task: dict[str, Any]) -> None:
    if not TASK_ID_RE.fullmatch(task_id):
        raise DecompositionPreflightError("task ID must match NSC-###")
    if task.get("id") != task_id or task.get("schema_version") != "2.0":
        raise DecompositionPreflightError(
            "committed schema-v2 task contract does not match selected task"
        )
    if task.get("contract_disposition") != "active":
        raise DecompositionPreflightError("selected task contract must be active")
    if task_id == "NSC-001" or not str(task.get("parent") or "").strip():
        raise DecompositionPreflightError("project root cannot be decomposed")
    if task.get("decomposition_state") == "decomposed":
        raise DecompositionPreflightError("selected task is already decomposed")
    if (
        task.get("execution_scope") == "single_agent"
        and task.get("decomposition_state") == "concrete"
    ):
        raise DecompositionPreflightError(
            "already concrete single_agent work does not require live decomposition"
        )
    eligible_scopes = {
        "needs_execution_decomposition", "human_integration_required", "unknown"
    }
    if (
        task.get("execution_scope") not in eligible_scopes
        and task.get("decomposition_state") == "concrete"
    ):
        raise DecompositionPreflightError(
            "selected task is not meaningfully decomposition-relevant"
        )


def _resource_path(resource: Any) -> str | None:
    if type(resource) is not str:
        return None
    for prefix in _RESOURCE_PATH_PREFIXES:
        if resource.startswith(prefix):
            return resource[len(prefix):]
    return None


def _context_paths(
    identity: SourceIdentity,
    task: dict[str, Any],
    parent: dict[str, Any] | None,
    children: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
) -> list[str]:
    candidates: list[str] = [
        f"Tasks/{task['id']}.yaml", GDD_PATH, RESOURCE_GROUPS_PATH,
    ]
    if parent is not None:
        candidates.append(f"Tasks/{parent['id']}.yaml")
    candidates.extend(f"Tasks/{item['id']}.yaml" for item in children)
    candidates.extend(f"Tasks/{item['id']}.yaml" for item in dependencies)
    for resource in task.get("exclusive_resources", []):
        path = _resource_path(resource)
        if path is not None and committed_path_exists(identity, path):
            candidates.append(path)
    for evidence in task.get("repository_evidence_at_bootstrap", []):
        if type(evidence) is dict and type(evidence.get("path")) is str:
            path = evidence["path"]
            try:
                if committed_path_exists(identity, path):
                    candidates.append(path)
            except Exception:
                continue

    result: list[str] = []
    folded: set[tuple[str, ...]] = set()
    for path in candidates:
        validate_repository_path(path, field="context_paths")
        key = tuple(component.casefold() for component in path.split("/"))
        if key not in folded:
            folded.add(key)
            result.append(path)
    return result


def build_context(identity: SourceIdentity, task_id: str) -> tuple[ContextPackage, PersistentWorkGraph]:
    """Build one deterministic context from the captured clean HEAD."""

    if not TASK_ID_RE.fullmatch(task_id):
        raise DecompositionPreflightError("task ID must match NSC-###")
    task_path = f"Tasks/{task_id}.yaml"
    task_raw = committed_bytes(identity, task_path)
    task = _parse_json_object(task_raw, "committed task contract")
    try:
        graph = load_persistent_work_graph(identity.root)
    except PersistentWorkGraphError as exc:
        raise DecompositionPreflightError(
            f"persistent work graph preflight failed: {exc}"
        ) from exc
    graph_task = graph.tasks_by_id.get(task_id)
    if graph_task is None:
        raise DecompositionPreflightError("selected task is absent from the validated graph")
    if graph_task != task:
        raise DecompositionPreflightError(
            "selected committed task differs from the clean validated work graph"
        )
    validate_task_selection(task_id, task)

    tasks = _ordered([deepcopy(item) for item in graph.plan.tasks])
    by_id = {item["id"]: item for item in tasks}
    parent_id = str(task.get("parent") or "")
    parent = deepcopy(by_id[parent_id]) if parent_id else None
    children = _ordered([deepcopy(item) for item in tasks if item.get("parent") == task_id])
    dependencies = _ordered([deepcopy(by_id[item]) for item in task["depends_on"]])
    dependents = _ordered([deepcopy(item) for item in tasks if task_id in item["depends_on"]])
    siblings = _ordered([
        deepcopy(item) for item in tasks
        if item["id"] != task_id and item.get("parent") == parent_id
    ])

    relevant_ids = {task_id, *task["depends_on"], *(item["id"] for item in children)}
    relevant_groups = [
        deepcopy(group) for group in graph.plan.resource_groups
        if relevant_ids.intersection(group["work_ids"])
    ]
    relevant_groups.sort(key=lambda group: group["resource_key"])

    gdd_raw = committed_bytes(identity, GDD_PATH)
    try:
        gdd_text = gdd_raw.decode("utf-8")
    except UnicodeError as exc:
        raise DecompositionPreflightError("canonical GDD is not valid UTF-8") from exc

    byte_hash = hashlib.sha256(task_raw).hexdigest()
    semantic_hash = semantic_json_sha256(task)
    task_execution_identity = {
        "path": task_path,
        "revision": task["contract_revision"],
        "sha256": byte_hash,
    }
    semantic_identity = {
        "task_id": task_id,
        "contract_revision": task["contract_revision"],
        "contract_sha256": semantic_hash,
    }
    paths = _context_paths(identity, task, parent, children, dependencies)
    payload = {
        "schema_version": "1.0",
        "source_identity": identity.to_context_dict(),
        "selected_task": {
            "path": task_path,
            "exact_byte_sha256": byte_hash,
            "semantic_contract_sha256": semantic_hash,
            "task_execution_identity": task_execution_identity,
            "d1a_semantic_parent_identity": semantic_identity,
            "contract": deepcopy(task),
        },
        "graph_neighborhood": {
            "immediate_parent_contract": parent,
            "direct_child_contracts": children,
            "dependency_contracts": dependencies,
            "direct_dependent_contracts": dependents,
            "sibling_contracts": siblings,
        },
        "task_catalog": [_catalog_entry(item) for item in tasks],
        "relevant_resource_groups": relevant_groups,
        "canonical_gdd": {
            "path": GDD_PATH,
            "exact_byte_sha256": hashlib.sha256(gdd_raw).hexdigest(),
            "full_committed_utf8_text": gdd_text,
        },
        "selected_task_gdd_evidence": deepcopy(task.get("gdd_evidence", [])),
        "historical_bootstrap_observations": {
            "authority_label": (
                "Historical bootstrap observations only; they may be stale and are not current repository truth."
            ),
            "repository_state_at_bootstrap": deepcopy(
                task.get("repository_state_at_bootstrap")
            ),
            "repository_evidence_at_bootstrap": deepcopy(
                task.get("repository_evidence_at_bootstrap", [])
            ),
        },
        "approved_artifacts": [],
        "approved_artifacts_authority_note": (
            "Approved-artifact retrieval is not implemented in D1B.1; unapproved drafts are never trusted context."
        ),
        "context_paths": paths,
        "authority_notes": {
            "gdd": "The canonical GDD is game-design authority.",
            "repository": "The current committed repository is implementation evidence, not design authority.",
            "task_contracts": "Task contracts define approved work.",
            "decomposer": "The Decomposer creates human-review proposals only.",
            "excluded_authority": (
                "No context or result establishes readiness, authorization, delivery, conformance, or completion."
            ),
        },
    }
    return ContextPackage.from_payload(payload), graph
