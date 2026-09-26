#!/usr/bin/env python3
"""A crew that stops because nothing was left to change says so, instead of blaming the role.

`incremental_check` can only observe that a required modification is ABSENT. Its one reason,
"role made no required file modification", is then copied verbatim into the run's reasons -- and it
reads as the ROLE having done nothing when the actual state can be the REPOSITORY already
satisfying the contract.

NSC-049 is the worked example. Its implementer returned `agent_status: succeeded`, no blockers,
`semantic_validation: accepted` and a detailed rationale that the work was already present at
revision 9, and the run still reported a generic failure. The Pipeline Runner spent a dispatch
re-deriving that from the role record.

WHAT THIS SUITE PROVES. That the two states are now distinguishable in the emitted reasons, that
the real `incremental_check` output is what the helper recognises (so the two cannot drift apart),
and that a genuine violation is NEVER re-described as a satisfied contract.

WHAT IT DOES NOT PROVE. That the repository really does satisfy NSC-049 -- the new reason reports
the ROLE'S OWN claim and says where to check it, deliberately, because the pipeline cannot verify
that claim here. It also does not change any gate: `require_change` still stops the run, and
`crew_status` is still "rejected". This is a diagnosis change, not a policy change.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    NO_REQUIRED_CHANGE_REASON,
    Snapshot,
    already_satisfied_reasons,
    incremental_check,
)

RUN_CREW = ROOT / "Pipeline/ExecutionCrew/run_crew.py"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check(*, require_change: bool, index: bytes = b"index", head: str = "head") -> list[str]:
    """Drive the real incremental_check with no changed paths.

    `invocation` is only consulted inside the per-changed-path loop, so with no changed paths it is
    never touched and None is safe. If that ever stops being true this raises instead of passing
    quietly, which is the failure we want.
    """
    before = Snapshot("head", b"index", {})
    after = Snapshot(head, index, {})
    actual, reasons = incremental_check(before, after, None, require_change=require_change)
    _require(actual == [], f"fixture is wrong: expected no changed paths, got {actual}")
    return reasons


def test_the_real_check_produces_exactly_the_reason_the_helper_recognises() -> None:
    """The drift pin, and it is the reason this suite exists.

    The helper compares against a constant; the check emits one. If either side is edited to a
    different string the two silently stop agreeing and the diagnosis disappears with no test
    failing anywhere. So the check's OWN output -- not a literal typed here -- is what is fed in.
    """
    reasons = _check(require_change=True)
    _require(
        reasons == [NO_REQUIRED_CHANGE_REASON],
        f"the check no longer emits the shared constant alone: {reasons}",
    )
    named = already_satisfied_reasons(
        "implementer", 1, status="succeeded", blockers=[], scope=reasons, new_paths=()
    )
    _require(
        len(named) == 1,
        "the helper does not recognise the check's own output; the two have drifted apart",
    )


def test_an_already_satisfied_implementer_is_not_described_as_a_role_failure() -> None:
    (reason,) = already_satisfied_reasons(
        "implementer", 1, status="succeeded", blockers=[], scope=_check(require_change=True), new_paths=()
    )
    _require("implementer" in reason, "the reason does not name the role it describes")
    _require(
        "not the same as the role failing" in reason,
        "the reason does not separate a satisfied contract from a failed role, which is its whole job",
    )
    _require(
        "role_results/implementer_1.json" in reason,
        "the reason does not say where the role's own rationale is; re-deriving that cost a dispatch",
    )
    _require(
        "delivery record" in reason,
        "the reason does not raise the alternative route, which is what the Runner actually needed",
    )


def test_the_attempt_number_points_at_the_record_that_exists() -> None:
    """require_change only fires on attempt 1 today, but the pointer must not hardcode that."""
    (reason,) = already_satisfied_reasons(
        "implementer", 2, status="succeeded", blockers=[], scope=_check(require_change=True), new_paths=()
    )
    _require(
        "role_results/implementer_2.json" in reason,
        "the record pointer ignores the attempt it was given",
    )


def test_a_second_scope_reason_is_never_re_described() -> None:
    """The safety test. A real violation beside the no-change reason must not be softened.

    Both reasons here come from the real check: a changed Git index is a genuine scope violation.
    """
    reasons = _check(require_change=True, index=b"index-after")
    _require(
        len(reasons) == 2 and NO_REQUIRED_CHANGE_REASON in reasons,
        f"fixture is wrong: wanted a real second reason beside the no-change one, got {reasons}",
    )
    _require(
        already_satisfied_reasons(
            "implementer", 1, status="succeeded", blockers=[], scope=reasons, new_paths=()
        )
        == (),
        "a run with a real scope violation was described as an already-satisfied contract",
    )


def test_a_changed_head_is_also_never_re_described() -> None:
    reasons = _check(require_change=True, head="head-after")
    _require(
        len(reasons) == 2,
        f"fixture is wrong: wanted two reasons, got {reasons}",
    )
    _require(
        already_satisfied_reasons(
            "implementer", 1, status="succeeded", blockers=[], scope=reasons, new_paths=()
        )
        == (),
        "a run whose clone HEAD moved was described as an already-satisfied contract",
    )


def test_an_outstanding_new_path_is_a_real_obligation_miss() -> None:
    """A declared new file that does not exist is not a satisfied contract.

    A path is in `new_paths` precisely because it is absent at baseline, so "nothing changed" means
    it is still absent. This is the same distinction the Test Author's require_change already makes
    by exempting an empty new_paths, applied to the one role that lacked it.
    """
    _require(
        already_satisfied_reasons(
            "implementer",
            1,
            status="succeeded",
            blockers=[],
            scope=_check(require_change=True),
            new_paths=("Assets/NoSafeCircle/Thing.cs",),
        )
        == (),
        "a role that never created its declared new file was excused as already satisfied",
    )


def test_a_blocker_is_not_an_already_satisfied_contract() -> None:
    _require(
        already_satisfied_reasons(
            "implementer",
            1,
            status="succeeded",
            blockers=[{"summary": "the contract contradicts the GDD"}],
            scope=_check(require_change=True),
            new_paths=(),
        )
        == (),
        "a role that raised a blocker was described as having found the work already done",
    )


def test_a_failed_agent_is_not_an_already_satisfied_contract() -> None:
    _require(
        already_satisfied_reasons(
            "implementer", 1, status="failed", blockers=[], scope=_check(require_change=True), new_paths=()
        )
        == (),
        "a failed agent invocation was described as an already-satisfied contract",
    )


def test_the_reason_appears_only_when_require_change_asked_for_one() -> None:
    """The control: with require_change off the check says nothing, so there is nothing to explain."""
    reasons = _check(require_change=False)
    _require(reasons == [], f"the check invented a reason with require_change off: {reasons}")
    _require(
        already_satisfied_reasons(
            "implementer", 1, status="succeeded", blockers=[], scope=reasons, new_paths=()
        )
        == (),
        "the helper named an already-satisfied contract for a run that never required a change",
    )


def test_the_implementer_call_site_passes_the_state_it_is_judging() -> None:
    """A structural pin: the wiring cannot be deleted or re-pointed silently.

    The helper is correct in isolation and useless if the call site hands it a stale or wrong
    object, and no behavioural test in this suite can see that.
    """
    tree = ast.parse(RUN_CREW.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "already_satisfied_reasons"
    ]
    _require(len(calls) == 1, f"expected exactly one call site, found {len(calls)}")
    call = calls[0]
    positional = [ast.unparse(arg) for arg in call.args]
    _require(
        positional == ["'implementer'", "attempt"],
        f"the call site no longer names the implementer and its attempt: {positional}",
    )
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords}
    _require(
        keywords
        == {
            "status": "res.status",
            "blockers": "blockers",
            "scope": "scope",
            "new_paths": "impl_plan.new_paths",
        },
        f"the call site no longer passes the live state it is judging: {keywords}",
    )


def test_the_test_author_does_not_borrow_this_diagnosis() -> None:
    """Its require_change already implies a non-empty new_paths, so a no-change there is a real miss.

    Recorded as a test rather than a comment because "apply it to the other role too" is the
    obvious next edit and it would be wrong.
    """
    source = RUN_CREW.read_text(encoding="utf-8")
    _require(
        'already_satisfied_reasons("test_author"' not in source,
        "the test_author now claims an already-satisfied contract, but its require_change only "
        "fires when new test paths are outstanding, which is a real obligation miss",
    )


def main() -> int:
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok  {name}")
    print("already-satisfied diagnosis: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
