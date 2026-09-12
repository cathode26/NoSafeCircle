#!/usr/bin/env python3
"""Windows launcher regressions for the selectable TaskReviewAgent supervisor.

Classification: in-memory/temporary-fixture behavior tests. Every test runs the
real ``Start-GameTaskAgent.ps1`` -- and, on the delegated path, the real
``Start-AutonomousGraphRun.ps1`` -- against stubbed ``git``, ``gh``, ``docker``
and ``python`` executables on PATH, reusing the stub harness that
``architect_managed_launcher_smoke_test.py`` already owns. No live provider,
container, Docker daemon, GitHub call, Unity invocation, scheduler, rehearsal
checkout, or tracked repository file is involved. The stub records the exact
argv every launcher and every ``docker`` call produced, so the assertions are
about real argument construction rather than source text.

The load-bearing claims are:

  * a top-level explicit task accepts ``-SupervisorProvider claude`` alongside
    ``-ArchitectProvider claude``, ``-ExecutionProvider claude`` and
    ``-ProviderAllowlist claude``, and forwards that exact value onward;
  * a Claude-only run inspects only the Claude credential volume and never
    enumerates, builds, or logs into anything Codex;
  * a Claude supervisor outside the allowlist stops before any Docker, GitHub,
    provider, or worker call;
  * a Codex supervisor outside the allowlist stops the same way;
  * omitting the parameter keeps the historical Codex behavior exactly,
    including the Codex credential-volume preflight;
  * ``-ProviderAllowlist claude`` never produces argv naming Codex.

Every test fails on the starting commit: the launcher had no
``-SupervisorProvider`` parameter at all and unconditionally demanded Codex in
any supplied ``-ProviderAllowlist``.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from architect_managed_launcher_smoke_test import (  # noqa: E402
    AUTONOMOUS_SCRIPT,
    DIRECT_SCRIPT,
    REPOSITORY,
    TASK,
    _calls,
    _environment,
    _real_controller_calls,
    _run,
    _value,
    _write_stub_path,
    require,
)


SCHEDULER_HEAD = "a" * 40
SCHEDULER_CONTRACT_SHA = "b" * 40


def docker_calls(records: list[dict]) -> list[list[str]]:
    return [list(item["argv"]) for item in records if item.get("tool") == "docker"]


def names_codex(values) -> bool:
    return any("codex" in str(item).casefold() for item in values)


def flatten(calls: list[list[str]]) -> list[str]:
    return [token for call in calls for token in call]


def test_claude_only_top_level_task_forwards_the_exact_supervisor() -> None:
    """A fully Claude run is accepted and the selection reaches the controller."""

    with tempfile.TemporaryDirectory(prefix="supervisor-launcher-claude-") as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture,
            log,
            [
                "-TaskId",
                TASK,
                "-SupervisorProvider",
                "claude",
                "-ArchitectProvider",
                "claude",
                "-ExecutionProvider",
                "claude",
                "-ProviderAllowlist",
                "claude",
                "-ConfirmRepository",
                REPOSITORY,
                "-Source",
                str(ROOT),
            ],
        )
        require(
            completed.returncode == 0,
            f"a Claude-only top-level run was refused: {completed.stdout}\n{completed.stderr}",
        )
        # _real_controller_calls returns the graph CLI argv the delegated
        # Start-AutonomousGraphRun.ps1 actually produced, so this asserts the
        # whole chain: top-level launcher -> graph launcher -> Python CLI.
        controller = _real_controller_calls(records)
        require(len(controller) == 1, f"expected one controller delegation: {controller}")
        require(
            _value(controller[0], "--supervisor-provider") == "claude",
            f"the supervisor selection did not reach the graph CLI: {controller[0]}",
        )
        require(
            _value(controller[0], "--architect-provider") == "claude"
            and _value(controller[0], "--execution-provider") == "claude"
            and _value(controller[0], "--provider-allowlist") == "claude",
            f"the three selectors were not all forwarded: {controller[0]}",
        )
        require(
            not names_codex(controller[0]),
            f"a Claude-only graph invocation named Codex: {controller[0]}",
        )


def test_a_claude_only_run_never_touches_the_codex_credential_volume() -> None:
    """Requirement 7: preflight inspects only the selected provider's volume."""

    with tempfile.TemporaryDirectory(prefix="supervisor-launcher-preflight-") as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture,
            log,
            [
                "-TaskId",
                TASK,
                "-SupervisorProvider",
                "claude",
                "-ExecutionProvider",
                "claude",
                "-ProviderAllowlist",
                "claude",
                "-Source",
                str(ROOT),
                "-RunId",
                "scheduler-run-supervisor",
                "-AdmissionSourceHead",
                SCHEDULER_HEAD,
                "-TaskContractSha256",
                SCHEDULER_CONTRACT_SHA,
            ],
        )
        require(
            completed.returncode == 0,
            f"a Claude-only worker run was refused: {completed.stdout}\n{completed.stderr}",
        )
        docker = docker_calls(records)
        require(docker, "the run performed no Docker preflight at all")
        require(
            not names_codex(flatten(docker)),
            "a Claude-only run inspected, built, or authenticated something Codex: "
            + repr(docker),
        )
        require(
            any(
                "nosafecircle_claude-config" in token
                for token in flatten(docker)
            ),
            f"the Claude credential volume was never inspected: {docker}",
        )
        worker = _calls(records, DIRECT_SCRIPT)
        require(len(worker) == 1, f"expected one worker invocation: {worker}")
        require(
            _value(worker[0], "--supervisor-provider") == "claude",
            f"the worker did not receive the selection: {worker[0]}",
        )
        require(
            not names_codex(worker[0]),
            f"a Claude-only worker argv named Codex: {worker[0]}",
        )


def test_a_supervisor_outside_the_allowlist_stops_before_anything_runs() -> None:
    """Requirements 6 and 7: both directions refuse before Docker or GitHub."""

    for supervisor, allowlist in (("claude", "codex"), ("codex", "claude")):
        with tempfile.TemporaryDirectory(prefix="supervisor-launcher-refuse-") as text:
            fixture = Path(text)
            log = _write_stub_path(fixture)
            completed, records = _run(
                fixture,
                log,
                [
                    "-TaskId",
                    TASK,
                    "-SupervisorProvider",
                    supervisor,
                    "-ExecutionProvider",
                    allowlist,
                    "-ArchitectProvider",
                    allowlist,
                    "-ProviderAllowlist",
                    allowlist,
                    "-Source",
                    str(ROOT),
                ],
            )
            require(
                completed.returncode != 0,
                f"a {supervisor} supervisor outside a {allowlist}-only allowlist was accepted",
            )
            combined = completed.stdout + completed.stderr
            require(
                "must be in ProviderAllowlist" in combined,
                f"the refusal did not name the allowlist: {combined}",
            )
            require(
                not docker_calls(records),
                f"the launcher reached Docker before refusing: {docker_calls(records)}",
            )
            require(
                not _calls(records, DIRECT_SCRIPT)
                and not _calls(records, AUTONOMOUS_SCRIPT),
                "the launcher started a pipeline before refusing",
            )
            require(
                not any(item.get("tool") == "gh" for item in records),
                "the launcher called GitHub before refusing",
            )


def test_omitting_the_parameter_keeps_the_existing_codex_behavior() -> None:
    """Requirement 12: an existing caller is unchanged, including its preflight."""

    with tempfile.TemporaryDirectory(prefix="supervisor-launcher-default-") as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture,
            log,
            [
                "-TaskId",
                TASK,
                "-ExecutionProvider",
                "claude",
                "-Source",
                str(ROOT),
                "-RunId",
                "scheduler-run-default",
                "-AdmissionSourceHead",
                SCHEDULER_HEAD,
                "-TaskContractSha256",
                SCHEDULER_CONTRACT_SHA,
            ],
        )
        require(
            completed.returncode == 0,
            f"the historical default run was refused: {completed.stdout}\n{completed.stderr}",
        )
        docker = flatten(docker_calls(records))
        require(
            names_codex(docker),
            "the default run stopped performing its Codex credential preflight",
        )
        worker = _calls(records, DIRECT_SCRIPT)
        require(len(worker) == 1, f"expected one worker invocation: {worker}")
        require(
            "--supervisor-provider" not in worker[0],
            "an unchosen supervisor must not be forwarded as an explicit selection; "
            f"the worker resolves the historical default itself: {worker[0]}",
        )


def test_the_controller_delegation_omits_an_unchosen_supervisor() -> None:
    """Requirement 12: the architect-managed path stays byte-compatible."""

    with tempfile.TemporaryDirectory(prefix="supervisor-launcher-omit-") as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture,
            log,
            [
                "-TaskId",
                TASK,
                "-ConfirmRepository",
                REPOSITORY,
                "-Source",
                str(ROOT),
            ],
        )
        require(
            completed.returncode == 0,
            f"the historical delegation was refused: {completed.stdout}\n{completed.stderr}",
        )
        controller = _real_controller_calls(records)
        require(len(controller) == 1, f"expected one controller delegation: {controller}")
        require(
            "--supervisor-provider" not in controller[0],
            f"an unchosen supervisor reached the graph CLI: {controller[0]}",
        )


def main() -> int:
    tests = (
        test_claude_only_top_level_task_forwards_the_exact_supervisor,
        test_a_claude_only_run_never_touches_the_codex_credential_volume,
        test_a_supervisor_outside_the_allowlist_stops_before_anything_runs,
        test_omitting_the_parameter_keeps_the_existing_codex_behavior,
        test_the_controller_delegation_omits_an_unchosen_supervisor,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"supervisor provider launcher tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
