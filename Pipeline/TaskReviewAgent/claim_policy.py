"""Load and validate the committed Stage 1 ephemeral claim policy.

``claim_policy.json`` is the committed policy authority for the short-lived
Git-ref claim layer. The loader fails closed on any weakening: Stage 1 only
permits ``resume_only`` mode, atomic nonexistence-CAS creation, atomic
exact-SHA-CAS release, and manual exact-SHA stale-claim repair. Changing any
of those requires a reviewed policy *and* code change together.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .contracts import TaskReviewContractError

CLAIM_POLICY_PATH = Path(__file__).resolve().parent / "claim_policy.json"
CLAIM_POLICY_SCHEMA_VERSION = "1.0"
ALLOWED_MODES = frozenset({"resume_only"})
REQUIRED_CREATION = "atomic_multi_ref_nonexistence_cas"
REQUIRED_RELEASE = "atomic_multi_ref_exact_sha_cas"
REQUIRED_STALE_CLAIM_REPAIR = "manual_exact_sha_only"
ACTIVATION_PENDING = "pending_capability_probe"
ACTIVATION_ACTIVE = "active"
ALLOWED_ACTIVATION_STATUSES = frozenset({ACTIVATION_PENDING, ACTIVATION_ACTIVE})

# A claim namespace is a plain refs/... prefix; logical refs are appended
# beneath it. Structural validation here; Git itself remains the final
# authority at push time via check-ref-format semantics.
_NAMESPACE_RE = re.compile(r"^refs/[0-9A-Za-z][0-9A-Za-z._/-]*[0-9A-Za-z]$")


class ClaimPolicyError(TaskReviewContractError):
    """Raised when the committed claim policy is missing, invalid, or weakened."""


class ClaimCoordinationNotActivatedError(ClaimPolicyError):
    """Raised when production Issue mutation is attempted before claim activation.

    The committed Stage 1 policy now records ``activation.status`` =
    ``active`` with ``activated_namespace`` = ``refs/nsc/claims``, proven
    live against a disposable GitHub repository (see
    ``Pipeline/TaskReviewAgent/evidence/stage1-github-claim-capability-
    20260830.json``). This error still exists to fail closed for any policy
    that has not been activated: no production claim refs may be created and
    the real mutating explicit-task path must stop instead of silently
    falling back to Issue-only admission.
    """


@dataclass(frozen=True)
class ClaimPolicy:
    schema_version: str
    mode: str
    namespace_preference: tuple[str, ...]
    creation: str
    release: str
    stale_claim_repair: str
    activation_status: str
    activated_namespace: str | None


def validate_claim_namespace(namespace: str) -> str:
    if type(namespace) is not str or not _NAMESPACE_RE.fullmatch(namespace):
        raise ClaimPolicyError(f"claim namespace is not a valid refs/ prefix: {namespace!r}")
    if "//" in namespace or ".." in namespace or namespace.endswith(".lock"):
        raise ClaimPolicyError(f"claim namespace contains an invalid component: {namespace!r}")
    return namespace


def load_claim_policy(path: Path | str | None = None) -> ClaimPolicy:
    policy_path = Path(path) if path is not None else CLAIM_POLICY_PATH
    try:
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClaimPolicyError(f"claim policy could not be read: {policy_path}") from exc
    if not isinstance(raw, dict):
        raise ClaimPolicyError("claim policy must be one JSON object")
    expected_keys = {
        "schema_version",
        "mode",
        "namespace_preference",
        "creation",
        "release",
        "stale_claim_repair",
        "activation",
    }
    if set(raw) != expected_keys:
        raise ClaimPolicyError(
            f"claim policy keys do not match contract: {sorted(raw)}"
        )
    if raw["schema_version"] != CLAIM_POLICY_SCHEMA_VERSION:
        raise ClaimPolicyError("claim policy has an unsupported schema_version")
    if raw["mode"] not in ALLOWED_MODES:
        raise ClaimPolicyError(
            f"claim policy mode {raw['mode']!r} is not permitted in Stage 1; "
            f"allowed: {sorted(ALLOWED_MODES)}"
        )
    namespaces = raw["namespace_preference"]
    if not isinstance(namespaces, list) or not namespaces:
        raise ClaimPolicyError("claim policy namespace_preference must be a non-empty list")
    validated = tuple(validate_claim_namespace(item) for item in namespaces)
    if len(set(validated)) != len(validated):
        raise ClaimPolicyError("claim policy namespace_preference contains duplicates")
    if raw["creation"] != REQUIRED_CREATION:
        raise ClaimPolicyError(
            f"claim creation must remain {REQUIRED_CREATION!r}: {raw['creation']!r}"
        )
    if raw["release"] != REQUIRED_RELEASE:
        raise ClaimPolicyError(
            f"claim release must remain {REQUIRED_RELEASE!r}: {raw['release']!r}"
        )
    if raw["stale_claim_repair"] != REQUIRED_STALE_CLAIM_REPAIR:
        raise ClaimPolicyError(
            "claim stale_claim_repair must remain "
            f"{REQUIRED_STALE_CLAIM_REPAIR!r}: {raw['stale_claim_repair']!r}"
        )
    activation = raw["activation"]
    if not isinstance(activation, dict) or set(activation) != {
        "status",
        "activated_namespace",
    }:
        raise ClaimPolicyError(
            "claim policy activation must be an object with exactly "
            "'status' and 'activated_namespace'"
        )
    status = activation["status"]
    activated_namespace = activation["activated_namespace"]
    if status not in ALLOWED_ACTIVATION_STATUSES:
        raise ClaimPolicyError(
            f"claim policy activation status {status!r} is not permitted; "
            f"allowed: {sorted(ALLOWED_ACTIVATION_STATUSES)}"
        )
    if status == ACTIVATION_PENDING:
        if activated_namespace is not None:
            raise ClaimPolicyError(
                "a pending_capability_probe claim policy must not name an "
                "activated namespace"
            )
    else:
        # Activation must name the exact probe-proven namespace; the first
        # preference entry is never selected implicitly.
        if activated_namespace not in validated:
            raise ClaimPolicyError(
                "an active claim policy must name one activated_namespace from "
                f"namespace_preference: {activated_namespace!r}"
            )
    return ClaimPolicy(
        schema_version=raw["schema_version"],
        mode=raw["mode"],
        namespace_preference=validated,
        creation=raw["creation"],
        release=raw["release"],
        stale_claim_repair=raw["stale_claim_repair"],
        activation_status=status,
        activated_namespace=activated_namespace,
    )


def preferred_claim_namespace(policy: ClaimPolicy | None = None) -> str:
    """First policy namespace. The disposable-GitHub capability probe proved
    the custom ``refs/nsc`` namespace live (see ``activated_claim_namespace``
    for the reviewed activation this preference feeds into); callers still
    choose a namespace explicitly rather than relying on preference order."""

    return (policy or load_claim_policy()).namespace_preference[0]


def activated_claim_namespace(policy: ClaimPolicy | None = None) -> str:
    """The namespace explicitly activated for production claim coordination.

    Fails closed with ``ClaimCoordinationNotActivatedError`` while the
    committed policy still records ``pending_capability_probe``. Activation is
    a reviewed policy change made only after the disposable-GitHub capability
    probe proves the namespace; it is never inferred from preference order.
    """

    resolved = policy or load_claim_policy()
    if resolved.activation_status != ACTIVATION_ACTIVE or not resolved.activated_namespace:
        raise ClaimCoordinationNotActivatedError(
            "atomic Git-ref claim coordination has not been activated: the "
            "committed claim policy records activation.status="
            f"{resolved.activation_status!r}. Run the disposable-GitHub "
            "capability probe, then activate exactly one proven namespace in "
            "Pipeline/TaskReviewAgent/claim_policy.json via a reviewed change. "
            "The production mutating explicit-task path must not fall back to "
            "Issue-only admission."
        )
    return validate_claim_namespace(resolved.activated_namespace)


__all__ = [
    "ACTIVATION_ACTIVE",
    "ACTIVATION_PENDING",
    "ALLOWED_ACTIVATION_STATUSES",
    "ALLOWED_MODES",
    "CLAIM_POLICY_PATH",
    "CLAIM_POLICY_SCHEMA_VERSION",
    "ClaimCoordinationNotActivatedError",
    "ClaimPolicy",
    "ClaimPolicyError",
    "activated_claim_namespace",
    "load_claim_policy",
    "preferred_claim_namespace",
    "validate_claim_namespace",
]
