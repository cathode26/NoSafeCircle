"""Inspect and clean only run-bound Docker Compose resources."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


def _run(args: list[str]) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError("Docker worker operation failed: " + result.stderr.strip())
    return result.stdout


def inventory(checkout: Path, worker: dict, *, runner=_run) -> list[dict]:
    run_id = worker.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Missing worker run identity")
    project = "assistant-crew-" + hashlib.sha256(run_id.encode()).hexdigest()[:20]
    if worker.get("compose_project") != project:
        raise ValueError("Worker Compose project does not match its run")
    ids = runner(["ps", "--all", "--no-trunc", "--filter",
                  "label=com.docker.compose.project=" + project, "--format", "{{.ID}}"]).splitlines()
    containers = []
    # Limit inspect output to non-credential fields. Never read Config.Env.
    template = '{"Id":{{json .Id}},"State":{{json .State}},"Labels":{{json .Config.Labels}},"Mounts":{{json .Mounts}}}'
    for container_id in ids:
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise ValueError("Docker inventory returned an invalid container identity")
        data = json.loads(runner(["inspect", "--format", template, container_id]))
        if (data.get("Id") != container_id
                or (data.get("Labels") or {}).get("com.docker.compose.project") != project):
            raise ValueError("Container no longer belongs to this run")
        if not any(mount.get("Type") == "bind" and mount.get("Destination") == "/workspace"
                   and Path(mount.get("Source", "")).resolve() == checkout.resolve()
                   for mount in data.get("Mounts", [])):
            raise ValueError("Container does not mount the owned task checkout")
        state = data.get("State") or {}
        if type(state.get("Running")) is not bool:
            raise ValueError("Container running state is unknown")
        containers.append({"id": container_id, "running": state["Running"], "project": project})
    return containers


def stop_containers(checkout: Path, worker: dict, *, runner=_run) -> dict:
    owned = inventory(checkout, worker, runner=runner)
    for container in owned:
        if container["running"]:
            runner(["stop", "--time", "10", container["id"]])
    remaining = inventory(checkout, worker, runner=runner)
    return {"containers_stopped": not any(item["running"] for item in remaining),
            "containers": remaining, "host_exit_confirmed": False, "capacity_released": False}


def remove_unused_project_resources(checkout: Path, worker: dict, *, runner=_run) -> dict:
    """Remove this ended worker's containers and default network, never volumes.

    The caller must have already authenticated the host process as ended.  We
    still refuse cleanup while any owned container is running, and authenticate
    every Docker object by the exact Compose project label before removing it.
    """
    try:
        owned = inventory(checkout, worker, runner=runner)
    except RuntimeError as exc:
        # Settlement already proved the host and worker tree ended. Docker can
        # disappear during that proof or be unavailable during cleanup; leave
        # capacity/result state valid and let a later settlement retry cleanup.
        return {"containers_removed": [], "networks_removed": [], "volumes_removed": [],
                "cleanup_deferred": True, "cleanup_error": str(exc)}
    if any(item["running"] for item in owned):
        raise ValueError("Run containers have not exited")
    project = owned[0]["project"] if owned else worker["compose_project"]
    removed_containers = [item["id"] for item in owned]
    if removed_containers:
        try:
            runner(["rm", *removed_containers])
        except RuntimeError as exc:
            return {"containers_removed": [], "networks_removed": [], "volumes_removed": [],
                    "cleanup_deferred": True, "cleanup_error": str(exc)}

    try:
        network_ids = runner(["network", "ls", "--no-trunc", "--filter",
                              "label=com.docker.compose.project=" + project,
                              "--format", "{{.ID}}"]).splitlines()
    except RuntimeError as exc:
        return {"containers_removed": removed_containers, "networks_removed": [],
                "volumes_removed": [], "cleanup_deferred": True, "cleanup_error": str(exc)}
    removed_networks = []
    for network_id in network_ids:
        if not re.fullmatch(r"[0-9a-f]{64}", network_id):
            raise ValueError("Docker inventory returned an invalid network identity")
        template = '{"Id":{{json .Id}},"Name":{{json .Name}},"Labels":{{json .Labels}},"Containers":{{json .Containers}}}'
        try:
            data = json.loads(runner(["network", "inspect", "--format", template, network_id]))
        except RuntimeError as exc:
            return {"containers_removed": removed_containers, "networks_removed": removed_networks,
                    "volumes_removed": [], "cleanup_deferred": True, "cleanup_error": str(exc)}
        labels = data.get("Labels") or {}
        if (data.get("Id") != network_id
                or labels.get("com.docker.compose.project") != project
                or data.get("Name") != project + "_default"):
            raise ValueError("Network no longer belongs to this worker project")
        if data.get("Containers"):
            raise ValueError("Worker project network is still in use")
        try:
            runner(["network", "rm", network_id])
        except RuntimeError as exc:
            return {"containers_removed": removed_containers, "networks_removed": removed_networks,
                    "volumes_removed": [], "cleanup_deferred": True, "cleanup_error": str(exc)}
        removed_networks.append(network_id)
    return {"containers_removed": removed_containers,
            "networks_removed": removed_networks,
            "volumes_removed": [], "cleanup_deferred": False}
