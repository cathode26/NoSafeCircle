"""Verified PASS carry-forward, explicit validation plans, and loop recovery.

This module is installed after mainline_reintegration.  It deliberately extends
existing downstream authority instead of weakening exact-commit validation:

* a human PASS may cross a clerical task-contract migration only after a
  hash-bound migration ledger, unchanged behavioral contract, unchanged
  task-owned blobs, and safe mainline drift are all proven;
* task-specific authoritative Unity platforms and filters come from a committed
  contract-hash-bound policy;
* repeated deterministic action rejection, turn exhaustion, and operator
  interruption release the active durable Issue lease instead of leaving an
  indefinitely owned task.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .contracts import TaskReviewContractError, semantic_sha256
from .downstream_pipeline import (
    _SHA40,
    _VALID_PLATFORMS,
    DownstreamPipelineError,
    _copy,
    _decode,
    _file_fact,
    _git,
    _git_text,
)
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
)


CARRY_FORWARD_SCHEMA_VERSION = "1.0"
VALIDATION_POLICY_SCHEMA_VERSION = "1.0"
_VALIDATION_POLICY_RELATIVE = Path(
    "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
)
_CLERICAL_MAINLINE_PREFIXES = (
    ".github/workflows/",
    "Docs/AI-Pipeline/",
    "Pipeline/Reconciliation/",
    "Pipeline/TaskGraph/",
    "Pipeline/TaskReviewAgent/",
    "Tasks/",
)
_CLERICAL_MAINLINE_FILES = frozenset({"AGENTS.md", "compose.override.yaml"})
_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


def _normalized_text(value: Any, *, limit: int = 1200) -> str:
    return " ".join(str(value).split())[:limit]


def _workflow_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    coordination = observation.get("coordination")
    if not isinstance(coordination, Mapping):
        return {}
    state = coordination.get("workflow_state")
    return dict(state) if isinstance(state, Mapping) else {}


def _safe_repository_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip().replace("\\", "/"))
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path.as_posix()


def _resource_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    for prefix in ("repo-file:", "unity-scene:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return _safe_repository_path(text)


def _paths_from_nul(data: bytes, *, label: str) -> list[str]:
    result: set[str] = set()
    for raw in data.split(b"\0"):
        if not raw:
            continue
        path = _safe_repository_path(_decode(raw, label))
        if path is None:
            raise DownstreamPipelineError(f"{label} returned an unsafe repository path")
        result.add(path)
    return sorted(result, key=str.casefold)


def _object_id_at(controller: Any, commit: str, path: str) -> str | None:
    result = _git(
        controller.command_runner,
        controller.checkout,
        "rev-parse",
        "--verify",
        f"{commit}:{path}",
        check=False,
    )
    if result.returncode != 0:
        return None
    value = _decode(result.stdout or b"", "git object identity").strip()
    return value if _SHA40.fullmatch(value) else None


def _is_clerical_mainline_path(path: str) -> bool:
    folded = path.casefold()
    if folded in {item.casefold() for item in _CLERICAL_MAINLINE_FILES}:
        return True
    return any(
        folded.startswith(prefix.casefold())
        for prefix in _CLERICAL_MAINLINE_PREFIXES
    )


def _replace_contract_paths(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        updated = value
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        return updated
    if isinstance(value, list):
        return [_replace_contract_paths(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_contract_paths(item, replacements)
            for key, item in value.items()
        }
    return value


def _json_at(controller: Any, commit: str, path: str, *, label: str) -> tuple[dict[str, Any], bytes]:
    result = _git(
        controller.command_runner,
        controller.checkout,
        "show",
        f"{commit}:{path}",
        check=False,
    )
    if result.returncode != 0:
        raise DownstreamPipelineError(f"{label} is missing at {commit}:{path}")
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownstreamPipelineError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DownstreamPipelineError(f"{label} must be a JSON object")
    return value, result.stdout


def validation_plan_for(
    root: Path | str,
    task: Mapping[str, Any],
) -> dict[str, Any] | None:
    repository = Path(root).resolve()
    path = repository / _VALIDATION_POLICY_RELATIVE
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DownstreamPipelineError(
            "authoritative validation policy is unreadable"
        ) from exc
    if document.get("schema_version") != VALIDATION_POLICY_SCHEMA_VERSION:
        raise DownstreamPipelineError(
            "authoritative validation policy schema is unsupported"
        )
    tasks = document.get("tasks")
    if not isinstance(tasks, Mapping):
        raise DownstreamPipelineError(
            "authoritative validation policy omitted tasks"
        )
    task_id = task.get("task_id") or task.get("id")
    if not isinstance(task_id, str):
        return None
    raw = tasks.get(task_id)
    inherited_from: dict[str, str] | None = None
    if raw is None:
        provenance = task.get("provenance")
        if (
            not isinstance(provenance, Mapping)
            or provenance.get("origin") != "progressive_decomposition"
        ):
            return None
        parent_id = provenance.get("parent_task_id")
        parent_hash = provenance.get("parent_contract_sha256")
        templates = document.get("decomposition_child_templates")
        if templates is None:
            return None
        if not isinstance(templates, Mapping):
            raise DownstreamPipelineError(
                "authoritative validation policy decomposition templates are invalid"
            )
        raw = templates.get(parent_id) if isinstance(parent_id, str) else None
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise DownstreamPipelineError(
                f"authoritative validation template for {parent_id} is invalid"
            )
        if raw.get("parent_task_contract_sha256") != parent_hash:
            raise DownstreamPipelineError(
                f"authoritative validation template for {task_id} is stale"
            )
        inherited_from = {
            "parent_task_id": parent_id,
            "parent_task_contract_sha256": parent_hash,
        }
    if not isinstance(raw, Mapping):
        raise DownstreamPipelineError(
            f"authoritative validation policy for {task_id} is invalid"
        )
    if inherited_from is not None and raw.get("validation_variants") is not None:
        variants = raw.get("validation_variants")
        resources = task.get("exclusive_resources")
        if (
            not isinstance(variants, list)
            or not variants
            or not isinstance(resources, list)
            or any(type(item) is not str for item in resources)
        ):
            raise DownstreamPipelineError(
                f"authoritative validation variants for {task_id} are invalid"
            )
        resource_set = set(resources)
        matches: list[Mapping[str, Any]] = []
        for variant in variants:
            if not isinstance(variant, Mapping):
                raise DownstreamPipelineError(
                    f"authoritative validation variants for {task_id} are invalid"
                )
            required = variant.get("required_exclusive_resources")
            if (
                not isinstance(required, list)
                or not required
                or any(type(item) is not str for item in required)
            ):
                raise DownstreamPipelineError(
                    f"authoritative validation variants for {task_id} are invalid"
                )
            if set(required) == resource_set:
                matches.append(variant)
        if len(matches) != 1:
            raise DownstreamPipelineError(
                f"authoritative validation variants for {task_id} did not match exactly once"
            )
        raw = {**raw, **matches[0]}
    contract_hash = task.get("task_contract_sha256")
    if (
        not isinstance(contract_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", contract_hash) is None
    ):
        raise DownstreamPipelineError(
            f"authoritative validation policy for {task_id} has no exact contract hash"
        )
    if inherited_from is None and raw.get("task_contract_sha256") != contract_hash:
        raise DownstreamPipelineError(
            f"authoritative validation policy for {task_id} is stale"
        )
    platforms = raw.get("required_test_platforms")
    filters = raw.get("test_filters")
    if (
        not isinstance(platforms, list)
        or not platforms
        or any(item not in _VALID_PLATFORMS for item in platforms)
        or len(set(platforms)) != len(platforms)
        or not isinstance(filters, Mapping)
    ):
        raise DownstreamPipelineError(
            f"authoritative validation policy for {task_id} has invalid platforms"
        )
    normalized_filters: dict[str, str] = {}
    for platform in platforms:
        value = filters.get(platform)
        if not isinstance(value, str) or not value.strip():
            raise DownstreamPipelineError(
                f"authoritative validation policy for {task_id} omitted {platform} filter"
            )
        normalized_filters[platform] = value.strip()
    payload = {
        "task_id": task_id,
        "task_contract_sha256": contract_hash,
        "required_test_platforms": list(platforms),
        "test_filters": normalized_filters,
        "authority": raw.get("authority")
        or "committed_task_authoritative_validation_policy",
        "policy_path": _VALIDATION_POLICY_RELATIVE.as_posix(),
    }
    if inherited_from is not None:
        payload["inherited_from_decomposition"] = inherited_from
    return {**payload, "policy_sha256": semantic_sha256(payload)}


def _migration_ledger_entry(
    controller: Any,
    event: Any,
    contract_path: str,
) -> tuple[str, dict[str, Any]]:
    migration_id = event.details.get("migration_id")
    if not isinstance(migration_id, str) or not migration_id.strip():
        raise DownstreamPipelineError(
            "task-contract migration event omitted migration_id"
        )
    ledger_path = (
        Path("Pipeline/TaskGraph/migrations") / f"{migration_id.strip()}.json"
    ).as_posix()
    ledger, _ = _json_at(
        controller,
        event.details["head_commit"],
        ledger_path,
        label="task-contract migration ledger",
    )
    if ledger.get("migration_id") != migration_id:
        raise DownstreamPipelineError(
            "task-contract migration ledger identity does not match the Issue event"
        )
    entries = ledger.get("task_contracts")
    if not isinstance(entries, list):
        raise DownstreamPipelineError(
            "task-contract migration ledger omitted task_contracts"
        )
    matches = [
        item
        for item in entries
        if isinstance(item, Mapping)
        and item.get("task_id") == controller.task_id
        and item.get("path") == contract_path
        and item.get("old_sha256")
        == event.details.get("old_task_contract_sha256")
        and item.get("new_sha256")
        == event.details.get("new_task_contract_sha256")
    ]
    if len(matches) != 1:
        raise DownstreamPipelineError(
            "task-contract migration ledger has no unique matching task entry"
        )
    return ledger_path, dict(matches[0])


def _matching_contract_migration_event(
    controller: Any,
    state: Mapping[str, Any],
    human: Mapping[str, Any],
    head: str,
) -> Any:
    service = controller.workflow.issue_workflow
    if service is None:
        raise DownstreamPipelineError("Issue workflow is unavailable")
    snapshot = service.find(controller.task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        raise DownstreamPipelineError(
            "validated PASS carry-forward requires a valid managed Issue"
        )
    matches = []
    for event in snapshot.events:
        if event.event_type is not WorkflowEventType.TASK_CONTRACT_MIGRATED:
            continue
        details = event.details
        if (
            details.get("head_commit") == head
            and details.get("human_handoff_commit")
            == human.get("tested_commit")
            and details.get("human_result") == "pass"
            and details.get("new_task_contract_sha256")
            == state.get("task_contract_sha256")
        ):
            matches.append(event)
    if len(matches) != 1:
        raise DownstreamPipelineError(
            "no unique task-contract migration authorizes the preserved human PASS"
        )
    return matches[0]


def _existing_carry_forward_receipt(
    controller: Any,
    *,
    head: str,
    human_commit: str,
) -> dict[str, Any] | None:
    receipt = controller.state.get("human_pass_carry_forward")
    if not isinstance(receipt, Mapping):
        return None
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") != CARRY_FORWARD_SCHEMA_VERSION
        or receipt.get("receipt_type")
        != "validated_human_pass_carry_forward"
        or receipt.get("authority_kind")
        != "clerical_task_contract_migration"
        or receipt.get("operational_commit") != head
        or receipt.get("human_tested_commit") != human_commit
        or receipt.get("receipt_sha256") != semantic_sha256(payload)
    ):
        return None
    return dict(receipt)


def _integrated_main_for_migration(
    controller: Any,
    human_commit: str,
    head: str,
) -> str:
    """Resolve the main parent that the clerical migration merged into the task.

    The current origin/main may have advanced after the migration. The receipt must
    therefore prove the historical migration first, then let integrate_current_main
    handle later automation-only progress as a separate transition.
    """

    candidates = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-list",
        "--merges",
        "--ancestry-path",
        f"{human_commit}..{head}",
        check=False,
    ).splitlines()
    for merge_commit in candidates:
        values = _git_text(
            controller.command_runner,
            controller.checkout,
            "rev-list",
            "--parents",
            "-n",
            "1",
            merge_commit,
            check=False,
        ).split()
        if len(values) != 3:
            continue
        parents = values[1:]
        contains_human = [
            _git(
                controller.command_runner,
                controller.checkout,
                "merge-base",
                "--is-ancestor",
                human_commit,
                parent,
                check=False,
            ).returncode
            == 0
            for parent in parents
        ]
        if contains_human.count(True) != 1:
            continue
        main_parent = parents[contains_human.index(False)]
        if (
            _git(
                controller.command_runner,
                controller.checkout,
                "merge-base",
                "--is-ancestor",
                main_parent,
                head,
                check=False,
            ).returncode
            == 0
        ):
            return main_parent
    raise DownstreamPipelineError(
        "clerical migration head does not contain one unambiguous mainline merge parent"
    )


def _build_contract_migration_receipt(
    controller: Any,
    state: Mapping[str, Any],
    human: Mapping[str, Any],
    head: str,
) -> dict[str, Any]:
    human_commit = human.get("tested_commit")
    if (
        human.get("result") != "pass"
        or not isinstance(human_commit, str)
        or not _SHA40.fullmatch(human_commit)
    ):
        raise DownstreamPipelineError(
            "clerical migration carry-forward requires an exact original human PASS"
        )
    if (
        _git(
            controller.command_runner,
            controller.checkout,
            "merge-base",
            "--is-ancestor",
            human_commit,
            head,
            check=False,
        ).returncode
        != 0
    ):
        raise DownstreamPipelineError(
            "human-tested commit is not an ancestor of the operational commit"
        )

    current_main = _integrated_main_for_migration(
        controller,
        human_commit,
        head,
    )

    observation = getattr(controller, "last_observation", None)
    task = (
        observation.get("task")
        if isinstance(observation, Mapping)
        and isinstance(observation.get("task"), Mapping)
        else {}
    )
    contract_path = _safe_repository_path(
        task.get("contract_path") or f"Tasks/{controller.task_id}.yaml"
    )
    if contract_path is None:
        raise DownstreamPipelineError("task contract path is invalid")

    event = _matching_contract_migration_event(
        controller,
        state,
        human,
        head,
    )
    ledger_path, ledger_entry = _migration_ledger_entry(
        controller,
        event,
        contract_path,
    )
    old_contract, old_bytes = _json_at(
        controller,
        human_commit,
        contract_path,
        label="human-tested task contract",
    )
    new_contract, new_bytes = _json_at(
        controller,
        head,
        contract_path,
        label="operational task contract",
    )
    old_hash = hashlib.sha256(old_bytes).hexdigest()
    new_hash = hashlib.sha256(new_bytes).hexdigest()
    if (
        old_hash != event.details.get("old_task_contract_sha256")
        or new_hash != event.details.get("new_task_contract_sha256")
        or new_hash != state.get("task_contract_sha256")
    ):
        raise DownstreamPipelineError(
            "task-contract migration hashes do not match Git and Issue authority"
        )

    raw_replacements = ledger_entry.get("replacements")
    if not isinstance(raw_replacements, list) or not raw_replacements:
        raise DownstreamPipelineError(
            "task-contract migration ledger omitted replacements"
        )
    replacements: dict[str, str] = {}
    for item in raw_replacements:
        if not isinstance(item, Mapping):
            raise DownstreamPipelineError(
                "task-contract migration replacement is invalid"
            )
        old = _safe_repository_path(item.get("from"))
        new = _safe_repository_path(item.get("to"))
        if old is None or new is None or old == new:
            raise DownstreamPipelineError(
                "task-contract migration replacement path is invalid"
            )
        replacements[old] = new

    old_revision = old_contract.get("contract_revision")
    new_revision = new_contract.get("contract_revision")
    if (
        not isinstance(old_revision, int)
        or not isinstance(new_revision, int)
        or new_revision != old_revision + 1
        or ledger_entry.get("old_contract_revision") != old_revision
        or ledger_entry.get("new_contract_revision") != new_revision
    ):
        raise DownstreamPipelineError(
            "task-contract migration revision identities are invalid"
        )
    normalized_old = _replace_contract_paths(old_contract, replacements)
    normalized_old["contract_revision"] = new_revision
    if normalized_old != new_contract:
        raise DownstreamPipelineError(
            "task-contract migration changed behavior beyond recorded clerical paths"
        )

    merge_base = _git_text(
        controller.command_runner,
        controller.checkout,
        "merge-base",
        human_commit,
        current_main,
    )
    task_paths = _paths_from_nul(
        _git(
            controller.command_runner,
            controller.checkout,
            "diff",
            "--name-only",
            "-z",
            merge_base,
            human_commit,
            "--",
        ).stdout,
        label="human-tested task delta",
    )
    main_paths = _paths_from_nul(
        _git(
            controller.command_runner,
            controller.checkout,
            "diff",
            "--name-only",
            "-z",
            merge_base,
            current_main,
            "--",
        ).stdout,
        label="clerical migration mainline delta",
    )
    unsafe_main_paths = [path for path in main_paths if not _is_clerical_mainline_path(path)]
    if unsafe_main_paths:
        raise DownstreamPipelineError(
            "clerical migration contains runtime-sensitive mainline paths: "
            + ", ".join(unsafe_main_paths)
        )

    resource_paths: set[str] = set()
    for contract in (old_contract, new_contract):
        values = contract.get("exclusive_resources")
        if isinstance(values, list):
            for value in values:
                path = _resource_path(value)
                if path is not None:
                    resource_paths.add(replacements.get(path, path))
    verified_paths = sorted(
        {
            replacements.get(path, path)
            for path in task_paths
            if path != contract_path
        }
        | resource_paths,
        key=str.casefold,
    )
    changed_blobs = []
    for path in verified_paths:
        before = _object_id_at(controller, human_commit, path)
        after = _object_id_at(controller, head, path)
        if before != after:
            changed_blobs.append(path)
    if changed_blobs:
        raise DownstreamPipelineError(
            "clerical migration changed task-owned blob identities: "
            + ", ".join(changed_blobs)
        )

    payload = {
        "schema_version": CARRY_FORWARD_SCHEMA_VERSION,
        "receipt_type": "validated_human_pass_carry_forward",
        "authority_kind": "clerical_task_contract_migration",
        "task_id": controller.task_id,
        "branch": state.get("branch"),
        "human_tested_commit": human_commit,
        "operational_commit": head,
        "integrated_main_commit": current_main,
        "merge_base": merge_base,
        "migration_event_id": event.event_id,
        "migration_id": event.details.get("migration_id"),
        "ledger_path": ledger_path,
        "old_task_contract_sha256": old_hash,
        "new_task_contract_sha256": new_hash,
        "contract_path": contract_path,
        "old_contract_revision": old_revision,
        "new_contract_revision": new_revision,
        "replacements": [
            {"from": old, "to": new}
            for old, new in sorted(replacements.items(), key=lambda item: item[0].casefold())
        ],
        "task_changed_paths": task_paths,
        "main_changed_paths": main_paths,
        "verified_unchanged_task_paths": verified_paths,
        "human_revalidation_of_operational_commit": False,
        "authority": "deterministic_verified_contract_migration",
    }
    return {**payload, "receipt_sha256": semantic_sha256(payload)}


def _contract_migration_receipt_for(
    controller: Any,
    state: Mapping[str, Any],
    human: Mapping[str, Any],
    head: str,
) -> dict[str, Any]:
    human_commit = str(human.get("tested_commit") or "")
    existing = _existing_carry_forward_receipt(
        controller,
        head=head,
        human_commit=human_commit,
    )
    if existing is not None:
        return existing
    receipt = _build_contract_migration_receipt(
        controller,
        state,
        human,
        head,
    )
    controller.state["human_pass_carry_forward"] = receipt
    controller.state["delivery_base_commit"] = receipt["integrated_main_commit"]
    controller._persist()
    return receipt


def _prepare_contract_migration_mainline_bridge(
    self: Any,
    state: Mapping[str, Any],
    human: Mapping[str, Any],
    head: str,
) -> dict[str, Any]:
    from .mainline_reintegration import _automation_receipt_for

    existing = _automation_receipt_for(self, head)
    if existing is not None:
        return existing
    carry_forward = _contract_migration_receipt_for(
        self,
        state,
        human,
        head,
    )
    payload = {
        "schema_version": "1.0",
        "task_id": self.task_id,
        "branch": state.get("branch"),
        "prior_task_head": carry_forward["human_tested_commit"],
        "human_tested_commit": carry_forward["human_tested_commit"],
        "main_head": carry_forward["integrated_main_commit"],
        "merge_base": carry_forward["merge_base"],
        "integrated_commit": head,
        "classification": "automation_only",
        "human_revalidation_required": False,
        "main_changed_paths": carry_forward["main_changed_paths"],
        "task_changed_paths": carry_forward["task_changed_paths"],
        "overlap_paths": [],
        "exclusive_overlap_paths": [],
        "non_automation_paths": [],
        "task_blob_changes_after_merge": [],
        "created_at_utc": utc_now(),
        "authority": "verified_contract_migration_mainline_bridge",
        "carry_forward_receipt_sha256": carry_forward["receipt_sha256"],
    }
    bridge_receipt = {
        **payload,
        "receipt_sha256": semantic_sha256(payload),
    }
    self.state["mainline_reintegration"] = bridge_receipt
    self._persist()
    return bridge_receipt


def _patched_integrate_current_main(self: Any) -> dict[str, Any]:
    observation = self.observe()
    state = _workflow_state(observation)
    phase = state.get("phase")
    if (
        state.get("state") != WorkflowState.AGENT_WORKING.value
        or state.get("worker_id") != self.workflow.worker_id
        or phase not in (
            WorkflowPhase.DELIVERY_EVIDENCE.value,
            WorkflowPhase.MERGE_CLOSEOUT.value,
        )
    ):
        raise DownstreamPipelineError(
            "mainline integration requires this worker's active downstream lease"
        )
    checkout = observation.get("checkout")
    if not isinstance(checkout, Mapping) or checkout.get("status") != "ready":
        raise DownstreamPipelineError("mainline integration requires a ready checkout")
    head = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "HEAD",
    )
    human = self._latest_human_validation()
    if (
        phase == WorkflowPhase.DELIVERY_EVIDENCE.value
        and isinstance(human, Mapping)
        and human.get("result") == "pass"
        and human.get("tested_commit") != head
    ):
        _prepare_contract_migration_mainline_bridge(
            self,
            state,
            human,
            head,
        )
    return _ORIGINALS["integrate_current_main"](self)


def _patched_assert_human_tested_head(
    self: Any,
    state: Mapping[str, Any],
) -> None:
    try:
        return _ORIGINALS["assert_human_tested_head"](self, state)
    except DownstreamPipelineError as original:
        if str(original) != "exact human PASS for checkout HEAD is missing":
            raise

    self._assert_checkout()
    head = _git_text(self.command_runner, self.checkout, "rev-parse", "HEAD")
    branch = _git_text(
        self.command_runner,
        self.checkout,
        "branch",
        "--show-current",
    )
    if head != state.get("head_commit") or branch != state.get("branch"):
        raise DownstreamPipelineError(
            "checkout differs from the exact branch/commit recorded in the Issue"
        )
    human = self._latest_human_validation()
    if human is None:
        raise DownstreamPipelineError("original human PASS is unavailable")
    receipt = _contract_migration_receipt_for(self, state, human, head)

    _git(
        self.command_runner,
        self.checkout,
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout_seconds=900.0,
    )
    current_main = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "origin/main",
    )
    if (
        _git(
            self.command_runner,
            self.checkout,
            "merge-base",
            "--is-ancestor",
            current_main,
            head,
            check=False,
        ).returncode
        != 0
    ):
        raise DownstreamPipelineError(
            "origin/main advanced beyond the validated clerical migration; run integrate_current_main"
        )
    base_commit = receipt["integrated_main_commit"]
    existing = self.state.get("delivery_base_commit")
    if existing is not None and existing != base_commit:
        raise DownstreamPipelineError(
            "delivery base changed after authoritative work began; reintegrate main"
        )
    if existing is None:
        self.state["delivery_base_commit"] = base_commit
        self._persist()


def _patched_human_validation_artifact(
    self: Any,
    commit: str,
) -> dict[str, Any]:
    receipt = self.state.get("human_pass_carry_forward")
    if not isinstance(receipt, Mapping) or receipt.get("operational_commit") != commit:
        return _ORIGINALS["human_validation_artifact"](self, commit)
    validated = _existing_carry_forward_receipt(
        self,
        head=commit,
        human_commit=str(receipt.get("human_tested_commit") or ""),
    )
    if validated is None:
        raise DownstreamPipelineError(
            "human PASS carry-forward receipt has invalid identity"
        )
    current = self.state.get("human_validation")
    if isinstance(current, Mapping):
        path = Path(str(current.get("path") or ""))
        if path.is_file() and current.get("sha256") == _file_fact(path)["sha256"]:
            return dict(current)
    human = self._latest_human_validation()
    if (
        human is None
        or human.get("result") != "pass"
        or human.get("tested_commit") != validated["human_tested_commit"]
    ):
        raise DownstreamPipelineError("original human PASS is unavailable")
    service = self.workflow.issue_workflow
    if service is None:
        raise DownstreamPipelineError("Issue workflow is unavailable")
    snapshot = service.find(self.task_id)
    if snapshot is None:
        raise DownstreamPipelineError("managed Issue is missing")
    output = self._output_root(commit) / "human-validation.txt"
    if output.exists():
        raise DownstreamPipelineError(
            "human-validation output exists with unknown identity"
        )
    output.write_text(
        "\n".join(
            (
                f"Task: {self.task_id}",
                f"Issue: {snapshot.issue_url}",
                f"Human-tested implementation commit: {validated['human_tested_commit']}",
                f"Operational commit under authoritative validation: {commit}",
                "Human result: PASS",
                "Operational-commit human revalidation: NOT PERFORMED",
                "Carry-forward authority: verified clerical task-contract migration",
                f"Migration ID: {validated['migration_id']}",
                f"Carry-forward receipt SHA256: {validated['receipt_sha256']}",
                "Authoritative Unity validation on the operational commit is required.",
                "",
                str(human.get("body") or "").strip(),
                "",
            )
        ),
        encoding="utf-8",
        newline="\n",
    )
    return _file_fact(output)


def _patched_required_platforms(task: Mapping[str, Any]) -> tuple[str, ...]:
    root = Path(__file__).resolve().parents[2]
    plan = validation_plan_for(root, task)
    if plan is not None:
        return tuple(plan["required_test_platforms"])
    return _ORIGINALS["required_platforms"](task)


def _patched_observe(self: Any) -> dict[str, Any]:
    observation = _ORIGINALS["observe"](self)
    task = observation.get("task")
    downstream = observation.get("downstream")
    if isinstance(task, Mapping) and isinstance(downstream, dict):
        plan = validation_plan_for(self.checkout, task)
        if plan is not None:
            downstream["authoritative_test_plan"] = plan
    self.last_observation = _copy(observation)
    return observation


def _patched_run_authoritative_unity_test(
    self: Any,
    *,
    test_platform: str,
    test_filter: str,
) -> dict[str, Any]:
    observation = self.observe()
    task = observation.get("task")
    if isinstance(task, Mapping):
        plan = validation_plan_for(self.checkout, task)
        if plan is not None:
            expected = plan["test_filters"].get(test_platform)
            if expected is None:
                raise DownstreamPipelineError(
                    f"{test_platform} is not authorized for {self.task_id}"
                )
            if test_filter.strip() != expected:
                raise DownstreamPipelineError(
                    "test_filter differs from the committed authoritative validation policy"
                )
    return _ORIGINALS["run_authoritative_unity_test"](
        self,
        test_platform=test_platform,
        test_filter=test_filter,
    )


def _rejection_fingerprint(
    controller: Any,
    *,
    action: str,
    error: BaseException,
) -> tuple[str, dict[str, Any]]:
    observation = getattr(controller, "last_observation", None)
    if not isinstance(observation, Mapping):
        underlying = getattr(controller, "_controller", controller)
        observation = underlying.observe()
    state = _workflow_state(observation)
    checkout = observation.get("checkout")
    checkout = checkout if isinstance(checkout, Mapping) else {}
    downstream = observation.get("downstream")
    if not isinstance(downstream, Mapping):
        downstream = observation.get("production_pipeline")
    downstream = downstream if isinstance(downstream, Mapping) else {}
    payload = {
        "action": action,
        "error_type": type(error).__name__,
        "error": _normalized_text(error),
        "state_version": state.get("state_version"),
        "state": state.get("state"),
        "phase": state.get("phase"),
        "next_action": downstream.get("next_action"),
        "checkout_status": checkout.get("status"),
        "checkout_head": checkout.get("head_commit"),
    }
    return semantic_sha256(payload), payload


def _release_active_lease(
    controller: Any,
    *,
    reason: str,
    details: Mapping[str, Any],
) -> bool:
    underlying = getattr(controller, "_controller", controller)
    workflow = getattr(underlying, "workflow", None)
    service = getattr(workflow, "issue_workflow", None)
    worker_id = str(getattr(workflow, "worker_id", "") or "")
    task_id = str(getattr(underlying, "task_id", "") or "")
    if service is None or not worker_id or not task_id:
        return False
    snapshot = service.find(task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        return False
    state = snapshot.state
    if (
        state.state is not WorkflowState.AGENT_WORKING
        or state.worker_id != worker_id
    ):
        return False
    next_state, event = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
        actor_type=WorkflowActor.AGENT,
        actor_id=worker_id,
        to_state=WorkflowState.AGENT_READY,
        to_phase=state.phase,
        details={"reason": reason, **dict(details)},
        now=utc_now(),
    )
    service.backend.add_comment(
        snapshot.issue_number,
        render_event_comment(
            event,
            "\n".join(
                (
                    "The agent released its lease because deterministic work could not continue safely.",
                    "",
                    f"- **Reason:** `{reason}`",
                    f"- **Action:** `{details.get('action')}`",
                    f"- **Error:** {details.get('error')}",
                    "",
                    "The Issue remains the durable resume token. A later generic run must "
                    "re-observe Git, TaskGraph, checkout, and Issue identities before acting.",
                )
            ),
        ),
    )
    service.backend.update_issue(
        snapshot.issue_number,
        body=update_issue_body(
            snapshot.body,
            next_state,
            next_action=(
                "Run the generic Game Task Agent again after the recorded deterministic "
                "failure is corrected."
            ),
        ),
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=[service.assignee],
    )
    service.verify_post_mutation_state(
        task_id,
        next_state,
        transition_name="deterministic failure lease release",
    )
    return True


def _record_action_rejection(
    self: Any,
    *,
    action: str,
    error: BaseException,
) -> bool:
    fingerprint, payload = _rejection_fingerprint(
        self,
        action=action,
        error=error,
    )
    counts = getattr(self, "_action_rejection_counts", None)
    if not isinstance(counts, dict):
        counts = {}
        self._action_rejection_counts = counts
    count = int(counts.get(fingerprint, 0)) + 1
    counts[fingerprint] = count
    if count < 2:
        return False
    details = {
        "action": action,
        "error_type": payload["error_type"],
        "error": payload["error"],
        "rejection_fingerprint": fingerprint,
        "repeated_count": count,
        "state_version": payload["state_version"],
        "checkout_head": payload["checkout_head"],
        "next_action": payload["next_action"],
    }
    released = _release_active_lease(
        self,
        reason="repeated_action_rejection",
        details=details,
    )
    if released:
        self._terminal_reasons = [
            f"{action} was rejected {count} times without deterministic state progress: "
            f"{payload['error']}"
        ]
        self._resilience_terminal_status = "repeated_action_rejection"
        progress = getattr(self, "_progress", None)
        if progress is not None:
            progress.emit(
                "repeated_action_rejection",
                "Repeated deterministic action rejection released the agent lease",
                action=action,
                error=payload["error"],
                rejection_fingerprint=fingerprint,
                repeated_count=count,
            )
    return released


def _release_for_pipeline_failure(
    self: Any,
    *,
    reason: str,
    action: str,
    error: BaseException,
) -> bool:
    detail = _normalized_text(error)
    released = _release_active_lease(
        self,
        reason=reason,
        details={
            "action": action,
            "error_type": type(error).__name__,
            "error": detail,
        },
    )
    if released:
        self._terminal_reasons = [f"{reason}: {detail}"]
        self._resilience_terminal_status = reason
    return released


def _patched_guard_observe(self: Any) -> dict[str, Any]:
    observation = _ORIGINALS["guard_observe"](self)
    status = getattr(self, "_resilience_terminal_status", None)
    if status and isinstance(observation.get("goal_loop_guard"), dict):
        observation["goal_loop_guard"]["status"] = status
        observation["goal_loop_guard"]["authority"] = (
            "deterministic_action_rejection_circuit_breaker"
        )
    return observation


def _wrap_execute(original: Any):
    def wrapped(decision: Any, controller: Any) -> Any:
        try:
            return original(decision, controller)
        except TaskReviewContractError as exc:
            recorder = getattr(controller, "record_action_rejection", None)
            if callable(recorder):
                recorder(action=decision.action, error=exc)
            raise

    return wrapped


def _wrap_run(original: Any, module: Any, *, pipeline_name: str):
    def wrapped(request: Any, controller: Any, **values: Any) -> Any:
        try:
            return original(request, controller, **values)
        except KeyboardInterrupt as exc:
            releaser = getattr(controller, "release_for_pipeline_failure", None)
            if callable(releaser):
                releaser(
                    reason="worker_interrupted",
                    action=f"{pipeline_name}_supervisor",
                    error=exc,
                )
            raise
        except Exception as exc:
            exhausted = "exhausted" in str(exc).casefold()
            releaser = getattr(controller, "release_for_pipeline_failure", None)
            if callable(releaser):
                releaser(
                    reason=(
                        "turn_budget_exhausted"
                        if exhausted
                        else "pipeline_failed"
                    ),
                    action=f"{pipeline_name}_supervisor",
                    error=exc,
                )
            if not exhausted:
                raise
            observation = controller.observe()
            terminal = module._terminal_outcome(request, observation)
            if terminal is not None:
                return terminal
            raise

    return wrapped


def install_downstream_resilience() -> None:
    """Install all downstream resilience extensions exactly once."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import downstream_pipeline as pipeline
    from . import downstream_runtime as runtime
    from . import goal_loop_guard as guard
    from . import openai_downstream as openai_downstream
    from . import openai_pipeline as openai_pipeline

    controller = runtime.ResumableDownstreamTaskController
    _ORIGINALS.update(
        {
            "assert_human_tested_head": controller._assert_human_tested_head,
            "human_validation_artifact": controller._human_validation_artifact,
            "integrate_current_main": controller.integrate_current_main,
            "required_platforms": pipeline._required_platforms,
            "observe": controller.observe,
            "run_authoritative_unity_test": controller.run_authoritative_unity_test,
            "guard_observe": guard.GuardedTaskController.observe,
            "downstream_execute": openai_downstream._execute,
            "production_execute": openai_pipeline._execute,
            "downstream_run": openai_downstream.run_openai_downstream_pipeline,
            "production_run": openai_pipeline.run_openai_production_pipeline,
        }
    )

    controller._assert_human_tested_head = _patched_assert_human_tested_head
    controller._human_validation_artifact = _patched_human_validation_artifact
    controller.observe = _patched_observe
    controller.run_authoritative_unity_test = _patched_run_authoritative_unity_test
    controller.integrate_current_main = _patched_integrate_current_main

    pipeline._required_platforms = _patched_required_platforms
    runtime._required_platforms = _patched_required_platforms

    guard.GuardedTaskController.record_action_rejection = _record_action_rejection
    guard.GuardedTaskController.release_for_pipeline_failure = (
        _release_for_pipeline_failure
    )
    guard.GuardedTaskController.observe = _patched_guard_observe

    openai_downstream._execute = _wrap_execute(
        openai_downstream._execute
    )
    openai_pipeline._execute = _wrap_execute(openai_pipeline._execute)
    openai_downstream.run_openai_downstream_pipeline = _wrap_run(
        openai_downstream.run_openai_downstream_pipeline,
        openai_downstream,
        pipeline_name="downstream",
    )
    openai_pipeline.run_openai_production_pipeline = _wrap_run(
        openai_pipeline.run_openai_production_pipeline,
        openai_pipeline,
        pipeline_name="implementation",
    )

    openai_downstream._GOAL_AND_RULES += """
- If downstream.authoritative_test_plan exists, use its exact platform/filter pair.
  Do not search for, infer, broaden, or substitute another Unity test filter.
- A human PASS may be carried forward only when deterministic host code exposes a
  validated hash-bound carry-forward receipt. Never infer carry-forward from ancestry.
- After a deterministic action rejection, select a materially different corrective
  action. Repeating the same rejection releases the lease and terminates the run.
"""

    _INSTALLED = True


__all__ = [
    "install_downstream_resilience",
    "validation_plan_for",
]
