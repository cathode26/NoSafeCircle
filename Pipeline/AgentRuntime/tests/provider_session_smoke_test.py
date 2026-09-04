#!/usr/bin/env python3
"""Deterministic tests for the opt-in provider-neutral persistent-session substrate.

Classification: pure/component tests over the Claude and Codex adapters with a
fake process runner and fake provider transcripts. No live provider call, no
network, no container, and no repository file is touched. Every test proves an
explicit regression-only invariant of the session contract.

The load-bearing claims are: a caller that supplies no binding stays byte-for-byte
ephemeral; a persistent invocation names exactly one conversation by exact UUID;
identity is confirmed from the provider transcript rather than the exit code; a
session cannot cross providers or roles; and a resumed assignment still carries
its own complete authority while explicitly revoking the previous one.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.contracts import (  # noqa: E402
    AgentInvocationRequest,
    Budgets,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.process_runner import ProcessResult  # noqa: E402
from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    PROVIDER_SESSION_SCHEMA_VERSION,
    RESUMED_AUTHORITY_NOTICE,
    ProviderSessionBinding,
    ProviderSessionConfirmation,
    ProviderSessionError,
    ProviderSessionLedger,
    prompt_with_resumed_authority,
    require_compatible_binding,
    validate_session_id,
)
from Pipeline.AgentRuntime.providers.base import (  # noqa: E402
    ProviderOutputInvalid,
    ProviderRequestRejected,
)
from Pipeline.AgentRuntime.providers.claude_code import ClaudeCodeProvider  # noqa: E402
from Pipeline.AgentRuntime.providers.openai_codex import (  # noqa: E402
    CODEX_RESUME_SANDBOX_BLOCKER,
    OpenAICodexProvider,
)

SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}
SESSION_A = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
SESSION_B = "9c858901-8a57-4791-81fe-4c455b099bc9"
CLAUDE_MODEL = "claude-sonnet-4-5-20260101"
CODEX_MODEL = "gpt-concrete-1"
WRITE_CAPABILITIES = ("repository_read", "repository_search", "repository_write")
# An operator-verified fragment that reproduces the start-time sandbox policy
# through an option `codex exec resume` accepts. The adapter refuses to resume
# without one; see CODEX_RESUME_SANDBOX_BLOCKER.
VERIFIED_RESUME_SANDBOX = ("-c", 'sandbox_mode="danger-full-access"')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action: Any, expected: type[BaseException]) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def request(
    *,
    role: str = "implementer",
    capabilities: tuple[str, ...] = (),
    boundaries: WriteBoundaries | None = None,
    budgets: Budgets = Budgets(7, 12.5),
    prompt: str = "Return JSON.",
    run_id: str = "provider-session-test",
) -> AgentInvocationRequest:
    if boundaries is None:
        boundaries = (
            WriteBoundaries(("Assets/Now.cs",), ("Assets/Denied.cs",))
            if "repository_write" in capabilities
            else WriteBoundaries((), ())
        )
    return AgentInvocationRequest(
        "1.0", run_id, role, prompt, (), capabilities, boundaries,
        SCHEMA, "standard", budgets, "session-config",
    )


def binding(
    provider: str = "claude-code",
    role: str = "implementer",
    mode: str = "start",
    session_id: str | None = SESSION_A,
) -> ProviderSessionBinding:
    return ProviderSessionBinding(provider, role, mode, session_id)


# --------------------------------------------------------------- Claude harness


def claude_transcript(**changes: Any) -> bytes:
    envelope: dict[str, Any] = {
        "type": "result",
        "is_error": False,
        "subtype": "success",
        "terminal_reason": "completed",
        "structured_output": {"message": "ok"},
    }
    envelope.update(changes)
    for key, value in list(envelope.items()):
        if value is _OMIT:
            del envelope[key]
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8") + b"\n"


_OMIT = object()


class ClaudeRunner:
    def __init__(self, stdout: bytes | None = None) -> None:
        self.stdout = claude_transcript() if stdout is None else stdout
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: Any, *, stdin: bytes, cwd: Path, timeout_seconds: float,
            **_extra: Any) -> ProcessResult:
        args = tuple(argv)
        self.calls.append(
            {"argv": args, "stdin": stdin, "cwd": Path(cwd), "timeout": timeout_seconds}
        )
        return ProcessResult(args, 0, self.stdout, b"", 0.25)


def claude_provider(temp: Path, runner: ClaudeRunner, **values: Any) -> ClaudeCodeProvider:
    return ClaudeCodeProvider(
        process_runner=runner, temporary_directory_parent=temp,
        repository_root=temp / "repo", **values,
    )


# ---------------------------------------------------------------- Codex harness


def codex_transcript(*, thread_ids: tuple[Any, ...] = (SESSION_A,)) -> bytes:
    lines = [
        json.dumps({"type": "thread.started", "thread_id": value}, separators=(",", ":"))
        for value in thread_ids
    ]
    lines.append(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 3, "output_tokens": 4,
                          "reasoning_output_tokens": 5, "total_tokens": 12},
            },
            separators=(",", ":"),
        )
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


class CodexRunner:
    def __init__(self, stdout: bytes | None = None, *, final: str = '{"message":"ok"}') -> None:
        self.stdout = codex_transcript() if stdout is None else stdout
        self.final = final
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: Any, *, stdin: bytes, cwd: Path, timeout_seconds: float,
            **_extra: Any) -> ProcessResult:
        args = tuple(argv)
        self.calls.append(
            {"argv": args, "stdin": stdin, "cwd": Path(cwd), "timeout": timeout_seconds}
        )
        Path(args[args.index("--output-last-message") + 1]).write_text(
            self.final, encoding="utf-8"
        )
        return ProcessResult(args, 0, self.stdout, b"", 0.1)


def codex_provider(temp: Path, runner: CodexRunner, *, writable: bool = False,
                   **values: Any) -> OpenAICodexProvider:
    return OpenAICodexProvider(
        process_runner=runner, temporary_directory_parent=temp / "outside",
        repository_root=temp / "repo",
        externally_isolated_writable_repository=writable,
        externally_enforced_read_only_repository=not writable,
        **values,
    )


def workspace() -> tempfile.TemporaryDirectory[str]:
    handle = tempfile.TemporaryDirectory(prefix="provider-session-test-")
    root = Path(handle.name)
    (root / "repo").mkdir()
    (root / "outside").mkdir()
    return handle


def flag_values(argv: tuple[str, ...], name: str) -> tuple[str, ...]:
    return tuple(argv[index + 1] for index, item in enumerate(argv) if item == name)


def stable_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Mask the per-invocation temporary file paths Codex passes by value."""

    masked = list(argv)
    for name in ("--output-schema", "--output-last-message"):
        if name in masked:
            masked[masked.index(name) + 1] = f"<{name}>"
    return tuple(masked)


# ------------------------------------------------- 1/2: default stays ephemeral


def test_guard_claude_default_call_is_unchanged_and_ephemeral() -> None:
    """Guard: passes before and after. Proves the default path did not move."""

    with workspace() as text:
        temp = Path(text)
        plain = ClaudeRunner()
        claude_provider(temp, plain).invoke(request(), CLAUDE_MODEL)
        argv = plain.calls[0]["argv"]
        require("--no-session-persistence" in argv, str(argv))
        require("--session-id" not in argv and "--resume" not in argv, str(argv))
        require(
            RESUMED_AUTHORITY_NOTICE not in plain.calls[0]["stdin"].decode("utf-8"),
            "ephemeral prompt carried a resumed-authority notice",
        )


def test_guard_codex_default_call_is_unchanged_and_ephemeral() -> None:
    """Guard: passes before and after. Proves the default path did not move."""

    with workspace() as text:
        temp = Path(text)
        plain = CodexRunner()
        codex_provider(temp, plain).invoke(request(), CODEX_MODEL)
        argv = plain.calls[0]["argv"]
        require(argv[1] == "exec" and argv[2] == "--ephemeral", str(argv))
        require("resume" not in argv and "--last" not in argv, str(argv))
        require(
            ("--sandbox", "danger-full-access") == argv[argv.index("--sandbox"):argv.index("--sandbox") + 2],
            str(argv),
        )
        require(
            RESUMED_AUTHORITY_NOTICE not in plain.calls[0]["stdin"].decode("utf-8"),
            "ephemeral prompt carried a resumed-authority notice",
        )


def test_explicit_none_binding_is_indistinguishable_from_omitting_it() -> None:
    with workspace() as text:
        temp = Path(text)
        plain = ClaudeRunner()
        claude_provider(temp, plain).invoke(request(), CLAUDE_MODEL)
        explicit = ClaudeRunner()
        claude_provider(temp, explicit, session=None).invoke(request(), CLAUDE_MODEL)
        require(
            explicit.calls[0]["argv"] == plain.calls[0]["argv"],
            "explicit None changed the Claude argv",
        )
        plain_codex = CodexRunner()
        codex_provider(temp, plain_codex).invoke(request(), CODEX_MODEL)
        explicit_codex = CodexRunner()
        codex_provider(temp, explicit_codex, session=None).invoke(request(), CODEX_MODEL)
        require(
            stable_argv(explicit_codex.calls[0]["argv"])
            == stable_argv(plain_codex.calls[0]["argv"]),
            "explicit None changed the Codex argv",
        )


# ---------------------------------------------------- 3/4: Claude start, resume


def test_claude_persistent_start_emits_only_session_id() -> None:
    with workspace() as text:
        temp = Path(text)
        runner = ClaudeRunner(claude_transcript(session_id=SESSION_A))
        ledger = ProviderSessionLedger()
        provider = claude_provider(temp, runner, session=binding(), session_ledger=ledger)
        provider.invoke(request(), CLAUDE_MODEL)
        argv = runner.calls[0]["argv"]
        require(flag_values(argv, "--session-id") == (SESSION_A,), str(argv))
        require("--resume" not in argv, "start emitted a resume flag")
        require("--no-session-persistence" not in argv, "persistent start disabled persistence")
        confirmed = ledger.confirmed
        require(confirmed is not None and confirmed.session_id == SESSION_A, str(confirmed))
        require(confirmed.mode == "start" and confirmed.role == "implementer", str(confirmed))
        require(
            RESUMED_AUTHORITY_NOTICE not in runner.calls[0]["stdin"].decode("utf-8"),
            "a fresh start carried a resumed-authority notice",
        )


def test_claude_resume_emits_only_resume_with_the_exact_uuid() -> None:
    with workspace() as text:
        temp = Path(text)
        runner = ClaudeRunner(claude_transcript(session_id=SESSION_A))
        ledger = ProviderSessionLedger()
        provider = claude_provider(
            temp, runner, session=binding(mode="resume"), session_ledger=ledger
        )
        provider.invoke(request(), CLAUDE_MODEL)
        argv = runner.calls[0]["argv"]
        require(flag_values(argv, "--resume") == (SESSION_A,), str(argv))
        require("--session-id" not in argv, "resume also emitted --session-id")
        require("--no-session-persistence" not in argv, "persistent resume disabled persistence")
        require(argv.count("--resume") == 1, "resume flag repeated")
        require(ledger.confirmed is not None and ledger.confirmed.mode == "resume", str(ledger.confirmed))


# ----------------------------------------------------- 5/6: Codex start, resume


def test_codex_persistent_start_omits_ephemeral_and_captures_its_uuid() -> None:
    with workspace() as text:
        temp = Path(text)
        runner = CodexRunner()
        ledger = ProviderSessionLedger()
        provider = codex_provider(
            temp, runner,
            session=binding("openai-codex", session_id=None),
            session_ledger=ledger,
        )
        provider.invoke(request(), CODEX_MODEL)
        argv = runner.calls[0]["argv"]
        require("--ephemeral" not in argv, "persistent start kept --ephemeral")
        require("resume" not in argv and "--last" not in argv, str(argv))
        require(
            ("--sandbox", "danger-full-access") == argv[argv.index("--sandbox"):argv.index("--sandbox") + 2],
            "persistent start lost its sandbox policy",
        )
        confirmed = ledger.confirmed
        require(confirmed is not None and confirmed.session_id == SESSION_A, str(confirmed))
        require(confirmed.provider_identifier == "openai-codex", str(confirmed))
        # Codex names the conversation, so binding a caller-chosen ID is refused.
        rejected = rejects(
            lambda: codex_provider(
                temp, CodexRunner(), session=binding("openai-codex", session_id=SESSION_A)
            ).invoke(request(), CODEX_MODEL),
            ProviderRequestRejected,
        )
        require("assigns its own thread UUID" in str(rejected), str(rejected))


def test_codex_resume_uses_the_exact_uuid_and_never_last() -> None:
    with workspace() as text:
        temp = Path(text)
        runner = CodexRunner()
        ledger = ProviderSessionLedger()
        provider = codex_provider(
            temp, runner,
            session=binding("openai-codex", mode="resume"),
            session_ledger=ledger,
            resume_sandbox_argument=VERIFIED_RESUME_SANDBOX,
        )
        provider.invoke(request(), CODEX_MODEL)
        argv = runner.calls[0]["argv"]
        require(argv[1] == "exec" and argv[2] == "resume", str(argv))
        require(SESSION_A in argv, "resume did not name the exact session UUID")
        require("--last" not in argv, "resume used the ambiguous --last selector")
        require("--ephemeral" not in argv, "resume asked for an ephemeral session")
        require(argv[-1] == "-", "resume did not read its prompt from stdin")
        require(argv[-2] == SESSION_A, "session UUID was not the positional argument")
        require(
            list(VERIFIED_RESUME_SANDBOX) == [argv[argv.index("-c")], argv[argv.index("-c") + 1]],
            "verified resume sandbox fragment missing",
        )
        require(ledger.confirmed is not None and ledger.confirmed.session_id == SESSION_A, str(ledger.confirmed))


def test_codex_resume_fails_closed_without_a_verified_sandbox_control() -> None:
    """`codex exec resume` has no --sandbox; refusing beats silently changing policy."""

    with workspace() as text:
        temp = Path(text)
        runner = CodexRunner()
        provider = codex_provider(
            temp, runner, session=binding("openai-codex", mode="resume")
        )
        rejected = rejects(
            lambda: provider.invoke(request(), CODEX_MODEL), ProviderRequestRejected
        )
        require(str(rejected) == CODEX_RESUME_SANDBOX_BLOCKER, str(rejected))
        require(runner.calls == [], "a refused resume still launched a subprocess")


# ------------------------------------------------ 7: invalid IDs never spawn


def test_invalid_session_ids_fail_before_any_subprocess() -> None:
    ambiguous = (
        "last", "--last", "", "   ", "most-recent", "Implementer session",
        SESSION_A.upper(), SESSION_A[:-1], SESSION_A.replace("-", ""),
        f"{{{SESSION_A}}}", f"urn:uuid:{SESSION_A}", f" {SESSION_A}",
        "00000000-0000-0000-0000-000000000000", None, 7, b"3f2504e0",
    )
    for value in ambiguous:
        rejects(lambda value=value: validate_session_id(value), ProviderSessionError)
        rejects(
            lambda value=value: ProviderSessionBinding(
                "claude-code", "implementer", "resume", value
            ),
            ProviderSessionError,
        )
    # A resume with no identity at all is the ambiguous selector this forbids.
    rejects(
        lambda: ProviderSessionBinding("claude-code", "implementer", "resume", None),
        ProviderSessionError,
    )
    rejects(
        lambda: ProviderSessionBinding("claude-code", "implementer", "continue", SESSION_A),
        ProviderSessionError,
    )
    with workspace() as text:
        temp = Path(text)
        for runner, provider in (
            (ClaudeRunner(), None),
            (CodexRunner(), None),
        ):
            pass
        claude_runner = ClaudeRunner()
        rejects(
            lambda: claude_provider(
                temp, claude_runner, session=binding(role="validator")
            ).invoke(request(role="implementer"), CLAUDE_MODEL),
            ProviderRequestRejected,
        )
        require(claude_runner.calls == [], "a refused invocation launched a subprocess")


# --------------------------------- 8: transcript identity, not the exit code


def test_missing_or_mismatched_claude_identity_fails_closed() -> None:
    with workspace() as text:
        temp = Path(text)
        cases = (
            claude_transcript(),                                  # session_id absent
            claude_transcript(session_id=SESSION_B),              # different session
            claude_transcript(session_id="last"),                 # ambiguous selector
            claude_transcript(session_id=SESSION_A.upper()),      # non-canonical
            claude_transcript(session_id=None),                   # null identity
            claude_transcript(session_id=7),                      # wrong type
        )
        for index, stdout in enumerate(cases):
            runner = ClaudeRunner(stdout)
            ledger = ProviderSessionLedger()
            provider = claude_provider(
                temp, runner, session=binding(), session_ledger=ledger
            )
            rejects(lambda: provider.invoke(request(), CLAUDE_MODEL), ProviderOutputInvalid)
            require(runner.calls[0] is not None, "case did not run")
            require(ledger.confirmed is None, f"case {index} recorded an unproven identity")


def test_missing_or_mismatched_codex_identity_fails_closed() -> None:
    with workspace() as text:
        temp = Path(text)
        cases = (
            codex_transcript(thread_ids=()),                       # no session event
            codex_transcript(thread_ids=(SESSION_A, SESSION_A)),   # duplicated
            codex_transcript(thread_ids=(SESSION_A, SESSION_B)),   # contradictory
            codex_transcript(thread_ids=("thread-1",)),            # thread name
            codex_transcript(thread_ids=(None,)),                  # null identity
        )
        for index, stdout in enumerate(cases):
            runner = CodexRunner(stdout)
            ledger = ProviderSessionLedger()
            provider = codex_provider(
                temp, runner,
                session=binding("openai-codex", session_id=None),
                session_ledger=ledger,
            )
            rejects(lambda: provider.invoke(request(), CODEX_MODEL), ProviderOutputInvalid)
            require(ledger.confirmed is None, f"case {index} recorded an unproven identity")
        # A resume that observes a different conversation is equally fatal.
        runner = CodexRunner(codex_transcript(thread_ids=(SESSION_B,)))
        provider = codex_provider(
            temp, runner, session=binding("openai-codex", mode="resume"),
            resume_sandbox_argument=VERIFIED_RESUME_SANDBOX,
        )
        rejects(lambda: provider.invoke(request(), CODEX_MODEL), ProviderOutputInvalid)


# ------------------------------------------------- 9/10: provider and role walls


def test_a_session_cannot_cross_providers() -> None:
    with workspace() as text:
        temp = Path(text)
        codex_runner = CodexRunner()
        rejected = rejects(
            lambda: codex_provider(
                temp, codex_runner, session=binding("claude-code", mode="resume"),
                resume_sandbox_argument=VERIFIED_RESUME_SANDBOX,
            ).invoke(request(), CODEX_MODEL),
            ProviderRequestRejected,
        )
        require("cannot be resumed through 'openai-codex'" in str(rejected), str(rejected))
        require(codex_runner.calls == [], "cross-provider resume launched a subprocess")
        claude_runner = ClaudeRunner()
        rejected = rejects(
            lambda: claude_provider(
                temp, claude_runner, session=binding("openai-codex", mode="resume")
            ).invoke(request(), CLAUDE_MODEL),
            ProviderRequestRejected,
        )
        require("cannot be resumed through 'claude-code'" in str(rejected), str(rejected))
        require(claude_runner.calls == [], "cross-provider resume launched a subprocess")
        # The compatibility key a scheduler compares must differ by provider.
        require(
            binding("claude-code").compatibility_key()
            != binding("openai-codex", session_id=None).compatibility_key(),
            "provider is absent from the compatibility key",
        )


def test_a_session_cannot_cross_execution_crew_roles() -> None:
    roles = ("contract_locality_auditor", "implementer", "test_author", "validator")
    keys = {role: binding(role=role).compatibility_key() for role in roles}
    require(len(set(keys.values())) == len(roles), f"roles share a compatibility key: {keys}")
    with workspace() as text:
        temp = Path(text)
        for owner in roles:
            for other in roles:
                if owner == other:
                    continue
                runner = ClaudeRunner()
                rejected = rejects(
                    lambda owner=owner, other=other, runner=runner: claude_provider(
                        temp, runner, session=binding(role=owner, mode="resume")
                    ).invoke(request(role=other), CLAUDE_MODEL),
                    ProviderRequestRejected,
                )
                require(f"cannot be resumed as role {other!r}" in str(rejected), str(rejected))
                require(runner.calls == [], "cross-role resume launched a subprocess")


# ---------------------------- 11/12: current authority survives, prior expires


def test_resume_still_supplies_every_current_control() -> None:
    with workspace() as text:
        temp = Path(text)
        runner = ClaudeRunner(claude_transcript(session_id=SESSION_A))
        provider = claude_provider(
            temp, runner, session=binding(mode="resume"),
            externally_isolated_writable_repository=True,
        )
        budgets = Budgets(9, 33.5)
        current = request(
            capabilities=WRITE_CAPABILITIES, budgets=budgets, prompt="Current task only.",
            boundaries=WriteBoundaries(("Assets/Current.cs",), ("Assets/Forbidden.cs",)),
        )
        provider.invoke(current, CLAUDE_MODEL)
        call = runner.calls[0]
        argv, stdin = call["argv"], call["stdin"].decode("utf-8")
        require(flag_values(argv, "--model") == (CLAUDE_MODEL,), str(argv))
        require(flag_values(argv, "--max-turns") == ("9",), str(argv))
        require(call["timeout"] == 33.5, str(call["timeout"]))
        require(json.loads(flag_values(argv, "--json-schema")[0]) == SCHEMA, str(argv))
        require("Edit" in argv and "Write" in argv, "resume lost its write tool policy")
        require("--disallowedTools" in argv and "Bash" in argv[argv.index("--disallowedTools") + 1], str(argv))
        require(flag_values(argv, "--permission-mode") == ("dontAsk",), str(argv))
        require("Assets/Current.cs" in stdin and "Assets/Forbidden.cs" in stdin, "current boundaries absent")
        require("Current task only." in stdin, "current task prompt absent")

        codex_runner = CodexRunner()
        codex = codex_provider(
            temp, codex_runner, writable=True,
            session=binding("openai-codex", mode="resume"),
            resume_sandbox_argument=VERIFIED_RESUME_SANDBOX,
        )
        codex.invoke(current, CODEX_MODEL)
        codex_argv = codex_runner.calls[0]["argv"]
        codex_stdin = codex_runner.calls[0]["stdin"].decode("utf-8")
        require(flag_values(codex_argv, "--model") == (CODEX_MODEL,), str(codex_argv))
        require("--output-schema" in codex_argv and "--json" in codex_argv, str(codex_argv))
        require("--strict-config" in codex_argv and "--ignore-user-config" in codex_argv, str(codex_argv))
        require("--ignore-rules" in codex_argv, str(codex_argv))
        require("model_reasoning_effort=high" in codex_argv, str(codex_argv))
        require("Assets/Current.cs" in codex_stdin and "Assets/Forbidden.cs" in codex_stdin, "current boundaries absent")


def test_resumed_prompt_revokes_all_previous_task_and_write_authority() -> None:
    with workspace() as text:
        temp = Path(text)
        for make_runner, make_provider, model, session in (
            (ClaudeRunner, claude_provider, CLAUDE_MODEL, binding(mode="resume")),
            (CodexRunner, codex_provider, CODEX_MODEL, binding("openai-codex", mode="resume")),
        ):
            runner = make_runner(
                claude_transcript(session_id=SESSION_A) if make_runner is ClaudeRunner else None
            )
            extra: dict[str, Any] = {"session": session}
            if make_provider is codex_provider:
                extra["resume_sandbox_argument"] = VERIFIED_RESUME_SANDBOX
            make_provider(temp, runner, **extra).invoke(request(), model)
            stdin = runner.calls[0]["stdin"].decode("utf-8")
            require(RESUMED_AUTHORITY_NOTICE in stdin, f"{model}: notice absent from resumed prompt")
            require(stdin.startswith(RESUMED_AUTHORITY_NOTICE), f"{model}: notice must lead the prompt")
            for phrase in (
                "has expired", "no longer applies", "recall only",
                "Do not act on a remembered task", "reuse a remembered write path",
            ):
                require(phrase in stdin, f"{model}: revocation phrase missing: {phrase}")


# ------------------------------------------------------- substrate unit checks


def test_binding_and_ledger_contract() -> None:
    start = binding()
    require(start.to_dict()["schema_version"] == PROVIDER_SESSION_SCHEMA_VERSION, str(start))
    require(ProviderSessionBinding.from_dict(start.to_dict()) == start, "round trip failed")
    rejects(lambda: ProviderSessionBinding.from_dict({"role": "implementer"}), ProviderSessionError)
    rejects(
        lambda: ProviderSessionBinding.from_dict({**start.to_dict(), "schema_version": "9.9"}),
        ProviderSessionError,
    )
    rejects(
        lambda: ProviderSessionBinding.from_dict({**start.to_dict(), "extra": 1}),
        ProviderSessionError,
    )
    confirmation = start.confirm(SESSION_A)
    require(type(confirmation) is ProviderSessionConfirmation, str(confirmation))
    require(confirmation.resume_binding().is_resume, "confirmation did not yield a resume binding")
    require(
        confirmation.compatibility_key() == start.compatibility_key(),
        "confirmation compatibility key drifted from its binding",
    )
    rejects(lambda: start.confirm(SESSION_B), ProviderSessionError)
    # A provider-assigned start adopts whatever exact UUID the transcript proves.
    assigned = ProviderSessionBinding("openai-codex", "implementer", "start", None)
    require(assigned.confirm(SESSION_B).session_id == SESSION_B, "assigned identity lost")

    ledger = ProviderSessionLedger()
    require(ledger.confirmed is None and ledger.to_dict() is None, "fresh ledger not empty")
    ledger.record(confirmation)
    require(ledger.to_dict() == confirmation.to_dict(), "ledger did not publish its confirmation")
    rejects(lambda: ledger.record(confirmation), ProviderSessionError)
    rejects(lambda: ProviderSessionLedger().record("nope"), ProviderSessionError)

    rejects(
        lambda: require_compatible_binding(None, provider_identifier="claude-code", role="implementer"),
        ProviderSessionError,
    )
    require(
        prompt_with_resumed_authority("body", None) == "body",
        "a non-session prompt was rewritten",
    )
    require(
        prompt_with_resumed_authority("body", start) == "body",
        "a fresh start prompt was rewritten",
    )


def test_ledger_requires_its_session_and_exact_types() -> None:
    with workspace() as text:
        temp = Path(text)
        for factory, kwargs in (
            (ClaudeCodeProvider, {}),
            (OpenAICodexProvider, {"externally_enforced_read_only_repository": True}),
        ):
            rejects(
                lambda factory=factory, kwargs=kwargs: factory(
                    repository_root=temp / "repo",
                    session_ledger=ProviderSessionLedger(), **kwargs
                ),
                ValueError,
            )
            rejects(
                lambda factory=factory, kwargs=kwargs: factory(
                    repository_root=temp / "repo", session="3f2504e0", **kwargs
                ),
                ValueError,
            )
        rejects(
            lambda: OpenAICodexProvider(
                repository_root=temp / "repo",
                externally_enforced_read_only_repository=True,
                resume_sandbox_argument=("",),
            ),
            ValueError,
        )


TESTS = (
    test_guard_claude_default_call_is_unchanged_and_ephemeral,
    test_guard_codex_default_call_is_unchanged_and_ephemeral,
    test_explicit_none_binding_is_indistinguishable_from_omitting_it,
    test_claude_persistent_start_emits_only_session_id,
    test_claude_resume_emits_only_resume_with_the_exact_uuid,
    test_codex_persistent_start_omits_ephemeral_and_captures_its_uuid,
    test_codex_resume_uses_the_exact_uuid_and_never_last,
    test_codex_resume_fails_closed_without_a_verified_sandbox_control,
    test_invalid_session_ids_fail_before_any_subprocess,
    test_missing_or_mismatched_claude_identity_fails_closed,
    test_missing_or_mismatched_codex_identity_fails_closed,
    test_a_session_cannot_cross_providers,
    test_a_session_cannot_cross_execution_crew_roles,
    test_resume_still_supplies_every_current_control,
    test_resumed_prompt_revokes_all_previous_task_and_write_authority,
    test_binding_and_ledger_contract,
    test_ledger_requires_its_session_and_exact_types,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    for test in TESTS:
        if selected and test.__name__ not in selected:
            continue
        test()
        print(f"PASS {test.__name__}")
    print("provider_session_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
