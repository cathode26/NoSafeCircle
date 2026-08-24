from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import sys
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.contracts import AgentInvocationRequest, Budgets, WriteBoundaries
from Pipeline.AgentRuntime.process_runner import ProcessResult, ProcessTimeoutError
from Pipeline.AgentRuntime.providers.base import (
    ProviderFailure, ProviderOutputInvalid, ProviderRequestRejected,
    ProviderTimeout, ProviderTransportError,
)
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider

SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}},
          "required": ["message"], "additionalProperties": False}
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


def request(*, capabilities: tuple[str, ...] = (), context_paths: tuple[str, ...] = (),
            budgets: Budgets = Budgets(2, 100), run_id: str = "codex-provider-test",
            boundaries: WriteBoundaries | None = None,
            output_schema: dict[str, Any] = SCHEMA) -> AgentInvocationRequest:
    boundaries = boundaries or (WriteBoundaries(("Pipeline/AgentRuntime",), ()) if "repository_write" in capabilities else WriteBoundaries((), ()))
    return AgentInvocationRequest("1.0", run_id, "reviewer", "Return JSON.", context_paths,
        capabilities, boundaries, output_schema, "standard", budgets, "codex")


class FakeRunner:
    def __init__(self, *, stdout: bytes | None = None, stderr: bytes = b"", returncode: int = 0,
                 final: str | None = '{"message":"ok"}', timeout: bool = False) -> None:
        self.stdout = stdout or (
            b'{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":4,'
            b'"reasoning_output_tokens":5,"total_tokens":12}}\n'
        )
        self.stderr, self.returncode, self.final, self.timeout = stderr, returncode, final, timeout
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: tuple[str, ...], *, stdin: bytes, cwd: Path,
            timeout_seconds: float) -> ProcessResult:
        args = tuple(argv)
        self.calls.append({"argv": args, "stdin": stdin, "cwd": Path(cwd), "timeout": timeout_seconds})
        final_path = Path(args[args.index("--output-last-message") + 1])
        schema_path = Path(args[args.index("--output-schema") + 1])
        self.calls[-1]["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        if self.final is not None:
            final_path.write_text(self.final, encoding="utf-8")
        result = ProcessResult(args, self.returncode, self.stdout, self.stderr, 0.1)
        if self.timeout:
            raise ProcessTimeoutError(result)
        return result


def rejects(action: Any, expected: type[BaseException]) -> None:
    try:
        action()
    except expected:
        return
    raise AssertionError(f"expected {expected.__name__}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-provider-test-") as text:
        temp = Path(text)
        repository = temp / "repo"
        repository.mkdir()
        outside = temp / "outside"
        outside.mkdir()
        runner = FakeRunner()
        provider = OpenAICodexProvider(reasoning_effort="xhigh", process_runner=runner,
            temporary_directory_parent=outside, repository_root=repository)
        assert provider.provider_identifier == "openai-codex"
        response = provider.invoke(request(), "gpt-concrete-1")
        call = runner.calls[0]
        assert call["stdin"] == b"Return JSON."
        assert call["cwd"] != repository and call["cwd"].parent == outside
        assert call["timeout"] == 60
        argv = call["argv"]
        assert argv[:2] == ("codex", "exec") and argv[-1] == "-"
        for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config",
                     "--skip-git-repo-check", "--json", "--output-schema", "--output-last-message"):
            assert flag in argv
        assert argv[argv.index("--model") + 1] == "gpt-concrete-1"
        assert "model_reasoning_effort=xhigh" in argv
        schema_path = Path(argv[argv.index("--output-schema") + 1])
        assert call["schema"] == SCHEMA
        assert not schema_path.exists() and not call["cwd"].exists()
        assert response.structured_output == {"message": "ok"}
        assert response.raw_log == runner.stdout.decode()
        assert response.usage and response.usage.to_dict() == {
            "input_tokens": 3, "output_tokens": 9, "total_tokens": 12,
            "estimated_cost_usd": None,
        }

        nullable_runner = FakeRunner(final='{"artifact_proposal":null}')
        nullable_provider = OpenAICodexProvider(
            process_runner=nullable_runner,
            temporary_directory_parent=outside,
            repository_root=repository,
        )
        nullable_response = nullable_provider.invoke(
            request(run_id="codex-nullable-schema", output_schema=NULLABLE_SCHEMA),
            "gpt-concrete-1",
        )
        assert nullable_response.structured_output == {"artifact_proposal": None}
        assert nullable_runner.calls[0]["schema"] == NULLABLE_SCHEMA
        assert nullable_runner.calls[0]["schema"]["properties"]["artifact_proposal"]["type"] == [
            "object", "null"
        ]

        for capabilities in (("repository_read",), ("repository_search",),
                             ("repository_read", "repository_search")):
            read_runner = FakeRunner()
            read_provider = OpenAICodexProvider(process_runner=read_runner,
                temporary_directory_parent=outside, repository_root=repository,
                externally_enforced_read_only_repository=True)
            read_provider.invoke(request(capabilities=capabilities,
                context_paths=("Docs/AI-Pipeline/START_HERE.md",)), "gpt-concrete-2")
            assert read_runner.calls[0]["cwd"] == repository
            assert b"Relevant repository paths" in read_runner.calls[0]["stdin"]

        no_profile = OpenAICodexProvider(process_runner=FakeRunner(),
            temporary_directory_parent=outside, repository_root=repository)
        rejects(lambda: no_profile.invoke(request(capabilities=("repository_read",)), "gpt"), ProviderRequestRejected)
        rejects(lambda: no_profile.invoke(request(capabilities=("repository_search",)), "gpt"), ProviderRequestRejected)
        rejects(lambda: provider.invoke(request(context_paths=("Docs/x",)), "gpt"), ProviderRequestRejected)
        rejects(lambda: provider.invoke(request(capabilities=("repository_write",)), "gpt"), ProviderRequestRejected)
        rejects(lambda: provider.invoke(request(capabilities=("approved_command_execution",)), "gpt"), ProviderRequestRejected)
        rejects(lambda: provider.invoke(request(budgets=Budgets(1, 10, 5)), "gpt"), ProviderRequestRejected)

        write_caps = ("repository_read", "repository_search", "repository_write")
        write_boundaries = WriteBoundaries(("allowed/file.txt", "allowed/subdir"),
                                           ("allowed/subdir/denied.txt", "private"))
        write_request = request(capabilities=write_caps, boundaries=write_boundaries)
        rejects(lambda: provider.invoke(write_request, "gpt"), ProviderRequestRejected)
        for forbidden_root in (ROOT, ROOT / "Pipeline", ROOT.parent):
            forbidden = OpenAICodexProvider(process_runner=FakeRunner(),
                temporary_directory_parent=outside, repository_root=forbidden_root,
                externally_isolated_writable_repository=True)
            rejects(lambda forbidden=forbidden: forbidden.invoke(write_request, "gpt"),
                    ProviderRequestRejected)
        missing = OpenAICodexProvider(process_runner=FakeRunner(),
            temporary_directory_parent=outside, repository_root=temp / "missing",
            externally_isolated_writable_repository=True)
        rejects(lambda: missing.invoke(write_request, "gpt"), ProviderRequestRejected)

        for source_temporary_parent in (ROOT, ROOT / "Pipeline"):
            source_parent_runner = FakeRunner()
            source_parent_provider = OpenAICodexProvider(
                process_runner=source_parent_runner,
                temporary_directory_parent=source_temporary_parent,
                repository_root=repository,
                externally_isolated_writable_repository=True)
            rejects(
                lambda source_parent_provider=source_parent_provider:
                    source_parent_provider.invoke(write_request, "gpt"),
                ProviderTransportError)
            assert source_parent_runner.calls == []

        write_runner = FakeRunner()
        writable = OpenAICodexProvider(process_runner=write_runner,
            temporary_directory_parent=outside, repository_root=repository,
            externally_isolated_writable_repository=True)
        writable.invoke(write_request, "gpt-write")
        write_call = write_runner.calls[0]
        assert write_call["cwd"] == repository.resolve()
        write_prompt = write_call["stdin"].decode("utf-8")
        assert "disposable isolated writable repository" in write_prompt
        assert ("Allowed write paths:\n- allowed/file.txt\n- allowed/subdir\n"
                "Denied write paths:\n- allowed/subdir/denied.txt\n- private") in write_prompt
        assert "request.is_path_writable(path)" in write_prompt
        assert ("You may use the minimum provider-local file-editing mechanism necessary "
                "to inspect and edit the permitted files.") in write_prompt
        assert ("Do not run project commands, tests, builds, project scripts, package "
                "managers, Unity, or destructive/state-changing Git operations.") in write_prompt
        assert "This does not grant AgentRuntime approved_command_execution." in write_prompt
        assert "not native path-level enforcement" in write_prompt
        rejects(lambda: writable.invoke(request(capabilities=("repository_read",)), "gpt"),
                ProviderRequestRejected)
        rejects(lambda: OpenAICodexProvider(
            externally_enforced_read_only_repository=True,
            externally_isolated_writable_repository=True), ValueError)
        rejects(lambda: writable.invoke(request(capabilities=write_caps,
            budgets=Budgets(1, 10, 5)), "gpt"), ProviderRequestRejected)
        rejects(lambda: writable.invoke(request(capabilities=write_caps +
            ("approved_command_execution",)), "gpt"), ProviderRequestRejected)

        cases = [
            (FakeRunner(final=None), ProviderOutputInvalid),
            (FakeRunner(final="{"), ProviderOutputInvalid),
            (FakeRunner(stdout=b"not-json\n"), ProviderOutputInvalid),
            (FakeRunner(stdout=b'{"type":"turn.started"}\n'), ProviderOutputInvalid),
            (FakeRunner(stdout=b'{"type":"turn.completed","usage":{"input_tokens":true}}\n'), ProviderTransportError),
            (FakeRunner(returncode=2), ProviderFailure),
            (FakeRunner(timeout=True), ProviderTimeout),
            (FakeRunner(stderr=b"warning"), ProviderTransportError),
        ]
        for index, (bad_runner, error) in enumerate(cases):
            bad = OpenAICodexProvider(process_runner=bad_runner,
                temporary_directory_parent=outside, repository_root=repository)
            rejects(lambda bad=bad, index=index: bad.invoke(request(run_id=f"bad-{index}"), "gpt"), error)

        assert list(repository.iterdir()) == []
    print("openai_codex_provider_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
