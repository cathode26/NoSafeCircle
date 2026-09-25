"""Prepare a retry proposal for a stopped decomposition run; authorize nothing.

A retry is worth paying for only if something that caused the failure is
different next time. This command reads the run's diagnosis and its
recorded inputs (providers, call budget, author checklist, model
environment, parent contract) and writes a proposal only when the requested
change is one that answers the diagnosed cause and is actually different
from the failed run:

    SETUP    provider-route     a different model for the provider whose round
                                failed (a 1M-context model for a capacity stop)
    BUDGET   budget-3           a two-call run moves to the three-call budget
    AUTHOR   author-checklist   the checklist was not enabled and now is
    CONTRACT contract-revision  the committed parent contract changed since
                                the run, with an explanation of how it helps
    STOP     -                  manual investigation; no proposal

The proposal is a file that must not already exist. It reserves no attempt,
grants no spend and launches nothing: `retry_authorized` is false, and a
retry still needs explicit authorization, a fresh run id and a fresh
checkout root (the old receipt is preserved). Scoped by Astra round 20.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.decomposition_diagnosis import diagnose
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task

from TaskDecomposition.context_builder import ContextPackage  # noqa: E402  (path set by diagnosis)
from TaskDecomposition.live_decomposition import _model_value_problem  # noqa: E402
from TaskDecomposition.policy import semantic_json_sha256  # noqa: E402
from TaskDecomposition.run_diagnosis import (  # noqa: E402
    RUN_RESULT_NAME,
    confined,
    load_run_snapshot,
    parse_json_object,
)

PROPOSAL_SCHEMA_VERSION = "decomposition-retry-proposal/v1"
CHANGE_FOR_ROUTE = {
    "SETUP": "provider-route",
    "BUDGET": "budget-3",
    "AUTHOR": "author-checklist",
    "CONTRACT": "contract-revision",
}
MODEL_VARIABLES = {"claude": "NSC_CLAUDE_MODEL", "codex": "NSC_OPENAI_CODEX_MODEL"}
_CAPACITY_CODES = {"prompt_too_long", "capacity_refused_before_call"}
_MODEL_CODES = {"unrecognized_model", "unsupported_model_version"}


class RetryPlanError(ValueError):
    """The requested change does not answer the diagnosed cause."""


def _prior_inputs(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "providers": list(receipt.get("providers") or []),
        "max_calls": receipt.get("max_calls", 2),
        "author_checklist": receipt.get("author_checklist"),
        "provider_environment": dict(receipt.get("provider_environment") or {}),
        "task_contract_sha256": receipt.get("task_contract_sha256"),
    }


def _failed_provider(diagnosis: Mapping[str, Any]) -> str | None:
    rounds = diagnosis.get("rounds") or []
    return rounds[-1].get("requested_provider") if rounds else None


def plan_retry(
    manager: Checkouts, task_id: str, *, run_id: str, out: Path, change: str,
    models: Mapping[str, str] | None = None, explanation: str | None = None,
) -> dict[str, Any]:
    """Write a retry proposal for one stopped run, or refuse with the reason."""

    out = Path(out)
    if out.exists():
        raise RetryPlanError(f"refusing to overwrite an existing proposal: {out}")
    diagnosis = diagnose(manager, task_id, run_id=run_id)
    route = diagnosis["primary"]["route"]
    code = diagnosis["primary"]["reason_code"]
    wanted = CHANGE_FOR_ROUTE.get(route)
    if wanted is None:
        raise RetryPlanError(f"{route}/{code} needs manual investigation; no retry is proposed")
    if change != wanted:
        raise RetryPlanError(f"{route}/{code} is answered by {wanted!r}, not {change!r}")

    # The prior inputs come from exactly the receipt and run result that were
    # diagnosed, and the two must agree about what the failed run used.
    receipt_bytes = confined(manager.records, diagnosis["receipt"]["path"]).read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != diagnosis["receipt"]["sha256"]:
        raise RetryPlanError("the receipt changed after it was diagnosed")
    receipt = parse_json_object(receipt_bytes, "decomposition receipt")
    run_dir = confined(manager.records, f"decomposition-runs/{run_id}")
    snapshot = load_run_snapshot(run_dir)
    if snapshot.manifest[RUN_RESULT_NAME] != diagnosis["input_manifest"].get(RUN_RESULT_NAME):
        raise RetryPlanError("the run result changed after it was diagnosed")
    run_result = snapshot.result
    prior = _prior_inputs(receipt)
    for label, recorded, observed in (
            ("call budget", prior["max_calls"], run_result.get("max_calls")),
            ("provider order", prior["providers"], run_result.get("provider_order")),
            ("author checklist", prior["author_checklist"], run_result.get("author_checklist"))):
        if recorded != observed:
            raise RetryPlanError(f"the receipt's {label} {recorded!r} disagrees with the run's {observed!r}")
    proposed = json.loads(json.dumps(prior))
    evidence: dict[str, Any] = {}

    if change == "budget-3":
        if prior["max_calls"] != 2:
            raise RetryPlanError("the failed run already had a three-call budget; a larger budget is not available")
        if len(set(prior["providers"])) != 2:
            raise RetryPlanError("a three-call budget requires two distinct providers")
        proposed["max_calls"] = 3
    elif change == "author-checklist":
        if prior["author_checklist"] is not None:
            raise RetryPlanError(
                f"the failed run already used the {prior['author_checklist']!r} checklist; "
                "no further author input is available yet")
        proposed["author_checklist"] = "parent-contract-v1"
    elif change == "provider-route":
        if code not in _CAPACITY_CODES | _MODEL_CODES:
            raise RetryPlanError(f"SETUP/{code} is not repaired by changing the model route; fix it by hand")
        provider = _failed_provider(diagnosis)
        variable = MODEL_VARIABLES.get(provider or "")
        new_model = (models or {}).get(variable or "")
        if variable is None or not new_model:
            raise RetryPlanError(f"name the new model for the failed {provider!r} round as {variable}=...")
        problem = _model_value_problem(new_model)
        if problem:
            raise RetryPlanError(f"model value {new_model!r} {problem}")
        recorded = prior["provider_environment"].get(variable)
        observed = (diagnosis.get("rounds") or [{}])[-1].get("actual_model")
        if recorded is None and observed is None:
            # A pooled pre-call refusal records neither: without the failed
            # route, "different" cannot be shown, so nothing qualifies.
            raise RetryPlanError(
                f"the failed round's {variable} is not recorded; confirm the route by hand before retrying")
        if new_model in {recorded, observed}:
            raise RetryPlanError(f"{new_model!r} is the route the failed round already used")
        if code in _CAPACITY_CODES:
            if any(str(model or "").endswith("[1m]") for model in (recorded, observed)):
                raise RetryPlanError("the failed round already ran a 1M-context route; reduce the context instead")
            if not new_model.endswith("[1m]"):
                raise RetryPlanError(f"a capacity stop needs a 1M-context model; {new_model!r} is not one")
        proposed["provider_environment"][variable] = new_model
        evidence["route"] = {
            "variable": variable, "recorded_model": recorded, "observed_model": observed, "to": new_model,
            "effect": "unverified until the launch preflight and container accept this route",
        }
    elif change == "contract-revision":
        if not (explanation and explanation.strip()):
            raise RetryPlanError("explain how the contract revision addresses the finding")
        head = git(manager.source, "rev-parse", "HEAD").decode().strip()
        current_task = load_committed_task(manager.source, task_id, commit=head)
        current = current_task["task_contract_sha256"]
        if current == prior["task_contract_sha256"]:
            raise RetryPlanError("the committed parent contract is unchanged since the failed run")
        context_bytes = confined(run_dir, "context.json").read_bytes()
        context = ContextPackage.from_payload(parse_json_object(context_bytes, "retained context"))
        if context.semantic_sha256 != run_result.get("context_sha256"):
            raise RetryPlanError("the retained context does not hash to the run's context_sha256")
        before = {k: v for k, v in context.to_dict()["selected_task"]["contract"].items()
                  if k != "task_contract_sha256"}
        after = {k: v for k, v in current_task.items() if k != "task_contract_sha256"}
        if semantic_json_sha256(before) == semantic_json_sha256(after):
            raise RetryPlanError("the parent contract changed only in formatting, not in content")
        proposed["task_contract_sha256"] = current
        evidence["contract"] = {
            "from": prior["task_contract_sha256"], "to": current, "source_commit": head,
            "changed_fields": sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)),
            "operator_explanation": explanation.strip(),
            "explanation_status": "the operator's claimed connection to the finding; not verified",
        }

    if proposed == prior:
        raise RetryPlanError("the proposal does not change any recorded input")
    proposal = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "task_id": task_id,
        "failed_run_id": run_id,
        "diagnosis": {"primary": diagnosis["primary"], "secondary": diagnosis["secondary"],
                      "classifier_version": diagnosis["classifier_version"]},
        "diagnosis_inputs_sha256": diagnosis["input_manifest"],
        "receipt": diagnosis["receipt"],
        "change": change,
        "prior_inputs": prior,
        "proposed_inputs": proposed,
        "evidence": evidence,
        "retry_authorized": False,
        "reserves_attempt": False,
        "note": ("A proposal only. Launching still needs explicit provider-spend authorization, "
                 "a fresh run id and a fresh checkout root; the old receipt is preserved."),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(proposal, indent=2, sort_keys=True) + "\n")
    return {**proposal, "proposal_path": str(out)}
