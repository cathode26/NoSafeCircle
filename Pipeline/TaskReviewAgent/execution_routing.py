#!/usr/bin/env python3
"""Deterministic execution routing for architect capability recommendations.

The architect may recommend a bounded capability tier and provider preference.
Only this operator-controlled policy selects executable provider identifiers,
model identifiers, reasoning effort, and supervisor turn budgets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


CAPABILITY_TIERS = ("fast", "standard", "deep")
PROVIDER_PREFERENCES = ("openai", "claude", "no_preference")
EXECUTION_PROVIDERS = ("claude", "codex")
OPENAI_REASONING_EFFORTS = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
MAX_RECOMMENDATION_RATIONALE_CHARACTERS = 1200
MAX_MODEL_IDENTIFIER_CHARACTERS = 200
MIN_SUPERVISOR_TURNS = 4
MAX_SUPERVISOR_TURNS = 160

_TIER_DEFAULTS = {
    "fast": {"reasoning": "medium", "max_turns": 40},
    "standard": {"reasoning": "high", "max_turns": 80},
    "deep": {"reasoning": "xhigh", "max_turns": 120},
}
_DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
_DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"


class ExecutionRoutingError(ValueError):
    """A recommendation or deterministic routing policy is unusable."""


def _bounded_text(value: object, *, field: str, maximum: int) -> str:
    if type(value) is not str or not value.strip():
        raise ExecutionRoutingError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > maximum:
        raise ExecutionRoutingError(
            f"{field} must be at most {maximum} characters"
        )
    if any(character in text for character in ("\r", "\n", "\x00")):
        raise ExecutionRoutingError(f"{field} must be a single safe text value")
    return text


def _preference_to_execution_provider(value: str) -> str:
    if value == "openai":
        return "codex"
    if value == "claude":
        return "claude"
    raise ExecutionRoutingError(f"unsupported provider name: {value!r}")


def _execution_provider_to_preference(value: str) -> str:
    if value == "codex":
        return "openai"
    if value == "claude":
        return "claude"
    raise ExecutionRoutingError(f"unsupported execution provider: {value!r}")


@dataclass(frozen=True)
class ExecutionRecommendation:
    capability_tier: str
    provider_preference: str
    rationale: str

    def __post_init__(self) -> None:
        if self.capability_tier not in CAPABILITY_TIERS:
            raise ExecutionRoutingError(
                f"unsupported capability_tier: {self.capability_tier!r}"
            )
        if self.provider_preference not in PROVIDER_PREFERENCES:
            raise ExecutionRoutingError(
                f"unsupported provider_preference: {self.provider_preference!r}"
            )
        object.__setattr__(
            self,
            "rationale",
            _bounded_text(
                self.rationale,
                field="execution_recommendation.rationale",
                maximum=MAX_RECOMMENDATION_RATIONALE_CHARACTERS,
            ),
        )

    @classmethod
    def from_dict(cls, value: object) -> "ExecutionRecommendation":
        if not isinstance(value, Mapping):
            raise ExecutionRoutingError("execution_recommendation must be an object")
        expected = {"capability_tier", "provider_preference", "rationale"}
        supplied = set(value)
        if supplied != expected:
            raise ExecutionRoutingError(
                "execution_recommendation fields must be exactly "
                f"{sorted(expected)}; received {sorted(supplied)}"
            )
        return cls(
            capability_tier=value["capability_tier"],
            provider_preference=value["provider_preference"],
            rationale=value["rationale"],
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "capability_tier": self.capability_tier,
            "provider_preference": self.provider_preference,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class TierExecutionRoutingPolicy:
    default_execution_provider: str
    allowed_execution_providers: frozenset[str]
    claude_model: str
    openai_model: str
    openai_reasoning_effort: str
    supervisor_model: str
    supervisor_reasoning_effort: str
    max_supervisor_turns: int

    def __post_init__(self) -> None:
        if self.default_execution_provider not in EXECUTION_PROVIDERS:
            raise ExecutionRoutingError(
                "default execution provider must be claude or codex"
            )
        allowed = frozenset(self.allowed_execution_providers)
        if not allowed or not allowed.issubset(EXECUTION_PROVIDERS):
            raise ExecutionRoutingError(
                "allowed execution providers must be a non-empty subset of claude,codex"
            )
        object.__setattr__(self, "allowed_execution_providers", allowed)
        if self.default_execution_provider not in allowed:
            raise ExecutionRoutingError(
                "default execution provider must be included in allowed providers"
            )
        for field in ("claude_model", "openai_model", "supervisor_model"):
            object.__setattr__(
                self,
                field,
                _bounded_text(
                    getattr(self, field),
                    field=field,
                    maximum=MAX_MODEL_IDENTIFIER_CHARACTERS,
                ),
            )
        for field in ("openai_reasoning_effort", "supervisor_reasoning_effort"):
            effort = getattr(self, field)
            if effort not in OPENAI_REASONING_EFFORTS:
                raise ExecutionRoutingError(
                    f"{field} must use a supported OpenAI reasoning effort"
                )
        turns = self.max_supervisor_turns
        if (
            isinstance(turns, bool)
            or not isinstance(turns, int)
            or not MIN_SUPERVISOR_TURNS <= turns <= MAX_SUPERVISOR_TURNS
        ):
            raise ExecutionRoutingError(
                f"max_supervisor_turns must be from {MIN_SUPERVISOR_TURNS} "
                f"through {MAX_SUPERVISOR_TURNS}"
            )


@dataclass(frozen=True)
class ExecutionRoutingPolicy:
    fast: TierExecutionRoutingPolicy
    standard: TierExecutionRoutingPolicy
    deep: TierExecutionRoutingPolicy

    def __post_init__(self) -> None:
        for tier in CAPABILITY_TIERS:
            if not isinstance(getattr(self, tier), TierExecutionRoutingPolicy):
                raise ExecutionRoutingError(
                    f"{tier} must be a TierExecutionRoutingPolicy"
                )

    def for_tier(self, capability_tier: str) -> TierExecutionRoutingPolicy:
        if capability_tier not in CAPABILITY_TIERS:
            raise ExecutionRoutingError(
                f"unsupported capability_tier: {capability_tier!r}"
            )
        return getattr(self, capability_tier)


@dataclass(frozen=True)
class ResolvedExecutionRoute:
    capability_tier: str
    provider_preference: str
    preference_honored: bool
    execution_provider: str
    execution_model: str
    execution_reasoning_effort: str | None
    supervisor_model: str
    supervisor_reasoning_effort: str
    max_supervisor_turns: int
    route_reason: str

    def to_event_dict(self) -> dict[str, object]:
        return {
            "capability_tier": self.capability_tier,
            "provider_preference": self.provider_preference,
            "preference_honored": self.preference_honored,
            "execution_provider": self.execution_provider,
            "execution_model": self.execution_model,
            "execution_reasoning_effort": self.execution_reasoning_effort,
            "supervisor_model": self.supervisor_model,
            "supervisor_reasoning_effort": self.supervisor_reasoning_effort,
            "max_turns": self.max_supervisor_turns,
            "route_reason": self.route_reason,
        }


def resolve_execution_route(
    recommendation: ExecutionRecommendation,
    policy: ExecutionRoutingPolicy,
) -> ResolvedExecutionRoute:
    if not isinstance(recommendation, ExecutionRecommendation):
        raise ExecutionRoutingError(
            "recommendation must be an ExecutionRecommendation"
        )
    if not isinstance(policy, ExecutionRoutingPolicy):
        raise ExecutionRoutingError("policy must be an ExecutionRoutingPolicy")
    tier = policy.for_tier(recommendation.capability_tier)
    if recommendation.provider_preference == "no_preference":
        provider = tier.default_execution_provider
        preference_honored = True
        reason = "no_preference_used_tier_default"
    else:
        preferred = _preference_to_execution_provider(
            recommendation.provider_preference
        )
        if preferred in tier.allowed_execution_providers:
            provider = preferred
            preference_honored = True
            reason = "architect_preference_allowed"
        else:
            provider = tier.default_execution_provider
            preference_honored = False
            reason = "architect_preference_unavailable_used_tier_default"
    if provider not in tier.allowed_execution_providers:
        raise ExecutionRoutingError(
            "resolved execution provider is not allowed by the tier policy"
        )
    return ResolvedExecutionRoute(
        capability_tier=recommendation.capability_tier,
        provider_preference=recommendation.provider_preference,
        preference_honored=preference_honored,
        execution_provider=provider,
        execution_model=(
            tier.claude_model if provider == "claude" else tier.openai_model
        ),
        execution_reasoning_effort=(
            tier.openai_reasoning_effort if provider == "codex" else None
        ),
        supervisor_model=tier.supervisor_model,
        supervisor_reasoning_effort=tier.supervisor_reasoning_effort,
        max_supervisor_turns=tier.max_supervisor_turns,
        route_reason=reason,
    )


def _environment_text(
    environment: Mapping[str, str],
    name: str,
    fallback: str,
) -> str:
    value = environment.get(name)
    return _bounded_text(
        fallback if value is None else value,
        field=name,
        maximum=MAX_MODEL_IDENTIFIER_CHARACTERS,
    )


def _allowed_providers(environment: Mapping[str, str], name: str) -> frozenset[str]:
    raw = environment.get(name, "openai,claude")
    if type(raw) is not str:
        raise ExecutionRoutingError(f"{name} must be text")
    values = [item.strip().casefold() for item in raw.split(",")]
    if not values or any(not item for item in values) or len(set(values)) != len(values):
        raise ExecutionRoutingError(
            f"{name} must contain unique comma-separated openai/claude values"
        )
    if any(item not in {"openai", "claude"} for item in values):
        raise ExecutionRoutingError(
            f"{name} must contain only openai and claude"
        )
    return frozenset(_preference_to_execution_provider(item) for item in values)


def _turns(environment: Mapping[str, str], name: str, fallback: int) -> int:
    raw = environment.get(name)
    if raw is None:
        return fallback
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ExecutionRoutingError(f"{name} must be an integer") from exc
    return value


def load_execution_routing_policy(
    environment: Mapping[str, str] | None = None,
    *,
    default_provider_override: str | None = None,
    supervisor_model_override: str | None = None,
    max_turns_override: int | None = None,
) -> ExecutionRoutingPolicy:
    """Load and validate all operational routing inputs as one frozen policy.

    Existing polling CLI options can override the tier default provider,
    supervisor model, or turn budget for operator compatibility. ExecutionCrew
    models remain independent and always come from the routing environment or
    the current provider defaults.
    """

    env = os.environ if environment is None else environment
    fallback_claude_model = env.get("NSC_CLAUDE_MODEL") or _DEFAULT_CLAUDE_MODEL
    fallback_openai_model = env.get("NSC_OPENAI_CODEX_MODEL") or _DEFAULT_OPENAI_MODEL
    fallback_supervisor_model = (
        env.get("NSC_TASK_SUPERVISOR_MODEL") or fallback_openai_model
    )
    override_provider: str | None = None
    if default_provider_override is not None:
        value = str(default_provider_override).strip().casefold()
        override_provider = (
            value if value in PROVIDER_PREFERENCES[:2] else _execution_provider_to_preference(value)
        )
    if max_turns_override is not None and (
        isinstance(max_turns_override, bool) or not isinstance(max_turns_override, int)
    ):
        raise ExecutionRoutingError("max_turns_override must be an integer")

    tiers: dict[str, TierExecutionRoutingPolicy] = {}
    for tier_name in CAPABILITY_TIERS:
        prefix = f"NSC_ROUTE_{tier_name.upper()}"
        defaults = _TIER_DEFAULTS[tier_name]
        default_name = override_provider or str(
            env.get(f"{prefix}_DEFAULT_PROVIDER", "claude")
        ).strip().casefold()
        if default_name not in {"openai", "claude"}:
            raise ExecutionRoutingError(
                f"{prefix}_DEFAULT_PROVIDER must be openai or claude"
            )
        reasoning = str(
            env.get(f"{prefix}_OPENAI_REASONING_EFFORT", defaults["reasoning"])
        ).strip().casefold()
        supervisor_reasoning = str(
            env.get(f"{prefix}_SUPERVISOR_REASONING_EFFORT", defaults["reasoning"])
        ).strip().casefold()
        tier_policy = TierExecutionRoutingPolicy(
            default_execution_provider=_preference_to_execution_provider(default_name),
            allowed_execution_providers=_allowed_providers(
                env, f"{prefix}_ALLOWED_PROVIDERS"
            ),
            claude_model=_environment_text(
                env, f"{prefix}_CLAUDE_MODEL", fallback_claude_model
            ),
            openai_model=_environment_text(
                env, f"{prefix}_OPENAI_MODEL", fallback_openai_model
            ),
            openai_reasoning_effort=reasoning,
            supervisor_model=(
                _bounded_text(
                    supervisor_model_override,
                    field="supervisor_model_override",
                    maximum=MAX_MODEL_IDENTIFIER_CHARACTERS,
                )
                if supervisor_model_override is not None
                else _environment_text(
                    env, f"{prefix}_SUPERVISOR_MODEL", fallback_supervisor_model
                )
            ),
            supervisor_reasoning_effort=supervisor_reasoning,
            max_supervisor_turns=(
                max_turns_override
                if max_turns_override is not None
                else _turns(env, f"{prefix}_MAX_TURNS", int(defaults["max_turns"]))
            ),
        )
        tiers[tier_name] = tier_policy
    return ExecutionRoutingPolicy(
        fast=tiers["fast"],
        standard=tiers["standard"],
        deep=tiers["deep"],
    )


__all__ = [
    "CAPABILITY_TIERS",
    "EXECUTION_PROVIDERS",
    "ExecutionRecommendation",
    "ExecutionRoutingError",
    "ExecutionRoutingPolicy",
    "MAX_RECOMMENDATION_RATIONALE_CHARACTERS",
    "OPENAI_REASONING_EFFORTS",
    "PROVIDER_PREFERENCES",
    "ResolvedExecutionRoute",
    "TierExecutionRoutingPolicy",
    "load_execution_routing_policy",
    "resolve_execution_route",
]
