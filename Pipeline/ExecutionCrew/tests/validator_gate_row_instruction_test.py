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

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.prompts import validator_prompt  # noqa: E402
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


def main() -> int:
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok  {name}")
    print("validator gate-row instruction: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
