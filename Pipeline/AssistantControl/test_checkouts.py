"""Component regressions for isolated checkouts; no providers or Unity invoked."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl import test_inspect_project as fixture


class CheckoutTests(unittest.TestCase):
    setUp = fixture.InventoryTests.setUp
    run_git = fixture.InventoryTests.run_git

    def manager(self):
        contract = json.loads(self.contract.read_text())
        contract["contract_disposition"] = "active"
        self.contract.write_text(json.dumps(contract))
        self.run_git("add", "Tasks/NSC-042.yaml")
        self.run_git("commit", "-m", "Activate fixture")
        parent = tempfile.TemporaryDirectory()
        self.addCleanup(parent.cleanup)
        return Checkouts(self.root, Path(parent.name) / "Checkouts")

    def test_isolated_checkout_pins_committed_files_and_preserves_dirty_source(self):
        manager = self.manager()
        (self.root / "wall file.txt").write_text("operator work")
        before_index = (self.root / ".git/index").read_bytes()
        before_head = self.run_git("rev-parse", "HEAD").decode().strip()
        result = manager.prepare("NSC-042")
        checkout = Path(result["checkout"])
        self.assertEqual("NSC-042", checkout.name)
        self.assertEqual(before_head, result["current_commit"])
        self.assertEqual("old\n", (checkout / "wall file.txt").read_text())
        self.assertEqual("operator work", (self.root / "wall file.txt").read_text())
        self.assertEqual(before_index, (self.root / ".git/index").read_bytes())
        self.assertFalse(result["execution_authorized"])
        self.assertIsNone(result["approval"])

    def test_repeat_preparation_preserves_worker_edits(self):
        manager = self.manager()
        first = manager.prepare("NSC-042")
        target = Path(first["checkout"]) / "wall file.txt"
        target.write_text("worker edit")
        second = manager.prepare("NSC-042")
        self.assertEqual(first["checkout"], second["checkout"])
        self.assertEqual("worker edit", target.read_text())
        self.assertEqual("wall file.txt", second["local_changes"][0]["path"])

    def test_owned_checkout_can_be_cloned_for_candidate_validation(self):
        manager = self.manager()
        checkout = Path(manager.prepare("NSC-042")["checkout"])
        hooks = subprocess.run(
            ("git", "-C", str(checkout), "config", "--local", "--get-all", "core.hooksPath"),
            capture_output=True, check=False,
        )
        self.assertEqual(1, hooks.returncode, hooks.stderr.decode(errors="replace"))
        validation = manager.root / "validation-clone"
        cloned = subprocess.run(
            ("git", "clone", "--no-local", "--no-hardlinks", "--no-checkout",
             str(checkout), str(validation)),
            capture_output=True, check=False,
        )
        self.assertEqual(0, cloned.returncode, cloned.stderr.decode(errors="replace"))

    def test_foreign_directory_is_never_adopted(self):
        manager = self.manager()
        existing = manager.root / "NSC-042"
        existing.mkdir(parents=True)
        (existing / "keep.txt").write_text("do not touch")
        with self.assertRaisesRegex(ValueError, "not owned"):
            manager.prepare("NSC-042")
        self.assertEqual("do not touch", (existing / "keep.txt").read_text())

    def test_finish_before_receipt_recovers_only_exact_clean_checkout(self):
        manager = self.manager()
        result = manager.prepare("NSC-042")
        receipt = manager.records / "NSC-042.json"
        record = json.loads(receipt.read_text())
        record["status"] = "preparing"
        receipt.write_text(json.dumps(record))
        self.assertEqual("prepared", manager.prepare("NSC-042")["status"])
        receipt.write_text(json.dumps(record))
        (Path(result["checkout"]) / "wall file.txt").write_text("changed after crash")
        with self.assertRaisesRegex(ValueError, "local changes"):
            manager.prepare("NSC-042")

    def test_source_directory_cannot_contain_checkouts(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            Checkouts(self.root, self.root / "Checkouts")

    def test_stale_source_request_does_not_create_task_checkout(self):
        manager = self.manager()
        with self.assertRaisesRegex(ValueError, "changed since inspection"):
            manager.prepare("NSC-042", expected_commit="0" * 40)
        self.assertFalse((manager.root / "NSC-042").exists())
        self.assertFalse((manager.records / "NSC-042.json").exists())

    def test_cli_returns_exact_checkout_as_json(self):
        import contextlib
        import io
        from Pipeline.AssistantControl.__main__ import main
        manager = self.manager()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([
                "--source", str(self.root), "--checkout-root", str(manager.root),
                "prepare", "NSC-042", "--source-commit",
                self.run_git("rev-parse", "HEAD").decode().strip(),
            ])
        self.assertEqual(0, exit_code)
        result = json.loads(output.getvalue())
        self.assertEqual(str(manager.root / "NSC-042"), result["checkout"])
        self.assertFalse(result["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
