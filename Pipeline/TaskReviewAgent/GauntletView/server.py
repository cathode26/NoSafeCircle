#!/usr/bin/env python3
"""Read-only live view of an NSC gauntlet task graph.

Serves a Cytoscape.js page backed by local on-disk sources:

  Tasks/NSC-*.yaml                          structure (parent, depends_on, wave)
  .task-review-agent/autonomous-runs/.../   scheduler scope + events.jsonl
  .task-review-agent/outputs/<TASK>/<run>/  per-worker progress.jsonl
                                                + durable run_result.json
                                                + optional ci_snapshot.json
  Pipeline/TaskGraph/evidence/<TASK>/       committed conformance + token totals

Nothing here writes to the repository or the run state. It reuses TaskGraph's
local committed-HEAD evaluator and otherwise uses the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from pipeline_activity import build_pipeline_activity
# Canonical bounded task-ID rule; an unbounded \d+ is rejected by
# tests/task_id_width_smoke_test.py.
TASK_FILE_RE = re.compile(r"^NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})\.yaml$")
GITHUB_REPOSITORY_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})"
)
ISSUE_NUMBER_FIELDS = ("issue_number", "result_issue_number")
ISSUE_URL_FIELDS = ("issue_url", "result_issue_url")
PULL_REQUEST_NUMBER_FIELDS = ("pull_request_number", "result_pull_request_number")
PULL_REQUEST_URL_FIELDS = ("pull_request_url", "result_pull_request_url")
TAIL_BYTES = 96_000  # enough to hold the tail of a long worker run
CI_SNAPSHOT_STALE_SECONDS = 60
MIN_ESTIMATE_SAMPLES = 3
CI_ACTION = "inspect_or_merge_pull_request"
INTEGRATION_PHASES = frozenset({"delivery_evidence", "merge_closeout"})
DECOMPOSITION_EXECUTION_SCOPE = "needs_execution_decomposition"
DECOMPOSITION_READY_STATE = "concrete"

# Presentation stage names stay centralized here; the browser consumes normalized
# node_lines and never reinterprets workflow phases.
PHASE_STAGES = {
    "waiting": (1, "WAITING"),
    "admission": (1, "WAITING"),
    "preparing_checkout": (2, "PREPARING CHECKOUT"),
    "checkout_preparation": (2, "PREPARING CHECKOUT"),
    "implementation": (3, "IMPLEMENTING"),
    "repair": (3, "REPAIRING"),
    "decomposition": (3, "DECOMPOSING"),
    "decomposition_apply_authorization": (3, "AWAITING VERIFICATION"),
    "decomposition_apply": (3, "DECOMPOSING"),
    "unity_runtime_validation": (4, "VALIDATING"),
    "validation": (4, "VALIDATING"),
    "delivery_evidence": (5, "PRODUCING EVIDENCE"),
    "merge_closeout": (6, "IN CI"),
}
ACTION_LABELS = {
    "run_execution_crew": "Execution crew",
    "search_repository": "Inspecting repository",
    "run_unity_tests": "Unity tests",
    "run_validation": "Validation",
    "repair_candidate": "Repairing candidate",
    "produce_delivery_evidence": "Delivery evidence",
    "inspect_or_merge_pull_request": "Monitoring pull-request checks",
    "run_decomposition": "Decomposition",
}

# Worker terminal statuses seen in progress.jsonl -> node state.
TERMINAL_STATE = {
    "complete": "complete",
    "checks_pending": "checks_pending",
    "human_action_required": "human_action",
    "human_revalidation_required": "human_action",
    "blocked": "blocked",
    "failed": "failed",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validated_repository_slug(value: Any) -> str | None:
    """Return one safe GitHub owner/repository slug, never a URL or path."""
    if not isinstance(value, str) or GITHUB_REPOSITORY_RE.fullmatch(value) is None:
        return None
    return value


def validated_issue_number(value: Any) -> int | None:
    """Return a positive integer Issue number, rejecting bool and coercion."""
    return value if type(value) is int and value > 0 else None


def is_available_decomposition(contract: dict[str, Any]) -> bool:
    """Recognize the exact TaskGraph contract shape eligible for decomposition."""

    return (
        contract.get("contract_disposition", contract.get("disposition")) == "active"
        and contract.get("kind") == "implementation"
        and contract.get("execution_scope") == DECOMPOSITION_EXECUTION_SCOPE
        and contract.get("decomposition_state") == DECOMPOSITION_READY_STATE
    )


def issue_number_from_url(value: Any, repository: str | None) -> int | None:
    """Extract an Issue number only from this manifest repository's exact URL."""
    repository = validated_repository_slug(repository)
    if repository is None or not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
    ):
        return None
    components = parsed.path.split("/")
    if len(components) != 5 or components[0] or components[3] != "issues":
        return None
    supplied_repository = validated_repository_slug(
        f"{components[1]}/{components[2]}"
    )
    if supplied_repository is None or supplied_repository.casefold() != repository.casefold():
        return None
    raw_number = components[4]
    if re.fullmatch(r"[1-9][0-9]*", raw_number) is None:
        return None
    return validated_issue_number(int(raw_number))


def github_issue_url(repository: str | None, issue_number: Any) -> str | None:
    """Construct the only URL form the API may expose as Issue navigation."""
    repository = validated_repository_slug(repository)
    issue_number = validated_issue_number(issue_number)
    if repository is None or issue_number is None:
        return None
    return f"https://github.com/{repository}/issues/{issue_number}"


def positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def parse_timestamp(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def newer(left: Any, right: Any) -> bool:
    """Whether left is durably newer; malformed/missing timestamps never win."""
    left_value = parse_timestamp(left)
    right_value = parse_timestamp(right)
    return left_value is not None and (right_value is None or left_value > right_value)


def pull_request_number_from_url(value: Any, repository: str | None) -> int | None:
    repository = validated_repository_slug(repository)
    if repository is None or not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    components = parsed.path.split("/")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or len(components) != 5
        or components[0]
        or components[3] != "pull"
    ):
        return None
    supplied = validated_repository_slug(f"{components[1]}/{components[2]}")
    if supplied is None or supplied.casefold() != repository.casefold():
        return None
    if re.fullmatch(r"[1-9][0-9]*", components[4]) is None:
        return None
    return validated_issue_number(int(components[4]))


def github_pull_request_url(repository: str | None, number: Any) -> str | None:
    repository = validated_repository_slug(repository)
    number = validated_issue_number(number)
    if repository is None or number is None:
        return None
    return f"https://github.com/{repository}/pull/{number}"


def duration_text(seconds: Any) -> str:
    value = positive_number(seconds)
    if value is None:
        return "unavailable"
    seconds_int = round(value)
    hours, remainder = divmod(seconds_int, 3600)
    minutes, seconds_int = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m" if seconds_int == 0 else f"{minutes}m {seconds_int}s"
    return f"{seconds_int}s"


def nested_objects(fields: dict[str, Any]) -> list[dict[str, Any]]:
    values = [fields]
    for name in ("result", "result_summary", "status", "summary"):
        candidate = fields.get(name)
        if isinstance(candidate, dict):
            values.append(candidate)
    return values


def projected_state(status: Any) -> str | None:
    if not isinstance(status, str):
        return None
    normalized = status.casefold()
    if normalized in ("complete", "completed", "merged"):
        return "complete"
    return TERMINAL_STATE.get(normalized)


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------


def discover_roots(tasks: str | None, state: str | None) -> tuple[Path, Path]:
    """Find a checkout with Tasks/ and a directory holding .task-review-agent."""
    # Public defaults bind to this checkout; sibling private runs are never
    # selected implicitly. Operators select an external state root explicitly.
    checkout = HERE.parents[2]
    return (
        Path(tasks).resolve() if tasks else checkout / "Tasks",
        Path(state).resolve() if state else checkout,
    )


def newest_autonomous_run(state_root: Path) -> Path | None:
    root = state_root / ".task-review-agent" / "autonomous-runs"
    runs = list(root.glob("*/*/manifest.json"))
    if not runs:
        return None
    return max(runs, key=lambda p: p.stat().st_mtime).parent


# --------------------------------------------------------------------------
# cached readers
# --------------------------------------------------------------------------


class FileCache:
    """Re-parse a file only when its mtime or size changes."""

    def __init__(self) -> None:
        self._entries: dict[tuple[Path, Any], tuple[float, int, Any]] = {}

    def get(self, path: Path, parse):
        key = (path, parse)
        try:
            stat = path.stat()
        except OSError:
            self._entries.pop(key, None)
            return None
        hit = self._entries.get(key)
        if hit is not None and hit[0] == stat.st_mtime and hit[1] == stat.st_size:
            return hit[2]
        try:
            value = parse(path)
        except Exception:
            value = None
        self._entries[key] = (stat.st_mtime, stat.st_size, value)
        return value


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_tail(path: Path, limit: int = TAIL_BYTES) -> list[dict]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > limit:
            handle.seek(size - limit)
            handle.readline()  # discard the partial first line
        raw = handle.read()
    out = []
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_jsonl(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def normalized_ci_checks(
    value: Any, *, observed_at: Any, source: str
) -> dict[str, Any] | None:
    if not isinstance(value, list):
        return None
    checks = []
    for raw in value[:100]:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name") or raw.get("context")
        if not isinstance(name, str) or not name.strip():
            continue
        status = str(raw.get("status") or "UNKNOWN").upper()
        conclusion_value = raw.get("conclusion")
        conclusion = str(conclusion_value).upper() if conclusion_value is not None else None
        step = raw.get("step") or raw.get("current_step")
        checks.append(
            {
                "name": " ".join(name.split())[:160],
                "status": status[:40],
                "conclusion": conclusion[:40] if conclusion else None,
                "step": " ".join(step.split())[:160] if isinstance(step, str) else None,
            }
        )
    if not checks:
        return None
    passed_values = {"SUCCESS", "NEUTRAL", "SKIPPED"}
    passed = sum(check["conclusion"] in passed_values for check in checks)
    failed_values = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
    failed = sum(check["conclusion"] in failed_values for check in checks)
    running_values = {"IN_PROGRESS", "RUNNING"}
    queued_values = {"QUEUED", "PENDING", "WAITING", "EXPECTED", "REQUESTED"}
    running = [check for check in checks if check["status"] in running_values]
    queued = [check for check in checks if check["status"] in queued_values]
    timestamp = parse_timestamp(observed_at)
    age = max(0.0, time.time() - timestamp) if timestamp is not None else None
    return {
        "source": source,
        "observed_at": observed_at if timestamp is not None else None,
        "age_seconds": round(age, 1) if age is not None else None,
        "stale": age is None or age > CI_SNAPSHOT_STALE_SECONDS,
        "checks": checks,
        "total": len(checks),
        "passed": passed,
        "failed": failed,
        "running": len(running),
        "queued": len(queued),
        "running_check": running[0]["name"] if running else None,
        "running_step": running[0]["step"] if running else None,
    }


def read_ci_snapshot(
    path: Path, *, task_id: str, run_id: str, repository: str | None
) -> dict[str, Any] | None:
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        return None
    if value.get("task_id") != task_id or value.get("run_id") != run_id:
        return None
    if value.get("repository") != repository or validated_repository_slug(repository) is None:
        return None
    number = validated_issue_number(value.get("pull_request_number"))
    if number is None:
        return None
    expected_url = github_pull_request_url(repository, number)
    supplied_url = value.get("pull_request_url")
    if supplied_url is not None and supplied_url != expected_url:
        return None
    result = normalized_ci_checks(
        value.get("checks"), observed_at=value.get("observed_at_utc"), source="ci_snapshot.json"
    )
    if result is None:
        return None
    result["pull_request_number"] = number
    result["pull_request_url"] = expected_url
    return result


def read_usage_receipts(path: Path) -> list[dict[str, Any]]:
    """Read canonical per-turn receipts once; callers deduplicate run/turn."""
    receipts = []
    for event in read_jsonl(path):
        if event.get("event") != "supervisor_decision":
            continue
        fields = event.get("fields")
        if not isinstance(fields, dict):
            continue
        turn = fields.get("turn")
        if type(turn) is not int or turn < 1:
            continue
        usage = fields.get("provider_usage")
        session = fields.get("provider_session")
        session = session if isinstance(session, dict) else {}
        receipts.append(
            {
                "turn": turn,
                "provider": fields.get("provider") or session.get("provider"),
                "model": fields.get("model"),
                "role": fields.get("role") or "task_supervisor",
                "status": fields.get("provider_call_status") or "succeeded",
                "usage": usage if isinstance(usage, dict) else None,
                "pooled_session": bool(session.get("warm_pooling_active")),
                "timestamp": event.get("timestamp_utc"),
            }
        )
    return receipts


def summarize_worker_run(path: Path) -> dict:
    """Condense one worker's progress.jsonl into current activity + outcome."""
    events = read_jsonl_tail(path)
    summary: dict[str, Any] = {
        "status": None,
        "finished": False,
        "turn": None,
        "action": None,
        "phase": None,
        "issue_state": None,
        "message": None,
        "issue_number": None,
        "issue_url": None,
        "_issue_url_evidence": [],
        "pull_request_number": None,
        "pull_request_url": None,
        "_pull_request_url_evidence": [],
        "projection_state": None,
        "projection_timestamp": None,
        "first_timestamp": None,
        "last_timestamp": None,
        "worker_id": None,
        "elapsed_seconds": None,
        "stage_elapsed_seconds": None,
        "role": None,
        "provider": None,
        "attempt": None,
        "blocked_reason": None,
        "ci_checks": None,
        "ci_observed_at": None,
    }
    action_started_elapsed: float | None = None
    previous_action: str | None = None
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("event")
        fields = event.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}
        timestamp = event.get("timestamp_utc")
        if parse_timestamp(timestamp) is not None:
            summary["first_timestamp"] = summary["first_timestamp"] or timestamp
            summary["last_timestamp"] = timestamp
        summary["worker_id"] = event.get("worker_id") or summary["worker_id"]
        elapsed = positive_number(event.get("elapsed_seconds"))
        if elapsed is not None:
            summary["elapsed_seconds"] = elapsed
        containers = nested_objects(fields)
        for values in containers:
            turn = values.get("turn")
            if type(turn) is int and turn > 0:
                summary["turn"] = turn
            attempt = values.get("attempt") or values.get("attempt_number")
            if type(attempt) is int and attempt > 0:
                summary["attempt"] = attempt
            summary["role"] = values.get("role") or summary["role"]
            summary["provider"] = values.get("provider") or summary["provider"]
            for field in ISSUE_NUMBER_FIELDS:
                issue_number = validated_issue_number(values.get(field))
                if issue_number is not None:
                    summary["issue_number"] = issue_number
            for field in ISSUE_URL_FIELDS:
                if field in values:
                    summary["_issue_url_evidence"].append(values[field])
            for field in PULL_REQUEST_NUMBER_FIELDS:
                number = validated_issue_number(values.get(field))
                if number is not None:
                    summary["pull_request_number"] = number
            for field in PULL_REQUEST_URL_FIELDS:
                if field in values:
                    summary["_pull_request_url_evidence"].append(values[field])
            for check_field in ("checks", "ci_checks", "status_check_rollup", "statusCheckRollup"):
                if check_field in values:
                    summary["ci_checks"] = values[check_field]
                    summary["ci_observed_at"] = timestamp
        if kind == "state_observed":
            summary["phase"] = fields.get("phase") or summary["phase"]
            summary["issue_state"] = fields.get("issue_state") or summary["issue_state"]
        if kind in (
            "pipeline_action_started",
            "pipeline_action_heartbeat",
            "pipeline_action_completed",
            "pipeline_action_failed",
            "supervisor_decision",
            "action_completed",
            "action_rejected",
        ):
            action = fields.get("action")
            if isinstance(action, str) and action:
                if action != previous_action:
                    action_started_elapsed = (
                        0.0
                        if previous_action is None and kind == "pipeline_action_heartbeat"
                        else elapsed
                    )
                    previous_action = action
                summary["action"] = action
                # An action name alone is not CI evidence. The classifier combines
                # merge-closeout + this action + an exact PR, while a durable
                # checks_pending result remains sufficient on its own.
                summary["projection_state"] = "active"
                summary["projection_timestamp"] = timestamp
        if event.get("message"):
            summary["message"] = event.get("message")
        for values in containers:
            candidate = projected_state(values.get("status") or values.get("result_status"))
            if candidate is not None and kind in (
                "action_completed",
                "pipeline_action_completed",
                "pipeline_action_failed",
            ):
                summary["projection_state"] = candidate
                summary["projection_timestamp"] = timestamp
            reason = values.get("blocked_reason") or values.get("reason")
            if isinstance(reason, str) and reason:
                summary["blocked_reason"] = reason
        if kind == "terminal_state":
            summary["status"] = fields.get("status") or summary["status"]
            candidate = projected_state(summary["status"])
            if candidate is not None:
                summary["projection_state"] = candidate
                summary["projection_timestamp"] = timestamp
        if kind == "run_finished":
            summary["status"] = fields.get("status") or summary["status"]
            summary["finished"] = True
            candidate = projected_state(summary["status"])
            if candidate is not None:
                summary["projection_state"] = candidate
                summary["projection_timestamp"] = timestamp
    if summary["elapsed_seconds"] is not None:
        if action_started_elapsed is None:
            summary["stage_elapsed_seconds"] = summary["elapsed_seconds"]
        else:
            summary["stage_elapsed_seconds"] = max(
                0.0, summary["elapsed_seconds"] - action_started_elapsed
            )
    return summary


# --------------------------------------------------------------------------
# snapshot
# --------------------------------------------------------------------------


class Snapshot:
    def __init__(self, tasks_dir: Path, state_root: Path) -> None:
        self.tasks_dir = tasks_dir
        self.state_root = state_root
        self.outputs = state_root / ".task-review-agent" / "outputs"
        self.cache = FileCache()
        self._taskgraph_stamp: str | None = None
        self._taskgraph_cache: dict[str, dict[str, Any]] = {}

    def load_contracts(self) -> dict[str, dict]:
        contracts: dict[str, dict] = {}
        for path in sorted(self.tasks_dir.iterdir()):
            if not TASK_FILE_RE.match(path.name):
                continue
            data = self.cache.get(path, read_json)
            if isinstance(data, dict) and data.get("id") == path.stem:
                contracts[path.stem] = data
        return contracts

    def worker_runs(self, task_id: str, repository: str | None) -> list[dict[str, Any]]:
        task_dir = self.outputs / task_id
        if not task_dir.is_dir():
            return []
        try:
            entries = list(task_dir.iterdir())
        except OSError:
            return []
        candidates: list[tuple[float, Path]] = []
        for run_dir in entries:
            progress = run_dir / "progress.jsonl"
            try:
                mtime = progress.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, progress))
        records: list[dict[str, Any]] = []
        for mtime, progress_path in sorted(candidates, key=lambda item: item[0]):
            raw_summary = self.cache.get(progress_path, summarize_worker_run)
            if not isinstance(raw_summary, dict):
                continue
            summary = dict(raw_summary)
            result = self.cache.get(progress_path.parent / "run_result.json", read_json)
            if isinstance(result, dict):
                if summary.get("issue_number") is None:
                    summary["issue_number"] = validated_issue_number(result.get("issue_number"))
                if summary.get("pull_request_number") is None:
                    summary["pull_request_number"] = validated_issue_number(result.get("pull_request_number"))
                if not summary.get("_issue_url_evidence") and "issue_url" in result:
                    summary["_issue_url_evidence"] = [result.get("issue_url")]
                if not summary.get("_pull_request_url_evidence") and "pull_request_url" in result:
                    summary["_pull_request_url_evidence"] = [result.get("pull_request_url")]
            summary.update(
                run_id=progress_path.parent.name,
                progress_path=progress_path,
                mtime=mtime,
                run_result=result if isinstance(result, dict) else None,
            )
            records.append(summary)
        if not records:
            return []
        issue_number = None
        pull_number = None
        for record in reversed(records):
            if issue_number is None:
                issue_number = validated_issue_number(record.get("issue_number"))
                if issue_number is None:
                    for candidate in reversed(record.get("_issue_url_evidence") or []):
                        issue_number = issue_number_from_url(candidate, repository)
                        if issue_number is not None:
                            break
            if pull_number is None:
                pull_number = validated_issue_number(record.get("pull_request_number"))
                if pull_number is None:
                    for candidate in reversed(record.get("_pull_request_url_evidence") or []):
                        pull_number = pull_request_number_from_url(candidate, repository)
                        if pull_number is not None:
                            break
        current = records[-1]
        current["issue_number"] = issue_number
        current["issue_url"] = github_issue_url(repository, issue_number)
        current["pull_request_number"] = pull_number
        current["pull_request_url"] = github_pull_request_url(repository, pull_number)
        current["updated_at"] = datetime.fromtimestamp(current["mtime"], timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        current["age_seconds"] = round(max(0.0, time.time() - current["mtime"]), 1)
        try:
            ci = read_ci_snapshot(
                current["progress_path"].parent / "ci_snapshot.json",
                task_id=task_id,
                run_id=current["run_id"],
                repository=repository,
            )
        except Exception:
            ci = None
        if not isinstance(ci, dict) and current.get("ci_checks") is not None:
            ci = normalized_ci_checks(
                current["ci_checks"],
                observed_at=current.get("ci_observed_at"),
                source="progress.jsonl",
            )
        current["ci"] = ci if isinstance(ci, dict) else None
        for record in records:
            record.pop("_issue_url_evidence", None)
            record.pop("_pull_request_url_evidence", None)
        return records

    def latest_worker_run(self, task_id: str, repository: str | None) -> dict | None:
        records = self.worker_runs(task_id, repository)
        if not records:
            return None
        summary = dict(records[-1])
        for internal in ("progress_path", "mtime", "run_result"):
            summary.pop(internal, None)
        return summary

    def taskgraph_states(self, task_ids: list[str]) -> tuple[bool, dict[str, dict[str, Any]]]:
        """Use TaskGraph's committed-HEAD evaluator; never infer conformance."""
        checkout = self.tasks_dir.parent
        if not (checkout / ".git").exists():
            return False, {}
        stamp = self.git_head_stamp(checkout)
        if (
            stamp is not None
            and stamp == self._taskgraph_stamp
            and all(task_id in self._taskgraph_cache for task_id in task_ids)
        ):
            return True, {task_id: self._taskgraph_cache[task_id] for task_id in task_ids}
        module_dir = checkout / "Pipeline" / "TaskGraph"
        if not module_dir.is_dir():
            return False, {}
        module_text = str(module_dir)
        if module_text not in sys.path:
            sys.path.insert(0, module_text)
        try:
            from current_conformance import ConformanceEvaluationContext

            context = ConformanceEvaluationContext(checkout)
            states = {task_id: context.evaluate(task_id).to_dict() for task_id in task_ids}
        except Exception:
            return False, {}
        self._taskgraph_stamp = stamp
        self._taskgraph_cache = states
        return True, states

    @staticmethod
    def git_head_stamp(checkout: Path) -> str | None:
        """Read the local Git administrative files without executing Git."""
        marker = checkout / ".git"
        try:
            if marker.is_file():
                line = marker.read_text(encoding="utf-8").strip()
                if not line.startswith("gitdir: "):
                    return None
                git_dir = Path(line[8:])
                if not git_dir.is_absolute():
                    git_dir = (checkout / git_dir).resolve()
            else:
                git_dir = marker
            head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
            if not head.startswith("ref: "):
                return head
            reference = head[5:]
            direct = git_dir / reference
            if direct.is_file():
                return f"{reference}:{direct.read_text(encoding='utf-8').strip()}"
            common_marker = git_dir / "commondir"
            common = (
                (git_dir / common_marker.read_text(encoding="utf-8").strip()).resolve()
                if common_marker.is_file()
                else git_dir
            )
            ref_path = common / reference
            if ref_path.is_file():
                return f"{reference}:{ref_path.read_text(encoding='utf-8').strip()}"
            packed = common / "packed-refs"
            return f"{reference}:{packed.stat().st_mtime_ns}:{packed.stat().st_size}"
        except OSError:
            return None

    @staticmethod
    def scheduler_projection(events: list[dict]) -> dict[str, Any]:
        lifecycle: dict[str, dict[str, Any]] = {}
        transitions: dict[str, dict[str, Any]] = {}
        queued: list[str] = []
        gate_timestamp = None
        for event in events:
            if not isinstance(event, dict):
                continue
            task_id = event.get("task_id")
            kind = event.get("event")
            timestamp = event.get("timestamp_utc")
            if isinstance(task_id, str) and kind == "worker_launched":
                lifecycle[task_id] = {
                    "active": True,
                    "timestamp": timestamp,
                    "worker_id": event.get("worker_id"),
                }
            elif isinstance(task_id, str) and kind in ("worker_finished", "worker_returned_to_pool"):
                lifecycle[task_id] = {"active": False, "timestamp": timestamp}
            transition = event.get("workflow_transition")
            if not isinstance(transition, dict):
                fields = event.get("fields")
                transition = fields.get("workflow_transition") if isinstance(fields, dict) else None
            if isinstance(task_id, str) and isinstance(transition, dict):
                state = transition.get("to_state")
                phase = transition.get("to_phase")
                if isinstance(state, str) and isinstance(phase, str):
                    transitions[task_id] = {
                        "state": state,
                        "phase": phase,
                        "timestamp": timestamp,
                    }
            if kind == "integration_gate_observed":
                values = event.get("queued_task_ids")
                queued = [value for value in values if isinstance(value, str)] if isinstance(values, list) else []
                gate_timestamp = timestamp
        return {
            "lifecycle": lifecycle,
            "transitions": transitions,
            "queued": queued,
            "gate_timestamp": gate_timestamp,
        }

    def token_cost(
        self,
        task_id: str,
        records: list[dict[str, Any]],
        shared_events: list[dict],
        taskgraph: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Use persisted usage only; no pricing or provider calls occur here."""
        receipts: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for record in records:
            for receipt in self.cache.get(record["progress_path"], read_usage_receipts) or []:
                identity = (record["run_id"], receipt["turn"])
                if identity in seen:
                    continue
                seen.add(identity)
                receipts.append({**receipt, "run_id": record["run_id"]})

        direct_cost = 0.0
        direct_tokens = 0
        complete = True
        missing = 0
        failed = 0
        categories = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
        }
        breakdown = []
        for receipt in receipts:
            usage = receipt.get("usage")
            status = str(receipt.get("status") or "").casefold()
            if status not in ("succeeded", "success", "complete", "completed"):
                failed += 1
            total_value = positive_number(usage.get("total_tokens")) if isinstance(usage, dict) else None
            total = int(total_value) if total_value is not None and total_value.is_integer() else None
            cost = positive_number(usage.get("estimated_cost_usd")) if isinstance(usage, dict) else None
            if total is None or cost is None:
                complete = False
                missing += 1
            if total is not None:
                direct_tokens += total
            if cost is not None:
                direct_cost += cost
            if isinstance(usage, dict):
                for name in categories:
                    number = positive_number(usage.get(name))
                    if number is not None and number.is_integer():
                        categories[name] += int(number)
            breakdown.append(
                {
                    "role": receipt.get("role"),
                    "provider": receipt.get("provider"),
                    "model": receipt.get("model"),
                    "run_id": receipt.get("run_id"),
                    "turn": receipt.get("turn"),
                    "cost_usd": cost,
                    "total_tokens": total,
                    "pooled_session": receipt.get("pooled_session") is True,
                    "shared": False,
                }
            )

        allocated_cost = 0.0
        allocated_tokens = 0
        shared_calls = []
        shared_seen: set[str] = set()
        for event in shared_events:
            if event.get("event") != "architect_provider_call":
                continue
            call_id = event.get("agent_runtime_run_id")
            task_ids = event.get("task_ids")
            usage = event.get("provider_usage")
            if (
                not isinstance(call_id, str)
                or call_id in shared_seen
                or not isinstance(task_ids, list)
                or task_id not in task_ids
                or len(task_ids) != len(set(task_ids))
                or not isinstance(usage, dict)
            ):
                continue
            shared_seen.add(call_id)
            count = len(task_ids)
            if count == 0:
                continue
            cost = positive_number(usage.get("estimated_cost_usd"))
            raw_total = positive_number(usage.get("total_tokens"))
            total = int(raw_total) if raw_total is not None and raw_total.is_integer() else None
            cost_share = cost / count if cost is not None else None
            token_share = total // count if total is not None else None
            if cost_share is None or token_share is None:
                complete = False
                missing += 1
            allocated_cost += cost_share or 0
            allocated_tokens += token_share or 0
            shared_calls.append(
                {
                    "call_id": call_id,
                    "complete_cost_usd": cost,
                    "allocated_cost_usd": round(cost_share, 8) if cost_share is not None else None,
                    "allocated_tokens": token_share,
                    "allocation_method": f"equal share across {count} named tasks",
                }
            )

        recorded_tokens: int | None = direct_tokens + allocated_tokens if receipts or shared_calls else None
        recorded_cost: float | None = direct_cost + allocated_cost if receipts or shared_calls else None
        cost_source = "persisted provider usage" if recorded_cost is not None else "unavailable"
        token_source = "persisted provider usage" if recorded_tokens is not None else "unavailable"
        if taskgraph and taskgraph.get("token_usage_status") in ("complete", "incomplete"):
            graph_total = taskgraph.get("total_tokens_used")
            if type(graph_total) is int:
                if recorded_cost is not None and recorded_tokens != graph_total:
                    # TaskGraph proves that the operational cost receipts do not
                    # cover every token-bearing call. Keep the cost as a lower bound.
                    complete = False
                recorded_tokens = graph_total
            complete = taskgraph.get("token_usage_complete") is True and complete
            token_source = "committed TaskGraph token-usage.json"
        if recorded_cost is not None:
            recorded_cost = round(recorded_cost, 8)
        if recorded_cost is None:
            cost_label = "unavailable"
        elif complete:
            cost_label = f"${recorded_cost:.2f}"
        else:
            cost_label = f"at least ${recorded_cost:.2f}"
        coverage = round(100 * (len(receipts) - missing) / len(receipts)) if receipts else None
        updated_candidates = [
            receipt.get("timestamp")
            for receipt in receipts
            if parse_timestamp(receipt.get("timestamp")) is not None
        ]
        usage_updated_at = max(updated_candidates, key=parse_timestamp) if updated_candidates else None
        return {
            "recorded_cost_usd": recorded_cost,
            "recorded_total_tokens": recorded_tokens,
            "usage_complete": complete if receipts or shared_calls or recorded_tokens is not None else False,
            "missing_usage_calls": missing,
            "total_calls": len(receipts) + len(shared_calls),
            "failed_or_incomplete_calls": failed + missing,
            "coverage_percent": coverage,
            "cost_label": cost_label,
            "cost_source": cost_source,
            "token_source": token_source,
            "pricing_version": None,
            "usage_updated_at": usage_updated_at,
            "direct_agent_cost_usd": round(direct_cost, 8) if receipts else None,
            "allocated_shared_cost_usd": round(allocated_cost, 8) if shared_calls else 0.0,
            "breakdown": breakdown,
            "shared_calls": shared_calls,
            "estimated_cache_savings_usd": None,
            **categories,
            "projection_label": "insufficient history",
            "projection_sample_count": 0,
            "projected_final_cost_usd": None,
        }

    @staticmethod
    def classify(
        *,
        contract: dict,
        task_id: str,
        excluded: set[str],
        worker: dict[str, Any] | None,
        lifecycle: dict[str, Any] | None,
        transition: dict[str, Any] | None,
        queued: list[str],
        taskgraph_available: bool,
        taskgraph: dict[str, Any] | None,
    ) -> tuple[str, bool]:
        if contract.get("contract_disposition") == "cancelled":
            return "cancelled", False
        if task_id in excluded:
            return "excluded", False
        if taskgraph and taskgraph.get("state") == "conformant":
            return "complete", False
        projection = worker.get("projection_state") if worker else None
        projection_time = worker.get("projection_timestamp") if worker else None
        active = bool(worker and not worker.get("finished"))
        if lifecycle and newer(lifecycle.get("timestamp"), worker.get("last_timestamp") if worker else None):
            active = lifecycle.get("active") is True
        workflow_newer = bool(transition and newer(transition.get("timestamp"), projection_time))
        launch_newer = bool(
            lifecycle
            and lifecycle.get("active") is True
            and newer(lifecycle.get("timestamp"), projection_time)
        )
        if workflow_newer or launch_newer:
            projection = None
        transition_projection = projected_state(transition.get("state")) if transition else None
        if workflow_newer and transition_projection in ("human_action", "failed", "blocked"):
            return transition_projection, False
        if projection == "complete" and not taskgraph_available:
            return "complete", False
        if projection in ("human_action", "failed", "blocked"):
            return projection, False
        if projection == "checks_pending" and not workflow_newer and not launch_newer:
            return "checks_pending", active
        if active:
            if (
                worker
                and worker.get("phase") == "merge_closeout"
                and worker.get("action") == CI_ACTION
                and worker.get("pull_request_url")
            ):
                return "checks_pending", True
            return "active", True
        if (
            transition
            and transition.get("state") == "agent_ready"
            and transition.get("phase") in INTEGRATION_PHASES
            and task_id in queued
        ):
            return "integration_queued", False
        return "pending", False

    @staticmethod
    def estimate(records: list[dict[str, Any]], worker: dict[str, Any] | None) -> dict[str, Any]:
        if not worker:
            return {"label": "Estimate unavailable", "sample_count": 0}
        durations = []
        for record in records[:-1]:
            if (
                record.get("finished")
                and record.get("phase") == worker.get("phase")
                and record.get("action") == worker.get("action")
            ):
                duration = positive_number(record.get("elapsed_seconds"))
                if duration is not None:
                    durations.append(duration)
        if len(durations) < MIN_ESTIMATE_SAMPLES:
            return {"label": "Estimate unavailable", "sample_count": len(durations)}
        low_total, high_total = min(durations), max(durations)
        elapsed = positive_number(worker.get("elapsed_seconds")) or 0
        low = max(0.0, low_total - elapsed)
        high = max(0.0, high_total - elapsed)
        if elapsed > high_total:
            label = f"Running longer than usual (usual total: {duration_text(low_total)}–{duration_text(high_total)})"
        else:
            label = f"Estimate: {duration_text(low)}–{duration_text(high)} remaining"
        return {
            "label": label,
            "sample_count": len(durations),
            "remaining_low_seconds": low,
            "remaining_high_seconds": high,
        }

    @staticmethod
    def node_lines(task: dict[str, Any]) -> list[str] | None:
        state = task["state"]
        worker = task.get("worker") or {}
        progress = task["progress"]
        if state == "decomposition_ready":
            return ["DECOMPOSITION AVAILABLE"]
        if state == "checks_pending":
            ci = progress.get("ci")
            if ci:
                first = f"IN CI · {ci['passed']}/{ci['total']} checks passed"
                current = ci.get("running_check") or ("checks queued" if ci.get("queued") else "checks observed")
                if ci.get("running_step"):
                    current += f": {ci['running_step']}"
                second = f"{current} · {duration_text(progress.get('stage_elapsed_seconds'))} elapsed"
            else:
                first = "IN CI · check status unavailable"
                second = f"Monitoring pull-request checks · {duration_text(progress.get('stage_elapsed_seconds'))} elapsed"
            third = progress["estimate"]["label"]
            if ci and ci.get("stale"):
                third += f" · stale ({duration_text(ci.get('age_seconds'))} old)"
            return [first, second, third]
        if state == "integration_queued":
            first = "WAITING FOR CI SLOT"
            if progress.get("queue_position") is not None:
                first += f" · queue position {progress['queue_position']}"
            return [first, f"Verified {duration_text(progress.get('queue_wait_seconds'))} ago"]
        if state != "active":
            return None
        phase = worker.get("phase")
        stage, label = PHASE_STAGES.get(
            phase, (None, str(phase or "PHASE UNAVAILABLE").replace("_", " ").upper())
        )
        first = f"{label} · Stage {stage}/6" if stage else label
        action = ACTION_LABELS.get(
            worker.get("action"),
            str(worker.get("action") or "Current phase unavailable").replace("_", " ").title(),
        )
        elapsed = duration_text(progress.get("stage_elapsed_seconds"))
        second = f"{action} · {elapsed} elapsed" if elapsed != "unavailable" else f"{action} · elapsed unavailable"
        if worker.get("phase") == "decomposition" and progress.get("children_total") is not None:
            third = f"{progress['children_complete']}/{progress['children_total']} children complete"
        else:
            activity = []
            if worker.get("role"):
                activity.append(str(worker["role"]).replace("_", " ").title())
            if worker.get("provider"):
                activity.append(str(worker["provider"]))
            if worker.get("turn") is not None:
                activity.append(f"turn {worker['turn']}")
            if (progress.get("attempt") or 0) > 1:
                activity.append(f"attempt {progress['attempt']}")
            if task["token_cost"].get("recorded_cost_usd") is not None:
                activity.append(f"cost so far {task['token_cost']['cost_label']}")
            third = " · ".join(activity) if activity else progress["estimate"]["label"]
        return [first, second, third]

    def build(self) -> dict:
        contracts = self.load_contracts()

        run_dir = newest_autonomous_run(self.state_root)
        manifest = self.cache.get(run_dir / "manifest.json", read_json) if run_dir else None
        progress = self.cache.get(run_dir / "progress.json", read_json) if run_dir else None
        receipt = self.cache.get(run_dir / "graph-complete.json", read_json) if run_dir else None
        events = self.cache.get(run_dir / "events.jsonl", read_jsonl) if run_dir else None
        events = events or []
        timeline = self.cache.get(run_dir / "run_timeline.jsonl", read_jsonl) if run_dir else []

        manifest = manifest if isinstance(manifest, dict) else {}
        repository = validated_repository_slug(manifest.get("github_repository"))
        scope = set(manifest.get("target_task_ids") or [])
        excluded = set(manifest.get("excluded_task_ids") or [])

        scheduler_projection = self.scheduler_projection(events)
        taskgraph_available, taskgraph_states = self.taskgraph_states(list(contracts))

        tasks = []
        for task_id, contract in contracts.items():
            records = self.worker_runs(task_id, repository)
            summary = dict(records[-1]) if records else None
            state, active = self.classify(
                contract=contract,
                task_id=task_id,
                excluded=excluded,
                worker=summary,
                lifecycle=scheduler_projection["lifecycle"].get(task_id),
                transition=scheduler_projection["transitions"].get(task_id),
                queued=scheduler_projection["queued"],
                taskgraph_available=taskgraph_available,
                taskgraph=taskgraph_states.get(task_id),
            )
            if summary:
                summary["active"] = active
                summary["monitoring_ci"] = state == "checks_pending" and active
                for internal in ("progress_path", "mtime", "run_result"):
                    summary.pop(internal, None)
            token_cost = self.token_cost(task_id, records, events, taskgraph_states.get(task_id))
            elapsed_values = [positive_number(record.get("elapsed_seconds")) or 0 for record in records]
            transition = scheduler_projection["transitions"].get(task_id)
            queue_position = (
                scheduler_projection["queued"].index(task_id) + 1
                if task_id in scheduler_projection["queued"]
                else None
            )
            queue_started = parse_timestamp(transition.get("timestamp")) if transition else None
            progress_data = {
                "phase": summary.get("phase") if summary else (transition.get("phase") if transition else None),
                "action": summary.get("action") if summary else None,
                "attempt": len(records) or None,
                "retry_count": max(0, len(records) - 1),
                "current_attempt_elapsed_seconds": elapsed_values[-1] if elapsed_values else None,
                "stage_elapsed_seconds": summary.get("stage_elapsed_seconds") if summary else None,
                "total_elapsed_seconds": sum(elapsed_values) if elapsed_values else None,
                "queue_position": queue_position,
                "queue_wait_seconds": max(0.0, time.time() - queue_started) if queue_started is not None else None,
                "ci": summary.get("ci") if summary else None,
                "estimate": self.estimate(records, summary),
                "blocked_reason": summary.get("blocked_reason") if summary else None,
            }

            provenance = contract.get("provenance") or {}
            tasks.append(
                {
                    "id": task_id,
                    "title": contract.get("title") or task_id,
                    "parent": contract.get("parent"),
                    "depends_on": list(contract.get("depends_on") or []),
                    "kind": contract.get("kind"),
                    "disposition": contract.get("contract_disposition"),
                    "decomposition_state": contract.get("decomposition_state"),
                    "execution_scope": contract.get("execution_scope"),
                    "notes": contract.get("notes"),
                    "reason": contract.get("decomposition_reason"),
                    "resources": list(contract.get("exclusive_resources") or []),
                    "acceptance": [
                        c.get("requirement")
                        for c in (contract.get("acceptance_criteria") or [])
                        if isinstance(c, dict)
                    ],
                    "wave": provenance.get("wave"),
                    "column": provenance.get("column"),
                    "in_scope": task_id in scope,
                    "state": state,
                    "worker": summary,
                    "progress": progress_data,
                    "token_cost": token_cost,
                    "taskgraph": taskgraph_states.get(task_id),
                }
            )

        # Unmet dependencies keep a task pending; otherwise it is ready.
        done = {t["id"] for t in tasks if t["state"] in ("complete", "cancelled")}
        for task in tasks:
            if task["state"] == "pending" and all(d in done for d in task["depends_on"]):
                task["state"] = "ready"
            if task["state"] == "ready" and is_available_decomposition(task):
                task["state"] = "decomposition_ready"

        by_parent: dict[str, list[dict[str, Any]]] = {}
        for task in tasks:
            if task.get("parent"):
                by_parent.setdefault(task["parent"], []).append(task)
        for task in tasks:
            children = by_parent.get(task["id"])
            if children:
                task["progress"]["children_total"] = len(children)
                task["progress"]["children_complete"] = sum(
                    child["state"] == "complete" for child in children
                )

        # Project final cost only from at least three exact-profile completed
        # persisted totals. No model pricing is present in this visualizer.
        for task in tasks:
            usage = task["token_cost"]
            if task["state"] not in ("active", "checks_pending"):
                continue
            worker = task.get("worker") or {}
            providers = sorted(
                {item.get("provider") for item in usage["breakdown"] if item.get("provider")}
            )
            roles = sorted({item.get("role") for item in usage["breakdown"] if item.get("role")})
            pooled = any(item.get("pooled_session") for item in usage["breakdown"])
            profile = (
                worker.get("phase"),
                tuple(providers),
                tuple(roles),
                task["progress"].get("retry_count"),
                pooled,
                task.get("rigor_profile"),
            )
            samples = []
            for candidate in tasks:
                candidate_worker = candidate.get("worker") or {}
                candidate_usage = candidate["token_cost"]
                candidate_providers = sorted(
                    {item.get("provider") for item in candidate_usage["breakdown"] if item.get("provider")}
                )
                candidate_roles = sorted(
                    {item.get("role") for item in candidate_usage["breakdown"] if item.get("role")}
                )
                candidate_profile = (
                    candidate_worker.get("phase"),
                    tuple(candidate_providers),
                    tuple(candidate_roles),
                    candidate["progress"].get("retry_count"),
                    any(item.get("pooled_session") for item in candidate_usage["breakdown"]),
                    candidate.get("rigor_profile"),
                )
                if (
                    candidate["state"] == "complete"
                    and candidate_profile == profile
                    and candidate_usage.get("recorded_cost_usd") is not None
                    and candidate_usage.get("usage_complete")
                ):
                    samples.append(candidate_usage["recorded_cost_usd"])
            if len(samples) >= MIN_ESTIMATE_SAMPLES:
                usage["projection_sample_count"] = len(samples)
                usage["projected_final_cost_usd"] = [min(samples), max(samples)]
                usage["projection_label"] = (
                    f"${min(samples):.2f}–${max(samples):.2f} ({len(samples)} samples)"
                )

        for task in tasks:
            lines = self.node_lines(task)
            if lines:
                task["node_lines"] = lines

        blocked_reasons = [
            e.get("reason") or e.get("message")
            for e in events[-40:]
            if e.get("event") == "scheduler_blocked"
        ]

        # Only this run's exact scheduler launches can supply global worker
        # activity. Do not reuse the per-node newest-run/history heuristic here.
        worker_events = []
        launched_runs = set()
        for event in events:
            task_id, worker_run_id = event.get("task_id"), event.get("run_id")
            if (event.get("event") != "worker_launched" or task_id not in scope
                    or not isinstance(task_id, str) or not TASK_FILE_RE.fullmatch(task_id + ".yaml")
                    or not isinstance(worker_run_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", worker_run_id)):
                continue
            if (task_id, worker_run_id) in launched_runs:
                continue
            launched_runs.add((task_id, worker_run_id))
            path = self.outputs / task_id / worker_run_id / "progress.jsonl"
            for item in self.cache.get(path, read_jsonl_tail) or []:
                worker_events.append({**item, "_task_id": task_id, "_worker_run_id": worker_run_id})

        activity = build_pipeline_activity(
            manifest=manifest, progress=progress, receipt=receipt, events=events,
            timeline=timeline or [], worker_events=worker_events, tasks=tasks, now=time.time(),
        )

        return {
            "generated_at": utc_now(),
            "pipeline_activity": activity,
            "tasks_dir": str(self.tasks_dir),
            "state_root": str(self.state_root),
            "run": {
                "dir": str(run_dir) if run_dir else None,
                "run_id": manifest.get("run_id"),
                "repository": repository,
                "max_capacity": manifest.get("max_capacity"),
                "targets": sorted(scope),
                "excluded": sorted(excluded),
                "progress": progress if isinstance(progress, dict) else None,
                "complete": bool(receipt),
            },
            "scheduler": {
                "active": sorted(
                    task_id
                    for task_id, item in scheduler_projection["lifecycle"].items()
                    if item.get("active")
                ),
                "blocked_reasons": [r for r in blocked_reasons if r][-5:],
            },
            "events": events[-60:],
            "tasks": tasks,
        }

    def fingerprint(self) -> str:
        """Cheap change detector across every file the snapshot reads."""
        parts: list[str] = []
        head_stamp = self.git_head_stamp(self.tasks_dir.parent)
        if head_stamp is not None:
            parts.append(f"taskgraph-head:{head_stamp}")
        try:
            for path in sorted(self.tasks_dir.iterdir()):
                if TASK_FILE_RE.match(path.name):
                    stat = path.stat()
                    parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            pass
        run_dir = newest_autonomous_run(self.state_root)
        if run_dir:
            for name in ("manifest.json", "progress.json", "events.jsonl", "run_timeline.jsonl", "graph-complete.json"):
                try:
                    stat = (run_dir / name).stat()
                except OSError:
                    continue
                parts.append(f"{name}:{stat.st_mtime_ns}:{stat.st_size}")
        try:
            for task_dir in self.outputs.iterdir():
                try:
                    parts.append(f"{task_dir.name}:{task_dir.stat().st_mtime_ns}")
                    runs = list(task_dir.iterdir())
                except OSError:
                    continue
                for run in runs:
                    for name in ("progress.jsonl", "run_result.json", "ci_snapshot.json"):
                        try:
                            stat = (run / name).stat()
                        except OSError:
                            continue
                        parts.append(
                            f"{task_dir.name}/{run.name}/{name}:"
                            f"{stat.st_mtime_ns}:{stat.st_size}"
                        )
        except OSError:
            pass
        evidence_root = self.tasks_dir.parent / "Pipeline" / "TaskGraph" / "evidence"
        try:
            for path in evidence_root.glob("NSC-*/**/*.json"):
                stat = path.stat()
                parts.append(
                    f"taskgraph/{path.relative_to(evidence_root)}:"
                    f"{stat.st_mtime_ns}:{stat.st_size}"
                )
        except OSError:
            pass
        return str(hash("|".join(parts)))


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    snapshot: Snapshot

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/vendor/"):
            target = (HERE / path.lstrip("/")).resolve()
            if HERE in target.parents and target.is_file():
                self._send(200, target.read_bytes(), "application/javascript; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")
            return
        if path == "/api/state":
            body = json.dumps(self.snapshot.build()).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/api/stream":
            self._stream()
            return
        self._send(404, b"not found", "text/plain")

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = None
        try:
            while True:
                current = self.snapshot.fingerprint()
                if current != last:
                    last = current
                    payload = json.dumps(self.snapshot.build())
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                else:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="Live NSC gauntlet task-graph view.")
    parser.add_argument("--tasks", help="path to a checkout's Tasks/ directory")
    parser.add_argument("--state", help="directory containing .task-review-agent")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    tasks_dir, state_root = discover_roots(args.tasks, args.state)
    if not tasks_dir.is_dir():
        raise SystemExit(f"Tasks directory not found: {tasks_dir}")

    Handler.snapshot = Snapshot(tasks_dir, state_root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True

    run_dir = newest_autonomous_run(state_root)
    print(f"  contracts : {tasks_dir}")
    print(f"  run state : {state_root}")
    print(f"  active run: {run_dir.name if run_dir else '(none found)'}")
    print(f"\n  http://127.0.0.1:{args.port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
