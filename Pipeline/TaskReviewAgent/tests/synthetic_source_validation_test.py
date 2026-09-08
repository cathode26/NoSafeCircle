"""Disposable-repository source-evidence checks; no Unity/provider/network use."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.Testing import synthetic_source_validation as source_checks
from Pipeline.Testing.validation_manifest import load_validation_manifest, ValidationManifestError
from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as generator
from Pipeline.TaskReviewAgent import synthetic_gauntlet_approver as approver
from Pipeline.TaskReviewAgent import issue_workflow as workflow
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


class SourceEvidence(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic-source-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "checkout"
        self.source.mkdir()
        self.git("init", "-b", "main")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        self.git("remote", "add", "origin", f"https://github.com/{generator.PRIVATE_REPOSITORY}.git")
        self.task = generator._concrete_task(2001, 1, generator.THOUSAND_PROFILE)
        self.task["provenance"]["profile"] = "thousand"
        self.script, self.meta = generator._value_paths(2001)
        for path, data in {
            "Tasks/NSC-2001.yaml": generator._json_bytes(self.task),
            self.script: b"namespace NoSafeCircle.DoorPrototype { public static class MuffcabbageGauntlet2001 { public const int Value = 2001; } }\n",
            self.meta: f"fileFormatVersion: 2\nguid: {generator._guid(self.script)}\n".encode(),
        }.items():
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            self.git("add", "--", path)
        self.git("commit", "-m", "fixture: constant contract and exact source")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.source, capture_output=True,
                                text=True, check=True, timeout=30)
        return result.stdout.strip()

    def validate(self):
        return source_checks.validate(self.source, "NSC-2001", generator._test_filter(2001), self.root / "evidence")

    def test_manifest_distinguishes_source_checks_from_unity(self):
        path = self.validate()
        payload = json.loads(path.read_bytes())
        self.assertEqual(payload["manifest_type"], "synthetic_source_validation")
        self.assertNotIn("unity", payload)
        manifest = load_validation_manifest(path)
        self.assertEqual(manifest.repository, generator.PRIVATE_REPOSITORY)
        self.assertEqual(manifest.unity.test_platform, "SyntheticSource")
        self.assertEqual(manifest.test_run.passed, 2)
        self.assertEqual(self.git("status", "--porcelain=v1"), "")
        self.assertEqual(manifest.validated_state.commit, self.git("rev-parse", "HEAD"))
        (path.parent / "source-validation.log").write_text("forged", encoding="utf-8")
        with self.assertRaises(ValidationManifestError):
            load_validation_manifest(path)

    def test_wrong_source_value_is_rejected_before_evidence_publication(self):
        path = self.source / self.script
        path.write_text(path.read_text().replace("Value = 2001", "Value = 9999"), encoding="utf-8")
        self.git("add", "--", self.script)
        self.git("commit", "-m", "fixture: wrong constant")
        with self.assertRaisesRegex(ValueError, "constant-only"):
            self.validate()
        self.assertFalse((self.root / "evidence").exists())

    def test_split_csharp_tokens_are_rejected_before_evidence_publication(self):
        path = self.source / self.script
        original = path.read_text(encoding="utf-8")
        for index, (before, after) in enumerate((("public", "pub lic"), ("MuffcabbageGauntlet2001", "Muffcabbage Gauntlet2001"),
                                               ("Value", "Val ue"), ("2001;", "20 01;"), ("2001;", "2000 + 1;"))):
            with self.subTest(after=after):
                path.write_text(original.replace(before, after), encoding="utf-8")
                self.git("add", "--", self.script)
                self.git("commit", "-m", "fixture: invalid token boundary")
                output = self.root / f"invalid-{index}"
                with self.assertRaisesRegex(ValueError, "constant-only"):
                    source_checks.validate(self.source, "NSC-2001", generator._test_filter(2001), output)
                self.assertFalse(output.exists())

    def test_both_authorized_repository_origins_are_accepted(self):
        for index, repository in enumerate(sorted(workflow.AUTOMATED_VALIDATION_REPOSITORIES)):
            with self.subTest(repository=repository):
                self.git("remote", "set-url", "origin", f"https://github.com/{repository}.git")
                path = source_checks.validate(self.source, "NSC-2001", generator._test_filter(2001),
                                              self.root / f"repository-{index}")
                self.assertEqual(json.loads(path.read_bytes())["repository"], repository)
                self.assertEqual(load_validation_manifest(path).repository, repository)
                self.assertIn(repository, (path.parent / "source-validation.log").read_text())

    def test_allowed_formatting_preserves_exact_tokens(self):
        path = self.source / self.script
        path.write_text(path.read_text().replace(" { ", "\n{\n\t").replace(" = ", "=")
                        .replace(" }", "\n}"), encoding="utf-8")
        self.git("add", "--", self.script)
        self.git("commit", "-m", "fixture: equivalent token formatting")
        self.assertEqual(load_validation_manifest(self.validate()).test_run.passed, 2)

    def test_source_manifest_requires_exact_repository_identity(self):
        path = self.validate()
        original = json.loads(path.read_bytes())
        for value in (None, "cathode26/NoSafeCircle", generator.PRIVATE_REPOSITORY.upper(), []):
            changed = {**original, "repository": value}
            if value is None:
                changed.pop("repository")
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValidationManifestError):
                load_validation_manifest(path)

    def test_origin_change_during_validation_blocks_evidence(self):
        original_git = source_checks.git
        origins = 0
        def observed(source, *args):
            nonlocal origins
            if args == ("remote", "get-url", "origin"):
                origins += 1
                if origins == 2:
                    other = next(item for item in workflow.AUTOMATED_VALIDATION_REPOSITORIES
                                 if item != generator.PRIVATE_REPOSITORY)
                    self.git("remote", "set-url", "origin", f"https://github.com/{other}.git")
            return original_git(source, *args)
        with patch.object(source_checks, "git", observed), self.assertRaisesRegex(ValueError, "checkout moved"):
            self.validate()
        self.assertFalse((self.root / "evidence").exists())

    def test_source_policy_binds_actual_repository(self):
        from Pipeline.TaskReviewAgent.downstream_resilience import validation_plan_for, DownstreamPipelineError
        contract_hash = hashlib.sha256(generator._json_bytes(self.task)).hexdigest()
        task = {**self.task, "task_contract_sha256": contract_hash}
        path = self.source / generator.POLICY_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema_version": "1.0", "tasks": {task["id"]: {
            "task_contract_sha256": contract_hash, "required_test_platforms": ["SyntheticSource"],
            "test_filters": {"SyntheticSource": generator._test_filter(2001)}}}}), encoding="utf-8")
        hashes = set()
        for repository in sorted(workflow.AUTOMATED_VALIDATION_REPOSITORIES):
            self.git("remote", "set-url", "origin", f"https://github.com/{repository}.git")
            plan = validation_plan_for(self.source, task)
            self.assertEqual(plan["repository"], repository)
            hashes.add(plan["policy_sha256"])
        self.assertEqual(len(hashes), 2)
        for repository in ("cathode26/NoSafeCircle", "other/Pipeline-Rehearsal"):
            self.git("remote", "set-url", "origin", f"https://github.com/{repository}.git")
            with self.assertRaises(DownstreamPipelineError):
                validation_plan_for(self.source, task)

    def test_dirty_checkout_and_production_are_rejected(self):
        (self.source / self.meta).write_text("wrong", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            self.validate()
        self.git("remote", "set-url", "origin", "https://github.com/cathode26/NoSafeCircle.git")
        with self.assertRaisesRegex(ValueError, "exact private rehearsal"):
            self.validate()
        self.assertFalse((self.root / "evidence").exists())

    def test_source_envelope_is_identity_bound_and_cannot_be_human_pass(self):
        path = self.validate()
        manifest = load_validation_manifest(path)
        commit, tree = manifest.validated_state.commit, manifest.validated_state.tree
        task = {**self.task, "task_contract_sha256": hashlib.sha256(generator._json_bytes(self.task)).hexdigest()}
        state = SimpleNamespace(task_id="NSC-2001", task_contract_sha256=task["task_contract_sha256"],
                                branch="synthetic-2001", last_event_id="f" * 64,
                                head_commit=commit, human_handoff_commit=commit, human_result=None)
        result = approver._synthetic_validation_result(
            task=task, state=state, repository=generator.PRIVATE_REPOSITORY, checkout=self.source,
            plan={"required_test_platforms": ["SyntheticSource"],
                  "authority": "committed_private_synthetic_gauntlet_validation_policy", "policy_sha256": "a" * 64},
            expected_filter=generator._test_filter(2001), commit=commit, tree=tree,
            post_commit=commit, post_tree=tree, manifest_path=path,
            manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            xml_sha256=manifest.xml.sha256, log_sha256=manifest.log.sha256,
            counts={"total": 2, "passed": 2, "failed": 0, "skipped": 0},
            evidence_source="reused_pre_handoff_validation",
        )
        evidence = result["evidence"]
        workflow._validate_automated_validation_details(state, evidence)
        self.assertIn("source_validations", evidence)
        self.assertNotIn("unity_validations", evidence)
        self.assertIsNone(state.human_result)
        for field, value in (("human_result", "PASS"), ("commit", "b" * 40),
                             ("schema_version", "1.0"), ("task_id", "NSC-042")):
            with self.assertRaises(workflow.WorkflowContractError):
                workflow._validate_automated_validation_details(state, {**evidence, field: value})


if __name__ == "__main__":
    start = time.perf_counter()
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    result = run_with_synthetic_authority(unittest.main, exit=False)
    print(json.dumps({"suite": "synthetic-source-validation", "tests": result.result.testsRun,
                      "duration_seconds": round(time.perf_counter() - start, 3)}))
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
