"""Read-only projection into the existing Gauntlet graph and task panels."""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.automation_policy import is_synthetic_gauntlet
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.process_identity import matches
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.GauntletView import server as gauntlet

STATE_CACHE_SECONDS = 2.5
HUMAN_REVIEW_ALARM_SECONDS = 30 * 60


def _epoch_seconds(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


class ExclusiveListenerError(OSError):
    """Another process already owns this viewer's requested port."""


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    """Refuse to share its listening port with any other socket.

    ``ThreadingHTTPServer`` inherits ``allow_reuse_address = True`` from
    ``socketserver.TCPServer``. On POSIX that only lets an immediate restart
    rebind a socket still in ``TIME_WAIT``. On Windows the same
    ``SO_REUSEADDR`` flag instead lets an unrelated second process bind the
    exact same address and port while the first is still actively listening,
    so a stale viewer from an earlier replay and its replacement could both
    silently serve the same port with no bind error at all. Requesting
    ``SO_EXCLUSIVEADDRUSE`` (Windows) makes the OS guarantee no other socket
    — with or without its own ``SO_REUSEADDR`` — may bind this address/port
    while this listener holds it, and disabling ``allow_reuse_address`` is
    required because Windows rejects setting both options on one socket.
    This is a real bind-time guarantee from the kernel, not a pre-bind probe
    that a second process could still race past.
    """

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            super().server_bind()
        except OSError as exc:
            raise ExclusiveListenerError(
                f"viewer port {self.server_address[1]} is already owned by another "
                "process or an earlier viewer instance"
            ) from exc


class EmptySnapshot(gauntlet.Snapshot):
    def idle_tasks(self):
        return []


def _load_contracts_at_head(source: Path, head: str) -> list[dict]:
    task_paths = git(source, "ls-tree", "-r", "--name-only", "-z", head, "--", "Tasks").split(b"\0")
    task_ids = sorted(
        Path(path.decode()).stem for path in task_paths
        if path.startswith(b"Tasks/NSC-") and path.endswith(b".yaml")
        and path.count(b"/") == 1
    )
    return [load_committed_task(source, task_id, commit=head) for task_id in task_ids]


class AssistantSnapshot:
    def __init__(self, source: Path, checkout_root: Path):
        self.manager = Checkouts(source, checkout_root)
        self.source = self.manager.source
        self.contract_head = None
        self.contracts = []
        self.lock = threading.Lock()
        self.cached_state = None
        self.cached_at = 0.0
        self.template = EmptySnapshot(self.source / "Tasks", checkout_root)

    def build(self, *, max_age_seconds: float = 0.0) -> dict:
        with self.lock:
            if (max_age_seconds > 0 and self.cached_state is not None
                    and time.monotonic() - self.cached_at < max_age_seconds):
                return self.cached_state
            state = self.template.idle_local_state()
            state["run"].update({
                "mode": "assistant", "marker": "ASSISTANT CONTROL",
                "source_repository": str(self.source), "dir": str(self.manager.root),
                "operator": {"viewer_persistent": False, "read_only": True},
                "status": "awaiting_instruction", "targets": [],
            })
            activity = state["pipeline_activity"]
            activity.pop("mode", None)
            activity.update({
                "headline": "Talk to your assistant to manage tasks",
                "description": "Read-only project view. Use conversation to request worker runs, inspect results, and make approval decisions.",
                "liveness": "assistant-controlled", "provider_profile": "not running",
            })
            try:
                head = git(self.source, "rev-parse", "HEAD").decode().strip()
                if head != self.contract_head:
                    contracts = _load_contracts_at_head(self.source, head)
                    if git(self.source, "rev-parse", "HEAD").decode().strip() != head:
                        raise ValueError("Source advanced while committed task contracts were being read")
                    self.contracts, self.contract_head = contracts, head
                state["run"]["source_commit"] = self.contract_head
                state["run"]["source_branch"] = git(self.source, "branch", "--show-current").decode().strip()
                simulation = self._load_simulation()
                state["tasks"] = [
                    self.task_row(contract, read_durable_state=simulation is None)
                    for contract in self.contracts
                ]
                if simulation is None:
                    self._apply_decomposition_projection(state["tasks"])
                    controller = self._apply_graph_controller(state, activity)
                    self._apply_controller_timing_projection(
                        state["tasks"], controller, now=time.time()
                    )
                else:
                    self._apply_simulation(state, activity, simulation)
                waiting = [row["id"] for row in state["tasks"] if row.get("state") == "human_action"]
                if waiting:
                    activity["headline"] = "🐴 Vincent needed"
                    activity["description"] = (
                        "Test the exact candidate in Unity, then tell your assistant approve or reject: "
                        + ", ".join(waiting)
                    )
                    state["assistant_attention"] = self._human_review_attention(
                        state["tasks"], now_epoch=time.time(),
                    )
                scheduler = state.get("scheduler")
                if isinstance(scheduler, dict) and "active" in scheduler:
                    scheduler["active"] = [
                        row["id"] for row in state["tasks"]
                        if row.get("state") == "active"
                        and (row.get("worker_observation") or {}).get("host_identity_alive") is not False
                    ]
                state["run"]["targets"] = [row["id"] for row in state["tasks"] if row["in_scope"]]
            except (OSError, RuntimeError, ValueError) as exc:
                activity["headline"] = "Project inspection needs attention"
                activity["description"] = str(exc)
                state["inspection_error"] = str(exc)
                # No stale green state on read errors. Keep the server serving.
            self.cached_state = state
            self.cached_at = time.monotonic()
            return state

    def _human_review_attention(self, rows: list[dict], *, now_epoch: float) -> dict:
        """Describe exact candidates waiting for Vincent and their alarm state.

        The task record's modification time is the durable handoff time. A new
        candidate or source synchronization rewrites that exact record and
        starts a new review window. Approve/reject removes ``human_action`` on
        the next snapshot, which is the only in-product way to stop the alarm.
        """
        candidates = []
        for row in rows:
            if row.get("state") != "human_action" or not row.get("candidate_commit"):
                continue
            record_path = self.manager.records / f"{row['id']}.json"
            try:
                since = record_path.stat().st_mtime
            except OSError:
                since = now_epoch
            candidates.append({
                "task_id": row["id"],
                "candidate_commit": row["candidate_commit"],
                "waiting_since_epoch": since,
                "waiting_seconds": max(0, int(now_epoch - since)),
            })
        return {
            "kind": "human_review",
            "task_ids": [item["task_id"] for item in candidates],
            "candidates": candidates,
            "review_alarm": {
                "active": any(
                    item["waiting_seconds"] >= HUMAN_REVIEW_ALARM_SECONDS
                    for item in candidates
                ),
                "after_seconds": HUMAN_REVIEW_ALARM_SECONDS,
            },
        }

    def _controller_owner_active(self, controller: dict) -> bool:
        path = self.manager.records / "graph-controller-owner.json"
        if not path.is_file():
            return False
        try:
            owner = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        if not isinstance(owner, dict):
            return False
        identity = owner.get("process_identity")
        invocation_id = controller.get("invocation_id")
        lock_path = self.manager.records / "graph-controller.lock"
        if (
            owner.get("schema_version") != "assistant-graph-controller-owner/v1"
            or owner.get("status") != "controller_started"
            or not isinstance(invocation_id, str) or not invocation_id
            or owner.get("invocation_id") != invocation_id
            or not isinstance(identity, dict)
            or owner.get("pid") != identity.get("pid")
            or owner.get("source") != str(self.source)
            or owner.get("checkout_root") != str(self.manager.root)
            or owner.get("targets") != controller.get("targets")
            or owner.get("lock_path") != str(lock_path)
            or not lock_path.is_file()
        ):
            return False
        try:
            return matches(identity)
        except (OSError, RuntimeError, ValueError):
            return False

    def _apply_graph_controller(self, state: dict, activity: dict) -> dict | None:
        path = self.manager.records / "graph-controller.json"
        if not path.is_file():
            return None
        try:
            controller = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Graph controller record is unreadable: {exc}") from exc
        if (not isinstance(controller, dict)
                or controller.get("schema_version") != "assistant-graph-controller/v1"):
            raise ValueError("Graph controller record has an unsupported schema")
        status = controller.get("status")
        recorded_status = status
        if status == "running" and not self._controller_owner_active(controller):
            status = "unknown"
            controller = {
                **controller, "status": status,
                "recorded_status": recorded_status, "owner_active": False,
            }
        action = controller.get("current_action") or {}
        task_id = action.get("task_id")
        state["run"].update({
            "status": status,
            "targets": controller.get("targets") or state["run"].get("targets") or [],
        })
        self._apply_controller_scope(state, controller.get("targets"))
        if status == "running":
            self._apply_running_controller_projection(state, controller, action)
            activity.update({
                "headline": "Assistant graph controller is working",
                "description": (
                    f"{action.get('kind', 'Checking graph')} {task_id or ''}".strip()
                ),
                "liveness": "assistant-controlled",
                "provider_profile": "bounded autonomous graph",
            })
        elif status == "preflight":
            self._apply_preflight_controller_projection(state, controller)
        elif status == "blocked":
            activity.update({
                "headline": "Graph controller needs attention",
                "description": str(controller.get("last_error") or "A task needs inspection."),
                "liveness": "blocked",
            })
        elif status == "unknown" and recorded_status == "running":
            activity.update({
                "headline": "Graph controller ownership is unknown",
                "description": (
                    "Stored running state has no matching active owner invocation "
                    "and process identity."
                ),
                "liveness": "unknown",
                "provider_profile": "not running",
            })
        state["graph_controller"] = controller
        return controller

    @staticmethod
    def _apply_controller_timing_projection(
        tasks: list[dict], controller: Mapping[str, Any] | None, *, now: float,
    ) -> None:
        """Merge controller-journal timings into each task's existing progress."""
        if not isinstance(controller, Mapping):
            return
        history = controller.get("history")
        if not isinstance(history, list):
            return
        current_action = controller.get("current_action")
        current_task_id = (
            current_action.get("task_id")
            if isinstance(current_action, Mapping) else None
        )
        is_controller_running = controller.get("status") == "running"

        attempts_by_task: dict[str, list[tuple[float, float | None]]] = {}
        pending: dict[str, tuple[Any, float]] = {}
        for entry in history:
            if not isinstance(entry, Mapping):
                continue
            action = entry.get("action")
            task_id = action.get("task_id") if isinstance(action, Mapping) else None
            at = _epoch_seconds(entry.get("at"))
            if not isinstance(task_id, str) or not task_id or at is None:
                continue
            open_attempt = pending.get(task_id)
            if open_attempt is not None and open_attempt[0] == action:
                attempts_by_task.setdefault(task_id, []).append((open_attempt[1], at))
                del pending[task_id]
            else:
                if open_attempt is not None:
                    attempts_by_task.setdefault(task_id, []).append((open_attempt[1], None))
                pending[task_id] = (action, at)
        for task_id, (_action, started) in pending.items():
            attempts_by_task.setdefault(task_id, []).append((started, None))

        by_id = {row["id"]: row for row in tasks if isinstance(row, dict) and row.get("id")}
        for task_id, attempts in attempts_by_task.items():
            row = by_id.get(task_id)
            if row is None or not row.get("in_scope"):
                continue
            attempts.sort(key=lambda attempt: attempt[0])
            completed = [attempt for attempt in attempts if attempt[1] is not None]
            open_attempt = attempts[-1] if attempts[-1][1] is None else None
            currently_ticking = (
                open_attempt is not None and is_controller_running
                and task_id == current_task_id
            )
            stage_elapsed = round(now - open_attempt[0], 1) if currently_ticking else None
            durable_stage_elapsed = (
                round(completed[-1][1] - completed[-1][0], 1) if completed else None
            )
            durable_task_elapsed = (
                round(sum(end - start for start, end in completed), 1) if completed else None
            )
            last_known_activity = (
                now if currently_ticking
                else completed[-1][1] if completed
                else open_attempt[0] if open_attempt is not None else None
            )
            total_elapsed = (
                round(last_known_activity - attempts[0][0], 1)
                if last_known_activity is not None else None
            )
            progress = row.get("progress")
            if not isinstance(progress, dict):
                progress = {}
                row["progress"] = progress
            progress.update({
                "current_attempt_elapsed_seconds": stage_elapsed,
                "stage_elapsed_seconds": stage_elapsed,
                "total_elapsed_seconds": total_elapsed,
                "durable_stage_elapsed_seconds": durable_stage_elapsed,
                "durable_task_elapsed_seconds": durable_task_elapsed,
            })

    def _apply_preflight_controller_projection(self, state: dict, controller: dict) -> None:
        """Project an exact read-only graph plan without claiming any action ran."""

        plan = controller.get("preflight_plan")
        if not isinstance(plan, dict):
            raise ValueError("Graph controller preflight plan is missing")
        targets = controller.get("targets")
        current_scope = [
            row.get("id") for row in state.get("tasks") or []
            if isinstance(row, dict) and row.get("in_scope")
        ]
        if (
            plan.get("schema_version") != "assistant-graph-controller/v1"
            or plan.get("source") != str(self.source)
            or plan.get("source_commit") != state.get("run", {}).get("source_commit")
            or plan.get("targets") != targets
            or plan.get("in_scope") != current_scope
            or plan.get("mutations_performed") is not False
        ):
            raise ValueError("Graph controller preflight plan differs from the current Source or scope")
        actions = plan.get("next_actions")
        blocked = plan.get("blocked")
        if not isinstance(actions, list) or not isinstance(blocked, list):
            raise ValueError("Graph controller preflight transitions are malformed")
        action_by_task = {
            item.get("task_id"): item for item in actions
            if isinstance(item, dict) and isinstance(item.get("task_id"), str)
        }
        blocked_by_task = {
            item.get("task_id"): item for item in blocked
            if isinstance(item, dict) and isinstance(item.get("task_id"), str)
        }
        if len(action_by_task) != len(actions) or len(blocked_by_task) != len(blocked):
            raise ValueError("Graph controller preflight contains duplicate or invalid task transitions")
        if set(action_by_task).intersection(blocked_by_task):
            raise ValueError("Graph controller preflight marks a task both actionable and blocked")
        for row in state.get("tasks") or []:
            if not isinstance(row, dict) or not row.get("in_scope"):
                continue
            task_id = row.get("id")
            blocked_item = blocked_by_task.get(task_id)
            action = action_by_task.get(task_id)
            if blocked_item is not None and blocked_item.get("reason") == "dependencies":
                dependencies = blocked_item.get("dependencies") or []
                row["state"] = "pending"
                row["progress"] = {
                    "phase": "dependencies_unmet",
                    "blocked_reason": "Waiting for: " + ", ".join(map(str, dependencies)),
                    "transition_context": "The exact preflight plan found unfinished dependencies.",
                }
            elif action is not None and action.get("kind") == "decompose":
                row["state"] = "decomposition_ready"
                row["progress"] = {
                    "phase": "decomposition_ready",
                    "transition_context": "The exact preflight plan found this parent ready for decomposition.",
                }
            elif action is not None:
                row["state"] = "ready"
                row["progress"] = {
                    "phase": "not_started",
                    "transition_context": "The task is ready; no preflight action has been executed.",
                }

    def _apply_running_controller_projection(
        self, state: dict, controller: dict, action: dict,
    ) -> None:
        """Distinguish graph-ready work from idle conversation and internal validation."""
        action_task = action.get("task_id")
        action_kind = action.get("kind")
        active_action_kinds = {
            "start_worker", "wait_worker", "settle_worker", "post_crew",
            "sync_candidate", "auto_approve", "integrate",
        }
        checkout_write_actions = {
            "prepare", "scope", "reserve", "post_crew", "sync_candidate",
            "auto_approve", "integrate",
        }
        auto_approve = controller.get("auto_approve_gauntlet") is True
        source_commit = state.get("run", {}).get("source_commit")
        for row in state.get("tasks") or []:
            if not isinstance(row, dict) or not row.get("in_scope"):
                continue
            task_id = row.get("id")
            phase = (row.get("progress") or {}).get("phase")
            has_candidate = bool(row.get("candidate_commit"))
            internal_transition = (
                phase in {"worker_succeeded", "approved", "integrating"}
                or (task_id == action_task and action_kind in active_action_kinds)
            )
            checkout_write_in_progress = (
                task_id == action_task
                and action_kind in checkout_write_actions
                and row.get("state") == "blocked"
                and phase == "checkout_needs_attention"
            )
            automatic_review = False
            if (row.get("state") == "human_action" and auto_approve
                    and task_id != "NSC-042" and isinstance(source_commit, str)):
                try:
                    automatic_review = is_synthetic_gauntlet(
                        self.source, str(task_id), source_commit,
                    )
                except (OSError, RuntimeError, ValueError):
                    automatic_review = False
            if (automatic_review or checkout_write_in_progress
                    or (has_candidate and phase in {"approved", "integrating"})):
                row["state"] = "active"
                row["progress"] = {
                    "phase": "automatic_validation",
                    "transition_context": (
                        "The graph controller is validating and integrating this disposable "
                        "Gauntlet candidate automatically."
                    ),
                }
            elif row.get("state") == "assistant_idle" and internal_transition:
                row["state"] = "active"
                row["progress"] = {
                    "phase": "candidate_validation",
                    "transition_context": (
                        "The worker finished; the graph controller is validating and settling "
                        "its exact candidate."
                    ),
                }
            elif row.get("state") == "assistant_idle":
                row["state"] = "ready"
                row["progress"] = {
                    "phase": "graph_ready",
                    "transition_context": (
                        "This task is in the active graph run and is waiting for worker admission."
                    ),
                }

    @staticmethod
    def _apply_controller_scope(state: dict, explicit_targets) -> None:
        """Apply the controller's complete committed graph scope to the rows."""
        if not isinstance(explicit_targets, list):
            return
        rows = state.get("tasks") or []
        by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
        scoped = {
            task_id for task_id in explicit_targets
            if isinstance(task_id, str) and task_id in by_id
        }
        changed = True
        while changed:
            changed = False
            for row in rows:
                task_id = row.get("id")
                if task_id in scoped:
                    for dependency in row.get("depends_on") or []:
                        if isinstance(dependency, str) and dependency in by_id and dependency not in scoped:
                            scoped.add(dependency)
                            changed = True
                elif row.get("parent") in scoped and task_id not in scoped:
                    scoped.add(task_id)
                    changed = True
        for row in rows:
            row["in_scope"] = row.get("id") in scoped
        state["run"]["targets"] = [row["id"] for row in rows if row.get("id") in scoped]

    @staticmethod
    def _apply_decomposition_projection(rows: list[dict]) -> None:
        """Project a completed decomposed parent from its retained children.

        A parent is complete only when every exact child ID from its contract is
        present in the current projection and is locally accepted.  In
        particular, an incomplete or missing child must never be treated as a
        successful decomposition.
        """
        by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
        for parent in rows:
            if (not isinstance(parent, dict)
                    or parent.get("decomposition_state") != "decomposed"
                    or parent.get("state") != "aggregate"):
                continue
            child_ids = parent.get("decomposition_children")
            if (not isinstance(child_ids, list) or not child_ids
                    or any(not isinstance(child_id, str) or not child_id for child_id in child_ids)
                    or len(set(child_ids)) != len(child_ids)):
                continue
            children = [by_id.get(child_id) for child_id in child_ids]
            if any(child is None or child.get("state") != "local_accepted" for child in children):
                continue
            parent["state"] = "local_accepted"
            parent["progress"] = {
                "phase": "children_integrated",
                "transition_context": "Every reviewed decomposition child is integrated locally.",
            }

    def _load_simulation(self) -> dict | None:
        """Read and validate the explicit visual-only projection, when present."""
        path = self.manager.records / "viewer-simulation.json"
        if not path.is_file():
            return None
        try:
            simulation = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Viewer simulation is unreadable: {exc}") from exc
        if not isinstance(simulation, dict) or simulation.get("schema_version") != "assistant-viewer-simulation/v1":
            raise ValueError("Viewer simulation has an unsupported schema")
        overrides = simulation.get("tasks")
        if not isinstance(overrides, dict):
            raise ValueError("Viewer simulation task overrides are missing")
        virtual_tasks = simulation.get("virtual_tasks", [])
        if not isinstance(virtual_tasks, list):
            raise ValueError("Viewer simulation virtual tasks must be a list")
        return simulation

    def _apply_simulation(self, state: dict, activity: dict, simulation: dict) -> None:
        """Project an explicitly labelled visual-only lifecycle demonstration."""
        overrides = simulation["tasks"]
        virtual_tasks = simulation.get("virtual_tasks", [])
        known_ids = {row["id"] for row in state["tasks"]}
        virtual_ids = set()
        for virtual in virtual_tasks:
            if (not isinstance(virtual, dict) or not isinstance(virtual.get("id"), str)
                    or virtual["id"] in known_ids):
                continue
            virtual_id = virtual["id"]
            state["tasks"].append({
                "id": virtual_id,
                "title": str(virtual.get("title") or virtual_id),
                "parent": virtual.get("parent"),
                "depends_on": list(virtual.get("depends_on") or []),
                "kind": "implementation",
                "disposition": "active",
                "decomposition_state": "concrete",
                "decomposition_children": [],
                "execution_scope": "single_agent",
                "resources": [],
                "acceptance": [],
                "in_scope": True,
                "state": "ready",
                "checkout_path": None,
                "checkout_exists": False,
                "checkout_commit": None,
                "worker": None,
                "progress": {"phase": "not_started"},
                "token_cost": None,
                "notes": "Simulated decomposition child; no task contract or Git mutation was created.",
                "reason": "Created only in the visual lifecycle simulation.",
                "taskgraph": None,
                "simulation": True,
            })
            known_ids.add(virtual_id)
            virtual_ids.add(virtual_id)
        rows = {row["id"]: row for row in state["tasks"]}
        visible_ids = set(virtual_ids)
        for task_id, override in overrides.items():
            if task_id not in rows or not isinstance(override, dict):
                continue
            row = rows[task_id]
            simulated_state = override.get("state")
            phase = override.get("phase")
            if isinstance(simulated_state, str) and simulated_state:
                row["state"] = simulated_state
            if isinstance(phase, str) and phase:
                row["progress"] = {
                    "phase": phase,
                    "transition_context": str(override.get("message") or "Simulated lifecycle event."),
                }
            if isinstance(override.get("depends_on"), list):
                row["depends_on"] = [
                    dependency for dependency in override["depends_on"]
                    if isinstance(dependency, str) and dependency
                ]
            row["simulation"] = True
            row["worker"] = override.get("worker")
            if phase == "simulation_out_of_scope":
                visible_ids.discard(task_id)
            else:
                visible_ids.add(task_id)
        for row in state["tasks"]:
            row["in_scope"] = row["id"] in visible_ids
        state["run"].update({
            "status": "simulation",
            "marker": "SIMULATION — NO PROVIDERS",
            "simulation": True,
        })
        activity.update({
            "headline": str(simulation.get("headline") or "Gauntlet lifecycle simulation"),
            "description": str(simulation.get("description") or "Visual-only demo; no providers or Git mutations."),
            "liveness": "simulated",
            "provider_profile": "fixture — no provider spend",
        })
        state["simulation"] = {
            "active": True,
            "step": simulation.get("step"),
            "updated_at": simulation.get("updated_at"),
        }

    def task_row(self, contract: dict, *, read_durable_state: bool = True) -> dict:
        task_id = contract["id"]
        active = contract.get("contract_disposition") == "active"
        executable = active and contract.get("execution_scope") != "not_applicable"
        visible_parent = active and contract.get("decomposition_state") == "decomposed"
        row = {
            "id": task_id, "title": contract.get("title"),
            "parent": contract.get("parent"), "depends_on": contract.get("depends_on") or [],
            "kind": contract.get("kind"), "disposition": contract.get("contract_disposition"),
            "decomposition_state": contract.get("decomposition_state"),
            "decomposition_children": contract.get("decomposition_children") or [],
            "execution_scope": contract.get("execution_scope"),
            "resources": contract.get("exclusive_resources") or [],
            "acceptance": [item.get("requirement") for item in contract.get("acceptance_criteria", [])],
            "in_scope": executable or visible_parent,
            "state": ("ready" if executable else "aggregate" if active else "cancelled"),
            "checkout_path": None, "checkout_exists": False,
            "checkout_commit": None, "worker": None,
            "progress": {"phase": "not_started"}, "token_cost": None,
            "notes": contract.get("notes"), "reason": contract.get("decomposition_reason"),
            "taskgraph": None,
        }
        if not read_durable_state:
            return row
        decomposition_receipt = self.manager.records / f"{task_id}.decomposition.json"
        if decomposition_receipt.is_file():
            try:
                decomposition = json.loads(decomposition_receipt.read_text(encoding="utf-8"))
                if (decomposition.get("schema_version") != "assistant-decomposition/v1"
                        or decomposition.get("task_id") != task_id
                        or decomposition.get("source") != str(self.source)):
                    raise ValueError("decomposition record identity differs")
                status = decomposition.get("status")
                if status == "running":
                    row["state"] = "active"
                    row["progress"] = {
                        "phase": "decomposition_working",
                        "transition_context": "Two-role decomposition crew is proposing and reviewing children.",
                    }
                elif status == "review_ready":
                    row["state"] = "human_action"
                    row["progress"] = {
                        "phase": "decomposition_review_ready",
                        "transition_context": "Independent review passed; the exact graph plan is ready for local application.",
                    }
                elif status == "failed":
                    row["state"] = "blocked"
                    row["progress"] = {
                        "phase": "decomposition_failed",
                        "blocked_reason": decomposition.get("error") or "Decomposition crew failed.",
                        "transition_context": "Decomposition artifacts and logs were retained.",
                    }
                elif status == "applied":
                    children = sorted(contract.get("decomposition_children") or [])
                    if children != sorted(decomposition.get("child_ids") or []):
                        raise ValueError("applied decomposition children differ from committed parent")
                    row["state"] = "aggregate"
                    row["progress"] = {
                        "phase": "decomposition_applied",
                        "transition_context": "Reviewed children were committed locally and are now ordinary tasks.",
                    }
                row["decomposition_run"] = {
                    "run_id": decomposition.get("run_id"),
                    "providers": decomposition.get("providers"),
                    "plan_id": (decomposition.get("review") or {}).get("plan_id"),
                    "child_ids": decomposition.get("child_ids") or (decomposition.get("review") or {}).get("child_ids"),
                    "artifact_root": decomposition.get("artifact_root"),
                }
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                row["state"] = "blocked"
                row["progress"] = {
                    "phase": "decomposition_record_invalid",
                    "blocked_reason": str(exc),
                    "transition_context": "The decomposition display record could not be authenticated.",
                }
        receipt = self.manager.records / f"{task_id}.json"
        if receipt.exists():
            try:
                checkout = self.manager.observe(task_id)
                row.update({"checkout_path": checkout["checkout"], "checkout_exists": True,
                            "checkout_commit": checkout["current_commit"],
                            "state": "assistant_idle",
                            "progress": {"phase": checkout["status"],
                                         "transition_context": "Task checkout exists; no worker has been started by this tool."}})
                if checkout.get("worker") or checkout.get("launch"):
                    from Pipeline.AssistantControl.worker_control import status as worker_status
                    observation = worker_status(self.manager, task_id)
                    self._apply_worker_projection(row, observation)
                if checkout.get("status") == "validation_failed":
                    materialization_failure = checkout.get("materialization_failure") or {}
                    candidate_failure = checkout.get("candidate_validation_failure") or {}
                    failure = materialization_failure or candidate_failure
                    row["state"] = "blocked"
                    row["progress"] = {
                        "phase": (
                            "unity_validation_failed"
                            if materialization_failure else "candidate_validation_failed"
                        ),
                        "blocked_reason": failure.get(
                            "validation_error", "Candidate validation failed; inspect the checkout.",
                        ),
                        "transition_context": (
                            "The exact candidate failed its focused tests. The checkout and "
                            "test failure are retained for the next crew."
                        ),
                    }
                    row["failed_candidate_commit"] = (
                        failure.get("materialized_commit") or failure.get("candidate_commit")
                    )
                    candidate = {}
                else:
                    candidate = checkout.get("candidate") or {}
                if candidate:
                    from Pipeline.AssistantControl.review import ReviewGate
                    commit = candidate.get("commit", "")
                    ReviewGate(self.manager)._require_candidate(
                        checkout, commit, allow_pending_materialization=True,
                    )
                    row["candidate_commit"] = commit
                    row["candidate_kind"] = candidate.get("kind", "crew_reviewed")
                    row["crew_review"] = candidate.get("crew_review", True)
                    status = checkout["status"]
                    if status in {"needs_materialization", "materialization_failed"}:
                        failure = checkout.get("materialization_failure") or {}
                        row["state"] = "blocked"
                        row["progress"] = {
                            "phase": status,
                            "blocked_reason": failure.get(
                                "materialization_error",
                                "Required Unity materialization has not completed.",
                            ),
                            "transition_context": (
                                "The code candidate is retained. The Windows Unity builder must "
                                "complete before Vincent is asked to review it."
                            ),
                        }
                    else:
                        if status == "integrated":
                            integrated = checkout.get("integration") or {}
                            if integrated.get("candidate") != commit:
                                raise ValueError("Integrated task is not bound to its candidate commit")
                            git(self.source, "merge-base", "--is-ancestor", commit, "HEAD")
                        row["state"] = (
                            "human_action" if status == "awaiting_human"
                            else "local_accepted" if status == "integrated"
                            else "assistant_idle"
                        )
                    automated = (checkout.get("approval") or {}).get("authority") == "assistant_gauntlet_automation"
                    messages = {
                        "awaiting_human": "Open this checkout in Unity and tell your assistant whether this exact commit passes.",
                        "approved": ("Automated Gauntlet validation passed; local integration has not finished."
                                     if automated else "Approved by Vincent; local integration has not finished."),
                        "changes_requested": "Vincent requested changes. The existing candidate is retained.",
                        "integrating": "Local integration is unfinished; inspect before retrying.",
                        "integrated": ("Validated Gauntlet candidate integrated locally."
                                       if automated else "Integrated locally; successful-project preservation is pending."),
                    }
                    if status not in {"needs_materialization", "materialization_failed"}:
                        row["progress"] = {
                            "phase": status,
                            "transition_context": messages.get(
                                status, "Candidate retained for inspection."
                            ),
                        }
                    if candidate.get("kind") == "assistant_restored" and status == "awaiting_human":
                        row["progress"]["transition_context"] = (
                            "Assistant-restored reference candidate; crew review is false. "
                            "Open it in Unity and test the displayed commit before approving."
                        )
                    if candidate.get("kind") == "unity_materialized" and status == "awaiting_human":
                        row["progress"]["transition_context"] = (
                            "The crew-reviewed C# was materialized by DoorPrototypeSceneBuilder.Build, "
                            "and NSC-042's focused Unity tests passed at this exact commit. "
                            "Crew review does not cover the generated payload; open this checkout in "
                            "Unity and visually test the displayed commit before approving."
                        )
                    if candidate.get("kind") == "source_synchronized":
                        row["synchronized_source_commit"] = candidate.get("source_commit")
                        row["original_candidate_commit"] = (candidate.get("original_candidate") or {}).get("commit")
                        if status == "awaiting_human":
                            row["progress"]["transition_context"] = (
                                "Source merged into this task checkout. This version has no new crew review; "
                                "open it in Unity and test the displayed commit before approving.")
                    row["human_review"] = checkout.get("human_review")
                successful = checkout.get("successful_project")
                if successful:
                    approved = checkout.get("approval") or {}
                    candidate = checkout.get("candidate") or {}
                    integrated = checkout.get("integration") or {}
                    commit = successful.get("commit")
                    if (checkout["status"] != "integrated" or approved.get("decision") != "approve"
                            or commit != approved.get("commit") or commit != candidate.get("commit")
                            or commit != integrated.get("candidate")
                            or checkout["task_contract_sha256"] != contract["task_contract_sha256"]):
                        raise ValueError("Successful project is not bound to this task's approved integration")
                    git(self.source, "merge-base", "--is-ancestor", commit, "HEAD")
                    saved = Path(successful["path"])
                    if git(saved, "rev-parse", "HEAD").decode().strip() != commit:
                        raise ValueError("Saved successful project now points to a different commit")
                    if git(saved, "rev-parse", "HEAD^{tree}").decode().strip() != candidate.get("tree"):
                        raise ValueError("Saved successful project tree differs")
                    row["successful_project_path"] = str(saved)
                    row["successful_project_commit"] = commit
                    row["state"] = "local_accepted"
                    row["progress"] = {"phase": "integrated",
                                       "transition_context": "Human-approved candidate integrated locally and retained in SuccessfullTasks."}
            except (OSError, RuntimeError, ValueError) as exc:
                row["state"] = "blocked"
                row["progress"] = {"phase": "checkout_needs_attention", "blocked_reason": str(exc)}
        return row

    def _bound_execution_crew(self, task_id: str, checkout: Path, worker: Mapping[str, Any]) -> dict[str, Any] | None:
        """Locate the exact durable ExecutionCrew run this worker attempt owns.

        ``compose.yaml`` binds ``./Pipeline/ExecutionCrew/outputs`` straight onto
        the container's ``/execution-output`` for every exec service, so the
        crew's own ``progress.jsonl`` and ``role_results`` land in this task's
        checkout in real time, whether the crew is still running or has already
        finished — no separate bridge is needed to make the events durable.
        A candidate run directory is accepted only when its own recorded
        ``run_started`` event names this exact task and was written at or after
        this exact worker attempt began; ambiguity is treated the same as
        absence rather than guessed at.
        """
        started_at = gauntlet.parse_timestamp(worker.get("started_at"))
        if started_at is None:
            return None
        outputs = checkout / "Pipeline" / "ExecutionCrew" / "outputs"
        try:
            if not outputs.is_dir():
                return None
            candidates = []
            for run_dir in outputs.iterdir():
                if not run_dir.is_dir() or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_dir.name) is None:
                    continue
                if not run_dir.resolve().is_relative_to(outputs.resolve()):
                    continue
                progress_path = run_dir / "progress.jsonl"
                rows = self.template.cache.get(progress_path, gauntlet.read_jsonl)
                if not isinstance(rows, list) or not rows:
                    continue
                rows = [entry for entry in rows if isinstance(entry, dict)
                        and entry.get("task_id") == task_id and entry.get("run_id") == run_dir.name]
                start_row = next((entry for entry in rows if entry.get("event") == "run_started"), None)
                started = gauntlet.parse_timestamp(start_row.get("timestamp_utc")) if start_row else None
                if started is None or started < started_at:
                    continue
                candidates.append({"run_dir": run_dir, "rows": rows})
            return candidates[0] if len(candidates) == 1 else None
        except OSError:
            return None

    def _apply_worker_projection(self, row: dict, observation: dict) -> None:
        """Project the exact worker attempt before candidate state is applied."""
        worker = observation["worker"]
        row["worker"] = worker
        row["worker_observation"] = observation
        running = worker.get("status") in {"running", "starting", "ready_pending"}
        # None is the short launcher handoff interval. Only an explicit False
        # proves that the recorded host has exited.
        active = running and observation.get("host_identity_alive") is not False
        if active:
            row["state"] = "active"
            context = ("Stop requested; waiting for worker exit." if observation["stop_requested"]
                       else "Assistant-started worker is running in this task checkout.")
        elif running:
            row["state"] = "blocked"
            context = "Worker host is absent or cannot be verified; inspect retained output before restarting."
        elif worker.get("status") in {"failed", "stopped"}:
            row["state"] = "blocked"
            context = "Worker ended; checkout and output are retained for inspection."
        elif worker.get("status") == "spawn_failed":
            row["state"] = "blocked"
            context = f"Worker spawn failed: {worker.get('error', 'exact error unavailable')}"
        elif worker.get("status") == "succeeded":
            row["state"] = "assistant_idle"
            context = "Worker finished; the reviewed output is waiting for its next controlled step."
        else:
            context = "Worker state is retained for inspection; no output is claimed."
        progress = {"phase": "worker_" + str(worker.get("status", "unknown")),
                   "transition_context": context}
        checkout_path = row.get("checkout_path")
        if isinstance(checkout_path, str) and checkout_path:
            binding = self._bound_execution_crew(row["id"], Path(checkout_path), worker)
            if binding is not None:
                # Every field below is read from the crew's own recorded rows
                # (role/attempt/status/duration_seconds events and their
                # role_results). Nothing here is derived from worker status,
                # the task contract, or controller actions.
                agents = self.template.crew_agents_from_rows(
                    task_id=row["id"], run_dir=binding["run_dir"], rows=binding["rows"],
                    active=active, now=time.time(),
                    stop_at=None if active else gauntlet.parse_timestamp(worker.get("finished_at")),
                )
                for agent in agents:
                    agent["action"] = gauntlet.AGENT_ROLE_ACTIONS.get(agent["role"], agent["label"])
                progress["agents"] = agents
                current = next((agent for agent in reversed(agents) if agent["status"] == "running"), None)
                progress["current_agent"] = current
                if current is not None:
                    required = next((entry.get("required_roles", []) for entry in binding["rows"]
                                     if entry.get("event") == "run_started"), [])
                    execution_roles = list(dict.fromkeys(
                        role for role in required
                        if isinstance(role, str) and role != "contract_locality_auditor"
                    ))
                    role = current["role"]
                    if role == "contract_locality_auditor":
                        stage_label = "Preparing execution crew · " + current["label"]
                    elif role in execution_roles:
                        current["role_index"] = execution_roles.index(role) + 1
                        current["role_count"] = len(execution_roles)
                        stage_label = f"Execution crew · {current['label']} {current['role_index']} of {current['role_count']}"
                    else:
                        stage_label = "Execution crew · " + current["label"]
                    progress["pipeline_stages"] = [{
                        "label": stage_label, "status": "active",
                        "elapsed_seconds": current["duration_seconds"],
                    }]
        row["progress"] = progress


def make_server(source: Path, checkout_root: Path, port: int = 8813) -> ThreadingHTTPServer:
    reader = AssistantSnapshot(source, checkout_root)
    instance_id = uuid.uuid4().hex

    class ReadOnlyHandler(gauntlet.Handler):
        health = {"status": "ok", "mode": "assistant", "read_only": True}

        def _state(self):
            state = reader.build(max_age_seconds=STATE_CACHE_SECONDS)
            # Immutable per-process identity, not part of the mutable graph
            # snapshot: a launcher polling /api/state after starting a viewer
            # must be able to confirm it reached this exact instance (not a
            # stale one still holding an old port) before trusting anything
            # else in the response.
            state["viewer_identity"] = dict(self.server.viewer_identity)
            return state

        def do_POST(self):
            self._send(405, b'Use conversation to control this project.', "text/plain")

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    # Every open browser tab shares one bounded state read. Without
                    # this cache, each SSE client launches the same Git inspection
                    # independently every two seconds.
                    state = reader.build(max_age_seconds=STATE_CACHE_SECONDS)
                    state["viewer_identity"] = dict(self.server.viewer_identity)
                    self.wfile.write(("data: " + json.dumps(state) + "\n\n").encode())
                    self.wfile.flush()
                    time.sleep(2)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    # Binding happens inside the constructor (server_bind/server_activate via
    # TCPServer.__init__), so ExclusiveListenerError/OSError already
    # propagates from here before any identity is attached or success is
    # reported to a caller.
    server = _ExclusiveHTTPServer(("127.0.0.1", port), ReadOnlyHandler)
    server.daemon_threads = True
    server.viewer_identity = {
        "instance_id": instance_id,
        "pid": os.getpid(),
        "source": str(reader.source),
        "checkout_root": str(reader.manager.root),
        "port": server.server_port,
    }
    return server
