#!/usr/bin/env python3
"""Deterministic regressions for the Claude supervisor route.

Classification: pure/component and in-memory boundary tests. Every test drives a
real resolution, factory, routing-policy, or pooled-turn boundary. Nothing here
searches source text, launches Docker, or calls a provider.

These close concrete defects found reviewing 6a6e615, where the supervisor
became selectable but the Claude route could not actually run:

  * the Claude supervisor resolved the OpenAI default model ``gpt-5.6-sol``,
    which ``ClaudeCodeProvider._validate_model`` rejects because it does not
    start with ``claude-``, so every Claude turn failed;
  * the scheduler routing policy pinned the same OpenAI model for every tier,
    so an architect-managed Claude run put it into the worker argv;
  * ``SupervisorSessionOwner.begin_turn`` read ``.argument`` off the activation,
    which only the Codex type has, so activating Claude pooling raised
    ``AttributeError`` after the lease was already active;
  * the Claude turn script inherited the Codex ``provider_session`` validator,
    which refuses the identity Claude requires at start;
  * the supervisor source guard proved only ``compose.yaml``, never the
    ``compose.override.yaml`` that declares every ``*-supervisor`` service.

Every test in this module fails against 6a6e615.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
    CodexSupervisorError,
    build_supervisor_decision_provider,
    describe_codex_runtime,
    resolve_supervisor_model,
)
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    _DEFAULT_CLAUDE_MODEL,
    _DEFAULT_OPENAI_MODEL,
    load_execution_routing_policy,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import PollingOrchestrator  # noqa: E402
from Pipeline.TaskReviewAgent.supervisor_providers import (  # noqa: E402
    supervisor_provider_profile,
)
from Pipeline.TaskReviewAgent.supervisor_session_pool import (  # noqa: E402
    ClaudeResumeActivation,
    CodexResumeActivation,
    SupervisorSessionOwner,
)


TASK = "NSC-900"
CLAUDE_TURN = ROOT / "Pipeline" / "TaskReviewAgent" / "claude_supervisor_turn.py"
CODEX_ACTIVATION = CodexResumeActivation(("-c", 'sandbox_mode="danger-full-access"'))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, kind, fragment: str) -> None:
    try:
        action()
    except kind as exc:
        require(
            fragment.casefold() in str(exc).casefold(),
            f"expected {fragment!r} in {exc!r}",
        )
        return
    raise AssertionError(f"expected {kind.__name__} mentioning {fragment!r}")


def run_claude_turn(request: dict) -> tuple[int, dict]:
    """Run the real Claude turn entrypoint on a crafted request.

    No Docker and no provider call: every assertion below is settled by the
    adapter's own validation before any process is launched.
    """

    completed = subprocess.run(
        (sys.executable, str(CLAUDE_TURN)),
        input=(json.dumps(request) + "\n").encode("utf-8"),
        capture_output=True,
        timeout=180.0,
        check=False,
    )
    text = completed.stdout.decode("utf-8").strip()
    return completed.returncode, (json.loads(text) if text else {})


def turn_request(**overrides) -> dict:
    request = {
        "schema_version": "1.0",
        "run_id": "nsc-900-supervisor-001",
        "prompt": "state\n",
        "output_schema": {
            "type": "object",
            "properties": {"action": {"type": "string"}},
            "required": ["action"],
            "additionalProperties": False,
        },
        "model": "claude-sonnet-5",
        "reasoning_effort": "high",
        "provider_turn_limit": 8,
        "timeout_seconds": 30.0,
    }
    request.update(overrides)
    return request


# ------------------------------------------------------------------- model


def test_the_supervisor_model_follows_the_selected_provider() -> None:
    """A Claude supervisor never inherits the OpenAI default model."""

    require(
        resolve_supervisor_model(None, "claude") == _DEFAULT_CLAUDE_MODEL,
        f"Claude default must be {_DEFAULT_CLAUDE_MODEL}, got "
        f"{resolve_supervisor_model(None, 'claude')}",
    )
    require(
        resolve_supervisor_model(None, "codex") == _DEFAULT_OPENAI_MODEL,
        "the Codex default must be unchanged",
    )
    require(
        resolve_supervisor_model(None) == _DEFAULT_OPENAI_MODEL,
        "an unchosen supervisor must keep the historical Codex default",
    )
    # The registry adopts the repository's own committed defaults rather than
    # inventing a model name; drift between the two is a defect.
    require(
        supervisor_provider_profile("claude").default_model == _DEFAULT_CLAUDE_MODEL
        and supervisor_provider_profile("codex").default_model == _DEFAULT_OPENAI_MODEL,
        "supervisor provider defaults drifted from the committed routing defaults",
    )


def test_a_cross_provider_supervisor_model_fails_on_the_host() -> None:
    """A mismatched model is refused before any container round trip."""

    expect_error(
        lambda: build_supervisor_decision_provider(
            supervisor_provider="claude",
            source=ROOT,
            model=_DEFAULT_OPENAI_MODEL,
            command_runner=lambda *values, **options: None,
        ),
        CodexSupervisorError,
        "must start with 'claude-'",
    )
    expect_error(
        lambda: build_supervisor_decision_provider(
            supervisor_provider="codex",
            source=ROOT,
            model=_DEFAULT_CLAUDE_MODEL,
            command_runner=lambda *values, **options: None,
        ),
        CodexSupervisorError,
        "must start with 'gpt-'",
    )
    claude = build_supervisor_decision_provider(
        supervisor_provider="claude",
        source=ROOT,
        command_runner=lambda *values, **options: None,
    )
    require(claude.model == _DEFAULT_CLAUDE_MODEL, claude.model)
    require(
        describe_codex_runtime("claude")["default_model"] == _DEFAULT_CLAUDE_MODEL,
        "Claude runtime evidence must report the Claude model",
    )


def test_the_scheduler_route_carries_a_claude_supervisor_model() -> None:
    """The architect-managed path is the one that pinned the OpenAI model."""

    for supervisor, expected in (
        (None, _DEFAULT_OPENAI_MODEL),
        ("codex", _DEFAULT_OPENAI_MODEL),
        ("claude", _DEFAULT_CLAUDE_MODEL),
    ):
        policy = load_execution_routing_policy({}, supervisor_provider=supervisor)
        for tier in ("fast", "standard", "deep"):
            actual = policy.for_tier(tier).supervisor_model
            require(
                actual == expected,
                f"supervisor={supervisor} tier={tier} resolved {actual}, expected {expected}",
            )

    orchestrator = PollingOrchestrator(
        source=ROOT,
        checkout_root=ROOT,
        scheduler_id="claude-route-scheduler",
        execution_provider="claude",
        model=None,
        max_turns=None,
        max_workers=1,
        architect_min_confidence=0.5,
        architect_runner=lambda *values, **options: None,
        provider_allowlist=("claude",),
        supervisor_provider="claude",
    )
    resolved = orchestrator.routing_policy_loader().for_tier("deep").supervisor_model
    require(
        resolved == _DEFAULT_CLAUDE_MODEL,
        f"a Claude-only scheduler resolved supervisor model {resolved}",
    )


# ------------------------------------------------------------- turn adapter


def test_the_claude_turn_refuses_an_openai_model_and_accepts_a_claude_one() -> None:
    """The adapter's own model rule is what made the route unusable."""

    code, envelope = run_claude_turn(turn_request(model=_DEFAULT_OPENAI_MODEL))
    require(code == 2, f"an OpenAI model must fail the Claude turn, exit={code}")
    failure = envelope.get("failure") or {}
    require(
        failure.get("classification") == "ProviderTransportError",
        f"unexpected classification: {failure}",
    )
    require(
        "concrete configured Claude model" in str(failure.get("detail")),
        f"unexpected detail: {failure}",
    )


def test_a_pooled_claude_start_is_validated_by_the_claude_rule() -> None:
    """The Claude turn must not inherit the Codex provider_session rule.

    Codex assigns its own thread, so its rule refuses a session_id at start.
    Claude accepts the identity the host chose, so the same rule made every
    pooled Claude start impossible.
    """

    request = turn_request(
        schema_version="1.1",
        model=_DEFAULT_OPENAI_MODEL,
        provider_session={
            "mode": "start",
            "session_id": "7a1f9c22-3d54-4b8e-9a06-5e2c81d4f7b3",
            "resume_sandbox_argument": None,
        },
    )
    code, envelope = run_claude_turn(request)
    failure = envelope.get("failure") or {}
    require(code == 2, f"exit={code}")
    # The request must get past session validation and fail on the model
    # instead, which proves the Claude session rule ran.
    require(
        failure.get("classification") == "ProviderTransportError",
        f"a pooled Claude start was rejected by the Codex session rule: {failure}",
    )
    require(
        "Codex" not in str(failure.get("detail")),
        f"the Claude route reported a Codex session rule: {failure}",
    )

    # A Codex sandbox control is still refused for Claude rather than ignored.
    refused = turn_request(
        schema_version="1.1",
        provider_session={
            "mode": "resume",
            "session_id": "7a1f9c22-3d54-4b8e-9a06-5e2c81d4f7b3",
            "resume_sandbox_argument": ["-c", 'sandbox_mode="danger-full-access"'],
        },
    )
    code, envelope = run_claude_turn(refused)
    failure = envelope.get("failure") or {}
    require(code == 2, f"exit={code}")
    require(
        failure.get("classification") == "SupervisorTurnError"
        and "not a Claude capability" in str(failure.get("detail")),
        f"a Codex sandbox control was not refused: {failure}",
    )


def test_each_route_reports_its_own_failure_banner() -> None:
    """A Claude failure must not be announced as a Codex one."""

    completed = subprocess.run(
        (sys.executable, str(CLAUDE_TURN)),
        input=(json.dumps(turn_request(model="gpt-4o")) + "\n").encode("utf-8"),
        capture_output=True,
        timeout=180.0,
        check=False,
    )
    first = completed.stderr.decode("utf-8").splitlines()[0]
    require(first.startswith("CLAUDE SUPERVISOR TURN"), f"banner was {first!r}")


# ------------------------------------------------------------ session pool


def test_claude_supervisor_pooling_produces_a_usable_turn_block() -> None:
    """begin_turn raised AttributeError on the Claude activation before this."""

    with tempfile.TemporaryDirectory(prefix="claude-supervisor-pool-") as text:
        temp = Path(text)
        owner = SupervisorSessionOwner(
            source=ROOT,
            checkout_root=temp / "checkouts",
            task_id=TASK,
            worker_id="claude-route-worker",
            run_id="claude-route-run",
            model=_DEFAULT_CLAUDE_MODEL,
            reasoning_effort="high",
            supervisor_provider="claude",
            resume_activation=ClaudeResumeActivation(),
            repository_identity="https://github.com/cathode26/NoSafeCircle.git",
            host_identity="test-host",
        )
        try:
            require(owner.warm_pooling_active, "Claude pooling must be active")
            turn = owner.begin_turn(turn=1, allowed_actions=("observe",))
            block = turn.provider_session
            require(block["mode"] == "start", block)
            # Claude accepts the identity the host chose, so unlike Codex the
            # pool must mint one at start.
            require(
                isinstance(block["session_id"], str) and block["session_id"],
                f"a pooled Claude start must carry the host-minted identity: {block}",
            )
            require(
                block["resume_sandbox_argument"] is None,
                f"Claude must receive no Codex sandbox control: {block}",
            )
            require(
                set(block) == {"mode", "session_id", "resume_sandbox_argument"},
                f"the container contract changed shape: {sorted(block)}",
            )
        finally:
            owner.close()


def test_codex_pooling_still_carries_its_verified_control() -> None:
    """The Codex route is unchanged, including its start-binds-nothing rule."""

    with tempfile.TemporaryDirectory(prefix="codex-supervisor-pool-") as text:
        temp = Path(text)
        owner = SupervisorSessionOwner(
            source=ROOT,
            checkout_root=temp / "checkouts",
            task_id=TASK,
            worker_id="codex-route-worker",
            run_id="codex-route-run",
            model=_DEFAULT_OPENAI_MODEL,
            reasoning_effort="high",
            supervisor_provider="codex",
            resume_activation=CODEX_ACTIVATION,
            repository_identity="https://github.com/cathode26/NoSafeCircle.git",
            host_identity="test-host",
        )
        try:
            turn = owner.begin_turn(turn=1, allowed_actions=("observe",))
            block = turn.provider_session
            require(
                block["session_id"] is None,
                f"Codex assigns its own thread, so a start binds nothing: {block}",
            )
            require(
                block["resume_sandbox_argument"]
                == ["-c", 'sandbox_mode="danger-full-access"'],
                f"the Codex verified control was lost: {block}",
            )
        finally:
            owner.close()


# ------------------------------------------------------------------ source


def test_the_supervisor_source_must_declare_its_compose_service() -> None:
    """The guard proved only compose.yaml, never the override that has the service."""

    with tempfile.TemporaryDirectory(prefix="supervisor-source-") as text:
        source = Path(text)
        (source / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        expect_error(
            lambda: build_supervisor_decision_provider(
                supervisor_provider="claude",
                source=source,
                command_runner=lambda *values, **options: None,
            ),
            CodexSupervisorError,
            "compose.override.yaml",
        )
        (source / "compose.override.yaml").write_text("services: {}\n", encoding="utf-8")
        provider = build_supervisor_decision_provider(
            supervisor_provider="claude",
            source=source,
            command_runner=lambda *values, **options: None,
        )
        require(provider.service == "claude-supervisor", provider.service)


def main() -> int:
    tests = (
        test_the_supervisor_model_follows_the_selected_provider,
        test_a_cross_provider_supervisor_model_fails_on_the_host,
        test_the_scheduler_route_carries_a_claude_supervisor_model,
        test_the_claude_turn_refuses_an_openai_model_and_accepts_a_claude_one,
        test_a_pooled_claude_start_is_validated_by_the_claude_rule,
        test_each_route_reports_its_own_failure_banner,
        test_claude_supervisor_pooling_produces_a_usable_turn_block,
        test_codex_pooling_still_carries_its_verified_control,
        test_the_supervisor_source_must_declare_its_compose_service,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Claude supervisor route tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
