from __future__ import annotations

"""Aggregate Game Task Agent provider usage through delivery evidence."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from Pipeline.TaskGraph.token_usage_metrics import (
    TOKEN_USAGE_SCHEMA_VERSION,
    TOKEN_USAGE_SCOPE,
    validate_token_usage_metric,
)


_TASK_ID_RE = re.compile(r"NSC-[0-9]{3}")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_TOKEN_FIELDS = ("input_tokens", "output_tokens", "total_tokens")
_CREW_USAGE_FIELDS = {
    "schema_version",
    "status",
    "complete",
    *_TOKEN_FIELDS,
    *(f"reported_{field}" for field in _TOKEN_FIELDS),
    "invocation_count",
    "usage_available_invocation_count",
    "missing_usage_invocation_count",
}


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8-sig"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"invalid JSON numeric constant {value}")
        ),
    )


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, int] = {}
    for field in _TOKEN_FIELDS:
        number = _integer(value.get(field))
        if number is None:
            return None
        result[field] = number
    return result


def _safe_run_id(value: Any, *, source: str) -> str:
    if type(value) is str and _RUN_ID_RE.fullmatch(value):
        return value
    return "invalid-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _bounded_errors(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))[:32]


def _run_record(
    *,
    run_id: str,
    source: str,
    usages: list[dict[str, int] | None],
    errors: list[str],
) -> dict[str, Any]:
    reported = {
        field: sum(usage[field] for usage in usages if usage is not None)
        for field in _TOKEN_FIELDS
    }
    available = sum(usage is not None for usage in usages)
    missing = len(usages) - available
    complete = missing == 0 and not errors
    return {
        "run_id": run_id,
        "source": source,
        "complete": complete,
        **{field: reported[field] if complete else None for field in _TOKEN_FIELDS},
        **{f"reported_{field}": reported[field] for field in _TOKEN_FIELDS},
        "invocation_count": len(usages),
        "usage_available_invocation_count": available,
        "missing_usage_invocation_count": missing,
        "errors": _bounded_errors(errors),
    }


def _aggregate(runs: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    reported = {
        field: sum(run[f"reported_{field}"] for run in runs)
        for field in _TOKEN_FIELDS
    }
    counts = {
        field: sum(run[field] for run in runs)
        for field in (
            "invocation_count",
            "usage_available_invocation_count",
            "missing_usage_invocation_count",
        )
    }
    complete = all(run["complete"] for run in runs) and not errors
    return {
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        **{field: reported[field] if complete else None for field in _TOKEN_FIELDS},
        **{f"reported_{field}": reported[field] for field in _TOKEN_FIELDS},
        "run_count": len(runs),
        **counts,
        "runs": runs,
        "errors": _bounded_errors(errors),
    }


def _supervisor_run(task_id: str, run_dir: Path) -> dict[str, Any]:
    source = f"{task_id}/{run_dir.name}/progress.jsonl"
    errors: list[str] = []
    metadata_path = run_dir / "run.json"
    events_path = run_dir / "progress.jsonl"
    metadata: Mapping[str, Any] = {}
    try:
        raw_metadata = _load_json(metadata_path)
        if not isinstance(raw_metadata, Mapping):
            raise ValueError("run metadata is not an object")
        metadata = raw_metadata
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"run metadata is invalid: {type(exc).__name__}")
    run_id = _safe_run_id(metadata.get("run_id"), source=source)
    if metadata.get("task_id") != task_id:
        errors.append("run metadata task identity does not match")
    if metadata.get("run_id") != run_dir.name:
        errors.append("run metadata identity does not match its directory")

    usages: list[dict[str, int] | None] = []
    seen_turns: set[int] = set()
    expected_sequence = 1
    try:
        lines = events_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append(f"progress journal is unreadable: {type(exc).__name__}")
        lines = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            errors.append(f"progress journal line {line_number} is blank")
            continue
        try:
            event = json.loads(
                line,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"invalid JSON numeric constant {value}")
                ),
            )
        except (json.JSONDecodeError, ValueError):
            errors.append(f"progress journal line {line_number} is invalid JSON")
            continue
        if not isinstance(event, Mapping):
            errors.append(f"progress journal line {line_number} is not an object")
            continue
        sequence = _integer(event.get("sequence"))
        if sequence != expected_sequence:
            errors.append(f"progress journal sequence is invalid at line {line_number}")
        expected_sequence += 1
        if event.get("task_id") != task_id or event.get("run_id") != metadata.get("run_id"):
            errors.append(f"progress journal identity mismatch at line {line_number}")
        if event.get("event") != "supervisor_decision":
            continue
        fields = event.get("fields")
        if not isinstance(fields, Mapping):
            errors.append(f"supervisor decision fields are invalid at line {line_number}")
            usages.append(None)
            continue
        turn = _integer(fields.get("turn"))
        if turn is None or turn < 1:
            errors.append(f"supervisor decision turn is invalid at line {line_number}")
            usages.append(None)
            continue
        if turn in seen_turns:
            errors.append(f"duplicate supervisor decision turn {turn}")
            continue
        seen_turns.add(turn)
        usages.append(_usage(fields.get("provider_usage")))
    return _run_record(
        run_id=run_id,
        source=source,
        usages=usages,
        errors=errors,
    )


def aggregate_supervisor_usage(task_id: str, output_root: Path | str) -> dict[str, Any]:
    root = Path(output_root).expanduser().resolve()
    task_root = root / task_id
    errors: list[str] = []
    runs: list[dict[str, Any]] = []
    candidates = (
        sorted(
            {
                path.parent
                for pattern in ("*/run.json", "*/progress.jsonl")
                for path in task_root.glob(pattern)
            },
            key=lambda path: path.name.casefold(),
        )
        if task_root.is_dir()
        else []
    )
    if not candidates:
        errors.append("no task-agent progress journals were found")
    seen_run_ids: set[str] = set()
    for run_dir in candidates:
        run = _supervisor_run(task_id, run_dir)
        if run["run_id"] in seen_run_ids:
            errors.append(f"duplicate supervisor run identity: {run['run_id']}")
            continue
        seen_run_ids.add(run["run_id"])
        runs.append(run)
    return _aggregate(runs, errors)


def _validate_crew_usage(value: Any, expected: Mapping[str, Any]) -> str | None:
    if not isinstance(value, Mapping) or set(value) != _CREW_USAGE_FIELDS:
        return "crew_result token_usage fields are invalid"
    if value.get("schema_version") != TOKEN_USAGE_SCHEMA_VERSION:
        return "crew_result token_usage schema_version is invalid"
    for field in _CREW_USAGE_FIELDS - {"schema_version", "status", "complete"}:
        if field in _TOKEN_FIELDS:
            actual = value.get(field)
            if actual is not None and _integer(actual) is None:
                return f"crew_result token_usage {field} is invalid"
        elif _integer(value.get(field)) is None:
            return f"crew_result token_usage {field} is invalid"
    expected_values = dict(expected)
    expected_values["status"] = "complete" if expected.get("complete") else "incomplete"
    for field in (
        "status",
        "complete",
        *_TOKEN_FIELDS,
        *(f"reported_{name}" for name in _TOKEN_FIELDS),
        "invocation_count",
        "usage_available_invocation_count",
        "missing_usage_invocation_count",
    ):
        if value.get(field) != expected_values.get(field):
            return f"crew_result token_usage {field} does not match role results"
    return None


def _crew_run(task_id: str, run_dir: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    source = f"Pipeline/ExecutionCrew/outputs/{run_dir.name}/crew_result.json"
    errors: list[str] = []
    run_id = _safe_run_id(result.get("run_id"), source=source)
    if result.get("run_id") != run_dir.name:
        errors.append("crew run identity does not match its directory")
    raw_role_paths = result.get("role_results")
    if not isinstance(raw_role_paths, list):
        raw_role_paths = []
        errors.append("crew_result role_results is invalid")
    usages: list[dict[str, int] | None] = []
    seen_paths: set[str] = set()
    seen_invocations: set[tuple[str, int]] = set()
    for index, raw_path in enumerate(raw_role_paths):
        if type(raw_path) is not str or not raw_path.startswith("role_results/") or ".." in Path(raw_path).parts:
            errors.append(f"role result path {index} is invalid")
            usages.append(None)
            continue
        if raw_path in seen_paths:
            errors.append(f"duplicate role result path: {raw_path}")
            continue
        seen_paths.add(raw_path)
        try:
            role_result = _load_json(run_dir / raw_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"role result {raw_path} is invalid: {type(exc).__name__}")
            usages.append(None)
            continue
        if not isinstance(role_result, Mapping):
            errors.append(f"role result {raw_path} is not an object")
            usages.append(None)
            continue
        role = role_result.get("role")
        attempt = _integer(role_result.get("attempt"))
        if type(role) is not str or not role or attempt is None or attempt < 1:
            errors.append(f"role result {raw_path} has an invalid invocation identity")
            usages.append(None)
            continue
        identity = (role, attempt)
        if identity in seen_invocations:
            errors.append(f"duplicate role invocation identity: {role}/{attempt}")
            continue
        seen_invocations.add(identity)
        usages.append(_usage(role_result.get("usage")))
    run = _run_record(run_id=run_id, source=source, usages=usages, errors=errors)
    aggregate_error = _validate_crew_usage(result.get("token_usage"), run)
    if aggregate_error is not None:
        run["errors"].append(aggregate_error)
        run["errors"] = _bounded_errors(run["errors"])
        run["complete"] = False
        for field in _TOKEN_FIELDS:
            run[field] = None
    return run


def aggregate_execution_crew_usage(task_id: str, checkout_root: Path | str) -> dict[str, Any]:
    output_root = Path(checkout_root).resolve() / "Pipeline" / "ExecutionCrew" / "outputs"
    errors: list[str] = []
    runs: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    for result_path in sorted(output_root.glob("*/crew_result.json"), key=lambda path: path.parent.name.casefold()):
        try:
            result = _load_json(result_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"crew result {result_path.parent.name} is invalid: {type(exc).__name__}")
            continue
        if not isinstance(result, Mapping):
            errors.append(f"crew result {result_path.parent.name} is not an object")
            continue
        if result.get("task_id") != task_id:
            if type(result.get("task_id")) is str and _TASK_ID_RE.fullmatch(result["task_id"]):
                continue
            errors.append(f"crew result {result_path.parent.name} has an invalid task identity")
            continue
        run = _crew_run(task_id, result_path.parent, result)
        if run["run_id"] in seen_run_ids:
            errors.append(f"duplicate ExecutionCrew run identity: {run['run_id']}")
            continue
        seen_run_ids.add(run["run_id"])
        runs.append(run)
    if not runs:
        errors.append("no ExecutionCrew results were found for the task")
    return _aggregate(runs, errors)


def build_task_token_usage(
    *,
    task_id: str,
    supervisor_output_root: Path | str,
    checkout_root: Path | str,
) -> dict[str, Any]:
    if type(task_id) is not str or not _TASK_ID_RE.fullmatch(task_id):
        raise ValueError("task_id must match NSC-###")
    supervisor = aggregate_supervisor_usage(task_id, supervisor_output_root)
    execution_crew = aggregate_execution_crew_usage(task_id, checkout_root)
    reported = {
        field: supervisor[f"reported_{field}"] + execution_crew[f"reported_{field}"]
        for field in _TOKEN_FIELDS
    }
    complete = supervisor["complete"] and execution_crew["complete"]
    metric = {
        "schema_version": TOKEN_USAGE_SCHEMA_VERSION,
        "task_id": task_id,
        "scope": TOKEN_USAGE_SCOPE,
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        **{field: reported[field] if complete else None for field in _TOKEN_FIELDS},
        **{f"reported_{field}": reported[field] for field in _TOKEN_FIELDS},
        "breakdown": {
            "supervisor": supervisor,
            "execution_crew": execution_crew,
        },
    }
    return validate_token_usage_metric(metric, expected_task_id=task_id)


def write_task_token_usage(path: Path | str, metric: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser().resolve()
    validated = validate_token_usage_metric(metric)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(validated, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination
