from __future__ import annotations

"""Generate a clerical review draft and finalize an explicitly approved delivery spec."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TASKGRAPH = ROOT / "Pipeline" / "TaskGraph"
TESTING = ROOT / "Pipeline" / "Testing"
for module_path in (str(TASKGRAPH), str(TESTING)):
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

from conformance_records import ConformanceRecordError, GitRepository, safe_repository_path  # noqa: E402
from persistent_work_graph import PersistentWorkGraphError, load_persistent_work_graph  # noqa: E402
from record_delivery import RecordDeliveryError, parse_delivery_spec, resolve_commit  # noqa: E402
from validation_manifest import ValidationManifestError, load_validation_manifest  # noqa: E402


class TaskDeliveryError(RuntimeError):
    pass


_SHA40 = re.compile(r"[0-9a-f]{40}")
_CREW_SCHEMAS = {"1.0"}
_REVIEW_FIELDS = {
    "schema_version", "review_kind", "review_status", "task", "validated_commit", "validated_tree",
    "base_commit", "candidate_commit", "base_source", "validation_manifests", "artifacts",
    "committed_diff_paths", "surface_candidates", "gates", "human_approval", "review_instructions",
}


def _run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise TaskDeliveryError(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


def _resolve_commit(root: Path, value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskDeliveryError(f"{label} must be a non-empty Git commit expression.")
    try:
        resolved = resolve_commit(root, value)
    except RecordDeliveryError as exc:
        raise TaskDeliveryError(str(exc)) from exc
    if not _SHA40.fullmatch(resolved):
        raise TaskDeliveryError(f"{label} did not resolve to a commit.")
    return resolved


def _clean_repo(root: Path) -> tuple[GitRepository, str, str]:
    try:
        repo = GitRepository(root)
        head = repo.head()
        tree = repo.tree(head)
        if repo.dirty():
            raise TaskDeliveryError("Repository must be completely clean.")
        load_persistent_work_graph(root)
    except (ConformanceRecordError, PersistentWorkGraphError) as exc:
        raise TaskDeliveryError(f"Repository or committed TaskGraph validation failed: {exc}") from exc
    return repo, head, tree


def _outside_new_path(path: Path, root: Path, label: str) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path)
    if path.exists() or path.is_symlink():
        raise TaskDeliveryError(f"{label} already exists; refusing to overwrite: {path}")
    parent = path.parent
    if not parent.is_dir():
        raise TaskDeliveryError(f"{label} parent directory does not exist: {parent}")
    resolved_parent = parent.resolve(strict=True)
    candidate = resolved_parent / path.name
    try:
        candidate.relative_to(root.resolve(strict=True))
    except ValueError:
        return candidate
    raise TaskDeliveryError(f"{label} must be outside the repository.")


def _outside_existing_file(path: Path, root: Path, label: str) -> Path:
    path = path.expanduser().resolve(strict=True)
    try:
        path.relative_to(root.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise TaskDeliveryError(f"{label} must be outside the repository.")
    if not stat.S_ISREG(path.lstat().st_mode):
        raise TaskDeliveryError(f"{label} must be a regular file: {path}")
    return path


def _publish_json(path: Path, value: Any) -> None:
    data = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise TaskDeliveryError(f"Output already exists; refusing to overwrite: {path}") from exc
    except OSError as exc:
        raise TaskDeliveryError(f"Atomic output publication failed for {path}: {exc}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskDeliveryError(f"Unable to parse {label} JSON at {path}.") from exc
    if not isinstance(value, dict):
        raise TaskDeliveryError(f"{label} must contain a JSON object.")
    return value


def _safe_paths(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TaskDeliveryError(f"{label} must be a list when present.")
    result = []
    for index, item in enumerate(value):
        try:
            result.append(safe_repository_path(item, f"{label}[{index}]"))
        except ConformanceRecordError as exc:
            raise TaskDeliveryError(str(exc)) from exc
    return result


def _load_crew(path: Path, task_id: str, root: Path, validated: str) -> tuple[dict[str, Any], str, dict[str, list[str]]]:
    crew = _json_file(path, "crew result")
    if crew.get("schema_version") not in _CREW_SCHEMAS:
        raise TaskDeliveryError("Crew result has an unsupported schema_version.")
    if crew.get("task_id") != task_id or crew.get("crew_status") != "review_ready":
        raise TaskDeliveryError("Crew result task_id/status is not the required matching review_ready result.")
    source_head = crew.get("source_head")
    if not isinstance(source_head, str) or not _SHA40.fullmatch(source_head):
        raise TaskDeliveryError("Crew result source_head must be a lowercase 40-character commit.")
    source_head = _resolve_commit(root, source_head, "crew source_head")
    repo = GitRepository(root)
    if not repo.is_ancestor(source_head, validated):
        raise TaskDeliveryError("Crew result source_head is not an ancestor of the validated commit.")
    source_tree = crew.get("source_tree")
    if source_tree is not None and (not isinstance(source_tree, str) or not _SHA40.fullmatch(source_tree)):
        raise TaskDeliveryError("Crew result source_tree metadata is invalid.")
    path_fields = {
        field: _safe_paths(crew.get(field), f"crew_result.{field}")
        for field in ("implementation_actual_changed_paths", "test_actual_changed_paths", "final_actual_changed_paths")
    }
    return crew, source_head, path_fields


def _file_sha_size(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                hasher.update(chunk)
    except OSError as exc:
        raise TaskDeliveryError(f"Unable to verify external artifact: {path}") from exc
    return hasher.hexdigest(), size


def _human_artifact(path: Path, index: int) -> dict[str, Any]:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise TaskDeliveryError(f"Human-validation input must be a regular file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TaskDeliveryError(f"Human-validation input must be valid UTF-8 text: {path}") from exc
    if not text.strip():
        raise TaskDeliveryError(f"Human-validation input must contain meaningful text: {path}")
    digest, size = _file_sha_size(path)
    return {"id": f"human_validation_{index:02d}", "type": "human_validation", "source_path": str(path.resolve()),
            "name": f"HumanValidation-{index:02d}", "sha256": digest, "size_bytes": size, "validation_manifest": None}


def _manifest_entry(manifest: Any) -> dict[str, Any]:
    digest, size = _file_sha_size(manifest.path)
    return {"path": str(manifest.path), "sha256": digest, "size_bytes": size,
            "commit": manifest.validated_state.commit, "tree": manifest.validated_state.tree,
            "test_platform": manifest.unity.test_platform, "test_filter": manifest.unity.test_filter}


def _unity_artifacts(manifests: list[Any]) -> list[dict[str, Any]]:
    artifacts = []
    for index, manifest in enumerate(manifests, 1):
        label = f"Unity-{manifest.unity.test_platform}-{index:02d}"
        for suffix, artifact_type, fact in (("results", "unity_test_results", manifest.xml), ("log", "unity_log", manifest.log)):
            artifacts.append({"id": f"unity_{index:02d}_{suffix}", "type": artifact_type,
                              "source_path": str(fact.path), "name": label,
                              "sha256": fact.sha256, "size_bytes": fact.size_bytes,
                              "validation_manifest": str(manifest.path)})
    return artifacts


def _resource_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    for prefix in ("repo-file:", "unity-scene:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    try:
        return safe_repository_path(value, "exclusive resource")
    except ConformanceRecordError:
        return None


def create_draft(*, root: Path, task_id: str, manifest_paths: list[Path], output: Path,
                 crew_result: Path | None = None, base_commit: str | None = None,
                 human_validation: list[Path] | None = None) -> Path:
    root = root.resolve(strict=True)
    output = _outside_new_path(output, root, "Draft output")
    repo, head, tree = _clean_repo(root)
    graph = load_persistent_work_graph(root)
    task = graph.tasks_by_id.get(task_id)
    if task is None or task.get("id") != task_id:
        raise TaskDeliveryError(f"Missing or mismatched task contract: {task_id}")
    if task.get("contract_disposition") != "active":
        raise TaskDeliveryError(f"Task {task_id} is not active.")

    if not manifest_paths:
        raise TaskDeliveryError("At least one validation manifest is required.")
    try:
        manifests = [load_validation_manifest(path) for path in manifest_paths]
    except ValidationManifestError as exc:
        raise TaskDeliveryError(str(exc)) from exc
    identities = {(item.validated_state.commit, item.validated_state.tree) for item in manifests}
    if len(identities) != 1:
        raise TaskDeliveryError("Validation manifests do not identify the same commit and tree.")
    validated, validated_tree = next(iter(identities))
    if (head, tree) != (validated, validated_tree):
        raise TaskDeliveryError("Current HEAD/tree does not match the validated state.")

    crew_paths: dict[str, list[str]] = {}
    inferred_base = None
    if crew_result is not None:
        _, inferred_base, crew_paths = _load_crew(crew_result.resolve(strict=True), task_id, root, validated)
    if base_commit is not None:
        base = _resolve_commit(root, base_commit, "base_commit")
        base_source = "explicit_base_commit_override" if inferred_base else "explicit_base_commit"
    elif inferred_base:
        base, base_source = inferred_base, "crew_result.source_head"
    else:
        raise TaskDeliveryError("No base commit can be established; provide --base-commit or --crew-result.")
    if not repo.is_ancestor(base, validated):
        raise TaskDeliveryError("Base commit is not an ancestor of the validated commit.")

    raw_diff = _run_git(root, "diff", "--name-only", "-z", base, validated, "--")
    diff_paths = sorted({safe_repository_path(item.decode("utf-8"), "committed diff path") for item in raw_diff.split(b"\0") if item})
    reasons: dict[str, set[str]] = {}
    for path in diff_paths:
        reasons.setdefault(path, set()).add("committed_diff")
    for field, paths in crew_paths.items():
        for path in paths:
            reasons.setdefault(path, set()).add(f"crew_result.{field}")
    for resource in task.get("exclusive_resources", []):
        path = _resource_path(resource)
        if path and repo.exists(validated, path):
            reasons.setdefault(path, set()).add("task.exclusive_resources")
    candidates = []
    for path in sorted(reasons):
        confirmed = "committed_diff" in reasons[path] or any(item.startswith("crew_result.") for item in reasons[path])
        candidates.append({"path": path, "sources": sorted(reasons[path]), "suggested_role": "implementation" if confirmed else "task resource",
                           "selected": confirmed, "role": ""})

    artifacts = _unity_artifacts(manifests)
    for index, path in enumerate(human_validation or [], 1):
        artifacts.append(_human_artifact(path.resolve(strict=True), index))
    gates = [{"gate_id": gate["gate_id"], "reference": gate["reference"], "requirement": gate["requirement"],
              "evidence": [], "notes": ""} for gate in task["completion_gates"]]
    user_name = subprocess.run(["git", "config", "user.name"], cwd=root, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, check=False).stdout.decode("utf-8", "replace").strip()
    task_bytes = repo.read(validated, f"Tasks/{task_id}.yaml")
    draft = {
        "schema_version": "1.0", "review_kind": "delivery_spec_review", "review_status": "needs_human",
        "task": {"id": task_id, "title": task["title"], "contract_revision": task["contract_revision"],
                 "contract_sha256": hashlib.sha256(task_bytes).hexdigest()},
        "validated_commit": validated, "validated_tree": validated_tree, "base_commit": base,
        "candidate_commit": validated, "base_source": base_source,
        "validation_manifests": [_manifest_entry(item) for item in manifests], "artifacts": artifacts,
        "committed_diff_paths": diff_paths, "surface_candidates": candidates, "gates": gates,
        "human_approval": {"required": True, "decision": "", "approved_by": user_name, "notes": ""},
        "review_instructions": ["Set review_status to approved after review.",
                                "Select only truthful conformance surfaces and provide each explicit role.",
                                "Map known evidence IDs to each gate and write meaningful gate notes.",
                                "Set human_approval.decision to approved and provide approval notes."],
    }
    _publish_json(output, draft)
    return output


def _exact_object(value: Any, label: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise TaskDeliveryError(f"{label} fields differ from the review schema.")
    return value


def _meaningful(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip().lower() in {"todo", "tbd", "placeholder", "n/a"}:
        raise TaskDeliveryError(f"{label} must contain explicit meaningful text.")
    return value


def _verify_external_artifact(raw: Any, manifests_by_path: dict[str, Any]) -> dict[str, str]:
    item = _exact_object(raw, "artifact", {"id", "type", "source_path", "name", "sha256", "size_bytes", "validation_manifest"})
    path = Path(item["source_path"])
    if not path.is_absolute() or not path.exists() or not stat.S_ISREG(path.lstat().st_mode):
        raise TaskDeliveryError(f"Artifact source is not an existing regular file: {path}")
    digest, size = _file_sha_size(path)
    if digest != item["sha256"] or size != item["size_bytes"]:
        raise TaskDeliveryError(f"Artifact changed after draft generation: {path}")
    manifest_path = item["validation_manifest"]
    if item["type"] in {"unity_test_results", "unity_log"} and manifest_path is None:
        raise TaskDeliveryError("Unity artifacts must remain bound to a known validation manifest.")
    if manifest_path is not None and manifest_path not in manifests_by_path:
        raise TaskDeliveryError(f"Artifact references an unknown validation manifest: {manifest_path}")
    if item["type"] == "human_validation":
        _human_artifact(path, 1)
    return {key: item[key] for key in ("id", "type", "source_path", "name")}


def finalize_review(*, root: Path, review_path: Path, output: Path) -> Path:
    root = root.resolve(strict=True)
    review_path = _outside_existing_file(review_path, root, "Review file")
    output = _outside_new_path(output, root, "Final output")
    repo, head, tree = _clean_repo(root)
    review = _json_file(review_path, "delivery review")
    if set(review) != _REVIEW_FIELDS or review.get("schema_version") != "1.0" or review.get("review_kind") != "delivery_spec_review":
        raise TaskDeliveryError("Review document does not match the strict supported schema.")
    if review.get("review_status") != "approved":
        raise TaskDeliveryError("Review status must be explicitly approved.")
    if head != review.get("validated_commit") or tree != review.get("validated_tree"):
        raise TaskDeliveryError("Current HEAD/tree no longer matches the reviewed validated state.")

    task_meta = _exact_object(review["task"], "task", {"id", "title", "contract_revision", "contract_sha256"})
    graph = load_persistent_work_graph(root)
    task = graph.tasks_by_id.get(task_meta["id"])
    if task is None or task.get("contract_disposition") != "active":
        raise TaskDeliveryError("Reviewed task is missing or inactive.")
    task_bytes = repo.read(head, f"Tasks/{task_meta['id']}.yaml")
    if (task.get("title"), task.get("contract_revision"), hashlib.sha256(task_bytes).hexdigest()) != (
            task_meta["title"], task_meta["contract_revision"], task_meta["contract_sha256"]):
        raise TaskDeliveryError("Task identity, revision, or source changed after draft generation.")
    base = _resolve_commit(root, review["base_commit"], "base_commit")
    candidate = _resolve_commit(root, review["candidate_commit"], "candidate_commit")
    if not repo.is_ancestor(base, head) or not repo.is_ancestor(candidate, head):
        raise TaskDeliveryError("Reviewed base/candidate commit relationship is no longer valid.")
    if candidate != head:
        raise TaskDeliveryError("candidate_commit must remain the reviewed validated commit.")
    raw_diff = _run_git(root, "diff", "--name-only", "-z", base, head, "--")
    current_diff = sorted({safe_repository_path(item.decode("utf-8"), "committed diff path") for item in raw_diff.split(b"\0") if item})
    if review["committed_diff_paths"] != current_diff:
        raise TaskDeliveryError("Committed diff inventory or reviewed base changed after draft generation.")

    if not isinstance(review["validation_manifests"], list) or not review["validation_manifests"]:
        raise TaskDeliveryError("validation_manifests must be a nonempty list.")
    manifests_by_path = {}
    for raw in review["validation_manifests"]:
        entry = _exact_object(raw, "validation manifest inventory entry", {"path", "sha256", "size_bytes", "commit", "tree", "test_platform", "test_filter"})
        if entry["commit"] != head or entry["tree"] != tree:
            raise TaskDeliveryError("Validation manifest inventory commit/tree must match the reviewed HEAD/tree.")
        try:
            path = Path(entry["path"]).resolve(strict=True)
        except (OSError, TypeError) as exc:
            raise TaskDeliveryError("Validation manifest inventory path must identify a regular file.") from exc
        if not stat.S_ISREG(path.lstat().st_mode):
            raise TaskDeliveryError(f"Validation manifest inventory path must identify a regular file: {path}")
        canonical_path = str(path)
        if canonical_path in manifests_by_path:
            raise TaskDeliveryError(f"Duplicate validation manifest path: {canonical_path}")
        digest, size = _file_sha_size(path)
        if digest != entry["sha256"] or size != entry["size_bytes"]:
            raise TaskDeliveryError("A validation manifest changed after draft generation.")
        try:
            manifest = load_validation_manifest(path)
        except ValidationManifestError as exc:
            raise TaskDeliveryError(str(exc)) from exc
        if (manifest.validated_state.commit, manifest.validated_state.tree, manifest.unity.test_platform, manifest.unity.test_filter) != (
                head, tree, entry["test_platform"], entry["test_filter"]):
            raise TaskDeliveryError("A validation manifest no longer matches the reviewed state or inventory.")
        manifests_by_path[canonical_path] = manifest

    expected_unity = _unity_artifacts(list(manifests_by_path.values()))
    reviewed_unity = [item for item in review["artifacts"] if isinstance(item, dict) and item.get("validation_manifest") is not None]
    if reviewed_unity != expected_unity:
        raise TaskDeliveryError("Unity artifact inventory was edited or no longer matches its validation manifests.")
    artifacts = [_verify_external_artifact(item, manifests_by_path) for item in review["artifacts"]]
    artifact_ids = [item["id"] for item in artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise TaskDeliveryError("Artifact IDs must be unique.")

    surfaces = []
    seen_surfaces = set()
    if not isinstance(review["surface_candidates"], list):
        raise TaskDeliveryError("surface_candidates must be a list.")
    for raw in review["surface_candidates"]:
        item = _exact_object(raw, "surface candidate", {"path", "sources", "suggested_role", "selected", "role"})
        if not isinstance(item["selected"], bool):
            raise TaskDeliveryError("Surface selected must be boolean.")
        if item["selected"]:
            try:
                path = safe_repository_path(item["path"], "selected surface path")
                role = _meaningful(item["role"], f"surface {path} role")
                blob = repo.blob(head, path)
                object_type = _run_git(root, "cat-file", "-t", blob).decode().strip()
            except ConformanceRecordError as exc:
                raise TaskDeliveryError(str(exc)) from exc
            if object_type != "blob" or path in seen_surfaces:
                raise TaskDeliveryError("Selected surfaces must be unique committed blobs.")
            seen_surfaces.add(path)
            surfaces.append({"path": path, "role": role})
    if not surfaces:
        raise TaskDeliveryError("At least one conformance surface must be explicitly selected.")

    current_gates = task.get("completion_gates")
    expected = [gate["gate_id"] for gate in current_gates]
    if not isinstance(review["gates"], list) or len(review["gates"]) != len(expected):
        raise TaskDeliveryError("Review must contain exactly every current task completion gate.")
    gates, seen_gates = [], set()
    for index, raw in enumerate(review["gates"]):
        item = _exact_object(raw, "gate", {"gate_id", "reference", "requirement", "evidence", "notes"})
        current = current_gates[index]
        if (item["gate_id"], item["reference"], item["requirement"]) != (current["gate_id"], current["reference"], current["requirement"]):
            raise TaskDeliveryError("Task gates changed or review gate inventory was edited.")
        if item["gate_id"] in seen_gates:
            raise TaskDeliveryError("Duplicate gate ID in review.")
        seen_gates.add(item["gate_id"])
        evidence = item["evidence"]
        if not isinstance(evidence, list) or not evidence or len(evidence) != len(set(evidence)) or any(x not in artifact_ids for x in evidence):
            raise TaskDeliveryError("Every gate needs unique mappings to known evidence IDs.")
        gates.append({"gate_id": item["gate_id"], "evidence": evidence, "notes": _meaningful(item["notes"], f"gate {item['gate_id']} notes")})

    approval = _exact_object(review["human_approval"], "human_approval", {"required", "decision", "approved_by", "notes"})
    if approval["required"] is not True or approval["decision"] != "approved":
        raise TaskDeliveryError("Required human approval must be internally consistent and approved.")
    approved_by = _meaningful(approval["approved_by"], "human_approval.approved_by")
    approval_notes = _meaningful(approval["notes"], "human_approval.notes")
    spec = {"schema_version": "1.0", "task_id": task_meta["id"], "validated_commit": head, "base_commit": base,
            "candidate_commit": candidate, "surfaces": surfaces, "artifacts": artifacts, "gates": gates,
            "human_approval": {"required": True, "decision": "approved", "approved_by": approved_by, "notes": approval_notes}}
    try:
        parse_delivery_spec(spec)
    except RecordDeliveryError as exc:
        raise TaskDeliveryError(f"Generated spec is not compatible with record_delivery.py: {exc}") from exc
    _publish_json(output, spec)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate human-reviewed TaskGraph delivery specs.")
    sub = parser.add_subparsers(dest="command", required=True)
    draft = sub.add_parser("draft")
    draft.add_argument("--task-id", required=True)
    draft.add_argument("--validation-manifest", action="append", required=True)
    draft.add_argument("--crew-result")
    draft.add_argument("--base-commit")
    draft.add_argument("--human-validation", action="append", default=[])
    draft.add_argument("--output", required=True)
    draft.add_argument("--root", default=str(ROOT))
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--review", required=True)
    finalize.add_argument("--output", required=True)
    finalize.add_argument("--root", default=str(ROOT))
    return parser


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "draft":
            output = create_draft(root=Path(args.root), task_id=args.task_id,
                                  manifest_paths=[Path(item) for item in args.validation_manifest], output=Path(args.output),
                                  crew_result=Path(args.crew_result) if args.crew_result else None,
                                  base_commit=args.base_commit,
                                  human_validation=[Path(item) for item in args.human_validation])
            print(f"Delivery review draft: {output}")
            print("Human review is required; no gate mapping or conformance claim was made.")
        else:
            output = finalize_review(root=Path(args.root), review_path=Path(args.review), output=Path(args.output))
            print(f"Delivery spec: {output}")
            print(f"python Pipeline/TaskGraph/record_delivery.py {_powershell_literal(str(output))}")
            print("Nothing was staged or committed; no conformance claim was made.")
        return 0
    except (TaskDeliveryError, OSError) as exc:
        print(f"generate_delivery_spec: FAIL\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
