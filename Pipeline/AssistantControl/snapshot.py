"""Read-only assessment of whether an execution baseline is a valid snapshot.

THE QUESTION THIS ANSWERS, and it is not the one admission asks today.
`admission.reserve` admits an ORDINARY prepared record only when its checkout
sits on EXACTLY current Source HEAD (`admission.py`: "source or persisted scope
is not at current HEAD"). Main advances every few minutes, so that equality
refuses almost every ordinary record for a reason that has nothing to do with
whether the record is executable.

Astra's design pass (`C:/nscrev/codex-jobs/ordinary-snapshot-validity-astra.report.md`,
gpt-6-astra, read-only) states the property in one sentence: *"An ordinary
prepared checkout should be admissible because it is a valid, accepted execution
snapshot -- not because it equals the latest Source commit."* And the trap, in
its words: the equality *"substitutes 'everything is current' for several more
specific facts"*, so **replacing equality with ancestry ALONE would remove the
substitute without establishing the facts it was indirectly supplying.**

THE FACT THIS MODULE ESTABLISHES IS THE ONE THE EQUALITY WAS REALLY SUPPLYING:
that the accepted content of every dependency is actually present in the tree the
crew will run in. Astra's worked example is why the timing matters, and it cuts
BOTH ways:

    I: dependency implementation integrated     B: ordinary task prepared
    B: ordinary task prepared, containing I     I: dependency implementation integrated
    E: dependency delivery evidence committed   E: dependency delivery evidence committed
    S: admission inspection                     S: admission inspection
    -> B CAN be valid                           -> B MUST fail

Identical later evidence, opposite answers. `dependencies.py` cannot tell them
apart: it takes the dependency list from Source's contract and evaluates each
dependency's conformance at Source, so **both which dependencies are required and
whether they are satisfied can describe a different task version from the
execution checkout.** Source's delivery record cannot make I appear in B.

WHAT THIS IS NOT. It is READ-ONLY and it decides nothing: nothing in this module
refuses an admission. It exists so readiness and reserve can consume ONE
assessment instead of two disagreeing ones -- the shape that had to be fixed
twice already (`c6a277f1`, `8eecdee7`) -- and so the rule can be MEASURED over
the live population before it gates anything.

WHAT IT DOES NOT PROVE, and this is Astra's caveat rather than a caveat about
this code: `conformance_surfaces` is a list of write-authorized files, and
`conformance_records.py` validates only its SHAPE -- it "does not establish that
this list completely covers the dependency's runtime requirements. It even
permits an empty list." So a passing content proof here is NECESSARY, never
sufficient, and an EMPTY surface list is reported as insufficient coverage rather
than as a pass. `content_proof` names which of the two you got.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from Pipeline.AssistantControl.inspect_project import git

#: A dependency state this module will attempt a content proof for. Anything
#: else is somebody else's refusal: `_dependency_is_satisfied` already blocks a
#: non-conformant dependency, and duplicating that here would report two
#: problems for one cause.
_ACCEPTED_DEPENDENCY_STATES = frozenset({"conformant"})

#: Where a task's committed delivery records live, relative to the repository
#: root. Same path `readiness._committed_delivery_evidence` reads.
_EVIDENCE_RECORDS = "Pipeline/TaskGraph/evidence/{task_id}/records/{record_id}.json"

#: The two content-proof strengths this module can return. Neither is a
#: completeness claim; the second says so out loud.
CONTENT_PROOF_DECLARED_SURFACES = "declared_surfaces_only"
CONTENT_PROOF_NONE = "none"


def _is_ancestor(source: Path, earlier: str, later: str) -> bool:
    try:
        git(source, "merge-base", "--is-ancestor", earlier, later)
    except Exception:
        return False
    return True


def _blob_at(source: Path, commit: str, path: str) -> str | None:
    """The blob id of ``path`` at ``commit``, or None when it is not a blob there.

    `rev-parse <commit>:<path>` and not `ls-tree` on purpose: it fails for an
    absent path AND for a path that is a tree at that commit, and those are the
    two ways a surface can stop being the file the evidence described.
    """
    try:
        raw = git(source, "rev-parse", f"{commit}:{path}").decode().strip()
    except Exception:
        return None
    if len(raw) < 40 or any(ch not in "0123456789abcdef" for ch in raw.lower()):
        return None
    return raw


def _selected_record(source: Path, source_head: str, task_id: str,
                     record_id: str) -> dict[str, Any] | None:
    """The accepted record, READ AT S. It does not have to exist in B.

    Astra: *"That does not require the evidence record itself to exist in B.
    Evidence may legitimately arrive after implementation."* Reading it at B
    instead is the bug this whole module exists to avoid.
    """
    path = _EVIDENCE_RECORDS.format(task_id=task_id, record_id=record_id)
    blob = _blob_at(source, source_head, path)
    if blob is None:
        return None
    try:
        value = json.loads(git(source, "cat-file", "blob", blob).decode("utf-8-sig"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _surface_applicability(source: Path, baseline: str,
                           surfaces: Any) -> dict[str, Any]:
    """Is every accepted surface blob byte-identical at the execution baseline?

    Ancestry of the validated commit into B is the cheaper test and Astra names
    exactly why it is not enough: *"Ancestry alone misses reverts and subsequent
    destructive edits."* Comparing the blobs catches both, and needs no
    assumption about how B's history was built.
    """
    if not isinstance(surfaces, list) or not surfaces:
        # An empty list is SHAPE-VALID (`conformance_records.py` permits it) and
        # proves nothing whatever. Calling it applicable would be a content
        # proof that passes because it made no comparison.
        return {"content_proof": CONTENT_PROOF_NONE, "applicable": False,
                "surfaces_declared": 0, "surfaces_matching": 0,
                "absent_at_baseline": [], "changed_at_baseline": [],
                "reason": "dependency_declares_no_conformance_surfaces"}
    absent: list[str] = []
    changed: list[str] = []
    matching = 0
    for surface in surfaces:
        if not isinstance(surface, Mapping):
            changed.append("<malformed surface entry>")
            continue
        path = surface.get("path")
        expected = surface.get("blob_sha")
        if not isinstance(path, str) or not path or not isinstance(expected, str):
            changed.append(str(path))
            continue
        # Normalise the same way the repository stores it; a backslash here
        # would silently miss on Windows.
        path = str(PurePosixPath(path.replace("\\", "/")))
        found = _blob_at(source, baseline, path)
        if found is None:
            absent.append(path)
        elif found.lower() != expected.lower():
            changed.append(path)
        else:
            matching += 1
    applicable = not absent and not changed
    reason = None
    if absent:
        reason = "accepted_dependency_surface_absent_at_baseline"
    elif changed:
        reason = "accepted_dependency_surface_differs_at_baseline"
    return {"content_proof": CONTENT_PROOF_DECLARED_SURFACES,
            "applicable": applicable,
            "surfaces_declared": len(surfaces), "surfaces_matching": matching,
            "absent_at_baseline": sorted(absent),
            "changed_at_baseline": sorted(changed),
            "reason": reason}


def assess_execution_snapshot(source: Path, baseline: str, source_head: str,
                              dependency: Mapping[str, Any]) -> dict[str, Any]:
    """Whether ``baseline`` is a valid execution snapshot against ``source_head``.

    ``dependency`` is an `inspect_dependencies` result. Passing it in rather than
    re-deriving it keeps the injectable fixture seam admission already has, and
    keeps this function from being a second reader of the same artifact.

    Returns an advisory. It raises only on an unusable argument.
    """
    if not isinstance(baseline, str) or not baseline.strip():
        raise ValueError("snapshot assessment requires an execution baseline")
    if not isinstance(source_head, str) or not source_head.strip():
        raise ValueError("snapshot assessment requires a source head")
    if not isinstance(dependency, Mapping):
        raise ValueError("snapshot assessment requires a dependency inspection")

    source = Path(source)
    refusals: list[str] = []

    is_ancestor = _is_ancestor(source, baseline, source_head)
    if not is_ancestor:
        # NOT the same statement as "the baseline is stale". A baseline that is
        # not an ancestor of S is not a snapshot OF S at all -- it is a divergent
        # line, which is what a reconciled merge legitimately is. Reported, not
        # interpreted.
        refusals.append("baseline_is_not_a_source_ancestor")

    items = dependency.get("dependencies")
    assessed: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        dep_id = item.get("task_id")
        state = item.get("state")
        record_id = item.get("selected_record_id")
        entry: dict[str, Any] = {"task_id": dep_id, "state": state,
                                 "selected_record_id": record_id}
        if state not in _ACCEPTED_DEPENDENCY_STATES:
            # Somebody else's refusal; see _ACCEPTED_DEPENDENCY_STATES.
            entry.update({"applicable": None, "content_proof": CONTENT_PROOF_NONE,
                          "reason": "dependency_not_accepted_at_source"})
            assessed.append(entry)
            continue
        if not isinstance(record_id, str) or not record_id.strip():
            entry.update({"applicable": False, "content_proof": CONTENT_PROOF_NONE,
                          "reason": "accepted_dependency_names_no_record"})
            assessed.append(entry)
            refusals.append(f"dependency_{dep_id}_names_no_record")
            continue
        record = _selected_record(source, source_head, str(dep_id), record_id)
        if record is None:
            entry.update({"applicable": False, "content_proof": CONTENT_PROOF_NONE,
                          "reason": "accepted_dependency_record_unreadable_at_source"})
            assessed.append(entry)
            refusals.append(f"dependency_{dep_id}_record_unreadable")
            continue
        validated = record.get("validated_state")
        validated_commit = (validated.get("commit")
                            if isinstance(validated, Mapping) else None)
        proof = _surface_applicability(source, baseline,
                                       record.get("conformance_surfaces"))
        entry.update(proof)
        entry["validated_commit"] = validated_commit
        # Reported beside the content proof, never instead of it. Ancestry is
        # the provenance question; the blob comparison is the content question.
        entry["validated_commit_is_baseline_ancestor"] = (
            _is_ancestor(source, validated_commit, baseline)
            if isinstance(validated_commit, str) and validated_commit.strip()
            else None)
        assessed.append(entry)
        if proof["applicable"] is not True:
            refusals.append(f"dependency_{dep_id}_{proof['reason']}")

    applicable_states = [item.get("applicable") for item in assessed]
    return {
        "schema": "assistant-execution-snapshot/v1",
        "baseline": baseline,
        "source_head": source_head,
        "baseline_equals_source_head": baseline == source_head,
        "baseline_is_source_ancestor": is_ancestor,
        "dependencies": assessed,
        "dependencies_assessed": len(assessed),
        "dependencies_applicable": sum(1 for value in applicable_states if value is True),
        "dependencies_not_applicable": sum(1 for value in applicable_states if value is False),
        "dependencies_unassessed": sum(1 for value in applicable_states if value is None),
        # NOT an admission verdict and deliberately not called one. It is "every
        # question THIS module asks is answered yes". Contract acceptance at S,
        # canon/policy acceptance, scope pinning, capacity, resources and the
        # Source-edit conflict check are all elsewhere and all still required.
        #
        # UNASSESSED COUNTS AGAINST IT, and the fixture's own control caught this
        # being wrong: with `refusals` empty by design for a dependency Source has
        # not accepted, an earlier version returned True while the content
        # question was never asked at all. `refusals` says what THIS module
        # refuses; this flag says what it ESTABLISHED, and silence is not
        # establishment.
        "snapshot_content_verified": (
            is_ancestor and not refusals
            and all(item.get("applicable") is True for item in assessed)),
        "refusals": sorted(set(refusals)),
    }


__all__ = ["assess_execution_snapshot", "CONTENT_PROOF_DECLARED_SURFACES",
           "CONTENT_PROOF_NONE"]
