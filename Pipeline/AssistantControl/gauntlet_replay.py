"""Create the fixed local-only Gauntlet replay family on an empty test branch."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from Pipeline.ExecutionCrew.run_crew import unity_meta_bytes, unity_meta_guid
from Pipeline.TaskReviewAgent.decomposition_policy_audit import (
    audit_decomposition_policy, parent_semantic_hash, read_committed_tasks,
)

REPLAY_MAP = {
    "NSC-898": "NSC-998",
    "NSC-1001": "NSC-1101",
    "NSC-1003": "NSC-1103",
    "NSC-1004": "NSC-1104",
    "NSC-1005": "NSC-1105",
    "NSC-1007": "NSC-1107",
    "NSC-1008": "NSC-1108",
    "NSC-1010": "NSC-1110",
}
TEMPLATE_REVISIONS = {
    "NSC-898": "612b2cb", "NSC-1007": "8290d3",
    "NSC-1008": "8290d3", "NSC-1010": "40aac37",
}
DECOMPOSITION_ROOTS = {"NSC-998", "NSC-1107", "NSC-1108"}
TEST_DIRECTORY = Path("Assets/NoSafeCircle/DoorPrototype/Tests/Editor")
TEST_NAMESPACE = "NoSafeCircle.DoorPrototype.Tests.Editor"
POLICY_PATH = Path("Pipeline/TaskReviewAgent/authoritative_validation_policy.json")
MAP_PATH = Path("Pipeline/TaskGraph/WORK_ID_MAP.json")


class GauntletReplayError(ValueError):
    pass


def _git(source: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(source), *args], capture_output=True)
    if result.returncode:
        raise GauntletReplayError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _meta_guid(source_path: str) -> str:
    return unity_meta_guid(source_path)


def _unit_suffixes(task_id: str) -> tuple[str, ...]:
    return ("Alpha", "Beta") if task_id in DECOMPOSITION_ROOTS else ("",)


def _test_class(task_id: str, suffix: str = "") -> str:
    number = int(task_id.split("-")[1])
    return f"GauntletReplay{number}{suffix}Tests"


def _test_path(task_id: str, suffix: str = "") -> Path:
    return TEST_DIRECTORY / f"{_test_class(task_id, suffix)}.cs"


def _test_filter(task_id: str, suffix: str = "") -> str:
    number = int(task_id.split("-")[1])
    return (f"{TEST_NAMESPACE}.{_test_class(task_id, suffix)}."
            f"Gauntlet{number}{suffix}HasExpectedValue")


def _test_resources(task_id: str, suffix: str = "") -> tuple[str, str]:
    path = _test_path(task_id, suffix).as_posix()
    return f"repo-file:{path}", f"repo-file:{path}.meta"


def _replace(value: Any, old_number: int, new_number: int) -> Any:
    if type(value) is int:
        return new_number if value == old_number else value
    if isinstance(value, str):
        for old_id, new_id in REPLAY_MAP.items():
            value = re.sub(rf"(?<![A-Za-z0-9-]){re.escape(old_id)}(?!\d)", new_id, value)
        value = value.replace(f"NSC-{old_number}", f"NSC-{new_number}")
        value = value.replace(f"Gauntlet{old_number}", f"Gauntlet{new_number}")
        value = value.replace(f"gauntlet-{old_number}", f"gauntlet-{new_number}")
        return re.sub(rf"(?<!\d){old_number}(?!\d)", str(new_number), value)
    if isinstance(value, list):
        return [_replace(item, old_number, new_number) for item in value]
    if isinstance(value, dict):
        return {_replace(key, old_number, new_number): _replace(item, old_number, new_number)
                for key, item in value.items()}
    return value


def _remap_contract(contract: dict[str, Any], old_id: str, new_id: str) -> dict[str, Any]:
    old_number, new_number = int(old_id.split("-")[1]), int(new_id.split("-")[1])
    result = _replace(copy.deepcopy(contract), old_number, new_number)
    result["id"] = new_id
    result["contract_revision"] = 1
    provenance = result.setdefault("provenance", {})
    provenance["origin"] = "assistant_control_local_gauntlet_replay"
    provenance["gauntlet_id"] = "assistant-control-local-replay-v1"
    meta_paths = [path for path in provenance.get("expected_paths", []) if path.endswith(".meta")]
    replacements = [_meta_guid(path[:-len(".meta")]) for path in meta_paths]
    replacement_index = 0
    for criterion in result.get("acceptance_criteria", []):
        requirement = criterion.get("requirement")
        if isinstance(requirement, str) and ".meta" in requirement and replacements:
            count = len(re.findall(r"\b[0-9a-f]{32}\b", requirement))
            for _ in range(count):
                guid = replacements[min(replacement_index, len(replacements) - 1)]
                requirement = re.sub(r"\b[0-9a-f]{32}\b", guid, requirement, count=1)
                replacement_index += 1
            criterion["requirement"] = requirement
    resources = result.get("exclusive_resources")
    if not isinstance(resources, list) or any(type(item) is not str for item in resources):
        raise GauntletReplayError(f"Template {old_id} has invalid exclusive resources")
    for suffix in _unit_suffixes(new_id):
        for resource in _test_resources(new_id, suffix):
            if resource in resources:
                raise GauntletReplayError(f"Template {old_id} already owns replay test resource {resource}")
            resources.append(resource)
    expected_filters = {_test_filter(new_id, suffix) for suffix in _unit_suffixes(new_id)}
    replaced_filters: set[str] = set()
    for gate in result.get("completion_gates", []):
        requirement = gate.get("requirement")
        if not isinstance(requirement, str):
            continue
        for suffix in _unit_suffixes(new_id):
            method = f"Gauntlet{new_number}{suffix}HasExpectedValue"
            if method not in requirement:
                continue
            match = re.search(r"\bfilter\s+([A-Za-z_][A-Za-z0-9_.+`]*)", requirement)
            if match is None:
                raise GauntletReplayError(f"Template {old_id} completion gate has no exact test filter")
            test_filter = _test_filter(new_id, suffix)
            gate["requirement"] = (requirement[:match.start(1)] + test_filter
                                   + requirement[match.end(1):])
            replaced_filters.add(test_filter)
            break
    if replaced_filters != expected_filters:
        raise GauntletReplayError(f"Template {old_id} does not bind every replay test unit")
    return result


def _load_template(source: Path, task_id: str) -> dict[str, Any]:
    revision = TEMPLATE_REVISIONS.get(task_id, "HEAD")
    raw = _git(source, "show", f"{revision}:Tasks/{task_id}.yaml")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("id") != task_id:
        raise GauntletReplayError(f"Template {task_id} is invalid at {revision}")
    return value


def _test_bytes(task_id: str, suffix: str = "") -> bytes:
    number = int(task_id.split("-")[1])
    name = f"Gauntlet{number}{suffix}"
    class_name = _test_class(task_id, suffix)
    text = f'''using System;
using System.Reflection;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{{
    public class {class_name}
    {{
        private static void AssertValue(string typeName, int expected)
        {{
            Type type = typeof(DoorInteractable).Assembly.GetType("NoSafeCircle.DoorPrototype." + typeName);
            Assert.That(type, Is.Not.Null, typeName);
            FieldInfo field = type.GetField("Value", BindingFlags.Public | BindingFlags.Static);
            Assert.That(field, Is.Not.Null, typeName);
            Assert.That(field.IsLiteral, Is.True, typeName);
            Assert.That((int)field.GetRawConstantValue(), Is.EqualTo(expected), typeName);
        }}

        [Test]
        public void {name}HasExpectedValue()
        {{
            AssertValue("{name}", {number});
        }}
    }}
}}
'''
    return text.replace("\n", "\r\n").encode()


def _policy_entry(task_id: str, contract_bytes: bytes) -> dict[str, Any]:
    return {"task_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": _test_filter(task_id)},
            "authority": "committed_private_synthetic_gauntlet_validation_policy"}


def _child_template(task: dict[str, Any]) -> dict[str, Any]:
    number = int(task["id"].split("-")[1])
    resources = list(task["exclusive_resources"])
    variants = []
    for suffix in ("Alpha", "Beta"):
        owned = [item for item in resources if f"Gauntlet{number}{suffix}.cs" in item]
        owned.extend(_test_resources(task["id"], suffix))
        variants.append({"required_exclusive_resources": owned,
                         "required_test_platforms": ["EditMode"],
                         "test_filters": {"EditMode": _test_filter(task["id"], suffix)}})
    return {"parent_task_contract_sha256": parent_semantic_hash(task),
            "validation_variants": variants,
            "authority": "committed_private_synthetic_gauntlet_decomposition_child_policy"}


def _preflight(source: Path, branch: str) -> Path:
    source = Path(_git(source, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if branch != _git(source, "branch", "--show-current").decode().strip() or not branch.startswith("gauntlet-replay/"):
        raise GauntletReplayError("Use the explicitly named gauntlet-replay/* local test branch")
    if _git(source, "remote").strip():
        raise GauntletReplayError("Replay generation requires a local test branch with no Git remote")
    if _git(source, "status", "--porcelain=v1", "--untracked-files=all"):
        raise GauntletReplayError("Replay generation requires a clean working tree")
    return source


def generate(source: Path, *, branch: str) -> dict[str, Any]:
    source = _preflight(source, branch)
    contracts = {_new: _remap_contract(_load_template(source, old), old, _new)
                 for old, _new in REPLAY_MAP.items()}
    task_bytes = {task_id: _json_bytes(contract) for task_id, contract in contracts.items()}
    policy = json.loads((source / POLICY_PATH).read_bytes())
    work_map = json.loads((source / MAP_PATH).read_bytes())
    test_files: dict[Path, bytes] = {}
    for task_id in contracts:
        for suffix in _unit_suffixes(task_id):
            test_path = _test_path(task_id, suffix)
            test_files[test_path] = _test_bytes(task_id, suffix)
            test_files[Path(test_path.as_posix() + ".meta")] = unity_meta_bytes(test_path.as_posix())
    targets = [*(source / "Tasks" / f"{task_id}.yaml" for task_id in contracts),
               *(source / path for path in test_files)]
    expected_outputs = [source / path for task in contracts.values()
                        for path in (task.get("provenance") or {}).get("expected_paths", [])]
    if "NSC-042" in contracts or any(path.exists() for path in targets + expected_outputs):
        raise GauntletReplayError("Replay collision or existing output file; nothing generated")
    ids = work_map.get("id_map") or {}
    if any(task["reconciliation_key"] in ids or task_id in ids.values()
           for task_id, task in contracts.items()):
        raise GauntletReplayError("Replay WORK_ID_MAP identity already exists")
    policy_tasks = policy.setdefault("tasks", {})
    policy_templates = policy.setdefault("decomposition_child_templates", {})
    if any(task_id in policy_tasks or task_id in policy_templates for task_id in contracts):
        raise GauntletReplayError("Replay validation policy identity already exists")
    for task_id, task in contracts.items():
        ids[task["reconciliation_key"]] = task_id
        if task_id in DECOMPOSITION_ROOTS:
            policy_templates[task_id] = _child_template(task)
        else:
            policy_tasks[task_id] = _policy_entry(task_id, task_bytes[task_id])
    work_map["id_map"] = dict(sorted(ids.items()))
    files = {source / "Tasks" / f"{task_id}.yaml": data for task_id, data in task_bytes.items()}
    files[source / MAP_PATH] = _json_bytes(work_map)
    files[source / POLICY_PATH] = _json_bytes(policy)
    files.update({source / path: data for path, data in test_files.items()})
    audited_tasks = read_committed_tasks(source)
    audited_tasks.update(contracts)
    audit_decomposition_policy(source, document=policy, tasks=audited_tasks)
    originals = {path: path.read_bytes() if path.exists() else None for path in files}
    try:
        for path, data in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)
        result = subprocess.run([sys.executable, str(source / "Pipeline/TaskGraph/taskcontrol.py"), "validate"],
                                cwd=source, capture_output=True, text=True)
        if result.returncode:
            raise GauntletReplayError("taskcontrol validate failed: " + (result.stderr or result.stdout).strip())
        diff_check = subprocess.run(["git", "-C", str(source), "diff", "--check"],
                                    capture_output=True, text=True)
        if diff_check.returncode:
            raise GauntletReplayError("git diff --check failed: " + (diff_check.stderr or diff_check.stdout).strip())
    except Exception:
        for path, data in originals.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)
        raise
    return {"status": "generated", "branch": branch, "task_ids": list(contracts),
            "files_written": [str(path.relative_to(source)).replace("\\", "/") for path in files],
            "validation": result.stdout.strip()}


__all__ = ["GauntletReplayError", "REPLAY_MAP", "generate"]
