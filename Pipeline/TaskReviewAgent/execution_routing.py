#!/usr/bin/env python3
"""Deterministic execution routing for architect capability recommendations.

The architect may recommend a bounded capability tier and provider preference.
Only this operator-controlled policy selects executable provider identifiers,
model identifiers, reasoning effort, and supervisor turn budgets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

from Pipeline.TaskReviewAgent.provider_policy import provider_allowlist as validate_provider_allowlist


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

CREW_PROFILES = ("lean", "standard", "full")
VALIDATION_PROFILES = ("targeted", "task_specific", "full_relevant")
HUMAN_VERIFICATION_POLICIES = ("required", "machine_evidence_permitted")
RIGOR_PROFILE_BY_TIER = {
    "fast": ("lean", "targeted"),
    "standard": ("standard", "task_specific"),
    "deep": ("full", "full_relevant"),
}

_TIER_RANK = {"fast": 0, "standard": 1, "deep": 2}
_FULL_RIGOR_ROOTS = (
    ".github/",
    "packages/",
    "pipeline/",
    "projectsettings/",
)
_FULL_RIGOR_NAMES = {
    "agents.md",
    "compose.yaml",
    "dockerfile",
}
_FULL_RIGOR_SUFFIXES = {
    ".anim",
    ".asmdef",
    ".asset",
    ".controller",
    ".inputactions",
    ".mat",
    ".physicsmaterial2d",
    ".playable",
    ".prefab",
    ".rendertexture",
    ".unity",
}
_FAST_SURFACE_SUFFIXES = {".cs", ".md", ".meta"}
# A Unity `.meta` file is import metadata, not serialized content -- but only in
# one exact shape. ExecutionCrew generates `<script>.cs.meta` for an approved new
# C# file under `Assets/`, and that sidecar carries nothing but a schema version
# and a deterministic GUID. Every other `.meta` stays substantive.
_UNITY_ASSET_ROOT = "assets/"
_SCRIPT_IMPORT_COMPANION_SUFFIX = ".cs.meta"
_META_SUFFIX = ".meta"

_TIER_DEFAULTS = {
    "fast": {"reasoning": "medium", "max_turns": 40},
    "standard": {"reasoning": "high", "max_turns": 80},
    "deep": {"reasoning": "xhigh", "max_turns": 120},
}
_DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
_DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"


class ExecutionRoutingError(ValueError):
    """A recommendation or deterministic routing policy is unusable."""


@dataclass(frozen=True)
class TaskRigorDecision:
    """Policy-owned minimum rigor applied to one architect recommendation.

    The architect chooses a requested capability tier. Repository facts may
    only preserve or raise that tier. They also select the executable crew,
    validation, and human-verification policies; free-form architect text can
    never name or waive one of these controls.

    ``reasons`` is the complete narrative. ``override_reasons`` is the subset
    whose policy floors actually exceed the architect's requested tier, plus
    the resulting escalation summary.  It is empty whenever the architect's
    recommendation is honored, even when repository facts establish a lower
    minimum tier.
    """

    architect_capability_tier: str
    minimum_capability_tier: str
    effective_capability_tier: str
    crew_profile: str
    validation_profile: str
    human_verification_policy: str
    reasons: tuple[str, ...]
    override_reasons: tuple[str, ...] = ()

    @property
    def architect_recommendation_honored(self) -> bool:
        """Whether the effective tier is exactly the tier the architect asked for."""

        return self.effective_capability_tier == self.architect_capability_tier

    def __post_init__(self) -> None:
        for field in (
            "architect_capability_tier",
            "minimum_capability_tier",
            "effective_capability_tier",
        ):
            if getattr(self, field) not in CAPABILITY_TIERS:
                raise ExecutionRoutingError(f"{field} must be a capability tier")
        if self.crew_profile not in CREW_PROFILES:
            raise ExecutionRoutingError("crew_profile is unsupported")
        if self.validation_profile not in VALIDATION_PROFILES:
            raise ExecutionRoutingError("validation_profile is unsupported")
        if self.human_verification_policy not in HUMAN_VERIFICATION_POLICIES:
            raise ExecutionRoutingError("human_verification_policy is unsupported")
        if not self.reasons or any(
            type(item) is not str or not item for item in self.reasons
        ):
            raise ExecutionRoutingError("rigor decision requires non-empty reasons")
        if any(
            type(item) is not str or not item for item in self.override_reasons
        ):
            raise ExecutionRoutingError("override reasons must be non-empty strings")
        if not set(self.override_reasons).issubset(self.reasons):
            raise ExecutionRoutingError(
                "every override reason must also appear in the full reason list"
            )
        if bool(self.override_reasons) and self.architect_recommendation_honored:
            raise ExecutionRoutingError(
                "an honored architect recommendation cannot report deterministic overrides"
            )
        if not self.architect_recommendation_honored and not self.override_reasons:
            raise ExecutionRoutingError(
                "an overruled architect recommendation requires deterministic override reasons"
            )

    def to_event_dict(self) -> dict[str, object]:
        return {
            "architect_capability_tier": self.architect_capability_tier,
            "minimum_capability_tier": self.minimum_capability_tier,
            "capability_tier": self.effective_capability_tier,
            "crew_profile": self.crew_profile,
            "validation_profile": self.validation_profile,
            "human_verification_policy": self.human_verification_policy,
            "architect_recommendation_honored": self.architect_recommendation_honored,
            "rigor_reasons": list(self.reasons),
            "rigor_override_reasons": list(self.override_reasons),
        }


def _surface_values(surface: object, field: str) -> tuple[str, ...]:
    value = getattr(surface, field, ())
    if not isinstance(value, (list, tuple)):
        raise ExecutionRoutingError(
            f"predicted_change_surface.{field} must be an array"
        )
    return tuple(str(item) for item in value)


def _normalized_surface_path(value: str) -> str:
    """Return the comparison form used by every path rule in this policy."""

    path = str(value).replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.casefold()


def _casefold_unique_paths(values: tuple[str, ...]) -> tuple[str, ...]:
    """Deduplicate path spellings under the policy's case-insensitive rules."""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalized_surface_path(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return tuple(result)


def _already_committed(
    probe: "Callable[[str], bool] | None",
    path: str,
) -> bool:
    """Report whether the committed source already contains this exact path.

    Without a probe, or when the probe cannot answer, the path is reported as
    already committed. Newness must be proven; an unprovable sidecar therefore
    keeps full rigor instead of silently qualifying for the lean exemption.
    """

    if probe is None:
        return True
    try:
        return bool(probe(path))
    except (OSError, RuntimeError, ValueError):
        return True


def _classify_serialized_surface(
    serialized: tuple[str, ...],
    exact_paths: tuple[str, ...],
    probe: "Callable[[str], bool] | None",
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split declared Unity serialized assets into import companions and content.

    A path is a non-substantive import companion only when every one of these
    holds: it is `<script>.cs.meta`, it lives under `Assets/`, its exact
    `<script>.cs` is part of the same bounded change, and it does not already
    exist in the committed source. That is precisely the sidecar ExecutionCrew
    generates for one approved new C# file.

    Everything else stays substantive and keeps the full profile: scenes,
    prefabs, `.asset` files, a `.meta` for any other asset type, an orphaned
    `.meta` whose script is not in the change, and an edit to an existing
    sidecar -- rewriting one changes a GUID that other assets reference.
    """

    scripts = {
        _normalized_surface_path(path)
        for path in exact_paths
        if _normalized_surface_path(path).endswith(".cs")
    }
    companions: list[str] = []
    substantive: list[str] = []
    for raw in serialized:
        path = _normalized_surface_path(raw)
        script = (
            path[: -len(_META_SUFFIX)]
            if path.endswith(_SCRIPT_IMPORT_COMPANION_SUFFIX)
            else None
        )
        if (
            script is not None
            and path.startswith(_UNITY_ASSET_ROOT)
            and script in scripts
            and not _already_committed(probe, raw)
        ):
            companions.append(raw)
        else:
            substantive.append(raw)
    return tuple(companions), tuple(substantive)


def _resource_paths(task: Mapping[str, Any]) -> tuple[str, ...]:
    resources = task.get("exclusive_resources") or ()
    if not isinstance(resources, (list, tuple)):
        raise ExecutionRoutingError("task exclusive_resources must be an array")
    paths: list[str] = []
    for item in resources:
        if type(item) is not str:
            continue
        folded = item.casefold()
        for prefix in ("repo-file:", "unity-scene:"):
            if folded.startswith(prefix):
                paths.append(item[len(prefix) :])
                break
    return tuple(paths)


def _has_logical_resource(task: Mapping[str, Any]) -> bool:
    resources = task.get("exclusive_resources") or ()
    if not isinstance(resources, (list, tuple)):
        raise ExecutionRoutingError("task exclusive_resources must be an array")
    return any(
        type(item) is str and item.casefold().startswith("logical:")
        for item in resources
    )


def resolve_task_rigor(
    recommendation: "ExecutionRecommendation",
    *,
    task: Mapping[str, Any],
    predicted_change_surface: object,
    committed_path_probe: "Callable[[str], bool] | None" = None,
) -> TaskRigorDecision:
    """Resolve architect judgment against deterministic minimum safeguards.

    ``committed_path_probe`` answers "does this exact path already exist in the
    committed source". It is required only to prove that a `<script>.cs.meta`
    sidecar is new; omitting it keeps the historical behavior of treating every
    declared Unity serialized asset as substantive.
    """

    if not isinstance(recommendation, ExecutionRecommendation):
        raise ExecutionRoutingError(
            "recommendation must be an ExecutionRecommendation"
        )
    if not isinstance(task, Mapping):
        raise ExecutionRoutingError("task must be an object")

    exact_paths = _casefold_unique_paths(
        (
            *_surface_values(predicted_change_surface, "exact_paths"),
            *_surface_values(predicted_change_surface, "unity_serialized_assets"),
            *_resource_paths(task),
        )
    )
    patterns = _surface_values(predicted_change_surface, "path_patterns")
    declared_serialized = _surface_values(
        predicted_change_surface, "unity_serialized_assets"
    )
    shared_systems = _surface_values(predicted_change_surface, "shared_systems")
    symbols_or_components = _surface_values(
        predicted_change_surface, "symbols_or_components"
    )
    serialized = _casefold_unique_paths(
        (
            *declared_serialized,
            *(
                path
                for path in exact_paths
                if _normalized_surface_path(path).endswith(_META_SUFFIX)
            ),
        )
    )

    minimum = "fast"
    reasons: list[str] = []
    floor_reasons: list[tuple[str, str]] = []

    def raise_floor(tier: str, reason: str) -> None:
        nonlocal minimum
        if _TIER_RANK[tier] > _TIER_RANK[minimum]:
            minimum = tier
        reasons.append(reason)
        floor_reasons.append((tier, reason))

    if task.get("execution_scope") != "single_agent" or task.get(
        "decomposition_state"
    ) != "concrete":
        raise_floor(
            "deep", "non-concrete or decomposable work requires the full profile"
        )
    if not exact_paths:
        raise_floor("standard", "no exact repository path surface was established")
    if patterns:
        raise_floor("standard", "path patterns require broader-than-exact review")
    if shared_systems:
        raise_floor("deep", "shared-system changes require the full profile")
    if _has_logical_resource(task):
        raise_floor("deep", "logical exclusive resources require the full profile")
    if symbols_or_components and (
        patterns or not exact_paths or len(symbols_or_components) > 4
    ):
        raise_floor(
            "standard",
            "named symbols or components are not confined to the small exact surface",
        )
    elif symbols_or_components:
        reasons.append(
            "named symbols or components are confined to the small exact path surface"
        )
    import_companions, substantive_serialized = _classify_serialized_surface(
        serialized, exact_paths, committed_path_probe
    )
    if substantive_serialized:
        raise_floor(
            "deep",
            "Unity serialized assets require the full profile: "
            + ", ".join(sorted(substantive_serialized)),
        )
    elif import_companions:
        # Not an escalation: recorded so the reduced profile is explainable.
        reasons.append(
            "deterministic new C# script import companions are not substantive "
            "serialized content: " + ", ".join(sorted(import_companions))
        )

    for raw_path in exact_paths:
        path = raw_path.replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        folded = _normalized_surface_path(path)
        name = PurePosixPath(path).name.casefold()
        suffix = PurePosixPath(path).suffix.casefold()
        if folded.startswith(_FULL_RIGOR_ROOTS) or name in _FULL_RIGOR_NAMES:
            raise_floor("deep", f"protected infrastructure surface: {path}")
        if suffix in _FULL_RIGOR_SUFFIXES:
            raise_floor("deep", f"serialized or project-wide asset surface: {path}")

    if len(exact_paths) > 4:
        raise_floor(
            "standard", "more than four exact paths exceed the lean-change bound"
        )
    if any(
        PurePosixPath(path.replace("\\", "/")).suffix.casefold()
        not in _FAST_SURFACE_SUFFIXES
        for path in exact_paths
    ):
        raise_floor(
            "standard", "the exact surface contains a non-lean file type"
        )

    if not reasons:
        reasons.append("exact isolated surface satisfies the lean-profile policy")

    requested = recommendation.capability_tier
    effective = (
        requested
        if _TIER_RANK[requested] >= _TIER_RANK[minimum]
        else minimum
    )
    overrides = [
        reason
        for tier, reason in floor_reasons
        if _TIER_RANK[tier] > _TIER_RANK[requested]
    ]
    if _TIER_RANK[effective] > _TIER_RANK[requested]:
        raised = (
            f"deterministic policy raised architect tier {requested} to {effective}"
        )
        reasons.append(raised)
        overrides.append(raised)
    elif _TIER_RANK[requested] > _TIER_RANK[minimum]:
        reasons.append(
            f"architect selected {requested}, stronger than the {minimum} minimum"
        )

    crew_profile, validation_profile = RIGOR_PROFILE_BY_TIER[effective]
    # Human verification stays REQUIRED for every task, including the lean
    # C#-plus-new-sidecar class recognized above. The separate automated-evidence
    # workflow is not yet authoritative, so routing must never turn synthetic
    # provenance, a reduced crew, or a narrow change surface into a fabricated
    # human PASS. Reducing the crew and validation profile changes how much
    # machine work runs; it never changes who signs off. `machine_evidence_permitted`
    # therefore remains unreachable until that workflow becomes authoritative.
    human_policy = "required"
    return TaskRigorDecision(
        architect_capability_tier=requested,
        minimum_capability_tier=minimum,
        effective_capability_tier=effective,
        crew_profile=crew_profile,
        validation_profile=validation_profile,
        human_verification_policy=human_policy,
        reasons=tuple(reasons),
        override_reasons=tuple(dict.fromkeys(overrides)),
    )


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
    rigor: TaskRigorDecision | None = None

    def to_event_dict(self) -> dict[str, object]:
        value = {
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
        if self.rigor is not None:
            value.update(self.rigor.to_event_dict())
        return value


def resolve_execution_route(
    recommendation: ExecutionRecommendation,
    policy: ExecutionRoutingPolicy,
    *,
    rigor: TaskRigorDecision | None = None,
) -> ResolvedExecutionRoute:
    if not isinstance(recommendation, ExecutionRecommendation):
        raise ExecutionRoutingError(
            "recommendation must be an ExecutionRecommendation"
        )
    if not isinstance(policy, ExecutionRoutingPolicy):
        raise ExecutionRoutingError("policy must be an ExecutionRoutingPolicy")
    capability_tier = (
        rigor.effective_capability_tier
        if rigor is not None
        else recommendation.capability_tier
    )
    if (
        rigor is not None
        and rigor.architect_capability_tier != recommendation.capability_tier
    ):
        raise ExecutionRoutingError(
            "rigor decision does not match the architect recommendation"
        )
    tier = policy.for_tier(capability_tier)
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
        capability_tier=capability_tier,
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
        rigor=rigor,
    )


def restrict_execution_routing_policy(
    policy: ExecutionRoutingPolicy,
    provider_allowlist: tuple[str, ...] | None,
) -> ExecutionRoutingPolicy:
    """Intersect ambient tier permissions with the immutable run restriction."""
    permitted = validate_provider_allowlist(provider_allowlist)
    if permitted is None:
        return policy
    tiers = {}
    for name in CAPABILITY_TIERS:
        tier = policy.for_tier(name)
        allowed = tier.allowed_execution_providers.intersection(permitted)
        if not allowed:
            raise ExecutionRoutingError(f"{name} tier has no provider permitted by provider_allowlist")
        tiers[name] = replace(
            tier,
            allowed_execution_providers=allowed,
            default_execution_provider=(
                tier.default_execution_provider
                if tier.default_execution_provider in allowed else sorted(allowed)[0]
            ),
        )
    return ExecutionRoutingPolicy(**tiers)


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
    provider_allowlist: tuple[str, ...] | None = None,
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
    return restrict_execution_routing_policy(ExecutionRoutingPolicy(
        fast=tiers["fast"],
        standard=tiers["standard"],
        deep=tiers["deep"],
    ), provider_allowlist)


__all__ = [
    "CAPABILITY_TIERS",
    "EXECUTION_PROVIDERS",
    "ExecutionRecommendation",
    "ExecutionRoutingError",
    "ExecutionRoutingPolicy",
    "HUMAN_VERIFICATION_POLICIES",
    "MAX_RECOMMENDATION_RATIONALE_CHARACTERS",
    "OPENAI_REASONING_EFFORTS",
    "PROVIDER_PREFERENCES",
    "ResolvedExecutionRoute",
    "TaskRigorDecision",
    "TierExecutionRoutingPolicy",
    "load_execution_routing_policy",
    "resolve_execution_route",
    "resolve_task_rigor",
]
