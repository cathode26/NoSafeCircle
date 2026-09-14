"""Real-Git, fixture-only recovery checks; no Unity or provider process runs."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import materialization_recovery
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.materialization_recovery import (
    MaterializationRecoveryError, failure_sha256,
    reopen_failed_nsc032_materialization, refresh_recovered_nsc032_index,
)
from Pipeline.AssistantControl.materialization_policy_recovery import (
    MaterializationPolicyRecoveryError, recover_nsc032_missing_validation_policy,
)
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.unity_materialization import _require_candidate
from Pipeline.AssistantControl.unity_materialization import materialize_candidate
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import (
    AuthoritativeCandidateValidationError, AuthoritativeValidationPolicyUnavailable,
)
from Pipeline.TaskReviewAgent.door_prototype_materialization import changed_paths
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitReceipt


BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
SCENE = "Assets/Scenes/DoorPrototype.unity"
ANIM = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/Idle.anim"
TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/FloorRunRestartPlayModeTests.cs"
ENEMIES_META = "Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies.meta"
ERROR = (
    "Unity created untracked paths outside the DoorPrototype builder-owned "
    f"boundary: ('{ENEMIES_META}',)"
)


class NSC032MaterializationRecoveryTests(unittest.TestCase):
    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(("git", "-C", str(root), *args), capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def setUp(self):
        base = Path.cwd() / ".test-work"
        base.mkdir(exist_ok=True)
        self.root = base / f"nsc032-materialization-recovery-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        self.git(self.source, "config", "user.name", name)
        self.git(self.source, "config", "user.email", email)
        for path, content in (
            (BUILDER, "class DoorPrototypeSceneBuilder {}\n"),
            (SCENE, "old scene\n"),
            (ANIM, "old animation\n"),
            (TEST, "class FloorRunRestartPlayModeTests {}\n"),
            ("Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/.gitkeep", "\n"),
        ):
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        task = {
            "schema_version": "2.0", "id": "NSC-032", "contract_revision": 1,
            "contract_disposition": "active", "title": "Fixture restart",
            "reconciliation_key": "fixture-restart", "kind": "implementation",
            "type": "run_lifecycle", "execution_scope": "single_agent",
            "execution_reason": "fixture", "decomposition_state": "concrete",
            "decomposition_reason": "fixture", "parent": None, "depends_on": [],
            "exclusive_resources": [f"repo-file:{BUILDER}", f"unity-scene:{SCENE}",
                                    f"repo-file:{TEST}"],
            "acceptance_criteria": [], "completion_gates": [],
            "downstream_integration_obligations": [], "gdd_evidence": [],
            "basis": "direct_gdd", "source_scope": "required", "confidence": "high",
        }
        task_path = self.source / "Tasks/NSC-032.yaml"
        task_path.parent.mkdir()
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "fixture base")
        self.base = self.git(self.source, "rev-parse", "HEAD")
        self.manager = Checkouts(self.source, self.root / "checkouts")
        prepared = self.manager.prepare("NSC-032")
        self.checkout = Path(prepared["checkout"])
        scope = AssistantScopePlanner(self.manager).plan(
            "NSC-032", ExecutionScopePlan((BUILDER, SCENE), (), (TEST,), ()),
            lease_id="fixture-lease",
        )
        (self.checkout / BUILDER).write_text("class FixedBuilder {}\n", newline="\n")
        self.git(self.checkout, "add", "--", BUILDER)
        self.git(self.checkout, "commit", "-q", "-m", "reviewed code candidate")
        self.candidate = self.git(self.checkout, "rev-parse", "HEAD")
        tree = self.git(self.checkout, "rev-parse", "HEAD^{tree}")
        self.record_path = self.manager.records / "NSC-032.json"
        record = json.loads(self.record_path.read_text(encoding="utf-8"))
        receipt = LocalCandidateCommitReceipt(
            task_id="NSC-032", lease_id="fixture-lease", plan_id=scope["plan_id"],
            run_id="fixture-run", source_base=self.base,
            candidate_commit=self.candidate, candidate_tree=tree,
            candidate_parent=self.base,
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            changed_paths=(BUILDER,), validation_sha256="c" * 64,
        )
        record["candidate"] = {
            "commit": self.candidate, "tree": tree, "parent": self.base,
            "run_id": "fixture-run", "lease_id": "fixture-lease",
            "plan_id": scope["plan_id"], "receipt": receipt.to_dict(),
        }
        record["status"] = "materialization_failed"
        record["approval"] = None
        record["human_review"] = None
        self.failure = {
            "schema_version": "assistant-unity-materialization/v1",
            "phase": "materialization_failed", "task_id": "NSC-032",
            "original_candidate_commit": self.candidate,
            "original_candidate_tree": tree,
            "task_contract_sha256": record["task_contract_sha256"],
            "plan_id": scope["plan_id"], "lease_id": "fixture-lease",
            "registered_generated_paths": [SCENE],
            "registered_generated_roots": [],
            "builder": "NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build",
            "materialization_error": ERROR, "retryable": False,
        }
        record["materialization_failure"] = dict(self.failure)
        write_record(self.record_path, record)
        self.journal_path = (self.manager.records
                             / f"NSC-032.unity-materialization.{self.candidate}.json")
        write_record(self.journal_path, self.failure)
        (self.checkout / SCENE).write_text("Unity changed scene\n", newline="\n")
        self.meta_content = (
            "fileFormatVersion: 2\nguid: 81075e5cba4420b499b12a31d486b2e6\n"
            "folderAsset: yes\nDefaultImporter:\n"
        )
        (self.checkout / ENEMIES_META).write_text(self.meta_content, newline="\n")
        self.failure_hash = failure_sha256(self.failure)

    def recover(self):
        return reopen_failed_nsc032_materialization(
            self.manager, "NSC-032", expected_candidate=self.candidate,
            expected_failure_sha256=self.failure_hash,
        )

    def materialize_with_validation(self, validation_runner):
        self.recover()
        unity = self.root / "Unity.exe"
        unity.write_bytes(b"fixture")
        def builder_runner(args, cwd, timeout):
            (cwd / SCENE).write_text("generated restart scene\n", newline="\n")
            (cwd / ENEMIES_META).write_text(self.meta_content, newline="\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return materialize_candidate(
            self.manager, "NSC-032", self.candidate,
            unity_executable=unity, unity_command_runner=builder_runner,
            validation_runner=validation_runner,
        )

    def test_missing_policy_keeps_clean_materialized_commit_without_pass_claim(self):
        calls = {"validation": 0}
        def missing_policy(**_kwargs):
            calls["validation"] += 1
            raise AuthoritativeValidationPolicyUnavailable(
                "NSC-032 has no committed authoritative validation policy"
            )
        result = self.materialize_with_validation(missing_policy)
        commit = result["candidate"]["commit"]
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("unity_materialized", result["candidate"]["kind"])
        self.assertNotIn("authoritative_validations", result["candidate"])
        self.assertEqual("not_run", result["candidate_validation_unavailable"]
                         ["automated_unity_validation"])
        self.assertEqual("", self.git(self.checkout, "status", "--porcelain=v1"))
        self.assertEqual(commit, self.git(self.checkout, "rev-parse", "HEAD"))
        self.assertEqual(1, calls["validation"])
        def forbidden_builder(*_args, **_kwargs):
            raise AssertionError("idempotent replay must not run Unity")
        replay = materialize_candidate(
            self.manager, "NSC-032", self.candidate,
            unity_command_runner=forbidden_builder,
            validation_runner=forbidden_builder,
        )
        self.assertEqual(result["candidate"], replay["candidate"])
        self.assertEqual(1, calls["validation"])

    def test_bound_old_missing_policy_recovery_is_idempotent_and_refuses_tamper(self):
        # An old host classified the exact missing-policy text as a test failure.
        def old_failure(**_kwargs):
            raise AuthoritativeCandidateValidationError(
                "NSC-032 has no committed authoritative validation policy"
            )
        with self.assertRaisesRegex(ValueError, "focused tests failed"):
            self.materialize_with_validation(old_failure)
        materialized = self.git(self.checkout, "rev-parse", "HEAD")
        failure_hash = hashlib.sha256(self.journal_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(MaterializationPolicyRecoveryError, "missing-policy"):
            recover_nsc032_missing_validation_policy(
                self.manager, "NSC-032", original_candidate=self.candidate,
                materialized_candidate=materialized, failed_journal_sha256="b" * 64,
            )
        unexpected = self.checkout / "unexpected.asset"
        unexpected.write_text("not in candidate\n")
        with self.assertRaisesRegex(MaterializationPolicyRecoveryError, "cleanliness"):
            recover_nsc032_missing_validation_policy(
                self.manager, "NSC-032", original_candidate=self.candidate,
                materialized_candidate=materialized, failed_journal_sha256=failure_hash,
            )
        unexpected.unlink()
        result = recover_nsc032_missing_validation_policy(
            self.manager, "NSC-032", original_candidate=self.candidate,
            materialized_candidate=materialized, failed_journal_sha256=failure_hash,
        )
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("unity_materialized", result["candidate"]["kind"])
        self.assertNotIn("authoritative_validations", result["candidate"])
        self.assertNotIn("validation_failure", result["candidate"])
        self.assertEqual("not_run", result["candidate_validation_unavailable"]
                         ["automated_unity_validation"])
        self.assertEqual(materialized, self.git(self.checkout, "rev-parse", "HEAD"))
        self.assertEqual("", self.git(self.checkout, "status", "--porcelain=v1"))
        again = recover_nsc032_missing_validation_policy(
            self.manager, "NSC-032", original_candidate=self.candidate,
            materialized_candidate=materialized, failed_journal_sha256=failure_hash,
        )
        self.assertEqual(result, again)
        tampered = json.loads(self.journal_path.read_text())
        tampered["validation_unavailable_reason"] = "test failed"
        write_record(self.journal_path, tampered)
        with self.assertRaisesRegex(MaterializationPolicyRecoveryError, "evidence differs"):
            recover_nsc032_missing_validation_policy(
                self.manager, "NSC-032", original_candidate=self.candidate,
                materialized_candidate=materialized, failed_journal_sha256=failure_hash,
            )

    def test_real_test_failure_cannot_be_reclassified_as_missing_policy(self):
        def real_failure(**_kwargs):
            raise AuthoritativeCandidateValidationError("NSC-032 focused test failed")
        with self.assertRaisesRegex(ValueError, "focused tests failed"):
            self.materialize_with_validation(real_failure)
        materialized = self.git(self.checkout, "rev-parse", "HEAD")
        failure_hash = hashlib.sha256(self.journal_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(MaterializationPolicyRecoveryError, "missing-policy"):
            recover_nsc032_missing_validation_policy(
                self.manager, "NSC-032", original_candidate=self.candidate,
                materialized_candidate=materialized, failed_journal_sha256=failure_hash,
            )
        record = json.loads(self.record_path.read_text())
        self.assertEqual("validation_failed", record["status"])
        self.assertEqual("unity_materialization_failed", record["candidate"]["kind"])

    def test_archives_dirty_unity_bytes_and_reopens_same_clean_candidate(self):
        result = self.recover()
        archive = Path(result["archive"])
        self.assertEqual("needs_materialization", result["status"])
        self.assertEqual("Unity changed scene\n", (archive / "dirty" / SCENE).read_text())
        self.assertEqual(self.meta_content, (archive / "dirty" / ENEMIES_META).read_text())
        self.assertTrue((archive / "failed-journal.json").is_file())
        self.assertEqual((), changed_paths(self.checkout))
        self.assertEqual(self.candidate, self.git(self.checkout, "rev-parse", "HEAD"))
        self.assertFalse(self.journal_path.exists())
        record = json.loads(self.record_path.read_text(encoding="utf-8"))
        self.assertEqual("needs_materialization", record["status"])
        self.assertEqual(self.candidate, record["candidate"]["commit"])
        self.assertIsNone(record["approval"])
        self.assertEqual((SCENE,), _require_candidate(self.manager, record, self.candidate)[3])
        unity = self.root / "Unity.exe"
        unity.write_bytes(b"fixture")
        def builder_runner(args, cwd, timeout):
            (cwd / SCENE).write_text("generated restart scene\n", newline="\n")
            (cwd / ENEMIES_META).write_text(self.meta_content, newline="\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        def validated(**kwargs):
            self.assertEqual("", self.git(self.checkout, "status", "--porcelain=v1",
                                          "--untracked-files=all"))
            self.assertEqual(self.candidate,
                             self.git(self.checkout, "rev-parse", "HEAD^"))
            self.assertTrue((self.checkout / ENEMIES_META).is_file())
            return ({"test_platform": "EditMode", "passed": 1,
                     "commit": kwargs["commit"]},)
        materialized = materialize_candidate(
            self.manager, "NSC-032", self.candidate,
            unity_executable=unity, unity_command_runner=builder_runner,
            validation_runner=validated,
        )
        self.assertEqual("unity_materialized", materialized["candidate"]["kind"])
        self.assertEqual([ENEMIES_META, SCENE], materialized["candidate"]["changed_paths"])
        self.assertEqual([ENEMIES_META], materialized["candidate"]["materialization"]
                         ["authenticated_incidental_meta_paths"])
        self.assertEqual((), changed_paths(self.checkout))

    def test_wrong_candidate_or_failure_refuses_without_cleanup(self):
        with self.assertRaisesRegex(MaterializationRecoveryError, "candidate"):
            reopen_failed_nsc032_materialization(
                self.manager, "NSC-032", expected_candidate="a" * 40,
                expected_failure_sha256=self.failure_hash,
            )
        with self.assertRaisesRegex(MaterializationRecoveryError, "failure"):
            reopen_failed_nsc032_materialization(
                self.manager, "NSC-032", expected_candidate=self.candidate,
                expected_failure_sha256="b" * 64,
            )
        self.assertTrue(self.journal_path.is_file())
        self.assertTrue((self.checkout / ENEMIES_META).is_file())

    def test_bound_index_refresh_accepts_unarchived_equal_unity_blob(self):
        self.recover()
        original_git = materialization_recovery.git
        seen = {"refreshed": False}
        def stale_stat_git(root, *args):
            if root == self.checkout and args[:2] == ("status", "--porcelain=v1"):
                return b"" if seen["refreshed"] else f" M {ANIM}\0".encode()
            if root == self.checkout and args[:2] == ("update-index", "--refresh"):
                seen["refreshed"] = True
                original_git(root, *args)
                raise RuntimeError("Git reported needs update after refreshing stale stat entries")
            return original_git(root, *args)
        with patch.object(materialization_recovery, "git", side_effect=stale_stat_git):
            result = refresh_recovered_nsc032_index(
                self.manager, "NSC-032", expected_candidate=self.candidate,
                expected_failure_sha256=self.failure_hash,
            )
        self.assertTrue(seen["refreshed"])
        self.assertEqual([ANIM], result["index_refreshed_paths"])
        self.assertNotIn(ANIM, json.loads((Path(result["archive"]) / "manifest.json")
                         .read_text())["archived_paths_sha256"])
        self.assertEqual("", self.git(self.checkout, "status", "--porcelain=v1"))
        self.assertEqual(self.candidate, self.git(self.checkout, "rev-parse", "HEAD"))

    def test_bound_index_refresh_refuses_real_content_or_identity_change(self):
        self.recover()
        (self.checkout / ANIM).write_text("post-recovery edit\n", newline="\n")
        with self.assertRaisesRegex(MaterializationRecoveryError, "content differs"):
            refresh_recovered_nsc032_index(
                self.manager, "NSC-032", expected_candidate=self.candidate,
                expected_failure_sha256=self.failure_hash,
            )
        self.assertEqual("post-recovery edit\n", (self.checkout / ANIM).read_text())
        with self.assertRaisesRegex(MaterializationRecoveryError, "reopened candidate"):
            refresh_recovered_nsc032_index(
                self.manager, "NSC-032", expected_candidate=self.candidate,
                expected_failure_sha256="b" * 64,
            )

    def test_unrelated_untracked_path_and_unrelated_source_refuse(self):
        (self.checkout / "unexpected.asset").write_text("preserve me\n")
        with self.assertRaisesRegex(MaterializationRecoveryError, "dirty paths"):
            self.recover()
        self.assertTrue((self.checkout / "unexpected.asset").is_file())
        (self.checkout / "unexpected.asset").unlink()
        self.git(self.source, "checkout", "--orphan", "unrelated-source")
        self.git(self.source, "rm", "-rf", "-q", ".")
        (self.source / "unrelated.txt").write_text("unrelated\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "unrelated")
        with self.assertRaisesRegex(MaterializationRecoveryError, "Source"):
            self.recover()
        self.assertTrue(self.journal_path.is_file())


if __name__ == "__main__":
    unittest.main()
