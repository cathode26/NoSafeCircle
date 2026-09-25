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

import json
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.decomposition_diagnosis import diagnose
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task

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

    receipt_path = manager.records / diagnosis["receipt"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    prior = _prior_inputs(receipt)
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
        old_model = prior["provider_environment"].get(variable)
        if new_model == old_model:
            raise RetryPlanError(f"{variable} is already {old_model!r} in the failed run")
        if code in _CAPACITY_CODES and not new_model.endswith("[1m]"):
            raise RetryPlanError(f"a capacity stop needs a 1M-context model; {new_model!r} is not one")
        proposed["provider_environment"][variable] = new_model
        evidence["route"] = {"variable": variable, "from": old_model, "to": new_model}
    elif change == "contract-revision":
        if not (explanation and explanation.strip()):
            raise RetryPlanError("explain how the contract revision addresses the finding")
        head = git(manager.source, "rev-parse", "HEAD").decode().strip()
        current = load_committed_task(manager.source, task_id, commit=head)["task_contract_sha256"]
        if current == prior["task_contract_sha256"]:
            raise RetryPlanError("the committed parent contract is unchanged since the failed run")
        proposed["task_contract_sha256"] = current
        evidence["contract"] = {"from": prior["task_contract_sha256"], "to": current,
                                "source_commit": head, "explanation": explanation.strip()}

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
