"""Continue a stopped D1B.2 run from its last revised candidate.

A three-call run can stop only because the call limit ended right after a
revision: the reviewer who revised may not approve its own candidate. That
candidate and its open findings are still the best work so far. A
continuation run reviews them further instead of starting from a new design:

- it re-validates the prior run's latest candidate against the current source
  and requires the exact recorded identity (sha256 and graph plan);
- it keeps the global round numbering (the next round after the prior run's
  last), so finding IDs stay unique and providers keep alternating;
- every round is an ordinary independent review of the current candidate by
  the provider that did not author it;
- it stops at an independent PASS, at its own call budget, or when the open
  blocking findings stop going down for two revisions in a row.

The prior run is read, never changed. A continuation may itself be continued.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

from Pipeline.AgentRuntime.json_values import thaw_json
from Pipeline.TaskExecution.contracts import TaskContractIdentity
from TaskDecomposition.author_checklist import with_author_checklist
from TaskDecomposition.context_builder import (
    DecompositionPreflightError,
    build_context,
    capture_clean_source,
    require_output_disjoint,
    require_physical_read_only,
    source_revalidation_reasons,
)
from TaskDecomposition.contracts import DecompositionContractError, TASK_ID_RE
from TaskDecomposition.live_decomposition import (
    ProgressReporter,
    ProviderFactory,
    _read_only_rejection_reasons,
    _validated_provider_bundle,
    heartbeat_interval,
    publish_json_no_overwrite,
    publish_text_no_overwrite,
)
from TaskDecomposition.policy import DecompositionPolicyError
from TaskDecomposition.review_contracts import DecompositionReviewContractError, ReviewFinding
from TaskDecomposition.review_policy import DecompositionReviewPolicyError, validate_decomposition_review
from TaskDecomposition.review_prompts import build_decomposition_reviewer_prompt
from TaskDecomposition.review_schemas import DECOMPOSITION_REVIEW_SCHEMA
from TaskDecomposition.round_robin_decomposition import (
    ROUND_ROBIN_RUN_RESULT_SCHEMA_VERSION,
    CandidateSnapshot,
    _human_next_step,
    _invoke_round,
    _publish_candidate,
    _round_directory_name,
    _round_invocation_id,
    _round_request,
    _round_summary,
    _validate_candidate,
    _validate_run_id,
    reviewer_budgets,
    validate_provider_order,
)
from graph_delta import GraphDeltaPlanningError

CONTINUATION_MODE = "round_robin_d1b2_continuation"
RUN_RESULT_NAME = "decomposition_run_result.json"
MAX_CONTINUATION_CALLS = 4
# Two revisions in a row that do not reduce the open blocking findings stop
# the run: the reviewers are no longer converging, and a person or GER should
# look at the findings before more calls are spent.
STALL_REVISIONS = 2


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise DecompositionPreflightError(f"{label} is missing: {path}")
    data = path.read_bytes()
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise DecompositionPreflightError(f"{label} is not a JSON object")
    return value, data


def continuable_problem(run_result: dict[str, Any]) -> str | None:
    """Why this run cannot be continued, or None when it can."""

    if run_result.get("run_status") != "needs_human":
        return f"the run ended {run_result.get('run_status')!r}; only a run that stopped after a revision continues"
    rounds = run_result.get("rounds") or []
    last = rounds[-1] if rounds else {}
    if not (isinstance(last, dict) and last.get("status") == "revised_candidate_valid"
            and last.get("candidate_after") == run_result.get("latest_candidate")):
        return "the run did not stop right after a valid revision"
    if not run_result.get("unresolved_findings"):
        return "the run has no open findings to continue from"
    return None


def chain_history(output_root: Path, run_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Every finding-history entry of this run and the runs it continued, oldest first."""

    history: list[dict[str, Any]] = []
    current = run_result
    seen_runs: set[str] = set()
    while True:
        history[0:0] = list(current.get("finding_history") or [])
        prior = (current.get("continued_from") or {}).get("run_id")
        if prior is None:
            return history
        if prior in seen_runs:
            raise DecompositionPreflightError(f"continuation chain loops at {prior}")
        seen_runs.add(prior)
        current, _ = _load_json(output_root / prior / RUN_RESULT_NAME, f"prior run {prior}")


def source_descends(root: Path, ancestor: Any, head: str) -> bool:
    """True when `ancestor` is `head` or one of its ancestors in `root`'s history."""

    if not isinstance(ancestor, str) or not ancestor:
        return False
    completed = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, head],
                               capture_output=True, check=False)
    if completed.returncode not in (0, 1):
        raise DecompositionPreflightError(f"git could not compare {ancestor} with {head}")
    return completed.returncode == 0


def _last_round_number(run_result: dict[str, Any]) -> int:
    return max(int(entry["round_number"]) for entry in run_result["rounds"])


def run_continuation(
    *,
    source: Path,
    output_root: Path,
    task_id: str,
    continue_from: str,
    provider_order: Iterable[str],
    max_calls: int,
    run_id: str,
    provider_factory: ProviderFactory | None = None,
    _require_physical_read_only_source: bool = True,
) -> dict[str, Any]:
    """Review the prior run's latest candidate further; see the module docstring."""

    started = time.monotonic()
    if type(task_id) is not str or TASK_ID_RE.fullmatch(task_id) is None:
        raise DecompositionPreflightError("task ID must match NSC-###")
    order = validate_provider_order(tuple(provider_order))
    if len(set(order)) != 2:
        raise DecompositionPreflightError("a continuation needs two distinct providers")
    if type(max_calls) is not int or not 1 <= max_calls <= MAX_CONTINUATION_CALLS:
        raise DecompositionPreflightError(f"a continuation runs 1..{MAX_CONTINUATION_CALLS} review calls")
    selected_run_id = _validate_run_id(run_id)
    prior_id = _validate_run_id(continue_from)
    source_identity = capture_clean_source(source)
    safe_output_root = require_output_disjoint(source_identity.root, output_root)
    if _require_physical_read_only_source:
        require_physical_read_only(source_identity.root)
    elif provider_factory is None:
        raise DecompositionPreflightError("writable-source test injection requires an injected provider factory")

    prior_dir = safe_output_root / prior_id
    prior, prior_bytes = _load_json(prior_dir / RUN_RESULT_NAME, "prior run result")
    problem = continuable_problem(prior)
    if prior.get("task_id") != task_id:
        problem = f"the prior run is for {prior.get('task_id')!r}, not {task_id}"
    if list(prior.get("provider_order") or []) != list(order):
        problem = problem or f"the prior run used providers {prior.get('provider_order')!r}, not {list(order)}"
    prior_head = (prior.get("source_identity") or {}).get("head_commit")
    if not source_descends(source_identity.root, prior_head, source_identity.head):
        problem = problem or "the prior run's source is not an ancestor of this source; start a fresh run instead"
    elif prior.get("task_execution_contract_identity") is None:
        problem = problem or "the prior run records no parent contract identity"
    if problem:
        raise DecompositionPreflightError(f"cannot continue {prior_id}: {problem}")

    context, graph = build_context(source_identity, task_id)
    if prior.get("author_checklist"):
        context = with_author_checklist(context, prior["author_checklist"])
    context_payload = context.to_dict()
    # The parent contract must be the one the prior run reviewed; the seed's
    # re-validation below then proves the graph plan is unchanged too.
    selected = context_payload["selected_task"]
    if (selected["task_execution_identity"] != prior.get("task_execution_contract_identity")
            or selected["d1a_semantic_parent_identity"] != prior.get("d1a_semantic_parent_identity")):
        raise DecompositionPreflightError("the parent contract changed since the prior run; start a fresh run")

    # The seed is the prior run's latest candidate, re-validated here and
    # required to be exactly what the prior run recorded.
    seed_summary = prior["latest_candidate"]
    seed_round = _last_round_number(prior)
    seed_raw, _ = _load_json(prior_dir / "rounds" / f"{seed_round:02d}" / "candidate.json", "prior latest candidate")
    try:
        seed_validated = _validate_candidate(
            seed_raw, context_payload=context_payload, graph=graph,
            author_provider=seed_summary["author_provider"], version=seed_summary["version"])
    except (DecompositionContractError, DecompositionPolicyError, GraphDeltaPlanningError) as exc:
        raise DecompositionPreflightError(f"the prior latest candidate no longer validates: {exc}") from exc
    candidate: CandidateSnapshot = seed_validated
    if candidate.summary() != seed_summary:
        raise DecompositionPreflightError("the prior latest candidate re-validates to another identity")

    history_before = chain_history(safe_output_root, prior)
    all_finding_ids: set[str] = {
        finding["finding_id"] for entry in history_before for finding in entry.get("findings") or []}
    unresolved: dict[str, ReviewFinding] = {}
    for index, raw in enumerate(prior["unresolved_findings"]):
        finding = ReviewFinding.from_dict(raw, f"prior unresolved_findings[{index}]")
        unresolved[finding.finding_id] = finding

    for provider in order:
        _validated_provider_bundle(provider, source_identity.root, provider_factory, role="decomposition_reviewer")
    run_dir = safe_output_root / selected_run_id
    safe_output_root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise DecompositionPreflightError(f"decomposition run directory already exists: {selected_run_id}") from exc
    reporter = ProgressReporter(run_dir / "progress.jsonl", run_id=selected_run_id, task_id=task_id,
                                provider="round-robin", started=started)
    continued_from = {
        "run_id": prior_id,
        "run_result_sha256": hashlib.sha256(prior_bytes).hexdigest(),
        "seed_round": seed_round,
        "seed_candidate": seed_summary,
    }
    publish_json_no_overwrite(run_dir / "decomposition_request.json", {
        "schema_version": "2.0", "mode": CONTINUATION_MODE, "run_id": selected_run_id,
        "selected_task_id": task_id, "provider_order": list(order), "max_calls": max_calls,
        "source_identity": source_identity.to_context_dict(), "context_sha256": context.semantic_sha256,
        "continued_from": continued_from, "authority": "review_only_not_applied",
    })
    publish_text_no_overwrite(run_dir / "context.json", context.canonical_json() + "\n")
    reporter.emit("run_started", f"D1B.2 continuation of {prior_id} started: {task_id}",
                  provider_order=list(order), max_calls=max_calls)

    identity = context_payload["selected_task"]["task_execution_identity"]
    task_contract_identity = TaskContractIdentity(identity["path"], identity["revision"], identity["sha256"])
    context_paths = tuple(context_payload["context_paths"])
    review_history = list(history_before)
    new_history: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    rejection_reasons: list[str] = []
    run_status = "rejected"
    approver: str | None = None
    calls_used = 0
    open_counts = [len(unresolved)]
    first_round = seed_round + 1

    for round_number in range(first_round, first_round + max_calls):
        calls_used += 1
        provider = order[(round_number - 1) % 2]
        if provider == candidate.author_provider:
            rejection_reasons.append("provider rotation would let the latest author review its own candidate")
            break
        role = "decomposition_reviewer"
        prompt = build_decomposition_reviewer_prompt(
            context=context, candidate=candidate.result, candidate_sha256=candidate.sha256,
            candidate_author_provider=candidate.author_provider, reviewer_provider=provider,
            round_number=round_number, graph_delta=candidate.graph_delta, review_history=review_history,
            unresolved_findings=(unresolved[key] for key in sorted(unresolved)))
        invocation_id = _round_invocation_id(task_id, selected_run_id, round_number, role)
        round_dir = run_dir / "rounds" / _round_directory_name(round_number)
        publish_json_no_overwrite(run_dir / "rounds" / f"{round_number:02d}-request.json", {
            **_round_request(round_number=round_number, role=role, provider=provider, invocation_id=invocation_id,
                             candidate=candidate, unresolved_findings=unresolved),
            "pooled_session_key": None, "session_mode": None, "requested_session_id": None,
        })
        agent_result, exception, duration, actual_id = _invoke_round(
            run_dir=run_dir, round_number=round_number, task_id=task_id, run_id=selected_run_id, role=role,
            provider=provider,
            provider_bundle=_validated_provider_bundle(
                provider, source_identity.root, provider_factory, role=role),
            prompt=prompt, output_schema=DECOMPOSITION_REVIEW_SCHEMA, context_paths=context_paths,
            task_contract_identity=task_contract_identity, budgets=reviewer_budgets(),
            heartbeat_seconds=heartbeat_interval(), reporter=reporter)
        summary = _round_summary(
            run_dir=run_dir, round_directory=_round_directory_name(round_number), round_number=round_number,
            role=role, provider=provider, invocation_id=invocation_id, agent_result=agent_result,
            duration_seconds=duration, candidate_before=candidate, unresolved_findings=unresolved)
        failures: list[str] = []
        if actual_id != invocation_id:
            failures.append("internal invocation identity mismatch")
        elif exception is not None:
            failures.append(f"task-associated invocation failed: {type(exception).__name__}: {exception}")
            run_status = "agent_failed"
        elif agent_result is None:
            failures.append("task-associated invocation returned no AgentResult")
            run_status = "agent_failed"
        elif agent_result.status != "succeeded":
            failures.append(f"AgentResult failed ({agent_result.failure_classification}): {agent_result.failure_message}")
            run_status = "agent_failed"
        else:
            failures.extend(_read_only_rejection_reasons(agent_result))
        failures.extend(source_revalidation_reasons(source_identity))
        if not failures and agent_result is not None:
            try:
                review, next_unresolved = validate_decomposition_review(
                    thaw_json(agent_result.structured_output), expected_candidate_sha256=candidate.sha256,
                    round_number=round_number, prior_unresolved_findings=unresolved,
                    all_prior_finding_ids=frozenset(all_finding_ids))
                publish_json_no_overwrite(round_dir / "review.json", review.to_dict())
                summary["verdict"] = review.verdict
                summary["new_finding_ids"] = [finding.finding_id for finding in review.findings]
                all_finding_ids.update(summary["new_finding_ids"])
                entry = {
                    "round_number": round_number, "reviewer_provider": provider,
                    "reviewed_candidate_sha256": candidate.sha256, "verdict": review.verdict,
                    "summary": review.summary, "findings": [finding.to_dict() for finding in review.findings],
                    "prior_finding_resolutions": [r.to_dict() for r in review.prior_finding_resolutions],
                }
                review_history.append(entry)
                new_history.append(entry)
                publish_json_no_overwrite(round_dir / "review_history_entry.json", entry)
                unresolved = next_unresolved
                if review.verdict == "pass":
                    approver = provider
                    summary["status"] = "independent_pass"
                    run_status = "review_ready"
                elif review.verdict == "needs_human":
                    summary["status"] = "needs_human"
                    run_status = "needs_human"
                else:
                    assert review.revised_decomposition is not None
                    revised = _validate_candidate(
                        review.revised_decomposition, context_payload=context_payload, graph=graph,
                        author_provider=provider, version=candidate.version + 1)
                    if revised.sha256 == candidate.sha256:
                        raise DecompositionReviewPolicyError(
                            "revise emitted a candidate identical to the reviewed candidate")
                    candidate = revised
                    _publish_candidate(round_dir, candidate)
                    summary["candidate_after"] = candidate.summary()
                    summary["status"] = "revised_candidate_valid"
                    run_status = "needs_human"
                    open_counts.append(len(unresolved))
                    recent = open_counts[-(STALL_REVISIONS + 1):]
                    if len(recent) == STALL_REVISIONS + 1 and all(b >= a for a, b in zip(recent, recent[1:])):
                        rejection_reasons.append(
                            f"not converging: open blocking findings went {recent} over the last "
                            f"{STALL_REVISIONS} revisions")
                        summary["rejection_reasons"] = []
                        summary["unresolved_finding_ids"] = sorted(unresolved)
                        publish_json_no_overwrite(round_dir / "round_result.json", summary)
                        rounds.append(summary)
                        break
            except (DecompositionReviewContractError, DecompositionReviewPolicyError, DecompositionContractError,
                    DecompositionPolicyError, GraphDeltaPlanningError) as exc:
                failures.append(f"review/revision deterministic validation failed: {exc}")
                run_status = "rejected"
        summary["rejection_reasons"] = failures
        summary["unresolved_finding_ids"] = sorted(unresolved)
        publish_json_no_overwrite(round_dir / "round_result.json", summary)
        rounds.append(summary)
        if failures:
            rejection_reasons.extend(f"round {round_number}: {reason}" for reason in failures)
            if run_status not in {"agent_failed"}:
                run_status = "rejected"
            break
        if run_status in {"review_ready"} or summary["status"] == "needs_human":
            break
    else:
        if run_status == "needs_human" and not rejection_reasons:
            rejection_reasons.append(
                "call limit ended immediately after a revision; the latest author may not approve its own candidate")

    if source_revalidation_reasons(source_identity) and run_status == "review_ready":
        run_status = "rejected"
        approver = None
        rejection_reasons.append("source changed during the continuation")
    result_path = graph_path = None
    if run_status == "review_ready":
        if unresolved or approver is None or approver == candidate.author_provider:
            run_status = "rejected"
            rejection_reasons.append("internal error: review_ready without a clean independent pass")
        else:
            publish_json_no_overwrite(run_dir / "decomposition_result.json", candidate.result.to_dict())
            result_path = "decomposition_result.json"
            if candidate.graph_delta is not None:
                publish_text_no_overwrite(run_dir / "graph_delta.json", candidate.graph_delta.canonical_json() + "\n")
                graph_path = "graph_delta.json"
    final = {
        "schema_version": ROUND_ROBIN_RUN_RESULT_SCHEMA_VERSION,
        "mode": CONTINUATION_MODE,
        "run_id": selected_run_id,
        "task_id": task_id,
        "provider_order": list(order),
        "max_calls": max_calls,
        "calls_used": calls_used,
        "author_corrections_used": 0,
        "continued_from": continued_from,
        "source_identity": source_identity.to_context_dict(),
        "task_execution_contract_identity": task_contract_identity.to_dict(),
        "d1a_semantic_parent_identity": context_payload["selected_task"]["d1a_semantic_parent_identity"],
        "context_sha256": context.semantic_sha256,
        **({"author_checklist": prior["author_checklist"]} if prior.get("author_checklist") else {}),
        "run_status": run_status,
        "decision": candidate.result.decision,
        "latest_candidate": candidate.summary(),
        "independent_approver_provider": approver if run_status == "review_ready" else None,
        "review_independence": "cross_provider",
        "decomposition_result_path": result_path,
        "graph_delta_path": graph_path,
        "rounds": rounds,
        "finding_history": new_history,
        "unresolved_findings": [unresolved[key].to_dict() for key in sorted(unresolved)],
        "open_blocking_counts": open_counts,
        "rejection_reasons": [] if run_status == "review_ready" else rejection_reasons,
        "human_next_step": _human_next_step(run_status),
        "duration_seconds": time.monotonic() - started,
        "authority": "review_only_not_applied",
        "pooled_sessions": None,
    }
    reporter.emit("run_completed", f"D1B.2 continuation completed: {run_status}", status=run_status,
                  calls_used=calls_used, duration_seconds=round(final["duration_seconds"], 3))
    publish_json_no_overwrite(run_dir / RUN_RESULT_NAME, final)
    return final
