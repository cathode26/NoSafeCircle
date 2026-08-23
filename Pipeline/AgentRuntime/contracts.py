"""Provider-neutral immutable request/result contracts for AgentRuntime."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

from .json_values import JsonValueError, freeze_json, thaw_json, validate_text


SCHEMA_VERSION = "1.0"
MODEL_CAPABILITY_CLASSES = frozenset({"low_cost", "standard", "high_reasoning"})
SUPPORTED_CAPABILITIES = frozenset(
    {
        "repository_read",
        "repository_search",
        "repository_write",
        "approved_command_execution",
    }
)
RESULT_STATUSES = frozenset({"succeeded", "failed"})
FAILURE_CLASSIFICATIONS = frozenset(
    {
        "none",
        "provider_error",
        "timeout",
        "permission_denied",
        "schema_error",
        "budget_exhausted",
        "invalid_request",
        "internal_error",
    }
)
MAX_TURN_LIMIT = 1_000
MAX_TIMEOUT_SECONDS = 86_400
MAX_TOKEN_LIMIT = 10_000_000

_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*$")
_TASK_ID = re.compile(r"^NSC-[0-9]{3}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = frozenset({"con", "prn", "aux", "nul", "conin$", "conout$"})
_WINDOWS_DEVICE = re.compile(r"^(?:com|lpt)[1-9]$")
_WINDOWS_FORBIDDEN = frozenset('<>:"|?*')


class ContractValidationError(ValueError):
    """Raised when a provider-neutral contract fails closed validation."""


def _expect_fields(value: Mapping[str, Any], expected: set[str], *, where: str) -> None:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{where} must be an object")
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise ContractValidationError(f"unsupported {where} fields: {sorted(unknown)}")
    if missing:
        raise ContractValidationError(f"missing {where} fields: {sorted(missing)}")


def validate_repository_path(path: Any, *, field: str = "path") -> str:
    """Validate an already-normalized repository-relative POSIX path."""
    if not isinstance(path, str) or not path:
        raise ContractValidationError(f"{field} must be a non-empty string")
    try:
        validate_text(path, path=field)
    except JsonValueError as exc:
        raise ContractValidationError(str(exc)) from exc
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        raise ContractValidationError(f"{field} contains a forbidden control character")
    if path.startswith("/") or _DRIVE.match(path) or "\\" in path:
        raise ContractValidationError(f"{field} must be repository-relative POSIX")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractValidationError(f"{field} is not normalized")
    for part in parts:
        if any(character in _WINDOWS_FORBIDDEN for character in part):
            raise ContractValidationError(
                f"{field} contains a Windows-unsafe path character"
            )
        if part.endswith((".", " ")):
            raise ContractValidationError(
                f"{field} contains a Windows-aliased trailing dot or space"
            )
        device_name = part.split(".", 1)[0].casefold()
        if device_name in _WINDOWS_RESERVED or _WINDOWS_DEVICE.fullmatch(device_name):
            raise ContractValidationError(
                f"{field} contains a reserved Windows device name"
            )
    return path


def _path_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractValidationError(f"{field} must be an array")
    result = tuple(validate_repository_path(item, field=field) for item in value)
    if len({tuple(part.casefold() for part in path.split("/")) for path in result}) != len(result):
        raise ContractValidationError(f"{field} contains duplicate paths")
    return result


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(x, str) for x in value):
        raise ContractValidationError(f"{field} must be an array of strings")
    result = tuple(value)
    try:
        for index, item in enumerate(result):
            validate_text(item, path=f"{field}[{index}]")
    except JsonValueError as exc:
        raise ContractValidationError(str(exc)) from exc
    if len(set(result)) != len(result):
        raise ContractValidationError(f"{field} contains duplicates")
    return result


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
            raise ContractValidationError("task contract sha256 must be 64 lowercase hex characters")

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "revision": self.revision, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TaskContractIdentity":
        _expect_fields(value, {"path", "revision", "sha256"}, where="task_contract_identity")
        return cls(value["path"], value["revision"], value["sha256"])


@dataclass(frozen=True)
class WriteBoundaries:
    allowed_paths: tuple[str, ...]
    denied_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_paths",
            _path_tuple(self.allowed_paths, field="allowed_paths"),
        )
        object.__setattr__(
            self,
            "denied_paths",
            _path_tuple(self.denied_paths, field="denied_paths"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"allowed_paths": list(self.allowed_paths), "denied_paths": list(self.denied_paths)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WriteBoundaries":
        _expect_fields(value, {"allowed_paths", "denied_paths"}, where="write_boundaries")
        return cls(value["allowed_paths"], value["denied_paths"])


@dataclass(frozen=True)
class Budgets:
    turn_limit: int
    timeout_seconds: float
    token_limit: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.turn_limit, bool)
            or not isinstance(self.turn_limit, int)
            or not 1 <= self.turn_limit <= MAX_TURN_LIMIT
        ):
            raise ContractValidationError(f"turn_limit must be 1..{MAX_TURN_LIMIT}")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise ContractValidationError(
                f"timeout_seconds must be >0 and <= {MAX_TIMEOUT_SECONDS}"
            )
        if self.token_limit is not None and (
            isinstance(self.token_limit, bool)
            or not isinstance(self.token_limit, int)
            or not 1 <= self.token_limit <= MAX_TOKEN_LIMIT
        ):
            raise ContractValidationError(
                f"token_limit must be 1..{MAX_TOKEN_LIMIT} when supplied"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_limit": self.turn_limit,
            "timeout_seconds": self.timeout_seconds,
            "token_limit": self.token_limit,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Budgets":
        _expect_fields(value, {"turn_limit", "timeout_seconds", "token_limit"}, where="budgets")
        return cls(value["turn_limit"], value["timeout_seconds"], value["token_limit"])


@dataclass(frozen=True)
class AgentRequest:
    schema_version: str
    run_id: str
    task_id: str
    task_contract_identity: TaskContractIdentity
    role: str
    prompt: str
    context_paths: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    write_boundaries: WriteBoundaries
    output_schema: Mapping[str, Any]
    model_capability_class: str
    budgets: Budgets
    provider_configuration_key: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("unsupported AgentRequest schema_version")
        if not isinstance(self.run_id, str) or not _SLUG.fullmatch(self.run_id):
            raise ContractValidationError("run_id must be a lowercase ASCII slug of 1..64 characters")
        if not isinstance(self.task_id, str) or not _TASK_ID.fullmatch(self.task_id):
            raise ContractValidationError("task_id must match NSC-###")
        if type(self.task_contract_identity) is not TaskContractIdentity:
            raise ContractValidationError("task_contract_identity has the wrong type")
        expected_task_path = f"Tasks/{self.task_id}.yaml"
        if self.task_contract_identity.path != expected_task_path:
            raise ContractValidationError(
                f"task_contract_identity.path must equal {expected_task_path}"
            )
        if not isinstance(self.role, str) or not _IDENTIFIER.fullmatch(self.role):
            raise ContractValidationError("role must be a conservative identifier")
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ContractValidationError("prompt must be non-empty")
        try:
            validate_text(self.prompt, path="prompt")
        except JsonValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        object.__setattr__(
            self,
            "context_paths",
            _path_tuple(self.context_paths, field="context_paths"),
        )
        capabilities = _string_tuple(self.allowed_capabilities, field="allowed_capabilities")
        unknown = set(capabilities) - SUPPORTED_CAPABILITIES
        if unknown:
            raise ContractValidationError(f"unsupported capabilities: {sorted(unknown)}")
        object.__setattr__(self, "allowed_capabilities", capabilities)
        if type(self.write_boundaries) is not WriteBoundaries:
            raise ContractValidationError("write_boundaries has the wrong type")
        has_write = "repository_write" in capabilities
        if has_write and not self.write_boundaries.allowed_paths:
            raise ContractValidationError("repository_write requires at least one allowed path")
        if not has_write and (self.write_boundaries.allowed_paths or self.write_boundaries.denied_paths):
            raise ContractValidationError("write paths require repository_write")
        if type(self.output_schema) not in (dict, MappingProxyType):
            raise ContractValidationError("output_schema must be an exact JSON object")
        from .schema_validation import validate_schema

        try:
            schema_value = (
                thaw_json(self.output_schema)
                if isinstance(self.output_schema, MappingProxyType)
                else self.output_schema
            )
            frozen_schema = freeze_json(schema_value, path="$.output_schema")
        except JsonValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        try:
            validate_schema(frozen_schema)
        except Exception as exc:
            from .schema_validation import SchemaValidationError
            if isinstance(exc, SchemaValidationError):
                raise ContractValidationError(str(exc)) from exc
            raise
        object.__setattr__(self, "output_schema", frozen_schema)
        if self.model_capability_class not in MODEL_CAPABILITY_CLASSES:
            raise ContractValidationError("unknown model_capability_class")
        if type(self.budgets) is not Budgets:
            raise ContractValidationError("budgets has the wrong type")
        if (
            not isinstance(self.provider_configuration_key, str)
            or not _IDENTIFIER.fullmatch(self.provider_configuration_key)
        ):
            raise ContractValidationError(
                "provider_configuration_key must be a conservative identifier"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "task_contract_identity": TaskContractIdentity.to_dict(self.task_contract_identity),
            "role": self.role,
            "prompt": self.prompt,
            "context_paths": list(self.context_paths),
            "allowed_capabilities": list(self.allowed_capabilities),
            "write_boundaries": WriteBoundaries.to_dict(self.write_boundaries),
            "output_schema": thaw_json(self.output_schema),
            "model_capability_class": self.model_capability_class,
            "budgets": Budgets.to_dict(self.budgets),
            "provider_configuration_key": self.provider_configuration_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AgentRequest":
        fields = {
            "schema_version", "run_id", "task_id", "task_contract_identity",
            "role", "prompt", "context_paths", "allowed_capabilities",
            "write_boundaries", "output_schema", "model_capability_class",
            "budgets", "provider_configuration_key",
        }
        _expect_fields(value, fields, where="AgentRequest")
        return cls(
            value["schema_version"],
            value["run_id"],
            value["task_id"],
            TaskContractIdentity.from_dict(value["task_contract_identity"]),
            value["role"],
            value["prompt"],
            value["context_paths"],
            value["allowed_capabilities"],
            WriteBoundaries.from_dict(value["write_boundaries"]),
            value["output_schema"],
            value["model_capability_class"],
            Budgets.from_dict(value["budgets"]),
            value["provider_configuration_key"],
        )

    def is_path_writable(self, candidate: str) -> bool:
        try:
            path = validate_repository_path(candidate, field="candidate path")
        except ContractValidationError:
            return False
        if "repository_write" not in self.allowed_capabilities:
            return False
        parts = tuple(path.split("/"))
        folded_parts = tuple(part.casefold() for part in parts)

        def prefix(boundary: str) -> bool:
            boundary_parts = tuple(part.casefold() for part in boundary.split("/"))
            return folded_parts[:len(boundary_parts)] == boundary_parts
        if any(prefix(item) for item in self.write_boundaries.denied_paths):
            return False
        return any(prefix(item) for item in self.write_boundaries.allowed_paths)


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None

    def __post_init__(self) -> None:
        values = (self.input_tokens, self.output_tokens, self.total_tokens)
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
            raise ContractValidationError("token usage values must be non-negative integers")
        if self.estimated_cost_usd is not None and (
            isinstance(self.estimated_cost_usd, bool)
            or not isinstance(self.estimated_cost_usd, (int, float))
            or not math.isfinite(self.estimated_cost_usd)
            or self.estimated_cost_usd < 0
        ):
            raise ContractValidationError(
                "estimated_cost_usd must be finite and non-negative"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "total_tokens": self.total_tokens, "estimated_cost_usd": self.estimated_cost_usd}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Usage":
        _expect_fields(value, {"input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd"}, where="usage")
        return cls(value["input_tokens"], value["output_tokens"], value["total_tokens"], value["estimated_cost_usd"])


@dataclass(frozen=True)
class AgentResult:
    schema_version: str
    run_id: str
    provider: str | None
    model: str | None
    role: str
    status: str
    failure_classification: str
    failure_message: str | None
    structured_output: Any
    claimed_changed_paths: tuple[str, ...]
    duration_seconds: float
    usage: Usage | None
    raw_log_reference: str
    claims_execution_occurred: bool
    claimed_test_commands: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("unsupported AgentResult schema_version")
        if not isinstance(self.run_id, str) or not _SLUG.fullmatch(self.run_id):
            raise ContractValidationError("invalid result run_id")
        if not isinstance(self.role, str) or not _IDENTIFIER.fullmatch(self.role):
            raise ContractValidationError("invalid result role")
        if self.status not in RESULT_STATUSES or self.failure_classification not in FAILURE_CLASSIFICATIONS:
            raise ContractValidationError("unknown result status or failure classification")
        if (self.status == "succeeded") != (self.failure_classification == "none"):
            raise ContractValidationError("result status and failure classification disagree")
        if self.status == "succeeded":
            if not isinstance(self.provider, str) or not _IDENTIFIER.fullmatch(self.provider):
                raise ContractValidationError("succeeded result requires a valid provider")
            if (
                not isinstance(self.model, str)
                or not self.model
                or self.model != self.model.strip()
            ):
                raise ContractValidationError("succeeded result requires a valid model")
            if self.failure_message not in (None, ""):
                raise ContractValidationError(
                    "succeeded result cannot have a failure_message"
                )
        else:
            if (self.provider is None) != (self.model is None):
                raise ContractValidationError(
                    "failed result provider and model must both be set or both be null"
                )
            if self.provider is None and self.failure_classification != "invalid_request":
                raise ContractValidationError(
                    "provider and model may be null only for pre-invocation invalid_request"
                )
            if self.provider is not None and (
                not isinstance(self.provider, str)
                or not _IDENTIFIER.fullmatch(self.provider)
            ):
                raise ContractValidationError("invalid result provider")
            if self.model is not None and (
                not isinstance(self.model, str)
                or not self.model
                or self.model != self.model.strip()
            ):
                raise ContractValidationError("invalid result model")
            if not isinstance(self.failure_message, str) or not self.failure_message.strip():
                raise ContractValidationError(
                    "failed result requires a non-empty failure_message"
                )
        for field, value in (("failure_message", self.failure_message), ("model", self.model)):
            if value is not None:
                try:
                    validate_text(value, path=field)
                except JsonValueError as exc:
                    raise ContractValidationError(str(exc)) from exc
        if self.status == "failed" and self.structured_output is not None:
            raise ContractValidationError(
                "failed result must not retain rejected structured_output"
            )
        try:
            frozen_output = freeze_json(
                self.structured_output,
                path="$.structured_output",
            )
        except JsonValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        object.__setattr__(self, "structured_output", frozen_output)
        object.__setattr__(
            self,
            "claimed_changed_paths",
            _path_tuple(self.claimed_changed_paths, field="claimed_changed_paths"),
        )
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, (int, float))
            or not math.isfinite(self.duration_seconds)
            or self.duration_seconds < 0
        ):
            raise ContractValidationError(
                "duration_seconds must be finite and non-negative"
            )
        if self.usage is not None and type(self.usage) is not Usage:
            raise ContractValidationError("usage has the wrong type")
        validate_repository_path(self.raw_log_reference, field="raw_log_reference")
        if not isinstance(self.claims_execution_occurred, bool):
            raise ContractValidationError("claims_execution_occurred must be boolean")
        object.__setattr__(
            self,
            "claimed_test_commands",
            _string_tuple(
                self.claimed_test_commands,
                field="claimed_test_commands",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "provider": self.provider,
            "model": self.model,
            "role": self.role,
            "status": self.status,
            "failure_classification": self.failure_classification,
            "failure_message": self.failure_message,
            "structured_output": thaw_json(self.structured_output),
            "claimed_changed_paths": list(self.claimed_changed_paths),
            "duration_seconds": self.duration_seconds,
            "usage": None if self.usage is None else Usage.to_dict(self.usage),
            "raw_log_reference": self.raw_log_reference,
            "claims_execution_occurred": self.claims_execution_occurred,
            "claimed_test_commands": list(self.claimed_test_commands),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AgentResult":
        fields = {"schema_version", "run_id", "provider", "model", "role", "status", "failure_classification", "failure_message", "structured_output", "claimed_changed_paths", "duration_seconds", "usage", "raw_log_reference", "claims_execution_occurred", "claimed_test_commands"}
        _expect_fields(value, fields, where="AgentResult")
        usage = None if value["usage"] is None else Usage.from_dict(value["usage"])
        return cls(
            value["schema_version"], value["run_id"], value["provider"],
            value["model"], value["role"], value["status"],
            value["failure_classification"], value["failure_message"],
            value["structured_output"], value["claimed_changed_paths"],
            value["duration_seconds"], usage, value["raw_log_reference"],
            value["claims_execution_occurred"],
            value["claimed_test_commands"],
        )
