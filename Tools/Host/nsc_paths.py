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
walking up from __file__ finds it; it has to be told. `canonical` is searched
for under the workspace rather than derived from this file, because a tool
running inside a job clone still needs the REAL checkout - that clone is not it.
containing_repo() answers the other question, "which repository is this file
part of", and the two are not interchangeable.

Resolution order: an explicit environment variable first, then whatever that
root can honestly work out for itself, then the documented default.

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

__all__ = ["workspace", "canonical", "work", "containing_repo", "describe",
           "require", "Root"]

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
    """The installation's canonical git checkout.

    Deliberately NOT derived from this file's own location. run_job.py uses
    this as the source that job clones are cloned FROM, so when it runs out
    of a clone it still needs the real canonical checkout - "the repo I happen
    to live in" would quietly make a clone its own source. Use
    containing_repo() when you do want the repository this file belongs to.

    The two known layouts are tried in order: <workspace>/NSC/NoSafeCircle on
    this machine, and <workspace>/NoSafeCircle, which the F: validation
    checkout uses. If neither exists the machine's layout is returned so the
    error names a real path instead of guessing.
    """
    found = _from_env("NSC_CANONICAL")
    if found is not None:
        return found
    home = workspace().path
    doubled, flat = home / "NSC" / "NoSafeCircle", home / "NoSafeCircle"
    if doubled.exists():
        return Root(doubled, "found under the workspace")
    if flat.exists():
        return Root(flat, "found under the workspace")
    return Root(doubled, "assumed under the workspace - does not exist")


def containing_repo() -> Root | None:
    """The repository this file is part of, or None when it is deployed.

    The tracked copy lives at <repo>/Tools/Host/nsc_paths.py; a deployed copy
    lives outside any checkout. For a tool that operates on its own repository
    - a linter, a test runner - this is the right root, and canonical() is
    not. Returns None rather than guessing, so a caller has to decide what to
    do when there is no containing repository.
    """
    tracked = _tracked_repo_root()
    if tracked is None:
        return None
    return Root(tracked, "derived from this file's tracked location")


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
