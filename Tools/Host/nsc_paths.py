#!/usr/bin/env python
"""Where am I, and where is everything else - answered once for every host tool.

Before this module each tool invented its own answer and hardcoded this machine
into it: `ROOT=C:/nscrev/codex-jobs` in a shell script, `Path(__file__).parent`
in a prompt generator whose tracked and deployed copies then disagreed about
where the prompt lands, `sys.path.insert(0, r"C:\\nscrev\\ger-tools")` in a
validator. None of them can run from an F: checkout.

    workspace       the NSC home: docs, agent state, the deployed tools
    canonical       the git checkout
    work            the scratch area: job clones, reports, job records
    containing_repo the repository this file is part of, if any

**Only `work` reads the environment, and that is a deliberate refusal.**

The obvious design is an NSC_HOME variable for each root. It is wrong here, and
run_job.py already records why: a review on 2026-09-18 found that a production
caller could move FORBIDDEN_ROOT and CANONICAL somewhere harmless and then run a
read-write job against the real canonical checkout. The guards did exactly what
they were told, about the wrong paths. run_job closed that by ignoring its own
overrides outside NSC_RUN_JOB_TESTING=1 - which is also precisely why it cannot
relocate today.

So relocation cannot be bought with an environment variable, because these roots
are what the guards protect. It is bought by DERIVING them from where the tool
is installed: a deployed tool at <workspace>/tools/<family>/x.py knows its own
workspace, and a caller cannot move it without write access to the tool itself -
at which point the guard was never the barrier. Deploy the tools to F:/NSC/tools
and they protect F:/NSC, with nothing to configure and nothing to forget.

`work` is the exception that proves the rule. It is a SIBLING of the workspace
with an unrelated name (C:/NSC -> C:/nscrev), so no walk up from __file__ can
find it; it must be told. It also gates no refusal - it is where job output and
clones live, and --out already lets a caller choose that. NSC_WORK is therefore
configuration, not a hole.

`canonical` is searched for under the workspace rather than derived from this
file, because a tool running inside a job clone still needs the REAL checkout -
that clone is not it. containing_repo() answers the other question, "which
repository is this file part of", and the two are not interchangeable.

Silent misconfiguration is the remaining hazard, so every root records HOW it
was decided, describe() exposes that for telemetry, and require() fails loudly
naming each missing root rather than letting a tool operate on one that is not
there.
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["workspace", "canonical", "work", "containing_repo", "describe",
           "require", "Root"]

# The documented defaults: this machine, so nothing changes until the tools are
# deployed somewhere else. Recorded in Tools/Host/README.md's deployment table.
DEFAULT_WORKSPACE = Path(r"C:\NSC")
DEFAULT_WORK = Path(r"C:\nscrev")

_HERE = Path(__file__).resolve().parent  # .../Tools/Host, or .../tools deployed


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
    """The NSC home: docs, agent state and the deployed tool tree.

    Derived from where this file is installed, never from the environment. This
    is the root run_job.py's FORBIDDEN_ROOT protects, and a caller who can set a
    variable must not be able to move a guard. See the module docstring.
    """
    deployed = _deployed_workspace()
    if deployed is not None:
        return Root(deployed, "derived from this file's deployed location")
    return Root(DEFAULT_WORKSPACE, "documented default")


def canonical() -> Root:
    """The installation's canonical git checkout.

    Not from the environment, for the same reason as workspace(): run_job.py
    refuses to use this path as a job clone, so moving it re-permits a
    read-write job in the live checkout.

    Not derived from this file either: a tool running inside a job clone still
    needs the real checkout. The two known layouts are tried in order -
    <workspace>/NSC/NoSafeCircle on this machine, and <workspace>/NoSafeCircle,
    which the F: validation checkout uses. If neither exists the machine's
    layout is returned so an error names a real path instead of guessing.
    """
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
    lives outside any checkout. For a tool that operates on its own repository -
    a linter, a test runner - this is the right root and canonical() is not. It
    is also worth refusing: a job clone should never be the repository the tool
    itself is running from. Returns None rather than guessing, so a caller has
    to decide what to do when there is no containing repository.
    """
    tracked = _tracked_repo_root()
    if tracked is None:
        return None
    return Root(tracked, "derived from this file's tracked location")


def work() -> Root:
    """The scratch area: job clones, reports and job records.

    The one root that reads the environment (NSC_WORK), because it cannot be
    derived - it is a sibling of the workspace with an unrelated name - and
    because it gates no refusal. Never derived, so an installation that moves
    must say where its scratch area went.
    """
    value = os.environ.get("NSC_WORK")
    if value and value.strip():
        return Root(Path(value.strip()), "environment NSC_WORK")
    return Root(DEFAULT_WORK, "documented default")


def describe() -> dict[str, dict[str, str]]:
    """Every root with the reason it resolved that way, for telemetry and --where.

    A tool that records this cannot be quietly pointed at the wrong drive: the
    reason travels with the value.
    """
    out = {}
    roots: list[tuple[str, Root | None]] = [
        ("workspace", workspace()), ("canonical", canonical()),
        ("work", work()), ("containing_repo", containing_repo()),
    ]
    for name, root in roots:
        if root is None:
            out[name] = {"path": "", "how": "not inside a checkout", "exists": "false"}
        else:
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
            "\nworkspace and canonical follow where the tools are deployed; "
            "deploy them under the installation root. NSC_WORK sets the "
            "scratch area."
        )
    return resolved


if __name__ == "__main__":
    import json
    print(json.dumps(describe(), indent=2))
