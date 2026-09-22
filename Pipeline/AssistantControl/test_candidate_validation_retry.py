from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.candidate_validation_retry import (
    CandidateValidationRetryError,
    reopen_candidate_validation,
    validation_failure_sha256,
)
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.source_update import synchronize_candidate
from Pipeline.AssistantControl.unity_materialization import (
    _require_candidate,
    materialize_candidate,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitReceipt


BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/ChapelOfAshSceneBuilder.cs"
SCENE = "Assets/Scenes/Rooms/ChapelOfAsh.unity"
TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/ChapelOfAshSceneTests.cs"


class CandidateValidationRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-q")
        self.git(self.source, "config", "user.name", "No Safe Circle Test Agent")
        self.git(self.source, "config", "user.email", "test@example.invalid")
        task = {
            "schema_version": "2.0",
            "id": "NSC-046",
            "contract_revision": 1,
            "contract_disposition": "active",
            "title": "Fixture room",
            "reconciliation_key": "fixture-room",
            "kind": "implementation",
            "type": "world-foundation",
            "execution_scope": "single_agent",
            "execution_reason": "fixture",
            "decomposition_state": "concrete",
            "decomposition_reason": "fixture",
            "parent": None,
            "depends_on": [],
            "exclusive_resources": [
                f"repo-file:{BUILDER}",
                f"repo-file:{TEST}",
                f"unity-scene:{SCENE}",
            ],
            "acceptance_criteria": [],
            "completion_gates": [],
            "downstream_integration_obligations": [],
            "gdd_evidence": [],
            "basis": "direct_gdd",
            "source_scope": "required",
            "confidence": "high",
        }
        task_path = self.source / "Tasks/NSC-046.yaml"
        task_path.parent.mkdir()
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        (self.source / "Pipeline/AssistantControl").mkdir(parents=True)
        (self.source / "Pipeline/AssistantControl/host.py").write_text(
            "HOST = 1\n", encoding="utf-8", newline="\n"
        )
        test_path = self.source / TEST
        test_path.parent.mkdir(parents=True)
        test_path.write_text("class ChapelOfAshSceneTests {}\n", encoding="utf-8", newline="\n")
        for parent in (
            self.source / "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms",
            self.source / "Assets/Scenes/Rooms",
        ):
            parent.mkdir(parents=True, exist_ok=True)
            (parent / ".keep").write_text("fixture\n", encoding="utf-8", newline="\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "fixture base")
        self.base = self.git(self.source, "rev-parse", "HEAD")

        self.manager = Checkouts(self.source, root / "checkouts")
        prepared = self.manager.prepare("NSC-046")
        self.checkout = Path(prepared["checkout"])
        self.unity = root / "Unity.exe"
        self.unity.write_bytes(b"fixture")
        self.lease = "fixture-lease"
        scope = AssistantScopePlanner(self.manager).plan(
            "NSC-046",
            ExecutionScopePlan((), (BUILDER, SCENE), (TEST,), ()),
            lease_id=self.lease,
        )
        builder = self.checkout / BUILDER
        builder.parent.mkdir(parents=True, exist_ok=True)
        builder.write_text("class ChapelOfAshSceneBuilder {}\n", encoding="utf-8", newline="\n")
        self.git(self.checkout, "add", "--", BUILDER)
        self.git(self.checkout, "commit", "-q", "-m", "crew room candidate")
        self.candidate = self.git(self.checkout, "rev-parse", "HEAD")
        tree = self.git(self.checkout, "rev-parse", "HEAD^{tree}")

        record_path = self.manager.records / "NSC-046.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        receipt = LocalCandidateCommitReceipt(
            task_id="NSC-046",
            lease_id=self.lease,
            plan_id=scope["plan_id"],
            run_id="fixture-run",
            source_base=self.base,
            candidate_commit=self.candidate,
            candidate_tree=tree,
            candidate_parent=self.base,
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64,
            candidate_patch_sha256="b" * 64,
            changed_paths=(BUILDER,),
            validation_sha256="c" * 64,
        )
        record["candidate"] = {
            "commit": self.candidate,
            "tree": tree,
            "parent": self.base,
            "run_id": "fixture-run",
            "lease_id": self.lease,
            "plan_id": scope["plan_id"],
            "receipt": receipt.to_dict(),
        }
        self.failure = {
            "candidate_commit": self.candidate,
            "validation_error": "old host validated before building the room scene",
            "failed_at": "2026-09-13T19:00:00+00:00",
        }
        record["status"] = "validation_failed"
        record["approval"] = None
        record["human_review"] = None
        record["candidate_validation_failure"] = dict(self.failure)
        write_record(record_path, record)

        (self.source / "Pipeline/AssistantControl/host.py").write_text(
            "HOST = 2\n", encoding="utf-8", newline="\n"
        )
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "fix materialization host")
        self.host_fix = self.git(self.source, "rev-parse", "HEAD")
        self.failure_sha = validation_failure_sha256(self.failure)

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(root), *args), capture_output=True, check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def reopen(self):
        return reopen_candidate_validation(
            self.manager,
            "NSC-046",
            expected_candidate=self.candidate,
            expected_failure_sha256=self.failure_sha,
            host_fix_commit=self.host_fix,
        )

    def test_reopens_exact_failure_syncs_source_and_preserves_crew_authority(self):
        result = self.reopen()
        self.assertEqual("validation_retry_authorized", result["status"])
        self.assertEqual(self.failure, result["candidate_validation_failure"])
        retry = result["candidate_validation_retry"]
        self.assertEqual(self.failure, retry["failed_validation"])
        self.assertEqual(self.host_fix, retry["host_fix_commit"])
        self.assertEqual([SCENE], retry["registered_generated_paths"])
        self.assertEqual(
            ["Pipeline/AssistantControl/host.py"], retry["host_changed_paths"]
        )
        self.assertEqual(1, len(result["candidate_validation_retry_history"]))
        self.assertEqual(result, self.reopen())
        synchronized = synchronize_candidate(
            self.manager, "NSC-046", self.candidate, self.host_fix,
        )
        self.assertEqual("awaiting_human", synchronized["status"])
        self.assertNotIn("candidate_validation_failure", synchronized)
        synced_candidate = synchronized["candidate"]
        self.assertEqual("source_synchronized", synced_candidate["kind"])
        self.assertEqual(
            "source_synchronized", synchronized["candidate_validation_retry"]["phase"]
        )
        (_checkout, _candidate, receipt, generated, generated_roots,
         _asset_metas) = _require_candidate(
            self.manager, synchronized, synced_candidate["commit"]
        )
        self.assertEqual([BUILDER], receipt["changed_paths"])
        self.assertEqual((SCENE,), generated)
        self.assertEqual((), generated_roots)

        def builder_runner(args, cwd, timeout):
            self.assertEqual(self.checkout.resolve(), cwd.resolve())
            self.assertGreater(timeout, 0)
            target = cwd / SCENE
            target.write_text("generated Chapel scene\n", encoding="utf-8", newline="\n")
            return subprocess.CompletedProcess(args, 0, b"builder complete\n", b"")

        def validation_runner(**kwargs):
            commit = self.git(kwargs["checkout"], "rev-parse", "HEAD")
            self.assertEqual(kwargs["commit"], commit)
            self.assertEqual("", self.git(kwargs["checkout"], "status", "--porcelain=v1"))
            return ({
                "test_platform": "EditMode",
                "test_filter": "ChapelOfAshSceneTests",
                "commit": commit,
                "tree": self.git(kwargs["checkout"], "rev-parse", "HEAD^{tree}"),
                "total": 1,
                "passed": 1,
            },)

        materialized = materialize_candidate(
            self.manager,
            "NSC-046",
            synced_candidate["commit"],
            unity_executable=self.unity,
            unity_command_runner=builder_runner,
            validation_runner=validation_runner,
        )
        final_candidate = materialized["candidate"]
        self.assertEqual("unity_materialized", final_candidate["kind"])
        self.assertEqual(receipt["plan_id"], final_candidate["plan_id"])
        self.assertEqual(receipt["lease_id"], final_candidate["lease_id"])
        self.assertEqual([SCENE], final_candidate["changed_paths"])
        self.assertEqual("awaiting_human", materialized["status"])
        self.assertIsNone(materialized["approval"])
        self.assertIsNone(materialized["human_review"])
        self.assertEqual(1, len(materialized["candidate_validation_retry_history"]))
        self.assertEqual(
            "source_synchronized",
            materialized["candidate_validation_retry"]["phase"],
        )

    def test_wrong_failure_hash_is_refused_without_changing_state(self):
        with self.assertRaisesRegex(
            CandidateValidationRetryError, "failed validation differs"
        ):
            reopen_candidate_validation(
                self.manager,
                "NSC-046",
                expected_candidate=self.candidate,
                expected_failure_sha256="0" * 64,
                host_fix_commit=self.host_fix,
            )
        record = json.loads(
            (self.manager.records / "NSC-046.json").read_text(encoding="utf-8")
        )
        self.assertEqual("validation_failed", record["status"])
        self.assertEqual(self.failure, record["candidate_validation_failure"])

    def test_task_contract_change_is_refused(self):
        task_path = self.source / "Tasks/NSC-046.yaml"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["contract_revision"] = 2
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "change task contract")
        unsafe_head = self.git(self.source, "rev-parse", "HEAD")
        with self.assertRaisesRegex(
            CandidateValidationRetryError, "task contract changed"
        ):
            reopen_candidate_validation(
                self.manager,
                "NSC-046",
                expected_candidate=self.candidate,
                expected_failure_sha256=self.failure_sha,
                host_fix_commit=unsafe_head,
            )

    def test_tampered_retry_marker_cannot_authorize_source_sync(self):
        self.reopen()
        record_path = self.manager.records / "NSC-046.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["candidate_validation_retry"]["failed_validation_sha256"] = "0" * 64
        write_record(record_path, record)
        with self.assertRaisesRegex(
            ValueError, "approved or unreviewed candidate"
        ):
            synchronize_candidate(
                self.manager, "NSC-046", self.candidate, self.host_fix,
            )

    def test_non_json_retry_failure_is_refused_without_affecting_other_states(self):
        self.reopen()
        record_path = self.manager.records / "NSC-046.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["candidate_validation_failure"]["invalid_number"] = float("nan")
        write_record(record_path, record)
        with self.assertRaisesRegex(
            ValueError, "approved or unreviewed candidate"
        ):
            synchronize_candidate(
                self.manager, "NSC-046", self.candidate, self.host_fix,
            )

    def test_source_advance_after_authorized_host_fix_requires_new_authorization(self):
        self.reopen()
        later = self.source / "Pipeline/AssistantControl/later.py"
        later.write_text("LATER = 1\n", encoding="utf-8", newline="\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "later unrelated source advance")
        later_head = self.git(self.source, "rev-parse", "HEAD")
        with self.assertRaisesRegex(
            ValueError, "authorized validation host-fix commit"
        ):
            synchronize_candidate(
                self.manager, "NSC-046", self.candidate, later_head,
            )


if __name__ == "__main__":
    unittest.main()
