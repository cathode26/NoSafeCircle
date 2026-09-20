#!/usr/bin/env python
"""Where am I, and where is everything else - answered once for every host tool.

Before this module each tool invented its own answer and hardcoded this machine
into it: `ROOT=C:/nscrev/codex-jobs` in a shell script, `Path(__file__).parent`
in a prompt generator whose tracked and deployed copies then disagreed about
where the prompt lands, `sys.path.insert(0, r"C:\\nscrev\\ger-tools")` in a
validator. None of them can run from an F: checkout.

Three roots, and they are genuinely independent - you cannot derive one from
another:

    workspace   the NSC home: docs, agent state, the deployed tools
    canonical   the git checkout
    work        the scratch area: job clones, reports, job records

On this machine they are C:/NSC, C:/NSC/NSC/NoSafeCircle and C:/nscrev.
`work` is a SIBLING of `workspace` with an unrelated name, so no amount of
walking up from __file__ finds it; it has to be told. `canonical` usually can be
derived, but not always - the F: validation checkout is F:/NSC/NoSafeCircle,
with no doubled NSC - so derivation is a default, never an assumption.

Resolution order for each root: an explicit environment variable, then a
derivation from this file's own location, then the documented default.

**This is deployment configuration, not a test hook.** run_job.py's existing
NSC_RUN_JOB_* overrides are ignored unless NSC_RUN_JOB_TESTING=1, which is
correct for redirecting fixtures and is exactly why the tool cannot relocate:
in production its paths stay pinned to C:. These variables are honoured always,
because "which drive is the project on" is a property of the installation.

Silent misconfiguration is the real hazard here, not a malicious environment -
anyone who can set NSC_HOME can also pass --out. So every root records HOW it
was decided, `describe()` exposes that, and `require()` fails loudly rather than
letting a tool operate on a root that does not exist.
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["workspace", "canonical", "work", "describe", "require", "Root"]

# The documented defaults: this machine, so nothing changes until someone sets
# the environment. Recorded in Tools/Host/README.md's deployment table.
DEFAULT_WORKSPACE = Path(r"C:\NSC")
DEFAULT_WORK = Path(r"C:\nscrev")

_HERE = Path(__file__).resolve().parent  # .../Tools/Host or .../tools


class Root:
    """A resolved root and the reason it resolved that way."""

    __slots__ = ("path", "how")

    def __init__(self, path: Path, how: str):
        self.path = path
        self.how = how

    def __fspath__(self) -> str:
        return str(self.path)

    def __truediv__(self, other) -> Path:
        return self.path / other

    def __str__(self) -> str:
        return str(self.path)

    def __repr__(self) -> str:
        return f"Root({self.path!s}, how={self.how!r})"

    def __eq__(self, other) -> bool:
        return Path(os.fspath(other)) == self.path if other is not None else False

    def exists(self) -> bool:
        return self.path.exists()


def _from_env(name: str) -> Root | None:
    value = os.environ.get(name)
    if not value or not value.strip():
        return None
    return Root(Path(value.strip()), f"environment {name}")


def _tracked_repo_root() -> Path | None:
    """<repo> when this file is the tracked copy at <repo>/Tools/Host/nsc_paths.py."""
    if _HERE.name == "Host" and _HERE.parent.name == "Tools":
        return _HERE.parent.parent
    return None


def _deployed_workspace() -> Path | None:
    """<workspace> when this file is deployed at <workspace>/tools/nsc_paths.py."""
    if _HERE.name.lower() == "tools":
        return _HERE.parent
    return None


def workspace() -> Root:
    """The NSC home: docs, agent state and the deployed tool tree."""
    found = _from_env("NSC_HOME")
    if found is not None:
        return found
    deployed = _deployed_workspace()
    if deployed is not None:
        return Root(deployed, "derived from this file's deployed location")
    return Root(DEFAULT_WORKSPACE, "documented default")


def canonical() -> Root:
    """The git checkout.

    Derived from the tracked location when this file is running out of the
    repository, because that is unambiguous. Otherwise the two known layouts
    are tried in order - <workspace>/NSC/NoSafeCircle on this machine, and
    <workspace>/NoSafeCircle, which is what the F: validation checkout uses -
    and the first that exists wins. If neither exists the machine's layout is
    returned so the error names a real path instead of guessing.
    """
    found = _from_env("NSC_CANONICAL")
    if found is not None:
        return found
    tracked = _tracked_repo_root()
    if tracked is not None:
        return Root(tracked, "derived from this file's tracked location")
    home = workspace().path
    doubled, flat = home / "NSC" / "NoSafeCircle", home / "NoSafeCircle"
    if doubled.exists():
        return Root(doubled, "found under the workspace")
    if flat.exists():
        return Root(flat, "found under the workspace")
    return Root(doubled, "assumed under the workspace - does not exist")


def work() -> Root:
    """The scratch area: job clones, reports and job records.

    Never derived. It is a sibling of the workspace with an unrelated name, so
    an installation that moves must say where it went.
    """
    found = _from_env("NSC_WORK")
    if found is not None:
        return found
    return Root(DEFAULT_WORK, "documented default")


def describe() -> dict[str, dict[str, str]]:
    """Every root with the reason it resolved that way, for telemetry and --where.

    A tool that records this cannot be quietly pointed at the wrong drive: the
    reason travels with the value.
    """
    out = {}
    for name, root in (("workspace", workspace()), ("canonical", canonical()),
                       ("work", work())):
        out[name] = {"path": str(root.path), "how": root.how,
                     "exists": str(root.path.exists()).lower()}
    return out


def require(*names: str) -> dict[str, Path]:
    """Resolve the named roots, raising if any does not exist.

    Loud beats silent: a tool operating on a root that is not there should say
    which root, what it resolved to and how it decided, not fail later on a
    confusing path.
    """
    known = {"workspace": workspace, "canonical": canonical, "work": work}
    resolved, missing = {}, []
    for name in names:
        if name not in known:
            raise KeyError(f"unknown root {name!r}; known roots: {sorted(known)}")
        root = known[name]()
        resolved[name] = root.path
        if not root.path.exists():
            missing.append(f"  {name} = {root.path}  ({root.how})")
    if missing:
        raise FileNotFoundError(
            "these roots do not exist:\n" + "\n".join(missing) +
            "\nSet NSC_HOME, NSC_CANONICAL or NSC_WORK to point at this installation."
        )
    return resolved


if __name__ == "__main__":
    import json
    print(json.dumps(describe(), indent=2))
