#!/usr/bin/env python
"""Unit tests for ask_astra.py. No provider calls: every Codex run is the fake.

    set TEMP=C:\\nscrev\\tmp\\astra & set TMP=C:\\nscrev\\tmp\\astra
    C:/Python313/python.exe -B tests/test_ask_astra.py
"""

from __future__ import annotations

import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_DIR = HERE.parent
sys.path.insert(0, str(TOOL_DIR))

FAKE_CODEX = HERE / "fake_codex.py"

PRIMER_TEXT = "You are Astra.\n\nReply now with exactly: READY\n"


class AstraTestCase(unittest.TestCase):
    """Each test gets its own HOME, its own fake codex and its own argv log."""

    mode = "ok"

    def setUp(self):
        self._saved_env = dict(os.environ)
        self._tmp = tempfile.TemporaryDirectory(prefix="astra-test-")
        self.home = Path(self._tmp.name) / "astra"
        self.home.mkdir(parents=True)
        self.primer = self.home / "primer.md"
        self.primer.write_text(PRIMER_TEXT, encoding="utf-8", newline="\n")
        self.argv_log = Path(self._tmp.name) / "argv.jsonl"

        os.environ["NSC_ASTRA_HOME"] = str(self.home)
        os.environ["NSC_ASTRA_PRIMER"] = str(self.primer)
        os.environ["NSC_ASTRA_CODEX_EXE"] = str(FAKE_CODEX)
        os.environ["FAKE_CODEX_ARGV_LOG"] = str(self.argv_log)
        os.environ["FAKE_CODEX_MODE"] = self.mode
        for key in (
            "FAKE_CODEX_ANSWER",
            "FAKE_CODEX_EVENT_ANSWER",
            "FAKE_CODEX_HANG_SECONDS",
            "NSC_ASTRA_FAKE_ALIVE_PIDS",
            "NSC_ASTRA_CODEX_BIN_ROOT",
            "NSC_ASTRA_CODEX_EXE_NAME",
        ):
            os.environ.pop(key, None)

        import ask_astra

        self.aa = importlib.reload(ask_astra)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.aa.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def calls(self):
        if not self.argv_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.argv_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def model_calls(self):
        """Every invocation that is not just `--version`."""
        return [c for c in self.calls() if "--version" not in c["argv"]]

    def do_init(self):
        code, out, err = self.run_cli("init")
        self.assertEqual(code, 0, f"init failed: {err}")
        return out


# ==========================================================================
# Finding the bundled CLI
# ==========================================================================


class FindCodex(AstraTestCase):
    def _bin_root(self, folders):
        """folders: {name: version or None}. None = no binary in that folder."""
        root = Path(self._tmp.name) / "codexbin"
        root.mkdir(exist_ok=True)
        made = {}
        for name, version in folders.items():
            folder = root / name
            folder.mkdir(exist_ok=True)
            if version is None:
                (folder / "codex-command-runner.py").write_text("# not the cli\n", encoding="utf-8")
                continue
            stub = folder / "codex.py"
            stub.write_text(
                "import sys\n"
                "if '--version' in sys.argv:\n"
                f"    print({version!r})\n"
                "sys.exit(0)\n",
                encoding="utf-8",
                newline="\n",
            )
            made[name] = stub
        os.environ.pop("NSC_ASTRA_CODEX_EXE", None)
        os.environ["NSC_ASTRA_CODEX_BIN_ROOT"] = str(root)
        os.environ["NSC_ASTRA_CODEX_EXE_NAME"] = "codex.py"
        import ask_astra

        self.aa = importlib.reload(ask_astra)
        return made

    def test_folder_without_the_binary_is_skipped(self):
        """The real machine has two hash folders and only one holds codex.exe.

        'Newest by mtime' alone picks the wrong one, which is why the scan
        filters on the binary existing before it ranks anything.
        """
        made = self._bin_root({"has_it": "codex-cli 0.155.0-alpha.2.6", "empty_one": None})
        # Make the binary-less folder the newest, so mtime alone would lose.
        empty = Path(os.environ["NSC_ASTRA_CODEX_BIN_ROOT"]) / "empty_one"
        os.utime(empty, (time.time() + 500, time.time() + 500))
        self.assertEqual(self.aa.find_codex(), made["has_it"])

    def test_highest_version_wins_over_newer_mtime(self):
        made = self._bin_root(
            {"old": "codex-cli 0.155.0-alpha.2.6", "new": "codex-cli 0.151.0"}
        )
        os.utime(made["new"], (time.time() + 500, time.time() + 500))
        self.assertEqual(self.aa.find_codex(), made["old"])

    def test_no_binary_anywhere_is_a_codex_failure_not_a_crash(self):
        self._bin_root({"empty_one": None})
        code, _out, err = self.run_cli("init")
        self.assertEqual(code, self.aa.EXIT_CODEX_FAILED)
        self.assertIn("codex.py", err)

    def test_explicit_override_wins(self):
        self.assertEqual(self.aa.find_codex(), FAKE_CODEX)

    def test_missing_override_is_reported(self):
        os.environ["NSC_ASTRA_CODEX_EXE"] = str(self.home / "nope.exe")
        import ask_astra

        self.aa = importlib.reload(ask_astra)
        code, _out, err = self.run_cli("init")
        self.assertEqual(code, self.aa.EXIT_CODEX_FAILED)
        self.assertIn("does not exist", err)

    def test_version_key_orders_alpha_builds(self):
        key = self.aa._version_key
        self.assertGreater(key("codex-cli 0.155.0-alpha.2.6"), key("codex-cli 0.152.1"))
        self.assertGreater(key("0.151.0"), key(""))
        self.assertEqual(key("no digits here"), (-1,))


# ==========================================================================
# init
# ==========================================================================


class Init(AstraTestCase):
    def test_writes_every_thread_field(self):
        self.do_init()
        thread = json.loads((self.home / "thread.json").read_text(encoding="utf-8"))
        for key in ("thread_id", "created_at", "model", "primer_sha256", "codex_version"):
            self.assertIn(key, thread)
        self.assertEqual(thread["model"], "gpt-6-astra")
        self.assertEqual(thread["thread_id"], "01a0ae11-fake-4d1e-9b77-000000000001")

    def test_argv_is_the_verified_exec_form(self):
        self.do_init()
        argv = self.model_calls()[0]["argv"]
        self.assertEqual(argv[0], "exec")
        self.assertNotIn("resume", argv)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertIn("--json", argv)
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-6-astra")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        # The primer goes as an argument, which is the form verified on 09-17.
        self.assertIn("Reply now with exactly: READY", argv[-1])

    def test_refuses_a_second_init(self):
        self.do_init()
        before = (self.home / "thread.json").read_text(encoding="utf-8")
        code, _out, err = self.run_cli("init")
        self.assertEqual(code, self.aa.EXIT_USAGE)
        self.assertIn("already exists", err)
        self.assertEqual((self.home / "thread.json").read_text(encoding="utf-8"), before)

    def test_new_archives_and_never_deletes(self):
        self.do_init()
        first = json.loads((self.home / "thread.json").read_text(encoding="utf-8"))
        os.environ["FAKE_CODEX_THREAD_ID"] = "01a0ae11-fake-4d1e-9b77-000000000002"
        code, _out, err = self.run_cli("init", "--new")
        self.assertEqual(code, 0, err)
        archived = list(self.home.glob("thread-*.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(
            json.loads(archived[0].read_text(encoding="utf-8"))["thread_id"], first["thread_id"]
        )
        now = json.loads((self.home / "thread.json").read_text(encoding="utf-8"))
        self.assertEqual(now["thread_id"], "01a0ae11-fake-4d1e-9b77-000000000002")

    def test_no_thread_id_is_a_codex_failure(self):
        os.environ["FAKE_CODEX_MODE"] = "no_thread"
        code, _out, err = self.run_cli("init")
        self.assertEqual(code, self.aa.EXIT_CODEX_FAILED)
        self.assertFalse((self.home / "thread.json").exists())
        self.assertIn("no thread", err.lower())

    def test_missing_primer_is_reported(self):
        self.primer.unlink()
        code, _out, err = self.run_cli("init")
        self.assertEqual(code, self.aa.EXIT_CODEX_FAILED)
        self.assertIn("primer not found", err)


# ==========================================================================
# ask
# ==========================================================================


class Ask(AstraTestCase):
    def test_argv_is_the_verified_resume_form(self):
        self.do_init()
        code, out, err = self.run_cli("ask", "--from", "Game Agent", "--question", "why?")
        self.assertEqual(code, 0, err)
        self.assertIn("READY", out)
        call = self.model_calls()[1]
        argv = call["argv"]
        self.assertEqual(argv[:3], ["exec", "resume", "01a0ae11-fake-4d1e-9b77-000000000001"])
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-6-astra")
        self.assertEqual(argv[argv.index("-c") + 1], "sandbox_mode=read-only")
        self.assertNotIn("--sandbox", argv)  # exec resume has no --sandbox flag
        self.assertIn("--skip-git-repo-check", argv)
        self.assertEqual(argv[-1], "-")
        self.assertEqual(call["stdin"].strip(), "From Game Agent: why?")

    def test_question_file(self):
        self.do_init()
        question = self.home / "q.md"
        question.write_text("# Stuck\n\nWhy does it loop?\n", encoding="utf-8", newline="\n")
        code, _out, err = self.run_cli(
            "ask", "--from", "Decomposition Agent", "--question-file", str(question)
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Why does it loop?", self.model_calls()[1]["stdin"])

    def test_missing_question_file_is_a_usage_error(self):
        self.do_init()
        code, _out, err = self.run_cli(
            "ask", "--from", "X", "--question-file", str(self.home / "nope.md")
        )
        self.assertEqual(code, self.aa.EXIT_USAGE)
        self.assertIn("not found", err)

    def test_empty_question_is_a_usage_error(self):
        self.do_init()
        code, _out, _err = self.run_cli("ask", "--from", "X", "--question", "   ")
        self.assertEqual(code, self.aa.EXIT_USAGE)

    def test_no_thread_yet_says_run_init(self):
        code, _out, err = self.run_cli("ask", "--from", "X", "--question", "hi")
        self.assertEqual(code, self.aa.EXIT_CODEX_FAILED)
        self.assertIn("init", err)
        self.assertEqual(self.model_calls(), [])

    def test_records_answer_log_and_last(self):
        self.do_init()
        os.environ["FAKE_CODEX_ANSWER"] = "ANSWER: because the lease was pinned."
        self.run_cli("ask", "--from", "Pipeline Maintainer Agent", "--question", "why?")

        answers = list((self.home / "answers").glob("*.md"))
        self.assertEqual(len(answers), 1)
        self.assertIn("pipeline-maintainer-agent", answers[0].name)
        body = answers[0].read_text(encoding="utf-8")
        self.assertIn("because the lease was pinned", body)
        self.assertIn("why?", body)

        logs = list((self.home / "log").glob("*.md"))
        self.assertEqual(len(logs), 1)
        self.assertIn("Pipeline Maintainer Agent", logs[0].read_text(encoding="utf-8"))

        last = json.loads((self.home / "last.json").read_text(encoding="utf-8"))
        self.assertEqual(last["from"], "Pipeline Maintainer Agent")
        self.assertEqual(last["status"], "answered")

    def test_log_appends_rather_than_overwrites(self):
        self.do_init()
        self.run_cli("ask", "--from", "A", "--question", "first")
        self.run_cli("ask", "--from", "B", "--question", "second")
        log = next((self.home / "log").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("first", log)
        self.assertIn("second", log)

    def test_answer_falls_back_to_the_event_stream(self):
        self.do_init()
        os.environ["FAKE_CODEX_EVENT_ANSWER"] = "from the events"
        code, out, err = self.run_cli("ask", "--from", "X", "--question", "q")
        self.assertEqual(code, 0, err)
        self.assertIn("from the events", out)

    def test_files_are_utf8_without_bom_and_lf(self):
        self.do_init()
        self.run_cli("ask", "--from", "X", "--question", "q")
        raw = next((self.home / "answers").glob("*.md")).read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", raw)


# ==========================================================================
# Exit codes
# ==========================================================================


class ExitCodes(AstraTestCase):
    def test_codex_failure_is_three(self):
        self.do_init()
        os.environ["FAKE_CODEX_MODE"] = "fail"
        code, _out, err = self.run_cli("ask", "--from", "X", "--question", "q")
        self.assertEqual(code, self.aa.EXIT_CODEX_FAILED)
        self.assertIn("exit 7", err)
        self.assertEqual(
            json.loads((self.home / "last.json").read_text(encoding="utf-8"))["status"],
            "codex-failed",
        )

    def test_model_unavailable_is_four_and_names_the_fallback(self):
        self.do_init()
        os.environ["FAKE_CODEX_MODE"] = "model_unavailable"
        code, _out, err = self.run_cli("ask", "--from", "X", "--question", "q")
        self.assertEqual(code, self.aa.EXIT_MODEL_UNAVAILABLE)
        self.assertIn("nsc-codex-jobs-guide.md 4.4", err)

    def test_init_reports_model_unavailable_too(self):
        os.environ["FAKE_CODEX_MODE"] = "model_unavailable"
        code, _out, err = self.run_cli("init")
        self.assertEqual(code, self.aa.EXIT_MODEL_UNAVAILABLE)
        self.assertIn("4.4", err)

    def test_an_answer_wins_over_an_unavailable_looking_stream(self):
        """A retried-then-successful call must not be reported as exit 4.

        The classifier reads stdout+stderr, so the string has to be THERE for
        this test to mean anything - putting it in the answer file only proves
        that the classifier does not read the answer file. Classification runs
        only when nothing came back; otherwise a call that printed a transient
        stream error and then answered would be reported as model-unavailable.
        """
        self.do_init()
        os.environ["FAKE_CODEX_NOISE_STDERR"] = (
            "stream error: `gpt-6-astra` requires a newer version of Codex; retrying 1/5"
        )
        os.environ["FAKE_CODEX_ANSWER"] = "ROOT CAUSE: the lease was pinned at reservation."
        code, out, _err = self.run_cli("ask", "--from", "X", "--question", "q")
        self.assertEqual(code, self.aa.EXIT_OK)
        self.assertIn("the lease was pinned", out)
        self.assertEqual(
            json.loads((self.home / "last.json").read_text(encoding="utf-8"))["status"],
            "answered",
        )

    def test_astra_quoting_the_error_in_its_prose_is_still_an_answer(self):
        self.do_init()
        os.environ["FAKE_CODEX_ANSWER"] = "ROOT CAUSE: Codex printed 'unknown model' because ..."
        code, out, _err = self.run_cli("ask", "--from", "X", "--question", "q")
        self.assertEqual(code, self.aa.EXIT_OK)
        self.assertIn("unknown model", out)

    def test_a_hung_call_is_three_not_two(self):
        self.do_init()
        os.environ["FAKE_CODEX_MODE"] = "hang"
        os.environ["FAKE_CODEX_HANG_SECONDS"] = "30"
        code, _out, err = self.run_cli(
            "ask", "--from", "X", "--question", "q", "--call-timeout-min", "0.01"
        )
        self.assertEqual(code, self.aa.EXIT_CODEX_FAILED)
        self.assertIn("did not finish", err)

    def test_a_hung_call_releases_the_lock(self):
        self.do_init()
        os.environ["FAKE_CODEX_MODE"] = "hang"
        os.environ["FAKE_CODEX_HANG_SECONDS"] = "30"
        self.run_cli("ask", "--from", "X", "--question", "q", "--call-timeout-min", "0.01")
        self.assertFalse((self.home / "astra.lock").exists())

    def test_usage_errors_are_64_never_2(self):
        """2 must mean 'busy' and nothing else, so argparse is remapped."""
        with self.assertRaises(SystemExit) as caught:
            with redirect_stderr(io.StringIO()):
                self.aa.main(["ask", "--question", "no --from"])
        self.assertEqual(caught.exception.code, self.aa.EXIT_USAGE)

        with self.assertRaises(SystemExit) as caught:
            with redirect_stderr(io.StringIO()):
                self.aa.main(["ask", "--from", "X", "--question", "a", "--question-file", "b"])
        self.assertEqual(caught.exception.code, self.aa.EXIT_USAGE)

    def test_the_four_codes_are_distinct(self):
        codes = {
            self.aa.EXIT_OK,
            self.aa.EXIT_BUSY,
            self.aa.EXIT_CODEX_FAILED,
            self.aa.EXIT_MODEL_UNAVAILABLE,
            self.aa.EXIT_USAGE,
        }
        self.assertEqual(len(codes), 5)


# ==========================================================================
# The lock
# ==========================================================================


class Locking(AstraTestCase):
    def _hold(self, owner="Someone Else", pid=None, age_seconds=0):
        started = self.aa._utc_now() - __import__("datetime").timedelta(seconds=age_seconds)
        payload = {
            "owner": owner,
            "pid": pid if pid is not None else os.getpid(),
            "started_at": self.aa._iso(started),
        }
        (self.home / "astra.lock").write_text(
            json.dumps(payload), encoding="utf-8", newline="\n"
        )
        return payload

    def test_one_question_at_a_time(self):
        self.do_init()
        self._hold(age_seconds=5)
        code, _out, err = self.run_cli(
            "ask", "--from", "X", "--question", "q", "--timeout-min", "0.005"
        )
        self.assertEqual(code, self.aa.EXIT_BUSY)
        self.assertIn("Someone Else", err)
        self.assertEqual(len(self.model_calls()), 1)  # only init's call ran

    def test_lock_is_released_after_a_normal_answer(self):
        self.do_init()
        code, _out, err = self.run_cli("ask", "--from", "X", "--question", "q")
        self.assertEqual(code, 0, err)
        self.assertFalse((self.home / "astra.lock").exists())

    def test_old_lock_with_a_live_pid_is_not_stale(self):
        """30 minutes is not enough on its own - the brief requires both."""
        held = self._hold(pid=4242, age_seconds=99 * 60)
        os.environ["NSC_ASTRA_FAKE_ALIVE_PIDS"] = "4242"
        self.assertFalse(self.aa._lock_is_stale(held))

    def test_young_lock_with_a_dead_pid_is_not_stale(self):
        held = self._hold(pid=4242, age_seconds=60)
        os.environ["NSC_ASTRA_FAKE_ALIVE_PIDS"] = ""
        self.assertFalse(self.aa._lock_is_stale(held))

    def test_old_lock_with_a_dead_pid_is_stale_and_gets_broken(self):
        self.do_init()
        self._hold(pid=4242, age_seconds=99 * 60)
        os.environ["NSC_ASTRA_FAKE_ALIVE_PIDS"] = ""
        code, _out, err = self.run_cli(
            "ask", "--from", "X", "--question", "q", "--timeout-min", "0.005"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("stale lock", err)

    def test_unreadable_lock_is_treated_as_stale(self):
        (self.home / "astra.lock").write_text("not json", encoding="utf-8")
        self.assertTrue(self.aa._lock_is_stale(self.aa._read_json(self.home / "astra.lock")))

    def test_waiter_polls_until_the_deadline(self):
        self._hold(age_seconds=5)
        naps = []
        with self.assertRaises(self.aa.Busy):
            self.aa.acquire_lock("Waiter", 25, sleeper=naps.append)
        self.assertGreaterEqual(len(naps), 2)
        self.assertLessEqual(max(naps), self.aa.POLL_SECONDS)


class PidLiveness(AstraTestCase):
    def test_probing_a_pid_does_not_kill_it(self):
        """os.kill(pid, 0) on Windows routes to TerminateProcess. This must not."""
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=self.aa.CREATE_NO_WINDOW,
        )
        try:
            self.assertTrue(self.aa._pid_alive(child.pid))
            time.sleep(0.3)
            self.assertIsNone(child.poll(), "the liveness probe killed the process")
        finally:
            child.kill()
            child.wait(timeout=10)

    def test_our_own_pid_is_alive(self):
        self.assertTrue(self.aa._pid_alive(os.getpid()))

    def test_nonsense_pids_are_dead(self):
        for bad in (0, -1, None, "", "abc"):
            self.assertFalse(self.aa._pid_alive(bad), bad)

    def test_a_reaped_child_is_dead(self):
        child = subprocess.Popen(
            [sys.executable, "-c", "pass"], creationflags=self.aa.CREATE_NO_WINDOW
        )
        child.wait(timeout=10)
        self.assertFalse(self.aa._pid_alive(child.pid))


# ==========================================================================
# Safety
# ==========================================================================


class Safety(AstraTestCase):
    def test_refuses_a_dangerous_flag(self):
        with self.assertRaises(RuntimeError) as caught:
            self.aa._assert_safe(
                ["codex", "exec", "-m", "gpt-6-astra", "--sandbox", "read-only",
                 "--dangerously-bypass-approvals-and-sandbox"]
            )
        self.assertIn("--dangerously", str(caught.exception))

    def test_refuses_an_unpinned_model(self):
        with self.assertRaises(RuntimeError):
            self.aa._assert_safe(["codex", "exec", "-m", "gpt-5", "--sandbox", "read-only"])

    def test_refuses_a_missing_read_only_sandbox(self):
        with self.assertRaises(RuntimeError):
            self.aa._assert_safe(["codex", "exec", "-m", "gpt-6-astra", "--json"])

    def test_both_real_argv_forms_pass_the_guard(self):
        self.do_init()
        self.run_cli("ask", "--from", "X", "--question", "q")
        for call in self.model_calls():
            self.aa._assert_safe(["codex"] + call["argv"])

    def test_no_dangerous_flag_reaches_the_cli(self):
        self.do_init()
        self.run_cli("ask", "--from", "X", "--question", "q")
        for call in self.calls():
            joined = " ".join(call["argv"]).lower()
            for bad in self.aa.FORBIDDEN_FLAG_SUBSTRINGS:
                self.assertNotIn(bad, joined)

    def test_scratch_never_lands_under_c_nsc(self):
        forbidden = Path(r"C:\NSC\astra-should-not-happen")
        os.environ["NSC_ASTRA_HOME"] = str(forbidden)
        import ask_astra

        aa = importlib.reload(ask_astra)
        self.assertFalse(forbidden.exists(), f"stale debris from an older run: {forbidden}")
        with self.assertRaises(RuntimeError) as caught:
            aa._out_file("ask")
        self.assertIn("refusing to write scratch", str(caught.exception))
        # Refusing after mkdir is not refusing: assert nothing was left behind.
        self.assertFalse(forbidden.exists(), f"_out_file created {forbidden} before refusing")

    def test_a_forbidden_home_creates_nothing_at_all(self):
        """The first version refused only AFTER mkdir, so it left the folder behind.

        A reviewer found `C:\\NSC\\astra-should-not-happen` on disk and could not
        explain it. Refusing while leaving debris is not refusing.
        """
        forbidden = Path(r"C:\NSC\astra-should-not-happen")
        self.assertFalse(forbidden.exists(), f"stale debris from an older run: {forbidden}")
        os.environ["NSC_ASTRA_HOME"] = str(forbidden)
        import ask_astra

        aa = importlib.reload(ask_astra)
        for argv in (["status"], ["init"], ["ask", "--from", "X", "--question", "q"]):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = aa.main(argv)
            self.assertEqual(code, aa.EXIT_CODEX_FAILED, argv)
            self.assertIn("refusing to work under", err.getvalue())
            self.assertFalse(forbidden.exists(), f"{argv} created {forbidden}")

    def test_the_forbidden_check_is_case_insensitive(self):
        os.environ["NSC_ASTRA_HOME"] = r"c:\nsc\lowercase-should-also-be-refused"
        import ask_astra

        aa = importlib.reload(ask_astra)
        self.assertTrue(aa._under_forbidden_root(aa.HOME))

    def test_every_subprocess_hides_its_console(self):
        """A console flash on every question would be Vincent's screen, repeatedly."""
        seen = []
        real_run = subprocess.run

        def spy(*args, **kwargs):
            seen.append(kwargs.get("creationflags"))
            return real_run(*args, **kwargs)

        self.aa.subprocess.run = spy
        try:
            self.do_init()
            self.run_cli("ask", "--from", "X", "--question", "q")
        finally:
            self.aa.subprocess.run = real_run
        self.assertTrue(seen)
        for flags in seen:
            self.assertEqual(flags, self.aa.CREATE_NO_WINDOW)

    def test_thread_file_is_written_atomically(self):
        """No half-written thread.json: the temp file is replaced, not appended."""
        seen = []
        real_replace = os.replace

        def spy(src, dst):
            seen.append((str(src), str(dst)))
            return real_replace(src, dst)

        self.aa.os.replace = spy
        try:
            self.do_init()
        finally:
            self.aa.os.replace = real_replace
        self.assertTrue(any(dst.endswith("thread.json") for _src, dst in seen))
        self.assertFalse(list(self.home.glob("thread.json.tmp*")))


# ==========================================================================
# status
# ==========================================================================


class Status(AstraTestCase):
    def test_status_makes_no_model_call(self):
        self.do_init()
        before = len(self.model_calls())
        code, out, _err = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.model_calls()), before)
        self.assertIn("01a0ae11-fake", out)

    def test_status_without_a_thread_says_run_init(self):
        code, out, _err = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("run `init`", out)

    def test_status_reports_the_lock_holder(self):
        self.do_init()
        (self.home / "astra.lock").write_text(
            json.dumps({"owner": "GER Agent", "pid": os.getpid(), "started_at": "2026-09-18T00:00:00Z"}),
            encoding="utf-8",
        )
        _code, out, _err = self.run_cli("status")
        self.assertIn("GER Agent", out)
        self.assertIn("pid_alive=True", out)

    def test_status_reports_the_last_question(self):
        self.do_init()
        self.run_cli("ask", "--from", "Viewer Agent", "--question", "q")
        _code, out, _err = self.run_cli("status")
        self.assertIn("Viewer Agent", out)

    def test_status_notices_a_changed_primer(self):
        self.do_init()
        self.primer.write_text("different primer\n", encoding="utf-8", newline="\n")
        _code, out, _err = self.run_cli("status")
        self.assertIn("CHANGED since init", out)

    def test_status_flags_the_test_override(self):
        os.environ["NSC_ASTRA_FAKE_ALIVE_PIDS"] = "1"
        _code, out, _err = self.run_cli("status")
        self.assertIn("test override active", out)


# ==========================================================================
# Small helpers
# ==========================================================================


class Helpers(AstraTestCase):
    def test_slug(self):
        self.assertEqual(self.aa._slug("Pipeline Maintainer Agent"), "pipeline-maintainer-agent")
        self.assertEqual(self.aa._slug("  !!!  "), "unknown")
        self.assertEqual(self.aa._slug(""), "unknown")

    def test_stamp_has_no_colons(self):
        self.assertNotIn(":", self.aa._stamp(self.aa._utc_now()))

    def test_thread_id_from_events_ignores_noise(self):
        stdout = "not json\n" + json.dumps({"type": "other"}) + "\n" + json.dumps(
            {"type": "thread.started", "thread_id": "abc"}
        )
        self.assertEqual(self.aa._thread_id_from_events(stdout), "abc")

    def test_thread_id_from_nested_shape(self):
        stdout = json.dumps({"type": "thread.started", "thread": {"id": "nested-1"}})
        self.assertEqual(self.aa._thread_id_from_events(stdout), "nested-1")

    def test_no_thread_id_returns_none(self):
        self.assertIsNone(self.aa._thread_id_from_events("nothing here\n{}\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
