#!/usr/bin/env python3
"""Windows launcher regressions for the supervisor session-pool activation gate.

Classification: temporary-fixture behavior tests. The real
`Start-GameTaskAgent.ps1` runs against stubbed `git`, `gh`, `docker`, and
`python` executables that record their exact argv and environment. No live
provider, Docker daemon, GitHub call, or tracked repository file is involved.

The claims are about real argument construction:

  * the operator's exact Codex resume control reaches the worker as one JSON
    array on `--supervisor-codex-resume-sandbox-argument`, and a single
    fragment stays an array rather than collapsing to a bare string;
  * the same decision is exported as `NSC_CODEX_RESUME_SANDBOX_ARGUMENT` so
    the architect controller and its scheduler-spawned workers inherit it;
  * with nothing supplied the gate is off: no argument is forwarded and the
    launcher says so instead of implying warm pooling;
  * a fragment `codex exec resume` cannot honour (`--sandbox`, `--last`, ...)
    fails before any pipeline starts.
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

from Pipeline.TaskReviewAgent.tests import architect_managed_launcher_smoke_test as base  # noqa: E402


DIRECT_SCRIPT = base.DIRECT_SCRIPT
AUTONOMOUS_SCRIPT = base.AUTONOMOUS_SCRIPT
FLAG = "--supervisor-codex-resume-sandbox-argument"
ENVIRONMENT = "NSC_CODEX_RESUME_SANDBOX_ARGUMENT"
CONTROL = ["-c", 'sandbox_mode="danger-full-access"']

# The base stub records argv only; this variant also records the resume
# control the process inherited, which is the whole point of the export.
STUB_SOURCE = base.STUB_SOURCE.replace(
    "$Record = [ordered]@{ tool = $Tool; argv = $Arguments }",
    "$Record = [ordered]@{ tool = $Tool; argv = $Arguments; resume = $env:NSC_CODEX_RESUME_SANDBOX_ARGUMENT }",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_stub_path(fixture: Path) -> Path:
    log = fixture / "invocations.jsonl"
    for tool in ("git", "gh", "docker", "python"):
        (fixture / f"{tool}.ps1").write_text(
            STUB_SOURCE.replace("@TOOL@", f"'{tool}'"), encoding="utf-8", newline="\r\n"
        )
    return log


def _run(fixture: Path, log: Path, command: str):
    environment = base._environment(fixture, log)
    environment.pop(ENVIRONMENT, None)
    environment.pop("NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS", None)
    completed = subprocess.run(
        ("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command),
        cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, check=False, timeout=180.0,
    )
    records = []
    if log.is_file():
        for line in log.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return completed, records


def _scheduler_command(extra: str = "") -> str:
    return (
        f"& '{base.LAUNCHER}' -TaskId {base.TASK} -RunId {base.SCHEDULER_RUN_ID} "
        f"-AdmissionSourceHead {base.SCHEDULER_HEAD} -TaskContractSha256 {base.SCHEDULER_CONTRACT_SHA} "
        f"-WorkerId worker-1 -ExecutionProvider claude -CheckoutRoot '{ROOT}' {extra}; exit $LASTEXITCODE"
    )


def _direct_calls(records):
    return base._calls(records, DIRECT_SCRIPT)


def test_operator_control_reaches_the_worker_as_one_json_array() -> None:
    with base.fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture, log,
            _scheduler_command("-CodexResumeSandboxArgument '-c','sandbox_mode=\"danger-full-access\"' -SupervisorContextWindowTokens 400000"),
        )
        require(completed.returncode == 0, f"launcher failed: {completed.stdout}\n{completed.stderr}")
        direct = _direct_calls(records)
        require(len(direct) == 1, f"expected one worker: {direct}")
        argv = direct[0]
        require(FLAG in argv, f"resume control was not forwarded: {argv}")
        require(json.loads(base._value(argv, FLAG)) == CONTROL, f"forwarded control differs: {base._value(argv, FLAG)}")
        require(base._value(argv, "--supervisor-context-window-tokens") == "400000", f"context window was not forwarded: {argv}")
        worker = [record for record in records if record["tool"] == "python" and os.path.basename(record["argv"][0]) == DIRECT_SCRIPT][0]
        require(json.loads(worker["resume"]) == CONTROL, f"worker did not inherit {ENVIRONMENT}: {worker}")
        require("warm Codex resume ACTIVE" in completed.stdout, completed.stdout)


def test_a_single_fragment_stays_a_json_array() -> None:
    with base.fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(
            fixture, log, _scheduler_command("-CodexResumeSandboxArgument '--profile=verified-resume'"),
        )
        require(completed.returncode == 0, f"launcher failed: {completed.stdout}\n{completed.stderr}")
        argv = _direct_calls(records)[0]
        require(json.loads(base._value(argv, FLAG)) == ["--profile=verified-resume"], base._value(argv, FLAG))


def test_nothing_supplied_leaves_the_gate_off_and_says_so() -> None:
    with base.fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        completed, records = _run(fixture, log, _scheduler_command())
        require(completed.returncode == 0, f"launcher failed: {completed.stdout}\n{completed.stderr}")
        argv = _direct_calls(records)[0]
        require(FLAG not in argv and "--supervisor-context-window-tokens" not in argv, f"gate-off worker must receive no resume control: {argv}")
        require("warm Codex resume OFF" in completed.stdout and "ACTIVE" not in completed.stdout, completed.stdout)


def test_inherited_environment_is_forwarded_to_the_worker() -> None:
    with base.fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        command = f"$env:{ENVIRONMENT} = '{json.dumps(CONTROL)}'; " + _scheduler_command()
        completed, records = _run(fixture, log, command)
        require(completed.returncode == 0, f"launcher failed: {completed.stdout}\n{completed.stderr}")
        argv = _direct_calls(records)[0]
        require(json.loads(base._value(argv, FLAG)) == CONTROL, f"inherited control was not forwarded: {argv}")


def test_top_level_architect_path_exports_the_control_to_the_controller() -> None:
    with base.fixture_dir() as text:
        fixture = Path(text)
        log = _write_stub_path(fixture)
        command = (
            f"& '{base.LAUNCHER}' -TaskId {base.TASK} -ConfirmRepository {base.REPOSITORY} "
            f"-CodexResumeSandboxArgument '-c','sandbox_mode=\"danger-full-access\"'; exit $LASTEXITCODE"
        )
        completed, records = _run(fixture, log, command)
        require(completed.returncode == 0, f"launcher failed: {completed.stdout}\n{completed.stderr}")
        controllers = [
            record for record in records
            if record["tool"] == "python" and os.path.basename(record["argv"][0]) == AUTONOMOUS_SCRIPT
            and "--completion-probe" not in record["argv"]
        ]
        require(len(controllers) == 1, f"expected one controller run: {controllers}")
        require(json.loads(controllers[0]["resume"]) == CONTROL, f"controller did not inherit the control: {controllers[0]}")
        require("warm Codex resume ACTIVE" in completed.stdout, completed.stdout)


def test_fragments_resume_cannot_honour_fail_before_any_pipeline() -> None:
    for fragment in ("'--sandbox','danger-full-access'", "'--last'", "'-s','danger-full-access'", "'--ephemeral'", "''"):
        with base.fixture_dir() as text:
            fixture = Path(text)
            log = _write_stub_path(fixture)
            completed, records = _run(fixture, log, _scheduler_command(f"-CodexResumeSandboxArgument {fragment}"))
            require(completed.returncode != 0, f"{fragment} was accepted: {completed.stdout}")
            require(not _direct_calls(records), f"{fragment}: the worker ran anyway")
            require("CodexResumeSandboxArgument" in completed.stderr + completed.stdout, f"{fragment}: {completed.stderr}")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"supervisor pool launcher smoke test: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
