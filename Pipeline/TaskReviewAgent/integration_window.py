"""Host-owned delivery window. Gate admission never enters a provider action menu."""
from __future__ import annotations

import json
from functools import wraps
import os
import socket
import subprocess
import uuid
from pathlib import Path
from typing import Any, Mapping

from .integration_gate import GitIntegrationGate, GateWakeListener, IntegrationGateError, owner_identity, ordered_waiters, same_owner

DELIVERY_PHASES = {"delivery_evidence", "merge_closeout"}
MERGE_ACTIONS = {"inspect_or_merge_pull_request", "verify_post_merge_and_complete"}


def guard_controller_mutations(controller: Any) -> None:
    """Fence direct public-controller calls as well as supervisor dispatch.

    Construction is the boundary: low-level unit fixtures which deliberately
    skip __init__ can still exercise the underlying reintegration primitives.
    Every normally constructed production controller enforces the remote owner.
    """
    for name in ("prepare_task_checkout", "integrate_current_main", "run_authoritative_unity_test",
                 "create_delivery_review_draft", "create_delivery_review_proposal", "publish_delivery_review",
                 "finalize_delivery_evidence_and_open_pr", "inspect_or_merge_pull_request", "verify_post_merge_and_complete"):
        original = getattr(controller, name)
        @wraps(original)
        def guarded(*args, _original=original, **kwargs):
            window = controller.integration_window
            if not window.held or not window.in_action:
                raise IntegrationGateError("final integration action requires this run's active integration gate operation")
            window.gate.require_owner(window.gate.read()[1], window.identity)
            return _original(*args, **kwargs)
        setattr(controller, name, guarded)


def workflow_state(observation: Mapping) -> Mapping:
    return (observation.get("coordination") or {}).get("workflow_state") or {}


def require_no_legacy_delivery_owner(service: Any, gate_owner: Mapping | None) -> None:
    """Migration fence: a pre-gate worker cannot be presumed quiescent."""
    from .issue_workflow_store import _consistent_snapshots, issue_author_authorized
    issues = [issue for issue in service.backend.list_issues()
              if str(issue.get("state", "")).upper() != "CLOSED" and issue_author_authorized(issue)]
    for entry in _consistent_snapshots(service.backend, issues):
        if entry.error:
            raise entry.error
        snapshot = entry.snapshot
        if snapshot is None or not snapshot.managed:
            continue
        if not snapshot.valid or snapshot.state is None or snapshot.pending_transition is not None:
            raise IntegrationGateError("integration migration requires coherent managed Issue reservations")
        state = snapshot.state.to_dict()
        if state["state"] == "agent_working" and state["phase"] in DELIVERY_PHASES:
            if not gate_owner or any(state[k] != gate_owner[k] for k in ("task_id", "worker_id")):
                raise IntegrationGateError(
                    f"legacy downstream owner {state['task_id']} / {state['worker_id']} has no matching gate receipt; "
                    "fence the old worker, reconcile remote operations, and release its Issue lease before resuming")


class IntegrationWindow:
    def __init__(self, controller: Any, *, gate: GitIntegrationGate | None = None,
                 automated_validator: Any = None):
        self.controller = controller
        self.source = Path(controller.workflow.base_observer.root)
        self.gate = gate or GitIntegrationGate(self.source)
        self.automated_validator = automated_validator or self._validate_automated
        self.identity: dict | None = None
        self.held = False
        self.finished = False
        self.automated_revalidation = False
        self.in_action = False

    def bind_run(self, run_id: str) -> None:
        if self.identity is not None:
            if self.identity["run_id"] != run_id:
                raise IntegrationGateError("integration window cannot change run identity")
            return
        # Replaying the exact worker/run recovers its original unguessable lease.
        # This local handle is not authority: every action checks the remote CAS.
        key = uuid.uuid5(uuid.NAMESPACE_URL, run_id + ":" + self.controller.workflow.worker_id).hex
        directory = self.controller.state_root / "integration-owners" / self.gate.domain
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (key + ".json")
        proposed = owner_identity(self.controller.task_id, run_id, self.controller.workflow.worker_id)
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(proposed, stream, sort_keys=True)
        except FileExistsError:
            try:
                proposed = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise IntegrationGateError("interrupted gate identity write; reconcile the preserved handle") from exc
        verified = owner_identity(*(proposed[k] for k in ("task_id", "run_id", "worker_id", "lease_id")))
        if (verified["task_id"] != self.controller.task_id or verified["run_id"] != run_id
                or verified["worker_id"] != self.controller.workflow.worker_id):
            raise IntegrationGateError("stale/mismatched integration owner handle")
        self.identity = verified

    def checkpoint(self, observation: Mapping) -> dict | None:
        if self.identity is None:
            raise IntegrationGateError("integration gate needs the durable worker run identity")
        state = workflow_state(observation)
        if not self.held and not self.finished:
            _, durable = self.gate.read()
            if same_owner(durable["owner"], self.identity):
                owner = self.gate.require_owner(durable, self.identity)
                self.held = True
                self.automated_revalidation = owner["progress"] == "automated_revalidation_pending"
        if self.held:
            _, gate_state = self.gate.read()
            owner = self.gate.require_owner(gate_state, self.identity)
            if owner["operation"] is not None:
                raise IntegrationGateError("unfinished gate operation on resume; reconcile before retry")
            if state.get("state") == "human_action_required":
                if self.automated_revalidation and state.get("phase") == "unity_runtime_validation":
                    self.gate.progress(self.identity, "automated_exact_commit_validation", operation=self.validation_operation())
                    self.in_action = True
                    self.automated_validator(state)
                    self.gate.progress(self.identity, "automated_validation_confirmed")
                    self.in_action = False
                    self.automated_revalidation = False
                    # Validate fresh Issue authority on the next observation;
                    # the prior exact human result is never carried forward.
                    return {"status": "continue"}
                self.settle(observation, "human_action_required")
            elif state.get("state") == "complete":
                self.settle(observation, "completed")
            return None
        if self.finished or state.get("phase") not in DELIVERY_PHASES:
            return None
        if (observation.get("environment") or {}).get("ready") is not True:
            return None
        if state.get("state") not in {"agent_ready", "agent_working"}:
            return None
        if state.get("state") == "agent_working" and state.get("worker_id") != self.identity["worker_id"]:
            return self.deferred(observation, "another worker owns the Issue")
        require_no_legacy_delivery_owner(self.controller.workflow.issue_workflow, self.gate.read()[1]["owner"])
        result = self.gate.enqueue(self.controller.task_id, ready_at=state["updated_at_utc"],
                                   ready_event=state["last_event_id"])
        if result["status"] == "deferred":
            return self.deferred(observation, "gate queue CAS contention")
        result = self.gate.acquire(self.identity)
        if result["status"] != "acquired":
            # Old resumptions may already own an Issue lease. Yield that exact
            # lease using the existing append-only transition, never a fatal.
            if state.get("state") == "agent_working":
                from .downstream_resilience import _release_active_lease
                _release_active_lease(self.controller, reason="integration_gate_waiting", details={"action": "gate_admission"})
            return self.deferred(observation, result.get("reason", "gate occupied"))
        self.held = True
        if result["owner"]["operation"] is not None:
            raise IntegrationGateError("same-owner resume has an unfinished operation; reconcile exact journal")
        # Acquisition precedes the authoritative main refresh and every delivery
        # action. The existing next-action machinery performs reintegration.
        self.gate.progress(self.identity, "refresh_authoritative_main", operation="git_refresh")
        self.in_action = True
        from .downstream_pipeline import _git
        root = self.controller.checkout if self.controller.checkout.is_dir() else self.source
        _git(self.controller.command_runner, root, "fetch", "origin",
             "+refs/heads/main:refs/remotes/origin/main", timeout_seconds=900.0)
        self.gate.progress(self.identity, "main_refreshed")
        self.in_action = False
        return {"status": "continue"}

    def deferred(self, observation: Mapping, reason: str) -> dict:
        return dict(schema_version="1.0", task_id=self.controller.task_id, status="integration_gate_waiting",
                    authority="durable_integration_gate", deterministic_final_state=observation,
                    next_action="Wait for gate release notification; recovery polling only.", blockers=[reason])

    def before_action(self, action: str) -> None:
        if not self.held:
            raise IntegrationGateError("downstream action requires the integration gate")
        kind = ("ci" if action == "inspect_or_merge_pull_request" else
                self.validation_operation() if action == "run_authoritative_unity_test" else action)
        self.gate.progress(self.identity, action, operation=kind)
        self.in_action = True

    def validation_operation(self) -> str:
        from .downstream_resilience import validation_plan_for
        task = self.controller.workflow.issue_workflow.task_loader(self.controller.task_id)
        plan = validation_plan_for(self.controller.checkout, task)
        return "source" if plan and plan["required_test_platforms"] == ["SyntheticSource"] else "unity"

    def after_action(self, action: str) -> None:
        stage = action + "_confirmed"
        if action in {"integrate_current_main", "inspect_or_merge_pull_request"}:
            snapshot = self.controller.workflow.issue_workflow.find(self.controller.task_id)
            if snapshot is None or not snapshot.valid or snapshot.state is None:
                raise IntegrationGateError("integrated handoff receipt missing")
            if snapshot.state.state.value == "human_action_required" and snapshot.state.phase.value == "unity_runtime_validation":
                # The existing reintegrator resolves exact authority before
                # changing HEAD. At the PR evidence head that resolver may
                # deliberately require a later evidence-release event, so do
                # not re-run it speculatively before an ordinary CI inspection.
                from .contracts import semantic_sha256
                receipt = dict(self.controller.state.get("mainline_reintegration") or {})
                digest = receipt.pop("receipt_sha256", None)
                self.automated_revalidation = bool(
                    receipt.get("validation_authority_kind") == "automated"
                    and receipt.get("integrated_commit") == snapshot.state.head_commit
                    and receipt.get("task_id") == self.controller.task_id
                    and digest == semantic_sha256(receipt))
                if self.automated_revalidation:
                    stage = "automated_revalidation_pending"
        self.gate.progress(self.identity, stage)
        self.in_action = False

    def settle(self, observation: Mapping, reason: str) -> None:
        if not self.held:
            return
        service = self.controller.workflow.issue_workflow
        snapshot = service.find(self.controller.task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise IntegrationGateError("gate settlement requires the verified durable Issue receipt")
        state = snapshot.state.to_dict()
        if state.get("last_event_id") != workflow_state(observation).get("last_event_id"):
            raise IntegrationGateError("Issue changed before gate settlement; re-observe")
        complete = reason == "completed"
        if complete and state["state"] != "complete":
            raise IntegrationGateError("gate completion requires verified Issue closeout")
        if not complete and state["state"] == "agent_working":
            from .downstream_resilience import _release_active_lease
            if not _release_active_lease(self.controller, reason=reason, details={"action": "gate_settlement"}):
                raise IntegrationGateError("cannot prove Issue lease relinquished")
            snapshot = service.find(self.controller.task_id)
            if snapshot is None or not snapshot.valid or snapshot.state is None:
                raise IntegrationGateError("Issue lease settlement receipt missing")
            state = snapshot.state.to_dict()
        receipt = dict(self.identity, schema_version="1.0", status="completed" if complete else "quiescent",
                       issue_event_id=state["last_event_id"], issue_state=state["state"],
                       head_commit=state["head_commit"])
        if complete:
            from .issue_workflow import WorkflowEventType
            event = next((event for event in snapshot.events
                          if event.event_id == state["last_event_id"]), None)
            if (event is None or event.event_type is not WorkflowEventType.COMPLETED
                    or event.actor_id != self.identity["worker_id"]
                    or event.details.get("merged_commit") != self.controller.state.get("merged_commit")):
                raise IntegrationGateError("completion receipt does not match this owner's verified closeout")
            receipt["verified_main"] = event.details["merged_commit"]
        self.gate.release(self.identity, reason=reason, receipt=receipt)
        self.held, self.finished = False, True

    def failure(self, error: BaseException, *, action: str = "pipeline") -> None:
        if not self.held:
            return
        uncertain = (isinstance(error, (KeyboardInterrupt, SystemExit, subprocess.TimeoutExpired, IntegrationGateError))
                     or (action in MERGE_ACTIONS and not str(error).startswith("pull-request checks failed:"))
                     or "timeout" in str(error).casefold()
                     or "timed out" in str(error).casefold())
        if uncertain:
            self.gate.quarantine(self.identity, f"{action}: {type(error).__name__}; reconcile preserved operation and remote state")
            self.held = False
            return
        if self.in_action:
            self.gate.progress(self.identity, action + "_failed_quiescent")
            self.in_action = False
        self.settle(self.controller.observe(), "recoverable_failure")

    def _validate_automated(self, state: Mapping) -> None:
        from .synthetic_gauntlet_approver import process_one_synthetic_handoff
        reports = []
        result = process_one_synthetic_handoff(
            self.controller.task_id, source=self.source, checkout_root=self.controller.checkout.parent,
            confirm_repository=self.controller._bound_repository(), apply=True,
            integration_owner=self.identity, report=reports.append)
        if result is None:
            raise IntegrationGateError("automated revalidation returned no durable exact-commit receipt")
        manifests = [report for report in reports if "manifest_path" in report]
        if len(manifests) != 1:
            raise IntegrationGateError("automated revalidation did not return one exact validation manifest")
        self.import_automated_manifest(manifests[0])

    def import_automated_manifest(self, report: Mapping) -> None:
        """Reuse the gate-held Unity result through the canonical evidence publisher.

        Re-import hashes from the newly verified Issue event, so this saves a
        duplicate exact-commit Unity run without trusting a path or exit code.
        """
        from Pipeline.Testing.validation_manifest import import_validation_manifest
        authority = self.controller._latest_validation_authority()
        if not authority or authority.get("kind") != "automated":
            raise IntegrationGateError("exact automated Issue authority missing after gated validation")
        details = authority["details"]
        validations = details.get("unity_validations", details.get("source_validations", []))
        if len(validations) != 1:
            raise IntegrationGateError("gated synthetic policy requires one exact validation")
        validation = validations[0]
        path = Path(report["manifest_path"])
        imported = import_validation_manifest(
            path, controller_root=path.parent, expected_commit=authority["tested_commit"],
            expected_tree=authority["tree"], expected_test_platform=validation["test_platform"],
            expected_test_filter=validation["test_filter"], expected_manifest_sha256=validation["manifest_sha256"],
            expected_xml_sha256=validation["xml_sha256"], expected_log_sha256=validation["log_sha256"])
        self.controller._publish_validation_evidence(
            imported.directory, imported.path.name, commit=authority["tested_commit"], tree=authority["tree"],
            test_platform=validation["test_platform"], test_filter=validation["test_filter"])


class GateAdmission:
    """Filter only delivery waiters before the existing architect selection.

    Implementation capacity/path-conflict policy stays in PollingOrchestrator.
    One controller event serves the entire pending set, including other hosts
    when NSC_GATE_WAKE_HOST names a reachable local interface.
    """
    def __init__(self, scheduler: Any, *, service: Any = None):
        self.scheduler = scheduler
        self.service = service
        self._gate: GitIntegrationGate | None = None
        self.listener: GateWakeListener | None = None
        self.observation: tuple | None = None
        self.issue_observations: dict = {}

    @property
    def gate(self) -> GitIntegrationGate:
        if self._gate is None:
            self._gate = GitIntegrationGate(self.scheduler.source)
        return self._gate

    def filter(self, entries: tuple) -> tuple:
        self.observation = None
        self.issue_observations = {}
        delivery = [entry for entry in entries if entry[1] in DELIVERY_PHASES]
        if not delivery:
            return entries
        if self.listener is None:
            self.listener = GateWakeListener(self.scheduler.worker_completion_event, self.gate.domain,
                                            host=os.getenv("NSC_GATE_WAKE_HOST") or socket.gethostbyname(socket.gethostname()),
                                            on_wake=lambda task_id: self.scheduler.events.emit(
                                                "gate_next_waiter_woken", task_id=task_id, gate_ref=self.gate.ref))
        service = self._service()
        _, initial_state = self.gate.read()
        require_no_legacy_delivery_owner(service, initial_state["owner"])
        for waiter in initial_state["queue"]:
            snapshot = service.find(waiter["task_id"])
            if snapshot is None or not snapshot.valid or snapshot.state is None:
                raise IntegrationGateError("queued Issue identity missing/corrupt; inspect the gate journal")
            if snapshot.state.state.value in {"human_action_required", "blocked", "complete"}:
                if not self.gate.withdraw(waiter["task_id"], issue_state=snapshot.state.state.value,
                                          issue_event_id=snapshot.state.last_event_id):
                    return tuple(entry for entry in entries if entry[1] not in DELIVERY_PHASES)
        # Register the complete current eligible set BEFORE deciding who starts.
        for entry in delivery:
            task_id = entry[2]["task"]["id"]
            snapshot = service.find(task_id)
            if snapshot is None or not snapshot.valid or snapshot.state is None:
                raise IntegrationGateError("gate admission requires a valid durable Issue")
            state = snapshot.state
            self.issue_observations[task_id] = snapshot
            if state.state.value != "agent_ready" or state.phase.value not in DELIVERY_PHASES:
                raise IntegrationGateError("delivery candidate changed before gate queue registration")
            result = self.gate.enqueue(task_id, ready_at=state.updated_at_utc, ready_event=state.last_event_id,
                                       endpoint=self.listener.endpoint)
            if result["status"] == "deferred":
                return tuple(entry for entry in entries if entry[1] not in DELIVERY_PHASES)
        oid, state = self.gate.read()
        self.observation = (oid, state)
        owner = state["owner"]
        queue = ordered_waiters(state)
        next_id = queue[0]["task_id"] if queue and owner is None else None
        self.scheduler.events.emit("integration_gate_observed", gate_ref=self.gate.ref, owner=owner,
                                   queued_task_ids=[w["task_id"] for w in queue], next_task_id=next_id)
        return tuple(entry for entry in entries
                     if entry[1] not in DELIVERY_PHASES or entry[2]["task"]["id"] == next_id)

    def _service(self):
        if self.service is not None:
            return self.service
        from .issue_workflow_store import GhIssueBackend, IssueWorkflowService
        from .committed_tasks import load_committed_task
        self.service = IssueWorkflowService(backend=GhIssueBackend(source_root=self.scheduler.source),
                                            worker_id=self.scheduler.scheduler_id,
                                            task_loader=lambda task_id: load_committed_task(self.scheduler.source, task_id))
        return self.service

    def close(self) -> None:
        if self.listener:
            self.listener.close()
