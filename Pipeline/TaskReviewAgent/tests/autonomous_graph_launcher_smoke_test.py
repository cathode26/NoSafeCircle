#!/usr/bin/env python3
"""Windows smoke test for exact autonomous PowerShell launcher forwarding."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / "Pipeline" / "TaskReviewAgent" / "Start-AutonomousGraphRun.ps1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _stub(path: Path, body: str) -> None:
    path.write_text("@echo off\r\n" + body + "\r\n", encoding="utf-8")


def main() -> int:
    require(os.name == "nt", "autonomous launcher test requires Windows")
    require(LAUNCHER.is_file(), f"launcher missing: {LAUNCHER}")
    with tempfile.TemporaryDirectory(prefix="autonomous-launcher-", dir=ROOT) as text:
        fixture = Path(text)
        argument_log = fixture / "python-arguments.txt"
        probe_log = fixture / "python-probe-arguments.txt"
        docker_log = fixture / "docker-arguments.txt"
        _stub(fixture / "git.cmd", "exit /b 0")
        _stub(fixture / "gh.cmd", "exit /b 0")
        _stub(fixture / "docker.cmd", f">>\"{docker_log}\" echo %*\r\nexit /b 0")
        _stub(
            fixture / "python.cmd",
            (
                "echo %* | findstr /c:\"--completion-probe\" >nul\r\n"
                "if errorlevel 1 goto realrun\r\n"
                f">\"{probe_log}\" echo %*\r\n"
                "exit /b 10\r\n"
                ":realrun\r\n"
                f">\"{argument_log}\" echo %*\r\n"
                "exit /b 7"
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = str(fixture) + os.pathsep + environment.get("PATH", "")
        completed = subprocess.run(
            (
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(LAUNCHER),
                "-RunId",
                "launcher-forwarding-test",
                "-ConfirmRepository",
                "cathode26/NoSafeCircle-Homework-Rehearsal",
                "-TargetTaskId",
                "NSC-922",
                "-ExcludeTaskId",
                "NSC-042",
                "-MaxWorkers",
                "10",
                "-ExecutionProvider",
                "claude",
                "-ArchitectProvider",
                "codex",
                "-Model",
                "worker-model",
                "-ArchitectModel",
                "architect-model",
                "-MaxTurns",
                "120",
                "-ArchitectMaxTurns",
                "24",
                "-ArchitectMaxInvocationsPerPoll",
                "6",
                "-FallbackSeconds",
                "60",
                "-CheckoutRoot",
                str(fixture / "checkouts"),
                "-EnableSyntheticEvidence",
            ),
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=60.0,
        )
        require(completed.returncode == 7, f"launcher masked exit: {completed}")
        require(argument_log.is_file(), f"python stub was not called: {completed}")
        arguments = argument_log.read_text(encoding="utf-8")
        require(probe_log.is_file(), f"completion probe was not called: {completed}")
        probe_arguments = probe_log.read_text(encoding="utf-8")
        expected = (
            "Pipeline/TaskReviewAgent/run_autonomous_graph.py",
            "--run-id launcher-forwarding-test",
            "--confirm-repository cathode26/NoSafeCircle-Homework-Rehearsal",
            "--target-task-id NSC-922",
            "--exclude-task-id NSC-042",
            "--max-workers 10",
            "--execution-provider claude",
            "--architect-provider codex",
            "--model worker-model",
            "--architect-model architect-model",
            "--max-turns 120",
            "--architect-max-turns 24",
            "--architect-max-invocations-per-poll 6",
            "--fallback-seconds 60",
            "--enable-synthetic-evidence",
        )
        for fragment in expected:
            require(fragment in arguments, f"launcher omitted {fragment!r}: {arguments}")
            require(
                fragment in probe_arguments,
                f"completion probe omitted identity {fragment!r}: {probe_arguments}",
            )
        require("--completion-probe" in probe_arguments, probe_arguments)
        require("--completion-probe" not in arguments, arguments)
        require(docker_log.is_file(), f"docker stub was not called: {completed}")
        docker_arguments = docker_log.read_text(encoding="utf-8")
        require(
            "volume inspect nosafecircle_claude-config" in docker_arguments,
            f"Claude provider volume name was corrupted: {docker_arguments}",
        )
        require(
            "volume inspect nosafecircle_codex-config" in docker_arguments,
            f"Codex provider volume name was corrupted: {docker_arguments}",
        )
        require(
            "claudeclaude" not in docker_arguments
            and "codexcodex" not in docker_arguments,
            f"provider name was duplicated: {docker_arguments}",
        )
        require(
            arguments.count("--target-task-id") == 1,
            f"target forwarding was not repeatable: {arguments}",
        )
        require(
            arguments.count("--exclude-task-id") == 1,
            f"exclusion forwarding was not exact: {arguments}",
        )
        launcher_source = LAUNCHER.read_text(encoding="utf-8-sig")
        require(
            "foreach ($TaskId in @($TargetTaskId))" in launcher_source
            and "$Arguments += @('--target-task-id', $TaskId)" in launcher_source,
            "launcher no longer repeats every target task argument",
        )
        launcher_probe = launcher_source.index("--completion-probe")
        github_preflight = launcher_source.index("gh' `")
        docker_preflight = launcher_source.index("compose', 'version")
        require(
            launcher_probe < github_preflight and launcher_probe < docker_preflight,
            "completed receipt probe no longer precedes GitHub/Docker calls",
        )
        docker_log.unlink()
        same_provider = subprocess.run(
            (
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(LAUNCHER),
                "-RunId",
                "same-provider-volume-test",
                "-ConfirmRepository",
                "cathode26/NoSafeCircle-Homework-Rehearsal",
                "-ExecutionProvider",
                "claude",
                "-ArchitectProvider",
                "claude",
            ),
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=60.0,
        )
        require(same_provider.returncode == 7, same_provider)
        omitted_optional_arguments = argument_log.read_text(encoding="utf-8")
        omitted_probe_arguments = probe_log.read_text(encoding="utf-8")
        for unexpected in ("--target-task-id", "--exclude-task-id"):
            require(
                unexpected not in omitted_optional_arguments,
                f"omitted optional task selector emitted {unexpected}: "
                f"{omitted_optional_arguments}",
            )
            require(
                unexpected not in omitted_probe_arguments,
                f"omitted optional task selector polluted the completion probe: "
                f"{omitted_probe_arguments}",
            )
        same_provider_docker = docker_log.read_text(encoding="utf-8")
        require(
            same_provider_docker.count("volume inspect") == 1
            and "volume inspect nosafecircle_claude-config" in same_provider_docker,
            f"same provider was not de-duplicated exactly: {same_provider_docker}",
        )
    print("autonomous graph launcher smoke test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
