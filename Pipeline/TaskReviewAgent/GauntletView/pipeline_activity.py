"""Deterministic, read-only projection of already loaded run artifacts.

No IO or process inspection belongs here. `now` is supplied by the caller.
Node workflow state is input only and is never rewritten by this reducer.
"""

from datetime import datetime


STALE_SECONDS = 60
# Highest applicable row wins. Within a row, the newest durable timestamp wins;
# equal timestamps retain journal order. Failure survives a subsequent drain/stop.
PRECEDENCE = ("terminal", "open_architect", "recorded_worker", "scheduler", "unknown")
TERMINALS = {
    "autonomous_run_error": ("failed", "Run failed"),
    "scheduler_stopped": ("stopped", "Run stopped"),
    "graph_complete_receipt_written": ("complete", "Graph complete"),
}
# These are boundaries the producer actually emits. Completion observations use
# past tense: they are not evidence that the next uninstrumented action started.
SCHEDULER_STAGES = {
    "autonomous_run_started": ("initializing", "Initializing the autonomous run"),
    "scheduler_started": ("initializing", "Initializing the scheduler"),
    "poll_started": ("refreshing", "Refreshing rehearsal main"),
    "source_main_refreshed": ("source_refreshed", "Rehearsal main refreshed; reading Issues and integration reservations next"),
    "integration_reservations_observed": ("portfolio", "Integration reservations read; building the eligible-task portfolio next"),
    "worker_finished": ("rechecking", "Worker finished; rechecking the graph for newly unblocked work next"),
    "worker_returned_to_architect": ("rechecking", "Worker returned; rechecking the graph for newly unblocked work next"),
    "issue_state_change_notified_to_architect": ("rechecking", "GitHub state-change poke received; rechecking the graph next"),
    "scheduler_wait_source_refresh": ("scheduler_wait", "Waiting to retry refreshing rehearsal main"),
    "scheduler_wait_observation_failure": ("scheduler_wait", "Waiting to retry reading Issues and integration reservations"),
    "scheduler_blocked": ("scheduler_wait", "Scheduler is waiting; admissions are blocked"),
}
WORKER_ACTIONS = {
    "prepare_task_checkout": ("checkout", "Preparing {task}'s isolated checkout"),
    "run_execution_crew": ("implementation", "ExecutionCrew is implementing {task}"),
    "repair_candidate": ("implementation", "ExecutionCrew is repairing {task}"),
    "integrate_current_main": ("integration", "Merging current main into {task}'s branch"),
    "run_authoritative_unity_test": ("validation", "Running Unity validation for {task}"),
    "run_unity_tests": ("validation", "Running Unity validation for {task}"),
    "run_validation": ("validation", "Validator is checking {task}"),
    "produce_delivery_evidence": ("evidence", "Producing delivery evidence for {task}"),
    "publish_delivery_evidence": ("evidence", "Publishing delivery evidence for {task}"),
    "create_delivery_review_draft": ("evidence", "Building the delivery-evidence draft for {task}"),
    "publish_delivery_review": ("evidence", "Publishing delivery review for {task}"),
    "finalize_delivery_evidence_and_open_pr": ("evidence", "Publishing delivery evidence and opening the pull request for {task}"),
    "inspect_or_merge_pull_request": ("ci", "Checking pull-request CI and merge status for {task}"),
    "run_decomposition": ("decomposition", "Reviewing task decomposition for {task}"),
}


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def integer(value):
    return value if type(value) is int and value >= 0 else None


def text(value):
    return value if isinstance(value, str) and value.strip() else "unavailable"


def duration(seconds):
    if seconds is None:
        return "unavailable"
    seconds = int(max(0, seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 60}m {seconds % 60}s"


def ordered_events(events, timeline, worker_events, run_id):
    """Ignore foreign timelines; preserve unknown events as readable history."""
    rows = []
    seen = set()
    for source, items in (("scheduler", events), ("run timeline", timeline), ("worker", worker_events)):
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("event"), str):
                continue
            if source == "run timeline" and item.get("run_id") != run_id:
                continue
            row = dict(item)
            row["source"] = source
            # Exact duplicate journal records must not multiply history or calls.
            key = (source, repr(sorted(item.items())))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return sorted(rows, key=lambda e: timestamp(e.get("timestamp_utc")) or float("-inf"))


def build_pipeline_activity(*, manifest, progress, receipt, events, timeline,
                            worker_events, tasks, now):
    rows = ordered_events(events, timeline, worker_events, manifest.get("run_id"))
    scope = set(manifest.get("target_task_ids") or [])
    progress = progress if isinstance(progress, dict) else {}
    runtime = manifest.get("runtime_configuration")
    runtime = runtime if isinstance(runtime, dict) else {}
    scheduler_stage = None
    terminal = None
    architect = None
    provider_open = False
    analysis_id = None
    waits = set()
    admitted = set()
    candidates = []
    candidate_count = None
    active = {}
    worker_stages = {}
    completions = set()
    completion_key = None
    launches = set()
    recent = []
    provider, model = "unavailable", "unavailable"
    provider_source = "unavailable"
    last_wait_stage = None

    def stage(row, key, headline, detail=""):
        return {"stage": key, "headline": headline, "description": detail,
                "started_at": row.get("timestamp_utc"), "source": row.get("source", "scheduler")}

    def all_wait():
        ids = {c["task_id"] for c in candidates}
        return bool(ids) and ids <= waits and not admitted

    for index, row in enumerate(rows):
        kind = row["event"]
        task_id = row.get("_task_id") if row["source"] == "worker" else row.get("task_id")
        next_stage = None
        if row["source"] == "worker":
            if task_id not in active or active[task_id] != row.get("_worker_run_id"):
                continue
            fields = row.get("fields")
            fields = fields if isinstance(fields, dict) else {}
            if kind in {"pipeline_action_started", "pipeline_action_heartbeat"}:
                action = fields.get("action")
                action = action if isinstance(action, str) else None
                key, headline = WORKER_ACTIONS.get(action, ("worker", "Worker is processing {task}"))
                previous = worker_stages.get(task_id)
                next_stage = stage(row, key, headline.format(task=task_id))
                # Heartbeats update freshness, never reset the stage stopwatch.
                if previous and previous.get("action") == action and kind.endswith("heartbeat"):
                    next_stage["started_at"] = previous["started_at"]
                next_stage["action"] = action
                worker_stages[task_id] = next_stage
            elif kind in {"pipeline_action_completed", "pipeline_action_failed", "run_finished", "terminal_state"}:
                worker_stages.pop(task_id, None)
                if kind in {"run_finished", "terminal_state"}:
                    active.pop(task_id, None)
                next_stage = stage(row, "worker_observed", f"{task_id}: {kind.replace('_', ' ')}")
                scheduler_stage = next_stage
        else:
            if kind in TERMINALS or (kind == "poll_capacity_batch_completed" and row.get("fatal") is True):
                key, headline = TERMINALS.get(kind, ("failed", "Run failed"))
                if kind == "autonomous_run_error" and row.get("exception_type") == "KeyboardInterrupt":
                    key, headline = "stopped", "Run stopped"
                # A normal scheduler stop does not erase a preceding fatal result.
                if not terminal or terminal["stage"] != "failed" or key == "complete":
                    terminal = stage(row, key, headline)
                next_stage = terminal
            elif kind == "architect_started":
                architect = row
                provider_open = True
                analysis_id, waits, admitted = None, set(), set()
                completion_key = None
                pairs = row.get("eligible_pairs")
                candidates = [{"task_id": c["task_id"], "work_types": [v for v in c.get("work_types", []) if isinstance(v, str)]
                               if isinstance(c.get("work_types"), list) else []}
                              for c in pairs if isinstance(c, dict) and isinstance(c.get("task_id"), str)] if isinstance(pairs, list) else []
                candidate_count = integer(row.get("portfolio_size"))
                if candidate_count is None and isinstance(pairs, list) and len(candidates) == len(pairs):
                    candidate_count = len(candidates)
                provider = text(row.get("provider") or runtime.get("architect_provider"))
                model = text(row.get("model") or runtime.get("architect_model"))
                provider_source = "start event" if row.get("provider") else "manifest configuration"
                if provider == "unavailable":
                    provider_source = "unavailable"
                headline = (f"Software Architect is reviewing {candidate_count} eligible tasks" if candidate_count is not None
                            else "Software Architect is deciding which tasks can start safely")
                next_stage = stage(row, "architect", headline,
                                   "The Software Architect is comparing these eligible tasks and deciding which can run safely in parallel.")
                architect = {**row, **next_stage, "_sequence": index}
                last_wait_stage = None
            elif kind in {"architect_provider_call", "architect_completed", "architect_capacity_decided"}:
                # Provider receipt is emitted AFTER the invocation returns, before
                # per-task completion. Counting per-task completions overcounts a batch.
                if architect and row.get("source_head") and architect.get("source_head") and row["source_head"] != architect["source_head"]:
                    continue
                provider_open = False
                analysis_id = row.get("analysis_id") or analysis_id
                if completion_key is None:
                    completion_key = row.get("agent_runtime_run_id") or analysis_id
                    if completion_key is None:
                        completion_key = ("start", architect["_sequence"]) if architect else ("row", index)
                completions.add(completion_key)
                if kind == "architect_provider_call":
                    provider, model = text(row.get("provider")), text(row.get("model"))
                    provider_source = "completed provider receipt"
                elif kind == "architect_completed" and isinstance(task_id, str):
                    admitted.add(task_id)
                next_stage = stage(row, "architect_decided", "Software Architect decision recorded; checking safe task starts")
            elif kind in {"architect_wait", "architect_human_review", "architect_capacity_deferred"}:
                if row.get("cached") is True:
                    next_stage = stage(row, "architect_cached", "Using a cached Software Architect decision")
                elif row.get("error"):
                    provider_open = False
                    next_stage = stage(row, "architect_unavailable", "Scheduler is waiting after an unusable Software Architect call")
                else:
                    if row.get("analysis_id") and (analysis_id is None or row["analysis_id"] == analysis_id):
                        provider_open = False
                    if analysis_id and row.get("analysis_id") == analysis_id and kind != "architect_human_review":
                        waits.add(task_id)
                    next_stage = stage(row, "architect_wait", "Software Architect deferred task admission")
                    if all_wait():
                        next_stage = stage(row, "all_wait", f"Software Architect chose WAIT for all {len(candidates)} eligible tasks")
                last_wait_stage = next_stage
            elif kind == "architect_wait_started":
                # This event names the scheduler's sleep, never a provider start.
                if row.get("wait_mode") == "event_or_fallback":
                    next_stage = stage(row, "event_wait", "Waiting for a GitHub state-change poke, worker return, or fallback refresh")
                elif row.get("wait_mode") == "fallback_timer":
                    next_stage = stage(row, "fallback_wait", "Waiting for the scheduler fallback refresh")
                else:
                    next_stage = stage(row, "scheduler_wait", "Scheduler is waiting; wait mode unavailable")
                if last_wait_stage:
                    next_stage["description"] = last_wait_stage["headline"] + "."
            elif kind == "architect_session_reconciled":
                provider_open = False
                next_stage = stage(row, "unknown", "Previous Software Architect call was interrupted; current activity unavailable")
            elif kind == "worker_launched" and task_id in scope:
                active[task_id] = row.get("run_id")
                launches.add(row.get("run_id") or (task_id, row.get("timestamp_utc")))
                admitted.add(task_id)
                next_stage = stage(row, "worker_launch", f"Starting {task_id} work")
                worker_stages[task_id] = next_stage
            elif kind in {"worker_finished", "worker_failed", "worker_returned_to_pool"}:
                active.pop(task_id, None)
                worker_stages.pop(task_id, None)
                next_stage = stage(row, "rechecking", f"{task_id or 'Worker'} returned; rechecking the graph for newly unblocked work next")
            elif kind == "integration_gate_observed" and row.get("queued_task_ids"):
                next_stage = stage(row, "integration_wait", "Waiting for the integration commit gate")
            elif kind == "plan_idle":
                next_stage = last_wait_stage or stage(row, "idle", "Scheduler idle; no safe task start recorded")
            elif kind in SCHEDULER_STAGES:
                next_stage = stage(row, *SCHEDULER_STAGES[kind])
                if isinstance(row.get("reason"), str):
                    next_stage["description"] = row["reason"][:500]
                if kind == "poll_started":
                    last_wait_stage = None
            if next_stage and next_stage["stage"] not in {"failed", "stopped", "complete"}:
                scheduler_stage = next_stage
        recent.append({"event": kind, "timestamp_utc": row.get("timestamp_utc"), "source": row["source"],
                       "headline": next_stage["headline"] if next_stage else kind.replace("_", " ")})

    if receipt and terminal is None:
        terminal = stage({}, "complete", "Graph complete")
        terminal["source"] = "graph-complete.json (timestamp unavailable)"
    recorded_worker = max(worker_stages.values(), key=lambda v: timestamp(v.get("started_at")) or float("-inf"), default=None)
    choices = {"terminal": terminal, "open_architect": architect if provider_open else None,
               "recorded_worker": recorded_worker, "scheduler": scheduler_stage,
               "unknown": stage({}, "unknown", "Pipeline activity unavailable")}
    chosen = next(choices[key] for key in PRECEDENCE if choices[key] is not None)
    provider_open = provider_open and terminal is None
    dated = [timestamp(item["timestamp_utc"]) for item in recent if timestamp(item["timestamp_utc"]) is not None]
    last_at = max(dated) if dated else None
    age = max(0, now - last_at) if last_at is not None else None
    started_at = timestamp(chosen.get("started_at"))
    elapsed = max(0, now - started_at) if started_at is not None else None
    in_scope = [task for task in tasks if task["id"] in scope]
    scheduler_observed = any(row["source"] == "scheduler" for row in rows)
    launch_total = integer(progress.get("worker_launches_total"))
    return {
        **chosen, "provider_call_open": provider_open,
        "provider": provider, "model": model, "provider_source": provider_source,
        "candidate_count": candidate_count, "candidates": candidates,
        "call_status": ("Paid provider call recorded as in progress; billing confirmation is unavailable until a receipt is written."
                        if provider_open else "No open provider call established by the selected stage."),
        "liveness": "Artifact-only liveness is not proof of process liveness.",
        "stage_elapsed_seconds": elapsed, "last_event_age_seconds": age,
        "sampled_at_epoch": now, "stale_after_seconds": STALE_SECONDS,
        "terminal": terminal is not None,
        "freshness": (f"No new durable event for {duration(age)}; process status is unknown from artifacts."
                      if age is not None else "Last durable event time unavailable; process status is unknown from artifacts."),
        "counters": {
            "active_workers": len(active) if scheduler_observed else None,
            "capacity": integer(manifest.get("max_capacity")),
            "eligible_or_queued": sum(task["state"] in {"ready", "decomposition_ready", "integration_queued"} and task["id"] not in active for task in in_scope),
            "dependency_blocked": sum(task["state"] == "pending" for task in in_scope),
            "completed": sum(task["state"] == "complete" for task in in_scope),
            "architect_calls_completed": len(completions) if scheduler_observed else None,
            "worker_launches": max(launch_total or 0, len(launches)) if scheduler_observed or launch_total is not None else None,
            "wakeups": integer(progress.get("wakeups_total")),
        },
        "recent_activity": list(reversed(recent[-8:])),
    }
