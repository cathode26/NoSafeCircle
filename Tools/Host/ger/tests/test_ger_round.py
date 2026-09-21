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
import review_result  # noqa: E402

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
        self._real_providers = (ger_round.run_codex, ger_round.run_claude)
        self.addCleanup(self._restore)

        self.round_dir = self.packet / ROUND

    def _restore(self):
        ger_round.CANONICAL = self._real_canonical
        ger_round.run_codex, ger_round.run_claude = self._real_providers

    def complete_prior(self, name: str, text: bytes = b"Prior round output.\n") -> bytes:
        """A prior round that finished: OUTPUT.md, METADATA.json, no FAILED.json."""
        prior = self.packet / name
        prior.mkdir(parents=True, exist_ok=True)
        (prior / "OUTPUT.md").write_bytes(text)
        (prior / "METADATA.json").write_text(
            json.dumps({"round": name, "exit_code": 0}), encoding="utf-8")
        return text

    def provider(self, *, exit_code=0, session_id="session-1", output=b"A review.",
                 is_error=None):
        """Install a fake provider. No process is started and nothing is paid for."""
        def fake(round_dir, snapshot, prompt, *rest):
            (round_dir / "RAW_EVENTS.jsonl").write_bytes(b'{"fixture": true}\n')
            (round_dir / "STDERR.log").write_bytes(b"")
            if output is not None:
                (round_dir / "OUTPUT.md").write_bytes(output)
            run = {"provider": "fixture", "cli": "fake", "cli_version": "fixture",
                   "command": ["fake"], "exit_code": exit_code,
                   "duration_seconds": 0.0, "session_id": session_id,
                   "model": "fixture-model", "raw_stdout": "RAW_EVENTS.jsonl"}
            if is_error is not None:
                run["is_error"] = is_error
            return run
        self.last_prompt: list[str] = []

        def capture(round_dir, snapshot, prompt, *rest):
            self.last_prompt.append(prompt)
            return fake(round_dir, snapshot, prompt, *rest)

        ger_round.run_codex = capture
        ger_round.run_claude = capture

    def run_round(self, name: str = ROUND) -> int:
        argv = ["ger_round.py", "--packet", str(self.packet),
                "--snapshot", str(self.snapshot), "--round", name,
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

    def test_a_non_decision_round_is_given_no_json_format(self):
        # Handing a drafting round a verdict format invites it to invent one.
        self.provider()
        self.assertEqual(self.run_round(), 0)
        prompt = self.last_prompt[-1]
        self.assertNotIn("FINAL MESSAGE (exactly one JSON object", prompt)
        self.assertNotIn("{DECISION_FORMAT}", prompt)
        self.assertNotIn("{REVIEWED_SHA256}", prompt)
        meta = json.loads((self.round_dir / "METADATA.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["protocol"], "none")
        self.assertEqual(meta["review_status"], "not-a-decision-round")

    def test_a_non_decision_round_keeps_its_output_verbatim(self):
        # Only decision rounds have their OUTPUT.md replaced by a rendered view.
        self.provider(output=b"A draft, written for people.\n")
        self.run_round()
        self.assertEqual((self.round_dir / "OUTPUT.md").read_bytes(),
                         b"A draft, written for people.\n")
        self.assertFalse((self.round_dir / "RESULT.json").exists())

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


DECISION = "04-claude-reaudit"
REVIEWED = "03-codex-refine"


class DecisionRounds(Base):
    """A decision round declares its verdict as JSON, or it has not finished."""

    def setUp(self):
        super().setUp()
        self.candidate = self.complete_prior(REVIEWED, b"The refined candidate.\n")
        for name in ("01-codex-generate", "02-claude-evaluate"):
            self.complete_prior(name)
        self.decision_dir = self.packet / DECISION

    def result(self, **overrides) -> bytes:
        body = {
            "schema_version": 1,
            "review_kind": "ger",
            "task_id": "NSC-001",
            "reviewed_artifact_kind": "ger_round_output",
            "reviewed_artifact_sha256": ger_round.sha256_bytes(self.candidate),
            "review_status": "complete",
            "recommendation": "commit_contract",
            "report_markdown": "1. Prior findings: all resolved.",
        }
        body.update(overrides)
        return json.dumps(body).encode("utf-8")

    def test_a_valid_decision_is_split_into_record_and_view(self):
        self.provider(output=self.result())
        self.assertEqual(self.run_round(DECISION), 0)

        # The record is the provider's bytes, verbatim.
        self.assertEqual((self.decision_dir / "RESULT.json").read_bytes(), self.result())

        # OUTPUT.md is the human view, and says so.
        view = (self.decision_dir / "OUTPUT.md").read_text(encoding="utf-8")
        self.assertIn("NOT a decision source", view)
        self.assertIn("1. Prior findings: all resolved.", view)
        self.assertIn("- Recommendation: commit_contract", view)

        meta = json.loads((self.decision_dir / "METADATA.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["protocol"], "json-v1")
        self.assertEqual(meta["review_status"], "complete")
        self.assertEqual(meta["recommendation"], "commit_contract")
        self.assertEqual(meta["result_sha256"], ger_round.sha256_bytes(self.result()))
        self.assertEqual(meta["reviewed"], f"{REVIEWED}/OUTPUT.md")
        # output_sha256 must describe what is ON DISK, which is now the view.
        self.assertEqual(
            meta["output_sha256"],
            ger_round.sha256_bytes((self.decision_dir / "OUTPUT.md").read_bytes()))
        self.assertNotEqual(meta["output_sha256"], meta["result_sha256"])

    def test_prose_instead_of_json_is_not_a_finished_round(self):
        self.provider(output=b"Final recommendation: commit_contract\n")
        with self.assertRaises(SystemExit):
            self.run_round(DECISION)
        self.assertFalse((self.decision_dir / "METADATA.json").exists())
        self.assertFalse((self.decision_dir / "RESULT.json").exists())
        body = json.loads((self.decision_dir / "FAILED.json").read_text(encoding="utf-8"))
        self.assertIn("did not declare a readable decision", body["reason"])

    def test_a_review_of_different_bytes_is_refused(self):
        self.provider(output=self.result(reviewed_artifact_sha256="c" * 64))
        with self.assertRaises(SystemExit):
            self.run_round(DECISION)
        self.assertFalse((self.decision_dir / "METADATA.json").exists())
        body = json.loads((self.decision_dir / "FAILED.json").read_text(encoding="utf-8"))
        self.assertIn("artifact_hash_mismatch", body["reason"])

    def test_a_closure_verdict_is_not_a_ger_verdict(self):
        # "Do not translate revise into needs_design" - the families stay apart.
        self.provider(output=self.result(recommendation="revise"))
        with self.assertRaises(SystemExit):
            self.run_round(DECISION)
        body = json.loads((self.decision_dir / "FAILED.json").read_text(encoding="utf-8"))
        self.assertIn("wrong_family_recommendation", body["reason"])

    def test_a_declared_incomplete_does_not_publish_a_decision(self):
        self.provider(output=self.result(review_status="incomplete", recommendation=None,
                                         report_markdown="Context ran out."))
        self.assertEqual(self.run_round(DECISION), 0)
        meta = json.loads((self.decision_dir / "METADATA.json").read_text(encoding="utf-8"))
        # The ROUND ran and recorded itself honestly; the DECISION is absent.
        self.assertEqual(meta["review_status"], "incomplete")
        self.assertIsNone(meta["recommendation"])

    def test_the_prompt_carries_the_format_and_the_real_hash(self):
        self.provider(output=self.result())
        self.run_round(DECISION)
        prompt = self.last_prompt[-1]
        self.assertIn("FINAL MESSAGE (exactly one JSON object", prompt)
        self.assertIn(ger_round.sha256_bytes(self.candidate), prompt,
                      "the prompt must give the reviewer the exact hash to copy")
        self.assertNotIn("{REVIEWED_SHA256}", prompt)
        self.assertNotIn("{DECISION_FORMAT}", prompt)
        self.assertIn('"task_id": "NSC-001"', prompt)

class ReadDecision(DecisionRounds):
    """The one interpretation every consumer goes through."""

    def completed(self, **overrides):
        self.provider(output=self.result(**overrides))
        self.assertEqual(self.run_round(DECISION), 0)

    def read(self):
        return ger_round.read_decision(self.packet, DECISION, "NSC-001")

    def test_it_returns_the_declared_decision(self):
        self.completed()
        self.assertEqual(self.read().recommendation, "commit_contract")

    def test_narrative_naming_other_verdicts_does_not_change_it(self):
        # The old reader grepped OUTPUT.md for the earliest verdict word, so a
        # re-audit merely discussing needs_design in its reasoning outranked its
        # own verdict. Here the prose is inside a string.
        self.completed(recommendation="commit_contract",
                       report_markdown="I considered needs_design and "
                                       "blocked_not_design before deciding.")
        self.assertEqual(self.read().recommendation, "commit_contract")

    def test_editing_the_reviewed_artifact_invalidates_the_decision(self):
        # The point of re-validating instead of trusting METADATA: a decision is
        # about specific bytes, and those bytes can change underneath it.
        self.completed()
        self.assertEqual(self.read().recommendation, "commit_contract")
        (self.packet / REVIEWED / "OUTPUT.md").write_bytes(b"A DIFFERENT candidate.\n")
        with self.assertRaises(review_result.ReviewResultError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "artifact_hash_mismatch")

    def strip_protocol(self):
        """Make a completed round look like a pre-cutover one."""
        (self.packet / DECISION / ger_round.RESULT_FILE).unlink()
        meta_path = self.packet / DECISION / "METADATA.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for key in ("protocol", "result_sha256", "result_file", "review_status",
                    "recommendation"):
            meta.pop(key, None)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    def test_a_legacy_packet_is_distinguishable_from_a_broken_one(self):
        # Legacy may use the old path; invalid v2 may not. One exception type for
        # both would erase that line.
        self.completed()
        self.strip_protocol()
        with self.assertRaises(ger_round.LegacyPacket):
            ger_round.read_decision(self.packet, DECISION, "NSC-001",
                                    allow_legacy=True)

    def test_legacy_is_the_callers_choice_not_an_inference(self):
        # Astra MJ-P2-02. Without the caller saying so, a packet that merely
        # declares no protocol is refused rather than read as Markdown.
        self.completed()
        self.strip_protocol()
        with self.assertRaises(ValueError) as caught:
            self.read()
        self.assertNotIsInstance(caught.exception, ger_round.LegacyPacket)
        self.assertIn("declares no protocol", str(caught.exception))

    def test_a_declared_json_round_with_no_result_is_broken_not_legacy(self):
        # The exact shape Astra reproduced: move ONE file aside and the verdict
        # used to revert to a grep of the derived view.
        self.completed()
        (self.packet / DECISION / ger_round.RESULT_FILE).unlink()
        for allow in (False, True):
            with self.subTest(allow_legacy=allow):
                with self.assertRaises(ValueError) as caught:
                    ger_round.read_decision(self.packet, DECISION, "NSC-001",
                                            allow_legacy=allow)
                self.assertNotIsInstance(caught.exception, ger_round.LegacyPacket)

    def test_an_unknown_protocol_is_refused(self):
        self.completed()
        meta_path = self.packet / DECISION / "METADATA.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["protocol"] = "json-v9"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            self.read()
        self.assertIn("json-v9", str(caught.exception))

    def test_a_v2_packet_with_unreadable_result_is_not_legacy(self):
        self.completed()
        (self.packet / DECISION / ger_round.RESULT_FILE).write_bytes(b"not json")
        # Refused as a TAMPERED record, not as bad JSON: the recorded hash no
        # longer matches the bytes, and that check runs before the parse. Either
        # way it is a ValueError-or-worse, never a LegacyPacket.
        with self.assertRaises((ValueError, review_result.ReviewResultError)) as caught:
            self.read()
        self.assertNotIsInstance(caught.exception, ger_round.LegacyPacket)

    def test_a_tampered_result_is_refused(self):
        # Astra MJ-P2-03: edit the verdict, leave the recorded hash stale.
        self.completed(recommendation="needs_design")
        path = self.packet / DECISION / ger_round.RESULT_FILE
        body = json.loads(path.read_text(encoding="utf-8"))
        body["recommendation"] = "commit_contract"
        path.write_bytes(json.dumps(body).encode("utf-8"))
        with self.assertRaises(ValueError) as caught:
            self.read()
        self.assertIn("edited since", str(caught.exception))

    def test_a_record_of_provider_failure_is_refused(self):
        self.completed()
        meta_path = self.packet / DECISION / "METADATA.json"
        for weakened in ({"exit_code": 9}, {"is_error": True}, {"session_id": None}):
            with self.subTest(weakened=weakened):
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta.update(weakened)
                meta_path.write_text(json.dumps(meta), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.read()

    def test_a_failed_round_carries_no_decision(self):
        self.provider(exit_code=1, output=self.result())
        with self.assertRaises(SystemExit):
            self.run_round(DECISION)
        with self.assertRaises(ValueError):
            self.read()

    def test_an_unfinished_round_carries_no_decision(self):
        (self.packet / DECISION).mkdir()
        with self.assertRaises(ValueError):
            self.read()

    def test_a_non_decision_round_is_refused(self):
        with self.assertRaises(ValueError):
            ger_round.read_decision(self.packet, ROUND, "NSC-001")

    def test_the_wrong_task_is_refused(self):
        self.completed()
        with self.assertRaises(review_result.ReviewResultError) as caught:
            ger_round.read_decision(self.packet, DECISION, "NSC-999")
        self.assertEqual(caught.exception.code, "task_mismatch")


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
