#!/usr/bin/env python3
"""Regressions for the durable run-evidence report.

Classification: pure/component tests over a synthetic run-evidence tree built
under ``tempfile``. No Unity asset, no tracked repository file, no GitHub call,
no Docker, no provider, and no real task are involved. Every artifact these
tests read is written by the test itself in the exact shape the production
writers use.

Contract or gate mapping: regression-only invariants for the ten-task gauntlet
evidence report. They prove that a finished run can be described from durable
artifacts alone and that missing evidence is reported as unavailable. They
prove no task acceptance criterion and no completion gate, and they are not
evidence that any gauntlet ran.

The fixture models one multi-worker run containing exactly the shapes the
report has to survive:

* ten top-level tasks NSC-911 through NSC-920;
* one decomposition child created from NSC-911;
* one task that was interrupted and retried, so it owns two worker run IDs;
* one provider call whose provider exposed no token usage;
* one task with a historical human stop that a strict graph-complete receipt
  later resolves, plus an incomplete-run regression where the same stop must
  remain current and must never be shown as a pass;
* a worker output root and an AgentRuntime root that a second autonomous run
  also wrote into, because both roots are shared and long-lived in production
  and the earlier run's artifacts for the same task IDs are exactly what an
  evidence report must refuse to absorb.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.run_evidence_report import (  # noqa: E402
    UNAVAILABLE,
    RunEvidenceError,
    build_report,
    load_run_evidence,
    main,
    render_markdown,
)

RUN_ID = "ten-task-gauntlet-run"
EARLIER_RUN_ID = "ten-task-gauntlet-run-earlier"
TARGETS = tuple(f"NSC-{number}" for number in range(911, 921))
CHILD = "NSC-921"
BASE = dt.datetime(2026, 9, 5, 12, 0, 0, tzinfo=dt.timezone.utc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def at(offset_seconds: float) -> str:
    moment = BASE + dt.timedelta(seconds=offset_seconds)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _append(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def worker_argv(
    task_id: str,
    worker_run: str,
    *,
    supervisor_provider: str | None = "claude",
    execution_provider: str = "claude",
    supervisor_model: str = "claude-opus-5",
    execution_model: str = "claude-sonnet-5",
) -> list[str]:
    """The exact worker command shape ``build_worker_command`` produces.

    The scheduler writes this argv into every ``worker_launched`` record, so it
    is the run's own durable statement of the providers and models it launched.
    """

    argv = [
        "python",
        "-u",
        "Pipeline/TaskReviewAgent/host_worker_launcher.py",
        "--task-id",
        task_id,
        "--mode",
        "openai",
        "--worker-id",
        "w-1",
        "--execution-provider",
        execution_provider,
        "--max-turns",
        "32",
        "--model",
        supervisor_model,
        "--execution-model",
        execution_model,
    ]
    if supervisor_provider is not None:
        argv.extend(("--supervisor-provider", supervisor_provider))
    argv.extend(("--run-id", worker_run))
    return argv


def build_fixture(root: Path, *, with_timeline: bool = True) -> tuple[Path, Path, Path]:
    """A complete multi-worker run: retry, decomposition child, human stop."""

    run_root = root / "autonomous-runs" / RUN_ID
    output_root = root / "outputs"
    manifest_sha = hashlib.sha256(RUN_ID.encode("ascii")).hexdigest()

    _write(
        run_root / "manifest.json",
        {
            "schema_version": "1.0",
            "run_id": RUN_ID,
            "sha256": manifest_sha,
            "source_repository": str(root / "source"),
            "github_repository": "fixture-owner/pipeline-rehearsal",
            "initial_source_commit": "a" * 40,
            "initial_source_tree": "b" * 40,
            "target_task_ids": list(TARGETS),
            "excluded_task_ids": ["NSC-042"],
            "max_capacity": 4,
            "runtime_configuration": {
                "architect_provider": "codex",
                "architect_model": "gpt-5.6-sol",
                "execution_provider": "claude",
                "execution_model": "claude-sonnet-5",
                "supervisor_provider": "claude",
                "provider_allowlist": ["claude", "codex"],
            },
        },
    )
    _write(
        run_root / "progress.json",
        {
            "schema_version": "1.0",
            "manifest_sha256": manifest_sha,
            "poll_cycles_total": 24,
            "architect_invocations_total": 12,
            "worker_launches_total": 12,
            "synthetic_pump_calls_total": 0,
            "fallback_waits_total": 2,
            "wakeups_total": 6,
            "baseline_verified": True,
            "last_fingerprint": None,
            "last_fallback_fingerprint": None,
        },
    )
    _write(
        run_root / "graph-complete.json",
        {
            "schema_version": "1.0",
            "manifest_sha256": manifest_sha,
            "evidence_fingerprint": "c" * 64,
            "source_commit": "d" * 40,
            "source_tree": "e" * 40,
            "relevant_task_ids": list(TARGETS) + [CHILD],
            "lifetime_counters": [["poll_cycles_total", 24]],
            "receipt_sha256": "f" * 64,
        },
    )

    events = run_root / "events.jsonl"
    _append(events, {"schema_version": "1.0", "event": "scheduler_started", "timestamp_utc": at(0), "scheduler_id": "s1", "max_workers": 4})

    # Two workers overlap, so peak concurrency is provably two.
    plan = [
        # (task, run suffix, launch, finish, terminal event)
        (TARGETS[0], "r1", 10, 70, "worker_finished"),
        (TARGETS[1], "r1", 20, 100, "worker_finished"),
        (TARGETS[2], "r1", 110, 150, "worker_finished"),
        # NSC-914 is interrupted and retried: two run IDs, never merged.
        (TARGETS[3], "r1", 160, 180, "worker_failed"),
        (TARGETS[3], "r2", 190, 240, "worker_finished"),
        (TARGETS[4], "r1", 250, 300, "worker_finished"),
        (TARGETS[5], "r1", 310, 350, "worker_finished"),
        (TARGETS[6], "r1", 360, 400, "worker_finished"),
        (TARGETS[7], "r1", 410, 450, "worker_finished"),
        # NSC-919 stops for a human. That is a stop, never a pass.
        (TARGETS[8], "r1", 460, 500, "worker_finished"),
        (TARGETS[9], "r1", 510, 560, "worker_finished"),
        (CHILD, "r1", 570, 610, "worker_finished"),
    ]
    for task_id, suffix, launch, finish, terminal in plan:
        worker_run = f"{task_id.lower()}-{suffix}"
        _append(
            events,
            {
                "schema_version": "1.0",
                "event": "worker_launched",
                "timestamp_utc": at(launch),
                "task_id": task_id,
                "run_id": worker_run,
                "worker_id": f"w-{suffix}",
                "work_type": "implementation",
                "argv": worker_argv(task_id, worker_run),
            },
        )
        _append(
            events,
            {
                "schema_version": "1.0",
                "event": terminal,
                "timestamp_utc": at(finish),
                "task_id": task_id,
                "run_id": worker_run,
                "worker_id": f"w-{suffix}",
                "returncode": 1 if terminal == "worker_failed" else 0,
                "reason": "worker process exited non-zero" if terminal == "worker_failed" else None,
            },
        )
    # The decomposition of NSC-911 that created the child.
    _append(
        events,
        {
            "schema_version": "1.0",
            "event": "architect_completed",
            "timestamp_utc": at(105),
            "task_id": TARGETS[0],
            "work_type_recommendation": "decomposition",
            "child_task_ids": [CHILD],
        },
    )
    _append(events, {"schema_version": "1.0", "event": "scheduler_stopped", "timestamp_utc": at(620), "scheduler_id": "s1", "reason": "graph_complete"})

    if with_timeline:
        timeline = run_root / "run_timeline.jsonl"
        _append(
            timeline,
            {
                "schema_version": "1.0",
                "timestamp_utc": at(0),
                "run_id": RUN_ID,
                "event": "autonomous_run_started",
                "max_capacity": 4,
            },
        )
        _append(
            timeline,
            {
                "schema_version": "1.0",
                "timestamp_utc": at(630),
                "run_id": RUN_ID,
                "event": "graph_complete_receipt_written",
                "receipt_sha256": "f" * 64,
            },
        )

    # Worker run directories: the per-task timing and terminal authority.
    for task_id, suffix, launch, finish, terminal in plan:
        worker_run = f"{task_id.lower()}-{suffix}"
        run_dir = output_root / task_id / worker_run
        _write(
            run_dir / "run.json",
            {
                "schema_version": "1.0",
                "run_id": worker_run,
                "task_id": task_id,
                "worker_id": f"w-{suffix}",
                "started_at_utc": at(launch),
            },
        )
        if terminal == "worker_failed":
            status, exit_code = "provider_failure", 3
        elif task_id == TARGETS[8]:
            status, exit_code = "human_action_required", 0
        else:
            status, exit_code = "delivered", 0
        _write(
            run_dir / "run_result.json",
            {
                "schema_version": "1.0",
                "run_id": worker_run,
                "worker_id": f"w-{suffix}",
                "task_id": task_id,
                "source_head": "a" * 40,
                "task_contract_sha256": hashlib.sha256(task_id.encode()).hexdigest(),
                "terminal_status": status,
                "outcome_authority": "worker",
                "issue_number": 100 + int(task_id.split("-")[1]),
                "exit_code": exit_code,
                "pid": 4242,
                "finished_at_utc": at(finish),
            },
        )

    # AgentRuntime provider calls under a root shared by every run that ever
    # used this checkout. The two architect calls are the ones this run's own
    # journal claims; the crew calls happened inside worker task checkouts and
    # nothing this run owns names their invocation IDs, so they must be
    # excluded rather than absorbed. The second architect call exposes no token
    # usage, which must surface as unavailable rather than as zero.
    claimed = [
        ("arch-1", 20, "architect", "openai-codex", "gpt-5.6-sol", {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200}),
        ("arch-2", 300, "architect", "openai-codex", "gpt-5.6-sol", None),
    ]
    unclaimed = [
        ("sup-1", "task_supervisor", "openai-codex", "gpt-5.6-sol", {"input_tokens": 500, "output_tokens": 100, "total_tokens": 600}),
        ("dec-1", "task_decomposer", "claude-code", "claude-sonnet-5", {"input_tokens": 800, "output_tokens": 300, "total_tokens": 1100}),
        ("rev-1", "decomposition_reviewer", "openai-codex", "gpt-5.6-sol", {"input_tokens": 400, "output_tokens": 150, "total_tokens": 550}),
        ("imp-1", "implementer", "claude-code", "claude-sonnet-5", {"input_tokens": 2000, "output_tokens": 900, "total_tokens": 2900}),
        ("tst-1", "test_author", "claude-code", "claude-sonnet-5", {"input_tokens": 700, "output_tokens": 250, "total_tokens": 950}),
        ("val-1", "validator", "claude-code", "claude-sonnet-5", None),
        ("rep-1", "repair", "claude-code", "claude-sonnet-5", {"input_tokens": 300, "output_tokens": 120, "total_tokens": 420}),
    ]
    for agent_run_id, moment, _role, provider, model, _usage in claimed:
        _append(
            events,
            {
                "schema_version": "1.0",
                "event": "architect_provider_call",
                "timestamp_utc": at(moment),
                "analysis_id": f"analysis-batch-{agent_run_id}",
                "agent_runtime_run_id": agent_run_id,
                "provider": provider,
                "model": model,
                "advisory_artifact_path": f"/fixture/{agent_run_id}.json",
            },
        )
    for agent_run_id, role, provider, model, usage in (
        [(item[0], item[2], item[3], item[4], item[5]) for item in claimed] + unclaimed
    ):
        _write(
            output_root / "crew" / "agent_runtime" / agent_run_id / "result.json",
            {
                "schema_version": "1.0",
                "run_id": agent_run_id,
                "provider": provider,
                "model": model,
                "role": role,
                "status": "succeeded",
                "duration_seconds": 12.5,
                "usage": (
                    None
                    if usage is None
                    else {**usage, "estimated_cost_usd": 0.01}
                ),
            },
        )
    return run_root, output_root, root


def build_earlier_run(root: Path) -> Path:
    """A second autonomous run that shares this checkout's durable roots.

    This is the production shape that broke the first report: one operator, one
    checkout, several autonomous runs. The earlier run attempted the same task
    IDs, wrote its worker directories under the same output root, and wrote its
    architect call under the same AgentRuntime root. Nothing distinguishes its
    artifacts from the later run's except the scheduler run IDs its own journal
    launched and the provider calls its own journal claimed.
    """

    run_root = root / "autonomous-runs" / EARLIER_RUN_ID
    output_root = root / "outputs"
    manifest_sha = hashlib.sha256(EARLIER_RUN_ID.encode("ascii")).hexdigest()
    _write(
        run_root / "manifest.json",
        {
            "schema_version": "1.0",
            "run_id": EARLIER_RUN_ID,
            "sha256": manifest_sha,
            "source_repository": str(root / "source"),
            "github_repository": "fixture-owner/pipeline-rehearsal",
            "initial_source_commit": "1" * 40,
            "initial_source_tree": "2" * 40,
            "target_task_ids": list(TARGETS),
            "excluded_task_ids": ["NSC-042"],
            "max_capacity": 4,
            "runtime_configuration": {
                "architect_provider": "codex",
                "architect_model": "gpt-5.6-sol",
                "execution_provider": "claude",
                "execution_model": "claude-sonnet-5",
                "supervisor_provider": "claude",
                "provider_allowlist": ["claude", "codex"],
            },
        },
    )

    events = run_root / "events.jsonl"
    # The earlier run attempted the last target three times and failed.
    earlier_plan = [
        (TARGETS[9], f"{TARGETS[9].lower()}-old-1", -2400, -2300, "worker_failed"),
        (TARGETS[9], f"{TARGETS[9].lower()}-old-2", -2200, -2100, "worker_failed"),
        (TARGETS[9], f"{TARGETS[9].lower()}-old-3", -2000, -1900, "worker_failed"),
    ]
    for task_id, worker_run, launch, finish, terminal in earlier_plan:
        _append(
            events,
            {
                "schema_version": "1.0",
                "event": "worker_launched",
                "timestamp_utc": at(launch),
                "task_id": task_id,
                "run_id": worker_run,
                "worker_id": "w-old",
                "argv": worker_argv(task_id, worker_run),
            },
        )
        _append(
            events,
            {
                "schema_version": "1.0",
                "event": terminal,
                "timestamp_utc": at(finish),
                "task_id": task_id,
                "run_id": worker_run,
                "worker_id": "w-old",
                "returncode": 1,
                "reason": "worker process exited non-zero",
            },
        )
        run_dir = output_root / task_id / worker_run
        _write(
            run_dir / "run.json",
            {
                "schema_version": "1.0",
                "run_id": worker_run,
                "task_id": task_id,
                "worker_id": "w-old",
                "started_at_utc": at(launch),
            },
        )
        _write(
            run_dir / "run_result.json",
            {
                "schema_version": "1.0",
                "run_id": worker_run,
                "worker_id": "w-old",
                "task_id": task_id,
                "source_head": "1" * 40,
                "task_contract_sha256": hashlib.sha256(task_id.encode()).hexdigest(),
                "terminal_status": "provider_failure",
                "outcome_authority": "worker",
                "issue_number": 100 + int(task_id.split("-")[1]),
                "exit_code": 3,
                "pid": 4243,
                "finished_at_utc": at(finish),
            },
        )
    _append(
        events,
        {
            "schema_version": "1.0",
            "event": "architect_provider_call",
            "timestamp_utc": at(-2500),
            "analysis_id": "analysis-batch-arch-old-1",
            "agent_runtime_run_id": "arch-old-1",
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "advisory_artifact_path": "/fixture/arch-old-1.json",
        },
    )
    _write(
        output_root / "crew" / "agent_runtime" / "arch-old-1" / "result.json",
        {
            "schema_version": "1.0",
            "run_id": "arch-old-1",
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "role": "architect",
            "status": "succeeded",
            "duration_seconds": 30.0,
            "usage": {
                "input_tokens": 9000,
                "output_tokens": 9000,
                "total_tokens": 18000,
                "estimated_cost_usd": 1.0,
            },
        },
    )
    _append(
        run_root / "run_timeline.jsonl",
        {
            "schema_version": "1.0",
            "timestamp_utc": at(-2600),
            "run_id": EARLIER_RUN_ID,
            "event": "autonomous_run_started",
            "max_capacity": 4,
        },
    )
    return run_root


def load(root: Path, run_root: Path, output_root: Path):
    return load_run_evidence(
        run_root=run_root,
        worker_output_root=output_root,
        provider_call_roots=[output_root],
    )


def test_reports_run_window_graph_completion_and_scope() -> None:
    """Overall timing, graph-complete state, and the exclusion proofs."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        report = build_report(load(root, run_root, output_root))

        window = report["run_window"]
        require(window["started_at_utc"] == at(0), str(window))
        require(window["finished_at_utc"] == at(630), str(window))
        require(window["elapsed_seconds"] == 630.0, str(window))
        require("timeline" in window["finish_source"], str(window))

        graph = report["graph_completion"]
        require(graph["graph_complete"] is True, str(graph))
        require(graph["completed_at_utc"] == at(630), str(graph))
        require(graph["source_commit"] == "d" * 40, str(graph))

        scope = report["scope"]
        require(scope["target_task_count"] == 10, str(scope))
        require(list(scope["target_task_ids"]) == list(TARGETS), str(scope))
        require(scope["nsc_042_excluded"] is True, "NSC-042 exclusion must be proven from the manifest")
        require(scope["nsc_042_never_ran"] is True, "NSC-042 must have no worker run")
        require(scope["decomposition_children"] == [CHILD], str(scope))
        require(scope["scale_proof"]["is_ten_task_scope"] is True, str(scope["scale_proof"]))
        require(scope["scale_proof"]["eighty_task_run_observed"] is False, "no 80-task run")
        require(scope["scale_proof"]["thousand_task_run_observed"] is False, "no 1000-task run")


def test_per_task_timing_counts_a_retry_once_per_run_id() -> None:
    """An interrupted and resumed task is one task with two bounded attempts."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-retry-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        report = build_report(load(root, run_root, output_root))
        tasks = {entry["task_id"]: entry for entry in report["tasks"]}

        require(len(tasks) == 11, f"ten targets plus one child: {sorted(tasks)}")
        require(tasks[CHILD]["origin"] == "decomposition_child", str(tasks[CHILD]))

        retried = tasks[TARGETS[3]]
        require(retried["attempt_count"] == 2, str(retried))
        require(retried["retry_count"] == 1, str(retried))
        # Elapsed spans first start to last finish; active time is the sum of
        # the two bounded attempts and must not double count the gap.
        require(retried["started_at_utc"] == at(160), str(retried))
        require(retried["finished_at_utc"] == at(240), str(retried))
        require(retried["elapsed_seconds"] == 80.0, str(retried))
        require(retried["active_worker_seconds"] == 70.0, f"20 + 50 seconds of work: {retried}")
        require(retried["terminal_status"] == "graph_complete", str(retried))
        require(retried["latest_attempt_terminal_status"] == "delivered", str(retried))
        require(
            retried["terminal_status_source"] == "strict graph-complete receipt",
            str(retried),
        )

        simple = tasks[TARGETS[0]]
        require(simple["attempt_count"] == 1 and simple["elapsed_seconds"] == 60.0, str(simple))


def test_graph_completion_resolves_an_earlier_human_stop_without_erasing_it() -> None:
    """A strict completion receipt outranks an earlier worker-attempt stop."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-human-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        report = build_report(load(root, run_root, output_root))
        tasks = {entry["task_id"]: entry for entry in report["tasks"]}

        stopped = tasks[TARGETS[8]]
        require(stopped["terminal_status"] == "graph_complete", str(stopped))
        require(
            stopped["latest_attempt_terminal_status"] == "human_action_required",
            str(stopped),
        )
        require(stopped["human_action_stop"] is False, str(stopped))
        require(stopped["historical_human_action_stop"] is True, str(stopped))
        require(stopped["succeeded"] is True, "the strict receipt must remain final authority")
        require(
            report["human_action_stops"] == [],
            str(report["human_action_stops"]),
        )
        require(
            [s["task_id"] for s in report["historical_human_action_stops"]]
            == [TARGETS[8]],
            str(report["historical_human_action_stops"]),
        )
        markdown = render_markdown(report)
        require("HUMAN ACTION REQUIRED" not in markdown, "a resolved stop looked current")
        require("Historical human-action stop" in markdown, "history was erased")
        require("later resolved" in markdown, "the final authority was not explained")


def test_unfinished_human_action_stop_is_never_reported_as_a_pass() -> None:
    """Without a strict receipt, the latest human stop remains current."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-current-human-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        (run_root / "graph-complete.json").unlink()
        (run_root / "run_timeline.jsonl").unlink()
        report = build_report(load(root, run_root, output_root))
        stopped = {entry["task_id"]: entry for entry in report["tasks"]}[TARGETS[8]]

        require(stopped["terminal_status"] == "human_action_required", str(stopped))
        require(stopped["human_action_stop"] is True, str(stopped))
        require(stopped["historical_human_action_stop"] is True, str(stopped))
        require(stopped["succeeded"] is False, "a current human stop became a pass")
        require(
            [s["task_id"] for s in report["human_action_stops"]] == [TARGETS[8]],
            str(report["human_action_stops"]),
        )
        markdown = render_markdown(report)
        require("HUMAN ACTION REQUIRED" in markdown, "the current stop was hidden")
        require("this is a stop, not a pass" in markdown, "the stop was not labelled")


def test_tokens_are_reported_by_role_and_unavailable_is_explicit() -> None:
    """Only this run's calls are counted, and partial usage stays unavailable."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-tokens-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        report = build_report(load(root, run_root, output_root))
        calls = report["provider_calls"]

        # Exactly the two architect invocations this run's journal claims. The
        # seven crew results under the same shared root belong to worker task
        # checkouts that nothing in this run's journal names.
        require(calls["claimed_call_count"] == 2, str(calls))
        require(calls["total_calls"] == 2, str(calls))
        require(calls["unattributed_result_count"] == 7, str(calls))
        require(calls["missing_claimed_call_ids"] == [], str(calls))
        buckets = {f"{b['role']}:{b['provider']}": b for b in calls["by_role_and_provider"]}
        require(sorted(buckets) == ["architect:openai-codex"], sorted(buckets))
        for role in ("implementer", "validator", "task_supervisor"):
            require(
                not any(key.startswith(f"{role}:") for key in buckets),
                f"{role} calls were absorbed without a run-owned claim: {sorted(buckets)}",
            )

        # One of the two claimed calls exposed no usage, so the role total
        # cannot be proven and the published partial sums say so exactly.
        architect = buckets["architect:openai-codex"]
        require(architect["calls"] == 2, str(architect))
        require(architect["models"] == ["gpt-5.6-sol"], str(architect))
        require(architect["tokens"] == UNAVAILABLE, f"a partial role total must be explicit: {architect}")
        require("1 of 2 call(s)" in architect["tokens_unavailable_reason"], str(architect))
        require(architect["reported_total_tokens"] == 1200, str(architect))
        require(architect["usage_available_invocation_count"] == 1, str(architect))
        require(architect["missing_usage_invocation_count"] == 1, str(architect))

        markdown = render_markdown(report)
        require("unavailable" in markdown, "the Markdown must show the unavailable token count")
        require("excluded as another run's" in markdown, "the Markdown must publish the exclusion count")


def test_a_role_that_never_exposed_tokens_is_unavailable_not_zero() -> None:
    """Every token-rollup path stays provable from run-owned claims.

    The join key is the ``agent_runtime_run_id`` field, not the event name, so
    any future run-owned emitter indexes its calls the same way. This fixture
    uses a second event name deliberately: today only the scheduler's architect
    batch emits ``architect_provider_call``, and this test must not be read as
    evidence that worker crew calls are indexed in production.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-roles-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        for agent_run_id in ("imp-1", "val-1", "tst-1"):
            _append(
                run_root / "events.jsonl",
                {
                    "schema_version": "1.0",
                    "event": "worker_provider_call",
                    "timestamp_utc": at(400),
                    "agent_runtime_run_id": agent_run_id,
                },
            )
        report = build_report(load(root, run_root, output_root))
        calls = report["provider_calls"]
        require(calls["claimed_call_count"] == 5, str(calls))
        require(calls["total_calls"] == 5, str(calls))
        require(calls["unattributed_result_count"] == 4, str(calls))
        buckets = {f"{b['role']}:{b['provider']}": b for b in calls["by_role_and_provider"]}

        # A role every one of whose calls reported usage publishes a total.
        implementer = buckets["implementer:claude-code"]
        require(implementer["tokens"]["total_tokens"] == 2900, str(implementer))
        require(implementer["status"] == "complete", str(implementer))

        # A role no call of which exposed usage is unavailable, never zero.
        validator = buckets["validator:claude-code"]
        require(validator["tokens"] == UNAVAILABLE, f"unexposed tokens must be explicit: {validator}")
        require("did not expose token usage" in validator["tokens_unavailable_reason"], str(validator))
        require(validator["reported_total_tokens"] == 0, str(validator))


def test_a_second_autonomous_run_sharing_the_roots_is_never_merged() -> None:
    """Two runs, one checkout, one output root, one AgentRuntime root.

    This is the exact defect a finished live run exposed: an earlier failed run
    of the same task owned worker directories under the shared output root and
    an architect call under the shared provider root, and the report absorbed
    all of them into the later run. Each report must now describe exactly its
    own run, and each must say how much it deliberately left out.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-two-runs-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        earlier_root = build_earlier_run(root)

        report = build_report(load(root, run_root, output_root))
        tasks = {entry["task_id"]: entry for entry in report["tasks"]}
        shared = tasks[TARGETS[9]]

        # The earlier run launched this task three times, starting 2400 seconds
        # before this run began. None of that may reach this report.
        require(shared["attempt_count"] == 1, str(shared))
        require(shared["launched_attempt_count"] == 1, str(shared))
        require(shared["retry_count"] == 0, str(shared))
        require(shared["started_at_utc"] == at(510), str(shared))
        require(shared["finished_at_utc"] == at(560), str(shared))
        require(shared["elapsed_seconds"] == 50.0, str(shared))
        require(shared["terminal_status"] == "graph_complete", str(shared))
        require(shared["latest_attempt_terminal_status"] == "delivered", str(shared))
        require(
            [attempt["run_id"] for attempt in shared["attempts"]]
            == [f"{TARGETS[9].lower()}-r1"],
            str(shared["attempts"]),
        )

        # The exclusion is stated, not silent.
        require(
            any("belong to other autonomous runs" in note for note in report["evidence_notes"]),
            str(report["evidence_notes"]),
        )
        calls = report["provider_calls"]
        require(calls["total_calls"] == 2, str(calls))
        require(calls["unattributed_result_count"] == 8, str(calls))

        # The window and utilization stay bounded by this run's own evidence.
        require(report["run_window"]["started_at_utc"] == at(0), str(report["run_window"]))
        require(report["utilization"]["bounded_intervals"] == 12, str(report["utilization"]))

        # The same roots, selected for the earlier run, describe that run only.
        earlier = build_report(
            load_run_evidence(
                run_root=earlier_root,
                worker_output_root=output_root,
                provider_call_roots=[output_root],
            )
        )
        earlier_tasks = {entry["task_id"]: entry for entry in earlier["tasks"]}
        earlier_shared = earlier_tasks[TARGETS[9]]
        require(earlier["run_id"] == EARLIER_RUN_ID, str(earlier["run_id"]))
        require(earlier_shared["attempt_count"] == 3, str(earlier_shared))
        require(earlier_shared["started_at_utc"] == at(-2400), str(earlier_shared))
        require(earlier_shared["terminal_status"] == "provider_failure", str(earlier_shared))
        require(earlier_shared["succeeded"] is False, str(earlier_shared))
        earlier_calls = earlier["provider_calls"]
        require(earlier_calls["total_calls"] == 1, str(earlier_calls))
        require(
            earlier_calls["by_role_and_provider"][0]["tokens"]["total_tokens"] == 18000,
            str(earlier_calls["by_role_and_provider"]),
        )
        # The later run's twelve worker directories are foreign to this one.
        require(
            any("belong to other autonomous runs" in note for note in earlier["evidence_notes"]),
            str(earlier["evidence_notes"]),
        )
        # Neither report claims the other's tasks ran.
        require(
            all(entry["observed"] is False for key, entry in earlier_tasks.items() if key != TARGETS[9]),
            str(sorted(k for k, v in earlier_tasks.items() if v["observed"])),
        )


def test_supervisor_and_models_come_from_the_run_not_a_default() -> None:
    """The configured supervisor is reported, never this pipeline's habit."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-supervisor-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        manifest_path = run_root / "manifest.json"

        # A Claude-supervised run states so in its manifest and in every worker
        # command it launched. Reporting Codex here is the defect.
        runtime = build_report(load(root, run_root, output_root))["runtime"]
        require(runtime["supervisor_provider"] == "claude", str(runtime))
        require(runtime["supervisor_provider_source"] == "run_manifest", str(runtime))
        require(runtime["supervisor_provider_confirmed_by_launch_argv"] is True, str(runtime))
        require(runtime["architect_provider"] == "codex", str(runtime))
        require(runtime["architect_model"] == "gpt-5.6-sol", str(runtime))
        require(runtime["launched_execution_providers"] == ["claude"], str(runtime))
        require(runtime["launched_execution_models"] == ["claude-sonnet-5"], str(runtime))
        require(runtime["launched_supervisor_models"] == ["claude-opus-5"], str(runtime))
        markdown = render_markdown(build_report(load(root, run_root, output_root)))
        require("Supervisor: claude" in markdown, markdown)

        # A manifest written before the supervisor became selectable names none.
        # The worker commands still do, and that is the run's own statement.
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["runtime_configuration"]["supervisor_provider"]
        _write(manifest_path, manifest)
        runtime = build_report(load(root, run_root, output_root))["runtime"]
        require(runtime["supervisor_provider"] == "claude", str(runtime))
        require(runtime["supervisor_provider_source"] == "worker_launch_argv", str(runtime))

        # With neither statement the historical default is reported as exactly
        # that: the documented load behaviour of a pre-selection manifest, and
        # labelled so a reader never mistakes it for a recorded selection.
        events_path = run_root / "events.jsonl"
        stripped = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            record.pop("argv", None)
            stripped.append(json.dumps(record, sort_keys=True))
        events_path.write_text("\n".join(stripped) + "\n", encoding="utf-8", newline="\n")
        runtime = build_report(load(root, run_root, output_root))["runtime"]
        require(runtime["supervisor_provider"] == "codex", str(runtime))
        require(runtime["supervisor_provider_source"] == "historical_default", str(runtime))
        require(runtime["supervisor_provider_confirmed_by_launch_argv"] is False, str(runtime))
        require(runtime["launched_execution_providers"] == UNAVAILABLE, str(runtime))
        require(runtime["launched_supervisor_models"] == UNAVAILABLE, str(runtime))


def test_conflicting_durable_identities_are_refused() -> None:
    """A contradiction between durable records is a refusal, never a merge."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-conflict-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        events_path = run_root / "events.jsonl"
        original = events_path.read_text(encoding="utf-8")

        # The manifest and the launched workers disagree about the supervisor.
        manifest_path = run_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["runtime_configuration"]["supervisor_provider"] = "codex"
        _write(manifest_path, manifest)
        try:
            build_report(load(root, run_root, output_root))
        except RunEvidenceError as exc:
            require("worker launches name" in str(exc), str(exc))
        else:
            raise AssertionError("a supervisor contradiction was accepted")
        manifest["runtime_configuration"]["supervisor_provider"] = "claude"
        _write(manifest_path, manifest)

        # Two workers of the same run name different supervisors.
        _append(
            events_path,
            {
                "schema_version": "1.0",
                "event": "worker_launched",
                "timestamp_utc": at(620),
                "task_id": TARGETS[1],
                "run_id": f"{TARGETS[1].lower()}-r2",
                "worker_id": "w-r2",
                "argv": worker_argv(
                    TARGETS[1], f"{TARGETS[1].lower()}-r2", supervisor_provider="codex"
                ),
            },
        )
        try:
            build_report(load(root, run_root, output_root))
        except RunEvidenceError as exc:
            require("more than one supervisor provider" in str(exc), str(exc))
        else:
            raise AssertionError("disagreeing worker launches were accepted")
        events_path.write_text(original, encoding="utf-8", newline="")

        # One scheduler run ID claimed by two different launches.
        _append(
            events_path,
            {
                "schema_version": "1.0",
                "event": "worker_launched",
                "timestamp_utc": at(621),
                "task_id": TARGETS[2],
                "run_id": f"{TARGETS[1].lower()}-r1",
                "worker_id": "w-r1",
                "argv": worker_argv(TARGETS[2], f"{TARGETS[1].lower()}-r1"),
            },
        )
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("share run_id" in str(exc), str(exc))
        else:
            raise AssertionError("two launches sharing a run ID were accepted")
        events_path.write_text(original, encoding="utf-8", newline="")

        # A worker directory claiming a run ID this run launched for a
        # different task is a contradiction, not another run's directory.
        stolen = output_root / TARGETS[5] / f"{TARGETS[0].lower()}-r1"
        _write(
            stolen / "run.json",
            {
                "schema_version": "1.0",
                "run_id": f"{TARGETS[0].lower()}-r1",
                "task_id": TARGETS[5],
                "worker_id": "w-r1",
                "started_at_utc": at(5),
            },
        )
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("claims a run ID this run launched" in str(exc), str(exc))
        else:
            raise AssertionError("a stolen worker run ID was accepted")

        # Two scheduler events claiming one provider call with different
        # identities cannot both be true.
        stolen.parent.rename(stolen.parent.with_name("removed-conflict"))
        _append(
            events_path,
            {
                "schema_version": "1.0",
                "event": "architect_provider_call",
                "timestamp_utc": at(622),
                "agent_runtime_run_id": "arch-1",
                "provider": "claude-code",
                "model": "claude-opus-5",
            },
        )
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("with different identities" in str(exc), str(exc))
        else:
            raise AssertionError("two conflicting provider-call claims were accepted")
        events_path.write_text(original, encoding="utf-8", newline="")

        # A claim whose result.json records a different provider is refused
        # rather than being reported with the claimed provider.
        _append(
            events_path,
            {
                "schema_version": "1.0",
                "event": "architect_provider_call",
                "timestamp_utc": at(623),
                "agent_runtime_run_id": "imp-1",
                "provider": "openai-codex",
                "model": "gpt-5.6-sol",
            },
        )
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("but its result.json records" in str(exc), str(exc))
        else:
            raise AssertionError("a claim contradicting its own result.json was accepted")


def test_utilization_is_computed_from_bounded_intervals() -> None:
    """Peak, time-weighted utilization and scheduler idle from real intervals."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-util-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        report = build_report(load(root, run_root, output_root))
        util = report["utilization"]

        require(util["max_capacity"] == 4, str(util))
        # NSC-911 (10-70) and NSC-912 (20-100) overlap, and nothing else does.
        require(util["peak_active_workers"] == 2, str(util))
        require(util["peak_utilization"] == 0.5, str(util))
        require(util["bounded_intervals"] == 12, str(util))
        require(not util["unclosed_intervals"], str(util["unclosed_intervals"]))
        # Active worker seconds sum every bounded interval: 60+80+40+20+50+50
        # +40+40+40+40+50+40 = 550. Busy wall seconds count time with at least
        # one worker active, so the 10-70 and 20-100 overlap contributes the
        # union [10,100] = 90 rather than 140: 90+40+20+50+50+40+40+40+40+50+40
        # = 500. Idle is the rest of the 630-second window.
        require(util["active_worker_seconds"] == 550.0, str(util))
        require(util["busy_wall_seconds"] == 500.0, str(util))
        require(util["scheduler_idle_seconds"] == 130.0, str(util))
        # The report rounds to six decimals, so the expectation uses the same
        # rounding rather than a tolerance tighter than the published value.
        require(
            util["time_weighted_utilization"] == round(550.0 / (4 * 630.0), 6),
            str(util),
        )


def test_missing_evidence_is_unavailable_and_never_inferred() -> None:
    """Absent artifacts become explicit unavailable fields, not guesses."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-missing-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root, with_timeline=False)
        # No timeline: the receipt still proves completion, but its moment is
        # not recoverable and must say so.
        report = build_report(load(root, run_root, output_root))
        graph = report["graph_completion"]
        require(graph["graph_complete"] is True, "the receipt still proves completion")
        require(graph["completed_at_utc"] == UNAVAILABLE, str(graph))
        require("carries no timestamp" in graph["completed_at_unavailable_reason"], str(graph))
        # The window falls back to the scheduler journal, and says so.
        require(report["run_window"]["finish_source"] == "scheduler journal", str(report["run_window"]))

        # No worker output root at all: per-task timing is unavailable, and the
        # report says why instead of inventing task rows with zero elapsed.
        bare = load_run_evidence(run_root=run_root)
        bare_report = build_report(bare)
        require(
            any("worker output root" in note for note in bare_report["evidence_notes"]),
            str(bare_report["evidence_notes"]),
        )
        for entry in bare_report["tasks"]:
            require(entry["observed"] is False, str(entry))
            require(entry["elapsed_seconds"] == UNAVAILABLE, str(entry))
            require("no durable worker run directory" in entry["unavailable_reason"], str(entry))

        # The produced branch and delivered commit live in managed Issue state,
        # which this report deliberately does not read.
        report_tasks = {e["task_id"]: e for e in report["tasks"]}
        delivered = report_tasks[TARGETS[0]]
        require(delivered["produced_branch"] == UNAVAILABLE, str(delivered))
        require(delivered["produced_commit"] == UNAVAILABLE, str(delivered))
        require("GitHub Issue state" in delivered["produced_unavailable_reason"], str(delivered))


def test_mixed_and_malformed_artifacts_are_refused() -> None:
    """Stale, mixed, or malformed evidence is a refusal, not a warning."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-refuse-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)

        # A receipt from another run.
        stale = json.loads((run_root / "graph-complete.json").read_text(encoding="utf-8"))
        stale["manifest_sha256"] = "9" * 64
        _write(run_root / "graph-complete.json", stale)
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("different run manifest" in str(exc), str(exc))
        else:
            raise AssertionError("a receipt from another run was accepted")
        _write(
            run_root / "graph-complete.json",
            {**stale, "manifest_sha256": hashlib.sha256(RUN_ID.encode("ascii")).hexdigest()},
        )

        # A malformed journal line.
        with (run_root / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("{not json\n")
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("malformed JSON" in str(exc), str(exc))
        else:
            raise AssertionError("a malformed journal line was accepted")


def test_worker_directory_contradictions_are_refused() -> None:
    """A worker result that contradicts its own directory is refused."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-contra-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        victim = output_root / TARGETS[0] / f"{TARGETS[0].lower()}-r1" / "run_result.json"
        payload = json.loads(victim.read_text(encoding="utf-8"))
        payload["run_id"] = "some-other-run"
        _write(victim, payload)
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("contradicts its directory" in str(exc), str(exc))
        else:
            raise AssertionError("a contradictory worker result was accepted")

        _write(victim, {**payload, "run_id": f"{TARGETS[0].lower()}-r1"})

        # A directory for a task this run never launched belongs to another run
        # sharing the output root. It is excluded and counted, not refused and
        # not adopted.
        _write(payload_path := (output_root / "NSC-777" / "x-r1" / "run.json"), {
            "schema_version": "1.0", "run_id": "x-r1", "task_id": "NSC-777",
            "worker_id": "w", "started_at_utc": at(1),
        })
        excluded = build_report(load(root, run_root, output_root))
        require(
            "NSC-777" not in {entry["task_id"] for entry in excluded["tasks"]},
            str([entry["task_id"] for entry in excluded["tasks"]]),
        )
        require(
            any("belong to other autonomous runs" in note for note in excluded["evidence_notes"]),
            str(excluded["evidence_notes"]),
        )
        payload_path.parent.parent.rename(payload_path.parent.parent.with_name("removed-NSC-777"))

        # A launch of a task outside the run scope is still a mixed run, and
        # that remains a refusal because this run's own journal claims it.
        _append(run_root / "events.jsonl", {
            "schema_version": "1.0", "event": "worker_launched", "timestamp_utc": at(2),
            "task_id": "NSC-777", "run_id": "x-r1", "worker_id": "w",
            "argv": worker_argv("NSC-777", "x-r1"),
        })
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("not in the run scope" in str(exc), str(exc))
        else:
            raise AssertionError("a task outside the run scope was accepted")


def test_graph_complete_receipt_proves_dynamic_decomposition_scope() -> None:
    """Real D1C children need no fictional scheduler child-ID event.

    The immutable manifest predates decomposition.  Production records the
    final transitive scope in ``graph-complete.json`` and in the controller
    timeline, but does not add ``child_task_ids`` to ``architect_completed``.
    The completed run must therefore accept and report the child from its
    graph-complete receipt while still rejecting any launch outside that exact
    receipt scope.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-dynamic-scope-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        events_path = run_root / "events.jsonl"
        records = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for record in records:
            record.pop("child_task_ids", None)
        events_path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
            newline="\n",
        )

        evidence = load(root, run_root, output_root)
        report = build_report(evidence)
        by_id = {entry["task_id"]: entry for entry in report["tasks"]}
        require(CHILD in by_id, str(sorted(by_id)))
        require(by_id[CHILD]["origin"] == "decomposition_child", str(by_id[CHILD]))
        require(report["scope"]["decomposition_children"] == [CHILD], str(report["scope"]))

        _append(
            events_path,
            {
                "schema_version": "1.0",
                "event": "worker_launched",
                "timestamp_utc": at(2),
                "task_id": "NSC-777",
                "run_id": "outside-r1",
                "worker_id": "outside-worker",
                "argv": worker_argv("NSC-777", "outside-r1"),
            },
        )
        try:
            load(root, run_root, output_root)
        except RunEvidenceError as exc:
            require("not in the run scope" in str(exc), str(exc))
        else:
            raise AssertionError("a task outside the receipt-proven scope was accepted")


def test_cli_writes_json_and_markdown() -> None:
    """The deterministic command produces both report formats."""

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-cli-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        json_path = root / "reports" / "run-evidence.json"
        markdown_path = root / "reports" / "run-evidence.md"
        code = main(
            [
                "--run-root", str(run_root),
                "--worker-output-root", str(output_root),
                "--provider-call-root", str(output_root),
                "--output-json", str(json_path),
                "--output-markdown", str(markdown_path),
            ]
        )
        require(code == 0, f"the report command exited {code}")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        require(payload["run_id"] == RUN_ID, str(payload["run_id"]))
        require(payload["scope"]["nsc_042_excluded"] is True, "the JSON carries the exclusion proof")
        markdown = markdown_path.read_text(encoding="utf-8")
        for heading in ("# Autonomous run evidence", "## Run window", "## Scope", "## Tasks", "## Utilization"):
            require(heading in markdown, f"missing heading {heading!r}")
        # Every top-level task appears in the Markdown table.
        for task_id in TARGETS:
            require(task_id in markdown, f"{task_id} missing from the Markdown report")
        require(CHILD in markdown, "the decomposition child is missing from the Markdown report")

        # A refusal exits non-zero rather than printing a partial report.
        (run_root / "manifest.json").unlink()
        require(
            main(["--run-root", str(run_root)]) == 2,
            "a missing manifest must be refused with a non-zero exit",
        )


def test_real_autonomous_shape_has_no_scheduler_bracket_events() -> None:
    """An autonomous run never emits scheduler_started or scheduler_stopped.

    The controller drives the scheduler through ``poll_capacity_batch``; the
    bracket pair is emitted only by ``PollingOrchestrator.run``, which an
    autonomous graph run never calls. The run window therefore has to come
    from the controller's own timeline, and when that is absent the report
    must fall back to observed scheduler activity and say which source it
    used rather than silently reporting a narrower window as the run.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-shape-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        # Rewrite the journal exactly as an autonomous run produces it: the
        # same records, minus the two bracket events the controller never
        # causes to be emitted.
        events_path = run_root / "events.jsonl"
        kept = [
            line
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line)["event"] not in {"scheduler_started", "scheduler_stopped"}
        ]
        events_path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
        require(
            all("scheduler_started" not in line for line in kept),
            "the fixture still contains a bracket event",
        )

        # With the controller timeline present the window is still exact.
        report = build_report(load(root, run_root, output_root))
        window = report["run_window"]
        require(window["started_at_utc"] == at(0), str(window))
        require(window["finished_at_utc"] == at(630), str(window))
        require("timeline" in window["start_source"], str(window))
        require("timeline" in window["finish_source"], str(window))

        # Remove the timeline too, which is the pre-instrumentation shape.
        # The window now falls back to observed activity and names that source
        # honestly instead of claiming to know when the run began.
        (run_root / "run_timeline.jsonl").unlink()
        fallback = build_report(load(root, run_root, output_root))["run_window"]
        require(fallback["start_source"] == "first scheduler event", str(fallback))
        require(fallback["finish_source"] == "last scheduler event", str(fallback))
        # First launch is at +10 and the last worker finish at +610, so the
        # observable window is strictly narrower than the true 630-second run.
        require(fallback["started_at_utc"] == at(10), str(fallback))
        require(fallback["elapsed_seconds"] == 600.0, str(fallback))
        require(
            fallback["elapsed_seconds"] < 630.0,
            "scheduler activity must not be presented as the full run window",
        )


def test_resume_hint_sender_and_consumer_are_correlated() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-run-evidence-hints-") as text:
        root = Path(text)
        run_root, output_root, _ = build_fixture(root)
        journal = run_root / "events.jsonl"
        successful = "1" * 32
        failed = "2" * 32
        transition = {
            "from_state": "human_action_required",
            "from_phase": "unity_runtime_validation",
            "to_state": "agent_ready",
            "to_phase": "delivery_evidence",
        }
        _append(
            journal,
            {
                "schema_version": "1.0",
                "event": "local_resume_hint_send_completed",
                "timestamp_utc": at(300),
                "hint_id": successful,
                "task_id": TARGETS[0],
                "sender_result": "success",
                "workflow_transition": transition,
            },
        )
        _append(
            journal,
            {
                "schema_version": "1.0",
                "event": "local_resume_hint_consumed",
                "timestamp_utc": at(301),
                "hint_id": successful,
                "task_id": TARGETS[0],
                "sender_result": "success",
                "scheduler_disposition": "already_awake",
                "workflow_transition": transition,
            },
        )
        _append(
            journal,
            {
                "schema_version": "1.0",
                "event": "local_resume_hint_send_completed",
                "timestamp_utc": at(302),
                "hint_id": failed,
                "task_id": TARGETS[1],
                "sender_result": "failure",
                "failure_reason": "local_datagram_send_failed",
                "workflow_transition": transition,
            },
        )
        report = build_report(load(root, run_root, output_root))
        hints = report["resume_hint_telemetry"]
        require(hints["send_count"] == 2, str(hints))
        require(hints["send_success_count"] == 1, str(hints))
        require(hints["send_failure_count"] == 1, str(hints))
        require(hints["consume_count"] == 1, str(hints))
        require(hints["correlated_count"] == 1, str(hints))
        require(hints["scheduler_dispositions"] == {"already_awake": 1}, str(hints))
        require(hints["failed_hint_ids"] == [failed], str(hints))
        markdown = render_markdown(report)
        require("## Local resume hints" in markdown, markdown)
        require("1 successful, 1 failed" in markdown, markdown)


def main_tests() -> int:
    tests = [
        test_reports_run_window_graph_completion_and_scope,
        test_per_task_timing_counts_a_retry_once_per_run_id,
        test_graph_completion_resolves_an_earlier_human_stop_without_erasing_it,
        test_unfinished_human_action_stop_is_never_reported_as_a_pass,
        test_tokens_are_reported_by_role_and_unavailable_is_explicit,
        test_a_role_that_never_exposed_tokens_is_unavailable_not_zero,
        test_a_second_autonomous_run_sharing_the_roots_is_never_merged,
        test_supervisor_and_models_come_from_the_run_not_a_default,
        test_conflicting_durable_identities_are_refused,
        test_utilization_is_computed_from_bounded_intervals,
        test_missing_evidence_is_unavailable_and_never_inferred,
        test_mixed_and_malformed_artifacts_are_refused,
        test_worker_directory_contradictions_are_refused,
        test_graph_complete_receipt_proves_dynamic_decomposition_scope,
        test_cli_writes_json_and_markdown,
        test_real_autonomous_shape_has_no_scheduler_bracket_events,
        test_resume_hint_sender_and_consumer_are_correlated,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"run evidence report tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_tests())
