#!/usr/bin/env python
"""Tests for apply_contract's decision reading.

Run:
    python -B test_apply_contract.py

Two readers live here and both used to infer a verdict from prose:

  - `round_decision` replaces three `final_recommendation(OUTPUT.md)` call sites
    for rounds 04, 06 and 08. Those files are derived views under the protocol.
  - `resolve_post_commit_check` read a closure report's own
    "Final recommendation:" line and never checked what the report was ABOUT.
    It now binds to the exact Git blob `Tasks/<task>.yaml` at the checked commit,
    which is also why the commit is resolved before the verdict is read.

The legacy path is reached only by an explicit `legacy=True`. It is never
inferred from the bytes: a v2 result that fails to validate is refused, because
sniffing the format is how "never retry a failed new parse through the old
reader" gets quietly lost.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import apply_contract as ac  # noqa: E402
import ger_fixtures as fixtures  # noqa: E402
import ger_round  # noqa: E402
import review_result  # noqa: E402

TASK = "NSC-001"
REAUDIT = "04-claude-reaudit"
REVIEWED = "03-codex-refine"
CANDIDATE = b"The refined candidate.\n"

CONTRACT_V1 = b'{"id": "NSC-001", "contract_revision": 1}\n'
CONTRACT_V2 = b'{"id": "NSC-001", "contract_revision": 2}\n'

LEGACY_CLOSURE_REPORT = (
    "Ledger:\n- L1: RESOLVED.\n\nFinal recommendation: commit_contract\n")


class Refused(Exception):
    """What the `error` callback raises; it must never return."""


def refuse(message: str):
    raise Refused(message)


class PacketBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.packet = Path(self._tmp.name) / "packet"
        (self.packet / REVIEWED).mkdir(parents=True)
        (self.packet / REVIEWED / "OUTPUT.md").write_bytes(CANDIDATE)
        (self.packet / REAUDIT).mkdir(parents=True)

    def v2(self, **overrides):
        """A realistic record, not a stub: hashes and provider evidence included."""
        return fixtures.decision(self.packet, fixtures.result_bytes(**overrides))

    def legacy(self, text: str):
        fixtures.legacy(self.packet, text)


class RoundDecision(PacketBase):
    def test_a_v2_packet_reads_its_declaration(self):
        self.v2()
        self.assertEqual(ac.round_decision(self.packet, REAUDIT, TASK),
                         "commit_contract")

    def test_reasoning_naming_other_verdicts_does_not_win(self):
        self.v2(report_markdown="I weighed needs_design at length.")
        self.assertEqual(ac.round_decision(self.packet, REAUDIT, TASK),
                         "commit_contract")

    def test_a_legacy_packet_reads_when_the_caller_says_so(self):
        self.legacy("Final recommendation: commit_contract_then_decompose\n")
        self.assertEqual(
            ac.round_decision(self.packet, REAUDIT, TASK, allow_legacy=True),
            "commit_contract_then_decompose")

    def test_a_legacy_packet_is_refused_by_default(self):
        self.legacy("Final recommendation: commit_contract\n")
        self.assertIsNone(ac.round_decision(self.packet, REAUDIT, TASK))

    def test_a_tampered_record_is_refused(self):
        raw = self.v2(recommendation="needs_design")
        body = json.loads(raw.decode("utf-8"))
        body["recommendation"] = "commit_contract"
        (self.packet / REAUDIT / ger_round.RESULT_FILE).write_bytes(
            json.dumps(body).encode("utf-8"))
        self.assertIsNone(ac.round_decision(self.packet, REAUDIT, TASK))

    def test_a_round_that_recorded_provider_failure_is_refused(self):
        fixtures.decision(self.packet, exit_code=9)
        self.assertIsNone(ac.round_decision(self.packet, REAUDIT, TASK))

    def test_an_invalid_v2_packet_does_not_fall_through(self):
        self.v2()
        (self.packet / REAUDIT / ger_round.RESULT_FILE).write_bytes(b"not json")
        (self.packet / REAUDIT / "OUTPUT.md").write_text(
            "Final recommendation: commit_contract\n", encoding="utf-8")
        self.assertIsNone(ac.round_decision(self.packet, REAUDIT, TASK))

    def test_the_legacy_grep_would_have_accepted_that(self):
        # Otherwise the test above proves nothing about fallthrough.
        self.assertEqual(
            ac.final_recommendation("Final recommendation: commit_contract\n"),
            "commit_contract")

    def test_edited_reviewed_bytes_invalidate_the_decision(self):
        self.v2()
        (self.packet / REVIEWED / "OUTPUT.md").write_bytes(b"edited.\n")
        self.assertIsNone(ac.round_decision(self.packet, REAUDIT, TASK))

    def test_final_recommendation_delegates_to_the_one_grep(self):
        # It used to be a second copy of ger_node's implementation, and the two
        # could drift. Asserted over inputs that would expose a divergence: the
        # order rule, a verdict absent, and a derived view.
        import ger_node

        for text in ("Final recommendation: revise\n",
                     "Final recommendation: needs_design, though commit_contract "
                     "may follow later\n",
                     "no verdict at all\n",
                     review_result.DERIVED_VIEW_HEADER + "\nFinal recommendation: "
                     "commit_contract\n"):
            with self.subTest(text=text[:40]):
                self.assertEqual(ac.final_recommendation(text),
                                 ger_round.legacy_round_recommendation(text))

    def test_the_order_rule_survived_the_move(self):
        # "The earliest option named after the heading wins": a needs_design
        # verdict that goes on to mention commit_contract stays needs_design.
        self.assertEqual(
            ac.final_recommendation("Final recommendation: needs_design; a later "
                                    "re-audit could reach commit_contract\n"),
            "needs_design")


class OverridesAfterReview(PacketBase):
    """Astra MJ-P2-07: an approval is about specific bytes, or it is about nothing."""

    PROPOSED = {"id": TASK, "contract_revision": 2, "acceptance": "as reviewed"}

    def test_a_substantive_override_after_a_json_review_is_refused(self):
        self.v2()
        with self.assertRaises(SystemExit) as caught:
            ac.review_override(self.packet, dict(self.PROPOSED),
                               {"acceptance": "something else"}, None)
        self.assertIn("acceptance", str(caught.exception))
        self.assertIn("must not present changed content", str(caught.exception))

    def test_a_no_op_override_is_not_substantive(self):
        self.v2()
        self.assertIsNone(ac.review_override(
            self.packet, dict(self.PROPOSED), {"acceptance": "as reviewed"}, None))

    def test_a_human_exception_is_allowed_and_recorded(self):
        self.v2()
        record = ac.review_override(self.packet, dict(self.PROPOSED),
                                    {"acceptance": "something else"},
                                    "Vincent accepted this wording directly")
        self.assertEqual(record["keys"], ["acceptance"])
        self.assertEqual(record["human_exception"],
                         "Vincent accepted this wording directly")

    def test_a_historical_review_is_unaffected(self):
        # Those reviews were never bound to anything, so there is no binding for
        # an override to contradict, and refusing here would break the old flow.
        self.legacy("Final recommendation: commit_contract\n")
        self.assertIsNone(ac.review_override(
            self.packet, dict(self.PROPOSED), {"acceptance": "something else"}, None))

    def test_a_change_python_equality_calls_equal_is_still_a_change(self):
        # Astra MJ-P2-07, second half. `proposed.get(key) != value` classified
        # three real changes as no-ops: `.get` returns None for an absent key, so
        # adding one whose value is null looked unchanged; and `True == 1` in
        # Python, so 1 -> true looked unchanged, nested inside a dict too. Each
        # produced a changed contract with no provenance record of the override.
        self.v2()
        cases = [
            ("an absent key set to null", {"notes": None}),
            ("an int changed to a bool", {"contract_revision": True}),
            ("the same change nested in a dict", {"gates": {"unity": True}}),
        ]
        proposed = dict(self.PROPOSED, contract_revision=1, gates={"unity": 1})
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(SystemExit):
                    ac.review_override(self.packet, dict(proposed), override, None)

    def test_a_genuinely_unchanged_override_is_still_a_no_op(self):
        # The guard must not become "refuse every override".
        self.v2()
        proposed = dict(self.PROPOSED, gates={"unity": 1}, notes=None)
        self.assertIsNone(ac.review_override(
            self.packet, dict(proposed),
            {"gates": {"unity": 1}, "notes": None, "acceptance": "as reviewed"}, None))

    def test_key_order_inside_a_value_is_not_a_change(self):
        self.v2()
        proposed = dict(self.PROPOSED, gates={"a": 1, "b": 2})
        self.assertIsNone(ac.review_override(
            self.packet, dict(proposed), {"gates": {"b": 2, "a": 1}}, None))

    def test_every_changed_key_is_named(self):
        self.v2()
        with self.assertRaises(SystemExit) as caught:
            ac.review_override(self.packet, dict(self.PROPOSED),
                               {"acceptance": "x", "contract_revision": 9}, None)
        self.assertIn("acceptance", str(caught.exception))
        self.assertIn("contract_revision", str(caught.exception))


class TheRecheckVerifiers(PacketBase):
    """MJ-P2-10: the two functions my NameError hid in, exercised end to end.

    I tested `round_decision` in isolation and never called the verifiers that
    use it, so `allow_legacy=args.legacy_rounds` inside functions with no `args`
    raised NameError on both otherwise-valid paths. These drive each verifier
    with records that reach and pass the decision read.
    """

    PATCHED = b'{"id": "NSC-001", "contract_revision": 2}\n'
    REVISED = b'{"id": "NSC-001", "contract_revision": 2}\n'

    def plain_round(self, name: str, text: bytes, **metadata) -> bytes:
        directory = self.packet / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "OUTPUT.md").write_bytes(text)
        (directory / "METADATA.json").write_text(
            json.dumps({"round": name, "output_sha256": ac.sha256(text), **metadata}),
            encoding="utf-8")
        return text

    def test_the_owner_patch_verifier_reads_a_json_recheck(self):
        hashes = {"03-codex-refine": ac.sha256(CANDIDATE)}
        reaudit = self.plain_round("04-claude-reaudit", b"re-audit output\n")
        hashes["04-claude-reaudit"] = ac.sha256(reaudit)

        patch_out = b"owner patch output\n"
        self.plain_round("05-owner-patch", patch_out,
                         patched_contract_sha256=ac.sha256(self.PATCHED),
                         input_sha256={"03-codex-refine/OUTPUT.md": hashes["03-codex-refine"],
                                       "04-claude-reaudit/OUTPUT.md": hashes["04-claude-reaudit"]})
        (self.packet / "05-owner-patch" / "PATCHED_CONTRACT.json").write_bytes(self.PATCHED)

        fixtures.decision(
            self.packet,
            fixtures.result_bytes(artifact=patch_out, recommendation="commit_contract"),
            round_name="06-claude-recheck",
            input_sha256={"05-owner-patch/OUTPUT.md": ac.sha256(patch_out)})

        record = ac.verify_owner_patch_and_recheck(
            self.packet, hashes, "blocked_not_design", TASK)
        self.assertEqual(record["recheck_recommendation"], "commit_contract")

    def test_the_decision_revision_verifier_reads_a_json_recheck(self):
        hashes = {"03-codex-refine": ac.sha256(CANDIDATE)}
        reaudit = self.plain_round("04-claude-reaudit", b"re-audit output\n")
        hashes["04-claude-reaudit"] = ac.sha256(reaudit)

        build_out = b"decision revision output\n"
        self.plain_round("07-owner-decision-revision", build_out,
                         revised_contract_sha256=ac.sha256(self.REVISED),
                         input_sha256={"03-codex-refine/OUTPUT.md": hashes["03-codex-refine"],
                                       "04-claude-reaudit/OUTPUT.md": hashes["04-claude-reaudit"]})
        (self.packet / "07-owner-decision-revision" / "REVISED_CONTRACT.json").write_bytes(
            self.REVISED)

        fixtures.decision(
            self.packet,
            fixtures.result_bytes(artifact=self.REVISED,
                                  recommendation="commit_contract_then_decompose"),
            round_name="08-claude-recheck",
            provider_evidence="imported",
            imported_from="the GER owner's reviewer report",
            exit_code=None, session_id=None,
            input_sha256={
                "07-owner-decision-revision/OUTPUT.md": ac.sha256(build_out),
                "07-owner-decision-revision/REVISED_CONTRACT.json": ac.sha256(self.REVISED)})

        record = ac.verify_decision_revision_and_recheck(self.packet, hashes, TASK)
        self.assertEqual(record["recheck_recommendation"],
                         "commit_contract_then_decompose")

    def test_neither_verifier_references_a_module_global_args(self):
        # The shape of the defect, not just the instance: any `args.` outside
        # main() is a NameError waiting for the path that reaches it.
        import ast

        tree = ast.parse(Path(ac.__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name == "main":
                continue
            spec = node.args
            names = {a.arg for a in spec.args} | {a.arg for a in spec.kwonlyargs}
            # *args and **kwargs bind the name too - `def git(*args)` is fine.
            for extra in (spec.vararg, spec.kwarg):
                if extra is not None:
                    names.add(extra.arg)
            if "args" in names:
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name) and inner.id == "args":
                    offenders.append(f"{node.name}:{inner.lineno}")
        self.assertEqual(offenders, [],
                         "these functions read `args` without receiving it")


class PostCommitCheck(unittest.TestCase):
    """The closure report filed against a commit that changed the contract."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = self.tmp / "repo"
        (self.repo / "Tasks").mkdir(parents=True)

        def git(*args):
            result = subprocess.run(["git", "-C", str(self.repo), *args],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                raise AssertionError(f"git {' '.join(args)}: {result.stderr}")
            return result.stdout.strip()

        (self.repo / "Tasks" / f"{TASK}.yaml").write_bytes(CONTRACT_V1)
        git("init", "-q")
        git("config", "user.name", "fixture")
        git("config", "user.email", "fixture@nosafecircle.invalid")
        git("add", "-A")
        git("commit", "-q", "-m", "first")
        (self.repo / "Tasks" / f"{TASK}.yaml").write_bytes(CONTRACT_V2)
        git("add", "-A")
        git("commit", "-q", "-m", "revision 2")
        self.checked = git("rev-parse", "HEAD")
        # The blob as GIT stores it, which is what the reviewer is shown.
        self.blob = subprocess.run(
            ["git", "-C", str(self.repo), "show", f"{self.checked}:Tasks/{TASK}.yaml"],
            capture_output=True).stdout

        self._real_repo = ac.REPO
        ac.REPO = self.repo
        self.addCleanup(lambda: setattr(ac, "REPO", self._real_repo))

    def report(self, raw: bytes, *, job_record: dict | None = ...) -> Path:
        """The report, and by default the job record proving its job succeeded."""
        path = self.tmp / "check.report.md"
        path.write_bytes(raw)
        ready = path.with_suffix(path.suffix + ".metadata.json")
        if job_record is ...:
            job_record = {"protocol": "json-v1", "result_sha256": ac.sha256(raw),
                          "exit_code": 0, "is_error": None}
        if job_record is None:
            if ready.exists():
                ready.unlink()
        else:
            ready.write_text(json.dumps(job_record), encoding="utf-8")
        return path

    def result(self, **overrides) -> bytes:
        body = {
            "schema_version": 1,
            "review_kind": "closure",
            "task_id": TASK,
            "reviewed_artifact_kind": "contract",
            "reviewed_artifact_sha256": ac.sha256(self.blob),
            "review_status": "complete",
            "recommendation": "commit_contract",
            "report_markdown": "Checked after the commit.",
        }
        body.update(overrides)
        return json.dumps(body).encode("utf-8")

    def resolve(self, raw: bytes, *, job_record=..., **kwargs):
        return ac.resolve_post_commit_check(
            self.report(raw, job_record=job_record), self.checked, TASK, refuse, **kwargs)

    def test_a_bound_result_is_accepted(self):
        record = self.resolve(self.result())
        self.assertEqual(record["verdict"], "commit_contract")
        self.assertEqual(record["protocol"], "json-v1")
        self.assertEqual(record["checked_commit"], self.checked)
        self.assertEqual(record["reviewed_artifact_sha256"], ac.sha256(self.blob))
        self.assertEqual(record["provider_evidence"], "generated")

    def test_a_report_with_no_job_record_is_refused(self):
        # Astra MJ-P3-03: this used to be accepted and stamped `imported`, so a
        # result whose own job FAILED acquired provenance it had not earned.
        with self.assertRaises(Refused) as caught:
            self.resolve(self.result(), job_record=None)
        self.assertIn("no job record beside it", str(caught.exception))

    def test_a_record_of_a_failed_job_is_refused(self):
        # The exact boundary: check_job_result rejects rc=9, and this must too.
        for failed in ({"exit_code": 9, "is_error": None},
                       {"exit_code": 0, "is_error": True}):
            with self.subTest(failed=failed):
                raw = self.result()
                record = {"protocol": "json-v1", "result_sha256": ac.sha256(raw), **failed}
                with self.assertRaises(Refused) as caught:
                    self.resolve(raw, job_record=record)
                self.assertIn("failed job", str(caught.exception))

    def test_a_record_for_different_bytes_is_refused(self):
        raw = self.result()
        record = {"protocol": "json-v1", "result_sha256": "f" * 64,
                  "exit_code": 0, "is_error": None}
        with self.assertRaises(Refused) as caught:
            self.resolve(raw, job_record=record)
        self.assertIn("recorded result hash", str(caught.exception))

    def test_a_hand_carried_review_is_declared_not_assumed(self):
        record = self.resolve(self.result(), job_record=None,
                              import_source="the GER owner carried this from Astra")
        self.assertEqual(record["provider_evidence"], "imported")
        self.assertEqual(record["imported_from"],
                         "the GER owner carried this from Astra")
        self.assertEqual(record["verdict"], "commit_contract")

    def test_a_negative_verdict_is_recorded_not_refused(self):
        self.assertEqual(self.resolve(self.result(recommendation="revise"))["verdict"],
                         "revise")

    def test_a_review_of_different_contract_bytes_is_refused(self):
        # The defect this binding closes: the report was never checked against
        # the commit it was filed against.
        with self.assertRaises(Refused) as caught:
            self.resolve(self.result(reviewed_artifact_sha256="c" * 64))
        self.assertIn("artifact_hash_mismatch", str(caught.exception))

    def test_a_review_of_the_previous_revision_is_refused(self):
        # The realistic version: a real hash, of the contract as it was BEFORE
        # the commit under check.
        with self.assertRaises(Refused):
            self.resolve(self.result(
                reviewed_artifact_sha256=ac.sha256(CONTRACT_V1)))

    def test_a_declared_incomplete_is_refused(self):
        with self.assertRaises(Refused) as caught:
            self.resolve(self.result(review_status="incomplete", recommendation=None,
                                     report_markdown="Did not finish."))
        self.assertIn("incomplete", str(caught.exception))

    def test_a_legacy_report_is_refused_without_the_flag(self):
        # No sniffing: the caller declares the format or it is not read.
        with self.assertRaises(Refused) as caught:
            self.resolve(LEGACY_CLOSURE_REPORT.encode("utf-8"))
        self.assertIn("not valid (not_json)", str(caught.exception))

    def test_a_legacy_report_reads_with_the_flag(self):
        record = self.resolve(LEGACY_CLOSURE_REPORT.encode("utf-8"), legacy=True)
        self.assertEqual(record["verdict"], "commit_contract")
        self.assertEqual(record["protocol"], "legacy-markdown")

    def test_the_legacy_flag_does_not_accept_a_broken_v2_result(self):
        # legacy=True selects the old READER; it is not a bypass that accepts
        # anything. A JSON result has no legacy verdict line.
        with self.assertRaises(Refused):
            self.resolve(self.result(), legacy=True)

    def test_a_commit_that_did_not_touch_the_task_is_refused(self):
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "--allow-empty",
                        "-m", "unrelated"], capture_output=True)
        head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        with self.assertRaises(Refused) as caught:
            ac.resolve_post_commit_check(
                self.report(self.result()), head, TASK, refuse)
        self.assertIn("did not change", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
