"""Deterministically undo one exact, unconsumed D1C decomposition commit.

The inverse is intentionally narrower than a general Git revert.  It accepts
only the exact D1C commit at ``HEAD`` and proves both whole-graph identities
from the stored reviewed ``GraphDeltaPlan`` before creating one additive undo
commit.  Any later commit means another operation may depend on the children,
so automatic undo is refused.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "Pipeline"
TASK_GRAPH = PIPELINE / "TaskGraph"
for module_root in (ROOT, PIPELINE, TASK_GRAPH):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from apply_graph_delta import (
    GraphApplyRepositoryError,
    _approved_identity,
    _decode_output,
    _git,
    _git_text,
    _nul_paths,
    _repository_preflight,
    _require_no_commit_stage_hooks,
    _stored_authority,
)
from graph_delta import GraphDeltaPlan, _plan_payload, semantic_json_sha256
from persistent_work_graph import load_persistent_work_graph


class GraphDeltaUndoError(GraphApplyRepositoryError):
    """The exact decomposition commit cannot be undone safely."""


@dataclass(frozen=True)
class GraphDeltaUndoPlan:
    plan_id: str
    parent_task_id: str
    apply_commit: str
    source_commit: str
    apply_tree: str
    source_tree: str
    changed_paths: tuple[str, ...]
    source_graph_semantic_hash: str
    proposed_graph_semantic_hash: str


@dataclass(frozen=True)
class GraphDeltaUndoResult:
    status: str
    plan_id: str
    parent_task_id: str
    apply_commit: str
    source_commit: str
    undo_commit: str
    committed_paths: tuple[str, ...]


def _selector_from_plan(stored_graph_delta: GraphDeltaPlan) -> dict[str, object]:
    payload = stored_graph_delta.to_dict()
    summary = payload.get("parent_before_summary")
    if not isinstance(summary, dict):
        raise GraphDeltaUndoError(
            "stored graph delta omitted its original parent summary"
        )
    return {
        "task_id": summary.get("task_id"),
        "contract_revision": summary.get("contract_revision"),
        "contract_sha256": payload.get("parent_before_hash"),
    }


def _graph_hash(root: Path) -> str:
    try:
        graph = load_persistent_work_graph(root)
    except Exception as exc:
        raise GraphDeltaUndoError(f"persistent TaskGraph is invalid: {exc}") from exc
    return semantic_json_sha256(_plan_payload(graph.plan))


def _commit_graph_hash(root: Path, commit: str) -> str:
    with tempfile.TemporaryDirectory(prefix="nsc-d1c-undo-inspect-") as temporary:
        clone = Path(temporary) / "source"
        result = subprocess.run(
            (
                "git",
                "clone",
                "--no-local",
                "--no-hardlinks",
                "--no-checkout",
                str(root),
                str(clone),
            ),
            cwd=str(root.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise GraphDeltaUndoError(
                "could not create the isolated source-graph verifier: "
                + _decode_output(result.stderr)
            )
        checkout = _git(clone, "checkout", "--detach", commit)
        if checkout.returncode != 0:
            raise GraphDeltaUndoError(
                "could not inspect the D1C source commit: "
                + _decode_output(checkout.stderr)
            )
        return _graph_hash(clone)


def inspect_graph_delta_undo(
    target_root: Path,
    stored_graph_delta: GraphDeltaPlan,
    *,
    expected_head: str | None = None,
) -> GraphDeltaUndoPlan:
    """Build a read-only exact-head undo plan or fail before mutation."""

    root, head = _repository_preflight(Path(target_root))
    if expected_head is not None and head != expected_head:
        raise GraphDeltaUndoError(
            f"undo expected HEAD {expected_head}, but the repository is at {head}"
        )
    try:
        authority = _stored_authority(
            stored_graph_delta,
            _selector_from_plan(stored_graph_delta),
        )
    except Exception as exc:
        raise GraphDeltaUndoError(f"stored graph-delta authority is invalid: {exc}") from exc
    payload = stored_graph_delta.to_dict()
    proposed_hash = payload.get("proposed_graph_semantic_hash")
    if _graph_hash(root) != proposed_hash:
        raise GraphDeltaUndoError(
            "current whole TaskGraph does not exactly equal the decomposition plan; "
            "later graph work may depend on it"
        )

    expected_subject = (
        f"taskgraph: apply {authority.parent_task_id} decomposition {authority.plan_id}"
    )
    subject = _git_text(root, "show", "-s", "--format=%s", head)
    if subject != expected_subject:
        raise GraphDeltaUndoError(
            "HEAD is not the exact D1C decomposition commit; automatic undo refuses "
            "later dependent history"
        )
    parents = _git_text(root, "show", "-s", "--format=%P", head).split()
    if len(parents) != 1:
        raise GraphDeltaUndoError("D1C decomposition commit must have exactly one parent")
    source_commit = parents[0]
    if _commit_graph_hash(root, source_commit) != authority.source_graph_semantic_hash:
        raise GraphDeltaUndoError(
            "D1C commit parent does not match the reviewed plan's source graph"
        )
    changed_paths = tuple(
        sorted(
            _nul_paths(
                _git(
                    root,
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "-z",
                    head,
                ).stdout,
                "D1C changed paths",
            ),
            key=str.casefold,
        )
    )
    if not changed_paths:
        raise GraphDeltaUndoError("D1C decomposition commit has no changed paths")
    return GraphDeltaUndoPlan(
        plan_id=authority.plan_id,
        parent_task_id=authority.parent_task_id,
        apply_commit=head,
        source_commit=source_commit,
        apply_tree=_git_text(root, "rev-parse", f"{head}^{{tree}}"),
        source_tree=_git_text(root, "rev-parse", f"{source_commit}^{{tree}}"),
        changed_paths=changed_paths,
        source_graph_semantic_hash=authority.source_graph_semantic_hash,
        proposed_graph_semantic_hash=str(proposed_hash),
    )


def _create_undo_commit(root: Path, plan: GraphDeltaUndoPlan) -> str:
    _require_no_commit_stage_hooks(root)
    name, email = _approved_identity()
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
    )
    with tempfile.TemporaryDirectory(prefix="nsc-d1c-undo-empty-hooks-") as hooks:
        result = _git(
            root,
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "-c",
            "commit.gpgSign=false",
            "-c",
            f"core.hooksPath={hooks}",
            "commit",
            "--no-verify",
            "--no-gpg-sign",
            "-m",
            f"taskgraph: undo {plan.parent_task_id} decomposition {plan.plan_id}",
            environment=environment,
        )
    if result.returncode != 0:
        raise GraphDeltaUndoError(
            "could not commit the exact graph-delta inverse: "
            + _decode_output(result.stderr)
        )
    return _git_text(root, "rev-parse", "HEAD")


def undo_graph_delta(
    target_root: Path,
    stored_graph_delta: GraphDeltaPlan,
    *,
    expected_head: str | None = None,
) -> GraphDeltaUndoResult:
    """Create one additive inverse commit for an exact unconsumed D1C apply."""

    root = Path(target_root).resolve()
    plan = inspect_graph_delta_undo(
        root,
        stored_graph_delta,
        expected_head=expected_head,
    )
    try:
        result = _git(root, "revert", "--no-commit", plan.apply_commit)
        if result.returncode != 0:
            raise GraphDeltaUndoError(
                "exact decomposition inverse did not apply cleanly: "
                + _decode_output(result.stderr)
            )
        staged = tuple(
            sorted(
                _nul_paths(
                    _git(root, "diff", "--cached", "--name-only", "-z").stdout,
                    "staged undo paths",
                ),
                key=str.casefold,
            )
        )
        if staged != plan.changed_paths:
            raise GraphDeltaUndoError(
                "staged decomposition inverse path set differs from the D1C commit"
            )
        if _git_text(root, "diff", "--name-only", "--"):
            raise GraphDeltaUndoError("decomposition inverse produced unstaged changes")
        if _git_text(root, "ls-files", "--others", "--exclude-standard"):
            raise GraphDeltaUndoError("decomposition inverse produced untracked files")
        if _git_text(root, "write-tree") != plan.source_tree:
            raise GraphDeltaUndoError(
                "staged decomposition inverse does not restore the exact source tree"
            )
        if _graph_hash(root) != plan.source_graph_semantic_hash:
            raise GraphDeltaUndoError(
                "staged decomposition inverse does not restore the source TaskGraph"
            )
        undo_commit = _create_undo_commit(root, plan)
        if _git_text(root, "rev-parse", f"{undo_commit}^") != plan.apply_commit:
            raise GraphDeltaUndoError("undo commit parent is not the exact D1C commit")
        if _git_text(root, "rev-parse", f"{undo_commit}^{{tree}}") != plan.source_tree:
            raise GraphDeltaUndoError("undo commit tree does not equal the D1C source tree")
        if _graph_hash(root) != plan.source_graph_semantic_hash:
            raise GraphDeltaUndoError("committed undo did not restore the source TaskGraph")
        if _git_text(root, "status", "--porcelain=v1", "--untracked-files=all"):
            raise GraphDeltaUndoError("committed graph-delta undo left a dirty checkout")
    except Exception:
        current = _git_text(root, "rev-parse", "HEAD", check=False)
        if current != plan.apply_commit or _git_text(
            root, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            _git(root, "reset", "--hard", plan.apply_commit)
        raise
    return GraphDeltaUndoResult(
        status="undone",
        plan_id=plan.plan_id,
        parent_task_id=plan.parent_task_id,
        apply_commit=plan.apply_commit,
        source_commit=plan.source_commit,
        undo_commit=undo_commit,
        committed_paths=plan.changed_paths,
    )


def _load_stored_plan(path: Path) -> GraphDeltaPlan:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GraphDeltaUndoError(
            f"graph-delta artifact is not readable UTF-8 JSON: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise GraphDeltaUndoError("graph-delta artifact must contain one JSON object")
    return GraphDeltaPlan.from_payload(value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph_delta", type=Path)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--expected-head")
    parser.add_argument("--confirm-plan-id")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the additive undo commit; omission is a read-only inspection.",
    )
    args = parser.parse_args(argv)
    try:
        stored = _load_stored_plan(args.graph_delta.resolve())
        source = args.source.resolve()
        plan = inspect_graph_delta_undo(
            source,
            stored,
            expected_head=args.expected_head,
        )
        if not args.apply:
            print(
                json.dumps(
                    {"status": "ready_dry_run", **asdict(plan)},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.confirm_plan_id != plan.plan_id:
            raise GraphDeltaUndoError(
                f"--apply requires --confirm-plan-id {plan.plan_id}"
            )
        result = undo_graph_delta(
            source,
            stored,
            expected_head=plan.apply_commit,
        )
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0
    except (GraphDeltaUndoError, OSError, ValueError) as exc:
        print(f"GRAPH DELTA UNDO: STOP\n{exc}", file=sys.stderr)
        return 2


__all__ = [
    "GraphDeltaUndoError",
    "GraphDeltaUndoPlan",
    "GraphDeltaUndoResult",
    "inspect_graph_delta_undo",
    "undo_graph_delta",
]


if __name__ == "__main__":
    raise SystemExit(main())
