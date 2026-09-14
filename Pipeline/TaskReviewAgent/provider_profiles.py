"""Canonical immutable provider topology, shared by launchers and workers.

Only the composition root expands a profile. Downstream boundaries deserialize
the exact resolved value; they never rebuild it from ambient provider defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .provider_policy import ProviderPolicyError

PROFILE_DEFINITIONS = {
    "all-claude": ("claude", ("claude",), "claude_role_pair"),
    "all-codex": ("codex", ("codex",), "codex_role_pair"),
    "claude-architect-balanced": ("claude", ("claude", "codex"), "cross_provider_round_robin"),
    "codex-architect-balanced": ("codex", ("claude", "codex"), "cross_provider_round_robin"),
}
PROVIDER_PROFILES = tuple(PROFILE_DEFINITIONS)

# The Test Author is deliberately the crew's low-cost role.  Routing it at the
# task tier's full Codex reasoning effort made a tiny, already-covered test
# change spend almost six minutes surveying unrelated policy and repository
# context.  Keep deep tasks more rigorous than ordinary tasks, but do not let
# this bounded role inherit the Implementer/Validator effort wholesale.
_CODEX_TEST_AUTHOR_REASONING = {
    "none": "none",
    "minimal": "low",
    "low": "low",
    "medium": "low",
    "high": "low",
    "xhigh": "medium",
    "max": "medium",
}


@dataclass(frozen=True)
class ProviderTopology:
    schema_version: str
    profile: str
    architect: str
    provider_allowlist: tuple[str, ...]
    supervisor_policy: str
    implementation_policy: str
    validator_relationship: str
    lead_developer_relationship: str
    decomposition_strategy: str
    session_policy: str
    balance_metric: str
    token_budgets: tuple[tuple[str, int | None], ...]
    codex_resume_required: bool

    def __post_init__(self) -> None:
        if self.profile not in PROFILE_DEFINITIONS:
            raise ProviderPolicyError("unknown provider profile")
        architect, allowed, decomposition = PROFILE_DEFINITIONS[self.profile]
        mixed = len(allowed) == 2
        expected = dict(schema_version="1.0", architect=architect, provider_allowlist=allowed,
            supervisor_policy="follow_implementer" if mixed else architect,
            implementation_policy="token_balance" if mixed else architect,
            validator_relationship="opposite_implementer" if mixed else "same_provider_separate_role",
            lead_developer_relationship="opposite_implementer" if mixed else "same_provider_separate_role",
            decomposition_strategy=decomposition, session_policy="pooled_separate_roles",
            balance_metric="consumed_total_tokens/configured_token_budget",
            codex_resume_required="codex" in allowed)
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ProviderPolicyError("resolved provider topology differs from its canonical profile")
        if type(self.codex_resume_required) is not bool or type(self.provider_allowlist) is not tuple:
            raise ProviderPolicyError("topology has noncanonical field types")
        if type(self.token_budgets) is not tuple:
            raise ProviderPolicyError("token budgets must be immutable pairs")
        for pair in self.token_budgets:
            if type(pair) is not tuple or len(pair) != 2:
                raise ProviderPolicyError("token budgets must be immutable pairs")
            budget = pair[1]
            if budget is not None and (type(budget) is not int or budget <= 0):
                raise ProviderPolicyError("configured token budgets must be positive integers or unavailable")
        if tuple(p for p, _ in self.token_budgets) != allowed:
            raise ProviderPolicyError("token budgets must name exactly the permitted providers")

    @property
    def mixed(self) -> bool:
        return self.implementation_policy == "token_balance"

    def supervisor_for(self, implementer: str) -> str:
        self.require_provider(implementer)
        return implementer if self.mixed else self.architect

    def reviewer_for(self, implementer: str) -> str:
        self.require_provider(implementer)
        return ("codex" if implementer == "claude" else "claude") if self.mixed else implementer

    def require_provider(self, provider: str) -> None:
        if provider not in self.provider_allowlist:
            raise ProviderPolicyError(f"provider {provider!r} escapes resolved topology")

    def to_dict(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["provider_allowlist"] = list(self.provider_allowlist)
        result["token_budgets"] = dict(self.token_budgets)
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderTopology":
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ProviderPolicyError("resolved provider topology fields differ from schema")
        if type(value["provider_allowlist"]) is not list or type(value["token_budgets"]) is not dict:
            raise ProviderPolicyError("resolved allowlist/budgets have invalid types")
        data = dict(value)
        data["provider_allowlist"] = tuple(data["provider_allowlist"])
        data["token_budgets"] = tuple(sorted(data["token_budgets"].items()))
        return cls(**data)

    @classmethod
    def from_json(cls, value: str) -> "ProviderTopology":
        return cls.from_dict(json.loads(value))


def expand_profile(profile: str, *, token_budgets: Mapping[str, int] | None = None) -> ProviderTopology:
    if profile not in PROFILE_DEFINITIONS:
        raise ProviderPolicyError("provider profile must be one of " + ", ".join(PROVIDER_PROFILES))
    architect, allowed, decomposition = PROFILE_DEFINITIONS[profile]
    budgets = dict(token_budgets or {})
    if set(budgets) - set(allowed):
        raise ProviderPolicyError("token budget names a provider outside the profile")
    mixed = len(allowed) == 2
    return ProviderTopology("1.0", profile, architect, allowed,
        "follow_implementer" if mixed else architect, "token_balance" if mixed else architect,
        "opposite_implementer" if mixed else "same_provider_separate_role",
        "opposite_implementer" if mixed else "same_provider_separate_role", decomposition,
        "pooled_separate_roles", "consumed_total_tokens/configured_token_budget",
        tuple((provider, budgets.get(provider)) for provider in allowed), "codex" in allowed)


def validate_legacy_agreement(topology: ProviderTopology, *, execution_provider=None,
                              architect_provider=None, supervisor_provider=None, provider_allowlist=None,
                              execution_model=None, architect_model=None) -> None:
    expected = dict(execution_provider=None if topology.mixed else topology.architect,
        architect_provider=topology.architect,
        supervisor_provider=None if topology.mixed else topology.architect,
        provider_allowlist=topology.provider_allowlist)
    supplied = dict(execution_provider=execution_provider, architect_provider=architect_provider,
        supervisor_provider=supervisor_provider, provider_allowlist=provider_allowlist)
    for field, value in supplied.items():
        if value is not None and value != expected[field]:
            raise ProviderPolicyError(f"explicit {field} contradicts provider profile {topology.profile}")
    for model, provider in ((architect_model, topology.architect),
                            (execution_model, None if topology.mixed else topology.architect)):
        if model is not None and (provider is None or
                (provider == "claude") != model.casefold().startswith("claude-")):
            raise ProviderPolicyError("explicit model contradicts the profile's provider selection")


def preflight_topology(topology: ProviderTopology) -> None:
    if topology.codex_resume_required:
        from .supervisor_session_pool import codex_resume_activation_from_environment
        if codex_resume_activation_from_environment() is None:
            raise ProviderPolicyError("profile requires operator-verified NSC_CODEX_RESUME_SANDBOX_ARGUMENT before paid work")


def profile_runtime_binding(topology: ProviderTopology, compose_project: str) -> dict:
    preflight_topology(topology)
    control = None
    if topology.codex_resume_required:
        from .supervisor_session_pool import codex_resume_activation_from_environment
        control = list(codex_resume_activation_from_environment().argument)
    return dict(conversation_stores=[f"compose:{compose_project}/{p}-config" for p in topology.provider_allowlist],
                codex_resume_control=control)


def routing_table(topology: ProviderTopology) -> dict[str, Any]:
    return dict(profile=topology.profile, architect=topology.architect,
        supervisor_policy=topology.supervisor_policy, implementation_policy=topology.implementation_policy,
        validator=topology.validator_relationship, lead_developer=topology.lead_developer_relationship,
        decomposition=topology.decomposition_strategy, provider_allowlist=list(topology.provider_allowlist),
        token_balance_metric=topology.balance_metric,
        credentials=[f"nosafecircle_{provider}-config" for provider in topology.provider_allowlist],
        sessions=topology.session_policy,
        codex_resume_control="operator_verified_required" if topology.codex_resume_required else "not_resolved")


def crew_role_routes(topology: ProviderTopology, implementer: str, tier) -> dict[str, dict]:
    """Host policy selects every role; model output can never supply this map."""
    topology.require_provider(implementer)
    result = {}
    for role in ("implementer", "test_author", "validator", "lead_developer"):
        provider = implementer if role in ("implementer", "test_author") else topology.reviewer_for(implementer)
        if provider not in tier.allowed_execution_providers:
            raise ProviderPolicyError("required independent role provider is unavailable under tier safety policy")
        reasoning_effort = tier.openai_reasoning_effort if provider == "codex" else None
        if provider == "codex" and role == "test_author":
            reasoning_effort = _CODEX_TEST_AUTHOR_REASONING[reasoning_effort]
        result[role] = dict(provider=provider,
            model=tier.claude_model if provider == "claude" else tier.openai_model,
            reasoning_effort=reasoning_effort)
    validate_crew_routes(topology, implementer, result)
    return result


def validate_crew_routes(topology: ProviderTopology, implementer: str, routes: dict) -> None:
    roles = {"implementer", "test_author", "validator", "lead_developer"}
    if type(routes) is not dict or set(routes) != roles:
        raise ProviderPolicyError("profile crew routes must name exactly the four policy roles")
    for role, route in routes.items():
        expected = implementer if role in ("implementer", "test_author") else topology.reviewer_for(implementer)
        if type(route) is not dict or set(route) != {"provider", "model", "reasoning_effort"}:
            raise ProviderPolicyError("profile role route has invalid fields")
        if route["provider"] != expected:
            raise ProviderPolicyError("crew role provider differs from immutable profile")
        model = route["model"]
        if type(model) is not str or not model or len(model) > 200 or (expected == "claude") != model.startswith("claude-"):
            raise ProviderPolicyError("crew role model differs from its provider")
        from .execution_routing import OPENAI_REASONING_EFFORTS
        if (expected == "claude" and route["reasoning_effort"] is not None) or (expected == "codex" and route["reasoning_effort"] not in OPENAI_REASONING_EFFORTS):
            raise ProviderPolicyError("crew role reasoning differs from its provider")
