"""Focused, hermetic tests for the post-human-approval CI boundary."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import review
from Pipeline.AssistantControl import test_checkouts as fixture
from Pipeline.AssistantControl.__main__ import main
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.AssistantControl.publication import PublicationAdapter, PublicationError
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


def _completed(args, returncode=0, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(tuple(args), returncode, stdout, stderr)


class FakeCommandRunner:
    def __init__(self):
        self.calls: list[tuple[str, ...]] = []
        self.prs: list[dict] = []
        self.rollup: list[dict] = []
        self.expected_head = ""
        self.create_count = 0

    def __call__(self, args, cwd, timeout_seconds):
        del timeout_seconds
        values = tuple(args)
        self.calls.append(values)
        if values[0] == "git":
            return subprocess.run(values, cwd=str(cwd), capture_output=True, check=False)
        if values[:3] == ("gh", "pr", "list"):
            return _completed(values, stdout=json.dumps(self.prs).encode())
        if values[:3] == ("gh", "pr", "create"):
            self.create_count += 1
            number = 100
            self.prs.append({
                "number": number,
                "url": f"https://example.invalid/example/repo/pull/{number}",
                "state": "OPEN",
                "headRefName": "assistant/NSC-042",
                "baseRefName": "main",
                "headRefOid": self.expected_head,
                "isDraft": False,
            })
            return _completed(values, stdout=(self.prs[-1]["url"] + "\n").encode())
        if values[:3] == ("gh", "pr", "view"):
            number = int(values[3])
            found = next((dict(item) for item in self.prs if item["number"] == number), None)
            if found is None:
                return _completed(values, 1, stderr=b"not found")
            found["statusCheckRollup"] = list(self.rollup)
            return _completed(values, stdout=json.dumps(found).encode())
        return _completed(values, 1, stderr=b"unexpected command")


class PublicationTests(unittest.TestCase):
    setUp = fixture.CheckoutTests.setUp
    run_git = fixture.CheckoutTests.run_git
    manager = fixture.CheckoutTests.manager

    def setUp(self):
        fixture.CheckoutTests.setUp(self)
        self.remote_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.remote_temp.cleanup)
        self.remote = Path(self.remote_temp.name) / "origin.git"
        subprocess.run(("git", "init", "--bare", str(self.remote)),
                       capture_output=True, check=True)
        self.run_git("remote", "add", "origin", str(self.remote))
        self.checkouts = fixture.CheckoutTests.manager(self)
        record = self.checkouts.prepare("NSC-042")
        self.checkout = Path(record["checkout"])
        name, email = validated_agent_git_identity()
        subprocess.run(("git", "-C", str(self.checkout), "config", "user.name", name),
                       capture_output=True, check=True)
        subprocess.run(("git", "-C", str(self.checkout), "config", "user.email", email),
                       capture_output=True, check=True)
        (self.checkout / "wall file.txt").write_text("approved candidate\n", encoding="utf-8")
        subprocess.run(("git", "-C", str(self.checkout), "add", "wall file.txt"),
                       capture_output=True, check=True)
        subprocess.run(("git", "-C", str(self.checkout), "commit", "-m", "Candidate"),
                       capture_output=True, check=True)
        self.commit = self.git("rev-parse", "HEAD")
        current = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        current["candidate"] = {
            "commit": self.commit,
            "tree": self.git("rev-parse", "HEAD^{tree}"),
            "parent": current["source_commit"],
        }
        current["status"] = "awaiting_human"
        write_record(self.checkouts.records / "NSC-042.json", current)
        review.ReviewGate(self.checkouts).decide(
            "NSC-042", tested_commit=self.commit,
            decision="approve", message="Fixture human PASS",
        )
        self.runner = FakeCommandRunner()
        self.runner.expected_head = self.commit

    def git(self, *args):
        return subprocess.run(
            ("git", "-C", str(self.checkout), *args),
            capture_output=True, check=True,
        ).stdout.decode().strip()

    @staticmethod
    def repository_resolver(_source, *, repository=None):
        if repository is not None and repository.casefold() != "example/repo":
            raise ValueError("repository assertion differs")
        return "example/repo"

    def adapter(self):
        return PublicationAdapter(
            self.checkouts, command_runner=self.runner,
            repository_resolver=self.repository_resolver,
        )

    def publish(self):
        return self.adapter().publish_approved(
            "NSC-042", candidate_commit=self.commit,
        )

    def test_publish_uses_exact_commit_and_reuses_one_pr(self):
        first = self.publish()
        second = self.publish()
        self.assertEqual("pull_request_open", first["status"])
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertEqual(1, self.runner.create_count)
        advertised = subprocess.run(
            ("git", "ls-remote", "--heads", str(self.remote),
             "refs/heads/assistant/NSC-042"),
            capture_output=True, check=True, text=True,
        ).stdout.split()[0]
        self.assertEqual(self.commit, advertised)
        pushes = [call for call in self.runner.calls if "push" in call]
        self.assertEqual(1, len(pushes))
        self.assertIn(f"{self.commit}:refs/heads/assistant/NSC-042", pushes[0])
        self.assertNotIn("refs/heads/main", " ".join(pushes[0]))

    def test_automated_approval_cannot_cross_publication_boundary(self):
        path = self.checkouts.records / "NSC-042.json"
        record = json.loads(path.read_text())
        automated = {
            "commit": self.commit, "decision": "approve", "message": "automation",
            "authority": "assistant_gauntlet_automation", "recorded_at": "fixture",
        }
        record["human_review"] = None
        record["approval"] = automated
        record["automation_review"] = automated
        record["status"] = "approved"
        write_record(path, record)
        with self.assertRaisesRegex(ValueError, "human approval"):
            self.publish()
        self.assertEqual([], self.runner.calls)

    def test_unrecorded_remote_head_is_never_overwritten(self):
        source_head = self.run_git("rev-parse", "HEAD").decode().strip()
        self.run_git("push", "origin", f"{source_head}:refs/heads/assistant/NSC-042")
        with self.assertRaisesRegex(PublicationError, "unrecorded head"):
            self.publish()
        self.assertFalse(any(call[:3] == ("gh", "pr", "list")
                             for call in self.runner.calls))

    def test_push_before_receipt_is_adopted_on_retry(self):
        adapter = self.adapter()
        original = adapter._append_event

        def interrupt(path, ledger, **values):
            if values["kind"] == "branch_published":
                raise OSError("fixture interruption after push")
            return original(path, ledger, **values)

        with patch.object(adapter, "_append_event", side_effect=interrupt):
            with self.assertRaisesRegex(OSError, "after push"):
                adapter.publish_approved("NSC-042", candidate_commit=self.commit)
        result = self.publish()
        self.assertEqual("pull_request_open", result["status"])
        self.assertEqual(1, self.runner.create_count)

    def test_ambiguous_or_closed_pr_never_creates_another(self):
        template = {
            "url": "https://example.invalid/example/repo/pull/1",
            "state": "OPEN", "headRefName": "assistant/NSC-042",
            "baseRefName": "main", "headRefOid": self.commit, "isDraft": False,
        }
        self.runner.prs = [{**template, "number": 1}, {**template, "number": 2}]
        with self.assertRaisesRegex(PublicationError, "multiple"):
            self.publish()
        self.assertEqual(0, self.runner.create_count)

        self.runner.prs = [{**template, "number": 1, "state": "CLOSED"}]
        with self.assertRaisesRegex(PublicationError, "not open"):
            self.publish()
        self.assertEqual(0, self.runner.create_count)

    def test_ci_requires_exact_head_and_uses_latest_effective_check(self):
        self.publish()
        self.runner.rollup = [
            {"name": "build", "status": "COMPLETED", "conclusion": "FAILURE",
             "startedAt": "2026-09-12T01:00:00Z",
             "detailsUrl": "https://example.invalid/actions/runs/1/job/1"},
            {"name": "build", "status": "COMPLETED", "conclusion": "SUCCESS",
             "startedAt": "2026-09-12T02:00:00Z",
             "detailsUrl": "https://example.invalid/actions/runs/2/job/2"},
        ]
        result = self.adapter().inspect_ci("NSC-042", candidate_commit=self.commit)
        self.assertEqual("checks_passed", result["status"])
        self.assertEqual(["build"], result["checks"]["passed"])
        self.assertEqual(1, result["checks"]["ignored_historical_count"])

        self.runner.prs[0]["headRefOid"] = self.run_git("rev-parse", "HEAD^").decode().strip()
        with self.assertRaisesRegex(PublicationError, "head commit differs"):
            self.adapter().inspect_ci("NSC-042", candidate_commit=self.commit)

    def test_tampered_receipt_fails_closed(self):
        result = self.publish()
        path = Path(result["receipt_path"])
        ledger = json.loads(path.read_text())
        ledger["events"][0]["payload"]["remote_before"] = "f" * 40
        path.write_text(json.dumps(ledger), encoding="utf-8")
        with self.assertRaisesRegex(PublicationError, "event hash differs"):
            self.adapter().inspect_ci("NSC-042", candidate_commit=self.commit)

    def test_cli_dispatches_without_legacy_workflow(self):
        fake = unittest.mock.Mock()
        fake.publish_approved.return_value = {"status": "pull_request_open"}
        output = io.StringIO()
        with patch("Pipeline.AssistantControl.publication.PublicationAdapter",
                   return_value=fake), contextlib.redirect_stdout(output):
            code = main([
                "--source", str(self.root), "--checkout-root", str(self.checkouts.root),
                "publish-approved", "NSC-042", "--candidate-commit", self.commit,
            ])
        self.assertEqual(0, code)
        self.assertEqual("pull_request_open", json.loads(output.getvalue())["status"])
        fake.publish_approved.assert_called_once_with(
            "NSC-042", candidate_commit=self.commit,
            base_branch="main", repository=None,
        )


if __name__ == "__main__":
    unittest.main()
