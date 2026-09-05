#!/usr/bin/env python3
"""Windows smoke test for exact autonomous PowerShell launcher forwarding.

Classification: behavior tests over the real `Start-AutonomousGraphRun.ps1`
driven with stubbed `git`, `gh`, `docker`, and `python` executables. No GitHub
call, Docker container, task checkout, claim, or real run is involved; the
launcher's constructed argv is captured and asserted exactly.
"""

from __future__ import annotations

import json
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


def _exact_argv_environment(fixture: Path, log: Path) -> dict[str, str]:
    """Install stubs that record the launcher's argv token-for-token.

    `echo %*` collapses an argument vector into one line, which cannot
    distinguish "an option carrying an empty value" from "a bare option". The
    defect this file guards is exactly that difference, so the Python stub dumps
    `sys.argv` as JSON and the assertions read real tokens.
    """

    dumper = fixture / "argvdump.py"
    dumper.write_text(
        "import json, sys\n"
        "with open(sys.argv[1], 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps(sys.argv[2:]) + '\\n')\n"
        "sys.exit(10 if '--completion-probe' in sys.argv[2:] else 7)\n",
        encoding="utf-8",
    )
    _stub(fixture / "git.cmd", "exit /b 0")
    _stub(fixture / "gh.cmd", "exit /b 0")
    _stub(fixture / "docker.cmd", "exit /b 0")
    _stub(
        fixture / "python.cmd",
        f'"{sys.executable}" "{dumper}" "{log}" %*\r\nexit /b %ERRORLEVEL%',
    )
    environment = os.environ.copy()
    environment["PATH"] = str(fixture) + os.pathsep + environment.get("PATH", "")
    return environment


def _recorded_argv(log: Path) -> list[list[str]]:
    require(log.is_file(), f"the python stub was never invoked: {log}")
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _require_no_valueless_option(argv: list[str], option: str) -> None:
    """Fail when `option` appears with no value token after it.

    Windows PowerShell drops an empty-string argument entirely at the native
    process boundary, so a lost value does not arrive as `""` -- it arrives as
    nothing, and argparse reports `expected one argument`. Checking the token
    that follows is therefore the only way to see it.
    """

    for index, token in enumerate(argv):
        if token != option:
            continue
        following = argv[index + 1] if index + 1 < len(argv) else None
        require(
            following is not None and not following.startswith("-"),
            f"{option} was emitted with no value: {argv}",
        )


def _run_launcher(
    fixture: Path, environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            *arguments,
        ),
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=120.0,
    )


def _run_launcher_command(
    environment: dict[str, str], arguments: str
) -> subprocess.CompletedProcess[str]:
    """Invoke the launcher through the command form with a distinct bind failure.

    A parameter-binding rejection raises a PowerShell error rather than setting
    a native exit code, so `$LASTEXITCODE` would otherwise keep whatever the
    previous native command left behind. Exit 90 names "the launcher refused its
    arguments" unambiguously.
    """

    command = (
        "$ErrorActionPreference = 'Stop'; "
        f"try {{ & '{LAUNCHER}' {arguments}; exit $LASTEXITCODE }} "
        "catch { exit 90 }"
    )
    return subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ),
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=120.0,
    )


def test_omitted_task_id_lists_emit_no_option() -> None:
    """An omitted -TargetTaskId/-ExcludeTaskId must contribute no argv at all.

    `@($null)` is a one-element array holding `$null`, so iterating an unbound
    `[string[]]` parameter ran the loop body once and appended the option with a
    null value. `Invoke-NscNativeCommand` types its `-ArgumentList` as
    `[string[]]`, which coerces that null to `''` before its own null guard can
    see it, and PowerShell then drops the empty token when it launches Python.
    """

    with tempfile.TemporaryDirectory(prefix="autonomous-launcher-omit-", dir=ROOT) as text:
        fixture = Path(text)
        log = fixture / "argv.jsonl"
        environment = _exact_argv_environment(fixture, log)
        completed = _run_launcher(
            fixture,
            environment,
            "-RunId",
            "omitted-task-id-lists-test",
            "-ConfirmRepository",
            "cathode26/NoSafeCircle-Homework-Rehearsal",
            "-ExecutionProvider",
            "claude",
            "-ArchitectProvider",
            "claude",
        )
        require(completed.returncode == 7, f"launcher masked exit: {completed}")
        invocations = _recorded_argv(log)
        require(len(invocations) == 2, f"expected probe and run: {invocations}")
        for argv in invocations:
            for option in ("--target-task-id", "--exclude-task-id"):
                require(
                    option not in argv,
                    f"an omitted list still emitted {option}: {argv}",
                )
                _require_no_valueless_option(argv, option)


def test_canonical_target_only_launch_carries_no_exclusion() -> None:
    """The exact controller argv `Start-GameTaskAgent.ps1 -TaskId NSC-914` builds.

    The canonical operator command supplies a target and no exclusions, which is
    the shape that failed with `argument --exclude-task-id: expected one
    argument` before any Issue or checkout existed.
    """

    with tempfile.TemporaryDirectory(prefix="autonomous-launcher-canon-", dir=ROOT) as text:
        fixture = Path(text)
        log = fixture / "argv.jsonl"
        environment = _exact_argv_environment(fixture, log)
        completed = _run_launcher(
            fixture,
            environment,
            "-RunId",
            "nsc-914-20260101t000000z-abc123",
            "-ConfirmRepository",
            "cathode26/NoSafeCircle",
            "-TargetTaskId",
            "NSC-914",
            "-MaxWorkers",
            "1",
            "-Source",
            str(ROOT),
            "-ExecutionProvider",
            "claude",
        )
        require(completed.returncode == 7, f"launcher masked exit: {completed}")
        for argv in _recorded_argv(log):
            require(
                argv[argv.index("--target-task-id") + 1] == "NSC-914",
                f"the canonical target was not forwarded exactly: {argv}",
            )
            require(
                "--exclude-task-id" not in argv,
                f"the canonical launch invented an exclusion option: {argv}",
            )
            require(
                argv[argv.index("--execution-provider") + 1] == "claude",
                f"provider forwarding was disturbed: {argv}",
            )
            require(
                argv[argv.index("--max-workers") + 1] == "1",
                f"worker forwarding was disturbed: {argv}",
            )
            _require_no_valueless_option(argv, "--exclude-task-id")
            _require_no_valueless_option(argv, "--target-task-id")


def test_multiple_exclusions_are_each_preserved() -> None:
    """A real array of exclusions must reach Python as repeated exact options.

    `powershell.exe -File` cannot bind more than one value to a `[string[]]`
    parameter, so the multi-value contract is exercised the way a caller with an
    actual array invokes it.
    """

    with tempfile.TemporaryDirectory(prefix="autonomous-launcher-multi-", dir=ROOT) as text:
        fixture = Path(text)
        log = fixture / "argv.jsonl"
        environment = _exact_argv_environment(fixture, log)
        completed = _run_launcher_command(
            environment,
            "-RunId multi-exclusion-test "
            "-ConfirmRepository cathode26/NoSafeCircle-Homework-Rehearsal "
            "-TargetTaskId @('NSC-922','NSC-923') "
            "-ExcludeTaskId @('NSC-042','NSC-050','NSC-1234') "
            "-ExecutionProvider claude -ArchitectProvider claude",
        )
        require(completed.returncode == 7, f"launcher masked exit: {completed}")
        for argv in _recorded_argv(log):
            excluded = [
                argv[index + 1]
                for index, token in enumerate(argv)
                if token == "--exclude-task-id"
            ]
            targeted = [
                argv[index + 1]
                for index, token in enumerate(argv)
                if token == "--target-task-id"
            ]
            require(
                excluded == ["NSC-042", "NSC-050", "NSC-1234"],
                f"exclusions were reordered, merged or lost: {argv}",
            )
            require(
                targeted == ["NSC-922", "NSC-923"],
                f"targets were reordered, merged or lost: {argv}",
            )
            _require_no_valueless_option(argv, "--exclude-task-id")
            _require_no_valueless_option(argv, "--target-task-id")


def test_empty_and_whitespace_exclusions_never_reach_python() -> None:
    """Null, empty and whitespace-only values are refused, not silently dropped.

    The committed `[ValidatePattern]` already refuses them at binding time. This
    pins that behavior so a future relaxation cannot reintroduce a valueless
    option, and proves the launcher never reaches Python with one.
    """

    with tempfile.TemporaryDirectory(prefix="autonomous-launcher-empty-", dir=ROOT) as text:
        fixture = Path(text)
        log = fixture / "argv.jsonl"
        environment = _exact_argv_environment(fixture, log)
        for value in ("", " ", "	"):
            completed = _run_launcher(
                fixture,
                environment,
                "-RunId",
                "empty-exclusion-test",
                "-ConfirmRepository",
                "cathode26/NoSafeCircle-Homework-Rehearsal",
                "-ExcludeTaskId",
                value,
                "-ExecutionProvider",
                "claude",
                "-ArchitectProvider",
                "claude",
            )
            require(
                completed.returncode not in (0, 7, 10),
                f"an empty exclusion was accepted: {value!r} {completed}",
            )
            require(
                not log.is_file(),
                f"an empty exclusion reached Python: {value!r} "
                f"{log.read_text(encoding='utf-8') if log.is_file() else ''}",
            )
        # A list mixing a real ID with an empty one is refused as a whole rather
        # than silently narrowed to the values that happen to be well formed.
        for mixed_list in ("@('NSC-042','')", "@('NSC-042',' ')", "@('NSC-042',$null)"):
            mixed = _run_launcher_command(
                environment,
                f"-RunId mixed-exclusion-test "
                "-ConfirmRepository cathode26/NoSafeCircle-Homework-Rehearsal "
                f"-ExcludeTaskId {mixed_list} "
                "-ExecutionProvider claude -ArchitectProvider claude",
            )
            require(
                mixed.returncode not in (0, 7, 10),
                f"a partially empty exclusion list was accepted: {mixed_list} {mixed}",
            )
        require(
            not log.is_file(),
            "a partially empty exclusion list reached Python: "
            f"{log.read_text(encoding='utf-8') if log.is_file() else ''}",
        )


def test_exact_forwarding_of_every_supplied_option() -> int:
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
            "foreach ($TaskId in $TargetTaskIds)" in launcher_source
            and "$Arguments += @('--target-task-id', $TaskId)" in launcher_source
            and "foreach ($TaskId in $ExcludeTaskIds)" in launcher_source
            and "$Arguments += @('--exclude-task-id', $TaskId)" in launcher_source,
            "launcher no longer repeats every target and exclusion argument",
        )
        require(
            "@($TargetTaskId)" not in launcher_source
            and "@($ExcludeTaskId)" not in launcher_source,
            "launcher iterates the raw parameter again; `@($null)` is a "
            "one-element array holding $null and emits a valueless option",
        )
        require(
            "IsNullOrWhiteSpace" in launcher_source,
            "launcher no longer filters null, empty and whitespace-only task IDs",
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
        same_provider_docker = docker_log.read_text(encoding="utf-8")
        require(
            same_provider_docker.count("volume inspect") == 1
            and "volume inspect nosafecircle_claude-config" in same_provider_docker,
            f"same provider was not de-duplicated exactly: {same_provider_docker}",
        )
    return 0


TESTS = (
    test_exact_forwarding_of_every_supplied_option,
    test_omitted_task_id_lists_emit_no_option,
    test_canonical_target_only_launch_carries_no_exclusion,
    test_multiple_exclusions_are_each_preserved,
    test_empty_and_whitespace_exclusions_never_reach_python,
)


def main() -> int:
    require(os.name == "nt", "autonomous launcher test requires Windows")
    require(LAUNCHER.is_file(), f"launcher missing: {LAUNCHER}")
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"autonomous graph launcher smoke test: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
