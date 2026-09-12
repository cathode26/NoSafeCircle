#!/usr/bin/env python3
"""Pure/component, regression-only viewer integrity tests using temporary Git repos.

No Unity asset, provider, GitHub service or production checkout is mutated.
Set NSC_THIRD_PRESERVE_FIXTURES=1 to retain disposable forensic evidence.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_rehearsal_view_test as fixture_module
from Pipeline.TaskReviewAgent import local_rehearsal
from Pipeline.TaskReviewAgent.contracts import semantic_sha256, TaskReviewContractError


class ThirdViewerIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.LocalRehearsalViewTests()
        self.fixture.setUp()
        self.context = self.fixture.context
        self.view = self.fixture.view()

    def tearDown(self):
        if os.environ.get("NSC_THIRD_PRESERVE_FIXTURES") != "1":
            self.fixture.tearDown()

    def rewrite(self, path, changes, hash_field):
        value = json.loads(path.read_text(encoding="utf-8"))
        changes(value)
        value.pop(hash_field, None)
        value[hash_field] = semantic_sha256(value)
        path.write_text(json.dumps(value), encoding="utf-8")
        return value

    def forge_manifest_and_rebind_state(self, change):
        manifest = self.rewrite(self.context.manifest_path, change, "manifest_sha256")
        self.rewrite(self.context.state_path,
                     lambda state: state.update(manifest_sha256=manifest["manifest_sha256"]),
                     "state_sha256")

    def assert_rejected(self, callback):
        with self.assertRaises((local_rehearsal.LocalRehearsalError, TaskReviewContractError)):
            callback()

    def test_committed_hash_does_not_authorize_forged_contract_body(self):
        task = self.fixture.task_id
        self.forge_manifest_and_rebind_state(
            lambda manifest: manifest["contracts"][task].update(title="Forged contract title"))
        self.assert_rejected(lambda: local_rehearsal.LocalRunContext.from_root(self.context.root))
        self.assert_rejected(self.view.build)

    def test_committed_hash_does_not_authorize_forged_graph_children(self):
        task = self.fixture.task_id
        self.forge_manifest_and_rebind_state(
            lambda manifest: manifest["contracts"][task].update(decomposition_children=["NSC-999"]))
        self.assert_rejected(lambda: local_rehearsal.LocalRunContext.from_root(self.context.root))

    def test_authority_rechecks_committed_contract_on_every_assertion(self):
        real_parse = local_rehearsal.parse_committed_task_bytes
        with mock.patch.object(
            local_rehearsal, "parse_committed_task_bytes", wraps=real_parse
        ) as calls:
            self.context.assert_current()
            self.context.assert_current()
        self.assertEqual(calls.call_count, 2 * len(self.context.task_ids))

    def test_warm_view_rejects_rehashed_manifest_identity_rewrite(self):
        self.view.build()
        self.forge_manifest_and_rebind_state(lambda manifest: manifest.update(max_capacity=999))
        self.assert_rejected(self.view.build)
        self.assert_rejected(self.view.fingerprint)

    def test_warm_poll_reuses_verified_contracts_but_checks_source(self):
        self.view.build()
        real_run = local_rehearsal.subprocess.run
        with mock.patch.object(local_rehearsal.subprocess, "run", wraps=real_run) as calls:
            self.view.build()
        commands = [call.args[0] for call in calls.call_args_list if call.args and call.args[0][0] == "git"]
        self.assertLessEqual(len(commands), 7, commands)
        self.assertFalse(any("show" in command for command in commands), commands)
        self.assertTrue(any("status" in command for command in commands), commands)
        self.assertEqual(sum("cat-file" in command for command in commands), 1, commands)

    def test_committed_batch_rejects_malformed_framing_and_changed_bytes(self):
        task = self.fixture.task_id
        command = ("git", "-C", str(self.fixture.source), "cat-file", "--batch")
        result = local_rehearsal.subprocess.run(
            command, input=f"{self.context.source_head}:Tasks/{task}.yaml\n".encode(),
            capture_output=True, check=True)
        valid = result.stdout
        header, body = valid.split(b"\n", 1)
        malformed = [b"", b"missing\n", valid[:-1], valid + b"unexpected\n",
                     header.replace(b" blob ", b" tree ") + b"\n" + body,
                     header + b"\n" + b"x" + body[1:]]
        for payload in malformed:
            with self.subTest(payload=payload[:70]):
                response = local_rehearsal.subprocess.CompletedProcess(command, 0, payload, b"")
                with mock.patch.object(local_rehearsal.subprocess, "run", return_value=response):
                    self.assert_rejected(self.context._assert_contract_bytes_current)

    def test_warm_view_rejects_source_changes(self):
        self.view.build()
        (self.fixture.source / "untracked.txt").write_text("dirty", encoding="utf-8")
        self.assert_rejected(self.view.build)
        self.assert_rejected(self.view.fingerprint)

    def test_warm_view_rejects_branch_change_at_same_commit(self):
        self.view.build()
        self.fixture.git("switch", "-c", "different")
        self.assert_rejected(self.view.build)

    def test_warm_view_rejects_detached_head(self):
        self.view.build()
        self.fixture.git("checkout", "--detach", "HEAD")
        self.assert_rejected(self.view.build)

    def test_warm_view_rejects_new_commit(self):
        self.view.build()
        self.fixture.git("commit", "--allow-empty", "-m", "Change disposable source commit")
        self.assert_rejected(self.view.build)

    def test_manifest_content_is_checked_when_size_and_timestamp_are_preserved(self):
        self.view.build()
        original = self.context.manifest_path.stat()
        payload = self.context.manifest_path.read_bytes()
        changed = payload.replace(b"all-claude", b"all-codexx")
        self.assertEqual(len(payload), len(changed))
        self.assertNotEqual(payload, changed)
        self.context.manifest_path.write_bytes(changed)
        os.utime(self.context.manifest_path, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assert_rejected(self.view.build)

    def test_warm_view_rejects_origin_change(self):
        self.view.build()
        self.fixture.git("remote", "add", "origin", "https://github.com/example/rehearsal.git")
        self.assert_rejected(self.view.build)

    def test_warm_view_rejects_git_blob_replacement_at_same_commit(self):
        self.view.build()
        task = self.fixture.task_id
        original_blob = self.fixture.git("rev-parse", f"HEAD:Tasks/{task}.yaml")
        replacement = self.fixture.root / "replacement-contract.json"
        contract = dict(self.context.manifest["contracts"][task], title="Replacement blob")
        contract.pop("task_contract_sha256")
        replacement.write_text(json.dumps(contract), encoding="utf-8")
        replacement_blob = self.fixture.git("hash-object", "-w", str(replacement))
        self.fixture.git("replace", original_blob, replacement_blob)
        self.assertEqual(self.fixture.git("rev-parse", "HEAD"), self.context.source_head)
        self.assertEqual(self.fixture.git("status", "--porcelain=v1"), "")
        self.assert_rejected(self.view.build)

    def test_warm_view_rejects_direct_loose_object_corruption(self):
        self.view.build()
        blob = self.fixture.git("rev-parse", f"HEAD:Tasks/{self.fixture.task_id}.yaml")
        path = self.fixture.source / ".git" / "objects" / blob[:2] / blob[2:]
        self.assertTrue(path.resolve().is_relative_to(self.fixture.root.resolve()))
        original = path.read_bytes()
        (self.fixture.root / "original-contract-blob.zlib").write_bytes(original)
        _, body = zlib.decompress(original).split(b"\0", 1)
        contract = json.loads(body)
        contract["title"] = "Corrupt object stored under the original Git object ID"
        changed = json.dumps(contract).encode("utf-8")
        path.chmod(path.stat().st_mode | stat.S_IWRITE)
        path.write_bytes(zlib.compress(b"blob " + str(len(changed)).encode("ascii") + b"\0" + changed))
        self.assertEqual(self.fixture.git("rev-parse", "HEAD"), self.context.source_head)
        self.assertEqual(self.fixture.git("status", "--porcelain=v1"), "")
        self.assert_rejected(self.view.build)
        self.assert_rejected(self.context.assert_current)

    def test_warm_view_rejects_state_hash_and_event_chain_damage(self):
        self.view.build()
        self.rewrite(self.context.state_path,
                     lambda state: state["events"][0].update(previous_event_id="forged"),
                     "state_sha256")
        self.assert_rejected(self.view.build)

    def test_snapshot_return_does_not_mutate_retained_authority(self):
        snapshot = self.view.local_snapshot()
        snapshot["contracts"][self.fixture.task_id]["title"] = "Caller mutation"
        snapshot["tasks"][self.fixture.task_id]["state"] = "complete"
        actual = self.view.local_snapshot()
        self.assertNotEqual(actual["contracts"][self.fixture.task_id]["title"], "Caller mutation")
        self.assertNotEqual(actual["tasks"][self.fixture.task_id]["state"], "complete")

    def test_warm_view_observes_new_valid_events(self):
        self.view.build()
        self.context.record_stage(self.fixture.task_id, "architect_admission")
        observed = self.view.local_snapshot()
        self.assertEqual(observed["tasks"][self.fixture.task_id]["pipeline_stage"], "architect_admission")
        self.assertEqual(observed["events"][-1]["event"], "architect_admission")


if __name__ == "__main__":
    unittest.main()
