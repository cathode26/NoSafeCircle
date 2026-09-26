#!/usr/bin/env python3
"""The validator is told where a gate it CANNOT certify goes.

NSC-049's crew did the work -- 934 lines across six files, 47.9 minutes, ~16M
tokens -- and was discarded on one line: `validator criteria_results missing
IDs: VAL-001..VAL-008`. Its own risks[0] was the correct analysis: "no Unity
Editor, NavMesh bake, or Physics query was actually executed, so VAL-001/002/
003/004/006/007/008 remain unconfirmed by real execution". It reasoned correctly
and wrote the conclusion into a field no check reads.

IT WAS NEVER STRUCTURALLY IMPOSSIBLE, and two counterexamples in the same
population say so: NSC-008's crew emitted all ten ACs AND all six VAL gates, six
of them execution-dependent, under the same inability to run Unity, and passed;
NSC-097 did the same on 09-24. The encoding already exists and is already
compatible with an overall pass:

    schemas.py   VALIDATOR_NON_PASS_REASON_CODES =
                     VALIDATOR_NOT_PROVEN_REASON_CODES - {"runtime_not_executed"}
    run_crew.py  if status == "pass" and non_pass_reason_used: reject

So `runtime_not_executed` is the one not_proven reason_code that may sit inside
an overall pass. What was missing was the instruction not to divert an
un-certifiable gate into `risks` instead.

WHAT THIS TEST PROVES AND WHAT IT DOES NOT. It proves the instruction reaches
the emitted validator prompt and cannot be deleted silently. It does NOT prove a
provider obeys it -- nothing here runs a model, and the first real test will be
whenever a VAL-gated task next runs a crew. Say that rather than implying the
defect is closed.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.prompts import validator_prompt  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import validator_semantic_reasons  # noqa: E402
from Pipeline.ExecutionCrew.schemas import (  # noqa: E402
    VALIDATOR_NON_PASS_REASON_CODES,
    VALIDATOR_NOT_PROVEN_REASON_CODES,
)


def _flat(text: str) -> str:
    """Probe the EMITTED bytes with whitespace flattened.

    A prompt is wrapped prose. Probing it with a phrase as typed fails on a line
    break while the content is perfectly correct -- four false FAILs in one
    session taught this, and three more today.
    """
    return re.sub(r"\s+", " ", text)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _prompt() -> str:
    return validator_prompt(
        task_id="NSC-049", title="gate-heavy task", task_contract="{}",
        candidate_patch="", changed_paths=(),
        implementer_output={}, test_author_output={},
    )


def test_an_uncertifiable_gate_is_told_where_to_go() -> None:
    prompt = _flat(_prompt())
    _require(
        "A gate you CANNOT certify still gets its criteria_results item" in prompt,
        "the validator prompt does not say an un-certifiable gate still gets a row",
    )
    _require(
        "reason_code=runtime_not_executed" in prompt,
        "the validator prompt does not name the reason_code that keeps overall pass valid",
    )


def test_risks_is_named_as_not_a_substitute() -> None:
    prompt = _flat(_prompt())
    _require(
        "an ID that appears only in risks is a MISSING ID" in prompt,
        "the validator prompt does not say risks is not a substitute for a criteria_results row",
    )
    _require(
        "rejects the entire run after the implementation has already been paid for" in prompt,
        "the validator prompt does not state the cost of omitting one ID",
    )


def test_the_instruction_matches_what_the_code_actually_enforces() -> None:
    """A prompt that promises something the code refuses is worse than silence.

    The prompt tells the validator that runtime_not_executed keeps an overall
    pass valid. That is only true because the code subtracts exactly that code
    from the set which cannot coexist with pass. Assert the RELATION, so this
    fails if someone later moves runtime_not_executed into the non-pass set.
    """
    _require(
        "runtime_not_executed" in VALIDATOR_NOT_PROVEN_REASON_CODES,
        "runtime_not_executed is no longer a not_proven reason_code",
    )
    _require(
        "runtime_not_executed" not in VALIDATOR_NON_PASS_REASON_CODES,
        "runtime_not_executed can no longer coexist with an overall pass, so the "
        "validator prompt is now instructing a rejection",
    )


def test_negative_control() -> None:
    """A clean result must be distinguishable from a broken probe."""
    prompt = _flat(_prompt())
    _require(
        "gates you cannot certify may be omitted" not in prompt,
        "negative control matched; the probe is not discriminating",
    )


# --------------------------------------------------------------------------
# THE IDS ARE NOW ENUMERATED, NOT ONLY DESCRIBED.
#
# CORRECTING MY OWN NOTE FIRST: I had written that "the validator is never shown
# the ids it must cover." THAT IS FALSE AS STATED. The prompt embeds the EXACT
# COMMITTED TASK CONTRACT, so every required ID is physically present -- measured
# at main 4910089f, all 14 of NSC-049 revision 9 (6 AC + 8 gates) appear as
# literal text in its 29,867 bytes, and all 6 of NSC-127 revision 3 in its
# 15,969, with a fabricated AC-999 correctly absent. What was missing is the
# DERIVED LIST: the pipeline computes the exact tuple it will judge the answer by
# and does not hand it over, so the model must re-extract 14 IDs from ~30KB and
# one miss discards a paid run.
#
# WHAT THESE TESTS PROVE: the enumeration reaches the emitted prompt, it is its
# own instruction rather than an artifact of the pasted contract, and it cannot
# drift from what the check demands. WHAT THEY DO NOT PROVE, and it is the whole
# question: that enumerating the IDs changes what a provider emits. Nothing here
# runs a model. The one live observation of the missing-IDs rejection is still
# ONE observation, and NSC-049's second dispatch died before the validator, so it
# neither confirmed nor refuted it.
# --------------------------------------------------------------------------

#: Modelled on NSC-049 revision 9 as measured above: 6 AC + 8 gates.
_NSC049_SHAPE = (
    "AC-001", "AC-002", "AC-003", "AC-004", "AC-005", "AC-006",
    "VAL-001", "VAL-002", "VAL-003", "VAL-004",
    "VAL-005", "VAL-006", "VAL-007", "VAL-008",
)


def _contract_text(ids: tuple[str, ...]) -> str:
    """A contract that CONTAINS every ID, so a lazy probe would pass trivially."""
    criteria = ", ".join(
        '{"criterion_id": "%s", "statement": "s"}' % i for i in ids if i.startswith("AC-"))
    gates = ", ".join(
        '{"gate_id": "%s", "requirement": "r"}' % i for i in ids if not i.startswith("AC-"))
    return '{"acceptance_criteria": [%s], "completion_gates": [%s]}' % (criteria, gates)


def _prompt_with(ids: tuple[str, ...]) -> str:
    return validator_prompt(
        task_id="NSC-049", title="gate-heavy task", task_contract=_contract_text(ids),
        candidate_patch="", changed_paths=(),
        implementer_output={}, test_author_output={},
        expected_requirement_ids=ids,
    )


def _instruction_half(prompt: str) -> str:
    """Everything BEFORE the pasted contract.

    The contract block holds every ID by construction, so probing the whole
    prompt cannot tell an instruction from an echo of the contract. This is the
    difference between the test passing because the feature exists and passing
    because the contract was pasted.
    """
    flat = _flat(prompt)
    marker = "EXACT COMMITTED TASK CONTRACT"
    _require(marker in flat, "the prompt no longer pastes the committed contract")
    return flat.split(marker, 1)[0]


def _enumerated_ids(prompt: str) -> tuple[str, ...]:
    """The IDs the prompt itself lists, parsed back out of the emitted text."""
    flat = _flat(prompt)
    marker = "no more and no fewer:"
    _require(marker in flat, "the validator prompt does not enumerate the required IDs")
    listing = flat.split(marker, 1)[1].split(".", 1)[0]
    return tuple(part.strip() for part in listing.split(",") if part.strip())


def test_the_prompt_enumerates_the_exact_ids_outside_the_pasted_contract() -> None:
    head = _instruction_half(_prompt_with(_NSC049_SHAPE))
    _require(
        "THE EXACT IDS THE AUTOMATED CHECK DEMANDS" in head,
        "the validator prompt does not enumerate the IDs as its own instruction",
    )
    _require(
        "14 of them, no more and no fewer" in head,
        "the enumeration does not state the COUNT, which is the model's checksum",
    )
    for requirement_id in _NSC049_SHAPE:
        _require(
            requirement_id in head,
            "%s is not enumerated in the instruction half; it may only be present "
            "inside the pasted contract, which is the state before this change"
            % requirement_id,
        )


def test_the_enumeration_cannot_drift_from_what_the_check_demands() -> None:
    """One tuple feeds both, so read the prompt back and hold the check to it.

    This is the property worth having: the run_crew call site passes the SAME
    object to `validator_prompt` and to `validator_semantic_reasons`, so if anyone
    later builds a second list for the prompt, the two disagree and this fails.
    Asserted on the specific substrings rather than on an empty reason list,
    because a synthetic output trips unrelated consistency rules and those are not
    what is under test here.
    """
    prompt = _prompt_with(_NSC049_SHAPE)
    enumerated = _enumerated_ids(prompt)
    _require(
        enumerated == _NSC049_SHAPE,
        "the prompt enumerates %r, the caller passed %r" % (enumerated, _NSC049_SHAPE),
    )
    output = {
        "status": "pass",
        "criteria_results": [
            {"id": i, "status": "not_proven", "reason_code": "runtime_not_executed",
             "reason": "no Unity run"} for i in enumerated
        ],
    }
    reasons = " | ".join(validator_semantic_reasons(output, _NSC049_SHAPE))
    _require(
        "missing IDs" not in reasons,
        "an output covering exactly the IDs the prompt enumerates is still "
        "reported as missing some: %s" % reasons,
    )
    _require(
        "unknown IDs" not in reasons,
        "the prompt enumerates an ID the check calls unknown: %s" % reasons,
    )


def test_dropping_one_enumerated_id_names_that_id_in_the_refusal() -> None:
    """The negative half, and it NAMES the refusal.

    "It was rejected" passes on any earlier unrelated rejection. This asserts the
    ID that was dropped appears in the reason, which is the only form that proves
    the coverage check is what fired.
    """
    prompt = _prompt_with(_NSC049_SHAPE)
    enumerated = _enumerated_ids(prompt)
    dropped = enumerated[-1]
    output = {
        "status": "pass",
        "criteria_results": [
            {"id": i, "status": "not_proven", "reason_code": "runtime_not_executed",
             "reason": "no Unity run"} for i in enumerated if i != dropped
        ],
    }
    reasons = " | ".join(validator_semantic_reasons(output, _NSC049_SHAPE))
    _require(
        "criteria_results missing IDs" in reasons,
        "dropping %s did not earn the missing-IDs reason: %s" % (dropped, reasons),
    )
    _require(
        dropped in reasons,
        "the refusal does not name the dropped ID %s: %s" % (dropped, reasons),
    )


def test_every_run_crew_call_site_passes_the_ids_it_will_judge_against() -> None:
    """The one-source claim lives at the CALL SITE, and nothing else here tests it.

    The tests above prove the prompt renders what it is given. They would all pass
    with `run_crew` never passing anything -- which is exactly the state before
    this change, and exactly the state a later edit could restore. Parsed with
    `ast` rather than grepped, so it holds under any reformatting and names the
    real property: every `validator_prompt(...)` call supplies
    `expected_requirement_ids`.

    There are two such calls -- the validator at run_crew.py:2748 and the pooled
    lead-developer diagnosis at :2788, which reuses the same builder -- and BOTH
    are checked against `validator_semantic_reasons` afterwards, so a prompt
    missing the list on either path is the same defect.
    """
    source_path = Path(__file__).resolve().parents[1] / "run_crew.py"
    _require(source_path.is_file(), "run_crew.py is not where this test expects it")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validator_prompt"
    ]
    _require(
        len(calls) >= 2,
        "expected at least 2 validator_prompt call sites in run_crew.py, found %d -- "
        "if the calls moved, this test is measuring the wrong file" % len(calls),
    )
    for call in calls:
        names = {keyword.arg for keyword in call.keywords}
        _require(
            "expected_requirement_ids" in names,
            "the validator_prompt call at run_crew.py:%d does not pass "
            "expected_requirement_ids, so that prompt asks for coverage it never "
            "enumerates while the check still demands it" % call.lineno,
        )


def test_a_task_with_no_ids_enumerates_nothing() -> None:
    """The feature must not claim coverage it was given nothing to cover.

    `_prompt()` passes no IDs at all -- the shape every existing caller had before
    this change -- and must render no enumeration, so an empty tuple can never
    read as "all required IDs are listed".
    """
    head = _instruction_half(_prompt())
    _require(
        "THE EXACT IDS THE AUTOMATED CHECK DEMANDS" not in head,
        "an empty ID list still renders an enumeration, which would assert "
        "coverage of nothing",
    )
    _require(
        "no more and no fewer" not in head,
        "an empty ID list still renders the count sentence",
    )


def main() -> int:
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok  {name}")
    print("validator gate-row instruction: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
