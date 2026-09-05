#!/usr/bin/env python3
"""Windows regressions for architect-managed top-level Game Task execution.

Classification: in-memory/temporary-fixture behavior tests. Every test runs the
real `Start-GameTaskAgent.ps1` -- and, on the delegated path, the real
`Start-AutonomousGraphRun.ps1` -- against stubbed `git`, `gh`, `docker` and
`python` executables on PATH. No live provider, container, Docker daemon,
GitHub call, Unity invocation, scheduler, or tracked repository file is
involved. The stub records the exact argv every launcher produced, so the
assertions are about real argument construction rather than source text.

The load-bearing claims are:

  * a top-level explicit `-TaskId` with no scheduler `-RunId` delegates exactly
    once to the existing autonomous graph controller, targets that task, and
    defaults to worker capacity 1;
  * that path never invokes `run_pipeline_agent.py`, so it cannot silently fall
    back to the conservative direct worker;
  * a scheduler child carrying a non-empty `-RunId` stays on the direct worker
    path and cannot recurse into the controller that spawned it;
  * that child receives the scheduler-resolved rigor, validation, model,
    reasoning effort and pooled-session authority verbatim;
  * `-DirectManual` keeps the previous conservative behavior and claims no pool
    authority;
  * synthetic evidence reaches the controller only when the operator asked for
    it, and the committed private-rehearsal guards are untouched;
  * the target set expands through committed decomposition children only --
    `depends_on` is never pulled into scope;
  * contradictory option combinations fail before either pipeline starts;
  * the controller's exit code survives the delegation unchanged.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LAUNCHER = ROOT / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
CONTROLLER_LAUNCHER = ROOT / "Pipeline" / "TaskReviewAgent" / "Start-AutonomousGraphRun.ps1"

AUTONOMOUS_SCRIPT = "run_autonomous_graph.py"
DIRECT_SCRIPT = "run_pipeline_agent.py"
PREFLIGHT_SCRIPT = "launcher_preflight.py"
RESOLVER_SCRIPT = "resolve_issue_repository.py"

TASK = "NSC-914"
REPOSITORY = "cathode26/NoSafeCircle-Homework-Rehearsal"
SCHEDULER_RUN_ID = "scheduler-run-914"
SCHEDULER_HEAD = "a" * 40
SCHEDULER_CONTRACT_SHA = "b" * 40

FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# --------------------------------------------------------------- stub PATH


# A PowerShell stub, not a .cmd shim: `Invoke-NscNativeCommand` hands Docker a
# multi-line probe script as one argument, and cmd.exe cannot carry an embedded
# newline through `%*`. PowerShell resolves a .ps1 on PATH as an ExternalScript
# and binds every argument, including dash-prefixed and multi-line ones,
# literally into $args.
STUB_SOURCE = '''$Tool = @TOOL@
$Arguments = @($args)
$Record = [ordered]@{ tool = $Tool; argv = $Arguments }
Add-Content -LiteralPath $env:NSC_STUB_LOG -Encoding UTF8 -Value (
    ConvertTo-Json -InputObject $Record -Compress -Depth 5
)

function Get-StubExit {
    param([string]$Name, [int]$Fallback)
    $Value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Fallback }
    return [int]$Value
}

function Write-ExactUtf8 {
    param([string]$Path, [string]$Text)
    $Parent = Split-Path -Parent $Path
    if ($Parent -and -not (Test-Path -LiteralPath $Parent -PathType Container)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    [System.IO.File]::WriteAllText(
        $Path, $Text, (New-Object System.Text.UTF8Encoding($false))
    )
}

if ($Tool -eq 'docker') {
    if ($Arguments.Count -ge 2 -and $Arguments[0] -eq 'volume' -and $Arguments[1] -eq 'ls') {
        Write-Output 'nosafecircle_codex-config'
        exit 0
    }
    $Index = [Array]::IndexOf([string[]]$Arguments, '-lc')
    if ($Index -ge 0 -and ($Index + 1) -lt $Arguments.Count) {
        $Match = [regex]::Match(
            [string]$Arguments[$Index + 1],
            '/execution-output/(permission-probe-[0-9a-fA-F]+\\.txt)'
        )
        if ($Match.Success) {
            Write-ExactUtf8 `
                -Path (Join-Path $env:NSC_STUB_EXECUTION_OUTPUT_ROOT $Match.Groups[1].Value) `
                -Text 'task-review-agent-permission-ok'
        }
    }
    exit 0
}

if ($Tool -ne 'python') { exit 0 }

$Script = if ($Arguments.Count -gt 0) { Split-Path -Leaf ([string]$Arguments[0]) } else { '' }
if ($Script -eq 'resolve_issue_repository.py') {
    $Index = [Array]::IndexOf([string[]]$Arguments, '--output')
    Write-ExactUtf8 -Path ([string]$Arguments[$Index + 1]) -Text $env:NSC_STUB_REPOSITORY
    exit 0
}
if ($Script -eq 'human_action_wait.py') {
    exit (Get-StubExit -Name 'NSC_STUB_HUMAN_WAIT_EXIT' -Fallback 4)
}
if ($Script -eq 'launcher_preflight.py') {
    Write-Output '{"status":"fresh_allowed"}'
    exit 0
}
if ($Arguments -contains '--completion-probe') {
    exit (Get-StubExit -Name 'NSC_STUB_PROBE_EXIT' -Fallback 10)
}
if ($Script -eq 'run_autonomous_graph.py') {
    exit (Get-StubExit -Name 'NSC_STUB_CONTROLLER_EXIT' -Fallback 0)
}
if ($Script -eq 'run_pipeline_agent.py') {
    exit (Get-StubExit -Name 'NSC_STUB_DIRECT_EXIT' -Fallback 0)
}
exit 0
'''


def _write_stub_path(fixture: Path) -> Path:
    """Create git/gh/docker/python shims that record their exact argv."""
    log = fixture / "invocations.jsonl"
    for tool in ("git", "gh", "docker", "python"):
        (fixture / f"{tool}.ps1").write_text(
            STUB_SOURCE.replace("@TOOL@", f"'{tool}'"), encoding="utf-8", newline="\r\n"
        )
    return log


def _environment(fixture: Path, log: Path, **overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = str(fixture) + os.pathsep + environment.get("PATH", "")
    environment["NSC_STUB_LOG"] = str(log)
    environment["NSC_STUB_REPOSITORY"] = REPOSITORY
    environment["NSC_STUB_EXECUTION_OUTPUT_ROOT"] = str(
        ROOT / "Pipeline" / "ExecutionCrew" / "outputs"
    )
    environment.update(overrides)
    return environment


def _run(fixture: Path, log: Path, arguments: list[str], **overrides: str):
    completed = subprocess.run(
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
        env=_environment(fixture, log, **overrides),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=180.0,
    )
    records = []
    if log.is_file():
        for line in log.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return completed, records


def _run_command(fixture: Path, log: Path, command: str, **overrides: str):
    """Invoke the launcher through -Command, which can express -Switch:$false."""
    completed = subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ),
        cwd=ROOT,
        env=_environment(fixture, log, **overrides),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=180.0,
    )
    records = []
    if log.is_file():
        for line in log.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return completed, records


def _calls(records: list[dict], script: str) -> list[list[str]]:
    """Every recorded python invocation of one pipeline entry point."""
    return [
        record["argv"]
        for record in records
        if record["tool"] == "python"
        and record["argv"]
        and os.path.basename(record["argv"][0]) == script
    ]


def _real_controller_calls(records: list[dict]) -> list[list[str]]:
    """Controller invocations that are the run itself, not its receipt probe."""
    return [
        argv
        for argv in _calls(records, AUTONOMOUS_SCRIPT)
        if "--completion-probe" not in argv
    ]


def _value(argv: list, flag: str) -> str | None:
    return str(argv[argv.index(flag) + 1]) if flag in argv else None


def fixture_dir():
    return tempfile.TemporaryDirectory(prefix="architect-managed-", dir=ROOT)


# ------------------------------------------- 1 and 2: top-level delegation


def test_top_level_task_delegates_once_to_the_autonomous_controller() -> None:
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture, log, ["-TaskId", TASK, "-ExecutionProvider", "claude"]
        )
        require(completed.returncode == 0, f"delegation failed: {completed}")

        controller = _real_controller_calls(records)
        require(len(controller) == 1,
                f"expected exactly one controller run, got {len(controller)}: {controller}")
        argv = controller[0]
        require(_value(argv, "--target-task-id") == TASK,
                f"controller did not target the requested task: {argv}")
        require(argv.count("--target-task-id") == 1,
                f"target task was forwarded more than once: {argv}")
        require(_value(argv, "--max-workers") == "1",
                f"default worker capacity is not 1: {argv}")
        require(_value(argv, "--execution-provider") == "claude",
                f"selected execution provider was not forwarded: {argv}")
        require(_value(argv, "--confirm-repository") == REPOSITORY,
                f"repository assertion was not forwarded: {argv}")

        run_id = _value(argv, "--run-id")
        require(run_id is not None and run_id.startswith(TASK.lower() + "-"),
                f"controller run identity does not use the project format: {run_id!r}")
        require(run_id != SCHEDULER_RUN_ID, "controller reused a worker run identity")
        require(run_id in completed.stdout,
                f"the operator was not shown the autonomous run ID: {completed.stdout}")
        require("-AutonomousRunId" in completed.stdout,
                f"the operator was not told how to resume: {completed.stdout}")

        # The receipt probe still runs first, and carries the same identity.
        probes = [a for a in _calls(records, AUTONOMOUS_SCRIPT) if "--completion-probe" in a]
        require(len(probes) == 1, f"expected exactly one completion probe: {probes}")
        require(_value(probes[0], "--run-id") == run_id, "probe identity differed")

        # A second launch mints a different durable identity rather than
        # silently adopting the previous run.
        log.unlink()
        _, records = _run(fixture, log, ["-TaskId", TASK])
        require(_value(_real_controller_calls(records)[0], "--run-id") != run_id,
                "two launches produced the same autonomous run identity")

        # An explicitly supplied identity is validated and forwarded verbatim so
        # an interrupted run can be resumed on purpose.
        log.unlink()
        resume_id = "nsc-914-20260904t181500z-3f9ab2"
        completed, records = _run(
            fixture, log, ["-TaskId", TASK, "-AutonomousRunId", resume_id]
        )
        require(completed.returncode == 0, f"resume failed: {completed}")
        argv = _real_controller_calls(records)[0]
        require(_value(argv, "--run-id") == resume_id,
                f"an explicit autonomous run identity was not forwarded: {argv}")


def test_the_top_level_path_never_invokes_the_direct_pipeline_agent() -> None:
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture, log, ["-TaskId", TASK, "-ExecutionProvider", "claude"]
        )
        require(completed.returncode == 0, f"delegation failed: {completed}")
        require(not _calls(records, DIRECT_SCRIPT),
                "the architect-managed path invoked run_pipeline_agent.py")
        require(not _calls(records, PREFLIGHT_SCRIPT),
                "the architect-managed path re-ran the direct-worker admission preflight")
        # The controller legitimately checks GitHub and Docker after its own
        # completed-receipt probe. What must never happen is this launcher
        # forcing either call ahead of that probe.
        probe_index = next(
            index
            for index, record in enumerate(records)
            if record["tool"] == "python" and "--completion-probe" in record["argv"]
        )
        before_probe = {record["tool"] for record in records[:probe_index]}
        require("gh" not in before_probe,
                f"GitHub was called before the controller receipt probe: {records[:probe_index]}")
        require("docker" not in before_probe,
                f"Docker was called before the controller receipt probe: {records[:probe_index]}")


# --------------------------------- 3 and 4: the scheduler child stays direct


def _scheduler_arguments() -> list[str]:
    return [
        "-TaskId", TASK,
        "-Mode", "openai",
        "-Source", str(ROOT),
        "-CheckoutRoot", str(ROOT),
        "-WorkerId", "worker-1",
        "-ExecutionProvider", "claude",
        "-MaxTurns", "96",
        "-HumanActionWaitMinutes", "0",
        "-OutputRoot", str(ROOT / "Pipeline" / "ExecutionCrew" / "outputs"),
        "-RunId", SCHEDULER_RUN_ID,
        "-AdmissionSourceHead", SCHEDULER_HEAD,
        "-TaskContractSha256", SCHEDULER_CONTRACT_SHA,
        "-AdmissionIssueNumber", "77",
        "-Model", "supervisor-model",
        "-SupervisorReasoningEffort", "high",
        "-ExecutionModel", "routed-execution-model",
        "-ExecutionReasoningEffort", "low",
        "-CrewProfile", "lean",
        "-ValidationProfile", "targeted",
        "-EnableExecutionSessionPool",
    ]


def test_a_scheduler_child_with_a_run_id_stays_on_the_direct_worker_path() -> None:
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(fixture, log, _scheduler_arguments())
        require(completed.returncode == 0, f"scheduler child failed: {completed}")
        require(not _calls(records, AUTONOMOUS_SCRIPT),
                "a scheduler-spawned worker recursed into the autonomous controller")
        direct = _calls(records, DIRECT_SCRIPT)
        require(len(direct) == 1, f"expected exactly one direct worker run: {direct}")
        require(_value(direct[0], "--run-id") == SCHEDULER_RUN_ID,
                f"the scheduler run identity was not preserved: {direct[0]}")


def test_the_scheduler_child_receives_every_decision_without_recomputation() -> None:
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(fixture, log, _scheduler_arguments())
        require(completed.returncode == 0, f"scheduler child failed: {completed}")
        argv = _calls(records, DIRECT_SCRIPT)[0]
        expected = {
            "--task-id": TASK,
            "--run-id": SCHEDULER_RUN_ID,
            "--admission-source-head": SCHEDULER_HEAD,
            "--task-contract-sha256": SCHEDULER_CONTRACT_SHA,
            "--admission-issue-number": "77",
            "--worker-id": "worker-1",
            "--execution-provider": "claude",
            "--model": "supervisor-model",
            "--supervisor-reasoning-effort": "high",
            "--execution-model": "routed-execution-model",
            "--execution-reasoning-effort": "low",
            "--crew-profile": "lean",
            "--validation-profile": "targeted",
            "--max-turns": "96",
        }
        for flag, value in expected.items():
            require(_value(argv, flag) == value,
                    f"scheduler decision {flag} was not preserved exactly: {argv}")
        require("--enable-execution-session-pool" in argv,
                f"scheduler-issued pool authority was dropped: {argv}")
        require("--checkout-root" in argv, f"checkout identity was dropped: {argv}")


# ------------------------------------------- 5: the direct/manual escape hatch


def test_direct_manual_keeps_the_conservative_defaults_and_no_pool_authority() -> None:
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture, log,
            ["-TaskId", TASK, "-ExecutionProvider", "claude", "-DirectManual"],
        )
        require(completed.returncode == 0, f"direct/manual failed: {completed}")
        require(not _calls(records, AUTONOMOUS_SCRIPT),
                "DirectManual delegated to the autonomous controller")
        direct = _calls(records, DIRECT_SCRIPT)
        require(len(direct) == 1, f"expected exactly one direct worker run: {direct}")
        argv = direct[0]
        # Supplying neither profile is what makes ExecutionCrew choose
        # full/full_relevant, which is the previous conservative default.
        require("--crew-profile" not in argv and "--validation-profile" not in argv,
                f"DirectManual no longer defers to the conservative default: {argv}")
        require("--enable-execution-session-pool" not in argv,
                f"DirectManual claimed ExecutionCrew pool authority: {argv}")
        require("--run-id" not in argv,
                f"DirectManual fabricated a scheduler run identity: {argv}")
        require(_calls(records, PREFLIGHT_SCRIPT),
                "DirectManual skipped the existing direct-worker admission preflight")

        # The existing route/profile override behavior is preserved.
        log.unlink()
        completed, records = _run(
            fixture, log,
            ["-TaskId", TASK, "-DirectManual", "-CrewProfile", "standard",
             "-ValidationProfile", "task_specific"],
        )
        require(completed.returncode == 0, f"direct/manual override failed: {completed}")
        argv = _calls(records, DIRECT_SCRIPT)[0]
        require(_value(argv, "--crew-profile") == "standard"
                and _value(argv, "--validation-profile") == "task_specific",
                f"DirectManual dropped an explicit profile override: {argv}")


# --------------------------------------------------- 6 and 7: synthetic evidence


def test_synthetic_evidence_is_forwarded_only_when_explicitly_requested() -> None:
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        _, records = _run(fixture, log, ["-TaskId", TASK])
        argv = _real_controller_calls(records)[0]
        require("--enable-synthetic-evidence" not in argv,
                f"synthetic evidence was enabled without being requested: {argv}")
        require("--disable-synthetic-evidence" not in argv,
                f"an unrequested run overrode the persisted setting: {argv}")

        log.unlink()
        _, records = _run(fixture, log, ["-TaskId", TASK, "-EnableSyntheticEvidence"])
        argv = _real_controller_calls(records)[0]
        require("--enable-synthetic-evidence" in argv,
                f"an explicit synthetic-evidence request was dropped: {argv}")

        # An explicit opt-out can never become an opt-in. `-File` cannot carry
        # `-Switch:$false`, so this uses the interactive `-Command` form.
        log.unlink()
        completed, records = _run_command(
            fixture,
            log,
            f"& '{LAUNCHER}' -TaskId {TASK} -EnableSyntheticEvidence:$false"
            "; exit $LASTEXITCODE",
        )
        require(completed.returncode == 0, f"explicit opt-out failed: {completed}")
        controller = _real_controller_calls(records)
        require(len(controller) == 1, f"expected one controller run: {controller}")
        require("--enable-synthetic-evidence" not in controller[0],
                f"an explicit opt-out enabled synthetic evidence: {controller[0]}")


def test_the_committed_synthetic_evidence_guards_are_untouched() -> None:
    """The launcher forwards a flag; it never relaxes who may receive evidence."""
    from Pipeline.TaskReviewAgent import synthetic_gauntlet_approver as approver
    from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import PRESERVED_TASK_ID

    require(PRESERVED_TASK_ID == "NSC-042",
            f"the preserved task guard moved: {PRESERVED_TASK_ID}")

    with tempfile.TemporaryDirectory(prefix="synthetic-guard-") as text:
        source = Path(text)
        try:
            approver._require_gauntlet_task(source, PRESERVED_TASK_ID)
        except approver.SyntheticApprovalError as exc:
            require("real validation" in str(exc),
                    f"NSC-042 was refused for an unexpected reason: {exc}")
        else:
            raise AssertionError("NSC-042 was accepted for synthetic approval")

    # The production repository is refused before any GitHub or file work, and
    # a mismatched assertion is refused before that.
    source_text = (
        ROOT / "Pipeline" / "TaskReviewAgent" / "synthetic_gauntlet_approver.py"
    ).read_text(encoding="utf-8")
    require('raise SyntheticApprovalError("synthetic approval refuses production")'
            in source_text,
            "the production-repository refusal is no longer present")
    require("synthetic approval requires the exact canonical rehearsal repository"
            in source_text,
            "the private-rehearsal-only requirement is no longer present")

    # The controller pump never offers the preserved task to the approver.
    controller_source = (
        ROOT / "Pipeline" / "TaskReviewAgent" / "run_autonomous_graph.py"
    ).read_text(encoding="utf-8")
    require("issue.task_id != PRESERVED_TASK_ID" in controller_source,
            "the controller pump no longer excludes the preserved task")


# ------------------------------------------ 8: documented target-set closure


def test_the_target_set_expands_through_decomposition_children_only() -> None:
    """`--target-task-id` is expanded transitively through committed
    `decomposition_children`. `depends_on` is deliberately NOT expanded: an
    unmet dependency of a target is never pulled into run scope, it simply
    leaves the target undispatchable until it is delivered."""
    import dataclasses

    from Pipeline.TaskReviewAgent.architect_preflight import (
        DEFAULT_ARCHITECT_MAX_TURNS,
        DEFAULT_ARCHITECT_MIN_CONFIDENCE,
    )
    from Pipeline.TaskReviewAgent.autonomous_graph_run import (
        AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        DEFAULT_FALLBACK_SECONDS,
        AutonomousRunManifest,
        AutonomousRuntimeConfiguration,
        TaskObservation,
        _relevant_task_ids,
    )
    from Pipeline.TaskReviewAgent.polling_orchestrator import (
        DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS,
        DEFAULT_FATAL_DRAIN_SECONDS,
        DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL,
        DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES,
    )

    # The controller's committed graph observation carries no dependency edge
    # at all, which is the strongest available proof that the target set can
    # never expand through depends_on.
    observation_fields = {f.name for f in dataclasses.fields(TaskObservation)}
    require("decomposition_children" in observation_fields,
            f"the closure input changed shape: {sorted(observation_fields)}")
    require(not {"depends_on", "dependencies"} & observation_fields,
            f"the graph observation gained a dependency edge: {sorted(observation_fields)}")

    def observation(task_id: str, children=()) -> TaskObservation:
        return TaskObservation(
            task_id=task_id,
            conformance_state="conformant",
            decomposition_children=tuple(children),
        )

    tasks = {
        "NSC-900": observation("NSC-900", children=("NSC-901",)),
        "NSC-901": observation("NSC-901", children=("NSC-902",)),
        "NSC-902": observation("NSC-902"),
        "NSC-910": observation("NSC-910"),
        "NSC-920": observation("NSC-920"),
    }

    def manifest(targets, exclusions=()) -> AutonomousRunManifest:
        return AutonomousRunManifest(
            schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
            run_id="closure-fixture",
            source_repository=str(ROOT),
            github_repository=REPOSITORY,
            runtime_configuration=AutonomousRuntimeConfiguration(
                execution_provider=None,
                execution_model=None,
                execution_max_turns=120,
                architect_provider="claude",
                architect_model=None,
                architect_max_turns=DEFAULT_ARCHITECT_MAX_TURNS,
                architect_min_confidence=DEFAULT_ARCHITECT_MIN_CONFIDENCE,
                architect_max_invocations_per_poll=(
                    DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL
                ),
                architect_min_reanalysis_seconds=(
                    DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS
                ),
                max_consecutive_observation_failures=(
                    DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES
                ),
                fatal_drain_seconds=DEFAULT_FATAL_DRAIN_SECONDS,
                fallback_seconds=DEFAULT_FALLBACK_SECONDS,
                synthetic_evidence_enabled=False,
            ),
            initial_source_commit="c" * 40,
            initial_source_tree="d" * 40,
            target_task_ids=tuple(targets),
            excluded_task_ids=tuple(exclusions),
            max_capacity=1,
        )

    relevant, missing = _relevant_task_ids(manifest(("NSC-900",)), tasks)
    require(relevant == ("NSC-900", "NSC-901", "NSC-902"),
            f"decomposition-children closure is not exact: {relevant}")
    require("NSC-910" not in relevant,
            f"a task reachable only by depends_on entered run scope: {relevant}")
    require("NSC-920" not in relevant, f"an unrelated task entered scope: {relevant}")
    require(missing == (), f"unexpected missing tasks: {missing}")

    excluded, _ = _relevant_task_ids(
        manifest(("NSC-900",), exclusions=("NSC-901",)), tasks
    )
    require(excluded == ("NSC-900",),
            f"an exclusion did not prune its own subtree: {excluded}")

    # Deterministic and sorted on repeated evaluation.
    require(
        _relevant_task_ids(manifest(("NSC-900",)), tasks)
        == _relevant_task_ids(manifest(("NSC-900",)), tasks),
        "closure evaluation is not deterministic",
    )

    documented = (ROOT / "Pipeline" / "TaskReviewAgent" / "README.md").read_text(
        encoding="utf-8"
    )
    require("decomposition children" in documented.casefold(),
            "the target-set closure is not documented in the TaskReviewAgent README")


# ------------------------------------ 9: contradictory combinations fail early


def test_contradictory_options_fail_before_either_pipeline_starts() -> None:
    contradictions = (
        ["-TaskId", TASK, "-DirectManual", "-RunId", SCHEDULER_RUN_ID,
         "-AdmissionSourceHead", SCHEDULER_HEAD,
         "-TaskContractSha256", SCHEDULER_CONTRACT_SHA],
        ["-TaskId", TASK, "-RunId", SCHEDULER_RUN_ID,
         "-AdmissionSourceHead", SCHEDULER_HEAD,
         "-TaskContractSha256", SCHEDULER_CONTRACT_SHA,
         "-AutonomousRunId", "resume-me"],
        ["-TaskId", TASK, "-DirectManual", "-AutonomousRunId", "resume-me"],
        ["-TaskId", TASK, "-DirectManual", "-EnableSyntheticEvidence"],
        ["-TaskId", TASK, "-DirectManual", "-MaxWorkers", "2"],
        ["-TaskId", TASK, "-DirectManual", "-EnableExecutionSessionPool"],
        ["-AutonomousRunId", "resume-me"],
        ["-TaskId", TASK, "-Mode", "observe", "-EnableSyntheticEvidence"],
        ["-TaskId", TASK, "-CrewProfile", "lean", "-ValidationProfile", "targeted"],
        ["-TaskId", TASK, "-EnableExecutionSessionPool"],
        ["-TaskId", TASK, "-Model", "supervisor-model"],
        ["-TaskId", TASK, "-AutonomousRunId", "Not A Valid Run Id"],
    )
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        for arguments in contradictions:
            if log.is_file():
                log.unlink()
            completed, records = _run(fixture, log, list(arguments))
            require(completed.returncode != 0,
                    f"contradiction was accepted: {arguments} -> {completed}")
            require(not _calls(records, AUTONOMOUS_SCRIPT),
                    f"a controller ran despite {arguments}")
            require(not _calls(records, DIRECT_SCRIPT),
                    f"a direct worker ran despite {arguments}")


# ------------------------------------------------ 10: exit-code propagation


def test_controller_exit_codes_propagate_through_the_launcher() -> None:
    with fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        # EXIT_DEADLOCK from run_autonomous_graph.py must not be flattened.
        completed, records = _run(
            fixture, log, ["-TaskId", TASK], NSC_STUB_CONTROLLER_EXIT="3"
        )
        require(completed.returncode == 3,
                f"controller exit code was masked: {completed}")
        require(len(_real_controller_calls(records)) == 1,
                "a failing controller was retried")
        require("exit code 3" in completed.stderr,
                f"the operator was not told the controller stopped: {completed.stderr}")

        log.unlink()
        completed, records = _run(
            fixture, log, ["-TaskId", TASK], NSC_STUB_CONTROLLER_EXIT="0"
        )
        require(completed.returncode == 0, f"a complete run did not succeed: {completed}")

        # A run whose graph-complete receipt already exists returns success from
        # the probe alone, without a second controller invocation.
        log.unlink()
        completed, records = _run(
            fixture, log, ["-TaskId", TASK], NSC_STUB_PROBE_EXIT="0"
        )
        require(completed.returncode == 0, f"an already-complete run failed: {completed}")
        require(not _real_controller_calls(records),
                "an already-complete run started the scheduler anyway")


# --------------------------------------------------------------------- main


def main() -> int:
    if os.name != "nt":
        print("architect managed launcher smoke test: SKIP (requires Windows)")
        return 0
    require(LAUNCHER.is_file(), f"launcher missing: {LAUNCHER}")
    require(CONTROLLER_LAUNCHER.is_file(), f"controller missing: {CONTROLLER_LAUNCHER}")
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_")
        and callable(value)
        and getattr(value, "__module__", None) == __name__
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            FAILURES.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    if FAILURES:
        print(f"architect managed launcher smoke test: FAIL ({len(FAILURES)})")
        return 1
    print("architect managed launcher smoke test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
