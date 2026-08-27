"""Strict deterministic contracts for the task-to-human-review goal."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping


TASK_REVIEW_SCHEMA_VERSION = "1.0"
TASK_ID_RE = re.compile(r"^NSC-[0-9]{3}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


class TaskReviewContractError(ValueError):
    """Raised when an untrusted task-review value violates its contract."""


class OutcomeStatus(str, Enum):
    HUMAN_REVIEW_READY = "human_review_ready"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"


class CrewStatus(str, Enum):
    REVIEW_READY = "review_ready"
    CONTRACT_REVIEW_REQUIRED = "contract_review_required"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    AGENT_FAILED = "agent_failed"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_string(value: Any, *, field: str, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise TaskReviewContractError(f"{field} must be an exact string")
    if not allow_empty and not value.strip():
        raise TaskReviewContractError(f"{field} must be non-empty")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise TaskReviewContractError(f"{field} must be valid UTF-8") from exc
    return value


def validate_task_id(value: Any) -> str:
    task_id = _require_string(value, field="task_id")
    if not TASK_ID_RE.fullmatch(task_id):
        raise TaskReviewContractError("task_id must match NSC-###")
    return task_id


def _validate_sha(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    text = _require_string(value, field=field)
    if not pattern.fullmatch(text):
        raise TaskReviewContractError(f"{field} has an invalid identity")
    return text


def _validate_repository_path(value: Any, *, field: str) -> str:
    text = _require_string(value, field=field)
    if "\\" in text:
        raise TaskReviewContractError(f"{field} must use repository-relative POSIX separators")
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts:
        raise TaskReviewContractError(f"{field} must be repository-relative")
    if any(part in ("", ".", "..") for part in path.parts):
        raise TaskReviewContractError(f"{field} contains an invalid path component")
    if text.casefold().endswith(".meta"):
        raise TaskReviewContractError(f"{field} must not grant model write authority to .meta")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise TaskReviewContractError(f"{field} contains a control character")
    return text


def _validated_paths(values: Iterable[Any], *, field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TaskReviewContractError(f"{field} must be a path array")
    normalized = tuple(_validate_repository_path(item, field=field) for item in values)
    folded = [item.casefold() for item in normalized]
    if len(folded) != len(set(folded)):
        raise TaskReviewContractError(f"{field} contains duplicate paths")
    return tuple(sorted(normalized, key=str.casefold))


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TaskReviewContractError(f"{field} must be an object")
    return value


def _require_keys(value: Mapping[str, Any], *, field: str, keys: set[str]) -> None:
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extras = sorted(actual - keys)
        raise TaskReviewContractError(
            f"{field} keys do not match contract; missing={missing}, extras={extras}"
        )


@dataclass(frozen=True)
class TaskReviewRequest:
    task_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", validate_task_id(self.task_id))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": TASK_REVIEW_SCHEMA_VERSION, "task_id": self.task_id}


@dataclass(frozen=True)
class ExecutionScopePlan:
    existing_implementation_paths: tuple[str, ...]
    new_implementation_paths: tuple[str, ...]
    existing_test_paths: tuple[str, ...]
    new_test_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        fields = (
            "existing_implementation_paths",
            "new_implementation_paths",
            "existing_test_paths",
            "new_test_paths",
        )
        for field_name in fields:
            object.__setattr__(
                self,
                field_name,
                _validated_paths(getattr(self, field_name), field=field_name),
            )

        implementation = (*self.existing_implementation_paths, *self.new_implementation_paths)
        tests = (*self.existing_test_paths, *self.new_test_paths)
        if not implementation:
            raise TaskReviewContractError(
                "execution scope requires at least one implementation path"
            )
        if not tests:
            raise TaskReviewContractError("execution scope requires at least one test path")
        implementation_folded = {item.casefold() for item in implementation}
        test_folded = {item.casefold() for item in tests}
        overlap = sorted(implementation_folded & test_folded)
        if overlap:
            raise TaskReviewContractError(
                f"implementation and test authority must be disjoint: {overlap}"
            )

    @classmethod
    def from_dict(cls, value: Any) -> "ExecutionScopePlan":
        raw = _require_mapping(value, field="execution_scope_plan")
        expected = {
            "existing_implementation_paths",
            "new_implementation_paths",
            "existing_test_paths",
            "new_test_paths",
        }
        _require_keys(raw, field="execution_scope_plan", keys=expected)
        return cls(
            tuple(raw["existing_implementation_paths"]),
            tuple(raw["new_implementation_paths"]),
            tuple(raw["existing_test_paths"]),
            tuple(raw["new_test_paths"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "existing_implementation_paths": list(self.existing_implementation_paths),
            "new_implementation_paths": list(self.new_implementation_paths),
            "existing_test_paths": list(self.existing_test_paths),
            "new_test_paths": list(self.new_test_paths),
        }

    @property
    def semantic_sha256(self) -> str:
        return semantic_sha256(self.to_dict())


@dataclass(frozen=True)
class ScopeValidationResult:
    accepted: bool
    reasons: tuple[str, ...]
    plan_id: str | None

    def __post_init__(self) -> None:
        if type(self.accepted) is not bool:
            raise TaskReviewContractError("accepted must be an exact boolean")
        normalized_reasons = tuple(
            _require_string(item, field="scope_validation_reason") for item in self.reasons
        )
        object.__setattr__(self, "reasons", normalized_reasons)
        if self.accepted:
            if self.reasons:
                raise TaskReviewContractError("accepted scope validation cannot contain reasons")
            plan_id = _require_string(self.plan_id, field="plan_id")
            if not RUN_ID_RE.fullmatch(plan_id):
                raise TaskReviewContractError("plan_id is invalid")
            object.__setattr__(self, "plan_id", plan_id)
        elif self.plan_id is not None:
            raise TaskReviewContractError("rejected scope validation cannot publish plan_id")
        elif not self.reasons:
            raise TaskReviewContractError("rejected scope validation requires reasons")

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "plan_id": self.plan_id,
        }


@dataclass(frozen=True)
class ExecutionRunObservation:
    run_id: str
    task_id: str
    crew_status: CrewStatus
    source_head: str
    task_contract_sha256: str
    candidate_patch_path: str | None
    candidate_sha256: str | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        run_id = _require_string(self.run_id, field="run_id")
        if not RUN_ID_RE.fullmatch(run_id):
            raise TaskReviewContractError("run_id is invalid")
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "task_id", validate_task_id(self.task_id))
        if not isinstance(self.crew_status, CrewStatus):
            try:
                object.__setattr__(self, "crew_status", CrewStatus(self.crew_status))
            except (TypeError, ValueError) as exc:
                raise TaskReviewContractError("crew_status is invalid") from exc
        object.__setattr__(
            self,
            "source_head",
            _validate_sha(self.source_head, field="source_head", pattern=GIT_SHA_RE),
        )
        object.__setattr__(
            self,
            "task_contract_sha256",
            _validate_sha(
                self.task_contract_sha256,
                field="task_contract_sha256",
                pattern=SHA256_RE,
            ),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(_require_string(item, field="execution_reason") for item in self.reasons),
        )
        if self.crew_status is CrewStatus.REVIEW_READY:
            path = _require_string(self.candidate_patch_path, field="candidate_patch_path")
            candidate_sha = _validate_sha(
                self.candidate_sha256,
                field="candidate_sha256",
                pattern=SHA256_RE,
            )
            object.__setattr__(self, "candidate_patch_path", path)
            object.__setattr__(self, "candidate_sha256", candidate_sha)
            if self.reasons:
                raise TaskReviewContractError("review_ready run cannot contain blocking reasons")
        elif self.candidate_patch_path is not None or self.candidate_sha256 is not None:
            raise TaskReviewContractError(
                "non-review-ready run cannot expose an applyable candidate identity"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "crew_status": self.crew_status.value,
            "source_head": self.source_head,
            "task_contract_sha256": self.task_contract_sha256,
            "candidate_patch_path": self.candidate_patch_path,
            "candidate_sha256": self.candidate_sha256,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class HumanReviewProof:
    proof_id: str
    task_id: str
    run_id: str
    source_head: str
    task_contract_sha256: str
    candidate_patch_path: str
    candidate_sha256: str
    apply_check_passed: bool
    source_unchanged: bool
    authority: str = "review_only_not_applied"

    def __post_init__(self) -> None:
        proof_id = _validate_sha(self.proof_id, field="proof_id", pattern=SHA256_RE)
        object.__setattr__(self, "proof_id", proof_id)
        object.__setattr__(self, "task_id", validate_task_id(self.task_id))
        run_id = _require_string(self.run_id, field="run_id")
        if not RUN_ID_RE.fullmatch(run_id):
            raise TaskReviewContractError("run_id is invalid")
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(
            self,
            "source_head",
            _validate_sha(self.source_head, field="source_head", pattern=GIT_SHA_RE),
        )
        object.__setattr__(
            self,
            "task_contract_sha256",
            _validate_sha(
                self.task_contract_sha256,
                field="task_contract_sha256",
                pattern=SHA256_RE,
            ),
        )
        object.__setattr__(
            self,
            "candidate_patch_path",
            _require_string(self.candidate_patch_path, field="candidate_patch_path"),
        )
        object.__setattr__(
            self,
            "candidate_sha256",
            _validate_sha(
                self.candidate_sha256,
                field="candidate_sha256",
                pattern=SHA256_RE,
            ),
        )
        if type(self.apply_check_passed) is not bool or type(self.source_unchanged) is not bool:
            raise TaskReviewContractError("proof booleans must be exact booleans")
        if not self.apply_check_passed or not self.source_unchanged:
            raise TaskReviewContractError(
                "human-review proof requires apply check and unchanged source"
            )
        if self.authority != "review_only_not_applied":
            raise TaskReviewContractError("human-review proof has invalid authority")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "source_head": self.source_head,
            "task_contract_sha256": self.task_contract_sha256,
            "candidate_patch_path": self.candidate_patch_path,
            "candidate_sha256": self.candidate_sha256,
            "apply_check_passed": self.apply_check_passed,
            "source_unchanged": self.source_unchanged,
            "authority": self.authority,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"proof_id": self.proof_id, **self.identity_payload()}

    @classmethod
    def create(cls, **values: Any) -> "HumanReviewProof":
        payload = dict(values)
        payload.setdefault("authority", "review_only_not_applied")
        return cls(proof_id=semantic_sha256(payload), **payload)

    @classmethod
    def from_dict(cls, value: Any) -> "HumanReviewProof":
        raw = _require_mapping(value, field="human_review_proof")
        expected = {
            "proof_id",
            "task_id",
            "run_id",
            "source_head",
            "task_contract_sha256",
            "candidate_patch_path",
            "candidate_sha256",
            "apply_check_passed",
            "source_unchanged",
            "authority",
        }
        _require_keys(raw, field="human_review_proof", keys=expected)
        proof = cls(**dict(raw))
        if semantic_sha256(proof.identity_payload()) != proof.proof_id:
            raise TaskReviewContractError("human-review proof identity does not match its payload")
        return proof


@dataclass(frozen=True)
class TaskReviewOutcome:
    status: OutcomeStatus
    task_id: str
    summary: str
    proof: HumanReviewProof | None
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, OutcomeStatus):
            try:
                object.__setattr__(self, "status", OutcomeStatus(self.status))
            except (TypeError, ValueError) as exc:
                raise TaskReviewContractError("outcome status is invalid") from exc
        object.__setattr__(self, "task_id", validate_task_id(self.task_id))
        object.__setattr__(self, "summary", _require_string(self.summary, field="summary"))
        object.__setattr__(
            self,
            "blockers",
            tuple(_require_string(item, field="blocker") for item in self.blockers),
        )
        if self.status is OutcomeStatus.HUMAN_REVIEW_READY:
            if not isinstance(self.proof, HumanReviewProof):
                raise TaskReviewContractError("human_review_ready requires deterministic proof")
            if self.proof.task_id != self.task_id:
                raise TaskReviewContractError("outcome task and proof task do not match")
            if self.blockers:
                raise TaskReviewContractError("human_review_ready cannot contain blockers")
        elif self.proof is not None:
            raise TaskReviewContractError("non-ready outcome cannot contain human-review proof")
        elif not self.blockers:
            raise TaskReviewContractError("non-ready outcome requires at least one blocker")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "status": self.status.value,
            "task_id": self.task_id,
            "summary": self.summary,
            "proof": self.proof.to_dict() if self.proof is not None else None,
            "blockers": list(self.blockers),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "TaskReviewOutcome":
        raw = _require_mapping(value, field="task_review_outcome")
        expected = {
            "schema_version",
            "status",
            "task_id",
            "summary",
            "proof",
            "blockers",
        }
        _require_keys(raw, field="task_review_outcome", keys=expected)
        if raw["schema_version"] != TASK_REVIEW_SCHEMA_VERSION:
            raise TaskReviewContractError("unsupported task-review outcome schema_version")
        proof = None if raw["proof"] is None else HumanReviewProof.from_dict(raw["proof"])
        return cls(
            status=OutcomeStatus(raw["status"]),
            task_id=raw["task_id"],
            summary=raw["summary"],
            proof=proof,
            blockers=tuple(raw["blockers"]),
        )
