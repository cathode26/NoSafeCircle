"""Refuse recursive deletes near the drive root. Runbook rule 26.

Vincent, 2026-09-20: "just make it a rule there is no recursive delete allowed on
any folder 1 or 2 directories deep from C".

Depth is counted from the drive root:

    C:\\                    depth 0   refused
    C:\\NSC                 depth 1   refused
    C:\\NSC\\tools           depth 2   refused
    C:\\NSC\\tools\\ger       depth 3   allowed

Deleting at depth 0-2 is Vincent's to execute by hand, not an agent's.

Two things this gets right that a hand-rolled check does not:

1.  **Junctions are resolved before the depth test.** A junction at depth 4 can
    point at depth 1, and the delete lands on the target, not the link. Six live
    junctions under C:\\nscrev point into C:\\NSC\\tools today.

2.  **`os.path.islink()` returns False for a Windows junction** - measured on
    Python 3.13, 2026-09-20. A guard written the obvious way misses every
    junction on this machine. Use `Path.is_junction()` (3.12+) and `realpath`.

Why depth rather than a list of protected names: name matching fails on Windows.
`C:\\nsc*` matches `C:\\NSC` case-insensitively, which nearly moved the whole
workspace on 2026-09-18. Depth cannot be fooled by capitalisation, by a typo, or
by a folder created after this rule was written, and it needs no maintenance.

Library:

    from safe_delete import check_recursive_delete, safe_rmtree, Refused
    check_recursive_delete(p)        # raises Refused, or returns the resolved path
    safe_rmtree(p, apply=True)       # checks, then deletes

CLI (dry run unless --apply):

    python -B safe_delete.py <path> [<path> ...]
    python -B safe_delete.py <path> --apply
    python -B safe_delete.py --check <path>      # exit 0 allowed, 3 refused
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path, PureWindowsPath

MIN_ALLOWED_DEPTH = 3


class Refused(Exception):
    """A delete this tool will not perform. The message says what to do instead."""


def real_path(p: str | os.PathLike) -> Path:
    """The path a delete would actually land on, with junctions resolved.

    `Path.resolve()` follows junctions as well as symlinks, which is what we
    want: the depth test must apply to the target, not to the link.
    """
    return Path(os.path.realpath(os.fspath(p)))


def is_reparse(p: str | os.PathLike) -> bool:
    """True for a junction OR a symlink. Both, because neither check catches both.

    `os.path.islink()` is False for a junction on Windows; `Path.is_junction()`
    is False for a symlink. Measured 2026-09-20.
    """
    q = Path(p)
    try:
        junction = q.is_junction()  # Python 3.12+
    except AttributeError:  # pragma: no cover - older interpreters
        junction = False
    return bool(junction or q.is_symlink() or os.path.islink(q))


def depth_from_root(p: str | os.PathLike) -> int:
    """Directories below the drive or share root. `C:\\` is 0, `C:\\NSC` is 1.

    Raises Refused for a path with no recognisable root, because a depth we
    cannot compute must never read as "deep enough".
    """
    q = PureWindowsPath(os.path.abspath(os.fspath(p)))
    if not q.anchor:
        raise Refused(f"{q} has no drive or share root, so its depth cannot be "
                      "determined. Pass an absolute path.")
    parts = [seg for seg in q.parts[1:] if seg not in ("", os.sep)]
    return len(parts)


def check_recursive_delete(p: str | os.PathLike) -> Path:
    """Return the resolved path if a recursive delete is allowed, else raise Refused."""
    given = Path(os.path.abspath(os.fspath(p)))
    resolved = real_path(given)

    via_link = resolved != given
    for label, candidate in (("the path given", given), ("its real target", resolved)):
        depth = depth_from_root(candidate)
        if depth < MIN_ALLOWED_DEPTH:
            detail = ""
            if via_link and candidate == resolved:
                detail = (f"\n  {given}\n  is a junction or symlink pointing at\n  {resolved}\n"
                          "  The delete would land on the target, not the link.")
            raise Refused(
                f"REFUSED: recursive delete of {candidate} - {label} is depth {depth}, "
                f"and rule 26 allows recursive delete only at depth {MIN_ALLOWED_DEPTH} "
                f"or deeper.{detail}\n"
                f"  Depth is counted from the drive root: C:\\ is 0, C:\\NSC is 1, "
                f"C:\\NSC\\tools is 2.\n"
                f"  Deleting at depth 0-2 is Vincent's to execute by hand. Either ask him, "
                f"or delete the specific children you mean at depth "
                f"{MIN_ALLOWED_DEPTH} or deeper."
            )
    return resolved


def safe_rmtree(p: str | os.PathLike, *, apply: bool = False) -> dict:
    """Check rule 26, then recursively delete. Dry run unless apply=True."""
    given = Path(os.path.abspath(os.fspath(p)))
    resolved = check_recursive_delete(given)

    report = {
        "path": str(given),
        "resolved": str(resolved),
        "depth": depth_from_root(resolved),
        "is_reparse_point": is_reparse(given),
        "exists": given.exists() or is_reparse(given),
        "applied": False,
        "action": None,
    }

    if not report["exists"]:
        report["action"] = "nothing to delete"
        return report

    # A junction at an allowed depth: remove the LINK, never its contents.
    if report["is_reparse_point"]:
        report["action"] = "unlink reparse point (target left untouched)"
        if apply:
            os.rmdir(given) if given.is_dir() else given.unlink()
            report["applied"] = True
        return report

    report["action"] = "recursive delete"
    report["rmtree_avoids_symlink_attacks"] = bool(
        getattr(shutil.rmtree, "avoids_symlink_attacks", False))
    if apply:
        # Look again, immediately before the delete. The first check happened
        # before this report was built, and an ancestor junction retargeted in
        # between would change what `given` resolves to without changing `given`.
        # Astra's 2026-09-20 review found that window.
        #
        # What this check is worth, stated accurately, because an earlier version
        # of this comment was not (Astra round 2, finding 3):
        #
        # It catches a retarget that landed while the report was assembled. It
        # does NOT narrow the window to "the gap before one syscall" - there is no
        # one syscall. shutil.rmtree takes the non-fd branch here
        # (avoids_symlink_attacks is False on Windows, os.supports_dir_fd is
        # empty) and issues one os.rmdir/os.unlink per entry, each resolving from
        # the drive root through whatever the ancestor points at AT THAT INSTANT.
        # On a tree the size of C:/nscrev/codex-jobs that runs for minutes. This
        # check covers the first microseconds of it.
        #
        # It is also a STRING comparison, so it is blind to a rename-swap: the
        # same path re-created as a different directory reads as unchanged.
        #
        # And the sentence this comment used to end on - that anyone able to
        # retarget an ancestor already holds write access and needs no help from
        # this tool - is a permission argument answering a question nobody asked.
        # Permission to retarget an ancestor does not imply permission to delete
        # what it points at. More to the point, rule 26 exists for ACCIDENTS, and
        # an accident does not do the damage directly - it does it through
        # whichever tool is mid-operation. Eight concurrent agents, six live
        # junctions and a scripted recreate drill are enough; no adversary is
        # required.
        #
        # The fix is known and is not this: delete `resolved` rather than `given`,
        # so every junction is already resolved for the whole operation, and pin a
        # directory handle across the delete. Design, with nine behavioural tests
        # and eight mutations:
        # C:/nscrev/reports/handoffs/fable-safe-delete-toctou-design-20260920.md
        again = check_recursive_delete(given)
        if again != resolved:
            raise Refused(
                f"{given} resolved to {resolved} when it was checked and to "
                f"{again} a moment later. Something re-pointed a link underneath "
                "this operation; nothing was deleted.")
        shutil.rmtree(given)
        report["applied"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="safe_delete.py",
        description="Recursive delete with runbook rule 26 enforced. Dry run by default.",
    )
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--apply", action="store_true",
                    help="actually delete; without this, only report what would happen")
    ap.add_argument("--check", action="store_true",
                    help="check only, delete nothing; exit 3 if any path is refused")
    args = ap.parse_args(argv)

    refused = 0
    for raw in args.paths:
        try:
            if args.check:
                resolved = check_recursive_delete(raw)
                print(f"ALLOWED  depth {depth_from_root(resolved)}  {resolved}")
                continue
            rep = safe_rmtree(raw, apply=args.apply)
            verb = "DELETED " if rep["applied"] else "would   "
            print(f"{verb} depth {rep['depth']}  {rep['action']}  {rep['path']}")
            if rep["resolved"] != rep["path"]:
                print(f"         -> resolves to {rep['resolved']}")
        except Refused as e:
            refused += 1
            print(str(e), file=sys.stderr)

    if refused:
        return 3
    if not args.apply and not args.check:
        print("\n(dry run - nothing deleted. Pass --apply to delete.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
