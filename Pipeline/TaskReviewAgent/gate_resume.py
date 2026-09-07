"""Conservative, observation-only admission of an already routed gate waiter.

The route receipt is host-owned history, never task or gate authority. Missing
history (including pre-upgrade workers) keeps the ordinary architect path.

Two failure classes are deliberately distinct:

``GateResumeUnavailable``
    This optimization does not apply -- a missing, corrupt or changed route
    receipt, a drifted observation, an occupied gate, a candidate outside the
    allowlist. The saved route is host-owned history and never authority, so
    every doubt about it keeps the ordinary architect path.

``GateResumeAuthorityError``
    The durable GATE record itself is not trustworthy -- a legacy owner that
    carries no source/base identity, an unreadable or malformed journal, or an
    unreconciled publication operation whose remote outcome is unknown. An
    architect cannot repair any of these, so paying for one would hide the
    incident: it becomes an observable blocked/reconciliation state instead.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any
import uuid

from .architect_preflight import PredictedChangeSurface, assess_unknown_surface_reservations, detect_deterministic_conflict
from .contracts import TaskReviewContractError, semantic_sha256
from .execution_routing import ExecutionRecommendation, ResolvedExecutionRoute, restrict_execution_routing_policy, resolve_execution_route, resolve_task_rigor
from .integration_gate import (
    LEGACY_OWNER_KEYS, IntegrationGateError, ordered_waiters, repository_identity)
from .issue_workflow import EVENT_RE
from .publication_fence import REQUIRES_RECONCILIATION, PublicationStatus


class GateResumeUnavailable(ValueError):
    """This deterministic optimization does not apply; use the architect path."""


class GateResumeAuthorityError(TaskReviewContractError):
    """Durable authority is not trustworthy; block and reconcile, never re-route."""


@dataclass(frozen=True)
class GateResumeDecision:
    entry: tuple
    surface: PredictedChangeSurface
    route: ResolvedExecutionRoute
    evidence: dict


def route_path(scheduler: Any, task_id: str) -> Path:
    return scheduler.checkout_root / ".task-review-agent" / "admission-routes" / (task_id + ".json")


def remember_route(scheduler: Any, *, task: dict, source_head: str, candidate: dict,
                   advisory: Any, route: ResolvedExecutionRoute, worker_id: str, run_id: str) -> None:
    """Persist the actual architect-backed route before attempting this launch.

    Replacing an earlier record also invalidates it on a failed/repaired launch.
    A receipt is usable only after this worker appears in the verified Issue
    event chain. No advisory is manufactured, copied, or treated as authority.
    """
    admission = scheduler.integration_gate_admission
    snapshot = admission._service().find(task["id"])
    payload = dict(schema_version="1.0", task_id=task["id"],
        task_contract_sha256=task["task_contract_sha256"], source_head=source_head,
        repository=admission.gate.repository_id,
        checkout_path=str((scheduler.checkout_root / task["id"]).resolve()),
        issue_number=snapshot.issue_number if snapshot else None,
        issue_event_id=snapshot.state.last_event_id if snapshot and snapshot.valid and snapshot.state else None,
        worker_id=worker_id, run_id=run_id,
        recommendation=advisory.execution_recommendation.to_dict(),
        surface=advisory.predicted_change_surface.to_dict(), route=asdict(route),
        supervisor_provider=scheduler.supervisor_provider,
        provider_allowlist=list(scheduler.provider_allowlist) if scheduler.provider_allowlist else None)
    payload["receipt_sha256"] = semantic_sha256(payload)
    path = route_path(scheduler, task["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise GateResumeUnavailable(reason)


def _require_authority(condition: bool, reason: str) -> None:
    """An integrity assertion whose failure is an incident, not a fallback."""

    if not condition:
        raise GateResumeAuthorityError(reason)


def _require_trustworthy_gate(admission: Any) -> tuple[str, dict]:
    """Read the gate, refusing any record that cannot carry publication authority."""

    try:
        oid, gate_state = admission.gate.read()
    except IntegrationGateError as exc:
        raise GateResumeAuthorityError(f"integration gate record is unusable: {exc}") from exc
    owner = gate_state["owner"]
    if owner is not None:
        _require_authority(
            set(owner) != set(LEGACY_OWNER_KEYS),
            "integration gate owner predates the versioned publication protocol; "
            "reconcile it explicitly instead of routing new work")
        record = owner.get("publication")
        if record is not None:
            _require_authority(
                PublicationStatus(record["status"]) not in REQUIRES_RECONCILIATION,
                f"publication operation {record['operation_id']} is {record['status']}; "
                "reconcile the authoritative branch outcome before admitting work")
    return oid, gate_state


def _issue_proof(admission: Any, entry: tuple, receipt: dict, checkout: Path) -> tuple[Any, dict]:
    """Use the existing hashed workflow and exact validation authority readers."""
    from .downstream_determinism import _authoritative_validation
    from .downstream_pipeline import _default_runner

    candidate, phase, portfolio = entry
    task = portfolio["task"]
    service = admission._service()
    snapshot = service.find(task["id"])
    _require(snapshot is not None and snapshot.managed and snapshot.valid
             and snapshot.pending_transition is None and snapshot.state is not None,
             "managed Issue is not coherent")
    state = snapshot.state
    _require(state.state.value == "agent_ready" and state.phase.value == phase
             and state.worker_id is None and state.lease_id is None,
             "Issue is not an unleased downstream continuation")
    _require(state.task_contract_sha256 == task["task_contract_sha256"]
             and candidate.get("issue_number") == snapshot.issue_number
             and candidate.get("issue_url") == snapshot.issue_url
             and candidate.get("branch") == state.branch
             and candidate.get("commit") == state.head_commit
             and Path(state.checkout_path or "").resolve() == checkout,
             "Issue/contract/branch/checkout identity changed")
    if admission.gate.repository_id.startswith("github.com/"):
        _require(snapshot.issue_url.casefold() ==
                 f"https://{admission.gate.repository_id}/issues/{snapshot.issue_number}".casefold(),
                 "Issue URL targets a different repository")
    observed = admission.issue_observations.get(task["id"])
    _require(observed is not None and observed.to_dict() == snapshot.to_dict(),
             "Issue changed since gate admission")
    events = snapshot.events
    if receipt["issue_number"] is not None:
        _require(receipt["issue_number"] == snapshot.issue_number,
                 "prior route belongs to a different Issue history")
    if receipt["issue_event_id"] is not None:
        _require(any(e.event_id == receipt["issue_event_id"] for e in events),
                 "prior route event is not in this Issue history")
    else:
        _require(bool(events) and events[0].actor_id == receipt["worker_id"],
                 "initial worker did not initialize this Issue")
    worker_events = [e for e in events if e.actor_id == receipt["worker_id"]
                     and e.event_type.value == "agent_lease_acquired"]
    _require(bool(worker_events), "recorded worker never acquired this Issue")
    anchor = (next(e.sequence for e in events if e.event_id == receipt["issue_event_id"])
              if receipt["issue_event_id"] is not None else worker_events[0].sequence)
    # A repair/failure/migration after this route needs a new architect decision.
    allowed = {"agent_lease_acquired", "human_handoff_created", "human_validation_passed",
               "automated_validation_passed", "agent_lease_released"}
    for event in events:
        if event.sequence < anchor:
            continue
        _require(event.event_type.value in allowed, "failure, repair, or identity migration after routing")
        if event.event_type.value == "agent_lease_released":
            _require(event.details.get("reason") in {None, "integration_gate_waiting"}
                     and not event.details.get("error"), "non-gate release requires judgment")
    downstream_path = checkout.parent / ".task-review-agent" / (task["id"] + ".downstream.json")
    downstream = json.loads(downstream_path.read_text(encoding="utf-8")) if downstream_path.exists() else {}
    if downstream_path.exists():
        identity = dict(downstream)
        downstream_digest = identity.pop("receipt_sha256", None)
        _require(downstream.get("schema_version") == "1.0" and downstream.get("task_id") == task["id"]
                 and downstream_digest == semantic_sha256(identity), "downstream receipt is corrupt")
    context = SimpleNamespace(task_id=task["id"], checkout=checkout, state=downstream,
                              workflow=SimpleNamespace(issue_workflow=service), command_runner=_default_runner)
    authority = _authoritative_validation(context)
    _require(authority is not None and authority.get("result") == "pass"
             and authority.get("tested_commit") == state.head_commit,
             "exact current validation authority is unavailable")
    validation_event = next(e for e in events if e.event_id == authority["event_id"])
    # Once validation passed, any unrecognized comment (including human feedback)
    # returns to judgment. Labels and the wake packet are never consulted here.
    comments = service.backend.get_comments(snapshot.issue_number)
    seen_validation = False
    for comment in comments:
        body = comment.get("body", "")
        raw_events = EVENT_RE.findall(body)
        parsed = [json.loads(value) for value in raw_events]
        if any(e.get("event_id") == validation_event.event_id for e in parsed):
            seen_validation = True
        elif seen_validation:
            _require(bool(parsed) and all(any(e.event_id == value.get("event_id") for e in events)
                                         for value in parsed), "new feedback after validation")
    _require(seen_validation, "validation event comment is missing")
    _require(service.find(task["id"]).to_dict() == snapshot.to_dict(), "Issue changed during proof")
    return snapshot, authority


def _prove(admission: Any, entry: tuple, *, source_head: str, refresh: dict, reservations: tuple) -> GateResumeDecision:
    from .polling_orchestrator import _git_text, _run_git
    from .dispatch_plan import _LazyTaskcontrolStateProvider, load_dispatch_policy

    scheduler = admission.scheduler
    candidate, phase, portfolio = entry
    task = portfolio["task"]
    task_id = task["id"]
    _require(phase in {"delivery_evidence", "merge_closeout"}
             and portfolio["eligible_work_types"] == ["implementation"]
             and task.get("execution_scope") == "single_agent", "not an implementation continuation")
    _require(task.get("provenance", {}).get("profile") != "thousand",
             "this profile requires an explicit architect capacity decision")
    _require(not any(0 <= scheduler.monotonic_clock() - observed <= 300
                     for observed, _ in scheduler.capacity_health_failures),
             "recent scheduler health failure requires capacity judgment")
    _require(scheduler.admission_allowlist is None or task_id in scheduler.admission_allowlist,
             "outside admission allowlist")
    oid, gate_state = _require_trustworthy_gate(admission)
    queue = ordered_waiters(gate_state)
    _require(admission.observation is not None and oid == admission.observation[0]
             and gate_state["owner"] is None and bool(queue) and queue[0]["task_id"] == task_id,
             "durable gate head/owner changed")
    _require(refresh.get("after") == source_head
             and not refresh.get("local_ahead")
             and refresh.get("remote_head", source_head) == source_head
             and _git_text(scheduler.source, "rev-parse", "refs/remotes/origin/main") == source_head
             and _git_text(scheduler.source, "rev-parse", "HEAD") == source_head
             and _git_text(scheduler.source, "branch", "--show-current") == "main"
             and not _git_text(scheduler.source, "status", "--porcelain"),
             "source main observation is not current and clean")
    path = route_path(scheduler, task_id)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    digest = receipt.pop("receipt_sha256")
    _require(digest == semantic_sha256(receipt) and receipt["schema_version"] == "1.0",
             "route receipt is corrupt")
    _require(set(receipt) == {"schema_version", "task_id", "task_contract_sha256", "source_head",
        "repository", "checkout_path", "issue_number", "issue_event_id", "worker_id", "run_id",
        "recommendation", "surface", "route", "supervisor_provider", "provider_allowlist"}
        and re.fullmatch(r"[0-9a-f]{40}", receipt["source_head"]) is not None
        and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", receipt["run_id"]) is not None,
        "route receipt schema or exact source/run identity is invalid")
    checkout = (scheduler.checkout_root / task_id).resolve()
    _require(checkout.parent == scheduler.checkout_root.resolve() and checkout.name == task_id,
             "checkout is outside its canonical task directory")
    _require(receipt["task_id"] == task_id and receipt["task_contract_sha256"] == task["task_contract_sha256"]
             and receipt["repository"] == admission.gate.repository_id
             and receipt["checkout_path"] == str(checkout)
             and receipt["supervisor_provider"] == scheduler.supervisor_provider
             and receipt["provider_allowlist"] == (list(scheduler.provider_allowlist) if scheduler.provider_allowlist else None),
             "prior route identity or provider restriction changed")
    snapshot, authority = _issue_proof(admission, entry, receipt, checkout)
    state = snapshot.state
    for root in (scheduler.source, checkout):
        _require(repository_identity(_git_text(root, "remote", "get-url", "origin")) == receipt["repository"],
                 "repository changed")
    _require(_git_text(checkout, "rev-parse", "--show-toplevel") == str(checkout).replace("\\", "/")
             and _git_text(checkout, "rev-parse", "HEAD") == state.head_commit
             and _git_text(checkout, "branch", "--show-current") == state.branch
             and not _git_text(checkout, "status", "--porcelain"), "checkout identity or contents changed")
    remote_branch = _git_text(checkout, "ls-remote", "--refs", "origin", "refs/heads/" + state.branch)
    _require(remote_branch.split() == [state.head_commit, "refs/heads/" + state.branch], "remote task branch changed")
    base = receipt["source_head"]
    for root, target in ((scheduler.source, source_head), (checkout, state.head_commit)):
        _require(_run_git(root, "merge-base", "--is-ancestor", base, target).returncode == 0,
                 "route source is not an ancestor of current main/task")
    surface = PredictedChangeSurface.from_dict(receipt["surface"])
    actual = set(_git_text(checkout, "diff", "--name-only", base, state.head_commit, "--").splitlines())
    _require(bool(actual) and actual.issubset(surface.exact_paths), "resource surface changed since routing")
    main_paths = _git_text(scheduler.source, "diff", "--name-only", base, source_head, "--").splitlines()
    _require(not any(path.startswith(("Pipeline/TaskReviewAgent/", "Pipeline/Testing/", "Pipeline/ExecutionCrew/"))
                     for path in main_paths), "validation or execution implementation changed on main")
    # A disjoint path proof is intentionally stricter than Git's merge heuristic.
    _require(not any(a == b or a.startswith(b + "/") or b.startswith(a + "/")
                     for a in (p.casefold() for p in actual) for b in (p.casefold() for p in main_paths)),
             "main changed the task surface; merge judgment required")
    unknown = assess_unknown_surface_reservations(candidate_task_id=task_id,
        candidate_exclusive_resources=task.get("exclusive_resources") or (), reservations=reservations)
    _require(not unknown.blocking_task_ids and not unknown.architect_confirmable_task_ids,
             "unobservable reservation requires judgment")
    _require(detect_deterministic_conflict(candidate_task_id=task_id,
        candidate_exclusive_resources=task.get("exclusive_resources") or (),
        candidate_surface=surface, reservations=reservations) is None, "reservation conflict")
    commit_snapshot = scheduler._admission_snapshot(source_head)
    dependencies = task.get("depends_on")
    _require(isinstance(dependencies, list), "dependencies are not observable")
    dependency_states = {}
    if dependencies:
        states = _LazyTaskcontrolStateProvider(root=scheduler.source, expected_task_ids=commit_snapshot.task_ids,
            source_commit=source_head, recognized_states=load_dispatch_policy().known_dependency_states,
            commit_snapshot=commit_snapshot)
        dependency_states = {dependency: states(dependency).get("state") for dependency in dependencies}
        _require(all(value == "conformant" for value in dependency_states.values()), "dependencies not conformant")
    recommendation = ExecutionRecommendation.from_dict(receipt["recommendation"])
    rigor = resolve_task_rigor(recommendation, task=task, predicted_change_surface=surface,
                              committed_path_probe=commit_snapshot.committed_path_probe())
    route = resolve_execution_route(recommendation,
        restrict_execution_routing_policy(scheduler.routing_policy_loader(), scheduler.provider_allowlist), rigor=rigor)
    # JSON normalization compares tuple/list representations without relaxing fields.
    _require(json.loads(json.dumps(asdict(route))) == receipt["route"], "routing or rigor policy changed")
    _require(admission.gate.read()[0] == oid, "gate moved during proof")
    evidence = dict(gate_ref=admission.gate.ref, gate_oid=oid, next_task_id=task_id,
        issue_number=snapshot.issue_number, issue_url=snapshot.issue_url, issue_event_id=state.last_event_id,
        task_contract_sha256=state.task_contract_sha256, branch=state.branch, task_head=state.head_commit,
        checkout_path=str(checkout), repository=receipt["repository"], source_head=source_head,
        validation_event_id=authority["event_id"], dependency_states=dependency_states,
        route_receipt_path=str(path), route_receipt_sha256=digest, prior_run_id=receipt["run_id"])
    return GateResumeDecision(entry, surface, route, evidence)


def prove_resume(admission: Any, entries: tuple, *, source_head: str, refresh: dict,
                 reservations: tuple) -> GateResumeDecision | None:
    for entry in entries:
        if entry[1] not in {"delivery_evidence", "merge_closeout"}:
            continue
        try:
            return _prove(admission, entry, source_head=source_head, refresh=refresh, reservations=reservations)
        except GateResumeAuthorityError as exc:
            # Authority integrity, not routing preference. Record it and stop;
            # an architect cannot repair a legacy owner, a corrupt durable
            # record, a mismatched identity or an unreconciled publication, and
            # paying one here would hide the incident.
            admission.scheduler.events.emit("integration_gate_resume_blocked",
                task_id=entry[2]["task"]["id"], gate_ref=admission.gate.ref,
                reason=str(exc)[:700])
            raise
        except Exception as exc:
            # This optional optimization cannot convert missing evidence into
            # authority, nor make previously eligible work fatal.
            admission.scheduler.events.emit("integration_gate_resume_requires_architect",
                task_id=entry[2]["task"]["id"], reason=str(exc)[:700])
    return None
