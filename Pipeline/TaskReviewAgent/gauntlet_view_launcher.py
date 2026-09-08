#!/usr/bin/env python3
"""Start or reuse one exact architect-managed GauntletView listener."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

HEALTH_SCHEMA = "nsc-gauntlet-view-health/v1"
TASK_ID_RE = re.compile(r"NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})")
SHA40_RE = re.compile(r"[0-9a-f]{40}")
RUN_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?")
REPOSITORY_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})"
)
DEFAULT_PORTS = tuple(range(8787, 8820))


class GauntletViewLaunchError(RuntimeError):
    """The exact listener could not be proved or safely started."""


@dataclass(frozen=True)
class ViewerIdentity:
    source: Path
    source_branch: str
    source_commit: str
    state_root: Path
    run_id: str
    run_dir: Path
    repository: str
    display_task_ids: tuple[str, ...]
    human_approval_enabled: bool = False

    def __post_init__(self) -> None:
        source = self.source.resolve()
        state_root = self.state_root.resolve()
        run_dir = self.run_dir.resolve()
        if not source.is_absolute() or not state_root.is_absolute() or not run_dir.is_absolute():
            raise GauntletViewLaunchError("GauntletView paths must be absolute")
        if (
            not isinstance(self.source_branch, str)
            or not self.source_branch
            or self.source_branch.strip() != self.source_branch
            or len(self.source_branch) > 255
            or any(character in self.source_branch for character in "\r\n\x00")
        ):
            raise GauntletViewLaunchError("GauntletView source branch is invalid")
        if SHA40_RE.fullmatch(self.source_commit) is None:
            raise GauntletViewLaunchError("GauntletView source commit must be an exact SHA")
        if RUN_ID_RE.fullmatch(self.run_id) is None:
            raise GauntletViewLaunchError("GauntletView run ID is invalid")
        if REPOSITORY_RE.fullmatch(self.repository) is None:
            raise GauntletViewLaunchError("GauntletView repository identity is invalid")
        task_ids = tuple(sorted(set(self.display_task_ids)))
        if not task_ids or task_ids != self.display_task_ids:
            raise GauntletViewLaunchError(
                "GauntletView display roots must be sorted, non-empty, and duplicate-free"
            )
        if any(TASK_ID_RE.fullmatch(task_id) is None for task_id in task_ids):
            raise GauntletViewLaunchError("GauntletView display root is not a task ID")
        if type(self.human_approval_enabled) is not bool:
            raise GauntletViewLaunchError("GauntletView approval setting must be boolean")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "state_root", state_root)
        object.__setattr__(self, "run_dir", run_dir)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "source_branch": self.source_branch,
            "source_commit": self.source_commit,
            "state_root": str(self.state_root),
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "repository": self.repository,
            "display_task_ids": list(self.display_task_ids),
            "descendants": "durable_decomposition_closure",
            "human_approval_enabled": self.human_approval_enabled,
        }


@dataclass(frozen=True)
class PortDecision:
    disposition: str
    port: int


@dataclass(frozen=True)
class ViewerLaunchResult:
    disposition: str
    port: int
    url: str
    identity: ViewerIdentity
    log_path: Path | None = None


def _health_identity(value: Any) -> dict[str, Any] | None:
    if (
        not isinstance(value, dict)
        or value.get("schema") != HEALTH_SCHEMA
        or value.get("status") != "ok"
    ):
        return None
    value = value.get("identity")
    return value if isinstance(value, dict) else None


def choose_existing_or_free_port(
    identity: ViewerIdentity,
    ports: Iterable[int],
    *,
    probe: Callable[[int], Any],
    port_available: Callable[[int], bool],
) -> PortDecision:
    """Prefer an exact listener anywhere in the range before starting another."""

    candidates = tuple(ports)
    expected = identity.to_dict()
    for port in candidates:
        if _health_identity(probe(port)) == expected:
            return PortDecision("reuse", port)
    for port in candidates:
        if port_available(port):
            return PortDecision("start", port)
    raise GauntletViewLaunchError(
        "no free GauntletView port exists and no exact-matching listener was found"
    )


def probe_listener(port: int, *, timeout: float = 0.35) -> dict[str, Any] | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else None
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
        return None


def port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            candidate.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            candidate.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def viewer_command(
    identity: ViewerIdentity,
    *,
    port: int,
    python_executable: str | None = None,
    server_path: Path | None = None,
) -> tuple[str, ...]:
    if type(port) is not int or not 1 <= port <= 65535:
        raise GauntletViewLaunchError("GauntletView port must be in 1..65535")
    server = server_path or (
        identity.source / "Pipeline" / "TaskReviewAgent" / "GauntletView" / "server.py"
    )
    command = [
        python_executable or sys.executable,
        str(server),
        "--tasks",
        str(identity.source / "Tasks"),
        "--state",
        str(identity.state_root),
        "--run-dir",
        str(identity.run_dir),
        "--source-commit",
        identity.source_commit,
        "--source-branch",
        identity.source_branch,
        "--run-id",
        identity.run_id,
        "--repository",
        identity.repository,
        "--port",
        str(port),
    ]
    for task_id in identity.display_task_ids:
        command.extend(("--display-task-id", task_id))
    if identity.human_approval_enabled:
        command.append("--enable-human-approval")
    return tuple(command)


@contextmanager
def _launch_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _spawn_hidden(command: tuple[str, ...], *, cwd: Path, log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        kwargs["startupinfo"] = startup
    try:
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **kwargs,
        )
    finally:
        log.close()


def ensure_gauntlet_view(
    identity: ViewerIdentity,
    *,
    ports: Iterable[int] = DEFAULT_PORTS,
    startup_timeout: float = 8.0,
) -> ViewerLaunchResult:
    """Reuse one exact listener or start one hidden process on a free port."""

    if not (identity.source / "Pipeline" / "TaskReviewAgent" / "GauntletView" / "server.py").is_file():
        raise GauntletViewLaunchError("GauntletView server is missing from the bound source")
    expected = identity.to_dict()
    lock_path = identity.run_dir / "gauntlet-view-launch.lock"
    with _launch_lock(lock_path):
        decision = choose_existing_or_free_port(
            identity,
            ports,
            probe=probe_listener,
            port_available=port_available,
        )
        url = f"http://127.0.0.1:{decision.port}"
        if decision.disposition == "reuse":
            return ViewerLaunchResult("reused", decision.port, url, identity)

        log_path = identity.run_dir / "gauntlet-view.log"
        process = _spawn_hidden(
            viewer_command(identity, port=decision.port),
            cwd=identity.source,
            log_path=log_path,
        )
        deadline = time.monotonic() + startup_timeout
        while time.monotonic() <= deadline:
            observed = _health_identity(probe_listener(decision.port))
            if observed == expected:
                return ViewerLaunchResult(
                    "started", decision.port, url, identity, log_path
                )
            if process.poll() is not None:
                break
            time.sleep(0.1)
        if process.poll() is None:
            process.terminate()
        raise GauntletViewLaunchError(
            f"GauntletView did not publish its exact identity on {url}; inspect {log_path}"
        )


__all__ = [
    "DEFAULT_PORTS",
    "GauntletViewLaunchError",
    "HEALTH_SCHEMA",
    "PortDecision",
    "ViewerIdentity",
    "ViewerLaunchResult",
    "choose_existing_or_free_port",
    "ensure_gauntlet_view",
    "viewer_command",
]
