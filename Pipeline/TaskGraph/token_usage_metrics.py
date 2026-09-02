from __future__ import annotations

"""Strict, non-authoritative TaskGraph token-usage sidecar handling."""

import json
import re
from typing import Any, Mapping


TOKEN_USAGE_SCHEMA_VERSION = "1.0"
TOKEN_USAGE_SCOPE = "through_delivery_evidence"
TOKEN_USAGE_STATUSES = frozenset({"complete", "incomplete"})
TASK_ID_RE = re.compile(r"NSC-[0-9]{3}")
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")

_TOKEN_FIELDS = ("input_tokens", "output_tokens", "total_tokens")
_COUNT_FIELDS = (
    "run_count",
    "invocation_count",
    "usage_available_invocation_count",
    "missing_usage_invocation_count",
)
_AGGREGATE_FIELDS = {
    "status",
    "complete",
    *_TOKEN_FIELDS,
    *(f"reported_{field}" for field in _TOKEN_FIELDS),
    *_COUNT_FIELDS,
    "runs",
    "errors",
}
_RUN_FIELDS = {
    "run_id",
    "source",
    "complete",
    *_TOKEN_FIELDS,
    *(f"reported_{field}" for field in _TOKEN_FIELDS),
    "invocation_count",
    "usage_available_invocation_count",
    "missing_usage_invocation_count",
    "errors",
}
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "task_id",
    "scope",
    "status",
    "complete",
    *_TOKEN_FIELDS,
    *(f"reported_{field}" for field in _TOKEN_FIELDS),
    "breakdown",
}


class TokenUsageMetricError(ValueError):
    """Raised when telemetry cannot be trusted as a token-usage metric."""


def _object(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TokenUsageMetricError(f"{field} must be one object")
    return dict(value)


def _exact_fields(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    if set(value) != expected:
        raise TokenUsageMetricError(
            f"{field} fields differ (missing={sorted(expected-set(value))}, "
            f"extra={sorted(set(value)-expected)})"
        )


def _integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TokenUsageMetricError(f"{field} must be a non-negative integer")
    return value


def _nullable_integer(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    return _integer(value, field=field)


def _validate_status_and_tokens(value: Mapping[str, Any], *, field: str) -> None:
    status = value.get("status")
    complete = value.get("complete")
    if status not in TOKEN_USAGE_STATUSES or type(complete) is not bool:
        raise TokenUsageMetricError(f"{field} has an invalid completeness status")
    if complete != (status == "complete"):
        raise TokenUsageMetricError(f"{field} status and complete disagree")
    for name in _TOKEN_FIELDS:
        token_value = _nullable_integer(value.get(name), field=f"{field}.{name}")
        if complete and token_value is None:
            raise TokenUsageMetricError(f"{field}.{name} is required when complete")
        if not complete and token_value is not None:
            raise TokenUsageMetricError(f"{field}.{name} must be null when incomplete")
        _integer(value.get(f"reported_{name}"), field=f"{field}.reported_{name}")


def _validate_run(value: Any, *, field: str) -> dict[str, Any]:
    run = _object(value, field=field)
    _exact_fields(run, _RUN_FIELDS, field=field)
    run_id = run.get("run_id")
    source = run.get("source")
    if type(run_id) is not str or not RUN_ID_RE.fullmatch(run_id):
        raise TokenUsageMetricError(f"{field}.run_id is invalid")
    if type(source) is not str or not source.strip():
        raise TokenUsageMetricError(f"{field}.source must be non-empty")
    _validate_status_and_tokens(
        {**run, "status": "complete" if run.get("complete") is True else "incomplete"},
        field=field,
    )
    invocation_count = _integer(run.get("invocation_count"), field=f"{field}.invocation_count")
    available = _integer(
        run.get("usage_available_invocation_count"),
        field=f"{field}.usage_available_invocation_count",
    )
    missing = _integer(
        run.get("missing_usage_invocation_count"),
        field=f"{field}.missing_usage_invocation_count",
    )
    if invocation_count != available + missing:
        raise TokenUsageMetricError(f"{field} invocation counts are inconsistent")
    errors = run.get("errors")
    if not isinstance(errors, list) or any(type(item) is not str or not item for item in errors):
        raise TokenUsageMetricError(f"{field}.errors must contain non-empty strings")
    if run["complete"] != (missing == 0 and not errors):
        raise TokenUsageMetricError(f"{field} completeness and missing usage disagree")
    return run


def _validate_aggregate(value: Any, *, field: str) -> dict[str, Any]:
    aggregate = _object(value, field=field)
    _exact_fields(aggregate, _AGGREGATE_FIELDS, field=field)
    _validate_status_and_tokens(aggregate, field=field)
    counts = {
        name: _integer(aggregate.get(name), field=f"{field}.{name}")
        for name in _COUNT_FIELDS
    }
    if counts["invocation_count"] != (
        counts["usage_available_invocation_count"]
        + counts["missing_usage_invocation_count"]
    ):
        raise TokenUsageMetricError(f"{field} invocation counts are inconsistent")
    raw_runs = aggregate.get("runs")
    if not isinstance(raw_runs, list):
        raise TokenUsageMetricError(f"{field}.runs must be a list")
    runs = [_validate_run(item, field=f"{field}.runs[{index}]") for index, item in enumerate(raw_runs)]
    run_ids = [run["run_id"] for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise TokenUsageMetricError(f"{field}.runs contains duplicate run identities")
    if counts["run_count"] != len(runs):
        raise TokenUsageMetricError(f"{field}.run_count does not match runs")
    for count_name in (
        "invocation_count",
        "usage_available_invocation_count",
        "missing_usage_invocation_count",
    ):
        if counts[count_name] != sum(run[count_name] for run in runs):
            raise TokenUsageMetricError(f"{field}.{count_name} does not match runs")
    errors = aggregate.get("errors")
    if not isinstance(errors, list) or any(type(item) is not str or not item for item in errors):
        raise TokenUsageMetricError(f"{field}.errors must contain non-empty strings")
    if aggregate["complete"] != (
        all(run["complete"] for run in runs)
        and counts["missing_usage_invocation_count"] == 0
        and not errors
    ):
        raise TokenUsageMetricError(f"{field} completeness does not match its provenance")
    for name in _TOKEN_FIELDS:
        reported = sum(run[f"reported_{name}"] for run in runs)
        if aggregate[f"reported_{name}"] != reported:
            raise TokenUsageMetricError(f"{field}.reported_{name} does not match runs")
        if aggregate["complete"] and aggregate[name] != reported:
            raise TokenUsageMetricError(f"{field}.{name} does not match complete runs")
    return aggregate


def validate_token_usage_metric(value: Any, *, expected_task_id: str | None = None) -> dict[str, Any]:
    metric = _object(value, field="token usage metric")
    _exact_fields(metric, _TOP_LEVEL_FIELDS, field="token usage metric")
    if metric.get("schema_version") != TOKEN_USAGE_SCHEMA_VERSION:
        raise TokenUsageMetricError("unsupported token usage schema_version")
    task_id = metric.get("task_id")
    if type(task_id) is not str or not TASK_ID_RE.fullmatch(task_id):
        raise TokenUsageMetricError("token usage task_id is invalid")
    if expected_task_id is not None and task_id != expected_task_id:
        raise TokenUsageMetricError(
            f"token usage task_id {task_id!r} does not match {expected_task_id!r}"
        )
    if metric.get("scope") != TOKEN_USAGE_SCOPE:
        raise TokenUsageMetricError("token usage scope is invalid")
    _validate_status_and_tokens(metric, field="token usage metric")
    breakdown = _object(metric.get("breakdown"), field="token usage metric.breakdown")
    _exact_fields(breakdown, {"supervisor", "execution_crew"}, field="token usage metric.breakdown")
    supervisor = _validate_aggregate(breakdown["supervisor"], field="breakdown.supervisor")
    execution_crew = _validate_aggregate(
        breakdown["execution_crew"],
        field="breakdown.execution_crew",
    )
    expected_complete = supervisor["complete"] and execution_crew["complete"]
    if metric["complete"] != expected_complete:
        raise TokenUsageMetricError("combined completeness does not match source breakdown")
    for name in _TOKEN_FIELDS:
        reported = supervisor[f"reported_{name}"] + execution_crew[f"reported_{name}"]
        if metric[f"reported_{name}"] != reported:
            raise TokenUsageMetricError(f"reported_{name} does not match source breakdown")
        if metric["complete"] and metric[name] != reported:
            raise TokenUsageMetricError(f"{name} does not match complete source breakdown")
    return metric


def load_token_usage_bytes(data: bytes, *, expected_task_id: str | None = None) -> dict[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8-sig"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                TokenUsageMetricError(f"invalid JSON numeric constant {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenUsageMetricError(f"token usage is not valid UTF-8 JSON: {exc}") from exc
    return validate_token_usage_metric(value, expected_task_id=expected_task_id)


def committed_token_usage_fields(repo: Any, commit: str, task_id: str) -> dict[str, Any]:
    """Read optional committed telemetry without influencing conformance authority."""

    path = f"Pipeline/TaskGraph/evidence/{task_id}/metrics/token-usage.json"
    try:
        if not repo.exists(commit, path):
            raise FileNotFoundError(path)
        metric = load_token_usage_bytes(repo.read(commit, path), expected_task_id=task_id)
    except FileNotFoundError:
        return {
            "total_tokens_used": None,
            "token_usage_complete": None,
            "token_usage_status": "unavailable",
            "token_usage_scope": None,
        }
    except Exception:  # Telemetry is explicitly non-authoritative.
        return {
            "total_tokens_used": None,
            "token_usage_complete": False,
            "token_usage_status": "invalid",
            "token_usage_scope": None,
        }
    return {
        "total_tokens_used": metric["total_tokens"],
        "token_usage_complete": metric["complete"],
        "token_usage_status": metric["status"],
        "token_usage_scope": metric["scope"],
    }
