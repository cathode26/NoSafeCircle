"""What a reconciled record proves about the rejection its next crew must answer.

THE DEFECT THIS EXISTS FOR. ``revise-on-source`` withdraws a candidate and
republishes the task as ``prepared`` on a merge of that candidate with current
Source. That is the only route a HUMAN-REJECTED candidate has once Source has
moved -- and Source moves every few minutes here, so the window in which
ordinary ``revise`` still applies is minutes wide, not hours.

But widening ``revise-on-source`` to accept a human rejection is NOT enough on
its own, and shipping only that would be worse than shipping nothing. Astra
found why, in the design report at
``C:/nscrev/codex-jobs/pm-stranded-candidate-design.report.md``:

    ``prepare_revision_feedback()`` returns ``{}`` for a record with no ordinary
    ``revision``, and ordinary ``revision`` ASSUMES the rejected commit IS the
    execution baseline. After a reconciliation those are different commits --
    C is the rejected candidate and M is the baseline -- so the ordinary
    binding is structurally unavailable, and a naive widening produces a task
    that re-scopes correctly and whose crew is told NOTHING. It would repeat
    the failure it was revised to fix, at full provider cost.

So the withdrawal writes a TYPED binding into its history entry, and this module
is the single reader of it. Four identities are kept separate on purpose:

    rejected_candidate        C   the work carried forward as INPUT
    inspected_source_commit   S   the Source an operator actually looked at
    reconciled_commit         M   the merge, which becomes the new baseline
    withdrawal_basis              human_rejection, or materialization_failure

WHY THE REVIEW IS FROZEN INTO THE ENTRY RATHER THAN LOOKED UP LATER. Raised by
the Pipeline Runner at the cheapest possible moment -- before this binding
existed -- from a live case: NSC-118's rejection says a regression check "is
still owed", the Game Agent then RAN it, and it passed. A rejection message can
therefore be false by the time a crew reads it. The remedy is to correct the
rejection BEFORE withdrawing it, which is safe: ``review.py`` appends to
``review_history`` before assigning ``human_review``, so a second reject with a
corrected message destroys nothing.

Once withdrawn, though, the exact bytes a crew was dispatched with must not move
underneath it. A correction landing after dispatch would silently change what a
running crew had been told, and nothing in the record would show the feedback
had moved -- one step worse than stale feedback, because it is invisible. So the
entry carries the review OBJECT, plus the index and hash of the
``review_history`` entry it was taken from, and reading it requires all three to
agree.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA_VERSION = "assistant-reconciliation-binding/v1"

HUMAN_REJECTION = "human_rejection"
MATERIALIZATION_FAILURE = "materialization_failure"
WITHDRAWAL_BASES = frozenset({HUMAN_REJECTION, MATERIALIZATION_FAILURE})


class ReconciliationBindingError(ValueError):
    """A reconciliation binding is present but does not hold together."""


def canonical_sha256(value: Any) -> str:
    """Hash a record fragment by its CONTENT, not by its serialized layout.

    Sorted keys and no insignificant whitespace, so a hash written by one writer
    and checked by another cannot disagree over indentation.
    """

    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_entry_index(record: Mapping[str, Any], review: Mapping[str, Any]) -> int:
    """Where in ``review_history`` this exact review sits.

    ``review_history`` is append-only -- ``review.py:205`` is its only writer in
    AssistantControl -- so an index taken now keeps pointing at the same entry
    for the life of the record. The hash is what catches a hand edit.
    """

    history = record.get("review_history")
    if not isinstance(history, list):
        raise ReconciliationBindingError("record has no review history to bind")
    wanted = canonical_sha256(dict(review))
    for index in range(len(history) - 1, -1, -1):
        entry = history[index]
        if isinstance(entry, Mapping) and canonical_sha256(dict(entry)) == wanted:
            return index
    raise ReconciliationBindingError(
        "the rejection is not present in review_history; it cannot be bound by identity")


def candidate_receipt_problem(record: Mapping[str, Any], candidate: Any,
                              task_id: str) -> str | None:
    """Why this is not an authenticated registered crew candidate, or None.

    A RAW crew candidate carries its provenance in its registered commit
    receipt. It has no wrapper flags, because none were applied to it:
    ``source_candidate_crew_review`` is a MATERIALIZATION field recording that a
    mechanically transformed candidate descends from crew-reviewed work.
    Requiring it here would exclude exactly the earlier-stage candidates this
    path exists for -- Astra's first finding, and the opposite of what that
    guard looks like it is doing.

    The same identity comparison is made in ``revision_feedback.py`` against an
    ARCHIVED candidate. One definition, two callers.
    """

    if not isinstance(candidate, Mapping):
        return "record carries no candidate"
    receipt = candidate.get("receipt")
    if not isinstance(receipt, Mapping):
        return "candidate has no registered crew commit receipt"
    run_id = candidate.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        return "candidate names no crew run"
    identity = {
        "task_id": task_id,
        "run_id": run_id,
        "lease_id": candidate.get("lease_id"),
        "plan_id": candidate.get("plan_id"),
        "candidate_commit": candidate.get("commit"),
        "candidate_tree": candidate.get("tree"),
        "candidate_parent": candidate.get("parent"),
        "task_contract_sha256": record.get("task_contract_sha256"),
        "source_base": record.get("source_commit"),
    }
    for key, value in identity.items():
        if not value or receipt.get(key) != value:
            return f"candidate receipt identity differs on {key}"
    return None


def human_rejection_binding(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The live human-rejection withdrawal this record sits on, or None.

    None means "there is no such withdrawal", and nothing else. Every way an
    EXISTING binding can fail to hold together raises instead, because the whole
    point of the binding is that a crew is never dispatched believing it carries
    feedback it does not carry. Returning an empty result quietly is the exact
    failure mode Astra named.
    """

    history = record.get("revise_on_source_history")
    if not isinstance(history, list) or not history:
        return None
    entry = history[-1]
    if not isinstance(entry, Mapping) or entry.get("withdrawal_basis") != HUMAN_REJECTION:
        # An older entry, or a materialization withdrawal: not this path's.
        return None

    reconciled = entry.get("reconciled_commit")
    if not isinstance(reconciled, str) or not reconciled:
        raise ReconciliationBindingError("withdrawal names no reconciled commit")
    if reconciled != record.get("source_commit"):
        # Something moved the record past this withdrawal. The binding is spent
        # rather than broken: whatever the record sits on now came from
        # elsewhere, and this entry says nothing about it.
        return None
    if entry.get("accepted_contract_sha256") != record.get("task_contract_sha256"):
        raise ReconciliationBindingError(
            "the reconciled contract is not the record's pinned contract")

    review = entry.get("rejected_review")
    rejected = entry.get("rejected_candidate")
    if (not isinstance(review, Mapping) or review.get("decision") != "reject"
            or not isinstance(rejected, str) or not rejected
            or review.get("commit") != rejected):
        raise ReconciliationBindingError(
            "withdrawal does not bind an exact rejection of the exact candidate")
    message = review.get("message")
    if not isinstance(message, str) or not message.strip() or "\x00" in message:
        raise ReconciliationBindingError("bound rejection message must be non-empty text")

    index = entry.get("review_entry_index")
    digest = entry.get("review_entry_sha256")
    entries = record.get("review_history")
    if (type(index) is not int or not isinstance(digest, str)
            or not isinstance(entries, list) or not 0 <= index < len(entries)):
        raise ReconciliationBindingError("withdrawal does not name its review history entry")
    live = entries[index]
    if not isinstance(live, Mapping) or canonical_sha256(dict(live)) != digest:
        raise ReconciliationBindingError(
            "the bound review history entry has changed since the withdrawal; the "
            "feedback a crew would be given is not the feedback that was withdrawn")
    if canonical_sha256(dict(review)) != digest:
        raise ReconciliationBindingError(
            "the frozen rejection differs from the review history entry it names")
    return entry


__all__ = [
    "HUMAN_REJECTION",
    "MATERIALIZATION_FAILURE",
    "ReconciliationBindingError",
    "SCHEMA_VERSION",
    "WITHDRAWAL_BASES",
    "canonical_sha256",
    "candidate_receipt_problem",
    "human_rejection_binding",
    "review_entry_index",
]
