"""Tests for resolve_codex.py, covering the two traps audit 20260920-143913 found.

Portable on purpose: no host paths, no real Codex install, no provider calls. Fake binaries are
tiny .py files, which resolve_codex runs through the current interpreter.

Run:  python -B -m unittest discover -s tests -p "test_resolve_codex.py"   (from C:\\NSC\\tools\\jobs)
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resolve_codex import NoCodex, candidates, resolve, version_key  # noqa: E402


def fake_codex(folder: Path, version: str | None) -> Path:
    """A folder that either holds a fake 'codex.exe' printing `version`, or holds nothing."""
    folder.mkdir(parents=True, exist_ok=True)
    if version is None:
        (folder / "README.txt").write_text("no binary here", encoding="utf-8")
        return folder
    exe = folder / "codex.exe.py"
    exe.write_text(f'print("codex-cli {version}")\n', encoding="utf-8")
    return exe


class VersionOrdering(unittest.TestCase):
    def test_plain_semver_orders_numerically(self):
        self.assertLess(version_key("0.151.0"), version_key("0.155.0"))
        self.assertLess(version_key("0.9.0"), version_key("0.10.0"))

    def test_prerelease_sorts_below_its_release(self):
        self.assertLess(version_key("0.155.0-alpha.9.2"), version_key("0.155.0"))

    def test_prereleases_order_by_their_own_numbers(self):
        """The exact pair the audit reproduced as colliding."""
        self.assertLess(version_key("0.155.0-alpha.2.6"), version_key("0.155.0-alpha.9.2"))

    def test_the_colliding_pair_no_longer_ties(self):
        self.assertNotEqual(version_key("0.155.0-alpha.2.6"), version_key("0.155.0-alpha.9.2"))

    def test_a_newer_release_beats_any_prerelease_of_an_older_one(self):
        self.assertLess(version_key("0.155.0-alpha.9.2"), version_key("0.156.0"))

    def test_a_short_version_is_padded_not_rejected(self):
        self.assertEqual(version_key("1.2")[:3], (1, 2, 0))


class Discovery(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rescodex-"))
        self.addCleanup(self._clean)
        self._saved = {k: os.environ.get(k) for k in ("NSC_CODEX_EXE", "NSC_CODEX_EXE_NAME")}
        os.environ.pop("NSC_CODEX_EXE", None)
        os.environ["NSC_CODEX_EXE_NAME"] = "codex.exe.py"
        import resolve_codex
        resolve_codex.EXE_NAME = "codex.exe.py"

    def _clean(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import resolve_codex
        resolve_codex.EXE_NAME = os.environ.get("NSC_CODEX_EXE_NAME", "codex.exe")

    def test_a_folder_without_the_binary_is_skipped(self):
        """Trap 1: at least one real hash folder on this host has no codex.exe."""
        fake_codex(self.tmp / "aaa_empty", None)
        fake_codex(self.tmp / "bbb_real", "0.155.0-alpha.9.2")
        found = candidates(self.tmp)
        self.assertEqual(len(found), 1)
        self.assertIn("bbb_real", str(found[0][2]))

    def test_the_newest_prerelease_wins_not_the_first_directory(self):
        """Trap 2: 'aaa' sorts first on the filesystem but is the older build."""
        fake_codex(self.tmp / "aaa", "0.155.0-alpha.2.6")
        fake_codex(self.tmp / "zzz", "0.155.0-alpha.9.2")
        self.assertIn("zzz", str(resolve(self.tmp)))

    def test_filesystem_order_does_not_decide_when_versions_tie_in_prefix(self):
        fake_codex(self.tmp / "zzz", "0.155.0-alpha.2.6")
        fake_codex(self.tmp / "aaa", "0.155.0-alpha.9.2")
        self.assertIn("aaa", str(resolve(self.tmp)))

    def test_a_release_beats_a_prerelease(self):
        fake_codex(self.tmp / "pre", "0.155.0-alpha.9.2")
        fake_codex(self.tmp / "rel", "0.155.0")
        self.assertIn("rel", str(resolve(self.tmp)))

    def test_no_usable_binary_raises_rather_than_returning_something(self):
        fake_codex(self.tmp / "empty1", None)
        fake_codex(self.tmp / "empty2", None)
        with self.assertRaises(NoCodex):
            resolve(self.tmp)

    def test_a_missing_bin_root_raises(self):
        with self.assertRaises(NoCodex):
            resolve(self.tmp / "does-not-exist")

    def test_an_explicit_override_is_honoured(self):
        exe = fake_codex(self.tmp / "other", "0.1.0")
        os.environ["NSC_CODEX_EXE"] = str(exe)
        self.assertEqual(resolve(self.tmp), exe)

    def test_an_override_that_does_not_exist_is_refused_not_ignored(self):
        os.environ["NSC_CODEX_EXE"] = str(self.tmp / "nope.exe")
        with self.assertRaises(NoCodex):
            resolve(self.tmp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
