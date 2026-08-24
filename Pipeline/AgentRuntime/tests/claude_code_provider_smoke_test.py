#!/usr/bin/env python3
"""Pure/component Stage 4B Claude adapter tests using only injected fakes."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "Pipeline/AgentRuntime"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner, RunAlreadyExistsError
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import (
    AgentInvocationRequest,
    AgentResult,
    Budgets,
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    Usage,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.process_runner import (
    ProcessResult,
    ProcessTimeoutError,
    StandardProcessRunner,
)
from Pipeline.AgentRuntime.providers import ClaudeCodeProvider
from Pipeline.AgentRuntime.providers.base import (
    ProviderFailure,
    ProviderOutputInvalid,
    ProviderRequestRejected,
    ProviderTimeout,
    ProviderTransportError,
)


MODEL = "claude-sonnet-4-5-20250929"
SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}
NULLABLE_SCHEMA = {
    "type": "object",
    "properties": {
        "artifact_proposal": {
            "type": ["object", "null"],
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        }
    },
    "required": ["artifact_proposal"],
    "additionalProperties": False,
}
DISALLOWED = "Bash,Edit,Write,NotebookEdit,WebSearch,WebFetch"
WRITE_DISALLOWED = "Bash,NotebookEdit,WebSearch,WebFetch"
AUTHORITY_FIELDS = {
    "complete",
    "conformant",
    "ready",
    "authorized",
    "approved",
    "integrated",
    "tests_passed",
}


def request(
    *,
    capabilities: tuple[str, ...] = (),
    context_paths: tuple[str, ...] = (),
    budgets: Budgets | None = None,
    prompt: str = "Return the bounded result.",
    boundaries: WriteBoundaries | None = None,
    output_schema: dict[str, Any] = SCHEMA,
) -> AgentInvocationRequest:
    effective_boundaries = boundaries or (
        WriteBoundaries(("Pipeline/AgentRuntime",), ())
        if "repository_write" in capabilities
        else WriteBoundaries((), ())
    )
    return AgentInvocationRequest(
        AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        "claude-stage-4b",
        "implementer",
        prompt,
        context_paths,
        capabilities,
        effective_boundaries,
        output_schema,
        "standard",
        Budgets(7, 12.5) if budgets is None else budgets,
        "claude-default",
    )


def successful_envelope(**changes: Any) -> dict[str, Any]:
    value = {
        "type": "result",
        "is_error": False,
        "subtype": "success",
        "terminal_reason": "completed",
        "structured_output": {"message": "ok"},
    }
    value.update(changes)
    return value


def encoded(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        return (json.dumps(value, ensure_ascii=False, indent=2) + "\r\n").encode(
            "utf-8"
        )
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


class FakeProcessRunner:
    def __init__(
        self,
        *,
        stdout: bytes | None = None,
        stderr: bytes = b"",
        returncode: int = 0,
        timeout: bool = False,
        failure: Exception | None = None,
    ) -> None:
        self.stdout = encoded(successful_envelope()) if stdout is None else stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timeout = timeout
        self.failure = failure
        self.calls: list[dict[str, Any]] = []

    def run(
        self,
        argv: Any,
        *,
        stdin: bytes,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        call = {
            "argv": tuple(argv),
            "stdin": stdin,
            "cwd": Path(cwd),
            "timeout_seconds": timeout_seconds,
            "cwd_exists": Path(cwd).is_dir(),
            "cwd_entries": tuple(sorted(path.name for path in Path(cwd).iterdir())),
        }
        self.calls.append(call)
        if self.failure is not None:
            raise self.failure
        result = ProcessResult(
            tuple(argv), self.returncode, self.stdout, self.stderr, 0.25
        )
        if self.timeout:
            raise ProcessTimeoutError(result)
        return result


def rejects(callable_: Any, exception: type[BaseException]) -> BaseException:
    try:
        callable_()
    except exception as exc:
        return exc
    raise AssertionError(f"expected {exception.__name__}")


def option(argv: tuple[str, ...], name: str) -> str:
    index = argv.index(name)
    return argv[index + 1]


def list_option(argv: tuple[str, ...], name: str) -> tuple[str, ...]:
    index = argv.index(name) + 1
    values = []
    while index < len(argv) and not argv[index].startswith("--"):
        values.append(argv[index])
        index += 1
    return tuple(values)


def assert_bounded_setting_sources(argv: tuple[str, ...]) -> None:
    assert argv.count("--setting-sources") == 1
    setting_sources = option(argv, "--setting-sources")
    assert setting_sources == "user,project"
    assert "local" not in setting_sources.split(",")


def tree_hashes(path: Path) -> dict[str, str]:
    return {
        candidate.relative_to(path).as_posix(): hashlib.sha256(
            candidate.read_bytes()
        ).hexdigest()
        for candidate in path.rglob("*")
        if candidate.is_file()
    }


def test_empty_capability_exact_invocation() -> None:
    with tempfile.TemporaryDirectory() as outer:
        temporary_parent = Path(outer)
        fake = FakeProcessRunner()
        provider = ClaudeCodeProvider(
            executable="/opt/claude/bin/claude",
            process_runner=fake,
            temporary_directory_parent=temporary_parent,
        )
        candidate = request(prompt="Prompt that must stay off argv.")
        response = provider.invoke(candidate, MODEL)
        assert response.structured_output == {"message": "ok"}
        assert response.claimed_changed_paths == ()
        assert response.claimed_test_commands == ()
        assert response.claims_execution_occurred is False
        assert response.usage is None
        assert len(fake.calls) == 1
        call = fake.calls[0]
        argv = call["argv"]
        expected_schema = json.dumps(
            SCHEMA,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        assert argv == (
            "/opt/claude/bin/claude",
            "-p",
            "--safe-mode",
            "--model",
            MODEL,
            "--max-turns",
            "7",
            "--permission-mode",
            "dontAsk",
            "--input-format",
            "text",
            "--output-format",
            "json",
            "--json-schema",
            expected_schema,
            "--no-session-persistence",
            "--setting-sources",
            "user,project",
            "--tools",
            "",
            "--disallowedTools",
            DISALLOWED,
        )
        assert "--allowedTools" not in argv
        assert_bounded_setting_sources(argv)
        assert option(argv, "--model") == MODEL
        assert option(argv, "--max-turns") == "7"
        assert call["timeout_seconds"] == 12.5
        assert "Prompt that must stay off argv." not in argv
        assert call["stdin"] == b"Prompt that must stay off argv."
        assert call["cwd"].parent == temporary_parent
        assert not call["cwd"].is_relative_to(ROOT)
        assert call["cwd_exists"] is True
        assert call["cwd_entries"] == ()
        assert not call["cwd"].exists()


def test_nullable_schema_serialization() -> None:
    envelope = successful_envelope(structured_output={"artifact_proposal": None})
    with tempfile.TemporaryDirectory() as outer:
        fake = FakeProcessRunner(stdout=encoded(envelope))
        provider = ClaudeCodeProvider(
            process_runner=fake,
            temporary_directory_parent=Path(outer),
        )
        response = provider.invoke(request(output_schema=NULLABLE_SCHEMA), MODEL)
    serialized_schema = json.loads(option(fake.calls[0]["argv"], "--json-schema"))
    assert response.structured_output == {"artifact_proposal": None}
    assert serialized_schema == NULLABLE_SCHEMA
    assert serialized_schema["properties"]["artifact_proposal"]["type"] == [
        "object", "null"
    ]


def test_repository_capability_invocations() -> None:
    cases = (
        (("repository_read",), "Read", ("Read",)),
        (("repository_search",), "Glob,Grep", ("Glob", "Grep")),
        (
            ("repository_read", "repository_search"),
            "Read,Glob,Grep",
            ("Read", "Glob", "Grep"),
        ),
    )
    for capabilities, expected_tools, expected_allowed in cases:
        fake = FakeProcessRunner()
        candidate = request(capabilities=capabilities)
        ClaudeCodeProvider(process_runner=fake).invoke(candidate, MODEL)
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert_bounded_setting_sources(call["argv"])
        assert call["cwd"] == ROOT
        assert option(call["argv"], "--tools") == expected_tools
        assert option(call["argv"], "--disallowedTools") == DISALLOWED
        assert list_option(call["argv"], "--allowedTools") == expected_allowed
        assert set(expected_allowed).isdisjoint(DISALLOWED.split(","))
        assert "Bash" not in expected_tools
        assert "Edit" not in expected_tools
        assert "Write" not in expected_tools
        assert "WebSearch" not in expected_tools
        assert "WebFetch" not in expected_tools
        effective_prompt = call["stdin"].decode("utf-8")
        assert effective_prompt.startswith("Return the bounded result.\n\n")
        assert "Repository context:" in effective_prompt
        assert "Repository root: /workspace" in effective_prompt
        assert "Use repository tools only for the No Safe Circle project." in effective_prompt
        assert (
            "Do not intentionally inspect /home, provider credentials, environment "
            "secrets, or unrelated filesystem locations."
        ) in effective_prompt
        assert "Relevant repository paths:" not in effective_prompt


def test_forbidden_capabilities_context_and_token_limits() -> None:
    forbidden = (
        "repository_write",
        "approved_command_execution",
        ("repository_read", "repository_write"),
        ("repository_search", "approved_command_execution"),
    )
    with tempfile.TemporaryDirectory() as outer:
        temporary_parent = Path(outer)

        for item in forbidden:
            capabilities = (item,) if isinstance(item, str) else item
            fake = FakeProcessRunner()
            provider = ClaudeCodeProvider(
                process_runner=fake,
                temporary_directory_parent=temporary_parent,
            )
            rejects(
                lambda capabilities=capabilities, provider=provider: provider.invoke(
                    request(capabilities=capabilities), MODEL
                ),
                ProviderRequestRejected,
            )
            assert fake.calls == []

        policies = (
            {"context_paths": ("Docs/guide.md",)},
            {"budgets": Budgets(3, 9, 100)},
            {"capabilities": ("repository_read",), "budgets": Budgets(3, 9, 100)},
        )
        for policy in policies:
            fake = FakeProcessRunner()
            provider = ClaudeCodeProvider(
                process_runner=fake,
                temporary_directory_parent=temporary_parent,
            )
            exception = rejects(
                lambda policy=policy, provider=provider: provider.invoke(
                    request(**policy), MODEL
                ),
                ProviderRequestRejected,
            )
            assert str(exception).strip()
            assert fake.calls == []

        fake = FakeProcessRunner()
        provider = ClaudeCodeProvider(
            process_runner=fake,
            temporary_directory_parent=temporary_parent,
        )
        candidate = request(
            capabilities=("repository_read",),
            context_paths=("Docs/AI-Pipeline/START_HERE.md", "Tasks/NSC-001.yaml"),
            prompt="Inspect the requested context.",
        )
        original_prompt = candidate.prompt
        original_paths = candidate.context_paths
        provider.invoke(candidate, MODEL)
        effective_prompt = fake.calls[0]["stdin"].decode("utf-8")
        assert "Repository root: /workspace" in effective_prompt
        assert "- Docs/AI-Pipeline/START_HERE.md" in effective_prompt
        assert "- Tasks/NSC-001.yaml" in effective_prompt
        assert "Use repository tools only for the No Safe Circle project." in effective_prompt
        assert (
            "Do not intentionally inspect /home, provider credentials, environment "
            "secrets, or unrelated filesystem locations."
        ) in effective_prompt
        assert "Relevant repository paths:" in effective_prompt
        assert candidate.prompt == original_prompt
        assert candidate.context_paths == original_paths


def test_isolated_writable_repository_policy() -> None:
    write_capabilities = ("repository_read", "repository_search", "repository_write")
    exact_boundaries = WriteBoundaries(
        ("Assets/NoSafeCircle/Feature", "Docs/implementation.md"),
        ("Assets/NoSafeCircle/Feature/Denied.asset", "Docs/private"),
    )
    candidate = request(capabilities=write_capabilities, boundaries=exact_boundaries)

    rejects(
        lambda: ClaudeCodeProvider(process_runner=FakeProcessRunner()).invoke(candidate, MODEL),
        ProviderRequestRejected,
    )
    for forbidden_root in (ROOT, ROOT / "Pipeline", ROOT.parent):
        rejects(
            lambda forbidden_root=forbidden_root: ClaudeCodeProvider(
                process_runner=FakeProcessRunner(), repository_root=forbidden_root,
                externally_isolated_writable_repository=True,
            ).invoke(candidate, MODEL),
            ProviderRequestRejected,
        )
    rejects(
        lambda: ClaudeCodeProvider(
            process_runner=FakeProcessRunner(), repository_root=ROOT.parent / "missing-write-root",
            externally_isolated_writable_repository=True,
        ).invoke(candidate, MODEL),
        ProviderRequestRejected,
    )

    with tempfile.TemporaryDirectory(prefix="claude-write-policy-") as text:
        temporary_parent = Path(text)
        repository = Path(text) / "repo"
        repository.mkdir()
        fake = FakeProcessRunner()
        provider = ClaudeCodeProvider(
            process_runner=fake,
            repository_root=repository,
            externally_isolated_writable_repository=True,
        )
        provider.invoke(candidate, MODEL)
        call = fake.calls[0]
        assert_bounded_setting_sources(call["argv"])
        assert call["cwd"] == repository.resolve()
        assert option(call["argv"], "--tools") == "Read,Glob,Grep,Edit,Write"
        assert option(call["argv"], "--disallowedTools") == WRITE_DISALLOWED
        allowed_tools = list_option(call["argv"], "--allowedTools")
        assert allowed_tools == ("Read", "Glob", "Grep", "Edit", "Write")
        assert set(allowed_tools).isdisjoint(WRITE_DISALLOWED.split(","))
        assert "Bash" in option(call["argv"], "--disallowedTools")
        prompt = call["stdin"].decode("utf-8")
        assert "disposable isolated writable repository" in prompt
        assert (
            "Allowed write paths:\n- Assets/NoSafeCircle/Feature\n"
            "- Docs/implementation.md\nDenied write paths:\n"
            "- Assets/NoSafeCircle/Feature/Denied.asset\n- Docs/private"
        ) in prompt
        assert "request.is_path_writable(path)" in prompt
        assert "Do not run commands, tests, or builds." in prompt
        assert "not native path-level Claude enforcement" in prompt
        assert "deterministic Git diff validation" in prompt

        rejects(
            lambda: provider.invoke(request(capabilities=("repository_read",)), MODEL),
            ProviderRequestRejected,
        )
        rejects(
            lambda: provider.invoke(
                request(capabilities=write_capabilities, budgets=Budgets(1, 10, 5)), MODEL
            ),
            ProviderRequestRejected,
        )
        rejects(
            lambda: provider.invoke(
                request(capabilities=write_capabilities + ("approved_command_execution",)), MODEL
            ),
            ProviderRequestRejected,
        )

def test_local_metadata_requirements() -> None:
    with tempfile.TemporaryDirectory() as outer:
        temporary_parent = Path(outer)
        rejects(lambda: ClaudeCodeProvider(temporary_parent), TypeError)

        provider = ClaudeCodeProvider(
            process_runner=FakeProcessRunner(),
            temporary_directory_parent=RUNTIME_ROOT,
        )
        rejects(lambda: provider.invoke(request(), MODEL), ProviderTransportError)
        assert provider.process_runner.calls == []

        for alias in ("sonnet", "opus", "haiku", "default", "gpt-5"):
            provider = ClaudeCodeProvider(
                process_runner=FakeProcessRunner(),
                temporary_directory_parent=temporary_parent,
            )
            rejects(lambda alias=alias: provider.invoke(request(), alias), ProviderTransportError)
            assert provider.process_runner.calls == []


def test_success_raw_log_and_usage_normalization() -> None:
    model_usage = {
        "claude-primary": {
            "inputTokens": 10,
            "cacheReadInputTokens": 20,
            "cacheCreationInputTokens": 30,
            "outputTokens": 4,
            "totalTokens": 64,
        },
        "claude-auxiliary": {
            "inputTokens": 1,
            "cacheReadInputTokens": 2,
            "cacheCreationInputTokens": 3,
            "outputTokens": 5,
        },
    }
    envelope = successful_envelope(
        stop_reason="tool_use",
        modelUsage=model_usage,
        usage={
            "input_tokens": 999,
            "cache_read_input_tokens": 999,
            "cache_creation_input_tokens": 999,
            "output_tokens": 999,
        },
        total_cost_usd=0.125,
    )
    raw = encoded(envelope, pretty=True)
    with tempfile.TemporaryDirectory() as outer:
        fake = FakeProcessRunner(stdout=raw)
        provider = ClaudeCodeProvider(
            process_runner=fake,
            temporary_directory_parent=Path(outer),
        )
        response = provider.invoke(request(), MODEL)
    assert response.structured_output == {"message": "ok"}
    assert response.raw_log == raw.decode("utf-8")
    assert response.usage == Usage(66, 9, 75, 0.125)
    assert response.claimed_changed_paths == ()
    assert response.claimed_test_commands == ()
    assert response.claims_execution_occurred is False

    fallback = successful_envelope(
        usage={
            "input_tokens": 7,
            "cache_read_input_tokens": 11,
            "cache_creation_input_tokens": 13,
            "output_tokens": 17,
            "total_tokens": 48,
        },
        total_cost_usd=2,
    )
    with tempfile.TemporaryDirectory() as outer:
        response = ClaudeCodeProvider(
            process_runner=FakeProcessRunner(stdout=encoded(fallback)),
            temporary_directory_parent=Path(outer),
        ).invoke(request(), MODEL)
    assert response.usage == Usage(31, 17, 48, 2)


def invoke_with_stdout(stdout: bytes, **runner_changes: Any) -> Any:
    outer = tempfile.TemporaryDirectory()
    try:
        provider = ClaudeCodeProvider(
            process_runner=FakeProcessRunner(stdout=stdout, **runner_changes),
            temporary_directory_parent=Path(outer.name),
        )
        return provider.invoke(request(), MODEL)
    finally:
        outer.cleanup()


def test_envelope_and_process_failures() -> None:
    malformed = b'{"type":"result"'
    exception = rejects(
        lambda: invoke_with_stdout(malformed), ProviderOutputInvalid
    )
    assert exception.raw_log == malformed.decode("utf-8")

    duplicate = (
        b'{"type":"result","type":"result","is_error":false,'
        b'"subtype":"success","terminal_reason":"completed",'
        b'"structured_output":{"message":"ok"}}'
    )
    exception = rejects(
        lambda: invoke_with_stdout(duplicate), ProviderOutputInvalid
    )
    assert exception.raw_log == duplicate.decode("utf-8")

    missing_output = encoded(successful_envelope())
    missing_value = json.loads(missing_output)
    del missing_value["structured_output"]
    missing_raw = encoded(missing_value)
    exception = rejects(
        lambda: invoke_with_stdout(missing_raw), ProviderOutputInvalid
    )
    assert exception.raw_log == missing_raw.decode("utf-8")

    for field in ("type", "is_error", "subtype", "terminal_reason"):
        incomplete = successful_envelope()
        del incomplete[field]
        incomplete_raw = encoded(incomplete)
        exception = rejects(
            lambda incomplete_raw=incomplete_raw: invoke_with_stdout(incomplete_raw),
            ProviderOutputInvalid,
        )
        assert exception.raw_log == incomplete_raw.decode("utf-8")

    malformed_metadata = (
        successful_envelope(type=1),
        successful_envelope(is_error=0),
        successful_envelope(subtype=False),
        successful_envelope(terminal_reason=None),
        successful_envelope(permission_denials={}),
        successful_envelope(permission_denials=False),
    )
    for envelope in malformed_metadata:
        raw = encoded(envelope)
        exception = rejects(
            lambda raw=raw: invoke_with_stdout(raw), ProviderOutputInvalid
        )
        assert exception.raw_log == raw.decode("utf-8")

    wrong_type_value = encoded(successful_envelope(type="assistant"))
    exception = rejects(
        lambda: invoke_with_stdout(wrong_type_value), ProviderOutputInvalid
    )
    assert exception.raw_log == wrong_type_value.decode("utf-8")

    unsuccessful = (
        successful_envelope(is_error=True, result="provider error"),
        successful_envelope(subtype="error"),
        successful_envelope(terminal_reason="max_turns"),
        successful_envelope(permission_denials=[{"tool": "Read"}]),
    )
    for envelope in unsuccessful:
        raw = encoded(envelope)
        exception = rejects(
            lambda raw=raw: invoke_with_stdout(raw), ProviderFailure
        )
        assert exception.raw_log == raw.decode("utf-8")

    allowed_permission_metadata = encoded(
        successful_envelope(permission_denials=[])
    )
    assert invoke_with_stdout(allowed_permission_metadata).structured_output == {
        "message": "ok"
    }

    nonzero_raw = b"provider failed before producing JSON\n"
    exception = rejects(
        lambda: invoke_with_stdout(
            nonzero_raw, returncode=9, stderr=b"safe provider diagnostic\n"
        ),
        ProviderFailure,
    )
    assert exception.raw_log == nonzero_raw.decode("utf-8")
    assert "safe provider diagnostic" in str(exception)

    success_raw = encoded(successful_envelope())
    exception = rejects(
        lambda: invoke_with_stdout(success_raw, stderr=b"unexpected warning\n"),
        ProviderTransportError,
    )
    assert exception.raw_log == success_raw.decode("utf-8")

    partial = b'{"type":"result","partial":true}\n'
    exception = rejects(
        lambda: invoke_with_stdout(partial, timeout=True), ProviderTimeout
    )
    assert exception.raw_log == partial.decode("utf-8")

    exception = rejects(
        lambda: invoke_with_stdout(b"bad\xffutf8"), ProviderTransportError
    )
    assert exception.raw_log == ""


def test_invalid_usage_fails_as_transport_error() -> None:
    invalid_envelopes = (
        successful_envelope(modelUsage=None),
        successful_envelope(modelUsage={}),
        successful_envelope(modelUsage={"model": []}),
        successful_envelope(modelUsage={"model": {
            "inputTokens": -1,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
            "outputTokens": 0,
        }}),
        successful_envelope(modelUsage={"model": {
            "inputTokens": True,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
            "outputTokens": 0,
        }}),
        successful_envelope(usage={
            "input_tokens": 1,
            "cache_read_input_tokens": 2,
            "cache_creation_input_tokens": 3,
            "output_tokens": 4,
            "total_tokens": 999,
        }),
        successful_envelope(usage={
            "input_tokens": 1,
            "cache_read_input_tokens": 2,
            "output_tokens": 4,
        }),
        successful_envelope(usage={
            "input_tokens": 1,
            "cache_read_input_tokens": 2,
            "cache_creation_input_tokens": 3,
            "output_tokens": 4,
        }, total_cost_usd=-0.1),
    )
    for envelope in invalid_envelopes:
        raw = encoded(envelope)
        exception = rejects(
            lambda raw=raw: invoke_with_stdout(raw), ProviderTransportError
        )
        assert exception.raw_log == raw.decode("utf-8")

    nonfinite = (
        b'{"type":"result","is_error":false,"subtype":"success",'
        b'"terminal_reason":"completed","structured_output":{"message":"ok"},'
        b'"usage":{"input_tokens":1e309,"cache_read_input_tokens":0,'
        b'"cache_creation_input_tokens":0,"output_tokens":0}}'
    )
    exception = rejects(
        lambda: invoke_with_stdout(nonfinite), ProviderTransportError
    )
    assert exception.raw_log == nonfinite.decode("utf-8")

    nonfinite_cost = (
        b'{"type":"result","is_error":false,"subtype":"success",'
        b'"terminal_reason":"completed","structured_output":{"message":"ok"},'
        b'"total_cost_usd":1e309}'
    )
    exception = rejects(
        lambda: invoke_with_stdout(nonfinite_cost), ProviderTransportError
    )
    assert exception.raw_log == nonfinite_cost.decode("utf-8")


def claude_configuration() -> RuntimeConfiguration:
    return RuntimeConfiguration(
        {
            "claude-default": {
                "provider": "claude-code",
                "models": {
                    "low_cost": MODEL,
                    "standard": MODEL,
                    "high_reasoning": MODEL,
                },
            }
        }
    )


def assert_runner_artifacts(
    run_root: Path,
    candidate: AgentInvocationRequest,
    result: AgentResult,
    raw_log: str,
) -> None:
    run_dir = run_root / candidate.run_id
    assert sorted(path.name for path in run_dir.iterdir()) == [
        "provider.log",
        "request.json",
        "result.json",
    ]
    assert (run_dir / "provider.log").read_bytes() == raw_log.encode("utf-8")
    request_value = json.loads((run_dir / "request.json").read_text("utf-8"))
    result_value = json.loads((run_dir / "result.json").read_text("utf-8"))
    assert AgentInvocationRequest.from_dict(request_value) == candidate
    assert AgentResult.from_dict(result_value) == result
    assert set(request_value).isdisjoint(AUTHORITY_FIELDS)
    assert set(result_value).isdisjoint(AUTHORITY_FIELDS)


def test_agent_runner_claude_integration() -> None:
    exact_success = encoded(
        successful_envelope(
            structured_output={"message": "integrated"},
            permission_denials=[],
        ),
        pretty=True,
    ).decode("utf-8")
    malformed = '{"type":"result"'
    missing = successful_envelope()
    del missing["structured_output"]
    missing_raw = encoded(missing).decode("utf-8")
    partial = '{"type":"result","partial":true}\n'

    fixtures = (
        (
            "claude-success",
            request(),
            FakeProcessRunner(stdout=exact_success.encode("utf-8")),
            "succeeded",
            "none",
            exact_success,
        ),
        (
            "claude-malformed",
            request(),
            FakeProcessRunner(stdout=malformed.encode("utf-8")),
            "failed",
            "schema_error",
            malformed,
        ),
        (
            "claude-missing",
            request(),
            FakeProcessRunner(stdout=missing_raw.encode("utf-8")),
            "failed",
            "schema_error",
            missing_raw,
        ),
        (
            "claude-transport",
            request(),
            FakeProcessRunner(
                stdout=exact_success.encode("utf-8"),
                stderr=b"unexpected transport warning\n",
            ),
            "failed",
            "internal_error",
            exact_success,
        ),
        (
            "claude-timeout",
            request(),
            FakeProcessRunner(stdout=partial.encode("utf-8"), timeout=True),
            "failed",
            "timeout",
            partial,
        ),
        (
            "claude-rejected",
            request(capabilities=("repository_write",)),
            FakeProcessRunner(),
            "failed",
            "invalid_request",
            "",
        ),
    )

    with tempfile.TemporaryDirectory() as outer:
        root = Path(outer)
        run_root = root / "runs"
        workspace_parent = root / "workspaces"
        workspace_parent.mkdir()
        for run_id, base_request, fake, status, classification, raw_log in fixtures:
            candidate = replace(base_request, run_id=run_id)
            provider = ClaudeCodeProvider(
                process_runner=fake,
                temporary_directory_parent=workspace_parent,
            )
            runner = AgentRunner(
                run_root,
                claude_configuration(),
                {"claude-code": provider},
            )
            result = runner.run(candidate)
            assert result.status == status
            assert result.failure_classification == classification
            assert result.provider == "claude-code"
            assert result.model == MODEL
            assert result.structured_output == (
                {"message": "integrated"} if status == "succeeded" else None
            )
            assert result.claimed_changed_paths == ()
            assert result.claimed_test_commands == ()
            assert result.claims_execution_occurred is False
            assert_runner_artifacts(run_root, candidate, result, raw_log)
            artifact_hashes = tree_hashes(run_root / run_id)
            rejects(lambda: runner.run(candidate), RunAlreadyExistsError)
            assert tree_hashes(run_root / run_id) == artifact_hashes
            if classification == "invalid_request":
                assert fake.calls == []


def test_transport_contract_exports_and_repository_cleanliness() -> None:
    result = ProcessResult(("program", "argument"), 0, b"out", b"err", 1.5)
    rejects(lambda: setattr(result, "returncode", 1), FrozenInstanceError)
    source = inspect.getsource(StandardProcessRunner.run)
    assert "shell=False" in source
    assert "stdout=subprocess.PIPE" in source
    assert "stderr=subprocess.PIPE" in source
    assert "input=stdin" in source

    from Pipeline.AgentRuntime import providers

    assert providers.ClaudeCodeProvider is ClaudeCodeProvider
    assert providers.ProviderRequestRejected is ProviderRequestRejected
    assert providers.ProviderTransportError is ProviderTransportError
    modules = {
        path.name for path in (ROOT / "Pipeline/AgentRuntime/providers").glob("*.py")
    }
    assert modules == {
        "__init__.py", "base.py", "claude_code.py", "fake.py", "openai_codex.py"
    }
    assert not (ROOT / "Pipeline/AgentRuntime/providers/codex.py").exists()
    assert not (ROOT / "Pipeline/AgentRuntime/providers/openai.py").exists()


def main() -> None:
    before = tree_hashes(RUNTIME_ROOT)
    status_before = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    test_empty_capability_exact_invocation()
    test_nullable_schema_serialization()
    test_repository_capability_invocations()
    test_forbidden_capabilities_context_and_token_limits()
    test_isolated_writable_repository_policy()
    test_local_metadata_requirements()
    test_success_raw_log_and_usage_normalization()
    test_envelope_and_process_failures()
    test_invalid_usage_fails_as_transport_error()
    test_agent_runner_claude_integration()
    test_transport_contract_exports_and_repository_cleanliness()
    after = tree_hashes(RUNTIME_ROOT)
    status_after = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert before == after, "Claude provider tests modified repository files"
    assert status_before == status_after, "Claude provider tests created repository output"
    print("ClaudeCodeProvider smoke test: PASS (Stage 4B.3 deterministic fixtures)")


if __name__ == "__main__":
    main()
