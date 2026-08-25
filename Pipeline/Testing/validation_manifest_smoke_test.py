#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from validation_manifest import ValidationManifestError, load_validation_manifest


XML = b'<test-run result="Passed" total="3" passed="2" failed="0" skipped="1" />\n'
LOG = b"Unity test log\n"


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
        "runner": {"path": "Pipeline/Testing/run_unity_tests_clean.ps1"},
    }
    path = directory / "validation-manifest.json"
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return path, raw


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
            self.assertEqual(before, sorted((p.name, p.read_bytes()) for p in Path(name).iterdir()))

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


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ValidationManifestSmokeTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful(): print("validation manifest smoke tests: PASS")
    raise SystemExit(0 if result.wasSuccessful() else 1)
