#!/usr/bin/env python
"""Tests for the tracked Claude closure-review adapter.

Run:
    python -B test_claude_closure_review.py

The two live adapters this replaces both returned 0 after a provider failure:
their only non-zero exits were an unreadable wrapper JSON and a usage-limit
phrase found in the review text. A run with `is_error: true`, or one whose
review was empty, reported success - so a caller branching on the exit status
was told a review had happened when it had not.

`interpret` is where every one of those decisions lives, and its ORDER is the
property under test: process status, then emptiness, then the protocol. A
well-formed result must never excuse a failed run, and a failed run must never be
read for content. Each test names which of those it pins.

No provider is called. The fixtures are captured wrapper JSON of the shape the
CLI emits with --output-format json.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import os
import shutil
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import claude_closure_review as ccr  # noqa: E402
import closure_record  # noqa: E402
import review_result  # noqa: E402

TASK = "NSC-001"
CONTRACT = b'{"task": "NSC-001", "revision": 7}\n'
DIGEST = hashlib.sha256(CONTRACT).hexdigest()


def result_json(**overrides) -> str:
    body = {
        "schema_version": 1,
        "review_kind": "closure",
        "task_id": TASK,
        "reviewed_artifact_kind": "contract",
        "reviewed_artifact_sha256": DIGEST,
        "review_status": "complete",
        "recommendation": "commit_contract",
        "report_markdown": "Ledger:\n- L1: RESOLVED.",
    }
    body.update(overrides)
    return json.dumps(body)


def wrapper(result: str | None = None, **overrides) -> bytes:
    """What the CLI writes with --output-format json."""
    body = {"subtype": "success", "is_error": False, "num_turns": 12,
            "result": result_json() if result is None else result}
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


class Base(unittest.TestCase):
    def interpret(self, raw: bytes, task_id: str = TASK, contract: bytes = CONTRACT):
        return ccr.interpret(raw, task_id=task_id, contract=contract)


class ProviderStatusComesFirst(Base):
    """A well-formed result must never excuse a failed run."""

    def test_is_error_fails_even_with_a_perfect_result(self):
        # The exact defect: the live adapters returned 0 here.
        status, message, result = self.interpret(
            wrapper(is_error=True, subtype="error_during_execution"))
        self.assertEqual(status, ccr.PROVIDER_FAILED)
        self.assertIn("is_error", message)
        self.assertIsNone(result)

    def test_a_wrapper_with_no_is_error_is_not_a_success(self):
        """Astra MJ-P3-03-A's fix, which Fable found nothing was pinning.

        I changed the check, wrote the reasoning in the comment above it, told
        Codex it was closed - and left the only is_error cases in this file as
        `is_error=True`. Both `if is_error:` and `if is_error is True:` kept the
        suite green. A fix with no failing test behind it is a claim.
        """
        body = json.loads(wrapper())
        del body["is_error"]
        status, message, result = self.interpret(json.dumps(body).encode("utf-8"))
        self.assertEqual(status, ccr.PROVIDER_FAILED)
        self.assertIn("missing", message)
        self.assertIsNone(result)

    def test_only_an_explicit_false_counts_as_success(self):
        # Every falsy value that is not False. `0 is False` is False in CPython,
        # so identity is what separates them and truthiness does not.
        for value in (None, 0, 0.0, "", [], {}, "false"):
            with self.subTest(is_error=repr(value)):
                status, _message, _result = self.interpret(wrapper(is_error=value))
                self.assertEqual(status, ccr.PROVIDER_FAILED)

    def test_a_subtype_other_than_success_fails(self):
        for subtype in ("error_during_execution", "error_max_turns", "Success", None):
            with self.subTest(subtype=repr(subtype)):
                status, message, _result = self.interpret(wrapper(subtype=subtype))
                self.assertEqual(status, ccr.PROVIDER_FAILED)
                self.assertIn("subtype", message)

    def test_a_missing_subtype_fails(self):
        body = json.loads(wrapper())
        del body["subtype"]
        self.assertEqual(self.interpret(json.dumps(body).encode("utf-8"))[0],
                         ccr.PROVIDER_FAILED)

    def test_an_empty_result_fails_even_when_the_run_reported_success(self):
        for empty in (None, "", "   \n\t"):
            with self.subTest(empty=repr(empty)):
                status, _message, _result = self.interpret(wrapper(result=empty or ""))
                self.assertEqual(status, ccr.EMPTY_RESULT)

    def test_a_missing_result_key_is_empty_not_a_crash(self):
        status, _message, _result = self.interpret(
            json.dumps({"is_error": False, "subtype": "success"}).encode("utf-8"))
        self.assertEqual(status, ccr.EMPTY_RESULT)

    def test_a_valid_result_that_mentions_a_rate_limit_is_still_a_review(self):
        """Fable: the usage-limit check had its own idea of "JSON-shaped".

        `lstrip().startswith("{")` does not skip a BOM. A perfectly good result
        that arrived with one, whose report happens to discuss rate limits,
        was therefore reported as a transport refusal telling the operator to
        stop jobs - a review turned into an incident by an invisible byte.
        """
        discusses = result_json(
            report_markdown="The task's retry path handles a rate limit poorly.")
        status, _message, result = self.interpret(
            wrapper(result=chr(0xFEFF) + discusses))
        self.assertEqual(status, 0)
        self.assertIsNotNone(result)
        self.assertEqual(result.recommendation, "commit_contract")

    def test_a_genuine_usage_limit_is_still_reported(self):
        # The control. Prose, no result object, so the refusal must survive.
        status, message, _result = self.interpret(
            wrapper(result="You have hit your usage limit. Try again later."))
        self.assertEqual(status, ccr.USAGE_LIMIT)
        self.assertIn("tell Vincent", message)

    def test_unreadable_wrapper_output_is_a_setup_failure(self):
        self.assertEqual(self.interpret(b"not json at all")[0], ccr.SETUP_REFUSED)
        self.assertEqual(self.interpret(b'["a list"]')[0], ccr.SETUP_REFUSED)


class TheProtocolDecides(Base):
    def test_a_bound_result_succeeds(self):
        status, message, result = self.interpret(wrapper())
        self.assertEqual(status, ccr.OK)
        self.assertIn("commit_contract", message)
        self.assertEqual(result.recommendation, "commit_contract")

    def test_a_negative_verdict_still_succeeds(self):
        status, _message, result = self.interpret(
            wrapper(result=result_json(recommendation="revise")))
        self.assertEqual(status, ccr.OK)
        self.assertEqual(result.recommendation, "revise")

    def test_a_declared_incomplete_is_not_actionable(self):
        status, message, _result = self.interpret(wrapper(result=result_json(
            review_status="incomplete", recommendation=None,
            report_markdown="I could not finish.")))
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("incomplete", message)

    def test_prose_instead_of_a_result_is_not_actionable(self):
        # What the old adapters accepted and grepped.
        status, message, _result = self.interpret(wrapper(
            result="Ledger:\n- L1 RESOLVED\n\nFinal recommendation: commit_contract"))
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("not_json", message)

    def test_a_review_of_a_different_contract_is_not_actionable(self):
        status, message, _result = self.interpret(
            wrapper(), contract=b'{"task": "NSC-001", "revision": 8}\n')
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("artifact_hash_mismatch", message)

    def test_a_review_of_a_different_task_is_not_actionable(self):
        status, message, _result = self.interpret(wrapper(), task_id="NSC-999")
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("task_mismatch", message)


class UsageLimits(Base):
    def test_a_usage_limit_in_prose_is_reported_as_one(self):
        status, message, _result = self.interpret(wrapper(
            result="I hit a usage limit and stopped."))
        self.assertEqual(status, ccr.USAGE_LIMIT)
        self.assertIn("tell Vincent", message)

    def test_a_review_that_merely_discusses_rate_limits_still_validates(self):
        # The old check searched the whole result text, so a review whose
        # narrative mentioned rate limits was reported as a usage limit. A
        # well-formed JSON result is a review, whatever it talks about.
        status, _message, result = self.interpret(wrapper(result=result_json(
            report_markdown="The task must handle a rate limit from the service.")))
        self.assertEqual(status, ccr.OK)
        self.assertEqual(result.recommendation, "commit_contract")


class TheRenderedView(Base):
    def test_it_is_labelled_and_carries_the_narrative(self):
        _status, _message, result = self.interpret(wrapper(result=result_json(
            report_markdown="Ledger:\n- L1: RESOLVED at line 40.")))
        view = ccr.render(result)
        self.assertIn(review_result.DERIVED_VIEW_MARKER, view)
        self.assertIn("L1: RESOLVED at line 40.", view)
        self.assertIn("- Recommendation: commit_contract", view)

    def test_narrative_does_not_change_the_rendered_verdict(self):
        _status, _message, result = self.interpret(wrapper(result=result_json(
            recommendation="revise",
            report_markdown="Final recommendation: commit_contract")))
        self.assertIn("- Recommendation: revise", ccr.render(result))


class TheTwoRunners(unittest.TestCase):
    """They differ by more than one command, which is what caught me out."""

    def test_docker_runs_in_the_clone_and_host_does_not(self):
        clone = Path("C:/nscrev/cj-example")
        docker_cmd, docker_cwd = ccr.command("docker", "claude-sonnet-5", "60", clone)
        self.assertEqual(docker_cwd, clone)
        self.assertEqual(docker_cmd[0], "docker")
        self.assertIn("--output-format", docker_cmd)

    def test_both_request_json_output_and_read_only_tools(self):
        docker_cmd, _ = ccr.command("docker", "m", "60", Path("C:/tmp"))
        for forbidden in ("Edit", "Write", "NotebookEdit"):
            self.assertNotIn(forbidden, docker_cmd)
        self.assertIn("json", docker_cmd)

    def test_the_host_cwd_is_not_a_spelled_out_machine_path(self):
        # Astra MJ-P3-04: it was hardcoded to C:/NSC even when every path
        # argument pointed elsewhere, which breaks a fresh install on F:.
        #
        # MJ-P3-05: the account guard is faked here. Calling the real one reaches
        # an actual `claude auth status` process, so this test passed only on a
        # machine with that CLI installed and signed in - or with
        # ALLOW_ANY_CLAUDE_ACCOUNT inherited, which is worse, because then the
        # guard is bypassed rather than exercised. Deterministic tests must need
        # no logged-in CLI; the guard has its own tests below, with a fake.
        real_guard, real_which = ccr.require_gmail_account, shutil.which
        ccr.require_gmail_account = lambda exe: None
        shutil.which = lambda name: "C:/fake/claude.exe"
        try:
            chosen = Path("D:/elsewhere/workspace")
            _cmd, cwd = ccr.command("host", "m", "60", Path("D:/elsewhere/cj-x"),
                                    host_cwd=chosen)
        finally:
            ccr.require_gmail_account, shutil.which = real_guard, real_which
        self.assertEqual(cwd, chosen)


class TheAccountGuard(unittest.TestCase):
    """Spend the Gmail account first. Faked subprocess, never a real CLI."""

    def setUp(self):
        self._real_run = subprocess.run
        self._flag = os.environ.pop("ALLOW_ANY_CLAUDE_ACCOUNT", None)
        self.addCleanup(self._restore)

    def _restore(self):
        subprocess.run = self._real_run
        if self._flag is not None:
            os.environ["ALLOW_ANY_CLAUDE_ACCOUNT"] = self._flag
        else:
            os.environ.pop("ALLOW_ANY_CLAUDE_ACCOUNT", None)

    def auth_says(self, text: str):
        subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(
            cmd, 0, stdout=text, stderr="")

    def test_the_gmail_account_passes(self):
        self.auth_says(f"Account: {ccr.GMAIL}\nPlan: max\n")
        ccr.require_gmail_account("C:/fake/claude.exe")      # must not raise

    def test_another_account_is_refused(self):
        self.auth_says("Account: someone.else@outlook.com\n")
        with self.assertRaises(SystemExit) as caught:
            ccr.require_gmail_account("C:/fake/claude.exe")
        self.assertIn(ccr.GMAIL, str(caught.exception))

    def test_the_override_short_circuits_before_any_process(self):
        os.environ["ALLOW_ANY_CLAUDE_ACCOUNT"] = "1"

        def must_not_run(cmd, **kwargs):
            raise AssertionError("the override must short-circuit before a process")

        subprocess.run = must_not_run
        ccr.require_gmail_account("C:/fake/claude.exe")


class ThePromptEachRunnerGets(unittest.TestCase):
    """Astra MJ-P3-02: Docker sees /workspace; the host sees the clone's real path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.clone = Path(self._tmp.name) / "cj-job"
        self.clone.mkdir()

    def test_docker_keeps_container_paths(self):
        prompt = ccr.localise_prompt("Review /workspace/REVISED_CONTRACT.json\n",
                                     self.clone, "60", "docker")
        self.assertIn("/workspace/REVISED_CONTRACT.json", prompt)
        self.assertNotIn(str(self.clone).replace("\\", "/"), prompt,
                         "the container was handed a host path it cannot resolve")

    def test_the_host_gets_the_clone_path(self):
        prompt = ccr.localise_prompt("Review /workspace/REVISED_CONTRACT.json\n",
                                     self.clone, "60", "host")
        root = str(self.clone).replace("\\", "/")
        self.assertIn(f"{root}/REVISED_CONTRACT.json", prompt)

    def test_copied_inputs_use_each_runners_own_root(self):
        source = Path(self._tmp.name) / "nscrev-ish.md"
        source.write_text("prior findings", encoding="utf-8")
        # localise_prompt only rewrites paths under C:/nscrev, so drive the
        # copy through a path shaped like one by pointing at the real file.
        for runner, expected in (("docker", "/workspace/_review_inputs/"),
                                 ("host", str(self.clone).replace("\\", "/")
                                  + "/_review_inputs/")):
            with self.subTest(runner=runner):
                prompt = ccr.localise_prompt("see /workspace/_review_inputs/x.md\n",
                                             self.clone, "60", runner)
                self.assertIn(expected, prompt)


class MainWiring(Base):
    """Astra MJ-P3-01: the rules are only real if main() actually applies them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.jobs = self.tmp / "codex-jobs"
        self.work = self.tmp / "claude-jobs"
        for d in (self.jobs, self.work):
            d.mkdir()
        (self.jobs / "JOB.prompt.md").write_text("review it\n", encoding="utf-8")

        self.clone = self.tmp / "cj-JOB"
        self._real = (ccr.build_clone, ccr.command, subprocess.run)

        def fake_clone(repo, clone, task, commit, previous, extras):
            clone.mkdir(parents=True)
            (clone / "REVISED_CONTRACT.json").write_bytes(CONTRACT)

        ccr.build_clone = fake_clone
        ccr.command = lambda *a, **k: (["fake-cli"], self.tmp)
        self.addCleanup(self._restore)

    def _restore(self):
        ccr.build_clone, ccr.command, subprocess.run = self._real

    def provider(self, *, code: int, wrapper_bytes: bytes):
        def fake_run(cmd, **kwargs):
            kwargs["stdout"].write(wrapper_bytes)
            return subprocess.CompletedProcess(cmd, code)
        subprocess.run = fake_run

    def run_main(self, runner: str = "host") -> int:
        return ccr.main(["--runner", runner, "--job", "JOB", "--task", TASK,
                         "--commit", "abc", "--previous", "def",
                         "--repo", str(self.tmp / "repo"),
                         "--jobs", str(self.jobs), "--work", str(self.work)])

    def test_docker_main_round_trips_and_keeps_container_paths(self):
        # Astra: MainWiring ran host only, and the two runners differ by more
        # than the command - which is how the Docker path broke once already.
        # No Docker engine is needed; the subprocess is faked like the host one.
        self.provider(code=0,
                      wrapper_bytes=wrapper(result=result_json(recommendation="revise")))
        self.assertEqual(self.run_main("docker"), ccr.OK)

        prompt = (self.work / "JOB.docker-prompt.md").read_text(encoding="utf-8")
        self.assertIn("/workspace", prompt)
        self.assertNotIn(str(self.clone).replace("\\", "/"), prompt,
                         "the container was handed a host path it cannot resolve")

        job = closure_record.read_job(self.jobs / "JOB.result.json", task_id=TASK,
                                      reviewed_artifact_sha256=DIGEST)
        self.assertEqual(job.result.recommendation, "revise")
        self.assertEqual(job.record["provider"], "claude-docker")

    def test_a_contract_changed_during_the_run_is_refused(self):
        # Astra MJ-P3-03-B: the contract was read AFTER the provider returned,
        # so a provider that edited the fixture got an approval of the bytes it
        # wrote rather than the ones the host selected.
        changed = b'{"task": "NSC-001", "revision": 8}\n'

        def meddling(cmd, **kwargs):
            (self.clone / "REVISED_CONTRACT.json").write_bytes(changed)
            kwargs["stdout"].write(wrapper(result=result_json(
                reviewed_artifact_sha256=hashlib.sha256(changed).hexdigest())))
            return subprocess.CompletedProcess(cmd, 0)

        subprocess.run = meddling
        # 8, not 2. Fable: this file's header promises its codes match
        # run_closure_review.sh "so a caller can branch the same way whichever
        # launcher produced the review", and for THIS condition they did not -
        # a caller branching on 8 to mean "the subject moved" missed every
        # Claude run and read it as an ordinary setup refusal.
        self.assertEqual(self.run_main(), ccr.CONTRACT_CHANGED)
        self.assertFalse((self.jobs / "JOB.result.json").exists())

    def test_the_two_launchers_agree_on_what_each_code_means(self):
        """The header's promise, checked rather than repeated.

        Every code this module defines must carry the meaning the shell script
        documents for the same number, because callers branch on the number.
        """
        shell = (pathlib.Path(ccr.__file__).resolve().parent.parent
                 / "codex-jobs" / "run_closure_review.sh").read_text(encoding="utf-8")
        header = shell.split("set -u")[0]
        for name, code, phrase in (("SETUP_REFUSED", 2, "setup refused"),
                                   ("USAGE_LIMIT", 3, "no result"),
                                   ("PROVIDER_FAILED", 4, "provider failed"),
                                   ("EMPTY_RESULT", 6, "empty result"),
                                   ("NOT_ACTIONABLE", 7, "not a finished"),
                                   ("CONTRACT_CHANGED", 8, "contract file changed")):
            with self.subTest(code=name):
                self.assertEqual(getattr(ccr, name), code)
                self.assertIn(f"{code} ", header,
                              f"the shell header does not document {code}")
                self.assertIn(phrase, header)

    def test_a_nonzero_process_fails_despite_a_valid_wrapper(self):
        # The exact reproduction: exit 9, is_error false, otherwise valid JSON.
        self.provider(code=9, wrapper_bytes=wrapper())
        self.assertEqual(self.run_main(), ccr.PROVIDER_FAILED)
        self.assertFalse((self.jobs / "JOB.result.json").exists(),
                         "actionable evidence was published for a failed process")
        self.assertFalse((self.jobs / "JOB.report.md").exists())

    def test_a_wrapper_error_with_a_zero_exit_also_fails(self):
        self.provider(code=0, wrapper_bytes=wrapper(is_error=True))
        self.assertEqual(self.run_main(), ccr.PROVIDER_FAILED)
        self.assertFalse((self.jobs / "JOB.result.json").exists())

    def test_a_complete_negative_succeeds_and_publishes(self):
        self.provider(code=0,
                      wrapper_bytes=wrapper(result=result_json(recommendation="revise")))
        self.assertEqual(self.run_main(), ccr.OK)
        self.assertEqual(json.loads((self.jobs / "JOB.result.json").read_text(
            encoding="utf-8"))["recommendation"], "revise")
        view = (self.jobs / "JOB.report.md").read_text(encoding="utf-8")
        self.assertIn(review_result.DERIVED_VIEW_MARKER, view)

    def test_a_completed_revise_round_trips_to_the_shared_reader(self):
        # The end-to-end property: what this launcher writes is what the
        # consumer's reader accepts, without either side being told about the
        # other's assumptions.
        self.provider(code=0,
                      wrapper_bytes=wrapper(result=result_json(recommendation="revise")))
        self.assertEqual(self.run_main(), ccr.OK)
        job = closure_record.read_job(
            self.jobs / "JOB.result.json", task_id=TASK,
            reviewed_artifact_sha256=DIGEST)
        self.assertEqual(job.result.recommendation, "revise")
        self.assertTrue(job.result.is_complete)
        self.assertFalse(job.result.is_committable)
        # The hash comes back from the SAME read that validated it.
        self.assertEqual(job.result_sha256,
                         closure_record.sha256((self.jobs / "JOB.result.json").read_bytes()))

    def test_an_incomplete_review_publishes_no_record(self):
        self.provider(code=0, wrapper_bytes=wrapper(result=result_json(
            review_status="incomplete", recommendation=None,
            report_markdown="Ran out of context.")))
        self.assertEqual(self.run_main(), ccr.NOT_ACTIONABLE)
        self.assertFalse(closure_record.metadata_path(
            self.jobs / "JOB.result.json").exists())

    def test_a_failed_process_publishes_no_record(self):
        self.provider(code=9, wrapper_bytes=wrapper())
        self.assertEqual(self.run_main(), ccr.PROVIDER_FAILED)
        self.assertFalse(closure_record.metadata_path(
            self.jobs / "JOB.result.json").exists())

    def test_the_record_names_this_runner_as_its_provider(self):
        self.provider(code=0, wrapper_bytes=wrapper())
        self.run_main()
        record = json.loads(closure_record.metadata_path(
            self.jobs / "JOB.result.json").read_text(encoding="utf-8"))
        self.assertEqual(record["provider"], "claude-host")
        self.assertIs(record["is_error"], False)
        self.assertEqual(record["exit_code"], 0)

    def test_a_repeated_job_is_refused_before_launching(self):
        # Astra MJ-P3-03-C: the clone reservation protects the working directory,
        # not the previous job's EVIDENCE. With the result, view and record on
        # disk but no clone, a fresh run used to start - and on failure left the
        # old record readable as an approval.
        self.provider(code=0, wrapper_bytes=wrapper())
        self.assertEqual(self.run_main(), ccr.OK)
        before = closure_record.metadata_path(self.jobs / "JOB.result.json").read_bytes()
        self.assertEqual(self.run_main(), ccr.SETUP_REFUSED)
        self.assertEqual(
            closure_record.metadata_path(self.jobs / "JOB.result.json").read_bytes(),
            before, "the earlier job's evidence was overwritten")

    def test_a_record_that_appears_mid_run_is_a_refusal_not_a_traceback(self):
        """The publisher's backstop, reported rather than raised.

        Both launchers check for existing evidence before launching, so this
        only fires if something appears in between - and an uncaught RecordError
        exits 1 with a traceback, a code this module does not document (Fable).
        """
        result_path = self.jobs / "JOB.result.json"
        real_build = closure_record.build

        def build_then_plant(**kwargs):
            record = real_build(**kwargs)
            closure_record.metadata_path(result_path).write_text(
                "{}", encoding="utf-8")
            return record

        self.provider(code=0, wrapper_bytes=wrapper())
        closure_record.build = build_then_plant
        try:
            self.assertEqual(self.run_main(), ccr.SETUP_REFUSED)
        finally:
            closure_record.build = real_build
        self.assertEqual(
            closure_record.metadata_path(result_path).read_text(encoding="utf-8"),
            "{}", "the refused publication still replaced the record")


if __name__ == "__main__":
    unittest.main(verbosity=2)
