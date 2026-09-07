#!/usr/bin/env python3
"""Behavioral smoke test for the minimal pre-launch ILPP PID cleanup."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "Pipeline/Testing/run_unity_tests_clean.ps1"
LOG_HYGIENE = ROOT / "Pipeline/Testing/unity_log_hygiene.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path, check: bool = True, env=None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def create_project(root: Path) -> Path:
    project = root / "project"
    (project / "ProjectSettings").mkdir(parents=True)
    (project / "Pipeline/TaskReviewAgent").mkdir(parents=True)
    (project / "Pipeline/Testing").mkdir(parents=True)
    (project / "ProjectSettings/ProjectVersion.txt").write_text(
        "m_EditorVersion: 6000.0.55f1\n", encoding="utf-8", newline="\n"
    )
    (project / ".gitignore").write_text(
        "/Library/\n/Temp/\n", encoding="utf-8", newline="\n"
    )
    shutil.copyfile(
        ROOT / "Pipeline/TaskReviewAgent/safe_unity_churn.py",
        project / "Pipeline/TaskReviewAgent/safe_unity_churn.py",
    )
    shutil.copyfile(
        ROOT / "Pipeline/Testing/unity_log_hygiene.py",
        project / "Pipeline/Testing/unity_log_hygiene.py",
    )
    run("git", "init", "-b", "main", str(project), cwd=root)
    run("git", "-C", str(project), "config", "user.name", "ILPP Smoke", cwd=root)
    run(
        "git",
        "-C",
        str(project),
        "config",
        "user.email",
        "ilpp-smoke@example.invalid",
        cwd=root,
    )
    run("git", "-C", str(project), "add", ".", cwd=root)
    run("git", "-C", str(project), "commit", "-m", "Create ILPP smoke fixture", cwd=root)
    return project


def create_controller(root: Path) -> tuple[Path, Path]:
    """Commit the real wrapper in a controller repo separate from its target."""

    controller = root / "controller"
    runner = controller / "Pipeline/Testing/run_unity_tests_clean.ps1"
    runner.parent.mkdir(parents=True)
    shutil.copyfile(RUNNER, runner)
    shutil.copyfile(LOG_HYGIENE, runner.parent / "unity_log_hygiene.py")
    run("git", "init", "-b", "main", str(controller), cwd=root)
    run("git", "-C", str(controller), "config", "user.name", "Runner Identity Smoke", cwd=root)
    run(
        "git",
        "-C",
        str(controller),
        "config",
        "user.email",
        "runner-identity-smoke@example.invalid",
        cwd=root,
    )
    run("git", "-C", str(controller), "add", ".", cwd=root)
    run(
        "git",
        "-C",
        str(controller),
        "commit",
        "-m",
        "Commit trusted controller runner",
        cwd=root,
    )
    return controller, runner


def create_fake_unity(root: Path) -> Path:
    executable = root / "fake-unity.cmd"
    executable.write_text(
        r"""@echo off
setlocal
set "PROJECT="
set "RESULTS="
set "LOG="
:parse
if "%~1"=="" goto execute
if /I "%~1"=="-projectPath" (
  set "PROJECT=%~2"
  shift
)
if /I "%~1"=="-testResults" (
  set "RESULTS=%~2"
  shift
)
if /I "%~1"=="-logFile" (
  set "LOG=%~2"
  shift
)
shift
goto parse
:execute
>"%NSC_FAKE_UNITY_SENTINEL%" echo entered
if exist "%PROJECT%\Library\ilpp.pid" (
  >"%NSC_FAKE_UNITY_OBSERVATION%" echo marker-present
  exit /b 91
)
>"%NSC_FAKE_UNITY_OBSERVATION%" echo marker-absent
>"%RESULTS%" echo ^<test-run result="Passed" total="1" passed="1" failed="0" skipped="0"^>^</test-run^>
>"%LOG%" echo Fake Unity validation passed.
exit /b 0
""",
        encoding="ascii",
        newline="\r\n",
    )
    return executable


@contextmanager
def hold_without_delete_sharing(path: Path):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = create_file(
        str(path),
        0x80000000,
        0x00000001 | 0x00000002,
        None,
        3,
        0x00000080,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def invoke_runner(
    project: Path,
    executable: Path,
    root: Path,
    *,
    runner: Path = RUNNER,
    runner_root: Path = ROOT,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    sentinel = root / "unity-entered.txt"
    observation = root / "unity-observation.txt"
    sentinel.unlink(missing_ok=True)
    observation.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["TEMP"] = str(root / "temp")
    environment["TMP"] = str(root / "temp")
    environment["NSC_FAKE_UNITY_SENTINEL"] = str(sentinel)
    environment["NSC_FAKE_UNITY_OBSERVATION"] = str(observation)
    (root / "temp").mkdir(exist_ok=True)
    result = run(
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(runner),
        "-TestPlatform",
        "EditMode",
        "-TestFilter",
        "Synthetic.Tests.One",
        "-UnityExecutable",
        str(executable),
        "-ProjectPath",
        str(project),
        cwd=runner_root,
        check=False,
        env=environment,
    )
    return result, sentinel, observation


def output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()


def validation_manifest(result: subprocess.CompletedProcess[str]) -> dict:
    match = re.search(r"(?im)^Validation manifest:\s*(.+?)\s*$", output(result))
    require(match is not None, f"wrapper omitted validation manifest path:\n{output(result)}")
    path = Path(match.group(1).strip())
    require(path.is_file(), f"validation manifest does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "validation manifest is not a JSON object")
    return value


def main() -> int:
    if os.name != "nt":
        print("Unity ILPP PID cleanup smoke test: SKIP (Windows only)")
        return 0
    runner_source = RUNNER.read_text(encoding="utf-8")
    require(
        '"${runnerSourceCommit}^{tree}"' in runner_source,
        "runner source tree is not derived from its already captured commit",
    )
    with tempfile.TemporaryDirectory(prefix="nsc-unity-ilpp-minimal-") as temporary:
        root = Path(temporary)
        project = create_project(root)
        controller, controller_runner = create_controller(root)
        executable = create_fake_unity(root)
        marker = project / "Library/ilpp.pid"

        missing, sentinel, observation = invoke_runner(project, executable, root)
        require(missing.returncode == 0, f"missing marker failed:\n{output(missing)}")
        require(sentinel.is_file(), "Unity did not start when the marker was missing")
        require(observation.read_text(encoding="ascii").strip() == "marker-absent", "wrong missing observation")
        require(not os.path.lexists(marker), "missing marker was recreated")
        print("PASS missing marker: Unity launched and validation passed")

        marker.parent.mkdir(exist_ok=True)
        marker.write_text(str(os.getpid()), encoding="ascii")
        stale, sentinel, observation = invoke_runner(project, executable, root)
        require(stale.returncode == 0, f"stale marker failed:\n{output(stale)}")
        require(sentinel.is_file(), "Unity did not start after stale marker cleanup")
        require(observation.read_text(encoding="ascii").strip() == "marker-absent", "Unity observed stale marker")
        require(not os.path.lexists(marker), "stale marker survived cleanup")
        print(f"PASS stale live-PID marker: removed before Unity start (pid={os.getpid()})")

        marker.write_text(str(os.getpid()), encoding="ascii")
        with hold_without_delete_sharing(marker):
            locked, sentinel, _ = invoke_runner(project, executable, root)
            require(locked.returncode == 20, f"wrong locked-marker result:\n{output(locked)}")
            require(not sentinel.exists(), "Unity started after marker removal failed")
            require(marker.is_file(), "locked marker unexpectedly disappeared")
        require("ilpp.pid" in output(locked), f"locked failure omitted marker path:\n{output(locked)}")
        marker.unlink()
        print("PASS locked marker: exit=20 and Unity launch was refused")

        # Make the historical target helper unusable while keeping its checkout
        # clean. The controller-owned runner must use the helper committed beside
        # itself; resolving this through ProjectPath would fail this execution.
        (project / "Pipeline/Testing/unity_log_hygiene.py").write_text(
            "raise SystemExit(97)\n",
            encoding="utf-8",
            newline="\n",
        )
        run("git", "-C", str(project), "add", ".", cwd=root)
        run(
            "git",
            "-C",
            str(project),
            "commit",
            "-m",
            "Poison historical target hygiene helper",
            cwd=root,
        )

        identified, sentinel, observation = invoke_runner(
            project,
            executable,
            root,
            runner=controller_runner,
            runner_root=controller,
        )
        require(identified.returncode == 0, f"runner identity case failed:\n{output(identified)}")
        require(sentinel.is_file(), "controller-owned runner did not start Unity")
        require(
            observation.read_text(encoding="ascii").strip() == "marker-absent",
            "controller-owned runner targeted the wrong project",
        )
        manifest = validation_manifest(identified)
        project_head = run("git", "-C", str(project), "rev-parse", "HEAD", cwd=root).stdout.strip()
        project_tree = run(
            "git", "-C", str(project), "rev-parse", "HEAD^{tree}", cwd=root
        ).stdout.strip()
        controller_head = run(
            "git", "-C", str(controller), "rev-parse", "HEAD", cwd=root
        ).stdout.strip()
        controller_tree = run(
            "git", "-C", str(controller), "rev-parse", "HEAD^{tree}", cwd=root
        ).stdout.strip()
        runner_sha256 = hashlib.sha256(controller_runner.read_bytes()).hexdigest()
        require(manifest.get("schema_version") == "1.1", str(manifest))
        require(
            manifest.get("validated_state", {}).get("commit") == project_head
            and manifest.get("validated_state", {}).get("tree") == project_tree,
            "manifest did not bind the separate target project's commit/tree",
        )
        require(
            manifest.get("runner")
            == {
                "path": "Pipeline/Testing/run_unity_tests_clean.ps1",
                "sha256": runner_sha256,
                "source_commit": controller_head,
                "source_tree": controller_tree,
            },
            f"manifest did not bind the actual controller runner: {manifest.get('runner')}",
        )
        require(
            controller_head != project_head and controller_tree != project_tree,
            "fixture did not separate controller and target Git identities",
        )
        print("PASS controller runner identity: executable bytes/source differ from target commit/tree")

    print("Unity ILPP PID cleanup smoke test: PASS (4 cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
