"""Deterministic, side-effect-free provider for contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import AgentRequest, Usage
from .base import (
    ProviderBudgetExhausted,
    ProviderFailure,
    ProviderInvocationResponse,
    ProviderPermissionDenied,
    ProviderTimeout,
)

@dataclass(frozen=True)
class FakeProvider:
    scenario: str = "success"
    structured_output: Any = None
    raw_log: str = "fake provider log\n"
    claimed_changed_paths: Any = ()
    claimed_test_commands: Any = ()
    claims_execution_occurred: Any = False
    usage: Any = None

    @property
    def provider_identifier(self) -> str:
        return "fake"

    def invoke(self, request: AgentRequest, model: str) -> ProviderInvocationResponse:
        errors = {
            "provider_error": ProviderFailure,
            "timeout": ProviderTimeout,
            "permission_denied": ProviderPermissionDenied,
            "budget_exhausted": ProviderBudgetExhausted,
        }
        if self.scenario in errors:
            raise errors[self.scenario](self.scenario, raw_log=self.raw_log)
        if self.scenario == "value_error":
            raise ValueError("fake provider value error")
        if self.scenario == "keyboard_interrupt":
            raise KeyboardInterrupt("fake provider interrupt")
        if self.scenario == "malformed_structured_output":
            output = {"unexpected": True}
        elif self.scenario == "success":
            output = self.structured_output
        else:
            raise ProviderFailure("unknown fake scenario", raw_log=self.raw_log)
        usage = self.usage if self.usage is not None else Usage(1, 1, 2)
        return ProviderInvocationResponse(
            output,
            self.raw_log,
            self.claimed_changed_paths,
            usage,
            self.claims_execution_occurred,
            self.claimed_test_commands,
        )
