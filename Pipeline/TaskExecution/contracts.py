"""Immutable No Safe Circle task-execution identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from Pipeline.AgentRuntime.contracts import (
    AgentInvocationRequest,
    ContractValidationError,
    validate_repository_path,
)


TASK_EXECUTION_REQUEST_SCHEMA_VERSION = "1.0"
_TASK_ID = re.compile(r"^NSC-[0-9]{3}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _expect_fields(value: Mapping[str, Any], expected: set[str], *, where: str) -> None:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{where} must be an object")
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise ContractValidationError(f"unsupported {where} fields: {sorted(unknown)}")
    if missing:
        raise ContractValidationError(f"missing {where} fields: {sorted(missing)}")


@dataclass(frozen=True)
class TaskContractIdentity:
    path: str
    revision: int
    sha256: str

    def __post_init__(self) -> None:
        validate_repository_path(self.path, field="task_contract_identity.path")
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ContractValidationError("task contract revision must be positive")
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise ContractValidationError(
                "task contract sha256 must be 64 lowercase hex characters"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "revision": self.revision, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TaskContractIdentity":
        _expect_fields(
            value,
            {"path", "revision", "sha256"},
            where="task_contract_identity",
        )
        return cls(value["path"], value["revision"], value["sha256"])


@dataclass(frozen=True)
class TaskExecutionRequest:
    schema_version: str
    task_id: str
    task_contract_identity: TaskContractIdentity
    invocation: AgentInvocationRequest

    def __post_init__(self) -> None:
        if self.schema_version != TASK_EXECUTION_REQUEST_SCHEMA_VERSION:
            raise ContractValidationError("unsupported TaskExecutionRequest schema_version")
        if not isinstance(self.task_id, str) or not _TASK_ID.fullmatch(self.task_id):
            raise ContractValidationError("task_id must match NSC-###")
        if type(self.task_contract_identity) is not TaskContractIdentity:
            raise ContractValidationError("task_contract_identity has the wrong type")
        expected_path = f"Tasks/{self.task_id}.yaml"
        if self.task_contract_identity.path != expected_path:
            raise ContractValidationError(
                f"task_contract_identity.path must equal {expected_path}"
            )
        if type(self.invocation) is not AgentInvocationRequest:
            raise ContractValidationError(
                "invocation must be an exact AgentInvocationRequest"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_contract_identity": TaskContractIdentity.to_dict(
                self.task_contract_identity
            ),
            "invocation": AgentInvocationRequest.to_dict(self.invocation),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TaskExecutionRequest":
        _expect_fields(
            value,
            {"schema_version", "task_id", "task_contract_identity", "invocation"},
            where="TaskExecutionRequest",
        )
        return cls(
            value["schema_version"],
            value["task_id"],
            TaskContractIdentity.from_dict(value["task_contract_identity"]),
            AgentInvocationRequest.from_dict(value["invocation"]),
        )
