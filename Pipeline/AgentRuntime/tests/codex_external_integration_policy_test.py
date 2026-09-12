from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.contracts import AgentInvocationRequest, Budgets, WriteBoundaries
from Pipeline.AgentRuntime.process_runner import ProcessResult
from Pipeline.AgentRuntime.providers.base import ProviderTransportError
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider


class Runner:
    def __init__(self, stderr: bytes = b"") -> None:
        self.stderr = stderr
        self.argv: tuple[str, ...] = ()
        self.stdin = b""

    def run(self, argv, *, stdin, cwd, timeout_seconds):
        self.argv, self.stdin = tuple(argv), stdin
        Path(self.argv[self.argv.index("--output-last-message") + 1]).write_text(
            '{"message":"ok"}', encoding="utf-8"
        )
        stdout = (
            b'{"type":"turn.completed","usage":{"input_tokens":3,'
            b'"output_tokens":4,"reasoning_output_tokens":5,"total_tokens":12}}\n'
        )
        return ProcessResult(self.argv, 0, stdout, self.stderr, 0.1)


def invocation(run_id: str) -> AgentInvocationRequest:
    schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }
    return AgentInvocationRequest(
        "1.0", run_id, "task_decomposer", "Inspect the repository and return JSON.", (),
        ("repository_read", "repository_search"), WriteBoundaries((), ()), schema,
        "high_reasoning", Budgets(2, 100), "codex",
    )


def disabled(argv: tuple[str, ...]) -> set[str]:
    return {
        argv[index + 1]
        for index, value in enumerate(argv[:-1])
        if value == "--disable"
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-external-policy-") as text:
        root = Path(text)
        repository, temporary = root / "repo", root / "temporary"
        repository.mkdir()
        temporary.mkdir()

        runner = Runner()
        provider = OpenAICodexProvider(
            process_runner=runner,
            temporary_directory_parent=temporary,
            repository_root=repository,
            externally_enforced_read_only_repository=True,
            prohibit_external_integrations=True,
        )
        result = provider.invoke(invocation("external-policy-positive"), "gpt-test")
        assert result.structured_output == {"message": "ok"}
        assert disabled(runner.argv) == {"apps", "plugins", "plugin_sharing", "remote_plugin"}
        assert "shell_tool" not in disabled(runner.argv)
        assert "unified_exec" not in disabled(runner.argv)
        prompt = runner.stdin.decode("utf-8")
        assert "Inspect it with ordinary file and search mechanisms." in prompt
        assert "Codex architect tool policy" not in prompt

        noisy = Runner(
            b'ERROR rmcp::transport::worker: UnexpectedServerResponse("HTTP 403: ")'
        )
        provider = OpenAICodexProvider(
            process_runner=noisy,
            temporary_directory_parent=temporary,
            repository_root=repository,
            externally_enforced_read_only_repository=True,
            prohibit_external_integrations=True,
        )
        try:
            provider.invoke(invocation("external-policy-stderr"), "gpt-test")
        except ProviderTransportError:
            pass
        else:
            raise AssertionError("successful Codex exit with stderr must remain a transport error")

    print(json.dumps({"status": "passed", "tests": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
