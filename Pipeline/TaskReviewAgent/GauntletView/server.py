#!/usr/bin/env python3
"""Local live view of an NSC gauntlet task graph.

Serves a Cytoscape.js page backed by local on-disk sources:

  Tasks/NSC-*.yaml                          structure (parent, depends_on, wave)
  .task-review-agent/autonomous-runs/.../   scheduler scope + events.jsonl
  .task-review-agent/outputs/<TASK>/<run>/  per-worker progress.jsonl
                                                + durable run_result.json
                                                + optional ci_snapshot.json
  Pipeline/TaskGraph/evidence/<TASK>/       committed conformance + token totals

Standalone mode writes nothing. Architect-managed mode may explicitly enable a
narrow one-time human approval that reuses the canonical Issue workflow service;
that capability is off by default. The view reuses TaskGraph's local
committed-HEAD evaluator and otherwise uses local durable state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for module_root in (HERE, ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
from pipeline_activity import build_local_pipeline_activity, build_pipeline_activity
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
WORKFLOW_TRANSITION_EVIDENCE_EVENTS = frozenset(
    {"local_resume_hint_send_completed", "workflow_transition_observed"}
)
INTEGRATION_PHASES = frozenset(
    {"candidate_gate", "delivery_evidence", "merge_closeout"}
)
DECOMPOSITION_EXECUTION_SCOPE = "needs_execution_decomposition"
DECOMPOSITION_READY_STATE = "concrete"
CURRENT_RUN_BOUNDARY_EVENTS = frozenset({"poll_started", "architect_started"})
HEALTH_SCHEMA = "nsc-gauntlet-view-health/v1"

# Presentation stage names stay centralized here; the browser consumes normalized
# node_lines and never reinterprets workflow phases.
PHASE_STAGES = {
    "waiting": (1, "WAITING"),
    "admission": (1, "WAITING"),
    "preparing_checkout": (2, "PREPARING CHECKOUT"),
    "checkout_preparation": (2, "PREPARING CHECKOUT"),
    "execution_scope": (3, "CHECKING TASK FILES"),
    "execution_crew": (3, "IMPLEMENTING AND VALIDATING"),
    "implementation": (3, "IMPLEMENTING"),
    "repair": (3, "REPAIRING"),
    "decomposition": (3, "DECOMPOSING"),
    "decomposition_apply_authorization": (3, "AWAITING VERIFICATION"),
    "decomposition_apply": (3, "DECOMPOSING"),
    "unity_runtime_validation": (4, "VALIDATING"),
    "validation": (4, "VALIDATING"),
    "candidate_gate": (5, "WAITING FOR MERGE GATE"),
    "delivery_evidence": (5, "PRODUCING EVIDENCE"),
    # Merge-closeout starts before a pull request/check monitor necessarily
    # exists.  IN CI is selected below only from exact durable PR evidence.
    "merge_closeout": (6, "SUBMITTING FOR CI"),
}
PIPELINE_STAGE_LABELS = {
    1: "WAITING",
    2: "CHECKOUT",
    3: "IMPLEMENT",
    4: "VALIDATE",
    5: "EVIDENCE",
    6: "CI",
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


def display_task_title(value: Any, fallback: str) -> str:
    """Normalise a task title for presentation without changing contracts."""
    title = str(value or fallback)
    return re.sub(r"\s{2,}", " ", title).strip(" :-") or fallback
ACTION_STAGES = {
    "prepare_task_checkout": 2,
    "run_execution_crew": 3,
    "repair_candidate": 3,
    "run_decomposition": 3,
    "integrate_current_main": 5,
    "run_authoritative_unity_test": 4,
    "run_unity_tests": 4,
    "run_validation": 4,
    "produce_delivery_evidence": 5,
    "publish_delivery_evidence": 5,
    "create_delivery_review_draft": 5,
    "create_delivery_review_proposal": 5,
    "publish_delivery_review": 5,
    "finalize_delivery_evidence": 5,
    "finalize_delivery_evidence_and_open_pr": 5,
    "open_pull_request": 5,
    "inspect_or_merge_pull_request": 6,
}
CI_SUBMISSION_ACTIONS = frozenset(
    {
        "create_delivery_review_draft",
        "create_delivery_review_proposal",
        "publish_delivery_review",
        "publish_delivery_evidence",
        "finalize_delivery_evidence",
        "finalize_delivery_evidence_and_open_pr",
        "open_pull_request",
    }
)
AGENT_ROLE_LABELS = {
    "task_supervisor": "Task Supervisor",
    "execution_crew": "ExecutionCrew",
    "task_decomposer": "Decomposition Author",
    "decomposition_reviewer": "Decomposition Reviewer",
    "contract_locality_auditor": "Contract Locality Auditor",
    "implementer": "Implementer",
    "test_author": "Test Author",
    "validator": "Validator",
    "lead_developer": "Lead Developer / Repair",
    "repair": "Lead Developer / Repair",
    "decomposition_worker": "Decomposition Worker",
}
AGENT_ROLE_ACTIONS = {
    "task_supervisor": "coordinating the task workflow",
    "execution_crew": "implementing the task",
    "decomposition_worker": "running the decomposition workflow",
    "task_decomposer": "authoring the decomposition plan",
    "decomposition_reviewer": "reviewing the decomposition plan",
    "contract_locality_auditor": "auditing contract locality",
    "implementer": "implementing the task",
    "test_author": "authoring task tests",
    "validator": "validating the candidate",
    "lead_developer": "repairing the candidate",
    "repair": "repairing the candidate",
}
SUPERVISOR_ACTIONS = {
    "run_execution_crew": "coordinating ExecutionCrew",
    "repair_candidate": "coordinating candidate repair",
    "run_decomposition": "coordinating decomposition",
    "prepare_task_checkout": "preparing the task checkout",
    "run_unity_tests": "coordinating Unity tests",
    "run_validation": "coordinating validation",
    "produce_delivery_evidence": "coordinating delivery evidence",
    "integrate_current_main": "merging main into the task branch",
    "create_delivery_review_draft": "submitting the task for CI",
    "create_delivery_review_proposal": "submitting the task for CI",
    "publish_delivery_review": "submitting the task for CI",
    "publish_delivery_evidence": "submitting the task for CI",
    "finalize_delivery_evidence": "submitting the task for CI",
    "finalize_delivery_evidence_and_open_pr": "submitting the task for CI",
    "open_pull_request": "submitting the task for CI",
    "inspect_or_merge_pull_request": "monitoring pull-request checks",
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

# Exact action outcomes may explain why a task changed hands.  These messages
# describe only what the durable action result proves: integrating current main
# into a candidate is not publication, while a merged pull request is.
DURABLE_TRANSITION_CONTEXTS = {
    ("integrate_current_main", "human_revalidation_required"): {
        "kind": "candidate_revalidation_required",
        "message": (
            "Current main merged into candidate successfully — waiting for "
            "revalidation review."
        ),
    },
    ("inspect_or_merge_pull_request", "merged"): {
        "kind": "published_post_merge_verification_pending",
        "message": "Published to main successfully — post-merge verification pending.",
    },
}

# These reservation kinds are produced from a parsed managed-Issue snapshot.
# Scheduler predictions and quarantined gate records are useful for conflict
# safety, but are not workflow-state authority for task presentation.
ISSUE_DERIVED_RESERVATION_EVIDENCE_TYPES = frozenset(
    {
        "durable_precheckout_surface_observed_empty",
        "durable_branch_or_checkout_actual_paths",
        "durable_branch_or_checkout_observed_empty",
        "durable_incomplete_surface_unknown",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_branch(source: Path) -> str | None:
    """Read the exact attached branch without changing repository state."""

    try:
        dot_git = source / ".git"
        git_dir = dot_git
        if dot_git.is_file():
            marker = dot_git.read_text(encoding="utf-8").strip()
            if not marker.startswith("gitdir: "):
                return None
            git_dir = Path(marker[8:])
            if not git_dir.is_absolute():
                git_dir = (source / git_dir).resolve()
        value = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    prefix = "ref: refs/heads/"
    return value[len(prefix):] if value.startswith(prefix) else None


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


def expand_decomposition_descendants(
    contracts: dict[str, dict[str, Any]], roots: set[str] | tuple[str, ...]
) -> set[str]:
    """Expand only the durable generated-child closure of exact display roots.

    Ordinary ``parent`` links describe the broader task hierarchy and must not
    widen an operator's view.  A generated descendant is admitted only when a
    decomposed contract names it in ``decomposition_children`` and the child
    contract points back to that exact parent.
    """

    expanded = {task_id for task_id in roots if task_id in contracts}
    pending = list(sorted(expanded))
    while pending:
        parent_id = pending.pop(0)
        parent = contracts[parent_id]
        if parent.get("decomposition_state") != "decomposed":
            continue
        child_ids = parent.get("decomposition_children")
        if not isinstance(child_ids, list):
            continue
        for child_id in child_ids:
            child = contracts.get(child_id) if isinstance(child_id, str) else None
            if (
                child is None
                or child.get("parent") != parent_id
                or child_id in expanded
            ):
                continue
            expanded.add(child_id)
            pending.append(child_id)
    return expanded


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


def has_durable_ci_monitor_evidence(worker: dict[str, Any] | None) -> bool:
    """Whether exact artifacts establish that PR/check monitoring has begun."""

    if not worker:
        return False
    if worker.get("projection_state") == "checks_pending" or isinstance(
        worker.get("ci"), dict
    ):
        return True
    return bool(
        worker.get("action") == CI_ACTION
        and validated_issue_number(worker.get("pull_request_number")) is not None
        and isinstance(worker.get("pull_request_url"), str)
        and worker["pull_request_url"]
    )


def active_stage_wording(worker: dict[str, Any] | None) -> str | None:
    """Prefer the most specific durable action without overstating CI state."""

    if not worker:
        return None
    action = worker.get("action")
    if action == "integrate_current_main":
        return "MERGING MAIN INTO TASK BRANCH"
    if action in CI_SUBMISSION_ACTIONS:
        return "SUBMITTING FOR CI"
    if action == CI_ACTION:
        return "IN CI" if has_durable_ci_monitor_evidence(worker) else "SUBMITTING FOR CI"
    return PHASE_STAGES.get(worker.get("phase"), (None, None))[1]


def pipeline_stage_projection(
    records: list[dict[str, Any]],
    worker: dict[str, Any] | None,
    *,
    active: bool,
    now: float,
    stop_at: float | None = None,
) -> tuple[list[dict[str, Any]], float | None, float | None]:
    """Build six honest clocks for only the latest persisted worker run."""

    current_stage = None
    if worker:
        current_stage = PHASE_STAGES.get(worker.get("phase"), (None, None))[0]
        current_stage = current_stage or ACTION_STAGES.get(worker.get("action"))
    evidence: dict[int, dict[str, Any]] = {}
    for record in records:
        for stage_number, item in (record.get("stage_evidence") or {}).items():
            if stage_number not in PIPELINE_STAGE_LABELS or not isinstance(item, dict):
                continue
            start = parse_timestamp(item.get("started_at"))
            end = parse_timestamp(item.get("completed_at"))
            if start is None:
                continue
            evidence[stage_number] = {"start": start, "end": end}
    if worker:
        for stage_number, item in (worker.get("stage_evidence") or {}).items():
            if stage_number not in PIPELINE_STAGE_LABELS or not isinstance(item, dict):
                continue
            start = parse_timestamp(item.get("started_at"))
            end = parse_timestamp(item.get("completed_at"))
            if start is not None:
                evidence[stage_number] = {"start": start, "end": end}

    rows = []
    for stage_number, label in PIPELINE_STAGE_LABELS.items():
        timing = evidence.get(stage_number)
        status = (
            "active"
            if active and stage_number == current_stage
            else "stopped"
            if (
                not active
                and stop_at is not None
                and timing
                and timing.get("end") is None
                and stage_number == current_stage
            )
            else "complete"
            if (timing and timing.get("end") is not None)
            or (current_stage is not None and stage_number < current_stage)
            else "future"
        )
        elapsed = None
        if timing:
            end = timing.get("end")
            if status == "active":
                end = now
            elif status == "stopped":
                end = stop_at
            if end is not None and end >= timing["start"]:
                elapsed = end - timing["start"]
        phase_label = active_stage_wording(worker)
        display_label = (
            f"{label} / {phase_label}"
            if status == "active" and isinstance(phase_label, str) and phase_label != label
            else label
        )
        rows.append(
            {
                "number": stage_number,
                "label": label,
                "display_label": display_label,
                "status": status,
                "elapsed_seconds": elapsed,
            }
        )

    starts = [
        parsed
        for parsed in (parse_timestamp(record.get("first_timestamp")) for record in records)
        if parsed is not None
    ]
    if worker:
        worker_start = parse_timestamp(worker.get("first_timestamp"))
        if worker_start is not None:
            starts.append(worker_start)
    task_start = min(starts) if starts else None
    task_end = (
        now
        if active
        else parse_timestamp(worker.get("last_timestamp"))
        if worker and worker.get("finished")
        else stop_at
        if stop_at is not None
        else parse_timestamp(worker.get("last_timestamp"))
        if worker
        else None
    )
    task_elapsed = (
        task_end - task_start
        if task_start is not None and task_end is not None and task_end >= task_start
        else None
    )
    recorded_stage = next(
        (row for row in reversed(rows) if row["status"] != "future"),
        None,
    )
    stage_elapsed = recorded_stage.get("elapsed_seconds") if recorded_stage else None
    return rows, stage_elapsed, task_elapsed


def run_terminal_timestamp(
    events: list[dict[str, Any]], timeline: list[dict[str, Any]], run_id: Any
) -> float | None:
    """Return the newest exact terminal boundary already recorded for this run."""

    candidates: list[float] = []
    for source, rows in (("scheduler", events), ("timeline", timeline)):
        for row in rows:
            if not isinstance(row, dict):
                continue
            if source == "timeline" and row.get("run_id") != run_id:
                continue
            kind = row.get("event")
            terminal = kind in {
                "autonomous_run_error",
                "operator_stopped",
                "scheduler_stopped",
                "graph_complete_receipt_written",
            } or (kind == "poll_capacity_batch_completed" and row.get("fatal") is True)
            value = parse_timestamp(row.get("timestamp_utc")) if terminal else None
            if value is not None:
                candidates.append(value)
    return max(candidates) if candidates else None


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
    """Use this checkout unless the caller supplies explicit public roots."""
    state_root = Path(state).resolve() if state else ROOT
    if tasks:
        return Path(tasks).resolve(), state_root
    tasks_root = ROOT / "Tasks"
    if not tasks_root.is_dir():
        raise SystemExit(
            "Could not find a Tasks/ directory. Pass --tasks <checkout>/Tasks "
            "and --state <dir containing .task-review-agent>."
        )
    return tasks_root, state_root


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


def read_checkout_manifest(path: Path) -> dict[str, Any]:
    # Session-pool leases identify the exact manifest bytes, in addition to
    # the semantic manifest hash checked by the local viewer below.
    payload = path.read_bytes()
    return {"value": json.loads(payload.decode("utf-8")),
            "identity": "manifest-sha256:" + hashlib.sha256(payload).hexdigest()}


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
        "action_timestamp": None,
        "phase": None,
        "phase_timestamp": None,
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
        "model": None,
        "crew_run_id": None,
        "attempt": None,
        "blocked_reason": None,
        "transition_context_kind": None,
        "transition_context": None,
        "transition_context_timestamp": None,
        "ci_checks": None,
        "ci_observed_at": None,
        "stage_evidence": {},
    }
    action_started_elapsed: float | None = None
    previous_action: str | None = None
    current_stage: int | None = None

    def observe_stage(stage_number: int | None, observed_at: Any) -> None:
        nonlocal current_stage
        if stage_number not in PIPELINE_STAGE_LABELS or parse_timestamp(observed_at) is None:
            return
        if current_stage == stage_number:
            return
        if current_stage is not None:
            prior = summary["stage_evidence"].get(current_stage)
            if prior is not None and prior.get("completed_at") is None:
                prior["completed_at"] = observed_at
        summary["stage_evidence"].setdefault(
            stage_number, {"started_at": observed_at, "completed_at": None}
        )
        current_stage = stage_number

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
            summary["model"] = values.get("model") or summary["model"]
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
            phase = fields.get("phase")
            if isinstance(phase, str) and phase:
                summary["phase"] = phase
                summary["phase_timestamp"] = timestamp
                observe_stage(PHASE_STAGES.get(phase, (None, None))[0], timestamp)
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
                if kind == "pipeline_action_started":
                    # A successor action may retry the same action name, so
                    # clear on its durable start rather than only on a name
                    # change.
                    summary["transition_context_kind"] = None
                    summary["transition_context"] = None
                    summary["transition_context_timestamp"] = None
                if action != previous_action:
                    action_started_elapsed = (
                        0.0
                        if previous_action is None and kind == "pipeline_action_heartbeat"
                        else elapsed
                    )
                    previous_action = action
                    summary["action_timestamp"] = timestamp
                summary["action"] = action
                observe_stage(ACTION_STAGES.get(action), timestamp)
                # An action name alone is not CI evidence. The classifier combines
                # merge-closeout + this action + an exact PR, while a durable
                # checks_pending result remains sufficient on its own.
                summary["projection_state"] = "active"
                summary["projection_timestamp"] = timestamp
        if kind == "action_completed":
            action = fields.get("action")
            result_summary = fields.get("result_summary")
            result_status = (
                result_summary.get("status")
                if isinstance(result_summary, dict)
                else None
            )
            context = DURABLE_TRANSITION_CONTEXTS.get((action, result_status))
            if context is not None:
                summary["transition_context_kind"] = context["kind"]
                summary["transition_context"] = context["message"]
                summary["transition_context_timestamp"] = timestamp
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
            if current_stage is not None and parse_timestamp(timestamp) is not None:
                current = summary["stage_evidence"].get(current_stage)
                if current is not None and current.get("completed_at") is None:
                    current["completed_at"] = timestamp
        if kind == "action_completed" and fields.get("action") == "run_execution_crew":
            result_summary = fields.get("result_summary")
            crew_run_id = result_summary.get("run_id") if isinstance(result_summary, dict) else None
            if isinstance(crew_run_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", crew_run_id):
                summary["crew_run_id"] = crew_run_id
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
    def __init__(
        self,
        tasks_dir: Path,
        state_root: Path,
        *,
        display_task_ids: list[str] | None = None,
        run_dir: Path | None = None,
        local_run_root: Path | None = None,
        source_branch: str | None = None,
    ) -> None:
        self.tasks_dir = tasks_dir
        self.state_root = state_root
        self.local_run_root = local_run_root.resolve() if local_run_root is not None else None
        self.source_branch = source_branch
        self._local_observer = None
        self._local_observer_lock = threading.Lock()
        self._rejected_local_run: Path | None = None
        self._idle_contracts: "Snapshot | None" = None
        if display_task_ids is not None and any(
            not isinstance(task_id, str) or not TASK_FILE_RE.fullmatch(task_id + ".yaml")
            for task_id in display_task_ids
        ):
            raise ValueError("Display task IDs must use the canonical NSC task-ID format")
        # Launch configuration is independent of mutable scheduler/run artifacts.
        self.display_task_ids = tuple(sorted(set(display_task_ids))) if display_task_ids is not None else None
        self.run_dir = run_dir.resolve() if run_dir is not None else None
        self.outputs = state_root / ".task-review-agent" / "outputs"
        self.cache = FileCache()
        self._taskgraph_stamp: str | None = None
        self._taskgraph_cache: dict[str, dict[str, Any]] = {}

    def follow_newest_local_run(self) -> None:
        """In persistent mode, re-point at the newest run when it changes."""
        global LAUNCH_RECEIPT_PATH
        if LOCAL_RUNS_ROOT is None:
            return
        newest = newest_local_run(LOCAL_RUNS_ROOT)
        newest = newest.resolve() if newest is not None else None
        if newest == self.local_run_root or (newest is not None and newest == self._rejected_local_run):
            return
        self._rejected_local_run = None
        _set_observe_error(None)
        with self._local_observer_lock:
            self.local_run_root = newest
            self.tasks_dir = newest if newest is not None else LOCAL_RUNS_ROOT
            self.state_root = self.tasks_dir
            self._local_observer = None
        LAUNCH_RECEIPT_PATH = (
            (LAUNCH_RECEIPTS_ROOT / newest.name / "launch-receipt.json")
            if newest is not None and LAUNCH_RECEIPTS_ROOT is not None else None
        )

    def release_local_run(self) -> None:
        """Let go of the current run (its directory is about to be deleted)."""
        with self._local_observer_lock:
            self._local_observer = None
            self.local_run_root = None

    def reject_local_run(self, error: BaseException) -> None:
        """Stay idle instead of dying when the newest run cannot be observed.

        A run bound to an older commit (main moved after it failed), a dirty
        checkout, or a half-deleted directory used to end the persistent viewer
        at startup and kill the event stream on every poll. The page now shows
        the reason next to Start; a newer run replaces it.
        """
        root = self.local_run_root
        self.release_local_run()
        self._rejected_local_run = root
        _set_observe_error(f"{root.name}: {error}" if root is not None else str(error))

    def idle_tasks(self) -> list[dict]:
        """With no run to follow, draw the checkout's contracts, as the production viewer does when idle.

        The rows come from the run-less build over the checkout's Tasks folder
        (a state root without autonomous runs renders the contracts alone), so
        the operator can still enable and disable tasks before pressing Start.
        """
        if LAUNCH_SOURCE is None or LOCAL_RUNS_ROOT is None:
            return []
        tasks_dir = LAUNCH_SOURCE / "Tasks"
        if not tasks_dir.is_dir():
            return []
        try:
            if self._idle_contracts is None or self._idle_contracts.tasks_dir != tasks_dir:
                self._idle_contracts = Snapshot(tasks_dir, LOCAL_RUNS_ROOT)
            tasks = self._idle_contracts.build().get("tasks") or []
        except (OSError, ValueError, KeyError):
            return []
        # "Run scope only" means what Start would run: the operator's enabled set,
        # else the launcher's default gauntlet scope, plus their generated children.
        roots = set(ENABLED_TASK_IDS) or set(LAUNCH_TASK_IDS) or set(launcher_default_scope(LAUNCH_SOURCE))
        scope = roots | expand_decomposition_descendants(self._idle_contracts.load_contracts(), roots) if roots else set()
        for task in tasks:
            task["in_scope"] = not roots or task.get("id") in scope
            # No run exists, so no worker checkout exists yet either.
            task["checkout_path"] = None
            task["checkout_exists"] = False
        return tasks

    def idle_local_state(self) -> dict:
        """What the page shows while no run exists yet under the runs root."""
        return {
            "generated_at": utc_now(),
            "tasks_dir": str(self.tasks_dir),
            "state_root": str(self.state_root),
            "run": {
                "dir": str(LOCAL_RUNS_ROOT) if LOCAL_RUNS_ROOT is not None else None,
                "run_id": None, "mode": ("production" if RUNS_MODE == "production" else "local_rehearsal"),
                "marker": ("PRODUCTION" if RUNS_MODE == "production" else "LOCAL REHEARSAL"),
                "repository": LAUNCH_REPOSITORY, "source_commit": None, "source_tree": None,
                "source_repository": str(LAUNCH_SOURCE) if LAUNCH_SOURCE is not None else None,
                "source_branch": LAUNCH_SOURCE_BRANCH, "source_clean": None,
                "local_runtime_patch_sha256": None, "provider_profile": None,
                "targets": [], "excluded": [], "max_capacity": None, "progress": None,
                "status": "waiting_for_run", "complete": False,
                "stop_requested": False,
                "stop": {"requested": False}, "operator": idle_operator_state(),
            },
            "scheduler": {"active": [], "blocked_reasons": []},
            "events": [],
            "tasks": self.idle_tasks(),
            # The page validates this record strictly; an idle viewer still needs one.
            "pipeline_activity": {
                "mode": "local_rehearsal",
                "headline": "Waiting for a run",
                "description": ("No production run exists under this checkout yet. Press Start run to launch one."
                                if RUNS_MODE == "production" else
                                "No run exists under this checkout yet. Press Start run to launch one in place."),
                "provider_profile": LAUNCH_PROFILE or "unknown", "provider": "none", "provider_source": "none",
                "model": "none", "model_source": "none", "call_status": "idle", "liveness": "no run",
                "terminal": False, "provider_call_open": False,
                "stage_elapsed_seconds": None, "run_elapsed_seconds": None, "last_event_age_seconds": None,
                "stale_after_seconds": 0,
                "counters": {key: None for key in ("active_workers", "capacity", "eligible_or_queued", "dependency_blocked",
                                                   "completed", "architect_calls_completed", "worker_launches", "wakeups",
                                                   "awaiting_worker", "local_review_ready")},
                "candidate_count": None, "candidates": [], "recent_activity": [],
            },
            "human_actions": [],
        }
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
        resume_phases: dict[str, dict[str, Any]] = {}
        inherited_workflow: dict[str, dict[str, Any]] = {}
        queued: list[str] = []
        gate_timestamp = None
        for event in events:
            if not isinstance(event, dict):
                continue
            task_id = event.get("task_id")
            kind = event.get("event")
            timestamp = event.get("timestamp_utc")
            if (
                isinstance(task_id, str)
                and kind == "integration_gate_resume_admitted"
                and isinstance(event.get("resume_phase"), str)
            ):
                resume_phases[task_id] = {
                    "phase": event["resume_phase"],
                    "timestamp": timestamp,
                }
            if isinstance(task_id, str) and kind == "worker_launched":
                phase = event.get("resume_phase")
                if not isinstance(phase, str):
                    phase = (resume_phases.get(task_id) or {}).get("phase")
                if not isinstance(phase, str) and event.get("work_type") == "decomposition":
                    phase = "decomposition"
                lifecycle[task_id] = {
                    "active": True,
                    "timestamp": timestamp,
                    "worker_id": event.get("worker_id"),
                    "run_id": event.get("run_id"),
                    "work_type": event.get("work_type"),
                    "phase": phase,
                    "checkout_path": event.get("checkout_path"),
                    "argv": event.get("argv"),
                }
            elif isinstance(task_id, str) and kind in ("worker_finished", "worker_returned_to_pool"):
                lifecycle[task_id] = {
                    "active": False,
                    "timestamp": timestamp,
                    "run_id": event.get("run_id"),
                }
            # A payload describing a hoped-for transition is not proof that the
            # managed Issue changed.  Only the durable resume outcome and the
            # explicit Issue-observation event are transition evidence.
            transition = (
                event.get("workflow_transition")
                if kind in WORKFLOW_TRANSITION_EVIDENCE_EVENTS
                else None
            )
            if not isinstance(transition, dict) and kind in WORKFLOW_TRANSITION_EVIDENCE_EVENTS:
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
            if kind == "integration_reservations_observed":
                # Each observation is a complete snapshot.  Replacing rather
                # than accumulating makes disappearance authoritative and
                # prevents stale earlier polls from repainting a task.
                inherited_workflow = {}
                values = event.get("reservations")
                if not isinstance(values, list) or parse_timestamp(timestamp) is None:
                    continue
                active_task_ids = {
                    value.get("task_id")
                    for value in values
                    if isinstance(value, dict)
                    and value.get("local_active") is True
                    and isinstance(value.get("task_id"), str)
                }
                for value in values:
                    if not isinstance(value, dict):
                        continue
                    reservation_task_id = value.get("task_id")
                    phase = value.get("phase")
                    if (
                        not isinstance(reservation_task_id, str)
                        or TASK_FILE_RE.fullmatch(reservation_task_id + ".yaml") is None
                        or reservation_task_id in active_task_ids
                        or value.get("workflow_state") != "human_action_required"
                        or value.get("local_active") is not False
                        or value.get("pending_transition") is not None
                        or value.get("evidence_type")
                        not in ISSUE_DERIVED_RESERVATION_EVIDENCE_TYPES
                        or not isinstance(phase, str)
                        or phase not in PHASE_STAGES
                    ):
                        continue
                    inherited_workflow[reservation_task_id] = {
                        "state": "human_action_required",
                        "phase": phase,
                        "timestamp": timestamp,
                        "source": "current-run integration reservation",
                    }
        return {
            "lifecycle": lifecycle,
            "transitions": transitions,
            "inherited_workflow": inherited_workflow,
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
            recorded_receipts = (
                record["usage_receipts"] if "usage_receipts" in record
                else self.cache.get(record["progress_path"], read_usage_receipts) or []
            )
            for receipt in recorded_receipts:
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
    def _exact_argv_option(argv: Any, name: str) -> str | None:
        if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
            return None
        positions = [index for index, item in enumerate(argv) if item == name]
        if len(positions) != 1 or positions[0] + 1 >= len(argv):
            return None
        value = argv[positions[0] + 1]
        return value if value and not value.startswith("--") else None

    def bound_decomposition_run(
        self, *, task_id: str, lifecycle: dict[str, Any] | None
    ) -> Path | None:
        """Resolve only the production scheduler's exact decomposition output."""

        if not lifecycle or lifecycle.get("active") is not True:
            return None
        run_id = lifecycle.get("run_id")
        argv = lifecycle.get("argv")
        if (
            lifecycle.get("work_type") != "decomposition"
            or not isinstance(run_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id) is None
            or self._exact_argv_option(argv, "--task-id") != task_id
            or self._exact_argv_option(argv, "--run-id") != run_id
        ):
            return None
        profile = os.environ.get("USERPROFILE")
        if not profile:
            return None
        source_text = self._exact_argv_option(argv, "--source")
        state_text = self._exact_argv_option(argv, "--checkout-root")
        scheduler_output_text = self._exact_argv_option(argv, "--scheduler-output-root")
        output_text = self._exact_argv_option(argv, "--output-root")
        if None in (source_text, state_text, scheduler_output_text, output_text):
            return None
        try:
            source = self.tasks_dir.parent.resolve()
            state_root = self.state_root.resolve()
            expected_script = (
                source / "Pipeline" / "TaskReviewAgent" / "host_decomposition_launcher.py"
            ).resolve()
            script_values = [
                Path(item).resolve()
                for item in argv
                if isinstance(item, str) and item.casefold().endswith("host_decomposition_launcher.py")
            ]
            selected_source = Path(source_text).resolve()
            selected_state = Path(state_text).resolve()
            selected_scheduler_output = Path(scheduler_output_text).resolve()
            selected_output = Path(output_text).resolve()
            expected_output = (
                Path(profile).resolve()
                / "Downloads"
                / "NoSafeCircleOutput"
                / task_id
            ).resolve()
        except (OSError, RuntimeError):
            return None
        if (
            script_values != [expected_script]
            or selected_source != source
            or selected_state != state_root
            or selected_scheduler_output != self.outputs.resolve()
            or selected_output != expected_output
        ):
            return None
        selected = selected_output / run_id
        try:
            resolved = selected.resolve()
        except (OSError, RuntimeError):
            return None
        return resolved if resolved.parent == selected_output and resolved.is_dir() else None

    def decomposition_agents(
        self,
        *,
        task_id: str,
        lifecycle: dict[str, Any] | None,
        active: bool,
        now: float,
        stop_at: float | None = None,
    ) -> list[dict[str, Any]]:
        run_dir = self.bound_decomposition_run(task_id=task_id, lifecycle=lifecycle)
        if run_dir is None:
            return []
        rows = self.cache.get(run_dir / "progress.jsonl", read_jsonl)
        if not isinstance(rows, list):
            return []
        states: dict[int, dict[str, Any]] = {}
        order: list[int] = []
        run_terminal = False
        for row in rows:
            if (
                not isinstance(row, dict)
                or row.get("task_id") != task_id
                or row.get("run_id") != run_dir.name
            ):
                continue
            kind = row.get("event")
            if not isinstance(kind, str):
                continue
            if kind == "run_completed":
                run_terminal = True
            if kind.startswith("round_provider_"):
                round_number = row.get("round_number")
                role = row.get("round_role")
                provider = row.get("round_provider")
            elif kind.startswith("provider_"):
                round_number = 1
                role = "task_decomposer"
                provider = row.get("provider")
            else:
                continue
            if (
                type(round_number) is not int
                or round_number < 1
                or role not in {"task_decomposer", "decomposition_reviewer"}
            ):
                continue
            if round_number not in order:
                order.append(round_number)
            item = states.setdefault(
                round_number,
                {
                    "role": role,
                    "attempt": round_number,
                    "started_at": None,
                    "completed_at": None,
                    "receipt_duration": None,
                    "status": "queued",
                    "provider": provider if isinstance(provider, str) else None,
                },
            )
            if kind.endswith("started"):
                item["started_at"] = row.get("timestamp_utc")
                item["status"] = "recorded_incomplete"
            elif kind.endswith("completed"):
                item["completed_at"] = row.get("timestamp_utc")
                item["receipt_duration"] = positive_number(row.get("duration_seconds"))
                item["status"] = "failed" if row.get("status") == "failed" else "completed"

        agents = []
        for round_number in order:
            item = states[round_number]
            start = parse_timestamp(item.get("started_at"))
            end = parse_timestamp(item.get("completed_at"))
            if item["status"] == "recorded_incomplete" and active and not run_terminal:
                item["status"] = "running"
                end = now
            elif item["status"] == "recorded_incomplete" and stop_at is not None:
                end = stop_at
            elapsed = item.get("receipt_duration")
            if elapsed is None and start is not None and end is not None and end >= start:
                elapsed = end - start
            round_result = self.cache.get(
                run_dir / "rounds" / f"{round_number:02d}" / "round_result.json", read_json
            )
            if not isinstance(round_result, dict) or round_result.get("role") != item["role"]:
                round_result = {}
            result_reference = round_result.get("agent_runtime_result_path")
            runtime_result = {}
            if (
                isinstance(result_reference, str)
                and ".." not in Path(result_reference).parts
                and result_reference.endswith("/result.json")
            ):
                candidate = (run_dir / result_reference).resolve()
                if candidate.is_relative_to(run_dir):
                    value = self.cache.get(candidate, read_json)
                    runtime_result = value if isinstance(value, dict) else {}
            usage = runtime_result.get("usage") if isinstance(runtime_result.get("usage"), dict) else {}
            agents.append(
                {
                    "role": item["role"],
                    "label": AGENT_ROLE_LABELS[item["role"]],
                    "attempt": round_number,
                    "status": item["status"],
                    "action": AGENT_ROLE_ACTIONS[item["role"]],
                    "duration_seconds": elapsed,
                    "provider": round_result.get("actual_provider") or item.get("provider"),
                    "model": round_result.get("actual_model") or runtime_result.get("model"),
                    "total_tokens": usage.get("total_tokens") if type(usage.get("total_tokens")) is int else None,
                    "cost_usd": positive_number(usage.get("estimated_cost_usd")),
                    "source": f"Pipeline/TaskDecomposition output round {round_number}",
                }
            )
        return agents

    def execution_crew_agents(
        self,
        *,
        task_id: str,
        lifecycle: dict[str, Any] | None,
        worker: dict[str, Any] | None,
        active: bool,
        now: float,
        stop_at: float | None = None,
    ) -> list[dict[str, Any]]:
        """Read one uniquely bound crew run; artifacts never prove liveness alone."""

        if not lifecycle or not isinstance(lifecycle.get("checkout_path"), str):
            return []
        try:
            checkout = Path(lifecycle["checkout_path"]).resolve()
            state_root = self.state_root.resolve()
        except (OSError, RuntimeError):
            return []
        if checkout.name != task_id or not checkout.is_relative_to(state_root):
            return []
        outputs = checkout / "Pipeline" / "ExecutionCrew" / "outputs"
        if not outputs.is_dir():
            return []

        run_id = worker.get("crew_run_id") if worker else None
        selected: tuple[Path, list[dict[str, Any]]] | None = None
        if isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id):
            run_dir = outputs / run_id
            rows = self.cache.get(run_dir / "progress.jsonl", read_jsonl)
            if isinstance(rows, list):
                selected = (run_dir, rows)
        elif active and worker and worker.get("action") == "run_execution_crew":
            action_started = parse_timestamp(worker.get("action_timestamp"))
            candidates = []
            try:
                run_dirs = list(outputs.iterdir())
            except OSError:
                run_dirs = []
            for run_dir in run_dirs:
                if not run_dir.is_dir() or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_dir.name) is None:
                    continue
                rows = self.cache.get(run_dir / "progress.jsonl", read_jsonl)
                if not isinstance(rows, list) or not rows:
                    continue
                start = next((row for row in rows if row.get("event") == "run_started"), None)
                started_at = parse_timestamp(start.get("timestamp_utc")) if isinstance(start, dict) else None
                if (
                    not isinstance(start, dict)
                    or start.get("task_id") != task_id
                    or start.get("run_id") != run_dir.name
                    or started_at is None
                    or action_started is None
                    or started_at < action_started
                ):
                    continue
                candidates.append((run_dir, rows))
            if len(candidates) == 1:
                selected = candidates[0]
        if selected is None:
            return []

        run_dir, rows = selected
        return self.crew_agents_from_rows(task_id=task_id, run_dir=run_dir, rows=rows,
                                         active=active, now=now, stop_at=stop_at)

    def crew_agents_from_rows(self, *, task_id: str, run_dir: Path, rows: list[dict[str, Any]],
                             active: bool, now: float, stop_at: float | None = None) -> list[dict[str, Any]]:
        run_terminal = any(row.get("event") in {"run_completed", "run_failed"} for row in rows)
        required: list[str] = []
        role_states: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("task_id") != task_id or row.get("run_id") != run_dir.name:
                continue
            kind = row.get("event")
            if kind == "run_started" and isinstance(row.get("required_roles"), list):
                required = [role for role in row["required_roles"] if isinstance(role, str)]
                continue
            role = row.get("role")
            if not isinstance(role, str) or re.fullmatch(r"[a-z][a-z0-9_]*", role) is None:
                continue
            attempt = row.get("attempt") if type(row.get("attempt")) is int and row.get("attempt") > 0 else 1
            key = f"{role}:{attempt}"
            if key not in order:
                order.append(key)
            item = role_states.setdefault(
                key,
                {
                    "role": role,
                    "attempt": attempt,
                    "started_at": None,
                    "completed_at": None,
                    "status": "queued",
                    "provider": row.get("provider") if isinstance(row.get("provider"), str) else None,
                },
            )
            if kind == "role_started":
                item["started_at"] = row.get("timestamp_utc")
                item["status"] = "recorded_incomplete"
            elif kind == "role_completed":
                item["completed_at"] = row.get("timestamp_utc")
                item["status"] = "failed" if row.get("status") == "failed" else "completed"
            elif kind == "role_skipped":
                item["completed_at"] = row.get("timestamp_utc")
                item["status"] = "omitted"

        for role in required:
            if not any(item["role"] == role for item in role_states.values()):
                key = f"{role}:1"
                order.append(key)
                role_states[key] = {
                    "role": role,
                    "attempt": 1,
                    "started_at": None,
                    "completed_at": None,
                    "status": "queued",
                    "provider": None,
                }

        agents = []
        for key in order:
            item = role_states[key]
            start = parse_timestamp(item.get("started_at"))
            end = parse_timestamp(item.get("completed_at"))
            if item["status"] == "recorded_incomplete" and active and not run_terminal:
                item["status"] = "running"
                end = now
            elif item["status"] == "recorded_incomplete" and stop_at is not None:
                end = stop_at
            duration = end - start if start is not None and end is not None and end >= start else None
            role_path = run_dir / "role_results" / f"{item['role']}_{item['attempt']}.json"
            role_result = (self.cache.get(role_path, read_json)
                           if role_path.resolve().is_relative_to(run_dir.resolve()) else {})
            role_result = role_result if isinstance(role_result, dict) else {}
            if role_result.get("role") != item["role"] or role_result.get("attempt") != item["attempt"]:
                role_result = {}
            usage = role_result.get("usage") if isinstance(role_result.get("usage"), dict) else {}
            agents.append(
                {
                    "role": item["role"],
                    "label": AGENT_ROLE_LABELS.get(item["role"], item["role"].replace("_", " ").title()),
                    "attempt": item["attempt"],
                    "status": item["status"],
                    "duration_seconds": duration,
                    "provider": role_result.get("provider") or item.get("provider"),
                    "model": role_result.get("model"),
                    "total_tokens": usage.get("total_tokens") if type(usage.get("total_tokens")) is int else None,
                    "cost_usd": positive_number(usage.get("estimated_cost_usd")),
                    "source": (f"crew-output/{task_id}/{run_dir.name}" if self.local_run_root is not None
                               else f"Pipeline/ExecutionCrew/outputs/{run_dir.name}"),
                }
            )
        return agents

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
        run_terminal: bool = False,
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
        exact_active_launch = bool(
            not run_terminal
            and lifecycle
            and lifecycle.get("active") is True
            and isinstance(lifecycle.get("run_id"), str)
            and (worker is None or worker.get("run_id") == lifecycle.get("run_id"))
        )
        if exact_active_launch:
            active = True
        elif lifecycle and newer(lifecycle.get("timestamp"), worker.get("last_timestamp") if worker else None):
            active = lifecycle.get("active") is True
        workflow_newer = bool(transition and newer(transition.get("timestamp"), projection_time))
        launch_newer = exact_active_launch or bool(
            not run_terminal
            and lifecycle
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
        if run_terminal:
            active = False
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
        ):
            return ("integration_queued" if task_id in queued else "delivery_ready"), False
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
        if state == "aggregate":
            complete = progress.get("children_complete") or 0
            total = progress.get("children_total") or 0
            counts = progress.get("children_by_state") or {}
            statuses = []
            for child_state, label in (
                ("active", "working"),
                ("checks_pending", "in CI"),
                ("integration_queued", "waiting for merge gate"),
                ("delivery_ready", "ready to continue"),
                ("human_action", "need verification"),
                ("local_review_ready", "local review ready"),
                ("blocked", "blocked"),
                ("failed", "failed"),
                ("ready", "unstarted"),
                ("pending", "dependencies unmet"),
            ):
                count = counts.get(child_state, 0)
                if count:
                    statuses.append(f"{count} {label}")
            first = (
                ("DECOMPOSED · CHILDREN LOCALLY ACCEPTED"
                 if progress.get("local_completion_only") else "DECOMPOSED · CHILDREN DELIVERED")
                if total and complete == total
                else "DECOMPOSED · CHILDREN IN PROGRESS"
            )
            second = (f"{complete}/{total} children locally accepted"
                      if progress.get("local_completion_only") else f"{complete}/{total} children complete")
            if statuses:
                second += " · " + " · ".join(statuses)
            child_tokens = progress.get("children_recorded_total_tokens") or 0
            third = (
                f"{child_tokens:,} child tokens recorded"
                if child_tokens
                else "Child token usage unavailable"
            )
            return [first, second, third]
        if state == "decomposition_ready":
            return ["DECOMPOSITION AVAILABLE"]
        if state == "delivery_ready":
            return ["VERIFIED · READY TO CONTINUE"]
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
            first = "WAITING FOR MERGE GATE"
            if progress.get("queue_position") is not None:
                first += f" · queue position {progress['queue_position']}"
            return [first, f"Verified {duration_text(progress.get('queue_wait_seconds'))} ago"]
        context_kind = progress.get("transition_context_kind")
        if state == "human_action" and context_kind == "candidate_revalidation_required":
            return [
                "REVALIDATION REQUIRED",
                "CURRENT MAIN INTEGRATED INTO CANDIDATE",
                "Waiting for revalidation review",
            ]
        if (
            state == "human_action"
            and progress.get("inherited_workflow_state") == "human_action_required"
        ):
            phase = progress.get("phase")
            phase_label = (
                phase.replace("_", " ").upper() if isinstance(phase, str) else None
            )
            return [
                "HUMAN ACTION REQUIRED",
                phase_label or "Workflow phase unavailable",
            ]
        if state != "active":
            return None
        context_lines = (
            ["PUBLISHED TO MAIN", "Post-merge verification pending"]
            if context_kind == "published_post_merge_verification_pending"
            else []
        )
        if task.get("active_work_type") == "decomposition":
            context_lines.insert(0, "TASK WORKING (DECOMPOSITION)")
        stage_rows = progress.get("pipeline_stages") or []
        stage_parts = []
        for item in stage_rows:
            marker = "✓" if item.get("status") == "complete" else ""
            shown_label = item.get("display_label") or item["label"]
            label = f"[{shown_label}]" if item.get("status") == "active" else shown_label
            elapsed = duration_text(item.get("elapsed_seconds"))
            suffix = (
                f" {elapsed}"
                if elapsed != "unavailable"
                else " · elapsed unavailable"
                if item.get("status") == "active"
                else ""
            )
            stage_parts.append(f"{marker}{label}{suffix}")
        stage_lines = [" · ".join(stage_parts[:3]), " · ".join(stage_parts[3:])] if stage_parts else ["PHASE UNAVAILABLE"]
        agent_lines = []
        for agent in progress.get("agents") or []:
            marker = {
                "running": "",
                "completed": "✓",
                "failed": "!",
                "omitted": "○",
                "queued": "…",
            }.get(agent.get("status"), "?")
            elapsed = duration_text(agent.get("duration_seconds"))
            timing = f" · {elapsed}" if elapsed != "unavailable" else " · duration unavailable"
            action = agent.get("action")
            activity = f" · {action}" if isinstance(action, str) and action else ""
            turn = f" · turn {worker['turn']}" if agent.get("role") == "task_supervisor" and worker.get("turn") else ""
            agent_lines.append(
                f"{marker} {agent['label']}{activity} · "
                f"{str(agent.get('status') or 'unavailable').replace('_', ' ')}{timing}{turn}"
            )
        if not agent_lines:
            action = ACTION_LABELS.get(
                worker.get("action"),
                str(worker.get("action") or "Current phase unavailable").replace("_", " ").title(),
            )
            agent_lines = [action]
        if worker.get("phase") == "decomposition" and progress.get("children_total") is not None:
            agent_lines.append(f"{progress['children_complete']}/{progress['children_total']} children complete")
        return [*context_lines, *stage_lines, *agent_lines]

    def local_snapshot(self) -> dict[str, Any]:
        """Read the selected backend through its identity/hash-chain validator."""
        module_dir = str(HERE.parents[2])
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        from Pipeline.TaskReviewAgent.local_rehearsal import LocalRunObserver

        # HTTP and SSE readers share one verified manifest. A failed admission
        # never publishes a context, and a later rewrite never replaces it.
        with self._local_observer_lock:
            if self._local_observer is None:
                self._local_observer = LocalRunObserver(self.local_run_root)
            value = self._local_observer.snapshot()
        if value.get("execution_mode") != "local_rehearsal":
            raise ValueError("Selected run is not a local rehearsal")
        return value

    def bound_local_worker(self, local: dict[str, Any], task_id: str, record: dict[str, Any]):
        root, worker_run = self.local_run_root, record.get("worker_run_id")
        if (root is None or record.get("run_id") != local.get("run_id") or not record.get("worker_id")
                or not isinstance(worker_run, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", worker_run) is None
                or TASK_FILE_RE.fullmatch(task_id + ".yaml") is None):
            return None
        directory = root / "checkouts" / ".task-review-agent" / "outputs" / task_id / worker_run
        paths = [directory / "run.json", directory / "progress.jsonl"]
        try:
            if any(not path.resolve().is_relative_to(root) for path in paths):
                return None
            run, rows = self.cache.get(paths[0], read_json), self.cache.get(paths[1], read_jsonl)
            identity = {"run_id": worker_run, "task_id": task_id, "worker_id": record["worker_id"]}
            if not isinstance(run, dict) or any(run.get(key) != value for key, value in identity.items()):
                return None
            rows = [row for row in (rows or []) if isinstance(row, dict)
                    and all(row.get(key) == value for key, value in identity.items())]
            return {"rows": rows, "watched": [*paths, directory / "run_result.json"]}
        except (OSError, RuntimeError, ValueError):
            return None

    @staticmethod
    def local_worker_step(rows, now):
        steps = {
            "pipeline_action": (None, None),
            "state_observation": ("workflow_state", "Reading workflow state"),
            "routing_observation": ("routing", "Reading task routing"),
            "routing": ("routing", "Choosing task routing"),
            "codex_supervisor": ("supervisor", "Task supervisor choosing next step"),
        }
        current = None
        for row in rows:
            event = row.get("event", "")
            for prefix, (phase, label) in steps.items():
                if event == prefix + "_started":
                    fields = row.get("fields") or {}
                    action = fields.get("action") if prefix == "pipeline_action" else phase
                    if prefix == "pipeline_action":
                        label = {"prepare_task_checkout": "Preparing checkout", "run_execution_crew": "Starting execution crew",
                            "validate_execution_scope": "Checking task files", "acquire_agent_lease": "Acquiring task lease"}.get(
                                action, ACTION_LABELS.get(action, str(action or "Task step").replace("_", " ").capitalize()))
                    current = {"prefix": prefix, "phase": action, "label": label,
                               "started": parse_timestamp(row.get("timestamp_utc")), "ended": None}
                elif current and current["prefix"] == prefix and event in {prefix + "_completed", prefix + "_failed"}:
                    current["ended"] = parse_timestamp(row.get("timestamp_utc"))
        if current is None or current["started"] is None:
            return None
        current["elapsed"] = max(0.0, (current["ended"] or now) - current["started"])
        if current["ended"] is not None:
            current["label"] += " · finished"
        return current

    def bound_local_crew(self, local: dict[str, Any], task_id: str, record: dict[str, Any]):
        """Bind only this local task's current worker, checkout and pooled crew.

        Paths come from the validated run namespace. The current worker action,
        hashed checkout manifest and exact source/slot lease jointly distinguish
        this crew from stale runs and from workers admitted on another commit.
        """
        from Pipeline.TaskReviewAgent.contracts import semantic_sha256
        root = self.local_run_root
        worker_run = record.get("worker_run_id")
        if (root is None or record.get("run_id") != local.get("run_id")
                or not record.get("worker_id") or not isinstance(worker_run, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", worker_run) is None
                or TASK_FILE_RE.fullmatch(task_id + ".yaml") is None):
            return None
        def read(path, loader=read_json):
            try:
                if not path.resolve().is_relative_to(root):
                    return None
                return self.cache.get(path, loader)
            except (OSError, RuntimeError):
                return None
        checkout = root / "checkouts" / task_id
        if Path(record.get("checkout_path") or "").resolve() != checkout.resolve():
            return None
        state_root = root / "checkouts" / ".task-review-agent"
        manifest_path = state_root / (task_id + ".json")
        manifest_read = read(manifest_path, read_checkout_manifest)
        manifest = manifest_read.get("value") if isinstance(manifest_read, dict) else None
        if not isinstance(manifest, dict):
            return None
        identity = {"task_id": task_id, "local_run_id": local["run_id"],
                    "worker_id": record["worker_id"], "lease_id": record.get("lease_id"),
                    "source_head": record.get("source_commit"), "source_tree": record.get("source_tree"),
                    "task_contract_sha256": record.get("task_contract_sha256")}
        if (any(manifest.get(key) != value for key, value in identity.items())
                or Path(manifest.get("checkout_path") or "").resolve() != checkout.resolve()
                or semantic_sha256({key: value for key, value in manifest.items() if key != "manifest_sha256"})
                    != manifest.get("manifest_sha256")):
            return None
        worker_dir = state_root / "outputs" / task_id / worker_run
        worker = self.bound_local_worker(local, task_id, record)
        if worker is None:
            return None
        rows = worker["rows"]
        actions = [row for row in rows if row.get("run_id") == worker_run and row.get("task_id") == task_id
                   and row.get("worker_id") == record["worker_id"] and row.get("event") == "pipeline_action_started"
                   and (row.get("fields") or {}).get("action") == "run_execution_crew"]
        action_start = parse_timestamp(actions[-1].get("timestamp_utc")) if actions else None
        if action_start is None:
            return None
        outputs = root / "crew-output" / task_id
        try:
            if not outputs.resolve().is_relative_to(root):
                return None
            candidates = []
            for crew in outputs.iterdir():
                if not crew.is_dir() or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", crew.name) is None:
                    continue
                progress_path = crew / "progress.jsonl"
                progress = read(progress_path, read_jsonl)
                if not isinstance(progress, list) or not progress:
                    continue
                progress = [row for row in progress if isinstance(row, dict)
                            and row.get("task_id") == task_id and row.get("run_id") == crew.name]
                start = next((row for row in progress if row.get("event") == "run_started"), {})
                started = parse_timestamp(start.get("timestamp_utc"))
                if (start.get("task_id") != task_id or start.get("run_id") != crew.name
                        or started is None or started < action_start):
                    continue
                matches = []
                for lease_path in (state_root / "session-pools").glob(f"*/*/assignments/{crew.name}.leases.json"):
                    assignment = read(lease_path)
                    leases = assignment.get("leases") if isinstance(assignment, dict) else None
                    if not isinstance(leases, dict) or not leases or assignment.get("run_id") != crew.name:
                        continue
                    expected = {"task_id": task_id, "worker_slot_id": record["worker_id"],
                                "worker_run_id": crew.name, "source_commit": record["source_commit"],
                                "checkout_identity": manifest_read["identity"]}
                    if all(isinstance(lease, dict) and all(lease.get(key) == value for key, value in expected.items())
                           for lease in leases.values()):
                        matches.append(lease_path)
                if len(matches) != 1:
                    continue
                watched = [manifest_path, worker_dir / "run.json", worker_dir / "progress.jsonl",
                           progress_path, matches[0], crew / "crew_result.json", *crew.glob("role_results/*.json")]
                watched = [path for path in watched if path.resolve().is_relative_to(root)]
                candidates.append({"run_dir": crew, "rows": progress, "watched": watched})
            return candidates[0] if len(candidates) == 1 else None
        except (OSError, RuntimeError):
            return None

    def bound_local_launch(self, local: dict[str, Any], task_id: str, record: dict[str, Any]):
        """Project recorded process startup before its asynchronous lease write.

        An architect admission alone is not a launch. Require the exact local
        scheduler manifest, task/worker/run, positive PID and owned result path.
        This reports durable startup evidence, not current process liveness.
        """
        root = self.local_run_root
        worker_run = record.get("worker_run_id")
        if (root is None or record.get("state") not in {"available", "architect_admission", "agent_ready"}
                or record.get("run_id") != local.get("run_id") or not record.get("worker_id")
                or not isinstance(worker_run, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", worker_run) is None
                or TASK_FILE_RE.fullmatch(task_id + ".yaml") is None):
            return None
        manifest_path, events_path = root / "autonomous-manifest.json", root / "scheduler-events.jsonl"
        try:
            if any(not path.resolve().is_relative_to(root) for path in (manifest_path, events_path)):
                return None
            manifest = self.cache.get(manifest_path, read_json)
            if (not isinstance(manifest, dict) or manifest.get("run_id") != local["run_id"]
                    or Path(manifest.get("local_rehearsal_root") or "").resolve() != root
                    or Path(manifest.get("source_repository") or "").resolve()
                        != Path(local.get("source_repository") or "").resolve()):
                return None
            events = self.cache.get(events_path, read_jsonl) or []
            expected_checkout = root / "checkouts" / task_id
            expected_result = root / "checkouts" / ".task-review-agent" / "outputs" / task_id / worker_run / "run_result.json"
            launch = None
            for event in events:
                if event.get("task_id") != task_id or event.get("worker_id") != record["worker_id"]:
                    continue
                if (event.get("event") in {"worker_failed", "worker_returned_to_pool", "worker_completed", "worker_reaped"}
                        and event.get("run_id") in {None, worker_run}):
                    launch = None
                if (event.get("event") == "worker_launched" and event.get("run_id") == worker_run
                        and type(event.get("pid")) is int and event["pid"] > 0
                        and parse_timestamp(event.get("timestamp_utc")) is not None
                        and Path(event.get("checkout_path") or "").resolve() == expected_checkout.resolve()
                        and Path(event.get("result_artifact_path") or "").resolve() == expected_result.resolve()):
                    launch = event
            # A finished result may reach disk before the scheduler return event.
            if expected_result.exists():
                return None
            return launch
        except (OSError, RuntimeError, ValueError):
            return None

    def local_decomposition_stage(self, local, task_id, record):
        """Display machine-owned work only from the run's durable exact binding."""
        if (local.get("local_decomposition_apply") is not True
                or record.get("state") != "human_action_required"
                or record.get("worker_id") is not None or record.get("lease_id") is not None
                or record.get("blocked_reason") or record.get("local_decomposition_refusal")):
            return None
        stage = record.get("pipeline_stage")
        if stage == "decomposition_review_pending":
            evidence = record.get("local_decomposition_pending")
            label = "Checking decomposition for automatic application"
        elif stage == "decomposition_apply_authorized":
            evidence = record.get("local_decomposition_authorization")
            label = "Applying decomposition"
        elif stage == "human_action_required":
            # The worker publishes the reviewed decomposition handoff before its
            # result file and before the controller records the host review. Bind
            # that exact durable workflow state so the machine-owned interval is
            # never presented as a request for human action.
            workflow = (local.get("decomposition_handoffs") or {}).get(task_id)
            if not isinstance(workflow, dict):
                return None
            if (workflow.get("state") != "human_action_required"
                    or workflow.get("phase") != "decomposition_apply_authorization"
                    or workflow.get("current_actor") != "human" or workflow.get("human_result") is not None
                    or workflow.get("head_commit") != record.get("source_commit")
                    or workflow.get("task_contract_sha256") != record.get("task_contract_sha256")
                    or (record.get("route") or {}).get("work_type") != "decomposition"):
                # record.last_event_id is the local journal hash written by
                # _save; the Issue workflow's last_event_id lives in another id
                # space, so it is deliberately not compared here.
                return None
            return "Checking decomposition for automatic application"
        else:
            return None
        if not isinstance(evidence, dict) or any(evidence.get(key) != expected for key, expected in (
            ("run_id", local["run_id"]), ("task_id", task_id),
            ("source_commit", record.get("source_commit")), ("source_tree", record.get("source_tree")),
            ("task_contract_sha256", record.get("task_contract_sha256")), ("human_result", None),
        )) or not evidence.get("handoff_event_id") or not evidence.get("graph_delta_plan_id"):
            return None
        if stage == "decomposition_review_pending":
            if not record.get("worker_run_id") or evidence.get("worker_run_id") != record["worker_run_id"]:
                return None
        elif (evidence.get("authority") != "local_rehearsal_only"
                or evidence.get("basis") != "explicit_run_setting:local_decomposition_apply"):
            return None
        return label

    @staticmethod
    def local_candidate_is_accepted(local, task_id, record):
        """Project local acceptance only from the validated receipt and lineage.

        A queued candidate, stage label, or successful crew result alone does
        not prove that its exact changes reached this run's local Source.
        """
        if (local.get("local_candidate_auto_accept") is not True
                or record.get("run_id") != local.get("run_id")
                or record.get("task_id") != task_id
                or record.get("state") != "local_review_ready"
                or record.get("pipeline_stage") != "local_candidate_accepted"
                or record.get("automated_acceptance_authority") != "local_machine_policy"
                or record.get("human_result") is not None
                or record.get("worker_id") is not None or record.get("lease_id") is not None
                or not record.get("accepted_worker_id") or record.get("blocked_reason")):
            return False
        result = record.get("result")
        if (not isinstance(result, dict)
                or result.get("local_run_id") != local.get("run_id")
                or result.get("task_id") != task_id
                or result.get("authority") != "local_rehearsal_only"
                or result.get("crew_status") != "review_ready"
                or type(result.get("returncode")) is not int or result["returncode"] != 0
                or result.get("rejection_reasons")):
            return False
        receipt = result.get("local_candidate_commit")
        if not isinstance(receipt, dict) or receipt.get("schema") != "nsc-local-candidate-commit/v1":
            return False
        from Pipeline.TaskReviewAgent.contracts import semantic_sha256
        body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        try:
            if receipt.get("receipt_sha256") != semantic_sha256(body):
                return False
        except (TypeError, ValueError):
            return False
        contract = (local.get("contracts") or {}).get(task_id) or {}
        bindings = {
            "task_id": task_id,
            "task_contract_sha256": record.get("task_contract_sha256"),
            "candidate_commit": record.get("local_candidate_commit"),
            "candidate_tree": record.get("local_candidate_tree"),
            "receipt_sha256": record.get("local_candidate_receipt_sha256"),
            "run_id": result.get("run_id"), "plan_id": result.get("plan_id"),
            "lease_id": result.get("lease_id"),
            "source_base": result.get("source_head"),
            "execution_result_sha256": result.get("result_sha256"),
            "candidate_patch_sha256": result.get("candidate_sha256"),
        }
        if (any(not value or receipt.get(key) != value for key, value in bindings.items())
                or receipt.get("candidate_parent") != receipt.get("source_base")
                or contract.get("task_contract_sha256") != record.get("task_contract_sha256")
                or result.get("task_contract_sha256") != record.get("task_contract_sha256")
                or not receipt.get("changed_paths")
                or receipt["changed_paths"] != result.get("final_actual_changed_paths")
                or record.get("source_commit") != record.get("local_source_integrated_commit")):
            return False
        lineage = local.get("source_lineage") or []
        sources = {local.get("initial_source_commit"), *(entry.get("applied_commit")
                   for entry in lineage if isinstance(entry, dict))}
        if receipt["source_base"] not in sources:
            return False
        return any(isinstance(entry, dict) and entry.get("kind") == "candidate"
                   and entry.get("task_id") == task_id
                   and entry.get("plan_id") == receipt["plan_id"]
                   and entry.get("candidate_commit") == receipt["candidate_commit"]
                   and entry.get("candidate_tree") == receipt["candidate_tree"]
                   and entry.get("candidate_receipt_sha256") == receipt["receipt_sha256"]
                   and entry.get("applied_commit") == record.get("source_commit")
                   and entry.get("applied_tree") == record.get("source_tree")
                   for entry in lineage)

    def build_local(self) -> dict[str, Any]:
        local = self.local_snapshot()
        sampled_now = time.time()
        events = local.get("events") or []
        shared_events = []
        for event in events:
            fields = event.get("fields")
            if (event.get("event") == "architect_provider_call" and event.get("task_id") is None
                    and isinstance(fields, dict) and isinstance(fields.get("task_ids"), list)):
                shared_events.append({**fields, "event": "architect_provider_call",
                                      "provider_usage": fields.get("provider_usage") or {}})
        tasks = []
        state_map = {
            "available": "ready",
            "architect_admission": "ready",
            "agent_ready": "ready",
            "agent_working": "active",
            "local_review_ready": "local_review_ready",
            "human_action_required": "human_action",
            "blocked": "blocked",
            "failed": "failed",
        }
        for task_id, record in sorted(local["tasks"].items()):
            contract = local["contracts"][task_id]
            local_state = record["state"]
            if local_state not in state_map:
                raise ValueError(f"Invalid local rehearsal state: {local_state}")
            state = state_map[local_state]
            locally_accepted = self.local_candidate_is_accepted(local, task_id, record)
            if locally_accepted:
                state = "complete"
            decomposition_label = self.local_decomposition_stage(local, task_id, record)
            launch = self.bound_local_launch(local, task_id, record)
            if launch is not None or decomposition_label is not None:
                state = "active"
            active = state == "active"
            # Queue time belongs to the run, not this task's active worker.
            # Old records without a lease start keep elapsed unavailable.
            started = record.get("started_at_utc")
            if launch is not None:
                started = launch["timestamp_utc"]
            updated = record.get("updated_at_utc")
            start_time = parse_timestamp(started)
            end_time = sampled_now if active else parse_timestamp(updated)
            elapsed = positive_number(record.get("elapsed_seconds"))
            if elapsed is None and start_time is not None and end_time is not None:
                elapsed = round(max(0.0, end_time - start_time), 1)
            stage_elapsed = positive_number(record.get("stage_elapsed_seconds"))
            phase = record.get("pipeline_stage") or record.get("phase")
            if launch is not None:
                phase = "worker_starting"
                stage_elapsed = elapsed
            if stage_elapsed is None and phase and end_time is not None:
                # Nothing in a local run records a stage duration, so derive it
                # from the newest durable event that entered the current stage.
                # Without this the stage clock reads unavailable for the whole
                # run while the task clock advances.
                entered = None
                for event in events:
                    if event.get("task_id") == task_id and event.get("event") == phase:
                        entered = event.get("timestamp_utc") or entered
                stage_start = parse_timestamp(entered)
                if stage_start is not None:
                    stage_elapsed = round(max(0.0, end_time - stage_start), 1)
            profile = record.get("provider_profile") or local.get("provider_profile")
            worker = {
                "run_id": local["run_id"],
                "worker_id": record.get("worker_id"),
                "lease_id": record.get("lease_id"),
                "status": local_state,
                "active": active,
                "finished": state in ("complete", "local_review_ready", "blocked", "failed", "human_action"),
                "phase": phase,
                "action": record.get("action"),
                "provider": record.get("provider") or record.get("execution_provider"),
                "provider_profile": profile,
                "turn": record.get("turn"),
                "role": record.get("role"),
                "updated_at": updated,
                "elapsed_seconds": elapsed,
                "stage_elapsed_seconds": stage_elapsed,
                "issue_number": None,
                "issue_url": None,
                "pull_request_number": None,
                "pull_request_url": None,
                "monitoring_ci": False,
            }
            if launch is not None:
                worker.update({"status": "starting", "phase": "worker_starting",
                    "action": "Worker launched; acquiring task lease", "pid": launch["pid"],
                    "worker_run_id": launch["run_id"], "launch_recorded_at": launch["timestamp_utc"]})
            stage_label = decomposition_label or ("Worker starting" if launch is not None else None)
            if decomposition_label is not None:
                worker.update(active=False, finished=False, host_action=True, action=decomposition_label)
            worker_output = self.bound_local_worker(local, task_id, record)
            step = self.local_worker_step(worker_output["rows"], sampled_now) if worker_output and active else None
            if step is not None:
                phase, stage_elapsed, stage_label = step["phase"], step["elapsed"], step["label"]
                worker.update(phase=phase, action=stage_label, stage_elapsed_seconds=stage_elapsed)
            # Usage is accepted only from this backend's validated task events.
            usage_records = []
            for index, event in enumerate(events):
                if event.get("task_id") != task_id:
                    continue
                fields = event.get("fields") or {}
                if not isinstance(fields, dict) or "provider_usage" not in fields:
                    continue
                turn = fields.get("turn")
                receipt = {
                    "turn": turn if type(turn) is int and turn > 0 else index + 1,
                    "provider": fields.get("provider"),
                    "model": fields.get("model"),
                    "role": fields.get("role"),
                    "status": fields.get("provider_call_status") or "succeeded",
                    "usage": fields.get("provider_usage"),
                    "pooled_session": fields.get("pooled_session") is True,
                    "timestamp": event.get("timestamp_utc"),
                }
                usage_records.append({
                    "run_id": ":".join(str(value or "") for value in (
                        local["run_id"], event.get("worker_id") or record.get("worker_id"),
                        fields.get("role"), fields.get("agent_runtime_run_id") or fields.get("call_id"),
                    )),
                    "usage_receipts": [receipt],
                })
            task_shared_events = [event for event in shared_events if task_id in event["task_ids"]]
            usage = self.token_cost(task_id, usage_records, task_shared_events, None)
            shared_by_call = {}
            for event in task_shared_events:
                shared_by_call.setdefault(event.get("agent_runtime_run_id"), event)
            for call in usage["shared_calls"]:
                event = shared_by_call[call["call_id"]]
                call.update({key: event.get(key) for key in ("role", "provider", "model")})
                total = positive_number(event["provider_usage"].get("total_tokens"))
                if total is not None and total.is_integer():
                    named = sorted(event["task_ids"])
                    # Assign integer remainder deterministically so displaying
                    # every named task neither loses nor duplicates tokens.
                    extra = int(named.index(task_id) < int(total) % len(named))
                    call["allocated_tokens"] += extra
                    usage["recorded_total_tokens"] += extra
                    call["allocation_method"] = f"equal share across {len(named)} named tasks; token remainder by task ID"
            direct_usage = [receipt["usage"] for usage_record in usage_records
                            for receipt in usage_record["usage_receipts"] if isinstance(receipt.get("usage"), dict)]
            known_usage = direct_usage + [event["provider_usage"] for event in task_shared_events
                                           if isinstance(event["provider_usage"], dict)]
            if not any(positive_number(value.get("estimated_cost_usd")) is not None for value in direct_usage):
                usage["direct_agent_cost_usd"] = None
            if not any(positive_number(value.get("estimated_cost_usd")) is not None for value in known_usage):
                usage.update(recorded_cost_usd=None,
                             cost_label="unavailable", cost_source="unavailable")
            if not any((total := positive_number(value.get("total_tokens"))) is not None and total.is_integer()
                       for value in known_usage):
                usage.update(recorded_total_tokens=None, token_source="unavailable")
            if usage["total_calls"]:
                usage["coverage_percent"] = round(100 * (usage["total_calls"] - usage["missing_usage_calls"]) / usage["total_calls"])
            progress = {
                "phase": phase,
                "action": worker["action"],
                "attempt": record.get("attempt"),
                "retry_count": record.get("retry_count", 0),
                "current_attempt_elapsed_seconds": elapsed,
                "stage_elapsed_seconds": stage_elapsed,
                "total_elapsed_seconds": elapsed,
                # The shipped detail pane reads these production names. A local
                # run knows exactly one active stage, so report that one rather
                # than manufacturing a full production stage timeline.
                "durable_task_elapsed_seconds": elapsed,
                "pipeline_stages": ([{
                    "label": stage_label or str(phase or "Stage unavailable"),
                    "display_label": str(phase or "Stage unavailable").replace("_", " "),
                    "status": "active",
                    "elapsed_seconds": stage_elapsed if stage_elapsed is not None else elapsed,
                }] if active else []),
                "current_agent": ({
                    "label": worker["worker_id"] or worker["provider"],
                    "action": worker["action"],
                    "duration_seconds": elapsed,
                } if active and (worker["worker_id"] or worker["provider"]) else None),
                "ci": None,
                "estimate": {"label": "Estimate unavailable", "sample_count": 0},
                "blocked_reason": record.get("blocked_reason") or record.get("local_decomposition_refusal"),
            }
            crew = self.bound_local_crew(local, task_id, record)
            if crew is not None:
                agents = self.crew_agents_from_rows(task_id=task_id, run_dir=crew["run_dir"], rows=crew["rows"],
                    active=active, now=sampled_now, stop_at=None if active else end_time)
                for agent in agents:
                    agent["action"] = AGENT_ROLE_ACTIONS.get(agent["role"], agent["label"])
                progress["agents"] = agents
                current = next((agent for agent in reversed(agents) if agent["status"] == "running"), None)
                progress["current_agent"] = current
                progress["crew_run_id"] = crew["run_dir"].name
                progress["crew_last_event_at"] = crew["rows"][-1].get("timestamp_utc")
                if current is not None:
                    required = next((row.get("required_roles", []) for row in crew["rows"] if row.get("event") == "run_started"), [])
                    execution_roles = list(dict.fromkeys(role for role in required
                        if isinstance(role, str) and role != "contract_locality_auditor"))
                    role = current["role"]
                    if role == "contract_locality_auditor":
                        stage_label = "Preparing execution crew · " + current["label"]
                    elif role in execution_roles:
                        current["role_index"], current["role_count"] = execution_roles.index(role) + 1, len(execution_roles)
                        stage_label = f"Execution crew · {current['label']} {current['role_index']} of {current['role_count']}"
                    else:
                        stage_label = "Execution crew · " + current["label"]
                    phase, stage_elapsed = "execution_crew", current["duration_seconds"]
                    progress["phase"] = worker["phase"] = phase
                    progress["stage_elapsed_seconds"] = worker["stage_elapsed_seconds"] = stage_elapsed
                    progress["pipeline_stages"] = [{"label": stage_label, "status": "active", "elapsed_seconds": stage_elapsed}]
                    progress["action"] = worker["action"] = current["action"]
                    worker["role"] = current["role"]
            progress["stage_label"] = stage_label
            task = {
                "id": task_id,
                "title": display_task_title(contract.get("title"), task_id),
                "parent": contract.get("parent"),
                "depends_on": list(contract.get("depends_on") or []),
                "kind": contract.get("kind"),
                "disposition": contract.get("contract_disposition"),
                "decomposition_state": contract.get("decomposition_state"),
                "decomposition_children": list(contract.get("decomposition_children") or []),
                "execution_scope": contract.get("execution_scope"),
                "notes": contract.get("notes"),
                "reason": record.get("blocked_reason") or record.get("local_decomposition_refusal"),
                "resources": list(contract.get("exclusive_resources") or []),
                "acceptance": [item.get("requirement") for item in contract.get("acceptance_criteria", []) if isinstance(item, dict)],
                "in_scope": True,
                "state": state,
                "local_state": local_state,
                "local_acceptance": ({"authority": "local_machine_policy",
                    "integrated_commit": record["local_source_integrated_commit"]}
                    if locally_accepted else None),
                # The worker's own project copy: LocalTaskCheckoutManager puts it here.
                "checkout_path": str(self.local_run_root / "checkouts" / task_id),
                "checkout_exists": (self.local_run_root / "checkouts" / task_id).is_dir(),
                "worker": worker,
                "active_work_type": (
                    worker.get("work_type")
                    if worker.get("work_type") in {"implementation", "decomposition"}
                    else "decomposition"
                    if worker.get("phase") in {"decomposition", "decomposition_apply"}
                    else "decomposition"
                    if contract.get("execution_scope") == DECOMPOSITION_EXECUTION_SCOPE
                    else "implementation"
                    if contract.get("kind") == "implementation"
                    else None
                ),
                "progress": progress,
                "token_cost": usage,
                "taskgraph": None,
                "source_commit": record.get("source_commit"),
                "source_tree": record.get("source_tree"),
                "task_contract_sha256": record.get("task_contract_sha256"),
            }
            if active:
                stage_text = stage_label or PHASE_STAGES.get(
                    phase,
                    (None, str(phase or "Stage unavailable").replace("_", " ").upper()),
                )[1]
                working_label = ("TASK WORKING (DECOMPOSITION)"
                                 if task["active_work_type"] == "decomposition" else "TASK WORKING")
                task["node_lines"] = [
                    working_label,
                    f"{stage_text} · {duration_text(elapsed)} elapsed",
                    " · ".join(str(value) for value in (worker["provider"], profile, worker["worker_id"]) if value),
                ]
                # An active node renders collapsed until it is expanded.
                # Two distinct clocks, as production reports them: the task's
                # total elapsed and the current stage's own elapsed. Reporting
                # the total under a CURRENT STAGE label would contradict the
                # detail pane, which reads stage_elapsed_seconds.
                task["node_heading"] = f"{task['id']} · Time {duration_text(elapsed)}"
                task["node_summary_lines"] = [working_label]
                if phase and positive_number(stage_elapsed) is not None:
                    task["node_summary_lines"].append(
                        f"[{stage_text}] · CURRENT STAGE "
                        + duration_text(stage_elapsed)
                    )
                if progress.get("current_agent"):
                    agent = progress["current_agent"]
                    task["node_summary_lines"].append(
                        f"CURRENT AGENT {agent['label']} · "
                        f"{agent.get('action') or 'action unavailable'} · "
                        + duration_text(agent.get("duration_seconds"))
                    )
            elif locally_accepted:
                task["node_lines"] = ["LOCAL ACCEPTED", "Integrated into local Source"]
                progress.update(stage_label="Locally accepted", action="Integrated into local Source",
                                completion_authority="local_machine_policy")
            elif state == "local_review_ready":
                task["node_lines"] = ["LOCAL REVIEW READY", "Local candidate awaiting review"]
            tasks.append(task)
        by_id = {task["id"]: task for task in tasks}
        for task in tasks:
            if not (
                task["state"] == "local_review_ready"
                and task.get("decomposition_state") == "decomposed"
                and task["progress"].get("phase") == "decomposition_applied"
            ):
                continue
            children = [
                by_id[child_id]
                for child_id in task.get("decomposition_children") or []
                if child_id in by_id and by_id[child_id].get("parent") == task["id"]
            ]
            child_counts: dict[str, int] = {}
            for child in children:
                child_counts[child["state"]] = child_counts.get(child["state"], 0) + 1
            task["progress"].update(
                phase="decomposition_children",
                action="monitor_decomposition_children",
                children_total=len(task.get("decomposition_children") or []),
                children_complete=sum(child["state"] == "complete" for child in children),
                local_completion_only=True,
                children_by_state=child_counts,
                children_recorded_total_tokens=sum(
                    int(child["token_cost"].get("recorded_total_tokens") or 0)
                    for child in children
                ),
            )
            task["state"] = "aggregate"
            task["active_work_type"] = None
            task["node_lines"] = self.node_lines(task)
        return {
            "generated_at": utc_now(),
            "tasks_dir": str(self.tasks_dir),
            "state_root": str(self.local_run_root),
            "run": {
                "dir": str(self.local_run_root),
                "run_id": local["run_id"],
                "mode": "local_rehearsal",
                "marker": "LOCAL REHEARSAL",
                "repository": None,
                "source_commit": local["source_commit"],
                "source_tree": local["source_tree"],
                "source_repository": local.get("source_repository"),
                "source_branch": local.get("source_branch"),
                "source_clean": local.get("source_clean"),
                "local_runtime_patch_sha256": local.get("local_runtime_patch_sha256"),
                "provider_profile": local.get("provider_profile"),
                "targets": [task["id"] for task in tasks],
                "excluded": [],
                "max_capacity": local.get("max_capacity"),
                "progress": local.get("progress"),
                "status": local.get("status") or "local_rehearsal",
                "complete": False,
            },
            "scheduler": {
                "active": [task["id"] for task in tasks if task["state"] == "active" and not task["worker"].get("host_action")],
                "blocked_reasons": [task["reason"] for task in tasks if task["reason"]],
            },
            "events": events[-60:],
            "tasks": tasks,
            "pipeline_activity": build_local_pipeline_activity(local=local, tasks=tasks, now=sampled_now),
        }

    def build(self) -> dict:
        if self.local_run_root is not None:
            return self.build_local()
        contracts = self.load_contracts()

        run_dir = self.run_dir or newest_autonomous_run(self.state_root)
        manifest = self.cache.get(run_dir / "manifest.json", read_json) if run_dir else None
        progress = self.cache.get(run_dir / "progress.json", read_json) if run_dir else None
        receipt = self.cache.get(run_dir / "graph-complete.json", read_json) if run_dir else None
        events = self.cache.get(run_dir / "events.jsonl", read_jsonl) if run_dir else None
        events = events or []
        timeline = self.cache.get(run_dir / "run_timeline.jsonl", read_jsonl) if run_dir else []

        manifest = manifest if isinstance(manifest, dict) else {}
        sampled_now = time.time()
        terminal_at = run_terminal_timestamp(
            events,
            timeline or [],
            manifest.get("run_id"),
        )
        run_terminal = terminal_at is not None or bool(receipt)
        repository = validated_repository_slug(manifest.get("github_repository"))
        scope_roots = set(manifest.get("target_task_ids") or [])
        scope = expand_decomposition_descendants(contracts, scope_roots)
        excluded = set(manifest.get("excluded_task_ids") or [])

        # Once the newest autonomous run has begun scheduling, only worker run
        # IDs launched by that exact run may describe its in-scope task nodes.
        # Older immutable output directories remain useful history, but must
        # not make a freshly reset task appear blocked, active, or complete.
        current_run_is_authoritative = bool(run_dir) and any(
            isinstance(event, dict)
            and (
                event.get("event") in CURRENT_RUN_BOUNDARY_EVENTS
                or (
                    event.get("event") == "worker_launched"
                    and isinstance(event.get("run_id"), str)
                    and re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9._-]*", event["run_id"]
                    )
                    is not None
                )
            )
            for event in events
        )
        current_run_worker_ids: dict[str, set[str]] = {}
        for event in events:
            if not isinstance(event, dict) or event.get("event") != "worker_launched":
                continue
            task_id = event.get("task_id")
            worker_run_id = event.get("run_id")
            if (
                task_id in scope
                and isinstance(task_id, str)
                and TASK_FILE_RE.fullmatch(task_id + ".yaml")
                and isinstance(worker_run_id, str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", worker_run_id)
            ):
                current_run_worker_ids.setdefault(task_id, set()).add(worker_run_id)

        scheduler_projection = self.scheduler_projection(events)
        taskgraph_available, taskgraph_states = self.taskgraph_states(list(contracts))

        tasks = []
        for task_id, contract in contracts.items():
            records = self.worker_runs(task_id, repository)
            if current_run_is_authoritative and task_id in scope:
                allowed_run_ids = current_run_worker_ids.get(task_id, set())
                records = [record for record in records if record.get("run_id") in allowed_run_ids]
            summary = dict(records[-1]) if records else None
            lifecycle = scheduler_projection["lifecycle"].get(task_id)
            transition = scheduler_projection["transitions"].get(task_id)
            inherited_workflow = scheduler_projection["inherited_workflow"].get(
                task_id
            )
            if summary is None and lifecycle and lifecycle.get("active") is True:
                launch_at = lifecycle.get("timestamp")
                phase = lifecycle.get("phase") or (transition.get("phase") if transition else None)
                stage_number = PHASE_STAGES.get(phase, (None, None))[0]
                summary = {
                    "status": None,
                    "finished": False,
                    "turn": None,
                    "action": None,
                    "phase": phase,
                    "phase_timestamp": launch_at,
                    "issue_state": transition.get("state") if transition else None,
                    "message": "Worker launch recorded by the scheduler",
                    "issue_number": None,
                    "issue_url": None,
                    "pull_request_number": None,
                    "pull_request_url": None,
                    "projection_state": None,
                    "projection_timestamp": None,
                    "first_timestamp": launch_at,
                    "last_timestamp": launch_at,
                    "worker_id": lifecycle.get("worker_id"),
                    "run_id": lifecycle.get("run_id"),
                    "work_type": lifecycle.get("work_type"),
                    "elapsed_seconds": None,
                    "stage_elapsed_seconds": None,
                    "role": None,
                    "provider": None,
                    "attempt": None,
                    "blocked_reason": None,
                    "ci": None,
                    "stage_evidence": (
                        {stage_number: {"started_at": launch_at, "completed_at": None}}
                        if stage_number is not None and parse_timestamp(launch_at) is not None
                        else {}
                    ),
                    "scheduler_projected": True,
                }
            elif summary and not summary.get("phase"):
                phase = (lifecycle or {}).get("phase") or (
                    transition.get("phase") if transition else None
                )
                if isinstance(phase, str):
                    phase_at = (lifecycle or {}).get("timestamp") or (
                        transition.get("timestamp") if transition else None
                    )
                    summary["phase"] = phase
                    summary["phase_timestamp"] = phase_at
                    stage_number = PHASE_STAGES.get(phase, (None, None))[0]
                    if stage_number is not None and parse_timestamp(phase_at) is not None:
                        summary.setdefault("stage_evidence", {}).setdefault(
                            stage_number,
                            {"started_at": phase_at, "completed_at": None},
                        )
            if summary and lifecycle and lifecycle.get("work_type") in {
                "implementation",
                "decomposition",
            }:
                summary.setdefault("work_type", lifecycle["work_type"])
            state, active = self.classify(
                contract=contract,
                task_id=task_id,
                excluded=excluded,
                worker=summary,
                lifecycle=lifecycle,
                transition=transition,
                queued=scheduler_projection["queued"],
                taskgraph_available=taskgraph_available,
                taskgraph=taskgraph_states.get(task_id),
                run_terminal=run_terminal,
            )
            token_cost = self.token_cost(task_id, records, events, taskgraph_states.get(task_id))
            elapsed_values = [positive_number(record.get("elapsed_seconds")) or 0 for record in records]
            task_stop_at = (
                parse_timestamp(summary.get("last_timestamp"))
                if summary and summary.get("finished")
                else terminal_at
            )
            stage_rows, durable_stage_elapsed, durable_task_elapsed = pipeline_stage_projection(
                [summary] if summary else [],
                summary,
                active=active,
                now=sampled_now,
                stop_at=task_stop_at,
            )
            crew_agents = self.execution_crew_agents(
                task_id=task_id,
                lifecycle=lifecycle,
                worker=summary,
                active=active,
                now=sampled_now,
                stop_at=task_stop_at,
            )
            decomposition_agents = self.decomposition_agents(
                task_id=task_id,
                lifecycle=lifecycle,
                active=active,
                now=sampled_now,
                stop_at=task_stop_at,
            )
            agents = []
            if summary and (
                not summary.get("scheduler_projected")
                or summary.get("phase") in {"decomposition", "decomposition_apply"}
            ):
                outer_role = (
                    "decomposition_worker"
                    if summary.get("scheduler_projected") and summary.get("phase") in {"decomposition", "decomposition_apply"}
                    else "task_supervisor"
                )
                outer_status = (
                    "running"
                    if active
                    else "failed"
                    if state in {"failed", "blocked"}
                    else "completed"
                    if summary.get("finished")
                    else "recorded_incomplete"
                )
                agents.append(
                    {
                        "role": outer_role,
                        "label": AGENT_ROLE_LABELS[outer_role],
                        "attempt": summary.get("attempt") or 1,
                        "status": outer_status,
                        "action": (
                            SUPERVISOR_ACTIONS.get(summary.get("action"))
                            or AGENT_ROLE_ACTIONS[outer_role]
                        ),
                        "duration_seconds": durable_task_elapsed,
                        "provider": summary.get("provider"),
                        "model": summary.get("model"),
                        "total_tokens": None,
                        "cost_usd": None,
                        "source": "task worker progress",
                    }
                )
            agents.extend(decomposition_agents)
            for agent in crew_agents:
                agent["action"] = AGENT_ROLE_ACTIONS.get(
                    agent["role"], "processing its assigned task"
                )
            agents.extend(crew_agents)
            if (
                active
                and summary
                and summary.get("action") == "run_execution_crew"
                and not any(agent.get("status") == "running" for agent in crew_agents)
            ):
                action_started = parse_timestamp(summary.get("action_timestamp"))
                agents.append(
                    {
                        "role": "execution_crew",
                        "label": AGENT_ROLE_LABELS["execution_crew"],
                        "attempt": summary.get("attempt") or 1,
                        "status": "running",
                        "action": f"implementing {contract.get('title') or task_id}",
                        "duration_seconds": (
                            max(0.0, time.time() - action_started)
                            if action_started is not None
                            else None
                        ),
                        "provider": summary.get("provider"),
                        "model": summary.get("model"),
                        "total_tokens": None,
                        "cost_usd": None,
                        "source": "task worker action",
                    }
                )
            current_agent = next(
                (agent for agent in reversed(agents) if agent.get("status") == "running"),
                None,
            )
            if summary:
                summary["active"] = active
                summary["monitoring_ci"] = state == "checks_pending" and active
                for internal in ("progress_path", "mtime", "run_result", "stage_evidence"):
                    summary.pop(internal, None)
            queue_position = (
                scheduler_projection["queued"].index(task_id) + 1
                if task_id in scheduler_projection["queued"]
                else None
            )
            queue_started = (
                parse_timestamp(transition.get("timestamp"))
                if transition
                else (
                    parse_timestamp(scheduler_projection["gate_timestamp"])
                    if task_id in scheduler_projection["queued"]
                    else None
                )
            )
            queue_clock_end = terminal_at if run_terminal and terminal_at is not None else sampled_now
            progress_data = {
                "phase": summary.get("phase") if summary else (transition.get("phase") if transition else None),
                "action": summary.get("action") if summary else None,
                "attempt": len(records) or None,
                "retry_count": max(0, len(records) - 1),
                "current_attempt_elapsed_seconds": elapsed_values[-1] if elapsed_values else None,
                "stage_elapsed_seconds": summary.get("stage_elapsed_seconds") if summary else None,
                "total_elapsed_seconds": elapsed_values[-1] if elapsed_values else None,
                "durable_stage_elapsed_seconds": durable_stage_elapsed,
                "durable_task_elapsed_seconds": durable_task_elapsed,
                "pipeline_stages": stage_rows,
                "agents": agents,
                "current_agent": current_agent,
                "queue_position": queue_position,
                "queue_wait_seconds": (
                    max(0.0, queue_clock_end - queue_started)
                    if queue_started is not None
                    else None
                ),
                "ci": summary.get("ci") if summary else None,
                "estimate": self.estimate(records, summary),
                "blocked_reason": summary.get("blocked_reason") if summary else None,
                "transition_context_kind": (
                    summary.get("transition_context_kind") if summary else None
                ),
                "transition_context": summary.get("transition_context") if summary else None,
                "transition_context_timestamp": (
                    summary.get("transition_context_timestamp") if summary else None
                ),
                "inherited_workflow_state": None,
                "inherited_workflow_source": None,
            }

            provenance = contract.get("provenance") or {}
            tasks.append(
                {
                    "id": task_id,
                    "title": display_task_title(contract.get("title"), task_id),
                    "parent": contract.get("parent"),
                    "depends_on": list(contract.get("depends_on") or []),
                    "kind": contract.get("kind"),
                    "disposition": contract.get("contract_disposition"),
                    "decomposition_state": contract.get("decomposition_state"),
                    "decomposition_children": list(
                        contract.get("decomposition_children") or []
                    ),
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
                    # The worker's own project copy: the checkout manager puts it here.
                    "checkout_path": str(self.state_root / task_id),
                    "checkout_exists": (self.state_root / task_id).is_dir(),
                    "worker": summary,
                    "active_work_type": (
                        summary.get("work_type")
                        if summary and summary.get("work_type") in {"implementation", "decomposition"}
                        else "decomposition"
                        if summary and summary.get("phase") in {"decomposition", "decomposition_apply"}
                        else "decomposition"
                        if contract.get("execution_scope") == DECOMPOSITION_EXECUTION_SCOPE
                        else "implementation"
                        if contract.get("kind") == "implementation"
                        else None
                    ),
                    "progress": progress_data,
                    "token_cost": token_cost,
                    "taskgraph": taskgraph_states.get(task_id),
                    "_inherited_workflow": inherited_workflow,
                    "_current_evidence_timestamps": [
                        summary.get("last_timestamp") if summary else None,
                        lifecycle.get("timestamp") if lifecycle else None,
                        transition.get("timestamp") if transition else None,
                    ],
                }
            )

        # Unmet dependencies keep a task pending; otherwise it is ready.  A
        # current-run gate snapshot is also authoritative queue evidence for
        # inherited recovery work: those tasks may not have a worker launch or
        # workflow transition in this run.  Apply that evidence only after
        # dependency resolution and only to otherwise-ready in-scope tasks, so
        # it cannot override terminal, excluded, blocked, human-action, or
        # active-worker evidence.
        done = {t["id"] for t in tasks if t["state"] in ("complete", "cancelled")}
        for task in tasks:
            if task["state"] == "pending" and all(d in done for d in task["depends_on"]):
                task["state"] = "ready"
            if task["state"] == "ready" and is_available_decomposition(task):
                task["state"] = "decomposition_ready"
            if (
                current_run_is_authoritative
                and task["in_scope"]
                and task["state"] == "ready"
                and task["id"] in scheduler_projection["queued"]
            ):
                task["state"] = "integration_queued"
            inherited_workflow = task.pop("_inherited_workflow", None)
            current_evidence_timestamps = task.pop("_current_evidence_timestamps", [])
            if (
                current_run_is_authoritative
                and task["in_scope"]
                and task["state"] in {"ready", "decomposition_ready"}
                and isinstance(inherited_workflow, dict)
                and inherited_workflow.get("state") == "human_action_required"
                and not any(
                    newer(timestamp, inherited_workflow.get("timestamp"))
                    for timestamp in current_evidence_timestamps
                )
            ):
                task["state"] = "human_action"
                task["progress"]["phase"] = inherited_workflow.get("phase")
                task["progress"]["inherited_workflow_state"] = inherited_workflow.get(
                    "state"
                )
                task["progress"]["inherited_workflow_source"] = inherited_workflow.get(
                    "source"
                )

        by_id = {task["id"]: task for task in tasks}
        hierarchy_children: dict[str, list[dict[str, Any]]] = {}
        for child in tasks:
            if child.get("parent"):
                hierarchy_children.setdefault(child["parent"], []).append(child)
        for task in tasks:
            declared_children = task.get("decomposition_children") or []
            children = (
                [
                    by_id[child_id]
                    for child_id in declared_children
                    if child_id in by_id
                    and by_id[child_id].get("parent") == task["id"]
                ]
                if declared_children
                else (
                    hierarchy_children.get(task["id"], [])
                    if task.get("decomposition_state") != "decomposed"
                    else []
                )
            )
            if children:
                task["progress"]["children_total"] = len(children)
                task["progress"]["children_complete"] = sum(
                    child["state"] == "complete" for child in children
                )
                child_counts: dict[str, int] = {}
                for child in children:
                    child_counts[child["state"]] = child_counts.get(child["state"], 0) + 1
                task["progress"]["children_by_state"] = child_counts
                task["progress"]["children_recorded_total_tokens"] = sum(
                    int(child["token_cost"].get("recorded_total_tokens") or 0)
                    for child in children
                )
            if task.get("decomposition_state") == "decomposed":
                # A durable decomposed parent is non-executable even while its
                # child contracts are still arriving. Generated children keep
                # their exact states once the two-way relationship is present.
                task["progress"].setdefault("children_total", 0)
                task["progress"].setdefault("children_complete", 0)
                task["progress"].setdefault("children_by_state", {})
                task["progress"].setdefault("children_recorded_total_tokens", 0)
                task["state"] = "aggregate"
                task["progress"]["phase"] = "decomposition_children"
                task["progress"]["action"] = "monitor_decomposition_children"

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
            if task["state"] == "active":
                total = duration_text(task["progress"].get("durable_task_elapsed_seconds"))
                task["node_heading"] = f"{task['id']} · Time {total}"
                current = next(
                    (
                        item
                        for item in task["progress"].get("pipeline_stages", [])
                        if item.get("status") == "active"
                    ),
                    None,
                )
                if current and positive_number(current.get("elapsed_seconds")) is not None:
                    stage_elapsed = duration_text(current.get("elapsed_seconds"))
                    task["node_summary_lines"] = [
                        f"[{current.get('display_label') or current['label']}] · CURRENT STAGE {stage_elapsed}"
                    ]
                else:
                    task["node_summary_lines"] = [
                        "TASK WORKING (DECOMPOSITION)"
                        if task.get("active_work_type") == "decomposition" else "TASK WORKING"
                    ]
                current_agent = task["progress"].get("current_agent")
                if current_agent:
                    agent_elapsed = duration_text(current_agent.get("duration_seconds"))
                    task["node_summary_lines"].append(
                        f"CURRENT AGENT {current_agent['label']} · {current_agent['action']} · {agent_elapsed}"
                    )

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
            timeline=timeline or [], worker_events=worker_events, tasks=tasks, now=sampled_now,
        )

        # Filter only the final projection. Dependencies, child counts, costs and
        # pipeline classification above still see the complete authoritative graph.
        display_ids = (
            set(contracts)
            if self.display_task_ids is None
            else expand_decomposition_descendants(contracts, self.display_task_ids)
        )
        displayed_tasks = [task for task in tasks if task["id"] in display_ids]
        return {
            "generated_at": utc_now(),
            "display": {
                "task_ids": list(self.display_task_ids) if self.display_task_ids is not None else None,
                "expanded_task_ids": sorted(display_ids),
                "missing_task_ids": [
                    task_id for task_id in self.display_task_ids or () if task_id not in contracts
                ],
            },
            "pipeline_activity": activity,
            "tasks_dir": str(self.tasks_dir),
            "state_root": str(self.state_root),
            "run": {
                "dir": str(run_dir) if run_dir else None,
                "run_id": manifest.get("run_id"),
                "repository": repository,
                "source_repository": manifest.get("source_repository"),
                "source_branch": self.source_branch,
                "max_capacity": manifest.get("max_capacity"),
                "targets": sorted(scope_roots),
                "expanded_targets": sorted(scope),
                "excluded": sorted(excluded),
                "progress": progress if isinstance(progress, dict) else None,
                "complete": bool(receipt),
            },
            "scheduler": {
                "active": [] if run_terminal else sorted(
                    task_id
                    for task_id, item in scheduler_projection["lifecycle"].items()
                    if item.get("active")
                ),
                "blocked_reasons": [r for r in blocked_reasons if r][-5:],
            },
            "events": events[-60:],
            "tasks": displayed_tasks,
        }

    def fingerprint(self) -> str:
        """Cheap change detector across every file the snapshot reads."""
        if self.local_run_root is not None:
            # Validate before broadcasting, and include no other run or checkout.
            try:
                local = self.local_snapshot()
            except (OSError, ValueError, KeyError) as error:
                # _state() rejects the run and shows why; the stream stays open.
                return "unobservable:" + str(error)
            fingerprint = {"snapshot": local}
            # Startup can become durable before local-state changes again.
            # The owned scheduler files are independently bound before display.
            launch_files = []
            for name in ("autonomous-manifest.json", "scheduler-events.jsonl"):
                path = self.local_run_root / name
                try:
                    if path.resolve().is_relative_to(self.local_run_root):
                        stamp = path.stat()
                        launch_files.append((name, stamp.st_mtime_ns, stamp.st_size))
                except OSError:
                    pass
            fingerprint["launch_files"] = launch_files
            crew_stamps = []
            for task_id, record in sorted(local["tasks"].items()):
                worker_output = self.bound_local_worker(local, task_id, record)
                crew = self.bound_local_crew(local, task_id, record)
                watched = (worker_output["watched"] if worker_output else []) + (crew["watched"] if crew else [])
                for path in watched:
                    try:
                        stamp = path.stat()
                        crew_stamps.append((str(path.relative_to(self.local_run_root)), stamp.st_mtime_ns, stamp.st_size))
                    except OSError:
                        continue
            fingerprint["crew_files"] = crew_stamps
            if any(record["state"] == "agent_working" or self.bound_local_launch(local, task_id, record) is not None
                   or self.local_decomposition_stage(local, task_id, record) is not None
                   for task_id, record in local["tasks"].items()):
                # SSE must refresh derived elapsed labels even during a long
                # provider call that emits no durable stage event.
                fingerprint["elapsed_tick"] = int(time.time())
            return json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
        parts: list[str] = []
        head_stamp = self.git_head_stamp(self.tasks_dir.parent)
        if head_stamp is not None:
            parts.append(f"taskgraph-head:{head_stamp}")
        if self.local_run_root is None and LAUNCH_SOURCE is not None:
            # Idle: the checkout's contracts are on the page; a commit there refreshes it.
            parts.append(f"launch-head:{self.git_head_stamp(LAUNCH_SOURCE)}:{sorted(ENABLED_TASK_IDS)}")
        try:
            for path in sorted(self.tasks_dir.iterdir()):
                if TASK_FILE_RE.match(path.name):
                    stat = path.stat()
                    parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            pass
        run_dir = self.run_dir or newest_autonomous_run(self.state_root)
        if run_dir:
            for name in ("manifest.json", "progress.json", "events.jsonl", "run_timeline.jsonl", "graph-complete.json"):
                try:
                    stat = (run_dir / name).stat()
                except OSError:
                    continue
                parts.append(f"{name}:{stat.st_mtime_ns}:{stat.st_size}")
            scheduler_events = self.cache.get(run_dir / "events.jsonl", read_jsonl)
            projection = self.scheduler_projection(
                scheduler_events if isinstance(scheduler_events, list) else []
            )
            # An active crew is stored inside its exact scheduler-created task
            # checkout, not under the supervisor output root. Watch only
            # identity-bound checkouts below state_root; never follow a path
            # supplied by a browser request or a free-form artifact field.
            for task_id, lifecycle in projection["lifecycle"].items():
                decomposition_run = self.bound_decomposition_run(
                    task_id=task_id, lifecycle=lifecycle
                )
                if decomposition_run is not None:
                    watched_decomposition = [
                        decomposition_run / "progress.jsonl",
                        decomposition_run / "decomposition_run_result.json",
                        *decomposition_run.glob("rounds/*/round_result.json"),
                        *decomposition_run.glob("rounds/*/agent_runtime/*/result.json"),
                        *decomposition_run.glob("agent_runtime/*/result.json"),
                    ]
                    for path in watched_decomposition:
                        try:
                            stat = path.stat()
                        except OSError:
                            continue
                        parts.append(
                            f"decomposition/{task_id}/{path.relative_to(decomposition_run)}:"
                            f"{stat.st_mtime_ns}:{stat.st_size}"
                        )
                checkout_text = lifecycle.get("checkout_path")
                if lifecycle.get("active") is not True or not isinstance(checkout_text, str):
                    continue
                try:
                    checkout = Path(checkout_text).resolve()
                    state_root = self.state_root.resolve()
                except (OSError, RuntimeError):
                    continue
                if (
                    TASK_FILE_RE.fullmatch(f"{task_id}.yaml") is None
                    or checkout.name != task_id
                    or not checkout.is_relative_to(state_root)
                ):
                    continue
                crew_outputs = checkout / "Pipeline" / "ExecutionCrew" / "outputs"
                try:
                    crew_outputs = crew_outputs.resolve()
                    if not crew_outputs.is_relative_to(checkout) or not crew_outputs.is_dir():
                        continue
                    crew_runs = list(crew_outputs.iterdir())
                except OSError:
                    continue
                for crew_run in crew_runs:
                    if (
                        not crew_run.is_dir()
                        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", crew_run.name) is None
                    ):
                        continue
                    watched = [
                        crew_run / "progress.jsonl",
                        crew_run / "crew_result.json",
                        *(crew_run / "role_results").glob("*.json"),
                        *(crew_run / "agent_runtime").glob("*/result.json"),
                    ]
                    for path in watched:
                        try:
                            stat = path.stat()
                        except OSError:
                            continue
                        parts.append(
                            f"crew/{task_id}/{crew_run.name}/{path.relative_to(crew_run)}:"
                            f"{stat.st_mtime_ns}:{stat.st_size}"
                        )
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
    health: dict[str, Any] | None = None
    approval: Any = None
    origin: str

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _state(self) -> dict[str, Any]:
        persistent = LOCAL_RUNS_ROOT is not None or RUNS_MODE == "production"
        if RUNS_MODE == "production":
            # The production build already discovers the newest run under the
            # checkout root and renders the contracts alone when there is none.
            self.snapshot.display_task_ids = production_display_ids(self.snapshot)
            run_root = newest_autonomous_run(self.snapshot.state_root)
            try:
                state = self.snapshot.build()
            except (OSError, ValueError, KeyError):
                state = self.snapshot.idle_local_state()
                run_root = None
        elif LOCAL_RUNS_ROOT is not None:
            self.snapshot.follow_newest_local_run()
            if self.snapshot.local_run_root is None:
                state = self.snapshot.idle_local_state()
            else:
                try:
                    state = self.snapshot.build()
                except (OSError, ValueError, KeyError) as error:
                    # Reset underneath us, or stale: stay idle until a different run appears.
                    self.snapshot.reject_local_run(error)
                    state = self.snapshot.idle_local_state()
            run_root = self.snapshot.local_run_root
        else:
            state = self.snapshot.build()
            run_root = getattr(self.snapshot, "local_run_root", None)
        state["human_actions"] = (
            self.approval.list_actions() if self.approval is not None else []
        )
        run = state.get("run")
        if isinstance(run, dict):
            if run_root is not None:
                stop = local_stop_state(Path(run_root))
                # Once the stop has completed the page offers Start again.
                run["stop_requested"] = bool(stop["requested"] and not stop["completed"])
                run["stop"] = stop
                run["operator"] = local_operator_state(Path(run_root))
                run["architect"] = architect_state(Path(run_root), run.get("run_id"))
            elif persistent and "operator" not in run:
                run["stop_requested"] = False
                run["stop"] = {"requested": False}
                run["operator"] = idle_operator_state()
            annotate_operator(run, persistent=persistent)
        return state

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
            body = json.dumps(self._state()).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/api/health":
            body = json.dumps(
                self.health
                or {"schema": HEALTH_SCHEMA, "status": "ok", "identity": None},
                sort_keys=True,
            ).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/api/stream":
            self._stream()
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        local_actions = {"/api/local/stop", "/api/local/force-stop", "/api/local/reset", "/api/local/start", "/api/local/poke",
                         "/api/local/scope", "/api/local/issue"}
        persistent = LOCAL_RUNS_ROOT is not None or RUNS_MODE == "production"
        followed_root = current_followed_run_root(self.snapshot) if persistent else getattr(self.snapshot, "local_run_root", None)
        idle_actions = {"/api/local/start", "/api/local/scope", "/api/local/issue"}
        local_stop = path in local_actions and (followed_root is not None or (path in idle_actions and persistent))
        if not local_stop and (path != "/api/approve" or self.approval is None):
            self._send(404, b"not found", "text/plain")
            return
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._send(403, b"loopback only", "text/plain")
            return
        if self.headers.get("Origin") != self.origin:
            self._send(403, b"same-origin request required", "text/plain")
            return
        if self.headers.get_content_type() != "application/json":
            self._send(415, b"application/json required", "text/plain")
            return
        length_text = self.headers.get("Content-Length")
        try:
            length = int(length_text or "")
        except ValueError:
            length = 0
        if not 1 <= length <= 2048:
            self._send(413, b"invalid request length", "text/plain")
            return
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send(400, b"invalid JSON", "text/plain")
            return
        if local_stop:
            if not isinstance(value, dict) or value.get("confirm") is not True:
                self._send(400, b"stop requires {\"confirm\": true}", "text/plain")
                return
            try:
                if path == "/api/local/start":
                    result = request_local_start()
                    self._send(200, json.dumps(result, sort_keys=True).encode("utf-8"), "application/json; charset=utf-8")
                    return
                if path == "/api/local/scope":
                    result = request_scope_change(value)
                    self._send(200, json.dumps(result, sort_keys=True).encode("utf-8"), "application/json; charset=utf-8")
                    return
                if path == "/api/local/issue":
                    result = request_task_issue(value)
                    self._send(200, json.dumps(result, sort_keys=True).encode("utf-8"), "application/json; charset=utf-8")
                    return
                run_root = Path(followed_root)
                if path == "/api/local/poke":
                    result = request_local_poke(run_root)
                    self._send(200, json.dumps(result, sort_keys=True).encode("utf-8"), "application/json; charset=utf-8")
                    return
                if path == "/api/local/force-stop":
                    result = request_local_force_stop(run_root)
                elif path == "/api/local/reset" and persistent:
                    # Persistent viewer: let go of the run and keep serving; the
                    # page shows the next run when it starts.
                    result = request_local_reset(run_root, viewer_pid=None)
                    self.snapshot.release_local_run()
                elif path == "/api/local/reset":
                    result = request_local_reset(run_root, viewer_pid=os.getpid())
                    # The reset waits for this process to exit; leave after the reply is flushed.
                    threading.Timer(1.0, lambda: os._exit(0)).start()
                else:
                    result = request_local_stop(run_root)
            except LocalStopError as error:
                body = json.dumps({"status": "rejected", "message": str(error)[:500]}).encode("utf-8")
                self._send(409, body, "application/json; charset=utf-8")
                return
            self._send(200, json.dumps(result, sort_keys=True).encode("utf-8"), "application/json; charset=utf-8")
            return
        if not isinstance(value, dict) or set(value) != {"action_token"}:
            self._send(400, b"only an action capability is accepted", "text/plain")
            return
        try:
            result = self.approval.approve(value["action_token"])
        except Exception as error:  # bounded local endpoint; reject fail-closed
            body = json.dumps(
                {"status": "rejected", "message": str(error)[:500]}
            ).encode("utf-8")
            self._send(409, body, "application/json; charset=utf-8")
            return
        body = json.dumps(result, sort_keys=True).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")

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
                    payload = json.dumps(self._state())
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                else:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def local_stop_state(run_root: Path) -> dict[str, Any]:
    """What the scheduler has done with an operator stop, from its own journal.

    ``requested`` mirrors the stop file; ``acknowledged`` is true once the
    scheduler journaled ``scheduler_draining`` after the request, and the
    active-children count and drain limit come from that event, so the viewer
    reports the drain the scheduler is actually doing rather than a guess.
    """
    run_root = Path(run_root)
    stop_path = run_root / "stop-request.json"
    state: dict[str, Any] = {"requested": stop_path.is_file(), "requested_at_utc": None,
                             "acknowledged": False, "draining_since_utc": None,
                             "active_children": None, "drain_limit_seconds": None,
                             "completed": False, "stopped_at_utc": None}
    if not state["requested"]:
        return state
    try:
        request = json.loads(stop_path.read_text(encoding="utf-8"))
        if isinstance(request, dict) and isinstance(request.get("requested_at_utc"), str):
            state["requested_at_utc"] = request["requested_at_utc"]
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    events_path = _events_file(run_root)
    try:
        size = events_path.stat().st_size
        with events_path.open("rb") as handle:
            handle.seek(max(0, size - 262144))
            tail = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return state
    requested_at = state["requested_at_utc"] or ""
    for line in reversed(tail):
        if '"scheduler_stopped"' in line and not state["completed"]:
            try:
                stopped = json.loads(line)
            except json.JSONDecodeError:
                stopped = None
            if isinstance(stopped, dict) and stopped.get("event") == "scheduler_stopped":
                stamp = str(stopped.get("timestamp_utc") or "")
                if not requested_at or stamp >= requested_at:
                    state.update(completed=True, stopped_at_utc=stamp or None)
            continue
        if '"scheduler_draining"' not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") != "scheduler_draining":
            continue
        stamp = str(event.get("timestamp_utc") or "")
        if requested_at and stamp < requested_at:
            break
        children = event.get("active_children")
        state.update(acknowledged=True, draining_since_utc=stamp or None,
                     active_children=len(children) if isinstance(children, list) else None,
                     drain_limit_seconds=event.get("fatal_drain_seconds"))
        break
    if not state["completed"] and scheduler_finished(run_root):
        # A scheduler that exited without journaling scheduler_stopped (force
        # stop, crash, drain error) is still over; do not keep saying "draining".
        state["completed"] = True
    return state


LAUNCH_RECEIPT_PATH: Path | None = None
AGENT_DIR = Path(__file__).resolve().parent.parent
# Persistent viewer: follow the newest run under this folder instead of one
# exact run root, so one browser tab on one port survives stop/reset/start.
LOCAL_RUNS_ROOT: Path | None = None
LAUNCH_RECEIPTS_ROOT: Path | None = None
# Persistent viewer's Start button: what to launch, in place, when no run is alive.
LAUNCH_SOURCE: Path | None = None
LAUNCH_CHECKOUT_ROOT: Path | None = None
LAUNCH_PROFILE = "all-claude"
LAUNCH_TASK_IDS: tuple[str, ...] = ()
LAUNCH_VIEWER_PORT = 8787
START_PENDING_MAX_SECONDS = 1800.0
# "local" follows <CheckoutRoot>/.task-review-agent/local-rehearsals; "production"
# follows the newest autonomous run under <CheckoutRoot> and launches
# start-production instead of start-here.
RUNS_MODE = "local"
LAUNCH_REPOSITORY: str | None = None
LAUNCH_SOURCE_BRANCH: str | None = None
# Production: launch without the synthetic evidence pump, so every task waits
# for a human PASS on its Issue.
LAUNCH_HUMAN_REVIEW = False
# Tasks the Start button will pass as -TaskId; toggled per task from the page
# and kept in <CheckoutRoot>/viewer-scope.json so a viewer restart keeps them.
ENABLED_TASK_IDS: frozenset[str] = frozenset()
# Last "Create GitHub Issue" outcome per task, shown in the task panel.
_ISSUE_RESULTS: dict[str, dict[str, Any]] = {}


def _events_file(run_root: Path) -> Path:
    """A local run journals scheduler-events.jsonl; a production run events.jsonl."""
    local = Path(run_root) / "scheduler-events.jsonl"
    return local if local.is_file() else Path(run_root) / "events.jsonl"


def _run_source(run_root: Path) -> Path | None:
    """The Source checkout a run was launched from (its wake endpoint lives beside it)."""
    for name in ("local-manifest.json", "manifest.json"):
        try:
            manifest = json.loads((Path(run_root) / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        source = manifest.get("source_repository") if isinstance(manifest, dict) else None
        if isinstance(source, str) and source:
            return Path(source)
    return LAUNCH_SOURCE


def current_followed_run_root(snapshot: "Snapshot") -> Path | None:
    """The run the persistent viewer is showing, in either mode."""
    if RUNS_MODE == "production":
        return newest_autonomous_run(snapshot.state_root)
    return snapshot.local_run_root


def launch_receipt_for(run_root: Path | None) -> Path | None:
    """Local receipts sit in <RunsRoot>/<run-id>/; production ones in <CheckoutRoot>/launch-receipts/<run-id>.json."""
    if RUNS_MODE == "production" and LAUNCH_RECEIPTS_ROOT is not None and run_root is not None:
        return LAUNCH_RECEIPTS_ROOT / (Path(run_root).name + ".json")
    return LAUNCH_RECEIPT_PATH


def stop_receipt_present(receipt: Path | None, run_root: Path | None) -> bool:
    """Stop-NscRun writes stop-receipt.json beside the launch receipt; production runs share that folder, so match the run id."""
    if receipt is None:
        return False
    path = receipt.parent / "stop-receipt.json"
    if not path.is_file():
        return False
    if RUNS_MODE != "production" or run_root is None:
        return True
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(record, dict) and record.get("run_id") == Path(run_root).name


def _scope_path() -> Path | None:
    return LAUNCH_CHECKOUT_ROOT / "viewer-scope.json" if LAUNCH_CHECKOUT_ROOT is not None else None


def load_enabled_scope() -> frozenset[str]:
    path = _scope_path()
    if path is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ids = data.get("task_ids") if isinstance(data, dict) else None
            if isinstance(ids, list):
                return frozenset(item for item in ids if isinstance(item, str))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    return frozenset(LAUNCH_TASK_IDS)


def scope_customized() -> bool:
    path = _scope_path()
    return path is not None and path.is_file()


def _save_enabled_scope() -> None:
    path = _scope_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"task_ids": sorted(ENABLED_TASK_IDS)}), encoding="utf-8")


def _requested_task_id(value: Any) -> str:
    task_id = value.get("task_id") if isinstance(value, dict) else None
    if not isinstance(task_id, str) or not TASK_FILE_RE.fullmatch(task_id + ".yaml"):
        raise LocalStopError("a task id such as NSC-042 is required")
    return task_id


def request_scope_change(value: Any) -> dict[str, Any]:
    """Enable or disable one task for the next Start; the choice is kept on disk."""
    global ENABLED_TASK_IDS
    task_id = _requested_task_id(value)
    enabled = value.get("enabled")
    if not isinstance(enabled, bool):
        raise LocalStopError("enabled must be true or false")
    updated = set(ENABLED_TASK_IDS)
    (updated.add if enabled else updated.discard)(task_id)
    ENABLED_TASK_IDS = frozenset(updated)
    _save_enabled_scope()
    return {"status": "scope_updated", "task_id": task_id, "enabled": enabled,
            "scope_task_ids": sorted(ENABLED_TASK_IDS)}


def request_task_issue(value: Any) -> dict[str, Any]:
    """Create the task's GitHub Issue and the NSC-Vincent inbox now, or report the ones that exist.

    This is the same code a production worker runs when it claims the task, so
    the Issue it leaves behind is exactly what the run expects to find.
    """
    if RUNS_MODE != "production" or not LAUNCH_REPOSITORY or LAUNCH_SOURCE is None or LAUNCH_CHECKOUT_ROOT is None:
        raise LocalStopError("GitHub Issues are created by the production viewer: NscRun viewer -Production")
    task_id = _requested_task_id(value)
    import subprocess
    from Pipeline.TaskReviewAgent.committed_tasks import CommittedTaskError, load_committed_task
    from Pipeline.TaskReviewAgent.issue_workflow_store import (
        VINCENT_INBOX_TITLE, GhIssueBackend, IssueWorkflowService, IssueWorkflowStoreError,
    )
    from Pipeline.TaskReviewAgent.issue_workflow_store import utc_now as workflow_now
    from Pipeline.TaskReviewAgent.vincent_inbox_bootstrap import ensure_autonomous_vincent_inbox
    source = LAUNCH_SOURCE
    try:
        inbox = ensure_autonomous_vincent_inbox(source=source, checkout_root=LAUNCH_CHECKOUT_ROOT, repository=LAUNCH_REPOSITORY)
        task = load_committed_task(source, task_id)
        service = IssueWorkflowService(
            backend=GhIssueBackend(source_root=source, repository=LAUNCH_REPOSITORY),
            task_loader=lambda other: load_committed_task(source, other),
            worker_id="gauntlet-view-operator",
            vincent_inbox_title=VINCENT_INBOX_TITLE,
        )
        existing = service.find(task_id)
        if existing is not None and existing.managed:
            issue, status = existing, "exists"
        else:
            issue, status = service._initialize_issue(task, now=workflow_now()), "created"
    except (IssueWorkflowStoreError, CommittedTaskError, OSError, subprocess.SubprocessError, ValueError) as error:
        raise LocalStopError((type(error).__name__ + ": " + str(error))[:500]) from error
    workflow_state = issue.state.state if issue.state is not None else None
    result = {
        "status": status, "task_id": task_id, "at": utc_now(),
        "issue_number": issue.issue_number,
        "issue_url": issue.issue_url or github_issue_url(LAUNCH_REPOSITORY, issue.issue_number),
        "state": getattr(workflow_state, "value", str(workflow_state)) if workflow_state is not None else None,
        "inbox_number": inbox.issue_number,
        "inbox_url": inbox.issue_url or github_issue_url(LAUNCH_REPOSITORY, inbox.issue_number),
        "inbox_disposition": inbox.disposition,
    }
    _ISSUE_RESULTS[task_id] = result
    return result


_LAUNCHER_SCOPE_RE = re.compile(r"\$taskIds\s*=\s*@\(([^)]*)\)")


def launcher_default_scope(source: Path | None) -> tuple[str, ...]:
    """The gauntlet scope Start runs without -TaskId, read from Run-ProfileGauntlet.ps1 as the launcher reads it."""
    if source is None:
        return ()
    try:
        text = (source / "Pipeline" / "TaskReviewAgent" / "Run-ProfileGauntlet.ps1").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    match = _LAUNCHER_SCOPE_RE.search(text)
    return tuple(re.findall(r"NSC-[0-9]+", match.group(1))) if match else ()


def idle_operator_state() -> dict[str, Any]:
    """Operator actions while no run exists yet: only Start (when the checkout is clean)."""
    dirty = source_dirty_files(LAUNCH_SOURCE) if LAUNCH_SOURCE is not None else []
    pending = start_pending()
    return {"launch_receipt": None, "stop_receipt_present": False, "scheduler_stopped": False,
            "force_stop_available": False, "reset_available": False, "viewer_persistent": True,
            "start_available": LAUNCH_SOURCE is not None and not pending and not dirty,
            "start_pending": pending,
            "start_blocker": ("checkout has uncommitted changes: " + ", ".join(dirty[:6])) if dirty else None,
            "start_error": _LAST_START_ERROR,
            "observe_error": _LAST_OBSERVE_ERROR}


def annotate_operator(run: dict[str, Any], *, persistent: bool) -> None:
    """Add what the page needs for its buttons, in either mode."""
    operator = run.get("operator")
    if isinstance(operator, dict):
        operator["viewer_persistent"] = persistent
        operator["runs_mode"] = RUNS_MODE
        operator["scope_task_ids"] = sorted(ENABLED_TASK_IDS)
        operator["scope_customized"] = scope_customized()
        operator["issues"] = dict(_ISSUE_RESULTS)
        operator["repository"] = LAUNCH_REPOSITORY
        operator["human_review"] = bool(LAUNCH_HUMAN_REVIEW)
    if RUNS_MODE == "production":
        run.setdefault("mode", "production")
        run["marker"] = "PRODUCTION"
        if not run.get("source_repository") and LAUNCH_SOURCE is not None:
            run["source_repository"] = str(LAUNCH_SOURCE)
        if not run.get("repository"):
            run["repository"] = LAUNCH_REPOSITORY
        if not run.get("source_branch"):
            run["source_branch"] = LAUNCH_SOURCE_BRANCH
    if run.get("repository"):
        run["github_url"] = "https://github.com/" + str(run["repository"])


def production_display_ids(snapshot: "Snapshot") -> tuple[str, ...] | None:
    """Show the launch scope, the enabled tasks and the newest run's targets; everything if none."""
    ids = set(LAUNCH_TASK_IDS) | set(ENABLED_TASK_IDS)
    run_root = newest_autonomous_run(snapshot.state_root)
    if run_root is not None:
        manifest = read_json(run_root / "manifest.json")
        if isinstance(manifest, dict):
            ids |= {item for item in (manifest.get("target_task_ids") or []) if isinstance(item, str)}
    return tuple(sorted(ids)) if ids else None


def _start_pending_path() -> Path | None:
    if LAUNCH_CHECKOUT_ROOT is not None:
        return LAUNCH_CHECKOUT_ROOT / "start-pending.json"
    return None


_LAST_START_ERROR: str | None = None
_LAST_OBSERVE_ERROR: str | None = None
_DIRTY_CACHE: dict[str, tuple[float, list[str]]] = {}


def _set_observe_error(message: str | None) -> None:
    global _LAST_OBSERVE_ERROR
    _LAST_OBSERVE_ERROR = message
_PID_CACHE: dict[int, tuple[float, bool]] = {}


def _process_alive(pid: int) -> bool:
    now = time.time()
    cached = _PID_CACHE.get(pid)
    if cached and now - cached[0] < 5.0:
        return cached[1]
    alive = False
    try:
        import subprocess
        if os.name == "nt":
            completed = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                                       capture_output=True, text=True, timeout=15)
            alive = str(int(pid)) in completed.stdout
        else:
            os.kill(int(pid), 0)
            alive = True
    except (OSError, subprocess.SubprocessError, ValueError):
        alive = False
    _PID_CACHE[pid] = (now, alive)
    return alive


def source_dirty_files(source: Path | None) -> list[str]:
    """Uncommitted paths in the launch checkout (cached ten seconds); an in-place run refuses them."""
    if source is None:
        return []
    key = str(source)
    now = time.time()
    cached = _DIRTY_CACHE.get(key)
    if cached and now - cached[0] < 10.0:
        return cached[1]
    files: list[str] = []
    try:
        module_dir = str(HERE.parents[2])
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        # Same rule as the run itself: a line-ending-only rewrite is not a change.
        from Pipeline.TaskReviewAgent.local_rehearsal import _dirty_paths
        files = _dirty_paths(source)
    except Exception:
        files = []
    _DIRTY_CACHE[key] = (now, files)
    return files


def _read_log_tail(path: Path, lines: int = 12) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    text = data.decode("utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else data.decode("utf-8", errors="replace")
    kept = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(kept[-lines:])


def start_pending() -> bool:
    """A Start was requested and no run newer than it has appeared yet.

    A launcher that exited without producing a run is reported as a failed
    start (its log tail becomes ``start_error``) and no longer blocks the button.
    """
    global _LAST_START_ERROR
    path = _start_pending_path()
    if path is None:
        return False
    try:
        marker = path.stat().st_mtime
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if time.time() - marker > START_PENDING_MAX_SECONDS:
        path.unlink(missing_ok=True)
        return False
    if RUNS_MODE == "production":
        newest = newest_autonomous_run(LAUNCH_CHECKOUT_ROOT) if LAUNCH_CHECKOUT_ROOT is not None else None
        manifest_name = "manifest.json"
    else:
        newest = newest_local_run(LOCAL_RUNS_ROOT) if LOCAL_RUNS_ROOT is not None else None
        manifest_name = "local-manifest.json"
    if newest is not None:
        try:
            if (newest / manifest_name).stat().st_mtime >= marker:
                path.unlink(missing_ok=True)
                _LAST_START_ERROR = None
                return False
        except OSError:
            pass
    helper_pid = record.get("helper_pid") if isinstance(record, dict) else None
    if isinstance(helper_pid, int) and helper_pid > 1 and not _process_alive(helper_pid):
        log = record.get("log") if isinstance(record, dict) else None
        tail = _read_log_tail(Path(log)) if isinstance(log, str) and log else ""
        _LAST_START_ERROR = ("The launcher exited without starting a run." + ("\n" + tail if tail else ""))
        path.unlink(missing_ok=True)
        return False
    return True


_SCHEDULER_PROCESS_CACHE: dict[str, tuple[float, int | None]] = {}


def scheduler_process(run_id: str) -> int | None:
    """Pid of the run's scheduler process, cached for ten seconds (Windows: WMI via PowerShell)."""
    now = time.time()
    cached = _SCHEDULER_PROCESS_CACHE.get(run_id)
    if cached and now - cached[0] < 10.0:
        return cached[1]
    pid: int | None = None
    if os.name == "nt":
        import subprocess
        pattern = re.escape(run_id)
        command = ("(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine "
                   "-and $_.CommandLine -match 'run_autonomous_graph' -and $_.CommandLine -match '" + pattern
                   + "' } | Select-Object -First 1).ProcessId")
        try:
            completed = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                       capture_output=True, text=True, timeout=20)
            text = completed.stdout.strip()
            pid = int(text) if text.isdigit() else None
        except (OSError, subprocess.SubprocessError, ValueError):
            pid = None
    _SCHEDULER_PROCESS_CACHE[run_id] = (now, pid)
    return pid


def architect_state(run_root: Path | None, run_id: str | None) -> dict[str, Any]:
    """Alive/dead for the run's scheduler (the architect's host) and how fresh its journal is."""
    state: dict[str, Any] = {"alive": False, "pid": None, "finished": False, "last_event": None,
                             "last_event_utc": None, "seconds_since_event": None, "wake_endpoint": False}
    if run_root is None or not run_id:
        return state
    pid = scheduler_process(run_id)
    state["alive"] = pid is not None
    state["pid"] = pid
    state["finished"] = scheduler_finished(run_root)
    events_path = _events_file(Path(run_root))
    try:
        size = events_path.stat().st_size
        with events_path.open("rb") as handle:
            handle.seek(max(0, size - 16384))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("event"):
                state["last_event"] = event.get("event")
                stamp = str(event.get("timestamp_utc") or "")
                state["last_event_utc"] = stamp or None
                try:
                    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    state["seconds_since_event"] = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
                except ValueError:
                    pass
                break
    except OSError:
        pass
    source = _run_source(Path(run_root))
    if source is not None:
        from Pipeline.TaskReviewAgent.human_action_wait import architect_wake_endpoint_path
        try:
            state["wake_endpoint"] = architect_wake_endpoint_path(source).is_file()
        except OSError:
            pass
    return state


def request_local_poke(run_root: Path) -> dict[str, Any]:
    """Wake the scheduler now (same authenticated datagram the stop uses) so it polls."""
    from Pipeline.TaskReviewAgent.request_run_stop import wake_scheduler
    source = _run_source(Path(run_root))
    if source is None:
        raise LocalStopError("no manifest in this run names a source repository")
    woke = wake_scheduler(source, reason="GauntletView poke")
    if not woke:
        raise LocalStopError("no live wake endpoint; the scheduler is not waiting (dead, draining, or mid-poll)")
    return {"status": "poked", "wake_sent": True}


# Journal events after which the scheduler never admits another worker.
_TERMINAL_EVENTS = ('"scheduler_stopped"', '"autonomous_run_error"', '"graph_complete"')
# A run whose scheduler process is gone and whose journal is this stale is over
# even without a terminal event (killed, crashed, machine rebooted).
_DEAD_RUN_AFTER_SECONDS = 120


def _last_activity_age(run_root: Path) -> int | None:
    """Seconds since the run folder's newest file changed (for runs with no journal)."""
    newest = None
    try:
        for item in Path(run_root).iterdir():
            if item.is_file():
                stamp = item.stat().st_mtime
                newest = stamp if newest is None or stamp > newest else newest
    except OSError:
        return None
    return None if newest is None else max(0, int(time.time() - newest))


def _last_event_age(run_root: Path) -> int | None:
    """Seconds since the newest journal event; falls back to file activity when there is no journal."""
    events_path = _events_file(Path(run_root))
    try:
        size = events_path.stat().st_size
        with events_path.open("rb") as handle:
            handle.seek(max(0, size - 16384))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        # A run that died before its first journal write (a preflight error
        # goes to the launcher log) still has a manifest; its files stop
        # changing the moment the scheduler is gone.
        return _last_activity_age(run_root)
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event"):
            stamp = str(event.get("timestamp_utc") or "")
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                return None
            return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    return None


def scheduler_finished(run_root: Path | None) -> bool:
    """True once the run can never make progress again.

    Journaled stop, error or completion counts, and so does a run with no
    scheduler process left and a journal that has been silent for a while:
    a run that died at preflight must offer Start, not Stop.
    """
    if run_root is None:
        return False
    run_root = Path(run_root)
    # A scheduler that is still running (draining after an error, say) holds
    # the scheduler lock, so a new Start would be refused: never call the run
    # finished while its process exists, whatever the journal says.
    if scheduler_process(run_root.name) is not None:
        return False
    if (run_root / "graph-complete.json").is_file():
        return True
    events_path = _events_file(run_root)
    tail = ""
    try:
        size = events_path.stat().st_size
        with events_path.open("rb") as handle:
            handle.seek(max(0, size - 131072))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        pass  # no journal: decide from the process and file activity below
    if any(marker in tail for marker in _TERMINAL_EVENTS):
        return True
    age = _last_event_age(run_root)
    if age is None or age < _DEAD_RUN_AFTER_SECONDS:
        return False
    return scheduler_process(run_root.name) is None


def _discard_stale_start_marker() -> None:
    """A start marker whose launcher is already gone belongs to an earlier viewer session."""
    path = _start_pending_path()
    if path is None or not path.is_file():
        return
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return
    helper_pid = record.get("helper_pid") if isinstance(record, dict) else None
    if not isinstance(helper_pid, int) or helper_pid <= 1 or not _process_alive(helper_pid):
        path.unlink(missing_ok=True)


def newest_local_run(runs_root: Path) -> Path | None:
    """The most recently created run directory under ``runs_root`` (or None)."""
    try:
        candidates = [child for child in Path(runs_root).iterdir() if child.is_dir()]
    except OSError:
        return None
    newest: tuple[float, Path] | None = None
    for child in candidates:
        manifest = child / "local-manifest.json"
        try:
            stamp = manifest.stat().st_mtime
        except OSError:
            continue
        if newest is None or stamp > newest[0]:
            newest = (stamp, child)
    return newest[1] if newest else None


def local_operator_state(run_root: Path) -> dict[str, Any]:
    """Which operator actions the viewer may offer for this run (local or production)."""
    receipt = launch_receipt_for(run_root)
    stopped = stop_receipt_present(receipt, run_root)
    finished = bool(local_stop_state(run_root).get("completed")) or scheduler_finished(run_root)
    pending = start_pending()
    dirty = source_dirty_files(LAUNCH_SOURCE)
    blocker = (f"checkout has {len(dirty)} uncommitted change(s): " + ", ".join(dirty[:6])
               + (" …" if len(dirty) > 6 else "")) if dirty else None
    return {"launch_receipt": str(receipt) if receipt is not None else None,
            "stop_receipt_present": stopped, "scheduler_stopped": finished,
            "force_stop_available": receipt is not None and not (stopped or finished),
            "reset_available": receipt is not None and (stopped or finished),
            "start_available": LAUNCH_SOURCE is not None and not pending and (stopped or finished) and not dirty,
            "start_pending": pending, "start_blocker": blocker, "start_error": _LAST_START_ERROR}


def start_command(scope: tuple[str, ...]) -> str:
    """The Start-NscRun.ps1 invocation the Start button runs, by mode (pure)."""
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    if RUNS_MODE == "production":
        launch = ("& " + quote(AGENT_DIR / "Start-NscRun.ps1") + " -Mode production -Source " + quote(LAUNCH_SOURCE)
                  + " -Repository " + quote(LAUNCH_REPOSITORY) + " -CheckoutRoot " + quote(LAUNCH_CHECKOUT_ROOT)
                  + " -Profile " + LAUNCH_PROFILE)
        if LAUNCH_HUMAN_REVIEW:
            launch += " -HumanReview"
    else:
        launch = ("& " + quote(AGENT_DIR / "Start-NscRun.ps1") + " -Mode local -InPlace -Source " + quote(LAUNCH_SOURCE)
                  + " -RunsRoot " + quote(LAUNCH_RECEIPTS_ROOT) + " -CheckoutRoot " + quote(LAUNCH_CHECKOUT_ROOT)
                  + " -Profile " + LAUNCH_PROFILE + " -ViewerPort " + str(int(LAUNCH_VIEWER_PORT)))
    if scope:
        launch += " -TaskId " + quote(",".join(scope))
    return launch


def request_local_start() -> dict[str, Any]:
    """Launch an in-place run through Start-NscRun.ps1, detached; the viewer follows it."""
    if LAUNCH_SOURCE is None or LAUNCH_CHECKOUT_ROOT is None or LAUNCH_RECEIPTS_ROOT is None:
        raise LocalStopError("this viewer was not started with launch settings; use NscRun start-here / viewer -Production")
    if RUNS_MODE == "production" and not LAUNCH_REPOSITORY:
        raise LocalStopError("this viewer has no GitHub repository to launch production against")
    scope = tuple(sorted(ENABLED_TASK_IDS))
    if not scope and scope_customized():
        raise LocalStopError("no task is enabled; click a task and press Enable for run first")
    if start_pending():
        raise LocalStopError("a start is already in progress")
    dirty = source_dirty_files(LAUNCH_SOURCE)
    if dirty:
        raise LocalStopError("the checkout has uncommitted changes; commit or discard them first: " + ", ".join(dirty[:6]))
    marker = _start_pending_path()
    assert marker is not None
    marker.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log = LAUNCH_CHECKOUT_ROOT / f"viewer-start-{stamp}.log"
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    launch = start_command(scope)
    # Visible console: the launcher's output is shown and teed into the log, a
    # terminating error is captured, and a failed launch keeps the window open.
    command = ("$host.UI.RawUI.WindowTitle = 'NscRun start (close or Ctrl+C to abort)'; try { " + launch
               + " *>&1 | Tee-Object -FilePath " + quote(log) + " } catch { $_ | Out-String | Tee-Object -FilePath "
               + quote(log) + " -Append; Read-Host 'Launch failed; press Enter to close'; exit 1 }")
    global _LAST_START_ERROR
    _LAST_START_ERROR = None
    pid = _detached_powershell(command, visible=True)
    marker.write_text(json.dumps({"requested_at_utc": utc_now(), "helper_pid": pid, "log": str(log)}), encoding="utf-8")
    return {"status": "start_requested", "helper_pid": pid, "log": str(log)}


def _detached_powershell(command: str, *, visible: bool = False) -> int:
    """Run a PowerShell command in the background and return its pid.

    Windows PowerShell 5.1 needs a console to start at all; DETACHED_PROCESS
    gives it none and it exits silently with 0 before running anything. The
    helper gets its own console in its own process group: hidden by default,
    visible for the Start launch so the operator can watch it and Ctrl+C it.
    """
    import subprocess
    console = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if visible else getattr(subprocess, "CREATE_NO_WINDOW", 0)
    flags = console | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                               creationflags=flags, close_fds=True,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return process.pid


def request_local_force_stop(run_root: Path) -> dict[str, Any]:
    """Run Stop-NscRun.ps1 -Force for this run, keeping the viewer alive to report it."""
    receipt = launch_receipt_for(run_root)
    if receipt is None or not receipt.is_file():
        raise LocalStopError("this viewer was not started with a launch receipt; use NscRun stop -Force")
    script = AGENT_DIR / "Stop-NscRun.ps1"
    command = ("& '" + str(script).replace("'", "''") + "' -Receipt '" + str(receipt).replace("'", "''")
               + "' -TimeoutSeconds 5 -Force -KeepViewer")
    pid = _detached_powershell(command)
    return {"status": "force_stop_started", "helper_pid": pid, "launch_receipt": str(receipt)}


def request_local_reset(run_root: Path, *, viewer_pid: int | None) -> dict[str, Any]:
    """Hand the reset to a detached shell that waits for this viewer to exit first."""
    receipt = launch_receipt_for(run_root)
    if receipt is None or not receipt.is_file():
        raise LocalStopError("this viewer was not started with a launch receipt; use NscRun reset -Force")
    if not local_operator_state(run_root)["reset_available"]:
        raise LocalStopError("stop the run first (Stop run, or Stop now); reset waits for the scheduler to exit")
    script = AGENT_DIR / "Reset-NscRun.ps1"
    wait = ("Wait-Process -Id " + str(int(viewer_pid)) + " -Timeout 60 -ErrorAction SilentlyContinue; "
            if viewer_pid is not None else "Start-Sleep -Seconds 3; ")
    command = (wait + "& '" + str(script).replace("'", "''") + "' -Receipt '" + str(receipt).replace("'", "''") + "' -Force")
    pid = _detached_powershell(command)
    return {"status": "reset_scheduled", "helper_pid": pid, "launch_receipt": str(receipt)}


class LocalStopError(RuntimeError):
    """The viewer could not turn the button press into a stop request."""


def request_local_stop(run_root: Path) -> dict[str, Any]:
    """Ask the local run under ``run_root`` to stop, exactly as Stop-NscRun does.

    Writes the run's stop-request.json and wakes the scheduler through its own
    authenticated endpoint (found beside the run's Source, which the local
    manifest names). Refuses a second request while the first is pending so
    the button cannot be mistaken for a force stop. Never terminates anything.
    """
    from Pipeline.TaskReviewAgent.request_run_stop import wake_scheduler, write_stop_request

    run_root = Path(run_root)
    if not run_root.is_dir():
        raise LocalStopError("local run root is missing")
    if (run_root / "stop-request.json").is_file():
        raise LocalStopError("a stop was already requested; the scheduler is draining its workers")
    source = _run_source(run_root)
    if source is None:
        raise LocalStopError("no manifest in this run names a source repository")
    path = write_stop_request(run_root, reason="GauntletView stop button")
    woke = wake_scheduler(source, reason="GauntletView stop button")
    return {"status": "stop_requested", "stop_request_path": str(path), "wake_sent": woke}


def main() -> int:
    parser = argparse.ArgumentParser(description="Live NSC gauntlet task-graph view.")
    parser.add_argument("--tasks", help="path to a checkout's Tasks/ directory")
    parser.add_argument("--state", help="directory containing .task-review-agent")
    parser.add_argument("--local-run-root", help="exact local rehearsal run directory; disables production discovery")
    parser.add_argument(
        "--display-task-id", action="append", dest="display_task_ids", metavar="NSC-ID",
        help="task to display independently of the run manifest; repeat for each task",
    )
    parser.add_argument("--run-dir", help="exact autonomous run directory")
    parser.add_argument("--source-commit", help="exact source commit bound to the run")
    parser.add_argument("--source-branch", help="exact attached controller branch")
    parser.add_argument("--run-id", help="exact autonomous run identity")
    parser.add_argument("--repository", help="exact GitHub owner/repository identity")
    parser.add_argument(
        "--enable-human-approval",
        action="store_true",
        help="enable the guarded local approval capability (architect-managed only)",
    )
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--launch-receipt", help="Start-NscRun launch receipt; enables the viewer's Stop now and Reset buttons")
    parser.add_argument("--local-runs-root", help="persistent mode: follow the newest local run under this local-rehearsals folder")
    parser.add_argument("--launch-source", help="persistent mode: checkout that the Start button launches in place")
    parser.add_argument("--launch-checkout-root", help="persistent mode: checkout root for launched runs")
    parser.add_argument("--launch-profile", default="all-claude")
    parser.add_argument("--launch-task-id", help="persistent mode: comma-separated scope for launched runs")
    parser.add_argument("--runs-mode", choices=("local", "production"), default="local",
                        help="persistent mode: follow local rehearsals (default) or the checkout root's production runs")
    parser.add_argument("--launch-repository", help="persistent production mode: GitHub owner/repo for start-production")
    parser.add_argument("--launch-source-branch", help="persistent production mode: the checkout's branch, for display")
    parser.add_argument("--launch-human-review", action="store_true",
                        help="persistent production mode: Start launches without the synthetic evidence pump")
    parser.add_argument("--launch-receipts-root", help="persistent mode: <root>/<run-id>/launch-receipt.json enables Stop now and Reset")
    args = parser.parse_args()
    global LAUNCH_RECEIPT_PATH
    if getattr(args, "launch_receipt", None):
        LAUNCH_RECEIPT_PATH = Path(args.launch_receipt).resolve()

    # An explicitly supplied but empty run root is an operator error, not an
    # absent argument. Treating it as absent silently selects production
    # discovery and serves a live production run from a local-only view.
    if args.local_run_root is not None and not str(args.local_run_root).strip():
        parser.error("--local-run-root requires an exact local rehearsal run directory")
    local_root = (
        Path(args.local_run_root).resolve() if args.local_run_root is not None else None
    )
    global LOCAL_RUNS_ROOT, LAUNCH_RECEIPTS_ROOT, RUNS_MODE, LAUNCH_REPOSITORY, LAUNCH_SOURCE_BRANCH, ENABLED_TASK_IDS
    global LAUNCH_HUMAN_REVIEW
    if args.runs_mode == "production":
        if local_root is not None or args.local_runs_root or args.state or args.tasks:
            parser.error("--runs-mode production takes its roots from --launch-source and --launch-checkout-root")
        if not (args.launch_source and args.launch_checkout_root and args.launch_repository):
            parser.error("--runs-mode production requires --launch-source, --launch-checkout-root and --launch-repository")
        RUNS_MODE = "production"
        LAUNCH_REPOSITORY = args.launch_repository
        LAUNCH_SOURCE_BRANCH = args.launch_source_branch
        LAUNCH_HUMAN_REVIEW = bool(args.launch_human_review)
        global LAUNCH_SOURCE, LAUNCH_CHECKOUT_ROOT, LAUNCH_PROFILE, LAUNCH_TASK_IDS, LAUNCH_VIEWER_PORT
        LAUNCH_SOURCE = Path(args.launch_source).resolve()
        LAUNCH_CHECKOUT_ROOT = Path(args.launch_checkout_root).resolve()
        LAUNCH_CHECKOUT_ROOT.mkdir(parents=True, exist_ok=True)
        LAUNCH_RECEIPTS_ROOT = (Path(args.launch_receipts_root).resolve() if args.launch_receipts_root
                                else LAUNCH_CHECKOUT_ROOT / "launch-receipts")
        LAUNCH_PROFILE = args.launch_profile or "all-claude"
        LAUNCH_TASK_IDS = tuple(item.strip() for item in (args.launch_task_id or "").split(",") if item.strip())
        LAUNCH_VIEWER_PORT = int(args.port)
        tasks_dir, state_root = LAUNCH_SOURCE / "Tasks", LAUNCH_CHECKOUT_ROOT
    elif args.local_runs_root:
        if local_root is not None or args.state or args.tasks:
            parser.error("--local-runs-root cannot be combined with --local-run-root, --state or --tasks")
        LOCAL_RUNS_ROOT = Path(args.local_runs_root).resolve()
        LOCAL_RUNS_ROOT.mkdir(parents=True, exist_ok=True)
        LAUNCH_RECEIPTS_ROOT = Path(args.launch_receipts_root).resolve() if args.launch_receipts_root else None
        LAUNCH_SOURCE = Path(args.launch_source).resolve() if args.launch_source else None
        LAUNCH_CHECKOUT_ROOT = Path(args.launch_checkout_root).resolve() if args.launch_checkout_root else None
        LAUNCH_PROFILE = args.launch_profile or "all-claude"
        LAUNCH_TASK_IDS = tuple(item.strip() for item in (args.launch_task_id or "").split(",") if item.strip())
        LAUNCH_VIEWER_PORT = int(args.port)
        local_root = newest_local_run(LOCAL_RUNS_ROOT)
        local_root = local_root.resolve() if local_root is not None else None
        if local_root is not None and LAUNCH_RECEIPTS_ROOT is not None:
            LAUNCH_RECEIPT_PATH = LAUNCH_RECEIPTS_ROOT / local_root.name / "launch-receipt.json"
        tasks_dir, state_root = (local_root, local_root) if local_root is not None else (LOCAL_RUNS_ROOT, LOCAL_RUNS_ROOT)
    elif local_root is not None:
        if args.state or args.tasks:
            parser.error("--local-run-root cannot be combined with --state or --tasks")
        tasks_dir, state_root = local_root, local_root
    else:
        tasks_dir, state_root = discover_roots(args.tasks, args.state)
    if local_root is None and not tasks_dir.is_dir():
        raise SystemExit(f"Tasks directory not found: {tasks_dir}")

    managed_values = (
        args.run_dir,
        args.source_commit,
        args.source_branch,
        args.run_id,
        args.repository,
    )
    managed = all(value is not None for value in managed_values)
    if any(value is not None for value in managed_values) and not managed:
        parser.error(
            "--run-dir, --source-commit, --source-branch, --run-id, and "
            "--repository must be supplied together"
        )
    # An explicit local rehearsal has no production run identity, and the
    # approval path builds a real GhIssueBackend. Refuse the combination.
    if local_root is not None and (
        any(value is not None for value in managed_values) or args.enable_human_approval
    ):
        parser.error(
            "--local-run-root has no production run identity and cannot enable human approval"
        )
    # Display scope resolves against committed contracts, which a local run does
    # not publish. Refuse it here rather than letting the contract check below
    # report the run's own tasks as missing.
    if local_root is not None and args.display_task_ids is not None:
        parser.error(
            "--local-run-root selects its run's own tasks; --display-task-id is not supported"
        )
    if args.enable_human_approval and not managed:
        parser.error("--enable-human-approval requires an exact architect-managed identity")
    run_dir = Path(args.run_dir).resolve() if managed else None
    if run_dir is not None:
        manifest = read_json(run_dir / "manifest.json")
        if not isinstance(manifest, dict):
            parser.error(f"Exact autonomous run manifest not found: {run_dir}")
        expected = {
            "run_id": args.run_id,
            "github_repository": args.repository,
            "initial_source_commit": args.source_commit,
        }
        changed = [name for name, value in expected.items() if manifest.get(name) != value]
        manifest_source = manifest.get("source_repository")
        try:
            source_matches = (
                isinstance(manifest_source, str)
                and Path(manifest_source).resolve() == tasks_dir.parent
            )
        except OSError:
            source_matches = False
        if not source_matches:
            changed.append("source_repository")
        if git_branch(tasks_dir.parent) != args.source_branch:
            changed.append("source_branch")
        if changed:
            parser.error("Exact autonomous run identity mismatch: " + ", ".join(changed))
        manifest_targets = tuple(sorted(set(manifest.get("target_task_ids") or [])))
        requested_targets = tuple(sorted(set(args.display_task_ids or [])))
        if requested_targets != manifest_targets:
            parser.error("Display roots must equal the exact autonomous run target roots")
    ENABLED_TASK_IDS = load_enabled_scope()
    _discard_stale_start_marker()
    try:
        Handler.snapshot = Snapshot(
            tasks_dir,
            state_root,
            display_task_ids=args.display_task_ids,
            run_dir=run_dir,
            local_run_root=local_root,
            source_branch=args.source_branch if managed else LAUNCH_SOURCE_BRANCH,
        )
    except ValueError as error:
        parser.error(str(error))
    if Handler.snapshot.display_task_ids is not None:
        missing = set(Handler.snapshot.display_task_ids) - Handler.snapshot.load_contracts().keys()
        if missing:
            parser.error("Display task contracts not found: " + ", ".join(sorted(missing)))
    if local_root is not None:
        # Fail closed before serving invalid or stale state. A bad run root is
        # an operator argument error, so report it the way every other bad
        # argument is reported rather than as an unhandled traceback.
        try:
            if local_root is not None:
                Handler.snapshot.build()
        except (ValueError, OSError) as error:
            if LOCAL_RUNS_ROOT is None:
                parser.error(f"Local rehearsal run rejected: {error}")
            # Persistent viewer: show the newest run as not followed, offer Start.
            print(f"Local rehearsal run not followed: {error}", file=sys.stderr)
            Handler.snapshot.reject_local_run(error)
    Handler.health = None
    Handler.approval = None
    if managed:
        Handler.health = {
            "schema": HEALTH_SCHEMA,
            "status": "ok",
            "identity": {
                "source": str(tasks_dir.parent),
                "source_branch": args.source_branch,
                "source_commit": args.source_commit,
                "state_root": str(state_root),
                "run_id": args.run_id,
                "run_dir": str(run_dir),
                "repository": args.repository,
                "display_task_ids": list(Handler.snapshot.display_task_ids or ()),
                "descendants": "durable_decomposition_closure",
                "human_approval_enabled": args.enable_human_approval,
            },
        }
    Handler.origin = f"http://127.0.0.1:{args.port}"
    if args.enable_human_approval:
        from Pipeline.TaskReviewAgent.GauntletView.approval import (
            GauntletApprovalController,
        )
        from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
        from Pipeline.TaskReviewAgent.issue_workflow_store import (
            GhIssueBackend,
            IssueWorkflowService,
            VINCENT_INBOX_TITLE,
        )

        backend = GhIssueBackend(
            source_root=tasks_dir.parent,
            repository=args.repository,
        )
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda task_id: load_committed_task(tasks_dir.parent, task_id),
            worker_id="gauntlet-view-human-approval",
            vincent_inbox_title=VINCENT_INBOX_TITLE,
        )

        def current_identity() -> dict[str, Any]:
            current = read_json(run_dir / "manifest.json") if run_dir else None
            current = current if isinstance(current, dict) else {}
            current_source = current.get("source_repository")
            try:
                normalized_source = (
                    str(Path(current_source).resolve())
                    if isinstance(current_source, str)
                    else None
                )
            except OSError:
                normalized_source = None
            return {
                "source": normalized_source,
                "source_branch": git_branch(tasks_dir.parent),
                "source_commit": current.get("initial_source_commit"),
                "state_root": str(state_root),
                "run_id": current.get("run_id"),
                "run_dir": str(run_dir),
                "repository": current.get("github_repository"),
                "display_task_ids": sorted(set(current.get("target_task_ids") or [])),
                "descendants": "durable_decomposition_closure",
                "human_approval_enabled": True,
            }

        Handler.approval = GauntletApprovalController(
            enabled=True,
            identity=Handler.health["identity"],
            service=service,
            state_provider=Handler.snapshot.build,
            identity_reader=current_identity,
        )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True

    run_dir = (
        local_root if local_root is not None
        else Handler.snapshot.run_dir or newest_autonomous_run(state_root)
    )
    print(f"  contracts : {tasks_dir}")
    print(f"  run state : {state_root}")
    print(f"  active run: {run_dir.name if run_dir else '(none found)'}")
    print("  display   : " + (", ".join(Handler.snapshot.display_task_ids or ()) or "all contracts (optional run filter)"))
    print(f"\n  http://127.0.0.1:{args.port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
