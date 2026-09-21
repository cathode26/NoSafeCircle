#!/usr/bin/env python
"""The Codex closure runner, driven end to end with a fake provider.

Run:
    python -B test_run_closure_review.py

`run_closure_review.sh` is the entry point that actually produces closure reviews,
and nothing exercised it. Its job-record arguments, its removed absolute helper
fallbacks and its ordering were only ever argued for in review.

The fixture DEPLOYS the tools: `Tools/Host` is copied to `<tmp>/tools`, which is
the layout `nsc_paths` derives a workspace from, so the script resolves its own
roots exactly as a deployment does rather than being told them. That also means
this test covers the relocation property for the shell path - it never touches the
real canonical checkout, the real work root or the real Codex binary.

No provider is called and nothing is paid for: `NSC_CODEX_EXE` points at a small
Python script that writes a prepared result to the path the runner asks for.

**Two things this file got wrong before, both of which made it lie.**

1. It ran `shutil.which("bash")`. On Windows that can select
   `C:/WINDOWS/system32/bash.exe`, the WSL launcher, which cannot take a Windows
   path and exits 127 before the script starts. Codex's audit hit exactly that:
   three positive cases failed and the four negative ones still "passed". Git
   Bash is chosen explicitly now, and a System32 result is refused rather than
   run.
2. Every negative case asserted only a non-zero exit, so ANY failure satisfied
   them - including the runner never starting. Each case now asserts the code the
   script documents (2 setup, 4 provider, 7 not an actionable review, 8 contract
   changed), and the fake provider writes a marker so a case can prove the
   provider did or did not reach its phase. The `--version` probe deliberately
   does NOT write the marker: being asked for a version is not having run.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
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

# Exit codes the script documents. Named so a test says which contract it checks.
OK = 0
SETUP_REFUSED = 2
PROVIDER_FAILED = 4
NOT_ACTIONABLE = 7
CONTRACT_CHANGED = 8

GIT_BASH = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
)


def sees_windows_paths(candidate: str) -> bool:
    """Can this bash stat a file by its Windows path?

    The one property this fixture needs, asked directly. The WSL launcher in
    System32 is called bash and answers `--version` with GNU bash when a distro
    is installed, so neither the name nor the version tells them apart - but it
    cannot see `C:\\Users\\...`, and Git Bash can. A stub at a Git path fails
    the same question for its own reason, which is the right answer too.
    """
    try:
        probe = subprocess.run(
            [candidate, "-c", f'test -f "{Path(__file__).resolve()}"'],
            capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def find_bash() -> str | None:
    """A bash that can run a Windows-path script, or nothing.

    `shutil.which` alone is not good enough on Windows: it can return the System32
    WSL launcher, which Codex's audit hit - three positive cases failed with exit
    127 and the four negative ones passed on that same failure. Git paths are
    tried first as a preference, then anything on PATH, and every candidate has to
    answer the probe above before it is used.
    """
    if os.name != "nt":
        return shutil.which("bash")
    for candidate in [*GIT_BASH, shutil.which("bash")]:
        if candidate and Path(candidate).is_file() and sees_windows_paths(candidate):
            return candidate
    return None


BASH = find_bash()

# The fake provider. It reads one JSON spec rather than having values pasted into
# its source, so a result containing quotes and braces cannot break the template.
FAKE_CODEX = '''
import json, pathlib, sys
args = sys.argv[1:]
# The resolver validates a candidate by asking for --version before the runner
# will use it, so the fake answers that too. This is BEFORE the marker: being
# probed is not having run, and a setup-refusal test relies on the difference.
if "--version" in args:
    print("codex-cli 0.155.0-fake")
    sys.exit(0)
spec = json.loads(pathlib.Path(r"__SPEC__").read_text(encoding="utf-8"))
pathlib.Path(spec["marker"]).write_text("the provider ran", encoding="utf-8")
out = cd = None
for i, a in enumerate(args):
    if a == "--output-last-message":
        out = pathlib.Path(args[i + 1])
    if a == "--cd":
        cd = pathlib.Path(args[i + 1])
sys.stdin.read()
if spec.get("tamper") is not None:
    (cd / "REVISED_CONTRACT.json").write_bytes(spec["tamper"].encode("utf-8"))
out.write_text(spec["result"], encoding="utf-8")
sys.exit(spec["exit"])
'''


def remove_tree(path: Path) -> None:
    """rmtree that survives a git clone on Windows.

    Git marks objects read-only, and `shutil.rmtree` raises on them. The first
    attempt here used `ignore_errors=True`, which turned that into a SILENT
    no-op - the clone stayed, the clone check refused the second run, and the
    test passed without the evidence check running at all.
    """
    def clear_readonly(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onexc=clear_readonly)


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {done.stderr}")
    return done.stdout.strip()


@unittest.skipIf(BASH is None, "Git Bash is required; the System32 WSL launcher "
                               "cannot run this fixture and is refused")
class TheCodexRunner(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

        # A deployment: <tmp>/tools is what nsc_paths derives its workspace from.
        self.tools = self.tmp / "tools"
        self.tools.mkdir(parents=True, exist_ok=True)
        for part in ("nsc_paths.py", "review_result.py"):
            shutil.copy2(HOST / part, self.tools / part)
        for family in ("jobs", "codex-jobs"):
            (self.tools / family).mkdir(parents=True, exist_ok=True)
        for name in ("resolve_codex.py", "check_job_result.py",
                     "check_closure_report.py", "closure_record.py"):
            shutil.copy2(HOST / "jobs" / name, self.tools / "jobs" / name)
        for name in ("run_closure_review.sh", "make_closure_prompt.py"):
            shutil.copy2(HOST / "codex-jobs" / name, self.tools / "codex-jobs" / name)
        shutil.copytree(HOST / "codex-jobs" / "templates",
                        self.tools / "codex-jobs" / "templates")

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
        self.marker = self.tmp / "provider-ran"

    # ---- fixtures -------------------------------------------------------

    def result_json(self, contract: bytes | None = None, **overrides) -> str:
        body = {
            "schema_version": 1, "review_kind": "closure", "task_id": TASK,
            "reviewed_artifact_kind": "contract",
            "reviewed_artifact_sha256": closure_record.sha256(
                self.contract if contract is None else contract),
            "review_status": "complete", "recommendation": "commit_contract",
            "report_markdown": "Ledger:\n- L1: RESOLVED.",
        }
        body.update(overrides)
        return json.dumps(body)

    def run_job(self, *, result: str | None = None, exit_code: int = 0,
                tamper: bytes | None = None, job: str = "JOB") -> int:
        spec = self.tmp / "spec.json"
        spec.write_text(json.dumps({
            "result": result if result is not None else self.result_json(),
            "marker": str(self.marker),
            "exit": exit_code,
            "tamper": None if tamper is None else tamper.decode("utf-8"),
        }), encoding="utf-8")
        fake = self.tmp / "fake_codex.py"
        fake.write_text(FAKE_CODEX.replace("__SPEC__", str(spec).replace("\\", "\\\\")),
                        encoding="utf-8")
        shim = self.tmp / "codex.cmd"
        shim.write_text(f'@echo off\r\n"{sys.executable}" -B "{fake}" %*\r\n',
                        encoding="utf-8")

        env = {**os.environ,
               "NSC_WORK": str(self.work),
               "NSC_CODEX_EXE": str(shim),
               "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run(
            [BASH, str(self.tools / "codex-jobs" / "run_closure_review.sh"),
             job, TASK, self.commit, self.previous],
            capture_output=True, text=True, env=env)
        self.output = done.stdout + done.stderr
        return done.returncode

    @property
    def result_path(self) -> Path:
        return self.work / "codex-jobs" / "JOB.result.json"

    def assertProviderRan(self):
        self.assertTrue(self.marker.exists(),
                        f"the provider never ran, so this case proves nothing about "
                        f"the phase it claims to test:\n{self.output}")

    def assertProviderDidNotRun(self):
        self.assertFalse(self.marker.exists(),
                         f"the provider ran; this refusal was supposed to come "
                         f"BEFORE launch:\n{self.output}")

    def assertNoRecord(self):
        self.assertFalse(closure_record.metadata_path(self.result_path).exists(),
                         f"a record was published:\n{self.output}")

    # ---- the review completes -------------------------------------------

    def test_a_completed_review_round_trips_to_the_shared_reader(self):
        self.assertEqual(self.run_job(), OK, self.output)
        self.assertProviderRan()
        job = closure_record.read_job(
            self.result_path, task_id=TASK,
            reviewed_artifact_sha256=closure_record.sha256(self.contract))
        self.assertEqual(job.result.recommendation, "commit_contract")
        self.assertEqual(job.record["provider"], "codex")
        # Codex reports no is_error; the record says so rather than inventing one.
        self.assertIsNone(job.record["is_error"])

    def test_a_completed_revise_is_a_success(self):
        self.assertEqual(
            self.run_job(result=self.result_json(recommendation="revise")), OK,
            self.output)
        self.assertProviderRan()
        job = closure_record.read_job(
            self.result_path, task_id=TASK,
            reviewed_artifact_sha256=closure_record.sha256(self.contract))
        self.assertEqual(job.result.recommendation, "revise")

    def test_the_runner_finds_its_helpers_beside_itself(self):
        # The absolute fallbacks are gone, so this deployment must be
        # self-sufficient: nothing here exists at C:/NSC/tools or C:/nscrev.
        self.assertEqual(self.run_job(), OK, self.output)
        self.assertIn("[DONE]", self.output)

    # ---- the run fails, each for its own documented reason ---------------

    def test_a_failed_provider_is_exit_4_and_publishes_no_record(self):
        self.assertEqual(self.run_job(exit_code=9), PROVIDER_FAILED, self.output)
        self.assertProviderRan()
        self.assertNoRecord()

    def test_prose_instead_of_a_result_is_exit_7(self):
        self.assertEqual(self.run_job(result="Final recommendation: commit_contract\n"),
                         NOT_ACTIONABLE, self.output)
        self.assertProviderRan()
        self.assertNoRecord()

    def test_a_review_of_different_bytes_is_exit_7(self):
        self.assertEqual(
            self.run_job(result=self.result_json(reviewed_artifact_sha256="c" * 64)),
            NOT_ACTIONABLE, self.output)
        self.assertProviderRan()
        self.assertNoRecord()

    def test_an_incomplete_review_is_exit_7(self):
        self.assertEqual(self.run_job(result=self.result_json(
            review_status="incomplete", recommendation=None,
            report_markdown="Could not finish.")), NOT_ACTIONABLE, self.output)
        self.assertProviderRan()
        self.assertNoRecord()

    # ---- Astra MJ-P3-03-B, on this path ----------------------------------

    def test_a_provider_that_rewrites_the_contract_is_refused(self):
        """The subject moved under the run, so the verdict is about nobody's bytes.

        Reproduced by Codex against the unedited script: the fake rewrote its
        clone's REVISED_CONTRACT.json and returned a result bound to the NEW
        bytes. Everything agreed with everything, the script exited 0, and a
        ready `commit_contract` record was published for a contract the host
        never selected.
        """
        changed = b'{"id": "NSC-001", "contract_revision": 99}\n'
        code = self.run_job(tamper=changed,
                            result=self.result_json(contract=changed))
        self.assertEqual(code, CONTRACT_CHANGED, self.output)
        self.assertProviderRan()
        self.assertNoRecord()
        self.assertIn("[TAMPERED]", self.output)

    def test_the_pre_launch_hash_is_of_the_hosts_own_selection(self):
        """A control for the case above: the same run without the rewrite passes.

        Without this, a `--contract-sha256` that was simply always wrong would
        make the tampering test pass for the wrong reason.
        """
        self.assertEqual(self.run_job(), OK, self.output)

    # ---- Astra MJ-P3-03-C, on this path ----------------------------------

    def test_evidence_from_an_earlier_run_is_refused_before_launch(self):
        """A retained record is evidence, not scratch space.

        Codex's reproduction started from a completed `revise` and got back a
        `commit_contract` under the same job name, with nothing on disk saying a
        replacement had happened: the script moved the result and view aside and
        the publisher's `os.replace` made the overwrite atomic, so it was
        invisible rather than partial.

        **The clone is deleted first, and that is the whole point.** The script
        already refused a second run whose clone directory still existed, so a
        test that leaves the clone in place passes without the evidence check
        ever running - which is what the mutation harness caught this file doing.
        Astra had written exactly that sentence in the finding ("a clone-only
        duplicate test does not cover this case") and I still wrote it wrong.
        Retained or relocated evidence with no clone beside it is the real case.
        """
        self.assertEqual(self.run_job(result=self.result_json(recommendation="revise")),
                         OK, self.output)
        before = closure_record.metadata_path(self.result_path).read_bytes()
        view_before = closure_record.view_path(self.result_path).read_bytes()
        self.marker.unlink()
        remove_tree(self.work / "codex-jobs" / "JOB")
        self.assertFalse((self.work / "codex-jobs" / "JOB").exists(),
                         "the clone survived, so the clone check would refuse first")

        code = self.run_job()
        self.assertEqual(code, SETUP_REFUSED, self.output)
        self.assertProviderDidNotRun()
        self.assertEqual(closure_record.metadata_path(self.result_path).read_bytes(),
                         before, "the earlier record was modified")
        self.assertEqual(closure_record.view_path(self.result_path).read_bytes(),
                         view_before, "the earlier view was modified")
        job = closure_record.read_job(
            self.result_path, task_id=TASK,
            reviewed_artifact_sha256=closure_record.sha256(self.contract))
        self.assertEqual(job.result.recommendation, "revise",
                         "the earlier verdict was replaced")

    # ---- Fable finding 4: the writer and the reader of the prompt ----------

    def test_the_prompt_builder_writes_where_the_runner_reads(self):
        """One tool writes it, another reads it, and they used to disagree.

        `make_closure_prompt.py` wrote beside ITSELF while the runner reads the
        work root, so the pair only worked when the tools happened to be
        deployed inside the work root - which the launcher's own relative helper
        lookup then broke. Nothing noticed, because every test here wrote the
        prompt by hand. This one builds it with the real tool.
        """
        (self.work / "codex-jobs" / "BUILT.prompt.md").unlink(missing_ok=True)
        reason = self.tmp / "reason.txt"
        reason.write_text("The contract gained a test filter.\n", encoding="utf-8")

        built = subprocess.run(
            [sys.executable, "-B",
             str(self.tools / "codex-jobs" / "make_closure_prompt.py"),
             "BUILT", TASK, str(reason), "none", "none"],
            capture_output=True, text=True,
            env={**os.environ, "NSC_WORK": str(self.work),
                 "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)

        prompt = self.work / "codex-jobs" / "BUILT.prompt.md"
        self.assertTrue(prompt.is_file(),
                        f"the builder did not write where the runner reads:\n"
                        f"{built.stdout}{built.stderr}")
        self.assertIn(TASK, prompt.read_text(encoding="utf-8"))

        # And the runner accepts it - the point is the pair, not either half.
        self.assertEqual(self.run_job(job="BUILT"), OK, self.output)

    def test_a_retry_under_a_new_job_name_is_allowed(self):
        """The refusal must not make the job unrepeatable, only unrepeatable HERE."""
        self.assertEqual(self.run_job(result=self.result_json(recommendation="revise")),
                         OK, self.output)
        (self.work / "codex-jobs" / "RETRY.prompt.md").write_text(
            "Review the revision.\n", encoding="utf-8")
        self.assertEqual(self.run_job(job="RETRY"), OK, self.output)
        retry = self.work / "codex-jobs" / "RETRY.result.json"
        job = closure_record.read_job(
            retry, task_id=TASK,
            reviewed_artifact_sha256=closure_record.sha256(self.contract))
        self.assertEqual(job.result.recommendation, "commit_contract")


if __name__ == "__main__":
    unittest.main(verbosity=2)
