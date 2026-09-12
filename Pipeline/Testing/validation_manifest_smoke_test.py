#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from validation_manifest import (
    ValidationManifestError,
    import_validation_manifest,
    load_validation_manifest,
)


XML = b'<test-run result="Passed" total="3" passed="2" failed="0" skipped="1" />\n'
LOG = b"Unity test log\n"
RUNNER_PATH = "Pipeline/Testing/run_unity_tests_clean.ps1"
RUNNER_SHA256 = "3" * 64
RUNNER_SOURCE_COMMIT = "4" * 40
RUNNER_SOURCE_TREE = "5" * 40


def fixture(directory: Path) -> tuple[Path, dict]:
    (directory / "test-results.xml").write_bytes(XML)
    (directory / "unity.log").write_bytes(LOG)
    raw = {
        "schema_version": "1.0", "manifest_type": "unity_test_validation", "status": "passed",
        "validated_state": {"commit": "1" * 40, "tree": "2" * 40, "post_commit": "1" * 40,
                            "post_tree": "2" * 40, "repository_clean_before": True, "repository_clean_after": True},
        "unity": {"version": "6000.0.55f1", "executable": r"C:\Unity\Unity.exe", "exit_code": 0,
                  "test_platform": "PlayMode", "test_filter": "Example.Tests"},
        "test_run": {"result": "Passed", "total": 3, "passed": 2, "failed": 0, "skipped": 1},
        "artifacts": {
            "xml": {"relative_path": "test-results.xml", "sha256": hashlib.sha256(XML).hexdigest(), "size_bytes": len(XML)},
            "log": {"relative_path": "unity.log", "sha256": hashlib.sha256(LOG).hexdigest(), "size_bytes": len(LOG)},
        },
        "runner": {"path": RUNNER_PATH},
    }
    path = directory / "validation-manifest.json"
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return path, raw


def identify_runner(raw: dict) -> None:
    """Upgrade a legacy fixture to the hash-bound runner schema."""

    raw["schema_version"] = "1.1"
    raw["runner"] = {
        "path": RUNNER_PATH,
        "sha256": RUNNER_SHA256,
        "source_commit": RUNNER_SOURCE_COMMIT,
        "source_tree": RUNNER_SOURCE_TREE,
    }


class ValidationManifestSmokeTest(unittest.TestCase):
    def run_case(self, change, *, files=None) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path, raw = fixture(directory)
            change(raw)
            path.write_text(json.dumps(raw), encoding="utf-8")
            if files:
                files(directory)
            with self.assertRaises(ValidationManifestError):
                load_validation_manifest(path)

    def test_happy_path_is_immutable_and_stable(self):
        with tempfile.TemporaryDirectory() as name:
            path, _ = fixture(Path(name))
            before = sorted((p.name, p.read_bytes()) for p in Path(name).iterdir())
            first = load_validation_manifest(path)
            second = load_validation_manifest(path)
            self.assertEqual(first, second)
            self.assertEqual(first.test_run.total, 3)
            self.assertEqual(first.runner.path, RUNNER_PATH)
            self.assertIsNone(first.runner.sha256)
            self.assertIsNone(first.runner.source_commit)
            self.assertIsNone(first.runner.source_tree)
            self.assertEqual(before, sorted((p.name, p.read_bytes()) for p in Path(name).iterdir()))

    def test_hash_bound_runner_identity_is_parsed_and_rechecked_by_importer(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path, raw = fixture(directory)
            identify_runner(raw)
            path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

            manifest = load_validation_manifest(path)
            self.assertEqual(manifest.runner.path, RUNNER_PATH)
            self.assertEqual(manifest.runner.sha256, RUNNER_SHA256)
            self.assertEqual(manifest.runner.source_commit, RUNNER_SOURCE_COMMIT)
            self.assertEqual(manifest.runner.source_tree, RUNNER_SOURCE_TREE)

            imported = import_validation_manifest(
                path,
                controller_root=directory,
                expected_commit="1" * 40,
                expected_tree="2" * 40,
                expected_test_platform="PlayMode",
                expected_test_filter="Example.Tests",
                expected_runner_sha256=RUNNER_SHA256,
                expected_runner_source_commit=RUNNER_SOURCE_COMMIT,
                expected_runner_source_tree=RUNNER_SOURCE_TREE,
            )
            self.assertEqual(imported.manifest.runner, manifest.runner)

    def test_hash_bound_runner_requires_every_exact_field(self):
        for missing in ("path", "sha256", "source_commit", "source_tree"):
            with self.subTest(missing=missing):
                self.run_case(
                    lambda raw, missing=missing: (
                        identify_runner(raw),
                        raw["runner"].pop(missing),
                    )
                )

        for field, malformed in (
            ("sha256", "g" * 64),
            ("sha256", "3" * 63),
            ("source_commit", "A" * 40),
            ("source_commit", "4" * 39),
            ("source_tree", "z" * 40),
            ("source_tree", "5" * 41),
        ):
            with self.subTest(field=field, malformed=malformed):
                self.run_case(
                    lambda raw, field=field, malformed=malformed: (
                        identify_runner(raw),
                        raw["runner"].__setitem__(field, malformed),
                    )
                )

        self.run_case(
            lambda raw: (
                identify_runner(raw),
                raw["runner"].__setitem__("unexpected", "value"),
            )
        )

    def test_importer_rejects_well_formed_but_forged_runner_identity(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path, raw = fixture(directory)
            identify_runner(raw)
            path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            common = {
                "controller_root": directory,
                "expected_commit": "1" * 40,
                "expected_tree": "2" * 40,
                "expected_test_platform": "PlayMode",
                "expected_test_filter": "Example.Tests",
                "expected_runner_sha256": RUNNER_SHA256,
                "expected_runner_source_commit": RUNNER_SOURCE_COMMIT,
                "expected_runner_source_tree": RUNNER_SOURCE_TREE,
            }
            for label, override in (
                ("sha256", {"expected_runner_sha256": "6" * 64}),
                ("source commit", {"expected_runner_source_commit": "7" * 40}),
                ("source tree", {"expected_runner_source_tree": "8" * 40}),
            ):
                with self.subTest(label=label):
                    with self.assertRaisesRegex(
                        ValidationManifestError,
                        "runner",
                    ):
                        import_validation_manifest(path, **{**common, **override})

    def test_importer_refuses_legacy_manifest_when_runner_identity_is_required(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path, _ = fixture(directory)
            with self.assertRaisesRegex(ValidationManifestError, "runner"):
                import_validation_manifest(
                    path,
                    controller_root=directory,
                    expected_commit="1" * 40,
                    expected_tree="2" * 40,
                    expected_test_platform="PlayMode",
                    expected_test_filter="Example.Tests",
                    expected_runner_sha256=RUNNER_SHA256,
                    expected_runner_source_commit=RUNNER_SOURCE_COMMIT,
                    expected_runner_source_tree=RUNNER_SOURCE_TREE,
                )

    def test_hash_and_size_mismatch(self):
        self.run_case(lambda raw: raw["artifacts"]["xml"].__setitem__("sha256", "0" * 64))
        self.run_case(lambda raw: raw["artifacts"]["log"].__setitem__("sha256", "0" * 64))
        self.run_case(lambda raw: raw["artifacts"]["xml"].__setitem__("size_bytes", len(XML) + 1))

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory() as name:
            path, _ = fixture(Path(name)); path.write_text("{", encoding="utf-8")
            with self.assertRaises(ValidationManifestError): load_validation_manifest(path)

    def test_unknown_and_missing_fields(self):
        self.run_case(lambda raw: raw.__setitem__("unknown", 1))
        self.run_case(lambda raw: raw.pop("runner"))
        self.run_case(lambda raw: raw["unity"].__setitem__("unknown", 1))

    def test_invalid_identities_and_hash(self):
        self.run_case(lambda raw: raw["validated_state"].__setitem__("commit", "A" * 40))
        self.run_case(lambda raw: raw["validated_state"].__setitem__("tree", "x" * 40))
        self.run_case(lambda raw: raw["artifacts"]["xml"].__setitem__("sha256", "g" * 64))

    def test_dirty_identity_exit_and_result_failures(self):
        self.run_case(lambda raw: raw["validated_state"].__setitem__("repository_clean_before", False))
        self.run_case(lambda raw: raw["validated_state"].__setitem__("repository_clean_after", 1))
        self.run_case(lambda raw: raw["validated_state"].__setitem__("post_commit", "3" * 40))
        self.run_case(lambda raw: raw["validated_state"].__setitem__("post_tree", "3" * 40))
        self.run_case(lambda raw: raw["unity"].__setitem__("exit_code", 1))
        self.run_case(lambda raw: raw["test_run"].__setitem__("result", "Failed"))
        self.run_case(lambda raw: raw["test_run"].__setitem__("failed", 1))

    def test_bad_counts(self):
        for value in (True, -1, 1.5, "1"):
            self.run_case(lambda raw, value=value: raw["test_run"].__setitem__("passed", value))
        self.run_case(lambda raw: raw["test_run"].update(total=1, passed=2))
        self.run_case(
            lambda raw: raw["test_run"].update(
                total=0, passed=0, failed=0, skipped=0
            )
        )

    def test_xml_mismatch_and_malformed(self):
        self.run_case(lambda raw: raw["test_run"].__setitem__("total", 4))
        def malformed(directory):
            data = b"not xml"; (directory / "test-results.xml").write_bytes(data)
        self.run_case(lambda raw: raw["artifacts"]["xml"].update(sha256=hashlib.sha256(b"not xml").hexdigest(), size_bytes=7), files=malformed)

    def test_missing_and_unsafe_artifacts(self):
        self.run_case(lambda raw: None, files=lambda directory: (directory / "unity.log").unlink())
        self.run_case(lambda raw: raw["artifacts"]["log"].__setitem__("relative_path", "/tmp/log"))
        self.run_case(lambda raw: raw["artifacts"]["log"].__setitem__("relative_path", "../unity.log"))
        self.run_case(lambda raw: raw["artifacts"]["log"].__setitem__("relative_path", r"C:\unity.log"))

    def test_artifact_path_traversal_vectors_rejected(self):
        cases = (
            ("../unity.log", "traversal component"),
            ("nested/../../../../unity.log", "traversal component"),
            ("a/../../b", "traversal component"),
            ("/etc/passwd", "repository-independent relative path"),
            (r"C:\Windows\System32\drivers\etc\hosts", "repository-independent relative path"),
            ("C:Windows/System32/drivers/etc/hosts", "repository-independent relative path"),
            (r"\\server\share\unity.log", "repository-independent relative path"),
            ("unity\x00.log", "control character"),
            ("unity\n.log", "control character"),
        )
        for relative_path, expected_error in cases:
            with self.subTest(relative_path=repr(relative_path)):
                with tempfile.TemporaryDirectory() as name:
                    path, raw = fixture(Path(name))
                    raw["artifacts"]["log"]["relative_path"] = relative_path
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    with self.assertRaisesRegex(
                        ValidationManifestError,
                        expected_error,
                    ):
                        load_validation_manifest(path)

    @unittest.skipUnless(os.name == "nt", "Windows case-insensitivity only")
    def test_case_insensitive_prefix_trick_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            parent = Path(name)
            directory = parent / "ArtifactRoot"
            outside = parent / "ARTIFACTROOT-Escape"
            directory.mkdir()
            outside.mkdir()
            (outside / "unity.log").write_bytes(LOG)
            path, raw = fixture(directory)
            relative_path = "../ARTIFACTROOT-ESCAPE/unity.log"
            candidate = directory / relative_path
            self.assertFalse(candidate.resolve().is_relative_to(directory.resolve()))
            raw["artifacts"]["log"]["relative_path"] = relative_path
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValidationManifestError, "traversal component"):
                load_validation_manifest(path)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as name, tempfile.TemporaryDirectory() as outside:
            directory = Path(name); path, raw = fixture(directory)
            target = Path(outside) / "log"; target.write_bytes(LOG)
            (directory / "unity.log").unlink()
            try: os.symlink(target, directory / "unity.log")
            except OSError: self.skipTest("symlink creation unavailable")
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValidationManifestError): load_validation_manifest(path)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_intermediate_symlink_escape_rejected_after_resolution(self):
        with tempfile.TemporaryDirectory() as name, tempfile.TemporaryDirectory() as outside:
            directory = Path(name)
            path, raw = fixture(directory)
            outside_directory = Path(outside)
            (outside_directory / "unity.log").write_bytes(LOG)
            link = directory / "artifacts"
            try:
                os.symlink(outside_directory, link, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink creation unavailable")
            raw["artifacts"]["log"]["relative_path"] = "artifacts/unity.log"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValidationManifestError, "escapes"):
                load_validation_manifest(path)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ValidationManifestSmokeTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful(): print("validation manifest smoke tests: PASS")
    raise SystemExit(0 if result.wasSuccessful() else 1)
