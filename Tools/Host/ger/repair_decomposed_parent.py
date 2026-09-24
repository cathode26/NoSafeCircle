#!/usr/bin/env python3
"""Add the decomposition forward-reference a historically-decomposed parent lacks.

WHY THIS EXISTS RATHER THAN AN ALLOW-LIST ON THE COMMITTERS
-----------------------------------------------------------
No GER committer may ADD a top-level key -- `contract_commit.py:220` and the
same invariant at `apply_followup_revision.py:149`, `ger_decision_revision.py:83`
and `new_task_commit.py:122`. Five agreeing enforcement points are a deliberate
invariant: `decomposition_children` and `decomposition_requirement_sha256` are
written ONLY by the decomposition apply path, which computes them atomically
from verified state.

NSC-026 was decomposed before that path existed, so it sits in a state the tools
cannot express: four real children, no forward reference, no way to add one, and
`non_executable_contract` forever.

Widening the committers would let an AUTHOR declare children that do not match
the contracts on disk -- the one error the invariant exists to prevent -- for
every contract, forever, to fix one historical task. **This command cannot lie,
because it DERIVES every field from committed state and refuses to overwrite.**

    decomposition_children            scanned: contracts whose `parent` is this task
    decomposition_requirement_sha256  aggregate_requirement_sha256(task), a pure
                                      function; current_conformance.py:285
                                      RECOMPUTES it to compare, so a wrong value
                                      cannot survive
    kind -> feature                   required by current_conformance.py:273

IT IS A REPAIR, NOT AN EDIT. It refuses when either field is already present, so
it can never rewrite an existing decomposition -- only supply a missing forward
reference. Run it with --commit; without, it is a dry run that writes nothing.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

REPO_DEFAULT = pathlib.Path(__file__).resolve().parents[3]
TARGET_KEYS = ("decomposition_children", "decomposition_requirement_sha256")


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True, help="the decomposed PARENT task id")
    parser.add_argument("--repo", type=pathlib.Path, default=REPO_DEFAULT)
    parser.add_argument("--reason", required=True, help="recorded in the commit message")
    parser.add_argument("--role", default="GER Agent",
                        help="recorded in the shared main-write journal")
    parser.add_argument("--commit", action="store_true",
                        help="write and commit; omit for a dry run that writes nothing")
    args = parser.parse_args()

    repo: pathlib.Path = args.repo.resolve()
    tasks = repo / "Tasks"
    path = tasks / f"{args.task}.yaml"
    if not path.is_file():
        raise SystemExit(f"no contract at {path}")

    # Replicate the module's OWN import path, not just the package root:
    # decomposition_graph_semantics does `from work_graph_validate import ...`,
    # a bare import that only resolves with Pipeline/TaskGraph on sys.path.
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo / "Pipeline" / "TaskGraph"))
    from Pipeline.TaskGraph.decomposition_graph_semantics import aggregate_requirement_sha256

    # Scoped to what this command WRITES. A tree-wide check refuses on unrelated
    # work -- including this script itself before it is committed -- while a
    # dirty contract is the thing that would actually corrupt the repair.
    dirty = _git(repo, "status", "--porcelain", "--", "Tasks")
    if dirty:
        raise SystemExit(f"contracts are dirty; refusing to repair on top of them:\n{dirty}")

    task = _load(path)

    # ---- PRECONDITIONS. Each names its own reason, so a refusal is never generic.
    if task.get("decomposition_state") != "decomposed":
        raise SystemExit(
            f"{args.task} decomposition_state is {task.get('decomposition_state')!r}, "
            "not 'decomposed'; this repairs an ALREADY decomposed parent only")
    present = [key for key in TARGET_KEYS if key in task]
    if present:
        raise SystemExit(
            f"{args.task} already has {present}; this command ADDS a missing forward "
            "reference and never rewrites one. Use the decomposition apply path.")

    children = sorted(
        child["id"] for child in (_load(p) for p in sorted(tasks.glob("*.yaml")))
        if child.get("parent") == args.task and child.get("id")
    )
    if not children:
        raise SystemExit(
            f"no contract names {args.task} as its parent; there is nothing to "
            "reference and the decomposition_state is therefore wrong, not the keys")

    repaired = dict(task)
    repaired["kind"] = "feature"
    repaired["decomposition_children"] = children
    repaired["contract_revision"] = int(task.get("contract_revision", 0)) + 1
    # Computed AFTER the other fields, because it hashes the task it is stored on.
    repaired["decomposition_requirement_sha256"] = aggregate_requirement_sha256(repaired)

    print(f"{args.task}: kind {task.get('kind')!r} -> 'feature'")
    print(f"  decomposition_children           {children}")
    print(f"  decomposition_requirement_sha256 {repaired['decomposition_requirement_sha256']}")
    print(f"  contract_revision                {task.get('contract_revision')} -> "
          f"{repaired['contract_revision']}")

    # SANITY PROBE: recompute exactly as current_conformance.py:285 does. If these
    # ever disagree the gate would report needs_replan, so prove it here instead.
    if aggregate_requirement_sha256(repaired) != repaired["decomposition_requirement_sha256"]:
        raise SystemExit("the requirement hash is not stable over its own field")

    if not args.commit:
        print("\n[DRY RUN] nothing written. Re-run with --commit.")
        return 0

    # TAKE THE SHARED main-write LOCK, like every other committer here. The first
    # version did not, and `git add` + `git commit` commits WHATEVER IS STAGED --
    # so a concurrent agent with something staged elsewhere would have had its
    # work swept into this commit. Reported by the GER Agent after running it.
    sys.path.insert(0, str(repo / "Tools" / "Host" / "ger"))
    import main_write

    rel = f"Tasks/{args.task}.yaml"
    head = _git(repo, "rev-parse", "--verify", "HEAD")
    original = path.read_bytes()
    message = (f"taskgraph: supply {args.task} decomposition forward reference\n\n"
               f"{args.reason}\n\n"
               f"Derived from committed state, not authored: children {children} already\n"
               f"name {args.task} as parent, and decomposition_requirement_sha256 is\n"
               f"aggregate_requirement_sha256 of the repaired contract, which\n"
               f"current_conformance.py:285 recomputes to compare.\n")

    with main_write.transaction(
            f"{args.task} decomposition forward reference", head,
            repo=repo, role=args.role, journal=main_write.default_journal(repo),
            touched=[rel], expected_files={rel: original}):
        path.write_text(json.dumps(repaired, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        validate = subprocess.run(
            [sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"],
            cwd=str(repo), capture_output=True, text=True)
        if validate.returncode != 0:
            path.write_bytes(original)
            raise SystemExit("taskcontrol validate failed; restored the contract:\n"
                             + (validate.stdout + validate.stderr).strip()[-1200:])
        print("[VALIDATE] PASS")
        # `--only <path>` commits THAT PATH ALONE, whatever else is in the index.
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "--only",
                        "-m", message, "--", rel], check=True)
    print(f"committed {_git(repo, 'rev-parse', '--verify', 'HEAD')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
