#!/usr/bin/env python
"""Tests for ger_round's completion record. The first tests this directory has had.

Run:
    python -B test_ger_round.py

The property under test is an ORDERING, and it is the one Astra flagged CRITICAL
in the minimal-JSON handoff: METADATA.json is the file `build_prompt` reads to
decide that a prior round completed, so it must not exist until the round has
passed its checks.

Before this change `main` wrote METADATA.json and only then looked at the exit
code, `is_error`, OUTPUT.md and the session id. `fail()` did also write
FAILED.json, and `build_prompt` does check for it, so the common failure was
caught - but anything that threw between the two writes published a completed
record with no failure marker beside it. `output.read_text(encoding="utf-8")` was
one such path: a provider writing bytes that are not UTF-8 raised out of `main`
with METADATA.json already on disk.

`test_non_utf8_output_is_a_problem_not_a_crash` is that exact case, and
`test_*_does_not_publish_metadata` are the general ordering.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ger_round  # noqa: E402

ROUND = "01-codex-generate"          # no prior rounds, so the fixture stays small
CONTEXT = "planning"                 # the smallest context preset

TASK = b"id: NSC-001\nname: fixture\n"
GDD = b"# GDD fixture\n"
ART = b"# Art direction fixture\n"

FILES = {
    "Tasks/NSC-001.yaml": TASK,
    "Docs/GDD/No_Safe_Circle_GDD.md": GDD,
    "Docs/Art/Environment/DUNGEON_ART_DIRECTION.md": ART,
}


def write(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {result.stderr}")
    return result.stdout.strip()


class Base(unittest.TestCase):
    """A temp canonical repo, a matching snapshot, and a packet that names both."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)

        self.repo = tmp / "canonical"
        self.repo.mkdir()
        for rel, data in FILES.items():
            write(self.repo, rel, data)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "fixture")
        git(self.repo, "config", "user.email", "fixture@nosafecircle.invalid")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "fixture")
        head = git(self.repo, "rev-parse", "HEAD")

        self.snapshot = tmp / "snap"
        self.snapshot.mkdir()
        for rel, data in FILES.items():
            write(self.snapshot, rel, data)
        (tmp / "snap.SNAPSHOT_IDENTITY.json").write_text(
            json.dumps({"source_head": head}), encoding="utf-8")

        self.packet = tmp / "packet"
        self.packet.mkdir()
        (self.packet / "GER_PACKET.md").write_text("# packet fixture\n", encoding="utf-8")
        (self.packet / "SOURCE_IDENTITY.json").write_text(json.dumps({
            "task_id": "NSC-001",
            "contract_revision": 1,
            "source_head": head,
            "task_sha256": ger_round.sha256_bytes(TASK),
            "gdd_sha256": ger_round.sha256_bytes(GDD),
            "art_direction_sha256": ger_round.sha256_bytes(ART),
        }), encoding="utf-8")

        # git_bytes shells out to `git -C CANONICAL`, so pointing CANONICAL at the
        # fixture repo is enough; nothing here touches the real checkout.
        self._real_canonical = ger_round.CANONICAL
        ger_round.CANONICAL = self.repo
        self._real_run_codex = ger_round.run_codex
        self.addCleanup(self._restore)

        self.round_dir = self.packet / ROUND

    def _restore(self):
        ger_round.CANONICAL = self._real_canonical
        ger_round.run_codex = self._real_run_codex

    def provider(self, *, exit_code=0, session_id="session-1", output=b"A review.",
                 is_error=None):
        """Install a fake provider. No process is started and nothing is paid for."""
        def fake(round_dir, snapshot, prompt, images, timeout):
            (round_dir / "RAW_EVENTS.jsonl").write_bytes(b'{"fixture": true}\n')
            (round_dir / "STDERR.log").write_bytes(b"")
            if output is not None:
                (round_dir / "OUTPUT.md").write_bytes(output)
            run = {"provider": "codex", "cli": "fake", "cli_version": "fixture",
                   "command": ["fake"], "exit_code": exit_code,
                   "duration_seconds": 0.0, "session_id": session_id,
                   "model": "fixture-model", "raw_stdout": "RAW_EVENTS.jsonl"}
            if is_error is not None:
                run["is_error"] = is_error
            return run
        ger_round.run_codex = fake

    def run_round(self) -> int:
        argv = ["ger_round.py", "--packet", str(self.packet),
                "--snapshot", str(self.snapshot), "--round", ROUND,
                "--context", CONTEXT]
        real_argv, sys.argv = sys.argv, argv
        try:
            return ger_round.main()
        finally:
            sys.argv = real_argv

    # -- assertions the ordering tests share ------------------------------------

    def assertNotPublished(self, reason_fragment: str):
        """The round failed: no completed record, a failure marker, evidence kept."""
        metadata = self.round_dir / "METADATA.json"
        failed = self.round_dir / "FAILED.json"
        self.assertFalse(metadata.exists(),
                         "METADATA.json was published for a round that failed its "
                         "checks; build_prompt reads that file as proof a prior "
                         "round completed")
        self.assertTrue(failed.is_file(), "no FAILED.json was written")
        body = json.loads(failed.read_text(encoding="utf-8"))
        self.assertIn(reason_fragment, body["reason"])
        # The evidence must survive the failure, just not under an actionable name.
        self.assertIn("metadata", body,
                      "the failure record dropped the metadata, losing the hashes "
                      "and provider evidence for the failed attempt")
        self.assertTrue((self.round_dir / "RAW_EVENTS.jsonl").is_file())
        self.assertTrue((self.round_dir / "PROMPT.md").is_file())

    def assertNoTempFiles(self):
        strays = [p.name for p in self.round_dir.iterdir()
                  if p.name.startswith(".METADATA")]
        self.assertEqual(strays, [], f"temporary publication files left behind: {strays}")


class TheHappyPath(Base):
    def test_a_clean_round_publishes_metadata(self):
        self.provider()
        self.assertEqual(self.run_round(), 0)
        metadata = json.loads((self.round_dir / "METADATA.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["task_id"], "NSC-001")
        self.assertEqual(metadata["exit_code"], 0)
        self.assertEqual(metadata["session_id"], "session-1")
        self.assertFalse((self.round_dir / "FAILED.json").exists())
        self.assertNoTempFiles()

    def test_the_round_directory_is_reserved(self):
        # Unchanged behaviour, asserted so the fix cannot quietly remove it.
        self.provider()
        self.assertEqual(self.run_round(), 0)
        with self.assertRaises(SystemExit):
            self.run_round()


class FailureDoesNotPublish(Base):
    """MJ-06: failure before or during publication leaves nothing actionable."""

    def failing(self, **kwargs):
        self.provider(**kwargs)
        with self.assertRaises(SystemExit) as caught:
            self.run_round()
        self.assertEqual(caught.exception.code, 2)

    def test_a_nonzero_exit_does_not_publish_metadata(self):
        self.failing(exit_code=1)
        self.assertNotPublished("exit code 1")
        self.assertNoTempFiles()

    def test_is_error_does_not_publish_metadata(self):
        self.failing(is_error=True)
        self.assertNotPublished("is_error")

    def test_a_missing_output_does_not_publish_metadata(self):
        self.failing(output=None)
        self.assertNotPublished("missing OUTPUT.md")

    def test_an_empty_output_does_not_publish_metadata(self):
        self.failing(output=b"   \n\t\n")
        self.assertNotPublished("empty OUTPUT.md")

    def test_a_missing_session_does_not_publish_metadata(self):
        self.failing(session_id=None)
        self.assertNotPublished("missing session identity")

    def test_non_utf8_output_is_a_problem_not_a_crash(self):
        # The unguarded read: this used to raise UnicodeDecodeError out of main,
        # with METADATA.json already written and no FAILED.json beside it.
        self.failing(output=b"\xff\xfe not text")
        self.assertNotPublished("unreadable OUTPUT.md")

    def test_several_problems_are_all_reported(self):
        self.failing(exit_code=3, session_id=None, output=None)
        body = json.loads((self.round_dir / "FAILED.json").read_text(encoding="utf-8"))
        for fragment in ("exit code 3", "missing OUTPUT.md", "missing session identity"):
            self.assertIn(fragment, body["reason"])


class CheckRun(unittest.TestCase):
    """The checks in isolation, so each reason is provably reachable."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output = Path(self._tmp.name) / "OUTPUT.md"
        self.output.write_text("A review.", encoding="utf-8")
        self.run = {"exit_code": 0, "session_id": "s", "raw_stdout": "RAW_EVENTS.jsonl"}

    def test_a_clean_run_has_no_problems(self):
        self.assertEqual(ger_round.check_run(self.run, self.output), [])

    def test_each_problem_is_reachable(self):
        cases = [
            ({"exit_code": 9}, "exit code 9"),
            ({"is_error": True}, "provider reported is_error"),
            ({"session_id": None}, "missing session identity"),
            ({"session_id": ""}, "missing session identity"),
        ]
        for patch, fragment in cases:
            with self.subTest(patch=patch):
                problems = ger_round.check_run({**self.run, **patch}, self.output)
                self.assertTrue(any(fragment in p for p in problems),
                                f"{fragment!r} not in {problems}")

    def test_a_directory_where_output_should_be_is_unreadable_not_a_crash(self):
        target = Path(self._tmp.name) / "as_dir"
        target.mkdir()
        problems = ger_round.check_run(self.run, target)
        self.assertTrue(problems, "a directory in OUTPUT.md's place must be a problem")


class PublishMetadata(unittest.TestCase):
    """Publication is one atomic step, or it has not happened."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_it_writes_the_record(self):
        ger_round.publish_metadata(self.dir, {"round": "01", "n": 1})
        body = json.loads((self.dir / "METADATA.json").read_text(encoding="utf-8"))
        self.assertEqual(body, {"round": "01", "n": 1})

    def test_it_leaves_no_temporary_file(self):
        ger_round.publish_metadata(self.dir, {"a": 1})
        self.assertEqual([p.name for p in self.dir.iterdir()], ["METADATA.json"])

    def test_the_temporary_name_is_not_the_published_name(self):
        # A reader globbing for METADATA.json must never match the in-progress
        # file, which is the whole reason for the rename.
        seen = {}
        real_replace = ger_round.os.replace

        def spy(src, dst):
            seen["src"] = Path(src).name
            seen["dst"] = Path(dst).name
            return real_replace(src, dst)

        ger_round.os.replace = spy
        try:
            ger_round.publish_metadata(self.dir, {"a": 1})
        finally:
            ger_round.os.replace = real_replace
        self.assertEqual(seen["dst"], "METADATA.json")
        self.assertNotEqual(seen["src"], "METADATA.json")

    def test_it_replaces_an_existing_record(self):
        (self.dir / "METADATA.json").write_text("stale", encoding="utf-8")
        ger_round.publish_metadata(self.dir, {"fresh": True})
        body = json.loads((self.dir / "METADATA.json").read_text(encoding="utf-8"))
        self.assertEqual(body, {"fresh": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
