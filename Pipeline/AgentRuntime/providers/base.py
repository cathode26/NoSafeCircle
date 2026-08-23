"""Provider adapter boundary. Adapters cannot establish repository authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..contracts import AgentInvocationRequest, Usage

@dataclass(frozen=True)
class ProviderInvocationResponse:
    structured_output: Any
    raw_log: str
    claimed_changed_paths: tuple[str, ...] = ()
    usage: Usage | None = None
    claims_execution_occurred: bool = False
    claimed_test_commands: tuple[str, ...] = ()

class ProviderInvocationError(RuntimeError):
    def __init__(self, message: str, *, raw_log: str = "") -> None:
        super().__init__(message)
        self.raw_log = raw_log


class ProviderOutputInvalid(ProviderInvocationError):
    pass


class ProviderTransportError(ProviderInvocationError):
    """Local provider transport or transcript processing failed."""


class ProviderRequestRejected(ProviderInvocationError):
    """The selected provider cannot safely honor the requested policy."""


class ProviderFailure(ProviderInvocationError):
    pass


class ProviderTimeout(ProviderInvocationError):
    pass


class ProviderPermissionDenied(ProviderInvocationError):
    pass


class ProviderBudgetExhausted(ProviderInvocationError):
    pass

class AgentProvider(Protocol):
    @property
    def provider_identifier(self) -> str:
        ...

    def invoke(
        self,
        request: AgentInvocationRequest,
        model: str,
    ) -> ProviderInvocationResponse:
        ...
