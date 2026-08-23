#!/usr/bin/env python3
"""Pure/component regression tests for Stage 3A; artifacts stay temporary."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
import operator
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner, RunAlreadyExistsError, _publish
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import (
    AgentRequest,
    AgentResult,
    Budgets,
    ContractValidationError,
    SCHEMA_VERSION,
    TaskContractIdentity,
    Usage,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.providers.base import (
    ProviderFailure,
    ProviderInvocationError,
    ProviderInvocationResponse,
    ProviderOutputInvalid,
    ProviderTimeout,
)
from Pipeline.AgentRuntime.providers.fake import FakeProvider
from Pipeline.AgentRuntime.json_values import JsonValueError, MAX_JSON_NESTING_DEPTH, freeze_json, thaw_json
from Pipeline.AgentRuntime.schema_validation import SchemaValidationError, validate_instance


SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}


def request(**changes: Any) -> AgentRequest:
    values = {
        "schema_version": SCHEMA_VERSION,
        "run_id": "run-001",
        "task_id": "NSC-001",
        "task_contract_identity": TaskContractIdentity(
            "Tasks/NSC-001.yaml", 1, "a" * 64
        ),
        "role": "implementer",
        "prompt": "Do bounded work.",
        "context_paths": ("Docs/guide.md",),
        "allowed_capabilities": ("repository_read", "repository_write"),
        "write_boundaries": WriteBoundaries(
            ("Pipeline/AgentRuntime",),
            ("Pipeline/AgentRuntime/locked",),
        ),
        "output_schema": SCHEMA,
        "model_capability_class": "standard",
        "budgets": Budgets(5, 30, 1000),
        "provider_configuration_key": "fake-default",
    }
    values.update(changes)
    return AgentRequest(**values)


def rejects(callable_: Any, exception: type[BaseException] = ValueError) -> None:
    try:
        callable_()
    except exception:
        return
    raise AssertionError("expected rejection")


def configuration(source: dict[str, Any] | None = None) -> RuntimeConfiguration:
    if source is None:
        source = json.loads(
            (ROOT / "Pipeline/AgentRuntime/config/example.json").read_text(
                encoding="utf-8"
            )
        )
    return RuntimeConfiguration.from_dict(source)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def tree_hashes(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in path.rglob("*")
        if item.is_file()
    }


class TimeoutSubclass(ProviderTimeout):
    pass


class RaisingProvider:
    provider_identifier = "fake"

    def __init__(self, exception: BaseException) -> None:
        self.exception = exception

    def invoke(self, request_: AgentRequest, model: str) -> ProviderInvocationResponse:
        raise self.exception


class CountingProvider:
    provider_identifier = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request_: AgentRequest, model: str) -> ProviderInvocationResponse:
        self.calls += 1
        return ProviderInvocationResponse({"message": "unexpected"}, "")


class ContainerProvider:
    provider_identifier = "fake"

    def invoke(self, request_: AgentRequest, model: str) -> Any:
        return {"structured_output": {"message": "not a response"}}


class BadPublicationRequest(AgentRequest):
    def to_dict(self) -> dict[str, Any]:
        return {"unsupported": object()}


class BadConfiguration(RuntimeConfiguration):
    def resolve(self, *args: Any) -> Any:
        raise AssertionError("subclass resolution must never run")


class IdentityMismatchProvider(CountingProvider):
    provider_identifier = "other"


class LyingIdentity(TaskContractIdentity):
    def to_dict(self) -> dict[str, Any]:
        return {"path": "Tasks/NSC-999.yaml", "revision": 9, "sha256": "b" * 64}


class LyingBoundaries(WriteBoundaries):
    def to_dict(self) -> dict[str, Any]:
        return {"allowed_paths": ["Everything"], "denied_paths": []}


class LyingBudgets(Budgets):
    def to_dict(self) -> dict[str, Any]:
        return {"turn_limit": 999, "timeout_seconds": 999, "token_limit": 999}


class LyingUsage(Usage):
    def to_dict(self) -> dict[str, Any]:
        return {"input_tokens": 999, "output_tokens": 999, "total_tokens": 999,
                "estimated_cost_usd": 999}


class ResponseSubclass(ProviderInvocationResponse):
    pass


class StaticResponseProvider:
    provider_identifier = "fake"

    def __init__(self, response: Any) -> None:
        self.response = response

    def invoke(self, request_: AgentRequest, model: str) -> Any:
        return self.response


class BrokenTextException(Exception):
    def __str__(self) -> str:
        return "\ud800"


class BadMapping(dict[str, Any]):
    def items(self) -> Any:
        raise ValueError("unsafe mapping callback")


class EvilText(str):
    def encode(self, *args: Any, **kwargs: Any) -> bytes:
        raise ValueError("unsafe text callback")


def test_contracts_and_immutability() -> None:
    schema = {
        "type": "object",
        "properties": {"message": {"type": "string", "enum": ["ok"]}},
        "required": ["message"],
        "additionalProperties": False,
    }
    req = request(output_schema=schema)
    schema["properties"]["message"]["enum"][0] = "mutated"
    assert req.to_dict()["output_schema"]["properties"]["message"]["enum"] == ["ok"]
    detached = req.to_dict()
    detached["output_schema"]["properties"]["message"]["enum"].append("new")
    assert req.to_dict()["output_schema"]["properties"]["message"]["enum"] == ["ok"]
    rejects(lambda: operator.setitem(req.output_schema, "type", "array"), TypeError)
    assert AgentRequest.from_dict(req.to_dict()) == req
    rejects(lambda: AgentRequest.from_dict({**req.to_dict(), "extra": True}))

    rejects(lambda: request(task_id="NSC-1"))
    rejects(
        lambda: request(
            task_contract_identity=TaskContractIdentity(
                "Tasks/NSC-002.yaml", 1, "a" * 64
            )
        )
    )
    rejects(lambda: TaskContractIdentity("Tasks/NSC-001.yaml", 1, "A" * 64))
    rejects(lambda: request(output_schema={"type": "number", "enum": [math.nan]}))
    rejects(lambda: request(output_schema={"type": "number", "enum": [math.inf]}))
    rejects(lambda: request(output_schema={"type": "string", "enum": [object()]}))
    rejects(lambda: request(output_schema={"type": "string", "enum": [1]}))
    rejects(lambda: request(output_schema={"type": "number", "enum": [1, 1.0]}))
    assert request(output_schema={"type": "string", "enum": ["a", "b"]})
    rejects(lambda: request(output_schema={"type": "number", "minimum": 0}))

    for number in (math.nan, math.inf, -math.inf):
        rejects(lambda number=number: Budgets(1, number))
        rejects(lambda number=number: Usage(0, 0, 0, number))

    for path in ("/absolute", "a/../b", "a\\b", "a//b", "./a", "C:/a"):
        rejects(lambda path=path: request(context_paths=(path,)))
    rejects(lambda: request(allowed_capabilities=("repository_read", "unknown")))
    rejects(
        lambda: request(
            allowed_capabilities=("repository_read", "repository_write"),
            write_boundaries=WriteBoundaries((), ()),
        )
    )
    rejects(
        lambda: request(
            allowed_capabilities=("repository_read",),
            write_boundaries=WriteBoundaries(("Assets",), ()),
        )
    )
    for budgets in (
        Budgets(1, 1),
    ):
        assert budgets
    for args in ((0, 1, None), (1001, 1, None), (1, 0, None),
                 (1, 86401, None), (1, 1, 0), (1, 1, 10000001)):
        rejects(lambda args=args: Budgets(*args))
    assert req.is_path_writable("Pipeline/AgentRuntime/contracts.py")
    assert not req.is_path_writable("Pipeline/AgentRuntime/locked/file")
    for alias in (
        "Pipeline/AgentRuntime/locked.",
        "Pipeline/AgentRuntime/locked ",
        "Pipeline/AgentRuntime/locked:stream",
    ):
        assert not req.is_path_writable(alias)
    case_request = request(
        write_boundaries=WriteBoundaries(("Assets/Foo",), ("Assets/Secret",))
    )
    assert case_request.is_path_writable("assets/foo/file")
    assert not case_request.is_path_writable("Assets/Foobar/file")
    assert not case_request.is_path_writable("Assets/secret/file")
    rejects(lambda: WriteBoundaries(("Assets/Foo", "assets/foo"), ()))


def test_json_and_schema_containers() -> None:
    mutable = {"array": [{"value": "ok"}]}
    frozen = freeze_json(mutable)
    refrozen = freeze_json(frozen)
    mutable["array"][0]["value"] = "changed"
    assert thaw_json(refrozen) == {"array": [{"value": "ok"}]}
    first_copy = thaw_json(refrozen)
    first_copy["array"][0]["value"] = "detached"
    assert thaw_json(refrozen) == {"array": [{"value": "ok"}]}
    validate_instance(
        [[1], [2]],
        {"type": "array", "items": {"type": "array", "items": {"type": "integer"}},
         "enum": [[[1], [2]]]},
    )
    validate_instance(
        {"nested": ["x"]},
        {"type": "object", "enum": [{"nested": ["x"]}]},
    )
    rejects(lambda: freeze_json("\ud800"))
    rejects(lambda: freeze_json({"\ud800": "bad"}))
    rejects(lambda: thaw_json([object()]))

    cyclic: list[Any] = []
    cyclic.append(cyclic)
    rejects(lambda: freeze_json(cyclic), JsonValueError)
    rejects(lambda: thaw_json(cyclic), JsonValueError)
    rejects(lambda: validate_instance(cyclic, {"type": "array", "items": {"type": "null"}}), SchemaValidationError)
    rejects(lambda: validate_instance({1: "bad"}, {"type": "object"}), SchemaValidationError)
    rejects(lambda: validate_instance("ok", {"type": "string", "enum": ["\ud800"]}), SchemaValidationError)
    deep: Any = None
    for _ in range(MAX_JSON_NESTING_DEPTH + 1):
        deep = [deep]
    rejects(lambda: freeze_json(deep), JsonValueError)
    cyclic_schema: dict[str, Any] = {"type": "array"}
    cyclic_schema["items"] = cyclic_schema
    rejects(lambda: request(output_schema=cyclic_schema), ContractValidationError)


def test_exact_nested_and_text_boundaries() -> None:
    rejects(lambda: request(task_contract_identity=LyingIdentity("Tasks/NSC-001.yaml", 1, "a" * 64)), ContractValidationError)
    rejects(lambda: request(write_boundaries=LyingBoundaries(("Pipeline/AgentRuntime",), ())), ContractValidationError)
    rejects(lambda: request(budgets=LyingBudgets(1, 1, 1)), ContractValidationError)
    rejects(lambda: request(prompt="bad\ud800"), ContractValidationError)
    for bad_path in (
        "bad\ud800", "bad\x00path", "bad\tpath", "bad\npath",
        "bad\x7fpath", "Assets/name:stream", "Assets/trailing.",
        "Assets/trailing ", "Assets/CON", "Assets/com1.txt",
        "Assets/name?bad",
    ):
        rejects(
            lambda bad_path=bad_path: request(context_paths=(bad_path,)),
            ContractValidationError,
        )
    base = AgentResult(SCHEMA_VERSION, "text-result", "fake", "model", "implementer",
                       "failed", "schema_error", "diagnostic", None, (), 0, None,
                       "provider.log", False, ())
    rejects(lambda: replace(base, failure_message=" \t "), ContractValidationError)
    rejects(lambda: replace(base, failure_message="bad\ud800"), ContractValidationError)
    rejects(lambda: replace(base, raw_log_reference="bad\nlog"), ContractValidationError)
    rejects(lambda: replace(base, claimed_test_commands=("bad\ud800",)), ContractValidationError)
    rejects(lambda: replace(base, usage=LyingUsage(1, 1, 2)), ContractValidationError)
    rejects(
        lambda: replace(base, structured_output={"rejected": True}),
        ContractValidationError,
    )
    source = configuration().to_dict()
    source["provider_configurations"]["fake-default"]["models"]["standard"] = "bad\ud800"
    rejects(lambda: RuntimeConfiguration.from_dict(source), ContractValidationError)


def test_response_snapshot_and_failure_audit() -> None:
    config = configuration()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        subclass_request = replace(request(), run_id="response-subclass")
        subclass = ResponseSubclass({"message": "ok"}, "log")
        result = AgentRunner(root, config, {"fake": StaticResponseProvider(subclass)}).run(subclass_request)
        assert result.failure_classification == "internal_error"

        unsafe_mapping_request = replace(request(), run_id="unsafe-mapping")
        result = AgentRunner(root, config, {"fake": StaticResponseProvider(
            ProviderInvocationResponse(BadMapping(), "exact log"))}).run(
                unsafe_mapping_request
            )
        assert result.failure_classification == "schema_error"
        assert (root / "unsafe-mapping/provider.log").read_text("utf-8") == "exact log"
        assert (root / "unsafe-mapping/result.json").is_file()

        evil_log_request = replace(request(), run_id="evil-log-subclass")
        result = AgentRunner(root, config, {"fake": StaticResponseProvider(
            ProviderInvocationResponse({"message": "ok"}, EvilText("raw"))
        )}).run(evil_log_request)
        assert result.failure_classification == "internal_error"
        assert (root / "evil-log-subclass/provider.log").read_bytes() == b""
        assert (root / "evil-log-subclass/result.json").is_file()

        claims_request = replace(request(), run_id="schema-claims")
        usage = Usage(3, 4, 7)
        result = AgentRunner(root, config, {"fake": StaticResponseProvider(
            ProviderInvocationResponse({"wrong": True}, "claim log", ("Assets/file",),
                                       usage, True, ("python3 check.py",)))}).run(claims_request)
        assert result.failure_classification == "schema_error"
        assert result.structured_output is None and result.usage == usage
        assert result.claimed_changed_paths == ("Assets/file",)
        assert result.claims_execution_occurred is True
        assert result.claimed_test_commands == ("python3 check.py",)
        assert (root / "schema-claims/provider.log").read_text("utf-8") == "claim log"

        cyclic: list[Any] = []
        cyclic.append(cyclic)
        cyclic_request = replace(request(), run_id="cyclic-output")
        result = AgentRunner(root, config, {"fake": StaticResponseProvider(
            ProviderInvocationResponse(cyclic, "cyclic log", usage=usage))}).run(cyclic_request)
        assert result.failure_classification == "schema_error" and result.usage == usage
        assert (root / "cyclic-output/provider.log").read_text("utf-8") == "cyclic log"
        assert (root / "cyclic-output/result.json").is_file()

        bad_log_request = replace(request(), run_id="bad-log")
        result = AgentRunner(root, config, {"fake": StaticResponseProvider(
            ProviderInvocationResponse({"message": "ok"}, "bad\ud800"))}).run(bad_log_request)
        assert result.failure_classification == "internal_error"
        assert (root / "bad-log/provider.log").read_bytes() == b""
        assert "raw_log was rejected" in result.failure_message

        exception_request = replace(request(), run_id="bad-exception")
        result = AgentRunner(root, config, {"fake": RaisingProvider(BrokenTextException())}).run(exception_request)
        assert result.failure_classification == "internal_error"
        (root / "bad-exception/result.json").read_text("utf-8")


def test_configuration() -> None:
    source = json.loads(
        (ROOT / "Pipeline/AgentRuntime/config/example.json").read_text("utf-8")
    )
    config = configuration(source)
    source["provider_configurations"]["fake-default"]["models"]["standard"] = "changed"
    assert config.provider_configurations["fake-default"]["models"]["standard"] == "fake-standard"
    detached = config.to_dict()
    detached["provider_configurations"]["fake-default"]["models"]["standard"] = "changed"
    assert config.provider_configurations["fake-default"]["models"]["standard"] == "fake-standard"
    rejects(
        lambda: operator.setitem(config.provider_configurations, "x", {}),
        TypeError,
    )
    rejects(
        lambda: configuration(
            {"schema_version": "1.0", "provider_configurations": {}}
        )
    )
    bad = config.to_dict()
    bad["provider_configurations"]["fake-default"]["models"]["standard"] = " padded "
    rejects(lambda: configuration(bad))
    rejects(lambda: RuntimeConfiguration({}))
    rejects(lambda: RuntimeConfiguration({"Bad": {"provider": "fake", "models": {}}}))
    rejects(
        lambda: RuntimeConfiguration(
            {"fake-default": {"provider": "fake", "models": {"low_cost": "x"}}}
        )
    )
    invalid_model = config.to_dict()["provider_configurations"]
    invalid_model["fake-default"]["models"]["standard"] = "\ud800"
    rejects(lambda: RuntimeConfiguration(invalid_model))
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "config.json"
        path.write_text('{"schema_version":"1.0","provider_configurations":{"x":{"provider":"fake","models":{"low_cost":"a","standard":NaN,"high_reasoning":"c"}}}}', encoding="utf-8")
        rejects(lambda: RuntimeConfiguration.load(path))
        path.write_text('{"schema_version":"1.0","schema_version":"1.0","provider_configurations":{}}', encoding="utf-8")
        rejects(lambda: RuntimeConfiguration.load(path))


def test_exact_type_boundaries() -> None:
    valid = request(run_id="malicious-request")
    malicious = BadPublicationRequest(*(
        getattr(valid, field) for field in valid.__dataclass_fields__
    ))
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        rejects(
            lambda: AgentRunner(root, configuration(), {"fake": CountingProvider()}).run(malicious),
            ContractValidationError,
        )
        assert not list(root.iterdir())
        rejects(
            lambda: AgentRunner(root, BadConfiguration(configuration().provider_configurations), {}),
            ContractValidationError,
        )
        assert not list(root.iterdir())


def test_direct_publication_no_overwrite() -> None:
    with tempfile.TemporaryDirectory() as temp:
        destination = Path(temp) / "artifact.json"
        _publish(destination, "first\n")
        assert destination.read_bytes() == b"first\n"
        rejects(lambda: _publish(destination, "second\n"), FileExistsError)
        assert destination.read_bytes() == b"first\n"
        assert sorted(Path(temp).iterdir()) == [destination]


def test_success_artifacts_and_claims() -> AgentResult:
    output = {"message": "ok"}
    raw_log = "raw\r\nprovider text\nno forced suffix"
    provider = FakeProvider(
        structured_output=output,
        raw_log=raw_log,
        claimed_changed_paths=("Pipeline/AgentRuntime/contracts.py",),
        claimed_test_commands=("python3 smoke.py",),
        claims_execution_occurred=True,
    )
    with tempfile.TemporaryDirectory() as outer:
        outer_path = Path(outer)
        run_root = outer_path / "runs"
        req = request()
        runner = AgentRunner(run_root, configuration(), {"fake": provider})
        result = runner.run(req)
        run_dir = run_root / req.run_id
        output["message"] = "provider mutation"

        assert result.status == "succeeded"
        assert result.failure_message is None
        assert result.to_dict()["structured_output"] == {"message": "ok"}
        assert result.claimed_changed_paths == (
            "Pipeline/AgentRuntime/contracts.py",
        )
        assert result.claimed_test_commands == ("python3 smoke.py",)
        assert result.claims_execution_occurred is True
        assert AgentResult.from_dict(result.to_dict()) == result
        assert replace(result) == result
        assert (run_dir / "provider.log").read_bytes() == raw_log.encode("utf-8")

        request_bytes = (run_dir / "request.json").read_bytes()
        result_bytes = (run_dir / "result.json").read_bytes()
        assert request_bytes == canonical_bytes(req.to_dict())
        assert result_bytes == canonical_bytes(result.to_dict())
        for content in (request_bytes, result_bytes):
            assert b"\r" not in content
            assert content.endswith(b"\n") and not content.endswith(b"\n\n")

        before = tree_hashes(run_dir)
        rejects(lambda: runner.run(req), RunAlreadyExistsError)
        assert tree_hashes(run_dir) == before
        assert all(path.is_relative_to(run_root) for path in outer_path.rglob("*") if path.is_file())
        return result


def test_failure_normalization() -> None:
    assert ProviderOutputInvalid.__bases__ == (ProviderInvocationError,)
    config = configuration()
    scenarios = {
        "provider_error": "provider_error",
        "output_invalid": "schema_error",
        "timeout": "timeout",
        "permission_denied": "permission_denied",
        "budget_exhausted": "budget_exhausted",
        "malformed_structured_output": "schema_error",
        "value_error": "internal_error",
    }
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for index, (scenario, expected) in enumerate(scenarios.items(), 1):
            candidate = replace(request(), run_id=f"failure-{index}")
            outcome = AgentRunner(
                root, config, {"fake": FakeProvider(scenario=scenario)}
            ).run(candidate)
            assert outcome.failure_classification == expected
            assert outcome.failure_message
            assert outcome.provider == "fake" and outcome.model == "fake-standard"

        invalid_request = replace(request(), run_id="output-invalid-artifacts")
        raw_log = "fake output invalid raw log"
        outcome = AgentRunner(
            root,
            config,
            {"fake": FakeProvider(scenario="output_invalid", raw_log=raw_log)},
        ).run(invalid_request)
        invalid_run_dir = root / invalid_request.run_id
        assert outcome.status == "failed"
        assert outcome.failure_classification == "schema_error"
        assert outcome.structured_output is None
        assert outcome.provider == "fake" and outcome.model == "fake-standard"
        assert outcome.failure_message == (
            "provider output did not yield a structured-output candidate"
        )
        assert (invalid_run_dir / "provider.log").read_bytes() == raw_log.encode("utf-8")
        assert (invalid_run_dir / "request.json").is_file()
        assert (invalid_run_dir / "provider.log").is_file()
        assert (invalid_run_dir / "result.json").is_file()
        serialized = json.loads((invalid_run_dir / "result.json").read_text("utf-8"))
        assert serialized["failure_classification"] == "schema_error"
        assert AgentResult.from_dict(serialized) == outcome

        whitespace = replace(request(), run_id="whitespace-failure")
        outcome = AgentRunner(
            root,
            config,
            {"fake": RaisingProvider(ProviderFailure("   ", raw_log="blank"))},
        ).run(whitespace)
        assert outcome.failure_classification == "provider_error"
        assert outcome.failure_message == "ProviderFailure"
        assert (root / "whitespace-failure/result.json").is_file()

        timeout = replace(request(), run_id="timeout-subclass")
        outcome = AgentRunner(
            root,
            config,
            {"fake": RaisingProvider(TimeoutSubclass("late", raw_log="exact"))},
        ).run(timeout)
        assert outcome.failure_classification == "timeout"
        assert (root / timeout.run_id / "provider.log").read_text() == "exact"

        interrupted = replace(request(), run_id="interrupt")
        runner = AgentRunner(
            root, config, {"fake": RaisingProvider(KeyboardInterrupt("stop"))}
        )
        rejects(lambda: runner.run(interrupted), KeyboardInterrupt)
        assert sorted(path.name for path in (root / interrupted.run_id).iterdir()) == [
            "request.json"
        ]
        exited = replace(request(), run_id="system-exit")
        runner = AgentRunner(root, config, {"fake": RaisingProvider(SystemExit(2))})
        rejects(lambda: runner.run(exited), SystemExit)
        generated = replace(request(), run_id="generator-exit")
        runner = AgentRunner(root, config, {"fake": RaisingProvider(GeneratorExit())})
        rejects(lambda: runner.run(generated), GeneratorExit)


def test_configuration_and_metadata_failures() -> None:
    config = configuration()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        counter = CountingProvider()
        unknown = replace(
            request(), run_id="unknown-config", provider_configuration_key="missing"
        )
        outcome = AgentRunner(root, config, {"fake": counter}).run(unknown)
        assert counter.calls == 0
        assert outcome.failure_classification == "invalid_request"
        assert outcome.provider is None and outcome.model is None
        assert "unknown provider configuration" in outcome.failure_message
        assert (root / unknown.run_id / "request.json").is_file()
        assert (root / unknown.run_id / "result.json").is_file()

        missing_registry = replace(request(), run_id="missing-registry")
        outcome = AgentRunner(root, config, {}).run(missing_registry)
        assert outcome.failure_classification == "invalid_request"
        assert "unknown provider registry entry" in outcome.failure_message

        mismatch = replace(request(), run_id="identity-mismatch")
        outcome = AgentRunner(root, config, {"fake": IdentityMismatchProvider()}).run(mismatch)
        assert outcome.failure_classification == "internal_error"
        assert "identity mismatch" in outcome.failure_message

        invalid_claim = replace(request(), run_id="invalid-claim")
        outcome = AgentRunner(
            root,
            config,
            {"fake": FakeProvider(
                structured_output={"message": "ok"},
                claimed_changed_paths=("../escape",),
                raw_log="metadata raw log",
            )},
        ).run(invalid_claim)
        assert outcome.failure_classification == "internal_error"
        assert "invalid provider response metadata" in outcome.failure_message
        assert "claimed_changed_paths" in outcome.failure_message
        assert (root / invalid_claim.run_id / "provider.log").read_text() == "metadata raw log"

        bad_container = replace(request(), run_id="bad-container")
        outcome = AgentRunner(root, config, {"fake": ContainerProvider()}).run(
            bad_container
        )
        assert outcome.failure_classification == "internal_error"
        assert "invalid response container" in outcome.failure_message



def test_model_capability_selections() -> None:
    config = configuration()
    expected = {
        "low_cost": "fake-low",
        "standard": "fake-standard",
        "high_reasoning": "fake-high",
    }
    registry = {"fake": CountingProvider()}
    for capability, model in expected.items():
        assert config.resolve("fake-default", capability, registry).model == model


def test_static_provider_neutrality() -> None:
    forbidden = ("claude", "openai", "codex", "mcp")
    for relative in ("contracts.py", "providers/base.py"):
        text = (ROOT / "Pipeline/AgentRuntime" / relative).read_text("utf-8").lower()
        assert not any(term in text for term in forbidden)
    provider_modules = {
        path.name for path in (ROOT / "Pipeline/AgentRuntime/providers").glob("*.py")
    }
    assert provider_modules == {"__init__.py", "base.py", "fake.py"}


def test_request_schema_and_authority_boundaries() -> None:
    req = request()
    serialized = req.to_dict()
    assert serialized["schema_version"] == "1.0"
    assert serialized["budgets"]["turn_limit"] == 5
    missing_turn_limit = serialized
    del missing_turn_limit["budgets"]["turn_limit"]
    rejects(lambda: AgentRequest.from_dict(missing_turn_limit))

    forbidden = {
        "complete", "conformant", "ready", "authorized", "approved",
        "integrated", "tests_passed",
    }
    for contract in (request().to_dict(), AgentResult(
        SCHEMA_VERSION, "authority-fields", "fake", "fake-standard", "implementer",
        "failed", "schema_error", "diagnostic", None, (), 0, None,
        "provider.log", False, (),
    ).to_dict()):
        assert set(contract).isdisjoint(forbidden)


def test_result_boundaries(result: AgentResult) -> None:
    rejects(lambda: replace(result, raw_log_reference="../escape.log"))
    rejects(lambda: replace(result, duration_seconds=math.inf))
    rejects(lambda: replace(result, structured_output=object()))
    rejects(
        lambda: AgentResult.from_dict(
            {**result.to_dict(), "run_id": "other", "authoritative": True}
        )
    )
    fields = set(result.to_dict())
    forbidden = {
        "complete", "conformant", "ready", "authorized", "tests_passed",
        "test_passed", "integrated", "approved",
    }
    assert fields.isdisjoint(forbidden)


def main() -> None:
    original_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    historical_before = {
        name: tree_hashes(ROOT / name) for name in ("AgentCrew", "Assignment6GER")
    }

    test_contracts_and_immutability()
    test_json_and_schema_containers()
    test_exact_nested_and_text_boundaries()
    test_configuration()
    test_exact_type_boundaries()
    test_direct_publication_no_overwrite()
    test_model_capability_selections()
    test_request_schema_and_authority_boundaries()
    result = test_success_artifacts_and_claims()
    test_failure_normalization()
    test_configuration_and_metadata_failures()
    test_response_snapshot_and_failure_audit()
    test_result_boundaries(result)
    test_static_provider_neutrality()

    assert historical_before == {
        name: tree_hashes(ROOT / name) for name in ("AgentCrew", "Assignment6GER")
    }
    final_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    before_lines = set(original_status.splitlines())
    after_lines = set(final_status.splitlines())
    expected_new = {
        f"?? Pipeline/AgentRuntime/{path.relative_to(ROOT / 'Pipeline/AgentRuntime').as_posix()}"
        for path in (ROOT / "Pipeline/AgentRuntime").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    unexpected = (after_lines - before_lines) - expected_new
    assert not unexpected, f"test created repository output: {sorted(unexpected)}"
    print("AgentRuntime smoke test: PASS (Stage 3A hardening regressions)")


if __name__ == "__main__":
    main()
