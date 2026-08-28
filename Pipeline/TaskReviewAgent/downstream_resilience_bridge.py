"""Bridge verified clerical contract migrations into reintegration handling.

The mainline reintegration transition already understands how to preserve an exact
human PASS while advancing an automation-only operational head. This bridge lets
that transition consume the independently verified contract-migration receipt
without pretending that every ancestor PASS is valid.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import semantic_sha256
from .downstream_pipeline import _SHA40, _git, _git_text
from .downstream_resilience import _verified_contract_migration_receipt


_INSTALLED = False
_ORIGINAL: Any = None


def _workflow_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    coordination = observation.get("coordination")
    if not isinstance(coordination, Mapping):
        return {}
    state = coordination.get("workflow_state")
    return dict(state) if isinstance(state, Mapping) else {}


def _integrated_main_parent(
    controller: Any,
    *,
    commit: str,
    contract_path: str,
    contract_sha256: str,
) -> str | None:
    values = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-list",
        "--parents",
        "-n",
        "1",
        commit,
    ).split()
    if not values or values[0] != commit:
        return None
    for parent in values[2:]:
        if not _SHA40.fullmatch(parent):
            continue
        result = _git(
            controller.command_runner,
            controller.checkout,
            "show",
            f"{parent}:{contract_path}",
            check=False,
        )
        if result.returncode != 0:
            continue
        import hashlib

        if hashlib.sha256(result.stdout or b"").hexdigest() == contract_sha256:
            return parent
    return None


def _compatibility_receipt(controller: Any, commit: str) -> dict[str, Any] | None:
    observation = controller.observe()
    state = _workflow_state(observation)
    task = observation.get("task")
    if not isinstance(task, Mapping) or state.get("head_commit") != commit:
        return None
    receipt = _verified_contract_migration_receipt(
        controller,
        state=state,
        task=task,
    )
    if receipt is None or receipt.get("operational_commit") != commit:
        return None
    main_head = _integrated_main_parent(
        controller,
        commit=commit,
        contract_path=receipt["task_contract_path"],
        contract_sha256=receipt["new_task_contract_sha256"],
    )
    if main_head is None:
        return None
    payload = {
        "schema_version": "1.0",
        "task_id": controller.task_id,
        "branch": state.get("branch"),
        "prior_task_head": receipt["human_tested_commit"],
        "human_tested_commit": receipt["human_tested_commit"],
        "main_head": main_head,
        "merge_base": receipt["human_tested_commit"],
        "integrated_commit": commit,
        "classification": "automation_only",
        "human_revalidation_required": False,
        "main_changed_paths": [],
        "task_changed_paths": [],
        "overlap_paths": [],
        "exclusive_overlap_paths": [],
        "non_automation_paths": [],
        "task_blob_changes_after_merge": [],
        "source_carry_forward_receipt_sha256": receipt["receipt_sha256"],
        "authority": "verified_clerical_task_contract_migration_compatibility",
    }
    return {**payload, "receipt_sha256": semantic_sha256(payload)}


def install_downstream_resilience_bridge() -> None:
    """Patch the shared receipt resolver exactly once."""

    global _INSTALLED, _ORIGINAL
    if _INSTALLED:
        return
    from . import mainline_reintegration as mainline

    _ORIGINAL = mainline._automation_receipt_for

    def resolve(controller: Any, commit: str) -> dict[str, Any] | None:
        original = _ORIGINAL(controller, commit)
        if original is not None:
            return original
        return _compatibility_receipt(controller, commit)

    mainline._automation_receipt_for = resolve
    _INSTALLED = True


__all__ = ["install_downstream_resilience_bridge"]
