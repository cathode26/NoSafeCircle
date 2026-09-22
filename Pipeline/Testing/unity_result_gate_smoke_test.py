"""The Unity runner's result gate, exercised against synthetic NUnit XML.

WHAT THIS DOES AND DOES NOT PROVE. It extracts the decision block from the REAL
run_unity_tests_clean.ps1 by anchor and executes that text, so editing the
script changes what is tested. It does NOT run the whole script, so it proves
the decision, not the Unity launch, the hygiene pass or the manifest.

A test that transcribed the block into its own fixture would pass forever while
the script drifted underneath it -- the failure this repository has hit often
enough to have a name.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PS1 = ROOT / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
START = '    if ($failed -ne 0) {'
END = '    if ($total -le 0) {'


def _decision_block() -> str:
    text = PS1.read_text(encoding="utf-8-sig")
    start = text.find(START)
    end = text.find(END, start)
    if start < 0 or end < 0:
        raise AssertionError(
            "result-gate anchors not found in run_unity_tests_clean.ps1; "
            "the block moved and this test must be re-anchored rather than deleted"
        )
    return text[start:end]


def _xml(total: int, passed: int, failed: int, skipped: int, result: str,
         ignored: tuple[str, ...] = ()) -> str:
    cases = "".join(
        f'<test-case fullname="{name}" result="Skipped" label="Ignored" />'
        for name in ignored
    )
    return (
        f'<test-run total="{total}" passed="{passed}" failed="{failed}" '
        f'skipped="{skipped}" result="{result}">{cases}</test-run>'
    )


class UnityResultGateTests(unittest.TestCase):
    """NSC-044 materialized with 14 passed, 0 failed, 1 explicitly ignored."""

    def decide(self, xml: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "results.xml"
            path.write_text(xml, encoding="utf-8")
            script = (
                'function Stop-WithCode { param($code, $message) '
                'Write-Host $message; exit 9 }\n'
                '$ExitResult = 9\n'
                f'[xml]$resultDocument = Get-Content -LiteralPath "{path}" -Raw\n'
                '$testRun = $resultDocument.SelectSingleNode("/test-run")\n'
                '$total = [int]$testRun.GetAttribute("total")\n'
                '$passed = [int]$testRun.GetAttribute("passed")\n'
                '$failed = [int]$testRun.GetAttribute("failed")\n'
                '$skipped = [int]$testRun.GetAttribute("skipped")\n'
                '$result = $testRun.GetAttribute("result")\n'
                + _decision_block()
                + '\nWrite-Host "GATE ACCEPTED"\n'
            )
            script_path = pathlib.Path(raw) / "gate.ps1"
            script_path.write_text(script, encoding="utf-8")
            done = subprocess.run(
                ("powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", str(script_path)),
                capture_output=True,
            )
            return done.returncode, done.stdout.decode(errors="replace")

    def test_nsc044_shape_is_accepted(self):
        """14 passed, 0 failed, one opt-in visual capture ignored."""
        code, out = self.decide(_xml(
            15, 14, 0, 1, "Skipped:Ignored",
            ("NoSafeCircle.RuinedEntrySceneTests.CaptureGameplayCameraReview",)))
        self.assertEqual(0, code, out)
        self.assertIn("GATE ACCEPTED", out)

    def test_the_ignored_test_is_named_in_the_output(self):
        """A skip invisible in the record is how opt-in becomes never-runs."""
        _code, out = self.decide(_xml(
            15, 14, 0, 1, "Skipped:Ignored",
            ("NoSafeCircle.RuinedEntrySceneTests.CaptureGameplayCameraReview",)))
        self.assertIn("CaptureGameplayCameraReview", out)

    def test_all_passing_is_still_accepted(self):
        code, out = self.decide(_xml(15, 15, 0, 0, "Passed"))
        self.assertEqual(0, code, out)

    def test_a_failing_test_is_still_refused(self):
        code, out = self.decide(_xml(15, 13, 1, 1, "Failed"))
        self.assertEqual(9, code, out)
        self.assertIn("failed test", out)

    def test_everything_ignored_is_REFUSED(self):
        """The degenerate case a blanket accept-skips rule would have created.

        failed=0, total>0, result="Skipped:Ignored" -- and not one test ran.
        This is why the change adds `passed > 0` rather than only widening the
        accepted labels.
        """
        code, out = self.decide(_xml(15, 0, 0, 15, "Skipped:Ignored"))
        self.assertEqual(9, code, out)
        self.assertIn("zero passed tests", out)

    def test_an_unexpected_label_is_still_refused(self):
        for label in ("Inconclusive", "Cancelled", "Error"):
            with self.subTest(label=label):
                code, out = self.decide(_xml(15, 14, 0, 1, label))
                self.assertEqual(9, code, out)


if __name__ == "__main__":
    unittest.main()
