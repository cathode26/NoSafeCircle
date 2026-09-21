"""Tests for safe_delete.py (runbook rule 26).

Run:  python -B -m unittest discover -s tests -p "test_safe_delete.py"
      (from C:\\NSC\\tools\\cleanup)

These build real junctions with `mklink /J`, because the whole point of the guard
is behaviour that only reproduces against a real Windows reparse point.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safe_delete import (  # noqa: E402
    Refused,
    check_recursive_delete,
    depth_from_root,
    is_reparse,
    real_path,
    safe_rmtree,
)


def make_junction(link: Path, target: Path) -> None:
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       capture_output=True, text=True)
    if r.returncode != 0:  # pragma: no cover
        raise unittest.SkipTest(f"could not create junction: {r.stderr.strip()}")


def shallow_real_dirs():
    """A real directory at depth 1 and one of its children at depth 2.

    These tests need genuinely shallow paths that EXIST: one to point a junction
    at, one to chdir into. A temp directory is always deep, so it cannot serve.
    This used to hardcode C:/NSC, which is why the suite failed the first time CI
    ran it - the runner's workspace is D:/a/... and there is no C:/NSC there.

    SystemRoot is the portable answer on Windows: present on every install,
    always at depth 1. Its child is discovered rather than named, so this does
    not trade one hardcoded path for another.
    """
    root = Path(os.environ.get("SystemRoot") or r"C:\Windows")
    if not root.is_dir() or depth_from_root(root) != 1:
        raise unittest.SkipTest(f"no usable depth-1 directory: {root}")
    child = None
    try:
        for candidate in sorted(root.iterdir()):
            try:
                if candidate.is_dir() and not is_reparse(candidate):
                    child = candidate
                    break
            except OSError:
                continue  # unreadable entries are not our business
    except OSError as exc:
        raise unittest.SkipTest(f"cannot list {root}: {exc}")
    if child is None or depth_from_root(child) != 2:
        raise unittest.SkipTest(f"no usable depth-2 directory under {root}")
    return root, child


class Depth(unittest.TestCase):
    def test_depth_is_counted_from_the_drive_root(self):
        self.assertEqual(depth_from_root(r"C:\\"), 0)
        self.assertEqual(depth_from_root(r"C:\NSC"), 1)
        self.assertEqual(depth_from_root(r"C:\NSC\tools"), 2)
        self.assertEqual(depth_from_root(r"C:\NSC\tools\ger"), 3)
        self.assertEqual(depth_from_root(r"C:\NSC\tools\ger\next"), 4)

    def test_a_trailing_separator_does_not_change_depth(self):
        self.assertEqual(depth_from_root(r"C:\NSC\tools"),
                         depth_from_root("C:\\NSC\\tools\\"))

    def test_forward_slashes_count_the_same(self):
        self.assertEqual(depth_from_root("C:/NSC/tools"), 2)


class RefusesShallow(unittest.TestCase):
    def test_the_drive_root_is_refused(self):
        with self.assertRaises(Refused):
            check_recursive_delete(r"C:\\")

    def test_depth_one_is_refused(self):
        with self.assertRaises(Refused):
            check_recursive_delete(r"C:\NSC")

    def test_depth_two_is_refused(self):
        with self.assertRaises(Refused):
            check_recursive_delete(r"C:\NSC\tools")

    def test_depth_three_is_allowed(self):
        self.assertEqual(check_recursive_delete(r"C:\NSC\tools\ger"),
                         Path(r"C:\NSC\tools\ger"))

    def test_refusal_is_case_insensitive_like_windows(self):
        # C:\nsc* matching C:\NSC is the 09-18 near-miss. Depth cannot be fooled.
        for spelling in (r"c:\nsc", r"C:\NSC", r"C:\nSc"):
            with self.assertRaises(Refused):
                check_recursive_delete(spelling)

    def test_dot_dot_cannot_climb_out_of_a_legal_depth(self):
        with self.assertRaises(Refused):
            check_recursive_delete(r"C:\NSC\tools\ger\..\..")

    def test_the_message_names_the_depth_and_the_remedy(self):
        with self.assertRaises(Refused) as cm:
            check_recursive_delete(r"C:\NSC")
        msg = str(cm.exception)
        self.assertIn("depth 1", msg)
        self.assertIn("rule 26", msg)
        self.assertIn("Vincent", msg)


class JunctionsResolveBeforeTheDepthTest(unittest.TestCase):
    """The case the whole guard exists for."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="safedel-"))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_junction_at_a_legal_depth_pointing_shallow_is_REFUSED(self):
        deep = self.tmp / "a" / "b" / "c"
        deep.mkdir(parents=True)
        link = deep / "link_to_root"
        shallow, _ = shallow_real_dirs()   # depth 1, and it exists
        make_junction(link, shallow)
        self.assertGreaterEqual(depth_from_root(link), 3,
                                "the link itself must sit at a legal depth for this test")
        with self.assertRaises(Refused) as cm:
            check_recursive_delete(link)
        self.assertIn("junction or symlink", str(cm.exception))

    def test_os_path_islink_does_not_see_a_junction_but_is_reparse_does(self):
        target = self.tmp / "target"
        target.mkdir()
        link = self.tmp / "link"
        make_junction(link, target)
        self.assertFalse(os.path.islink(link), "documented trap: islink misses junctions")
        self.assertTrue(is_reparse(link), "is_reparse must catch what islink misses")

    def test_a_junction_AT_a_protected_depth_is_refused_even_if_it_points_deep(self):
        """The mirror of the case above, and the one the first suite missed.

        A link at C:\\<name> is depth 1. Resolving it may land somewhere deep and
        perfectly legal - but the thing being deleted still sits at depth 1, so
        rule 26 refuses it. Checking only the resolved target would allow it.

        Patched rather than built, because creating a real junction at the drive
        root to prove a point is exactly the kind of thing this guard exists to
        stop.
        """
        import safe_delete

        deep = self.tmp / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        original = safe_delete.real_path
        try:
            safe_delete.real_path = lambda p: deep          # type: ignore[assignment]
            with self.assertRaises(Refused) as cm:
                safe_delete.check_recursive_delete(r"C:\some-link-at-depth-one")
            self.assertIn("depth 1", str(cm.exception))
        finally:
            safe_delete.real_path = original                # type: ignore[assignment]

    def test_real_path_follows_the_junction(self):
        target = self.tmp / "target"
        target.mkdir()
        link = self.tmp / "link"
        make_junction(link, target)
        self.assertEqual(real_path(link), real_path(target))

    def test_deleting_a_junction_removes_the_link_and_spares_the_target(self):
        canary = self.tmp / "CANARY"
        canary.mkdir()
        (canary / "precious.txt").write_text("must survive", encoding="utf-8")
        deep = self.tmp / "a" / "b" / "c"
        deep.mkdir(parents=True)
        link = deep / "link"
        make_junction(link, canary)

        rep = safe_rmtree(link, apply=True)
        self.assertTrue(rep["applied"])
        self.assertIn("unlink", rep["action"])
        self.assertFalse(link.exists())
        self.assertTrue((canary / "precious.txt").exists(),
                        "the junction target must never be touched")


class ActuallyDeletes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="safedel-"))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_dry_run_deletes_nothing(self):
        victim = self.tmp / "x" / "y" / "victim"
        victim.mkdir(parents=True)
        (victim / "f.txt").write_text("hi", encoding="utf-8")
        rep = safe_rmtree(victim, apply=False)
        self.assertFalse(rep["applied"])
        self.assertTrue(victim.exists(), "dry run must not delete")

    def test_apply_deletes_at_a_legal_depth(self):
        victim = self.tmp / "x" / "y" / "victim"
        (victim / "sub").mkdir(parents=True)
        (victim / "sub" / "f.txt").write_text("hi", encoding="utf-8")
        rep = safe_rmtree(victim, apply=True)
        self.assertTrue(rep["applied"])
        self.assertFalse(victim.exists())

    def test_a_missing_path_is_reported_not_crashed(self):
        rep = safe_rmtree(self.tmp / "x" / "y" / "never-existed", apply=True)
        self.assertFalse(rep["applied"])
        self.assertEqual(rep["action"], "nothing to delete")

    def test_a_missing_but_SHALLOW_path_is_still_refused(self):
        # absence must not read as permission
        with self.assertRaises(Refused):
            safe_rmtree(r"C:\this-root-does-not-exist", apply=True)


class RelativeAndOddPaths(unittest.TestCase):
    def test_a_relative_path_is_resolved_before_the_check(self):
        shallow, child = shallow_real_dirs()
        cwd = os.getcwd()
        try:
            os.chdir(shallow)                      # depth 1
            with self.assertRaises(Refused):
                check_recursive_delete(child.name)  # depth 2, refused
        finally:
            os.chdir(cwd)

    def test_a_rootless_path_is_refused_rather_than_guessed(self):
        with self.assertRaises(Refused):
            depth_from_root_no_anchor()


def depth_from_root_no_anchor():
    from pathlib import PureWindowsPath
    import safe_delete
    # force the no-anchor branch without depending on cwd
    original = os.path.abspath
    try:
        os.path.abspath = lambda p: "relative\\thing"        # type: ignore[assignment]
        return safe_delete.depth_from_root("relative/thing")
    finally:
        os.path.abspath = original                            # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main(verbosity=2)
