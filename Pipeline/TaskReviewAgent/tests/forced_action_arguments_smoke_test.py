#!/usr/bin/env python3
"""Deterministic regressions for host-derived arguments on forced downstream actions.

Classification: pure/component tests. Injected observations and a fake provider
object; no Docker, Codex, GitHub, Unity, network, or checkout is touched.

NSC-914 delivery run `scheduler-nsc-914-adac4ceeac204e5f` proved two
parameterized actions still reached the provider even though downstream had
already narrowed them to the sole expected action:

  * acquire_agent_lease            17,808 input / 542 output tokens
  * run_authoritative_unity_test   18,746 input / 238 output tokens

Both arguments sets are derivable from durable state -- the second was already
being pasted into the prompt as a "Host-authorized exact plan" before the
provider was paid to echo it back -- so the provider was buying nothing. These
tests pin zero provider invocations for both, prove the arguments come only from
durable state, and prove that missing or invalid durable state fails closed
instead of falling back to invented provider values.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
    CodexDockerDecisionProvider,
    SupervisorDecision,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
)
from Pipeline.TaskReviewAgent import downstream_determinism as determinism  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_determinism import (  # noqa: E402
    _ALLOWED_ACTION_CONTEXT,
    _patched_provider_decide,
    _patched_render_supervisor_prompt,
    allowed_actions_for,
    forced_action_arguments,
)
from Pipeline.TaskReviewAgent.openai_downstream import (  # noqa: E402
    _ACTIONS as _DOWNSTREAM_ACTIONS,
)

TASK = "NSC-914"
FILTER = "NoSafeCircle.Tests.DoorPrototypeSceneBuilderTests"
PLAYMODE_FILTER = "NoSafeCircle.Tests.PlayModeDoorTests"

FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action, expected=DownstreamPipelineError) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


# ---------------------------------------------------------------- observations


def observation(
    *,
    next_action: str,
    phase: str = "delivery_evidence",
    state: str = "agent_working",
    plan: Mapping[str, Any] | None = None,
    manifests: Sequence[Mapping[str, Any]] | None = None,
    checkout_ready: bool = True,
) -> dict[str, Any]:
    downstream: dict[str, Any] = {"next_action": next_action}
    if plan is not None:
        downstream["authoritative_test_plan"] = dict(plan)
    if manifests is not None:
        downstream["receipt"] = {"validation_manifests": [dict(m) for m in manifests]}
    return {
        "task": {"task_id": TASK},
        "coordination": {
            "workflow_state": {"state": state, "phase": phase},
        },
        "downstream": downstream,
        "checkout": {"status": "ready"} if checkout_ready else {},
    }


def editmode_plan() -> dict[str, Any]:
    return {
        "required_test_platforms": ["EditMode"],
        "test_filters": {"EditMode": FILTER},
        "authority": "committed_validation_policy",
        "policy_sha256": "f" * 64,
    }


class RecordingProvider:
    """A provider whose real decide path must never be reached for a forced action."""

    def __init__(self) -> None:
        self.last_usage: dict[str, Any] | None = None
        self.provider_calls: list[tuple[str, ...]] = []


def decide(observed: Mapping[str, Any]) -> tuple[SupervisorDecision, RecordingProvider]:
    """Drive the exact production shape: patched render, then decide on the full menu."""
    _patched_render_supervisor_prompt(
        task_id=TASK,
        goal_and_rules="rules",
        observation=observed,
        history=(),
        actions=_DOWNSTREAM_ACTIONS,
    )
    provider = object.__new__(CodexDockerDecisionProvider)
    provider.last_usage = None
    calls: list[tuple[str, ...]] = []
    original = determinism._ORIGINALS["provider_decide"]

    def counted(_self, *, task_id, turn, prompt, allowed_actions):
        calls.append(tuple(allowed_actions))
        return SupervisorDecision(task_id, "record_pipeline_blocker", {}, "provider ran")

    determinism._ORIGINALS["provider_decide"] = counted
    try:
        decision = _patched_provider_decide(
            provider,
            task_id=TASK,
            turn=1,
            prompt="provider must not be called for a forced action",
            allowed_actions=tuple(_DOWNSTREAM_ACTIONS),
        )
    finally:
        determinism._ORIGINALS["provider_decide"] = original
    recorder = RecordingProvider()
    recorder.last_usage = provider.last_usage
    recorder.provider_calls = calls
    return decision, recorder


# ------------------------------ 1-2: zero provider invocations for both actions


def test_run_authoritative_unity_test_invokes_no_provider() -> None:
    observed = observation(
        next_action="run_authoritative_unity_tests", plan=editmode_plan()
    )
    selected = allowed_actions_for(observed, (), _DOWNSTREAM_ACTIONS)
    require(selected == ("run_authoritative_unity_test",),
            f"the host did not force one action: {selected}")
    require(len(_DOWNSTREAM_ACTIONS) > 1,
            "the production menu must have more than one action to prove anything")

    decision, provider = decide(observed)
    require(provider.provider_calls == [],
            f"the provider was invoked for a forced action: {provider.provider_calls}")
    require(decision.action == "run_authoritative_unity_test", decision.action)
    require(decision.arguments == {"test_platform": "EditMode", "test_filter": FILTER},
            f"arguments were not derived from durable state: {decision.arguments}")
    require(provider.last_usage == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "authority": "deterministic_host_single_action",
    }, f"usage accounting did not record a zero-token host action: {provider.last_usage}")


def test_acquire_agent_lease_invokes_no_provider() -> None:
    observed = observation(
        next_action="acquire_agent_lease",
        state="agent_ready",
        plan=editmode_plan(),
    )
    selected = allowed_actions_for(observed, (), _DOWNSTREAM_ACTIONS)
    require(selected == ("acquire_agent_lease",),
            f"the host did not force one action: {selected}")

    decision, provider = decide(observed)
    require(provider.provider_calls == [],
            f"the provider was invoked for a forced action: {provider.provider_calls}")
    require(decision.action == "acquire_agent_lease", decision.action)
    require(set(decision.arguments) == {"planned_approach", "expected_validation"},
            f"lease arguments are not the exact contract: {sorted(decision.arguments)}")
    for name, value in decision.arguments.items():
        require(isinstance(value, str) and value.strip(), f"{name} is not usable prose")
    require(provider.last_usage == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "authority": "deterministic_host_single_action",
    }, f"usage accounting did not record a zero-token host action: {provider.last_usage}")


# ------------------------------------- 3: arguments come only from durable state


def test_unity_arguments_come_only_from_the_committed_plan() -> None:
    plan = {
        "required_test_platforms": ["EditMode", "PlayMode"],
        "test_filters": {"EditMode": FILTER, "PlayMode": PLAYMODE_FILTER},
        "authority": "committed_validation_policy",
        "policy_sha256": "f" * 64,
    }
    # Nothing validated yet: the first outstanding platform in committed order.
    first = forced_action_arguments(
        "run_authoritative_unity_test",
        observation(next_action="run_authoritative_unity_tests", plan=plan),
    )
    require(first == {"test_platform": "EditMode", "test_filter": FILTER}, str(first))

    # Durable evidence for EditMode moves the derivation to the next platform.
    second = forced_action_arguments(
        "run_authoritative_unity_test",
        observation(
            next_action="run_authoritative_unity_tests",
            plan=plan,
            manifests=[{"test_platform": "EditMode", "test_filter": FILTER}],
        ),
    )
    require(second == {"test_platform": "PlayMode", "test_filter": PLAYMODE_FILTER},
            str(second))

    # The derivation is a pure function of durable state, so it is repeatable.
    require(
        forced_action_arguments(
            "run_authoritative_unity_test",
            observation(next_action="run_authoritative_unity_tests", plan=plan),
        )
        == first,
        "the derivation is not deterministic",
    )


def test_lease_prose_names_only_durable_facts() -> None:
    arguments = forced_action_arguments(
        "acquire_agent_lease",
        observation(
            next_action="acquire_agent_lease",
            state="agent_ready",
            plan=editmode_plan(),
        ),
    )
    require(TASK in arguments["planned_approach"], arguments["planned_approach"])
    require("delivery_evidence" in arguments["planned_approach"],
            arguments["planned_approach"])
    require(FILTER in arguments["expected_validation"],
            "the delivery-evidence lease did not name the committed filter")

    closeout = forced_action_arguments(
        "acquire_agent_lease",
        observation(
            next_action="acquire_agent_lease",
            state="agent_ready",
            phase="merge_closeout",
        ),
    )
    require("Merge closeout" in closeout["expected_validation"],
            closeout["expected_validation"])
    require(closeout != arguments, "both phases produced identical lease prose")


# --------------------------------- 4: missing/ambiguous/invalid state fails closed


def test_underdetermined_unity_arguments_fail_closed() -> None:
    for label, observed in (
        (
            "no committed plan",
            observation(next_action="run_authoritative_unity_tests"),
        ),
        (
            "malformed platform list",
            observation(
                next_action="run_authoritative_unity_tests",
                plan={"required_test_platforms": [], "test_filters": {}},
            ),
        ),
        (
            "non-string platform",
            observation(
                next_action="run_authoritative_unity_tests",
                plan={"required_test_platforms": [7], "test_filters": {}},
            ),
        ),
        (
            "missing filter",
            observation(
                next_action="run_authoritative_unity_tests",
                plan={"required_test_platforms": ["EditMode"], "test_filters": {}},
            ),
        ),
        (
            "blank filter",
            observation(
                next_action="run_authoritative_unity_tests",
                plan={
                    "required_test_platforms": ["EditMode"],
                    "test_filters": {"EditMode": "   "},
                },
            ),
        ),
        (
            "every platform already validated",
            observation(
                next_action="run_authoritative_unity_tests",
                plan=editmode_plan(),
                manifests=[{"test_platform": "EditMode", "test_filter": FILTER}],
            ),
        ),
    ):
        exc = rejects(
            lambda o=observed: forced_action_arguments(
                "run_authoritative_unity_test", o
            )
        )
        require("refusing" in str(exc) or "redundant" in str(exc),
                f"{label}: unexpected refusal {exc}")


def test_underdetermined_state_never_reaches_the_provider() -> None:
    """Fail closed means raise, not fall back to an invented provider value."""
    observed = observation(
        next_action="run_authoritative_unity_tests",
        plan={"required_test_platforms": ["EditMode"], "test_filters": {}},
    )
    calls: list[tuple[str, ...]] = []
    original = determinism._ORIGINALS["provider_decide"]

    def counted(_self, *, task_id, turn, prompt, allowed_actions):
        calls.append(tuple(allowed_actions))
        return SupervisorDecision(task_id, "record_pipeline_blocker", {}, "provider ran")

    determinism._ORIGINALS["provider_decide"] = counted
    try:
        rejects(
            lambda: _patched_render_supervisor_prompt(
                task_id=TASK,
                goal_and_rules="rules",
                observation=observed,
                history=(),
                actions=_DOWNSTREAM_ACTIONS,
            )
        )
    finally:
        determinism._ORIGINALS["provider_decide"] = original
    require(calls == [], f"an underdetermined forced action reached the provider: {calls}")


# ------------------------- 5: judgmental delivery-review decisions still consult


def test_judgmental_actions_still_consult_the_provider() -> None:
    """A genuinely judgmental state keeps its provider turn.

    `create_delivery_review_proposal` needs the reviewer's own summary text, so
    the host must not manufacture it. This proves the change removed only calls
    that bought nothing.
    """
    observed = observation(next_action="create_delivery_review_proposal")
    selected = allowed_actions_for(observed, (), _DOWNSTREAM_ACTIONS)
    require(selected == ("delivery_review_facts",),
            f"unexpected narrowing: {selected}")
    require(
        forced_action_arguments("create_delivery_review_proposal", observed) is None,
        "a judgmental action was treated as host-derivable",
    )

    history = [{"action": "delivery_review_facts", "result": {"status": "ok"}}]
    proposal_selected = allowed_actions_for(observed, history, _DOWNSTREAM_ACTIONS)
    require(proposal_selected == ("create_delivery_review_proposal",),
            f"unexpected proposal narrowing: {proposal_selected}")

    _patched_render_supervisor_prompt(
        task_id=TASK,
        goal_and_rules="rules",
        observation=observed,
        history=history,
        actions=_DOWNSTREAM_ACTIONS,
    )
    provider = object.__new__(CodexDockerDecisionProvider)
    provider.last_usage = None
    calls: list[tuple[str, ...]] = []
    original = determinism._ORIGINALS["provider_decide"]

    def counted(_self, *, task_id, turn, prompt, allowed_actions):
        calls.append(tuple(allowed_actions))
        return SupervisorDecision(
            task_id, "create_delivery_review_proposal", {"summary": "s"}, "judged"
        )

    determinism._ORIGINALS["provider_decide"] = counted
    try:
        decision = _patched_provider_decide(
            provider,
            task_id=TASK,
            turn=1,
            prompt="judgment required",
            allowed_actions=tuple(_DOWNSTREAM_ACTIONS),
        )
    finally:
        determinism._ORIGINALS["provider_decide"] = original
    require(len(calls) == 1,
            f"a judgmental action lost its provider turn: {calls}")
    require(decision.action == "create_delivery_review_proposal", decision.action)


# --------------------------- 6: GUARD - the existing zero-argument path is intact


def test_guard_zero_argument_actions_still_bypass_the_provider() -> None:
    """GUARD: the pre-existing zero-argument short-circuit is unchanged."""
    observed = observation(next_action="create_delivery_review_proposal")
    decision, provider = decide(observed)
    require(provider.provider_calls == [],
            f"a zero-argument action regressed to the provider: {provider.provider_calls}")
    require(decision.action == "delivery_review_facts", decision.action)
    require(decision.arguments == {}, "a zero-argument action invented arguments")


def test_guard_an_unnarrowed_menu_still_consults_the_provider() -> None:
    """GUARD: the short-circuit still depends entirely on host narrowing."""
    _ALLOWED_ACTION_CONTEXT.set(None)
    determinism._FORCED_ARGUMENTS_CONTEXT.set(None)
    provider = object.__new__(CodexDockerDecisionProvider)
    provider.last_usage = None
    calls: list[tuple[str, ...]] = []
    original = determinism._ORIGINALS["provider_decide"]

    def counted(_self, *, task_id, turn, prompt, allowed_actions):
        calls.append(tuple(allowed_actions))
        return SupervisorDecision(task_id, "delivery_review_facts", {}, "provider chose")

    determinism._ORIGINALS["provider_decide"] = counted
    try:
        _patched_provider_decide(
            provider,
            task_id=TASK,
            turn=1,
            prompt="no narrowing context",
            allowed_actions=tuple(_DOWNSTREAM_ACTIONS),
        )
    finally:
        determinism._ORIGINALS["provider_decide"] = original
    require(len(calls) == 1, f"the provider was skipped without narrowing: {calls}")


def test_a_forced_derivation_cannot_be_applied_to_another_action() -> None:
    """Derived arguments are keyed to the exact action they came from."""
    observed = observation(
        next_action="run_authoritative_unity_tests", plan=editmode_plan()
    )
    _patched_render_supervisor_prompt(
        task_id=TASK,
        goal_and_rules="rules",
        observation=observed,
        history=(),
        actions=_DOWNSTREAM_ACTIONS,
    )
    forced = determinism._FORCED_ARGUMENTS_CONTEXT.get()
    require(forced is not None and forced[0] == "run_authoritative_unity_test",
            f"the derivation was not keyed to its action: {forced}")

    provider = object.__new__(CodexDockerDecisionProvider)
    provider.last_usage = None
    calls: list[tuple[str, ...]] = []
    original = determinism._ORIGINALS["provider_decide"]

    def counted(_self, *, task_id, turn, prompt, allowed_actions):
        calls.append(tuple(allowed_actions))
        return SupervisorDecision(task_id, "record_pipeline_blocker", {}, "provider ran")

    determinism._ORIGINALS["provider_decide"] = counted
    try:
        # A different sole action must not inherit the Unity arguments.
        _patched_provider_decide(
            provider,
            task_id=TASK,
            turn=1,
            prompt="different action",
            allowed_actions=("record_pipeline_blocker",),
        )
    finally:
        determinism._ORIGINALS["provider_decide"] = original
    require(len(calls) == 1,
            "another action inherited a derivation it did not own")


# --------------------------------------------------------------------- main


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_")
        and callable(value)
        and getattr(value, "__module__", None) == __name__
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            FAILURES.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    if FAILURES:
        print(f"forced action arguments tests: FAIL ({len(FAILURES)})")
        return 1
    print(f"forced action arguments tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
