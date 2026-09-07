#!/usr/bin/env python3
"""Deterministic tests for ExecutionCrew's opt-in provider-session seam.

Classification: pure/component tests over the crew's provider construction and
role-binding resolution. No provider process, container, network call, or
repository file is involved. Every test proves an explicit regression-only
invariant: a run without pool bindings behaves exactly as before, and a run with
one binds the session to that exact provider and that exact role.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    ProviderSessionBinding,
    ProviderSessionLedger,
)
from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    CrewBlocked,
    construct_real_provider,
    crew_provider_identifier,
    resolve_role_session,
)

SESSION_A = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
CREW_ROLES = ("contract_locality_auditor", "implementer", "test_author", "validator")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action, expected: type[BaseException]) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def binding(role: str = "implementer", provider: str = "claude-code",
            mode: str = "resume") -> ProviderSessionBinding:
    return ProviderSessionBinding(provider, role, mode, SESSION_A)


def test_no_bindings_leaves_every_role_ephemeral() -> None:
    for role in CREW_ROLES:
        require(resolve_role_session(None, role, "claude-code") is None, role)
        require(resolve_role_session({}, role, "claude-code") is None, role)
        require(
            resolve_role_session({"validator": binding("validator")}, "implementer", "claude-code")
            is None,
            "an unrelated role's binding leaked into implementer",
        )
    with tempfile.TemporaryDirectory(prefix="crew-session-test-") as text:
        repo = Path(text) / "repo"
        repo.mkdir()
        for name in ("claude", "codex"):
            provider = construct_real_provider(name, repo, False)
            require(provider.session is None, f"{name} defaulted to a persistent session")
            require(provider.session_ledger is None, f"{name} defaulted to a ledger")
        codex = construct_real_provider("codex", repo, False)
        require(codex.resume_sandbox_argument is None, "codex defaulted to a resume sandbox override")


def test_binding_is_bound_to_its_exact_role() -> None:
    for owner in CREW_ROLES:
        bindings = {owner: binding(owner)}
        require(resolve_role_session(bindings, owner, "claude-code") is not None, owner)
        # A binding filed under one role but naming another must fail closed
        # rather than silently continuing that role's conversation.
        for other in CREW_ROLES:
            if other == owner:
                continue
            blocked = rejects(
                lambda owner=owner, other=other: resolve_role_session(
                    {other: binding(owner)}, other, "claude-code"
                ),
                CrewBlocked,
            )
            require(f"cannot be used for role {other!r}" in str(blocked), str(blocked))


def test_binding_is_bound_to_its_exact_provider() -> None:
    blocked = rejects(
        lambda: resolve_role_session({"implementer": binding()}, "implementer", "openai-codex"),
        CrewBlocked,
    )
    require("cannot be used through 'openai-codex'" in str(blocked), str(blocked))
    blocked = rejects(
        lambda: resolve_role_session(
            {"implementer": binding(provider="openai-codex")}, "implementer", "claude-code"
        ),
        CrewBlocked,
    )
    require("cannot be used through 'claude-code'" in str(blocked), str(blocked))
    require(crew_provider_identifier("claude") == "claude-code", "claude identity drifted")
    require(crew_provider_identifier("codex") == "openai-codex", "codex identity drifted")
    rejects(lambda: crew_provider_identifier("gemini"), CrewBlocked)
    rejects(
        lambda: resolve_role_session({"implementer": "3f2504e0"}, "implementer", "claude-code"),
        CrewBlocked,
    )


def test_provider_construction_carries_the_session_and_ledger() -> None:
    with tempfile.TemporaryDirectory(prefix="crew-session-test-") as text:
        repo = Path(text) / "repo"
        repo.mkdir()
        ledger = ProviderSessionLedger()
        claude = construct_real_provider(
            "claude", repo, True, session=binding(), session_ledger=ledger
        )
        require(claude.session is not None and claude.session.session_id == SESSION_A, "claude session lost")
        require(claude.session_ledger is ledger, "claude ledger lost")
        require(claude.live_observer is not None, "claude lost its live renderer")
        codex_ledger = ProviderSessionLedger()
        codex = construct_real_provider(
            "codex", repo, True, openai_reasoning_effort="xhigh",
            session=binding(provider="openai-codex"), session_ledger=codex_ledger,
            codex_resume_sandbox_argument=("-c", 'sandbox_mode="danger-full-access"'),
        )
        require(codex.session_ledger is codex_ledger, "codex ledger lost")
        require(codex.reasoning_effort == "xhigh", "codex reasoning effort lost")
        require(
            codex.resume_sandbox_argument == ("-c", 'sandbox_mode="danger-full-access"'),
            "codex resume sandbox argument lost",
        )


TESTS = (
    test_no_bindings_leaves_every_role_ephemeral,
    test_binding_is_bound_to_its_exact_role,
    test_binding_is_bound_to_its_exact_provider,
    test_provider_construction_carries_the_session_and_ledger,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    for test in TESTS:
        if selected and test.__name__ not in selected:
            continue
        test()
        print(f"PASS {test.__name__}")
    print("crew_provider_session_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
