#!/usr/bin/env python3
"""Regression tests for prefab_lint.py's line-ending check.

WHY THIS EXISTS. The original check was `b"\\r\\n" in raw`, which fails a file with UNIFORM CRLF
line endings exactly as hard as a genuinely MIXED one. On a host with `core.autocrlf=true` (this
one), every committed LF blob becomes CRLF on checkout, so a perfectly clean, unmodified checkout
of all 73 committed prefabs failed 73 of 73 on this check alone - a false failure the check's own
comment did not intend ("a MIXED file re-serializes").

These tests pin the corrected behaviour directly against `check_prefab`, not by shelling out and
re-parsing text output, so a regression back to the old any-CRLF check is caught by
`test_uniform_crlf_passes` and a regression that simply deletes the check is caught by
`test_mixed_endings_still_fails`. Run:

    python -B Tools/test_prefab_lint.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import prefab_lint  # noqa: E402


MINIMAL_PREFAB_LF = (
    "%YAML 1.1\n"
    "%TAG !u! tag:unity3d.com,2011:\n"
    "--- !u!1 &100000\n"
    "GameObject:\n"
    "  m_ObjectHideFlags: 0\n"
    "--- !u!4 &100001\n"
    "Transform:\n"
    "  m_ObjectHideFlags: 0\n"
)


class LineEndingChecks(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def _line_ending_failures(self, raw: bytes) -> list:
        """Just the line-ending-related failures from check_prefab, isolated from every other
        check this function also runs (guid resolution, YAML header, anchors, ...)."""
        path = pathlib.Path(self._tmp.name) / "probe.prefab"
        path.write_bytes(raw)
        meta = path.with_suffix(path.suffix + ".meta")
        meta.write_text("guid: 0123456789abcdef0123456789abcdef\n", encoding="utf-8")
        failures = prefab_lint.check_prefab(path, known_guids=set())
        return [f for f in failures if "line ending" in f or "CRLF" in f or " LF" in f]

    def test_uniform_crlf_passes(self):
        """THE REGRESSION THIS FIX ADDRESSES: a uniformly-CRLF file (what `core.autocrlf=true`
        produces from every committed LF blob) must NOT fail. Reverting to the old
        `b"\\r\\n" in raw` check makes this test fail."""
        raw = MINIMAL_PREFAB_LF.replace("\n", "\r\n").encode("utf-8")
        self.assertEqual(self._line_ending_failures(raw), [],
                          "a uniformly-CRLF file must pass the line-ending check")

    def test_uniform_lf_passes(self):
        raw = MINIMAL_PREFAB_LF.encode("utf-8")
        self.assertEqual(self._line_ending_failures(raw), [],
                          "a uniformly-LF file must pass the line-ending check")

    def test_mixed_endings_still_fails(self):
        """A GENUINELY mixed file (some lines CRLF, some bare LF) must still fail. Proves the fix
        narrowed the check to MIXED endings rather than removing the check entirely."""
        lines = MINIMAL_PREFAB_LF.split("\n")
        half = len(lines) // 2
        mixed = "\r\n".join(lines[:half]) + "\r\n" + "\n".join(lines[half:])
        raw = mixed.encode("utf-8")
        self.assertTrue(b"\r\n" in raw and b"\n" in raw.replace(b"\r\n", b""),
                         "fixture sanity: must actually contain both a CRLF and a bare LF")
        failures = self._line_ending_failures(raw)
        self.assertEqual(len(failures), 1, "a mixed-ending file must fail exactly once on this check")
        self.assertIn("mixes CRLF and bare LF", failures[0])

    def test_all_committed_prefabs_pass_line_ending_check(self):
        """The end-to-end acceptance count, run against the real repo tree this file lives in."""
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        assets = repo_root / "Assets"
        prefabs = [p for p in sorted(assets.rglob("*.prefab"))
                   if "Library" not in p.parts and "Temp" not in p.parts]
        self.assertGreater(len(prefabs), 0,
                           "sanity probe: enumeration must find authored prefabs")
        line_ending_failures = {}
        for prefab in prefabs:
            raw = prefab.read_bytes()
            has_crlf = b"\r\n" in raw
            has_bare_lf = b"\n" in raw.replace(b"\r\n", b"")
            if has_crlf and has_bare_lf:
                line_ending_failures[prefab.as_posix()] = "mixed"
        self.assertEqual(line_ending_failures, {},
                          "no committed prefab should have genuinely mixed line endings")


if __name__ == "__main__":
    unittest.main()
