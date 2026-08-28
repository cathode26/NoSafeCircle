"""Hash-bound human approval proposals for TaskDelivery review drafts."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import SHA256_RE, TaskReviewContractError, validate_task_id


DELIVERY_PROPOSAL_SCHEMA_VERSION = "1.0"


class DeliveryReviewError(TaskReviewContractError):
    """Raised when a delivery proposal or approved review is invalid."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryReviewError(f"unable to read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise DeliveryReviewError(f"{label} must contain a JSON object")
    return value


def _meaningful(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeliveryReviewError(f"{field} must be non-empty")
    text = value.strip()
    if text.casefold() in {"todo", "tbd", "placeholder", "n/a"}:
        raise DeliveryReviewError(f"{field} must be meaningful")
    return text


def _new_output(path: Path, label: str) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if path.exists() or path.is_symlink():
        raise DeliveryReviewError(f"{label} already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _publish(path: Path, value: Any) -> None:
    data = _canonical_bytes(value)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except FileExistsError as exc:
        raise DeliveryReviewError(f"refusing to overwrite output: {path}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class DeliveryReviewProposal:
    task_id: str
    draft_path: str
    draft_sha256: str
    validated_commit: str
    branch: str
    selected_surfaces: tuple[tuple[str, str], ...]
    gate_mappings: tuple[tuple[str, tuple[str, ...], str], ...]
    approval_notes: str
    created_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DELIVERY_PROPOSAL_SCHEMA_VERSION,
            "proposal_kind": "delivery_spec_approval",
            "task_id": self.task_id,
            "draft_path": self.draft_path,
            "draft_sha256": self.draft_sha256,
            "validated_commit": self.validated_commit,
            "branch": self.branch,
            "selected_surfaces": [
                {"path": path, "role": role}
                for path, role in self.selected_surfaces
            ],
            "gate_mappings": [
                {"gate_id": gate_id, "evidence": list(evidence), "notes": notes}
                for gate_id, evidence, notes in self.gate_mappings
            ],
            "approval_notes": self.approval_notes,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeliveryReviewProposal":
        expected = {
            "schema_version",
            "proposal_kind",
            "task_id",
            "draft_path",
            "draft_sha256",
            "validated_commit",
            "branch",
            "selected_surfaces",
            "gate_mappings",
            "approval_notes",
            "created_by",
        }
        if set(value) != expected:
            raise DeliveryReviewError("delivery proposal fields do not match schema")
        if value.get("schema_version") != DELIVERY_PROPOSAL_SCHEMA_VERSION:
            raise DeliveryReviewError("unsupported delivery proposal schema_version")
        if value.get("proposal_kind") != "delivery_spec_approval":
            raise DeliveryReviewError("unsupported delivery proposal kind")
        task_id = validate_task_id(value.get("task_id"))
        draft_path = _meaningful(value.get("draft_path"), "draft_path")
        draft_sha = _meaningful(value.get("draft_sha256"), "draft_sha256")
        if not SHA256_RE.fullmatch(draft_sha):
            raise DeliveryReviewError("draft_sha256 is invalid")
        commit = _meaningful(value.get("validated_commit"), "validated_commit")
        if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
            raise DeliveryReviewError("validated_commit is invalid")
        branch = _meaningful(value.get("branch"), "branch")
        raw_surfaces = value.get("selected_surfaces")
        if not isinstance(raw_surfaces, list) or not raw_surfaces:
            raise DeliveryReviewError("selected_surfaces must be non-empty")
        surfaces: list[tuple[str, str]] = []
        for item in raw_surfaces:
            if not isinstance(item, Mapping) or set(item) != {"path", "role"}:
                raise DeliveryReviewError("selected surface has invalid fields")
            surfaces.append(
                (
                    _meaningful(item.get("path"), "surface path"),
                    _meaningful(item.get("role"), "surface role"),
                )
            )
        if len({path for path, _ in surfaces}) != len(surfaces):
            raise DeliveryReviewError("selected surface paths must be unique")
        raw_gates = value.get("gate_mappings")
        if not isinstance(raw_gates, list) or not raw_gates:
            raise DeliveryReviewError("gate_mappings must be non-empty")
        gates: list[tuple[str, tuple[str, ...], str]] = []
        for item in raw_gates:
            if not isinstance(item, Mapping) or set(item) != {"gate_id", "evidence", "notes"}:
                raise DeliveryReviewError("gate mapping has invalid fields")
            evidence = item.get("evidence")
            if (
                not isinstance(evidence, list)
                or not evidence
                or any(not isinstance(entry, str) or not entry for entry in evidence)
                or len(evidence) != len(set(evidence))
            ):
                raise DeliveryReviewError("gate evidence must be a unique non-empty list")
            gates.append(
                (
                    _meaningful(item.get("gate_id"), "gate_id"),
                    tuple(evidence),
                    _meaningful(item.get("notes"), "gate notes"),
                )
            )
        if len({gate_id for gate_id, _, _ in gates}) != len(gates):
            raise DeliveryReviewError("gate IDs must be unique")
        return cls(
            task_id=task_id,
            draft_path=draft_path,
            draft_sha256=draft_sha,
            validated_commit=commit,
            branch=branch,
            selected_surfaces=tuple(surfaces),
            gate_mappings=tuple(gates),
            approval_notes=_meaningful(value.get("approval_notes"), "approval_notes"),
            created_by=_meaningful(value.get("created_by"), "created_by"),
        )


def _validate_against_draft(
    proposal: DeliveryReviewProposal,
    draft: Mapping[str, Any],
) -> None:
    if draft.get("schema_version") != "1.0" or draft.get("review_kind") != "delivery_spec_review":
        raise DeliveryReviewError("delivery draft has an unsupported schema")
    task = draft.get("task")
    if not isinstance(task, Mapping) or task.get("id") != proposal.task_id:
        raise DeliveryReviewError("proposal task differs from delivery draft")
    if draft.get("validated_commit") != proposal.validated_commit:
        raise DeliveryReviewError("proposal commit differs from delivery draft")
    raw_candidates = draft.get("surface_candidates")
    if not isinstance(raw_candidates, list):
        raise DeliveryReviewError("delivery draft omitted surface_candidates")
    candidate_paths = {
        item.get("path")
        for item in raw_candidates
        if isinstance(item, Mapping) and isinstance(item.get("path"), str)
    }
    selected_paths = {path for path, _ in proposal.selected_surfaces}
    if not selected_paths or not selected_paths.issubset(candidate_paths):
        raise DeliveryReviewError("proposal selected a surface outside the draft")
    artifacts = draft.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise DeliveryReviewError("delivery draft omitted artifacts")
    artifact_ids = {
        item.get("id")
        for item in artifacts
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    draft_gates = draft.get("gates")
    if not isinstance(draft_gates, list) or not draft_gates:
        raise DeliveryReviewError("delivery draft omitted gates")
    expected_gates = [
        item.get("gate_id")
        for item in draft_gates
        if isinstance(item, Mapping)
    ]
    actual_gates = [gate_id for gate_id, _, _ in proposal.gate_mappings]
    if actual_gates != expected_gates:
        raise DeliveryReviewError(
            "proposal gates must exactly preserve the draft gate order"
        )
    for gate_id, evidence, _ in proposal.gate_mappings:
        if any(item not in artifact_ids for item in evidence):
            raise DeliveryReviewError(
                f"gate {gate_id} references an unknown artifact"
            )


def create_delivery_review_proposal(
    *,
    draft_path: Path,
    output_path: Path,
    task_id: str,
    branch: str,
    selected_surfaces: Iterable[Mapping[str, Any]],
    gate_mappings: Iterable[Mapping[str, Any]],
    approval_notes: str,
    created_by: str,
) -> dict[str, Any]:
    draft_path = draft_path.resolve(strict=True)
    draft = _json_file(draft_path, "delivery review draft")
    proposal = DeliveryReviewProposal.from_dict(
        {
            "schema_version": DELIVERY_PROPOSAL_SCHEMA_VERSION,
            "proposal_kind": "delivery_spec_approval",
            "task_id": task_id,
            "draft_path": str(draft_path),
            "draft_sha256": file_sha256(draft_path),
            "validated_commit": draft.get("validated_commit"),
            "branch": branch,
            "selected_surfaces": list(selected_surfaces),
            "gate_mappings": list(gate_mappings),
            "approval_notes": approval_notes,
            "created_by": created_by,
        }
    )
    _validate_against_draft(proposal, draft)
    output_path = _new_output(output_path, "delivery proposal")
    _publish(output_path, proposal.to_dict())
    return {
        "schema_version": DELIVERY_PROPOSAL_SCHEMA_VERSION,
        "task_id": proposal.task_id,
        "draft_path": str(draft_path),
        "draft_sha256": proposal.draft_sha256,
        "proposal_path": str(output_path),
        "proposal_sha256": file_sha256(output_path),
        "validated_commit": proposal.validated_commit,
        "selected_surfaces": [
            {"path": path, "role": role}
            for path, role in proposal.selected_surfaces
        ],
        "gate_mappings": [
            {"gate_id": gate_id, "evidence": list(evidence), "notes": notes}
            for gate_id, evidence, notes in proposal.gate_mappings
        ],
    }


def materialize_approved_review(
    *,
    proposal_path: Path,
    expected_proposal_sha256: str,
    output_path: Path,
    approved_by: str,
) -> dict[str, Any]:
    proposal_path = proposal_path.resolve(strict=True)
    if file_sha256(proposal_path) != expected_proposal_sha256:
        raise DeliveryReviewError("delivery proposal changed after human approval")
    proposal = DeliveryReviewProposal.from_dict(
        _json_file(proposal_path, "delivery proposal")
    )
    draft_path = Path(proposal.draft_path).resolve(strict=True)
    if file_sha256(draft_path) != proposal.draft_sha256:
        raise DeliveryReviewError("delivery draft changed after proposal creation")
    draft = _json_file(draft_path, "delivery review draft")
    _validate_against_draft(proposal, draft)

    selected = {path: role for path, role in proposal.selected_surfaces}
    surface_candidates = draft.get("surface_candidates")
    assert isinstance(surface_candidates, list)
    for item in surface_candidates:
        if not isinstance(item, dict):
            raise DeliveryReviewError("delivery draft surface candidate is invalid")
        path = item.get("path")
        item["selected"] = path in selected
        item["role"] = selected.get(path, "")

    mappings = {
        gate_id: (list(evidence), notes)
        for gate_id, evidence, notes in proposal.gate_mappings
    }
    gates = draft.get("gates")
    assert isinstance(gates, list)
    for item in gates:
        if not isinstance(item, dict) or item.get("gate_id") not in mappings:
            raise DeliveryReviewError("delivery draft gate is invalid")
        evidence, notes = mappings[item["gate_id"]]
        item["evidence"] = evidence
        item["notes"] = notes

    draft["review_status"] = "approved"
    draft["human_approval"] = {
        "required": True,
        "decision": "approved",
        "approved_by": _meaningful(approved_by, "approved_by"),
        "notes": proposal.approval_notes,
    }
    output_path = _new_output(output_path, "approved delivery review")
    _publish(output_path, draft)
    return {
        "schema_version": "1.0",
        "task_id": proposal.task_id,
        "approved_review_path": str(output_path),
        "approved_review_sha256": file_sha256(output_path),
        "proposal_path": str(proposal_path),
        "proposal_sha256": expected_proposal_sha256,
        "validated_commit": proposal.validated_commit,
    }
