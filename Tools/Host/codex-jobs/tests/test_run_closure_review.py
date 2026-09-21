#!/usr/bin/env python
"""The Codex closure runner, driven end to end with a fake provider.

Run:
    python -B test_run_closure_review.py

`run_closure_review.sh` is the entry point that actually produces closure reviews,
and nothing exercised it. Its new job-record arguments, its removed absolute
helper fallbacks and its ordering were only ever argued for in review.

The fixture DEPLOYS the tools: `Tools/Host` is copied to `<tmp>/tools`, which is
the layout `nsc_paths` derives a workspace from, so the script resolves its own
roots exactly as a deployment does rather than being told them. That also means
this test covers the relocation property for the shell path - it never touches the
real canonical checkout, the real work root or the real Codex binary.

No provider is called and nothing is paid for: `NSC_CODEX_EXE` points at a small
Python script that writes a prepared result to the path the runner asks for.

Skipped where bash is unavailable, which keeps it honest on a machine that cannot
run the thing under test rather than passing vacuously.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOST = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HOST))
sys.path.insert(0, str(HOST / "jobs"))
import closure_record  # noqa: E402

TASK = "NSC-001"
BASH = shutil.which("bash")

# What the fake Codex writes, with the contract hash filled in by the runner's
# own fixture. `{...}` placeholders are substituted, not formatted, so the JSON
# braces survive.
FAKE_CODEX = '''
import json, pathlib, sys
args = sys.argv[1:]
# The resolver validates a candidate by asking for --version before the runner
# will use it, so the fake answers that too. Without this the runner exits 2 at
# setup - and the failure-path tests then "passed" on the wrong exit code.
if "--version" in args:
    print("codex-cli 0.155.0-fake")
    sys.exit(0)
out = None
for i, a in enumerate(args):
    if a == "--output-last-message":
        out = pathlib.Path(args[i + 1])
sys.stdin.read()
result = pathlib.Path(r"__RESULT__").read_text(encoding="utf-8")
out.write_text(result, encoding="utf-8")
sys.exit(__EXIT__)
'''


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {done.stderr}")
    return done.stdout.strip()


@unittest.skipIf(BASH is None, "bash is not available on this machine")
class TheCodexRunner(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

        # A deployment: <tmp>/tools is what nsc_paths derives its workspace from.
        self.tools = self.tmp / "tools"
        for part in ("nsc_paths.py", "review_result.py"):
            (self.tools).mkdir(parents=True, exist_ok=True)
            shutil.copy2(HOST / part, self.tools / part)
        for family in ("jobs", "codex-jobs"):
            (self.tools / family).mkdir(parents=True, exist_ok=True)
        for name in ("resolve_codex.py", "check_job_result.py",
                     "check_closure_report.py", "closure_record.py"):
            shutil.copy2(HOST / "jobs" / name, self.tools / "jobs" / name)
        shutil.copy2(HOST / "codex-jobs" / "run_closure_review.sh",
                     self.tools / "codex-jobs" / "run_closure_review.sh")

        # The canonical checkout this deployment owns: <workspace>/NoSafeCircle.
        self.repo = self.tmp / "NoSafeCircle"
        (self.repo / "Tasks").mkdir(parents=True)
        (self.repo / "Tasks" / f"{TASK}.yaml").write_bytes(
            b'{"id": "NSC-001", "contract_revision": 1}\n')
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "fixture")
        git(self.repo, "config", "user.email", "fixture@nosafecircle.invalid")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "first")
        self.previous = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "Tasks" / f"{TASK}.yaml").write_bytes(
            b'{"id": "NSC-001", "contract_revision": 2}\n')
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "revision 2")
        self.commit = git(self.repo, "rev-parse", "HEAD")
        self.contract = subprocess.run(
            ["git", "-C", str(self.repo), "show", f"{self.commit}:Tasks/{TASK}.yaml"],
            capture_output=True).stdout

        self.work = self.tmp / "work"
        (self.work / "codex-jobs").mkdir(parents=True)
        (self.work / "codex-jobs" / "JOB.prompt.md").write_text(
            "Review the revision.\n", encoding="utf-8")

    def result_json(self, **overrides) -> str:
        body = {
            "schema_version": 1, "review_kind": "closure", "task_id": TASK,
            "reviewed_artifact_kind": "contract",
            "reviewed_artifact_sha256": closure_record.sha256(self.contract),
            "review_status": "complete", "recommendation": "commit_contract",
            "report_markdown": "Ledger:\n- L1: RESOLVED.",
        }
        body.update(overrides)
        return json.dumps(body)

    def run_job(self, *, result: str | None = None, exit_code: int = 0) -> int:
        prepared = self.tmp / "prepared.json"
        prepared.write_text(result if result is not None else self.result_json(),
                            encoding="utf-8")
        fake = self.tmp / "fake_codex.py"
        fake.write_text(
            FAKE_CODEX.replace("__RESULT__", str(prepared).replace("\\", "\\\\"))
                      .replace("__EXIT__", str(exit_code)), encoding="utf-8")
        shim = self.tmp / "codex.cmd"
        shim.write_text(f'@echo off\r\n"{sys.executable}" -B "{fake}" %*\r\n',
                        encoding="utf-8")

        env = {**os.environ,
               "NSC_WORK": str(self.work),
               "NSC_CODEX_EXE": str(shim),
               "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run(
            [BASH, str(self.tools / "codex-jobs" / "run_closure_review.sh"),
             "JOB", TASK, self.commit, self.previous],
            capture_output=True, text=True, env=env)
        self.output = done.stdout + done.stderr
        return done.returncode

    @property
    def result_path(self) -> Path:
        return self.work / "codex-jobs" / "JOB.result.json"

    def test_a_completed_review_round_trips_to_the_shared_reader(self):
        code = self.run_job()
        self.assertEqual(code, 0, self.output)
        job = closure_record.read_job(
            self.result_path, task_id=TASK,
            reviewed_artifact_sha256=closure_record.sha256(self.contract))
        self.assertEqual(job.result.recommendation, "commit_contract")
        self.assertEqual(job.record["provider"], "codex")
        # Codex reports no is_error; the record says so rather than inventing one.
        self.assertIsNone(job.record["is_error"])

    def test_a_completed_revise_is_a_success(self):
        code = self.run_job(result=self.result_json(recommendation="revise"))
        self.assertEqual(code, 0, self.output)
        job = closure_record.read_job(
            self.result_path, task_id=TASK,
            reviewed_artifact_sha256=closure_record.sha256(self.contract))
        self.assertEqual(job.result.recommendation, "revise")

    def test_a_failed_provider_publishes_no_record(self):
        code = self.run_job(exit_code=9)
        self.assertNotEqual(code, 0)
        self.assertFalse(closure_record.metadata_path(self.result_path).exists(),
                         self.output)

    def test_prose_instead_of_a_result_publishes_no_record(self):
        code = self.run_job(result="Final recommendation: commit_contract\n")
        self.assertNotEqual(code, 0)
        self.assertFalse(closure_record.metadata_path(self.result_path).exists(),
                         self.output)

    def test_a_review_of_different_bytes_publishes_no_record(self):
        code = self.run_job(result=self.result_json(
            reviewed_artifact_sha256="c" * 64))
        self.assertNotEqual(code, 0)
        self.assertFalse(closure_record.metadata_path(self.result_path).exists(),
                         self.output)

    def test_an_incomplete_review_publishes_no_record(self):
        code = self.run_job(result=self.result_json(
            review_status="incomplete", recommendation=None,
            report_markdown="Could not finish."))
        self.assertNotEqual(code, 0)
        self.assertFalse(closure_record.metadata_path(self.result_path).exists(),
                         self.output)

    def test_the_runner_finds_its_helpers_beside_itself(self):
        # The absolute fallbacks are gone, so this deployment must be
        # self-sufficient: nothing here exists at C:/NSC/tools or C:/nscrev.
        self.assertEqual(self.run_job(), 0, self.output)
        self.assertIn("[DONE]", self.output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
