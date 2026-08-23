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


def request(*, capabilities: tuple[str, ...] = (), context_paths: tuple[str, ...] = (),
            budgets: Budgets = Budgets(2, 100), run_id: str = "codex-provider-test") -> AgentInvocationRequest:
    boundaries = WriteBoundaries(("Pipeline/AgentRuntime",), ()) if "repository_write" in capabilities else WriteBoundaries((), ())
    return AgentInvocationRequest("1.0", run_id, "reviewer", "Return JSON.", context_paths,
        capabilities, boundaries, SCHEMA, "standard", budgets, "codex")


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
