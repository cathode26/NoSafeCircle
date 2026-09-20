#!/usr/bin/env python
"""Unit tests for run_job.py.

No network, no provider, no Docker, no Unity. Every external executable is a
fake written by this file into C:/nscrev/tmp/run-job/, and every path the tool
touches is redirected there with the NSC_RUN_JOB_* environment overrides.

Run:
    C:/Python313/python.exe -B C:/nscrev/job-tools/tests/test_run_job.py
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "run_job.py"
SCRATCH = Path(r"C:\nscrev\tmp\run-job") / "tests"
PYTHON = r"C:\Python313\python.exe"

sys.path.insert(0, str(HERE.parent))
import run_job  # noqa: E402  (imported for its pure functions)


GUIDE_TEXT = """# Running Codex bulk jobs safely

> **No Codex until {until}: all Claude for everything** (Vincent: "...").
> - **Scope:** host and Docker Codex share the account.
"""


def write_shim(path: Path, script: Path) -> Path:
    path.write_text(
        f'@echo off\r\n"{PYTHON}" -B "{script}" %*\r\n', encoding="ascii"
    )
    return path


class Fixture:
    """One scratch sandbox: fake exes, fake guide, fake canonical repo."""

    def __init__(self, root: Path):
        self.root = root
        self.bin = root / "bin"
        self.jobs = root / "jobs"
        self.nscrev = root / "nscrev"
        self.forbidden = root / "fake-NSC"
        self.canonical = self.forbidden / "NSC" / "NoSafeCircle"
        self.record = root / "record.jsonl"
        self.guide = root / "guide.md"
        for folder in (self.bin, self.jobs, self.nscrev, self.canonical):
            folder.mkdir(parents=True, exist_ok=True)
        (self.canonical / ".git").mkdir(exist_ok=True)
        (self.canonical / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        self.claude = write_shim(self.bin / "claude.cmd", HERE / "fake_claude.py")
        self.docker = write_shim(self.bin / "docker.cmd", HERE / "fake_docker.py")
        self.set_codex_off(days_ahead=2)

    def set_codex_off(self, days_ahead: int) -> None:
        until = _dt.date.today() + _dt.timedelta(days=days_ahead)
        self.guide.write_text(GUIDE_TEXT.format(until=until.isoformat()),
                              encoding="utf-8")

    def make_clone(self, name: str, worktree: bool = False,
                   no_git: bool = False, compose: bool = True) -> Path:
        clone = self.root / name
        clone.mkdir(parents=True, exist_ok=True)
        if worktree:
            (clone / ".git").write_text(
                "gitdir: ../fake-NSC/NSC/NoSafeCircle/.git/worktrees/x\n",
                encoding="utf-8",
            )
        elif not no_git:
            (clone / ".git").mkdir(exist_ok=True)
        if compose:
            (clone / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        return clone

    def make_brief(self, name: str, text: str = "Do the thing.\n") -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def env(self, **extra) -> dict:
        env = dict(os.environ)
        env.update({
            "NSC_RUN_JOB_NSCREV": str(self.nscrev),
            "NSC_RUN_JOB_JOBS_DIR": str(self.jobs),
            "NSC_RUN_JOB_TELEMETRY": str(self.jobs / "jobs.jsonl"),
            "NSC_RUN_JOB_GUIDE": str(self.guide),
            "NSC_RUN_JOB_CANONICAL": str(self.canonical),
            "NSC_RUN_JOB_FORBIDDEN_ROOT": str(self.forbidden),
            "NSC_RUN_JOB_CLAUDE": str(self.claude),
            "NSC_RUN_JOB_DOCKER": str(self.docker),
            "FAKE_CLAUDE_RECORD": str(self.record),
            "FAKE_DOCKER_RECORD": str(self.record),
            "TEMP": str(self.root / "tmp"),
            "TMP": str(self.root / "tmp"),
            "PYTHONPYCACHEPREFIX": str(self.root / "pycache"),
            # Since 2026-09-18 the NSC_RUN_JOB_* overrides above are ignored
            # unless this is set, so that a production caller cannot move
            # FORBIDDEN_ROOT and CANONICAL out of the way and then run a
            # read-write job against the real canonical checkout. The suite is
            # the only thing that sets it.
            "NSC_RUN_JOB_TESTING": "1",
        })
        (self.root / "tmp").mkdir(parents=True, exist_ok=True)
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def run(self, *args, **extra_env):
        proc = subprocess.run(
            [PYTHON, "-B", str(TOOL), *[str(a) for a in args]],
            capture_output=True, text=True, env=self.env(**extra_env),
            cwd=str(self.root), timeout=300,
        )
        return proc

    def records(self) -> list[dict]:
        if not self.record.exists():
            return []
        return [json.loads(line) for line in
                self.record.read_text(encoding="utf-8").splitlines() if line.strip()]

    def telemetry(self) -> list[dict]:
        path = self.jobs / "jobs.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Base(unittest.TestCase):
    counter = 0

    def setUp(self):
        Base.counter += 1
        root = SCRATCH / f"case{Base.counter:03d}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        self.fx = Fixture(root)

    def wait_for(self, predicate, seconds: int = 90) -> bool:
        """Poll until a detached background child has finished its work."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.2)
        return bool(predicate())

    def assertRefused(self, proc, *needles):
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        self.assertIn("REFUSED:", proc.stderr)
        for needle in needles:
            self.assertIn(needle, proc.stderr, msg=proc.stderr)


# ---------------------------------------------------------------------------
# argv each type builds
# ---------------------------------------------------------------------------

DOCKER_EXPECT = {
    # type: (service, model, max_turns, tools)
    "lookup": ("claude-exec", "claude-haiku-4-5-20251001", "30",
               ["Read", "Glob", "Grep", "Bash"]),
    "review": ("claude-exec", "claude-sonnet-5", "80",
               ["Read", "Glob", "Grep", "Bash"]),
    "test-run": ("claude-exec", "claude-haiku-4-5-20251001", "30",
                 ["Read", "Glob", "Grep", "Bash"]),
    "clone-edit": ("claude", "claude-sonnet-5", "60",
                   ["Read", "Glob", "Grep", "Bash", "Edit", "Write"]),
    "contract-draft": ("claude", "claude-sonnet-5", "60",
                       ["Read", "Glob", "Grep", "Bash", "Edit", "Write"]),
}


class TestDockerArgv(Base):
    def _dry(self, job_type):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run(job_type, "--brief", brief, "--clone", clone, "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        return proc, argv

    def test_each_docker_type_argv(self):
        for job_type, (service, model, turns, tools) in DOCKER_EXPECT.items():
            with self.subTest(job_type):
                self.setUp()
                proc, argv = self._dry(job_type)
                out = str((self.fx.jobs / "j").as_posix())
                self.assertEqual(argv[1:9], [
                    "compose", "-p", "nosafecircle", "run", "--rm", "-T",
                    "--no-deps", "-v",
                ])
                self.assertEqual(argv[9], f"{out}:/out")
                self.assertEqual(argv[10], service)
                self.assertEqual(argv[11:], [
                    "claude", "-p",
                    "--model", model,
                    "--max-turns", turns,
                    "--permission-mode", "dontAsk",
                    "--allowedTools", *tools,
                    "--disallowedTools", "Task",
                    "--output-format", "json",
                ])

    def test_dry_run_prints_msys_and_redirects(self):
        proc, _ = self._dry("lookup")
        self.assertIn("MSYS_NO_PATHCONV=1", proc.stdout)
        self.assertIn("docker compose -p nosafecircle run --rm -T --no-deps",
                      proc.stdout.replace("\\\n", "").replace("  ", " "))
        self.assertIn("j.prompt.md", proc.stdout)
        self.assertIn("j.json", proc.stdout)
        self.assertIn("j.log", proc.stdout)

    def test_dry_run_runs_nothing(self):
        self._dry("review")
        self.assertEqual(self.fx.records(), [])

    def test_model_override_alias(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("review", "--brief", brief, "--clone", clone,
                           "--model", "opus", "--dry-run")
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        self.assertIn("claude-opus-5", argv)

    def test_max_turns_override(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--max-turns", "5", "--dry-run")
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        self.assertEqual(argv[argv.index("--max-turns") + 1], "5")

    def test_out_override_is_mounted(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        out = self.fx.root / "custom-out"
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--out", out, "--dry-run")
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        self.assertEqual(argv[9], f"{out.as_posix()}:/out")


class TestHostArgv(Base):
    def test_host_lookup_argv(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        self.assertTrue(argv[0].endswith("claude.cmd"))
        self.assertEqual(argv[1:], [
            "-p",
            "--model", "claude-haiku-4-5-20251001",
            "--max-turns", "30",
            "--permission-mode", "dontAsk",
            "--allowedTools", "Read", "Glob", "Grep",
            "--disallowedTools", "Task",
            "--output-format", "json",
        ])
        self.assertNotIn("MSYS_NO_PATHCONV=1", proc.stdout)

    def test_advice_argv_is_opus_and_read_only_with_add_dir(self):
        brief = self.fx.make_brief("a.prompt.md")
        proc = self.fx.run("advice", "--brief", brief, "--dry-run")
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        self.assertEqual(argv[1:3], ["-p", "--add-dir"])
        self.assertIn(self.fx.forbidden.as_posix(), argv)
        self.assertIn(self.fx.nscrev.as_posix(), argv)
        self.assertIn("claude-opus-5", argv)
        self.assertNotIn("Write", argv)
        self.assertNotIn("Edit", argv)
        self.assertNotIn("Bash", argv)

    def test_agent_flag(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--agent", "scribe",
                           "--dry-run")
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        self.assertEqual(argv[1:4], ["-p", "--agent", "scribe"])

    def test_allow_bash_builds_program_rule(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-bash", "git", "--allow-bash", "python",
                           "--dry-run")
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        start = argv.index("--allowedTools")
        end = argv.index("--disallowedTools")
        self.assertEqual(argv[start + 1:end],
                         ["Read", "Glob", "Grep", "Bash(git:*)", "Bash(python:*)"])

    def test_allow_tool_passes_an_exact_command_prefix_rule(self):
        brief = self.fx.make_brief("h.prompt.md")
        rule = "Bash(git -C C:/NSC/NSC/NoSafeCircle log:*)"
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-tool", rule, "--allow-tool", "Bash(gh run list:*)",
                           "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        start = argv.index("--allowedTools")
        end = argv.index("--disallowedTools")
        self.assertEqual(argv[start + 1:end],
                         ["Read", "Glob", "Grep", rule, "Bash(gh run list:*)"])
        self.assertIn(f'"{rule}"', proc.stdout)  # quoted in the copy-paste line

    def test_allow_tool_refused_on_docker_types(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--allow-tool", "Bash(git:*)", "--dry-run")
        self.assertRefused(proc, "--allow-tool is for host types")

    def test_every_type_has_dont_ask_and_no_task(self):
        for job_type in sorted(run_job.JOB_TYPES):
            with self.subTest(job_type):
                self.setUp()
                brief = self.fx.make_brief("j.prompt.md")
                args = [job_type, "--brief", brief, "--dry-run"]
                if run_job.JOB_TYPES[job_type]["needs_clone"]:
                    args += ["--clone", self.fx.make_clone("cj-x")]
                proc = self.fx.run(*args)
                argv = json.loads(proc.stdout.split("argv:", 1)[1])
                self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
                self.assertEqual(argv[argv.index("--disallowedTools") + 1], "Task")
                self.assertEqual(argv[argv.index("--output-format") + 1], "json")


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


class TestCloneGuards(Base):
    def test_refuses_canonical_checkout(self):
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("lookup", "--brief", brief,
                           "--clone", self.fx.canonical, "--dry-run")
        self.assertRefused(proc, "canonical checkout", "git clone -q")

    def test_refuses_anything_under_forbidden_root(self):
        inside = self.fx.forbidden / "somewhere" / "else"
        inside.mkdir(parents=True)
        (inside / ".git").mkdir()
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", inside, "--dry-run")
        self.assertRefused(proc, "canonical checkout")

    def test_refuses_git_worktree(self):
        clone = self.fx.make_clone("wt-x", worktree=True)
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("clone-edit", "--brief", brief, "--clone", clone,
                           "--dry-run")
        self.assertRefused(proc, "git worktree", ".git is a file")

    def test_refuses_non_repo(self):
        clone = self.fx.make_clone("plain", no_git=True)
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone, "--dry-run")
        self.assertRefused(proc, "no .git")

    def test_refuses_missing_clone(self):
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("lookup", "--brief", brief,
                           "--clone", self.fx.root / "nope", "--dry-run")
        self.assertRefused(proc, "does not exist")

    def test_docker_type_needs_clone(self):
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("lookup", "--brief", brief, "--dry-run")
        self.assertRefused(proc, "needs --clone")

    def test_refuses_clone_without_compose_yaml(self):
        clone = self.fx.make_clone("cj-nc", compose=False)
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone, "--dry-run")
        self.assertRefused(proc, "no compose.yaml")

    def test_host_type_clone_also_guarded(self):
        brief = self.fx.make_brief("j.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--clone", self.fx.canonical, "--dry-run")
        self.assertRefused(proc, "canonical checkout")


class TestDockerGuards(Base):
    def test_refuses_when_engine_down(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--skip-account-check", FAKE_DOCKER_ENGINE_DOWN="1")
        self.assertRefused(proc, "Docker engine did not answer",
                           "Start Docker Desktop")

    def test_refuses_when_image_missing(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--skip-account-check",
                           FAKE_DOCKER_NO_IMAGE="nosafecircle-claude-exec:latest")
        self.assertRefused(proc, "is not built",
                           "docker compose -p nosafecircle build claude-exec")

    def test_engine_and_image_checked_before_running(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--skip-account-check")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        verbs = [r["argv"][0] for r in self.fx.records()]
        self.assertEqual(verbs[:2], ["version", "images"])
        self.assertEqual(verbs[2], "compose")


class TestCodexGuard(Base):
    def test_refuses_astra_while_codex_off(self):
        self.fx.set_codex_off(days_ahead=2)
        brief = self.fx.make_brief("a.prompt.md")
        until = (_dt.date.today() + _dt.timedelta(days=2)).isoformat()
        proc = self.fx.run("advice", "--brief", brief, "--astra", "--dry-run")
        self.assertRefused(proc, f"Codex is off until {until}", "drop --astra")

    def test_date_comes_from_the_banner_not_a_constant(self):
        self.fx.set_codex_off(days_ahead=30)
        until = (_dt.date.today() + _dt.timedelta(days=30)).isoformat()
        brief = self.fx.make_brief("a.prompt.md")
        proc = self.fx.run("advice", "--brief", brief, "--astra", "--dry-run")
        self.assertRefused(proc, until)

    def test_fails_closed_when_banner_unreadable(self):
        self.fx.guide.write_text("# guide with no banner\n", encoding="utf-8")
        brief = self.fx.make_brief("a.prompt.md")
        proc = self.fx.run("advice", "--brief", brief, "--astra", "--dry-run")
        self.assertRefused(proc, "cannot tell whether Codex is on", "fail closed")

    def test_fails_closed_when_banner_date_is_junk(self):
        with self.assertRaises(run_job.Refused):
            run_job.guard_codex_available(guide=self.fx.guide.with_name("missing.md"))

    def test_codex_back_still_refuses_because_tool_is_claude_only(self):
        self.fx.set_codex_off(days_ahead=-1)  # banner date already passed
        brief = self.fx.make_brief("a.prompt.md")
        proc = self.fx.run("advice", "--brief", brief, "--astra", "--dry-run")
        self.assertRefused(proc, "only builds Claude job commands", "4.4")

    def test_astra_rejected_on_other_types(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--astra", "--dry-run")
        self.assertRefused(proc, "--astra is only for `advice`")

    def test_advice_without_astra_runs_on_claude(self):
        brief = self.fx.make_brief("a.prompt.md")
        proc = self.fx.run("advice", "--brief", brief, "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)


class TestBriefAndArgGuards(Base):
    def test_refuses_missing_brief(self):
        proc = self.fx.run("host-lookup", "--brief", self.fx.root / "nope.md",
                           "--dry-run")
        self.assertRefused(proc, "does not exist", "templates")

    def test_refuses_empty_brief(self):
        brief = self.fx.make_brief("empty.prompt.md", "   \n\n")
        proc = self.fx.run("host-lookup", "--brief", brief, "--dry-run")
        self.assertRefused(proc, "is empty")

    def test_refuses_unfilled_template(self):
        brief = self.fx.make_brief("t.prompt.md",
                                   "<!-- Docker Claude job: LOOKUP.\n"
                                   "Fill every <...> and delete this comment "
                                   "before running. -->\n\nbody\n")
        proc = self.fx.run("host-lookup", "--brief", brief, "--dry-run")
        self.assertRefused(proc, "template header comment")

    def test_refuses_unknown_model(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--model", "gpt-6-astra", "--dry-run")
        self.assertRefused(proc, "not a model this tool will pass on")

    def test_refuses_agent_on_docker_type(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--agent", "scribe", "--dry-run")
        self.assertRefused(proc, "--agent works only for host types")

    def test_refuses_allow_bash_on_docker_type(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("lookup", "--brief", brief, "--clone", clone,
                           "--allow-bash", "git", "--dry-run")
        self.assertRefused(proc, "--allow-bash is for host types")

    def test_refuses_allow_bash_with_a_path_or_command(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-bash", "C:/Python313/python.exe", "--dry-run")
        self.assertRefused(proc, "not a bare program name")

    def test_refuses_out_inside_forbidden_root(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--out", self.fx.forbidden / "out", "--dry-run")
        self.assertRefused(proc, "is inside")

    def test_refuses_unsafe_job_name(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--name", "bad name; rm", "--dry-run")
        self.assertRefused(proc, "will not pass on")

    def test_refuses_unknown_type(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("bulk-rewrite", "--brief", brief)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid choice", proc.stderr)

    def test_missing_executable_override_refused(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--dry-run",
                           NSC_RUN_JOB_CLAUDE=str(self.fx.root / "no-claude.cmd"))
        self.assertRefused(proc, "which does not exist")


# ---------------------------------------------------------------------------
# account check
# ---------------------------------------------------------------------------


class TestAccountCheck(Base):
    def test_prints_account_and_percentages(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("account: cathode26@gmail.com", proc.stdout)
        self.assertIn("session 42%", proc.stdout)
        self.assertIn("week 61%", proc.stdout)
        usage_calls = [r for r in self.fx.records() if "/usage" in r["argv"]]
        self.assertEqual(len(usage_calls), 1)
        self.assertEqual(usage_calls[0]["argv"],
                         ["-p", "/usage", "--output-format", "json"])

    def test_warns_over_85_percent(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run(
            "host-lookup", "--brief", brief,
            FAKE_CLAUDE_USAGE="Account: gmail.user@gmail.com\n"
                              "Session: 91% used\nWeek: 88% used\n")
        self.assertIn("WARNING: session usage is 91%", proc.stdout)
        self.assertIn("WARNING: week usage is 88%", proc.stdout)
        self.assertEqual(proc.returncode, 0)

    def test_unparseable_usage_is_a_warning_not_a_crash(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           FAKE_CLAUDE_USAGE="totally unexpected text")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("WARNING", proc.stdout)
        self.assertIn("continuing", proc.stdout)
        self.assertIn("ANSWER:", proc.stdout)

    def test_skip_flag_means_no_provider_call(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual([r for r in self.fx.records() if "/usage" in r["argv"]], [])

    def test_dry_run_never_calls_usage(self):
        brief = self.fx.make_brief("h.prompt.md")
        self.fx.run("host-lookup", "--brief", brief, "--dry-run")
        self.assertEqual(self.fx.records(), [])

    def test_parse_usage_variants(self):
        cases = [
            ("Account: a@b.com\nCurrent session: 42% used\nWeek: 61% used",
             "a@b.com", 42, 61),
            ('{"result": "logged in as x@y.org\\nSession 7% / Weekly 12%"}',
             "x@y.org", 7, 12),
            ("Session usage 100%\nWeek usage 3%", None, 100, 3),
            ("nothing useful here", None, None, None),
        ]
        for raw, account, session, week in cases:
            with self.subTest(raw[:30]):
                got = run_job.parse_usage(raw)
                self.assertEqual(got["account"], account)
                self.assertEqual(got["session_pct"], session)
                self.assertEqual(got["week_pct"], week)


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


class TestSummary(Base):
    def _job(self):
        return {
            "type": "review", "name": "n", "model": "claude-sonnet-5",
            "where": "docker:claude-exec", "max_turns": 80,
            "json_path": Path(r"C:\nscrev\claude-jobs\n.json"),
            "log_path": Path(r"C:\nscrev\claude-jobs\n.log"),
            "out_dir": Path(r"C:\nscrev\claude-jobs\n"),
            "brief": Path(r"C:\nscrev\claude-jobs\n.prompt.md"),
            "clone": None, "service": "claude-exec",
        }

    def test_at_most_20_lines_even_for_a_huge_result(self):
        data = {
            "subtype": "success", "is_error": False, "num_turns": 12,
            "total_cost_usd": 1.5,
            "result": "VERDICT APPROVE\n" + "\n".join(f"line {i}" for i in range(500)),
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "permission_denials": [],
        }
        lines = run_job.build_summary(self._job(), data, 12.0, 0)
        self.assertLessEqual(len(lines), 20)
        self.assertIn("VERDICT APPROVE", lines[1])
        self.assertTrue(any("full JSON:" in x for x in lines))
        self.assertTrue(any("log:" in x for x in lines))
        self.assertTrue(any("telemetry:" in x for x in lines))

    def test_counts_and_denials(self):
        data = {
            "subtype": "success", "is_error": False, "num_turns": 3,
            "total_cost_usd": 0.25,
            "result": "ANSWER: yes",
            "usage": {"input_tokens": 10, "output_tokens": 20,
                      "cache_read_input_tokens": 30,
                      "cache_creation_input_tokens": 40},
            "permission_denials": [{"tool_name": "Write"}, {"tool_name": "Write"},
                                   {"tool_name": "Task"}],
            "subagent_stats": {"spawned": 2},
        }
        lines = run_job.build_summary(self._job(), data, 3.5, 0)
        text = "\n".join(lines)
        self.assertIn("tokens: in 10 out 20 cache_read 30 cache_create 40", text)
        self.assertIn("cost: $0.2500", text)
        self.assertIn("permission denials: 3 (Task, Write)", text)
        self.assertIn("WARNING: subagents spawned: 2", text)

    def test_verdict_line_picked_over_preamble(self):
        for result, expected in (
            ("blah blah\nVERDICT FIX FIRST\nmore", "VERDICT FIX FIRST"),
            ("ANSWER: two files\nEVIDENCE:", "ANSWER: two files"),
            ("EDIT: branch abc\nFiles: x", "EDIT: branch abc"),
            ("ROOT CAUSE: the mount\nNEXT STEP: remount", "ROOT CAUSE: the mount"),
            ("just prose here", "just prose here"),
            ("", "(no result text)"),
        ):
            with self.subTest(expected):
                self.assertEqual(run_job.pick_verdict_line(result), expected)

    def test_no_result_json(self):
        lines = run_job.build_summary(self._job(), None, 1.0, 137)
        self.assertIn("NO RESULT JSON (exit 137)", lines[0])
        self.assertLessEqual(len(lines), 20)

    def test_garbage_output_does_not_crash_and_exits_nonzero(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                           FAKE_CLAUDE_GARBAGE="1")
        self.assertIn("NO RESULT JSON", proc.stdout)
        self.assertEqual(proc.returncode, 1)

    def test_is_error_exits_nonzero(self):
        brief = self.fx.make_brief("h.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                           FAKE_CLAUDE_IS_ERROR="1")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("is_error=True", proc.stdout)

    def test_printed_summary_is_capped_at_20_lines(self):
        brief = self.fx.make_brief("h.prompt.md")
        big = "ANSWER: ok\n" + "\n".join(f"detail {i}" for i in range(200))
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                           FAKE_CLAUDE_RESULT=big)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertLessEqual(len(proc.stdout.strip().splitlines()), 20)

    def test_brief_is_the_stdin_and_outputs_land_on_disk(self):
        brief = self.fx.make_brief("h.prompt.md", "PROMPT BODY 12345\n")
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        job_records = [r for r in self.fx.records() if r.get("stdin")]
        self.assertIn("PROMPT BODY 12345", job_records[0]["stdin"])
        self.assertTrue((self.fx.jobs / "h.json").exists())
        self.assertTrue((self.fx.jobs / "h.log").exists())
        self.assertIn("fake claude log line",
                      (self.fx.jobs / "h.log").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# telemetry
# ---------------------------------------------------------------------------


class TestTelemetry(Base):
    def test_one_line_per_job_with_every_field(self):
        brief = self.fx.make_brief("j.prompt.md")
        clone = self.fx.make_clone("cj-x")
        proc = self.fx.run("review", "--brief", brief, "--clone", clone)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        rows = self.fx.telemetry()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["type"], "review")
        self.assertEqual(row["name"], "j")
        self.assertEqual(row["account"], "cathode26@gmail.com")
        self.assertEqual(row["session_pct"], 42)
        self.assertEqual(row["week_pct"], 61)
        self.assertEqual(row["model"], "claude-sonnet-5")
        self.assertEqual(row["where"], "docker:claude-exec")
        self.assertEqual(row["service"], "claude-exec")
        self.assertEqual(row["clone"], clone.as_posix())
        self.assertGreaterEqual(row["duration_s"], 0.0)
        self.assertEqual(row["tokens"], {"input": 90, "output": 210,
                                         "cache_read": 4000, "cache_creation": 300})
        self.assertEqual(row["cost_usd"], 0.0102)
        self.assertEqual(row["exit_status"], "success")
        self.assertEqual(row["exit_code"], 0)
        self.assertEqual(row["num_turns"], 4)
        self.assertEqual(row["max_turns"], 80)
        self.assertEqual(row["permission_denials"], [])
        self.assertEqual(row["paths"]["json"], (self.fx.jobs / "j.json").as_posix())
        self.assertEqual(row["paths"]["log"], (self.fx.jobs / "j.log").as_posix())
        self.assertEqual(row["paths"]["out"], (self.fx.jobs / "j").as_posix())
        self.assertEqual(row["paths"]["brief"], brief.as_posix())
        self.assertRegex(row["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_appends_and_never_rewrites(self):
        brief = self.fx.make_brief("h.prompt.md")
        self.fx.run("host-lookup", "--brief", brief, "--skip-account-check")
        self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                    "--name", "second")
        rows = self.fx.telemetry()
        self.assertEqual([r["name"] for r in rows], ["h", "second"])

    def test_error_status_recorded(self):
        brief = self.fx.make_brief("h.prompt.md")
        self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                    FAKE_CLAUDE_IS_ERROR="1")
        self.assertEqual(self.fx.telemetry()[0]["exit_status"], "error:success")

    def test_no_result_json_status(self):
        brief = self.fx.make_brief("h.prompt.md")
        self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                    FAKE_CLAUDE_GARBAGE="1")
        self.assertEqual(self.fx.telemetry()[0]["exit_status"], "no-result-json")

    def test_dry_run_writes_no_telemetry(self):
        brief = self.fx.make_brief("h.prompt.md")
        self.fx.run("host-lookup", "--brief", brief, "--dry-run")
        self.assertEqual(self.fx.telemetry(), [])

    def test_telemetry_failure_does_not_fail_the_job(self):
        brief = self.fx.make_brief("h.prompt.md")
        # point the telemetry file at a path that cannot be created
        blocker = self.fx.root / "blocker"
        blocker.write_text("not a directory\n", encoding="utf-8")
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                           NSC_RUN_JOB_TELEMETRY=str(blocker / "sub" / "jobs.jsonl"))
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("ANSWER:", proc.stdout)
        self.assertIn("WARNING: telemetry not written", proc.stdout)


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


class TestMisc(Base):
    def test_every_documented_type_exists(self):
        self.assertEqual(sorted(run_job.JOB_TYPES), [
            "advice", "clone-edit", "contract-draft", "host-lookup", "lookup",
            "review", "test-run",
        ])

    def test_docker_types_never_get_edit_write_on_claude_exec(self):
        for job_type, cfg in run_job.JOB_TYPES.items():
            if cfg["service"] == "claude-exec":
                self.assertNotIn("Write", cfg["tools"], job_type)
                self.assertNotIn("Edit", cfg["tools"], job_type)

    def test_banner_reader_finds_the_real_guide_date_format(self):
        self.fx.set_codex_off(days_ahead=3)
        until, how = run_job.read_codex_banner(self.fx.guide)
        self.assertEqual(until, (_dt.date.today() + _dt.timedelta(days=3)).isoformat())
        self.assertIn("banner", how)

    def test_shell_quote_protects_spaces(self):
        self.assertEqual(run_job.shell_quote("C:/a/b"), "C:/a/b")
        self.assertEqual(run_job.shell_quote("a b"), '"a b"')
        self.assertEqual(run_job.shell_quote("Bash(git:*)"), '"Bash(git:*)"')

    def test_background_returns_at_once_and_runs_the_job(self):
        brief = self.fx.make_brief("bg.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--background",
                           "--skip-account-check")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("started in background, pid", proc.stdout)
        self.assertTrue(self.wait_for(lambda: self.fx.telemetry()),
                        "background child never finished")
        rows = self.fx.telemetry()
        self.assertEqual(len(rows), 1, "background child did not record telemetry")
        self.assertEqual(rows[0]["name"], "bg")

    def test_background_forwards_every_flag_to_the_child(self):
        brief = self.fx.make_brief("bg2.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--background",
                           "--skip-account-check", "--model", "sonnet",
                           "--max-turns", "9", "--agent", "scribe",
                           "--allow-bash", "git",
                           "--allow-tool", "Bash(gh run list:*)",
                           "--add-dir", self.fx.root, "--name", "bgflags")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertTrue(self.wait_for(lambda: self.fx.telemetry()),
                        "background child never finished")
        argv = next(r["argv"] for r in self.fx.records() if "--model" in r["argv"])
        self.assertEqual(argv[argv.index("--model") + 1], "claude-sonnet-5")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "9")
        self.assertEqual(argv[argv.index("--agent") + 1], "scribe")
        self.assertIn("Bash(git:*)", argv)
        self.assertIn("Bash(gh run list:*)", argv)
        self.assertIn(self.fx.root.as_posix(), argv)
        self.assertEqual(self.fx.telemetry()[0]["name"], "bgflags")


class TestAccountGuard(Base):
    """Vincent's rule: outsourced work spends cathode26@gmail.com. A job that would spend another
    account, or cannot tell which it would spend, is refused before anything runs."""

    def test_wrong_account_is_refused_before_the_job_runs(self):
        brief = self.fx.make_brief("wrong-account.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           FAKE_CLAUDE_ACCOUNT="Vincent.j.liguori@outlook.com")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Vincent.j.liguori@outlook.com", proc.stdout + proc.stderr)
        self.assertIn("cathode26@gmail.com", proc.stdout + proc.stderr)
        self.assertEqual([r for r in self.fx.records() if r.get("stdin")], [],
                         "the job must not run on the wrong account")

    def test_allow_account_runs_it_and_says_so(self):
        brief = self.fx.make_brief("allowed-account.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                           "--allow-account", "Vincent.j.liguori@outlook.com",
                           FAKE_CLAUDE_ACCOUNT="Vincent.j.liguori@outlook.com")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("WARNING", proc.stdout)
        self.assertTrue([r for r in self.fx.records() if r.get("stdin")])

    def test_unknown_account_fails_closed(self):
        brief = self.fx.make_brief("unknown-account.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           FAKE_CLAUDE_ACCOUNT="__none__")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot tell which account", proc.stdout + proc.stderr)
        self.assertEqual([r for r in self.fx.records() if r.get("stdin")], [])


# ---------------------------------------------------------------------------
# Regressions from the Fable review of 2026-09-18.
#
# Every finding below passed the suite as it stood. Each test here fails
# against the pre-fix tool - proven with tests/review_mutation_check.py, which
# reverts each fix one at a time and confirms something goes red.
# ---------------------------------------------------------------------------


class ReviewCloneGuardSpellings(Base):
    """The clone guard compared strings, so other spellings of the same
    directory walked straight past it. `resolve()` keeps the `\\?\` and UNC
    prefixes, `relative_to` raises ValueError, and `is_under` returned False."""

    SPELLINGS = [
        "\\\\?\\{path}",
        "\\\\localhost\\{drive}$\\{rest}",
        "\\\\127.0.0.1\\{drive}$\\{rest}",
    ]

    def _spellings_of(self, path: Path):
        text = str(path)
        drive = text[0]
        rest = text[3:]
        out = [self.SPELLINGS[0].format(path=text)]
        for template in self.SPELLINGS[1:]:
            out.append(template.format(drive=drive, rest=rest))
        out.append(text.lower())
        out.append(str(path.parent / ".." / path.parent.name / path.name))
        return out

    def test_every_spelling_of_the_canonical_repo_is_refused(self):
        canonical = run_job.CANONICAL
        if not canonical.is_dir():
            self.skipTest(f"{canonical} is not on this machine")
        for spelling in self._spellings_of(canonical):
            with self.subTest(spelling=spelling):
                with self.assertRaises(run_job.Refused) as caught:
                    run_job.guard_clone(Path(spelling), True, "clone-edit")
                self.assertIn("canonical checkout", str(caught.exception))

    def test_every_spelling_of_the_forbidden_root_is_under_it(self):
        root = run_job.FORBIDDEN_ROOT
        if not root.is_dir():
            self.skipTest(f"{root} is not on this machine")
        for spelling in self._spellings_of(run_job.CANONICAL):
            with self.subTest(spelling=spelling):
                self.assertTrue(run_job.is_under(Path(spelling), root))

    def test_a_real_job_clone_is_still_accepted(self):
        clone = self.fx.make_clone("cj-ok")
        self.assertEqual(run_job.guard_clone(clone, True, "clone-edit"), clone.resolve())

    def test_a_path_outside_the_root_is_not_under_it(self):
        self.assertFalse(run_job.is_under(self.fx.root / "elsewhere", run_job.FORBIDDEN_ROOT))


class ReviewAllowToolWidening(Base):
    """`--allow-tool` appended any string verbatim, so a read-only advice job
    could be handed Write, Edit and unrestricted Bash on Opus with C:/NSC on
    --add-dir."""

    def test_write_tools_are_refused_on_a_read_only_type(self):
        brief = self.fx.make_brief("widen.prompt.md")
        for rule in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            with self.subTest(rule=rule):
                proc = self.fx.run("advice", "--brief", brief,
                                   "--allow-tool", rule, "--dry-run")
                self.assertRefused(proc, "read-only job type")

    def test_bare_bash_is_refused_everywhere(self):
        brief = self.fx.make_brief("bare-bash.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-tool", "Bash", "--dry-run")
        self.assertRefused(proc, "unrestricted shell")

    def test_subagent_tools_are_refused_on_every_type(self):
        brief = self.fx.make_brief("subagent.prompt.md")
        for rule in ("Task", "Agent", "Task(anything)", "agent"):
            with self.subTest(rule=rule):
                proc = self.fx.run("host-lookup", "--brief", brief,
                                   "--allow-tool", rule, "--dry-run")
                self.assertRefused(proc, "spawn its own subagents")

    def test_a_scoped_bash_rule_is_still_allowed(self):
        """The documented use of --allow-tool must keep working."""
        brief = self.fx.make_brief("scoped.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-tool", "Bash(git log:*)", "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("Bash(git log:*)", proc.stdout)

    def test_docker_types_refuse_allow_tool_outright(self):
        """Docker types carry a verified tool list and take no additions at all,
        so the widening path does not exist there. Pinned so that a future
        loosening of --allow-tool has to face this test."""
        clone = self.fx.make_clone("cj-rw")
        brief = self.fx.make_brief("rw.prompt.md")
        proc = self.fx.run("clone-edit", "--brief", brief, "--clone", clone,
                           "--allow-tool", "Write", "--dry-run")
        self.assertRefused(proc, "host types")

    def test_the_final_tool_list_is_checked_once_more(self):
        """guard_tool_list is the belt-and-braces pass over the assembled list,
        whatever route a rule took to reach it."""
        with self.assertRaises(run_job.Refused):
            run_job.guard_tool_list(["Read", "Task"], run_job.HOST_READ_ONLY_TOOLS, "host-lookup")
        with self.assertRaises(run_job.Refused):
            run_job.guard_tool_list(["Read", "Write"], run_job.HOST_READ_ONLY_TOOLS, "host-lookup")
        run_job.guard_tool_list(["Read", "Bash(git log:*)"],
                                run_job.HOST_READ_ONLY_TOOLS, "host-lookup")

    def test_a_malformed_rule_is_refused(self):
        # A single token (no top-level comma or space, so round 3's split
        # leaves it whole) that still is not `Tool` or `Tool(specifier)`:
        # unbalanced parentheses and a stray `!` are not valid syntax either
        # way.
        brief = self.fx.make_brief("malformed.prompt.md")
        for rule in ("Bash(unterminated", "not-a-rule!"):
            with self.subTest(rule=rule):
                proc = self.fx.run("host-lookup", "--brief", brief,
                                   "--allow-tool", rule, "--dry-run")
                self.assertRefused(proc, "not a tool rule")

    def test_an_unknown_tool_is_refused(self):
        brief = self.fx.make_brief("unknown-tool.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-tool", "WebSocket", "--dry-run")
        self.assertRefused(proc, "not part of")

    # -- round 3 (2026-09-18 review 2): several rules packed into one
    # --allow-tool value parsed as a single rule with a greedy specifier. ----

    def test_a_packed_allow_tool_value_is_refused(self):
        """`claude --help` says --allowedTools is a comma-or-space-separated
        list, so the CLI would split each of these into several rules -
        including Agent/Write/Task, which no read-only type may have."""
        brief = self.fx.make_brief("packed.prompt.md")
        for packed in (
            "Read(a),Bash,Agent,Write,Read(b)",
            "Glob(x) Write(y)",
            "Grep(a) Task Read(b)",
            "mcp__x(a),Write(b)",
        ):
            with self.subTest(packed=packed):
                proc = self.fx.run("host-lookup", "--brief", brief,
                                   "--allow-tool", packed, "--dry-run")
                self.assertRefused(proc)

    def test_the_same_rules_pass_as_separate_legitimate_flags(self):
        brief = self.fx.make_brief("separate.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-tool", "Read(a)",
                           "--allow-tool", "Bash(git log:*)",
                           "--allow-tool", "Read(b)", "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        for rule in ("Read(a)", "Bash(git log:*)", "Read(b)"):
            self.assertIn(rule, argv)

    def test_a_packed_value_of_only_legitimate_rules_is_split_and_kept(self):
        """Proves the fix splits (not just refuses): several legitimate rules
        packed into one flag must all reach --allowedTools, individually."""
        brief = self.fx.make_brief("packed-ok.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-tool", "Read(a) Read(b),Bash(git log:*)",
                           "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        for rule in ("Read(a)", "Read(b)", "Bash(git log:*)"):
            self.assertIn(rule, argv)
        self.assertNotIn("Read(a) Read(b),Bash(git log:*)", argv)

    def test_guard_tool_list_also_splits_a_packed_entry(self):
        """The belt-and-braces pass must not be fooled by a packed string
        that reaches it directly, bypassing guard_allow_tool."""
        with self.assertRaises(run_job.Refused):
            run_job.guard_tool_list(["Read(a),Write(b)"], run_job.HOST_READ_ONLY_TOOLS,
                                    "host-lookup")
        with self.assertRaises(run_job.Refused):
            run_job.guard_tool_list(["Grep(a) Task"], run_job.HOST_READ_ONLY_TOOLS,
                                    "host-lookup")
        run_job.guard_tool_list(["Read(a) Read(b)"], run_job.HOST_READ_ONLY_TOOLS,
                                "host-lookup")

    # -- round 3: only an empty Bash specifier was refused; Bash(*) and
    # friends constrain nothing and reached the argv. -----------------------

    def test_unconstrained_bash_specifiers_are_refused(self):
        brief = self.fx.make_brief("bash-noop.prompt.md")
        for rule in ("Bash(*)", "Bash( )", "Bash(:*)", "Bash(**)", "bash(*)"):
            with self.subTest(rule=rule):
                proc = self.fx.run("host-lookup", "--brief", brief,
                                   "--allow-tool", rule, "--dry-run")
                self.assertRefused(proc, "unrestricted shell")

    def test_scoped_bash_specifiers_still_work(self):
        brief = self.fx.make_brief("bash-scoped.prompt.md")
        for rule in ("Bash(git log:*)", "Bash(git status:*)"):
            with self.subTest(rule=rule):
                proc = self.fx.run("host-lookup", "--brief", brief,
                                   "--allow-tool", rule, "--dry-run")
                self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
                argv = json.loads(proc.stdout.split("argv:", 1)[1])
                self.assertIn(rule, argv)

    def test_allow_bash_shorthand_still_works(self):
        brief = self.fx.make_brief("bash-shorthand.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--allow-bash", "git", "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        argv = json.loads(proc.stdout.split("argv:", 1)[1])
        self.assertIn("Bash(git:*)", argv)


class ReviewAccountCache(Base):
    """The 24h account cache failed open: a `checked_at` in the future never
    expired, and the file lives where every agent can write it."""

    def _poison(self, account: str = "cathode26@gmail.com") -> Path:
        self.fx.jobs.mkdir(parents=True, exist_ok=True)
        path = self.fx.jobs / "account-cache.json"
        path.write_text(
            json.dumps({"claude": {"account": account, "checked_at": 9e12},
                        "claude-exec": {"account": account, "checked_at": 9e12}}),
            encoding="utf-8",
        )
        return path

    def test_a_poisoned_cache_cannot_approve_a_wrong_account(self):
        self._poison()
        clone = self.fx.make_clone("cj-cache")
        brief = self.fx.make_brief("cache.prompt.md")
        proc = self.fx.run("clone-edit", "--brief", brief, "--clone", clone,
                           FAKE_DOCKER_ACCOUNT="someone@outlook.com")
        self.assertRefused(proc, "someone@outlook.com")

    def test_the_docker_login_is_asked_every_time(self):
        self._poison()
        clone = self.fx.make_clone("cj-ask")
        brief = self.fx.make_brief("ask.prompt.md")
        self.fx.run("clone-edit", "--brief", brief, "--clone", clone,
                    FAKE_DOCKER_ACCOUNT="someone@outlook.com")
        asked = [r for r in self.fx.records()
                 if "auth" in r.get("argv", []) and "status" in r.get("argv", [])]
        self.assertTrue(asked, "the container login was never asked for")

    def test_the_docker_branch_reads_the_container_account(self):
        """FAKE_DOCKER_ACCOUNT existed but nothing used it, so a Docker branch
        that always returned the Gmail address would have kept the suite green."""
        clone = self.fx.make_clone("cj-branch")
        brief = self.fx.make_brief("branch.prompt.md")
        proc = self.fx.run("clone-edit", "--brief", brief, "--clone", clone,
                           FAKE_DOCKER_ACCOUNT="wrong@outlook.com")
        self.assertRefused(proc, "wrong@outlook.com")
        proc = self.fx.run("clone-edit", "--brief", brief, "--clone", clone,
                           "--dry-run", FAKE_DOCKER_ACCOUNT="cathode26@gmail.com")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_the_cache_file_is_gone_for_good(self):
        self.assertFalse(hasattr(run_job, "ACCOUNT_CACHE"))
        self.assertFalse(hasattr(run_job, "_read_account_cache"))


class ReviewEnvironmentOverrides(Base):
    """The NSC_RUN_JOB_* overrides relaxed the guards in production: point
    FORBIDDEN_ROOT and CANONICAL elsewhere and a write job ran in the real
    canonical checkout."""

    def _constants(self, env_extra: dict) -> dict:
        env = dict(os.environ)
        env.pop("NSC_RUN_JOB_TESTING", None)
        env.update({k: str(v) for k, v in env_extra.items()})
        env["PYTHONPYCACHEPREFIX"] = str(self.fx.root / "pycache")
        proc = subprocess.run(
            [PYTHON, "-B", "-c",
             "import json,sys;sys.path.insert(0,r'" + str(HERE.parent) + "');"
             "import run_job;"
             "print(json.dumps({'nscrev':str(run_job.NSCREV),"
             "'canonical':str(run_job.CANONICAL),"
             "'forbidden':str(run_job.FORBIDDEN_ROOT),"
             "'ignored':run_job._IGNORED_OVERRIDES,'testing':run_job.TESTING}))"],
            capture_output=True, text=True, env=env, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_overrides_are_ignored_without_the_testing_flag(self):
        got = self._constants({
            "NSC_RUN_JOB_FORBIDDEN_ROOT": str(self.fx.forbidden),
            "NSC_RUN_JOB_CANONICAL": str(self.fx.canonical),
            "NSC_RUN_JOB_NSCREV": str(self.fx.nscrev),
        })
        self.assertFalse(got["testing"])
        self.assertEqual(got["forbidden"], r"C:\NSC")
        self.assertEqual(got["canonical"], r"C:\NSC\NSC\NoSafeCircle")
        self.assertEqual(got["nscrev"], r"C:\nscrev")
        self.assertIn("NSC_RUN_JOB_FORBIDDEN_ROOT", got["ignored"])

    def test_overrides_apply_with_the_testing_flag(self):
        env = {
            "NSC_RUN_JOB_TESTING": "1",
            "NSC_RUN_JOB_FORBIDDEN_ROOT": str(self.fx.forbidden),
        }
        got = self._constants(env)
        self.assertTrue(got["testing"])
        self.assertEqual(got["forbidden"], str(self.fx.forbidden))
        self.assertEqual(got["ignored"], [])


class ReviewDryRunSideEffects(Base):
    def test_dry_run_creates_no_folders(self):
        brief = self.fx.make_brief("dry.prompt.md")
        out = self.fx.root / "not-created-yet"
        shutil.rmtree(self.fx.jobs, ignore_errors=True)
        proc = self.fx.run("host-lookup", "--brief", brief, "--out", out, "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertFalse(out.exists(), f"--dry-run created {out}")
        self.assertFalse(self.fx.jobs.exists(), "--dry-run recreated the jobs directory")

    def test_a_real_run_does_create_them(self):
        brief = self.fx.make_brief("wet.prompt.md")
        out = self.fx.root / "created-by-a-real-run"
        proc = self.fx.run("host-lookup", "--brief", brief, "--out", out,
                           "--skip-account-check")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertTrue(out.is_dir())


class ReviewOutGuard(Base):
    """`guard_out` refused an --out UNDER FORBIDDEN_ROOT but not one that is
    an ANCESTOR of it. `--out C:/` (also `C:/Users/..`, `//localhost/C$` and
    `//?/C:/`) passed and would mount C:\\NSC writable at /out/NSC.

    The ancestor-direction cases are checked directly against the real
    FORBIDDEN_ROOT module constant and its filesystem-identity spellings, the
    same way ReviewCloneGuardSpellings checks `is_under` and `guard_clone` -
    the bypass is about which way `is_under` is called, not anything the
    fixture's own fake forbidden root can exercise by itself.
    """

    def _ancestor_spellings(self):
        root = run_job.FORBIDDEN_ROOT
        if not root.is_dir():
            self.skipTest(f"{root} is not on this machine")
        drive = str(root)[0]
        return [
            Path(f"{drive}:\\"),
            Path(f"{drive}:/Users/.."),
            Path(f"\\\\localhost\\{drive}$"),
            Path(f"\\\\?\\{drive}:\\"),
        ]

    def test_an_ancestor_of_forbidden_root_is_refused(self):
        for spelling in self._ancestor_spellings():
            with self.subTest(spelling=spelling):
                with self.assertRaises(run_job.Refused) as caught:
                    run_job.guard_out(spelling, dry_run=True)
                self.assertIn("ancestor of", str(caught.exception))

    def test_a_descendant_of_forbidden_root_is_still_refused(self):
        root = run_job.FORBIDDEN_ROOT
        if not root.is_dir():
            self.skipTest(f"{root} is not on this machine")
        with self.assertRaises(run_job.Refused) as caught:
            run_job.guard_out(root / "somewhere", dry_run=True)
        self.assertIn("is inside", str(caught.exception))

    def test_the_reviewers_repro_is_refused_end_to_end(self):
        """`clone-edit --clone <ok> --out C:/ --dry-run` exited 0. Reproduced
        here through the CLI against the fixture's own FORBIDDEN_ROOT
        override, so nothing real is touched: --out set to the parent of the
        fake forbidden root is an ancestor of it."""
        brief = self.fx.make_brief("anc.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--out", self.fx.forbidden.parent, "--dry-run")
        self.assertRefused(proc, "ancestor of")

    def test_an_ordinary_out_under_the_sandbox_still_works(self):
        brief = self.fx.make_brief("out-ok.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--out", self.fx.root / "normal-out", "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


class ReviewJobName(Base):
    def test_a_traversal_name_is_refused(self):
        brief = self.fx.make_brief("trav.prompt.md")
        for name in ("..", ".", "..."):
            with self.subTest(name=name):
                proc = self.fx.run("host-lookup", "--brief", brief,
                                   "--name", name, "--dry-run")
                self.assertRefused(proc, "traversal")

    def test_an_ordinary_name_still_works(self):
        brief = self.fx.make_brief("ord.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           "--name", "a.good-name_1", "--dry-run")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


class ReviewBackgroundRefusals(Base):
    """A background job that was refused printed "started in background" and
    exited 0, leaving no json, no log and no telemetry row."""

    def test_the_account_guard_runs_before_anything_is_spawned(self):
        brief = self.fx.make_brief("bgacct.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--background",
                           "--name", "bgacct",
                           FAKE_CLAUDE_ACCOUNT="someone@outlook.com")
        self.assertRefused(proc, "someone@outlook.com")
        self.assertNotIn("started in background", proc.stdout)
        self.assertEqual(self.fx.telemetry(), [])

    def test_allow_account_and_host_reason_reach_the_child(self):
        import unittest.mock as mock

        # `out` points into the sandbox: spawn_background is called in-process,
        # where the module constants are the REAL ones, so leaving it None would
        # write a stray log into the live C:/nscrev/claude-jobs.
        class Args:
            type = "host-lookup"
            brief = "b.md"
            clone = model = agent = None
            out = str(self.fx.root / "fwd")
            name = "fwd"
            max_turns = timeout = None
            allow_bash: list = []
            allow_tool: list = []
            add_dir: list = []
            allow_account = "someone@outlook.com"
            host_reason = "because Vincent asked"

        with mock.patch.object(run_job.subprocess, "Popen") as popen:
            popen.return_value.pid = 4321
            run_job.spawn_background(Args())
        child = popen.call_args[0][0]
        self.assertIn("--allow-account", child)
        self.assertEqual(child[child.index("--allow-account") + 1], "someone@outlook.com")
        self.assertIn("--host-reason", child)
        self.assertEqual(child[child.index("--host-reason") + 1], "because Vincent asked")

    def test_the_child_stderr_is_kept_not_devnulled(self):
        import unittest.mock as mock

        class Args:
            type = "host-lookup"
            brief = "b.md"
            clone = model = agent = None
            out = str(self.fx.root / "bgerr")
            name = "bgerr"
            max_turns = timeout = None
            allow_bash: list = []
            allow_tool: list = []
            add_dir: list = []
            allow_account = host_reason = None

        with mock.patch.object(run_job.subprocess, "Popen") as popen:
            popen.return_value.pid = 99
            run_job.spawn_background(Args())
        stderr = popen.call_args[1]["stderr"]
        self.assertIsNot(stderr, run_job.subprocess.DEVNULL)
        self.assertTrue((Path(Args.out) / "background-stderr.log").is_file())


class ReviewAccountRefusalShape(Base):
    def test_the_account_guard_prints_refused_and_exits_2(self):
        """Every other guard exits 2 with REFUSED:. This one raised an uncaught
        traceback and exited 1, so a caller branching on the code could not
        tell a refusal from a crash."""
        brief = self.fx.make_brief("shape.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief,
                           FAKE_CLAUDE_ACCOUNT="someone@outlook.com")
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        self.assertIn("REFUSED:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class ReviewSubprocessStdin(Base):
    def test_preflight_calls_close_their_stdin(self):
        """With stdin on an open pipe a reviewer watched `auth status` block
        until the 300-second limit. A pre-flight check that can hang is one
        that gets skipped."""
        import unittest.mock as mock

        seen = []
        real = subprocess.run

        def spy(*args, **kwargs):
            seen.append(kwargs.get("stdin"))
            return real(*args, **kwargs)

        with mock.patch.object(run_job.subprocess, "run", spy):
            run_job.run_quiet([PYTHON, "-c", "pass"], capture_output=True, text=True)
        self.assertEqual(seen, [run_job.subprocess.DEVNULL])

    def test_a_caller_can_still_pipe_its_own_stdin(self):
        proc = run_job.run_quiet([PYTHON, "-c", "import sys;print(sys.stdin.read())"],
                                 input="hello", capture_output=True, text=True)
        self.assertIn("hello", proc.stdout)


class ReviewTelemetryAttribution(Base):
    def test_the_paying_account_is_recorded_even_when_usage_is_skipped(self):
        """Every --background child passes --skip-account-check, so the rows
        that most needed an owner were the ones recording account: null."""
        brief = self.fx.make_brief("attr.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--skip-account-check",
                           "--name", "attr")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        row = self.fx.telemetry()[0]
        self.assertEqual(row["account"], "cathode26@gmail.com")
        self.assertIn("account_source", row)

    def test_usage_percentages_say_which_account_they_describe(self):
        brief = self.fx.make_brief("attr2.prompt.md")
        proc = self.fx.run("host-lookup", "--brief", brief, "--name", "attr2")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        row = self.fx.telemetry()[0]
        self.assertIn("usage_account", row)
        if row.get("session_pct") is not None:
            self.assertIsNotNone(row["usage_account"])

if __name__ == "__main__":
    SCRATCH.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
