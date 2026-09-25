"""Bounded Docker command construction for AssistantControl decomposition."""
from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any, Mapping

from Pipeline.TaskReviewAgent.contracts import validate_task_id


ROOT = Path(__file__).resolve().parents[2]
for _module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from TaskDecomposition.round_robin_decomposition import same_provider_role_pair  # noqa: E402
from TaskDecomposition.live_decomposition import (  # noqa: E402
    MODEL_ENVIRONMENT_NAMES,
    model_environment_arguments,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# The exact path the container reads its leases from; it must stay equal to
# Pipeline/TaskReviewAgent/host_decomposition_launcher.POOL_LEASE_MOUNT, which
# the transport does not import because that module loads the whole scheduler.
POOL_LEASE_MOUNT = "/nsc-pool/decomposition-leases.json"

# The allow-list and the renderer live with `provider_configuration`, which is
# what resolves the models, so this transport and the production launcher
# cannot answer differently.
_model_environment_arguments = model_environment_arguments


def build_compose_command(
    *, task_id: str, project: str, providers: str, max_calls: int,
    run_id: str, pool_assignment: Mapping[str, Any] | None = None,
    provider_environment: Mapping[str, Any] | None = None,
    author_checklist: str | None = None,
    timeout_environment: Mapping[str, int] | None = None,
) -> tuple[str, ...]:
    """Build the only decomposition transport AssistantControl supports.

    AssistantControl always runs exactly two calls: one author followed by one
    independent reviewer. Two distinct providers are independent by provider
    identity and carry no reservation. One provider may serve both roles only
    through ``pool_assignment``: the host's durable reservation of one
    conversation per role, mounted read-only as the lease bundle. It does not
    inherit the production launcher's Issue or workflow-state dependencies.
    """
    provider_order = tuple(item.strip() for item in providers.split(",") if item.strip())
    if len(provider_order) != 2 or any(name not in {"claude", "codex"} for name in provider_order):
        raise ValueError("Assistant decomposition requires exactly two claude/codex roles")
    # Two calls is the only profile a same-provider pooled run supports. The
    # opt-in three-call budget needs two distinct providers, so an independent
    # PASS of a reviewer revision comes from the other provider.
    if type(max_calls) is not int or max_calls not in (2, 3):
        raise ValueError("Assistant decomposition requires a two- or three-call budget")
    if max_calls == 3 and (len(set(provider_order)) != 2 or pool_assignment is not None):
        raise ValueError("A three-call decomposition budget requires two distinct providers and no pool")
    if not _SAFE_ID.fullmatch(project):
        raise ValueError("Compose project name is invalid")
    if not _SAFE_ID.fullmatch(run_id):
        raise ValueError("Decomposition run id is invalid")
    pooled = same_provider_role_pair(provider_order)
    if not pooled and pool_assignment is not None:
        raise ValueError(
            "Assistant decomposition with two distinct providers consumes no role-session reservation"
        )
    if pooled and pool_assignment is None:
        raise ValueError(
            "Assistant decomposition by one provider requires the host's role-session "
            "lease reservation; without it author and reviewer are one conversation"
        )
    if pool_assignment is not None and provider_environment is not None:
        # A pooled run's model is part of the identity its leases were reserved
        # for. A second source would either lose silently or make the container
        # fail closed; either way there must be one source, not a winner.
        raise ValueError(
            "A pooled decomposition takes its model from its reservation: "
            "provider_environment is one source too many"
        )
    command = ["docker", "compose", "-p", project, "run", "--rm", "-T"]
    if pool_assignment is not None:
        bundle = pool_assignment.get("lease_bundle_path")
        identity = pool_assignment.get("repository_identity")
        if any(type(value) is not str or not value.strip() for value in (bundle, identity)):
            raise ValueError("Pooled decomposition requires exact lease-bundle and repository identities")
        # The bundle becomes a Docker bind source, so it must be the exact
        # regular file the reservation wrote and nothing else.
        if not Path(bundle).is_file():
            raise ValueError(f"Reserved decomposition lease bundle is not one regular file: {bundle}")
        command.extend(("--volume", f"{bundle}:{POOL_LEASE_MOUNT}:ro"))
        # The container resolves its model from its own environment, so the
        # model the leases were reserved for is pinned here; the container
        # still fails closed on any route it observes that differs.
        command.extend(
            _model_environment_arguments(pool_assignment.get("provider_environment") or {})
        )
    elif provider_environment:
        # The same pinning for a mixed pair, which has no reservation to carry
        # it. Without this the container ran `provider_configuration`'s own
        # defaults - claude-sonnet-5 and gpt-5.6-sol - while the run reported
        # success, so a caller that asked for Opus silently got Sonnet. It is
        # NOT a compose.yaml passthrough: on the pooled path a host value that
        # disagreed with the reservation would make the container fail closed,
        # which is why this lives here and applies only when unpooled.
        command.extend(_model_environment_arguments(provider_environment))
    # Only the budget-3 profile binds explicit role timeouts, and only these two.
    if timeout_environment is not None:
        if max_calls != 3 or set(timeout_environment) != set(TIMEOUT_ENVIRONMENT_NAMES):
            raise ValueError("Explicit decomposition timeouts belong only to the three-call profile")
        for name in sorted(timeout_environment):
            value = timeout_environment[name]
            if type(value) is not int or value <= 0:
                raise ValueError(f"Decomposition timeout {name} must be a positive integer")
            command.extend(("--env", f"{name}={value}"))
    command.extend((
        "round-robin-decompose", "python3",
        "Pipeline/TaskDecomposition/run_round_robin_decomposition.py",
        "--task-id", validate_task_id(task_id),
        "--providers", ",".join(provider_order),
        "--max-calls", str(max_calls),
        "--run-id", run_id,
    ))
    if pool_assignment is not None:
        command.extend((
            "--role-session-leases", POOL_LEASE_MOUNT,
            "--scheduler-repository-identity", str(pool_assignment["repository_identity"]),
        ))
    # Opt-in only: omitting it leaves the command, and so the prompts, unchanged.
    # The container's own argparse choices refuse an unknown version.
    if author_checklist is not None:
        if type(author_checklist) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,63}", author_checklist):
            raise ValueError("Assistant decomposition author checklist must be a version name")
        command.extend(("--author-checklist", author_checklist))
    return tuple(command)


TIMEOUT_ENVIRONMENT_NAMES = (
    "NSC_DECOMPOSITION_REVIEWER_TIMEOUT_SECONDS",
    "NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS",
)


__all__ = ["MODEL_ENVIRONMENT_NAMES", "POOL_LEASE_MOUNT", "TIMEOUT_ENVIRONMENT_NAMES", "build_compose_command"]
