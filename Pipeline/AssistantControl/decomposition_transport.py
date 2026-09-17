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


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# The exact path the container reads its leases from; it must stay equal to
# Pipeline/TaskReviewAgent/host_decomposition_launcher.POOL_LEASE_MOUNT, which
# the transport does not import because that module loads the whole scheduler.
POOL_LEASE_MOUNT = "/nsc-pool/decomposition-leases.json"


def build_compose_command(
    *, task_id: str, project: str, providers: str, max_calls: int,
    run_id: str, pool_assignment: Mapping[str, Any] | None = None,
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
    if type(max_calls) is not int or max_calls != 2:
        raise ValueError("Assistant decomposition requires exactly two provider calls")
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
        environment = pool_assignment.get("provider_environment") or {}
        for name, value in sorted(environment.items()):
            if value:
                command.extend(("--env", f"{name}={value}"))
    command.extend((
        "round-robin-decompose", "python3",
        "Pipeline/TaskDecomposition/run_round_robin_decomposition.py",
        "--task-id", validate_task_id(task_id),
        "--providers", ",".join(provider_order),
        "--max-calls", "2",
        "--run-id", run_id,
    ))
    if pool_assignment is not None:
        command.extend((
            "--role-session-leases", POOL_LEASE_MOUNT,
            "--scheduler-repository-identity", str(pool_assignment["repository_identity"]),
        ))
    return tuple(command)


__all__ = ["POOL_LEASE_MOUNT", "build_compose_command"]
