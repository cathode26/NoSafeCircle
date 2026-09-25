"""diagnose-decomposition finds exactly the run's receipt and reads only its directory."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    import _winapi
except ImportError:  # not Windows
    _winapi = None

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.decomposition_diagnosis import diagnose

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "TaskDecomposition" / "tests" / "fixtures" / "failure_diagnosis"
)
RUN = "decomp-nsc088-clone-20260924c"


class DiagnoseDecompositionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-diagnosis-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        self.manager = Checkouts(source, root / "checkouts")
        self.manager.records.mkdir(parents=True, exist_ok=True)
        self.run_dir = self.manager.records / "decomposition-runs" / RUN
        self.run_dir.parent.mkdir(parents=True)
        shutil.copytree(FIXTURES / RUN, self.run_dir)
        self.outside = root / "outside"

    def receipt(self, name: str = "NSC-088.decomposition.json", **changes) -> Path:
        value = {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-088",
            "run_id": RUN, "status": "failed", "source": str(self.manager.source),
            "artifact_root": str(self.run_dir), **changes,
        }
        path = self.manager.records / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_the_current_receipt_is_diagnosed_without_authorizing_a_retry(self):
        self.receipt()
        result = diagnose(self.manager, "NSC-088", run_id=RUN)
        self.assertEqual(("BUDGET", "revision_used_last_call"),
                         (result["primary"]["route"], result["primary"]["reason_code"]))
        self.assertIs(False, result["retry_authorized"])
        self.assertEqual("NSC-088.decomposition.json", result["receipt"]["path"])

    def test_an_archived_receipt_is_found_by_its_run_id(self):
        self.receipt(f"NSC-088.decomposition.{RUN}.failed.archived.json")
        result = diagnose(self.manager, "NSC-088", run_id=RUN)
        self.assertEqual(f"NSC-088.decomposition.{RUN}.failed.archived.json", result["receipt"]["path"])

    def test_a_receipt_pointing_outside_its_run_directory_is_refused(self):
        elsewhere = self.manager.records / "decomposition-runs" / "another-run"
        shutil.copytree(self.run_dir, elsewhere)
        self.receipt(artifact_root=str(elsewhere))
        with self.assertRaisesRegex(ValueError, "not this run's retained directory"):
            diagnose(self.manager, "NSC-088", run_id=RUN)

    def test_a_receipt_for_another_run_or_task_is_refused(self):
        self.receipt(run_id="some-other-run")
        with self.assertRaisesRegex(ValueError, "found 0"):
            diagnose(self.manager, "NSC-088", run_id=RUN)
        self.receipt(task_id="NSC-007")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            diagnose(self.manager, "NSC-088", run_id=RUN)

    def test_two_receipts_for_one_run_are_refused(self):
        self.receipt()
        self.receipt(f"NSC-088.decomposition.{RUN}.failed.archived.json")
        with self.assertRaisesRegex(ValueError, "found 2"):
            diagnose(self.manager, "NSC-088", run_id=RUN)

    def test_a_path_shaped_run_id_is_refused(self):
        for run_id in ("../escape", "a/b", ""):
            with self.subTest(run_id=run_id), self.assertRaisesRegex(ValueError, "plain identifier"):
                diagnose(self.manager, "NSC-088", run_id=run_id)

    def test_a_duplicate_key_receipt_is_refused(self):
        (self.manager.records / "NSC-088.decomposition.json").write_text(
            '{"run_id": "%s", "run_id": "%s"}' % (RUN, RUN), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            diagnose(self.manager, "NSC-088", run_id=RUN)

    def junction(self, link: Path, target: Path) -> None:
        if not hasattr(_winapi, "CreateJunction"):
            self.skipTest("junctions are Windows-only")
        _winapi.CreateJunction(str(target), str(link))

    def test_a_run_directory_junction_is_refused(self):
        shutil.move(str(self.run_dir), str(self.outside))
        self.junction(self.run_dir, self.outside)
        self.receipt()
        with self.assertRaisesRegex(ValueError, "link or junction"):
            diagnose(self.manager, "NSC-088", run_id=RUN)

    def test_a_redirected_ancestor_is_refused(self):
        runs = self.manager.records / "decomposition-runs"
        shutil.move(str(runs), str(self.outside))
        self.junction(runs, self.outside)
        self.receipt()
        with self.assertRaisesRegex(ValueError, "link or junction"):
            diagnose(self.manager, "NSC-088", run_id=RUN)

    def test_a_run_result_that_names_another_run_is_refused(self):
        result = json.loads((self.run_dir / "decomposition_run_result.json").read_text(encoding="utf-8"))
        result["run_id"] = "different"
        (self.run_dir / "decomposition_run_result.json").write_text(json.dumps(result), encoding="utf-8")
        self.receipt()
        with self.assertRaisesRegex(ValueError, "identity differs from its receipt"):
            diagnose(self.manager, "NSC-088", run_id=RUN)


if __name__ == "__main__":
    unittest.main()
