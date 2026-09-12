"""Component regression: every pipeline role avoids unsolicited plugin traffic.

Construct real adapters and execute the supervisor boundary with a fake turn.
No provider, Docker, network, or project asset is used.
"""
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider
from Pipeline.ExecutionCrew.run_crew import construct_real_provider
from Pipeline.TaskReviewAgent import codex_supervisor_turn as supervisor

ROOT = Path(__file__).resolve().parents[3]
EXTERNAL = {"apps", "plugins", "plugin_sharing", "remote_plugin"}


def disabled(provider):
    argv = provider._argv("test-model", ROOT / "schema.json", ROOT / "result.json")
    return [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "--disable"]


class CodexRolePluginPolicyTests(unittest.TestCase):
    def test_implementation_and_validation_keep_repository_tools(self):
        for writable in (True, False):
            with self.subTest(writable=writable):
                provider = construct_real_provider("codex", ROOT, writable)
                self.assertEqual(set(disabled(provider)), EXTERNAL)
                self.assertFalse(provider.prohibit_tool_execution)
                self.assertEqual(provider.externally_isolated_writable_repository, writable)
                self.assertEqual(provider.externally_enforced_read_only_repository, not writable)

    def test_supervisor_disables_plugins_without_architect_prompt_policy(self):
        raw = {"run_id": "supervisor-policy-test", "prompt": "Choose the next permitted action.",
               "output_schema": {"type": "object", "properties": {"action": {"type": "string"}},
                                 "required": ["action"], "additionalProperties": False},
               "provider_turn_limit": 1, "timeout_seconds": 30,
               "reasoning_effort": "high", "model": "test-model"}
        constructed = []

        def factory(**kwargs):
            real = OpenAICodexProvider(**kwargs)
            constructed.append(real)
            return SimpleNamespace(invoke=lambda *_: SimpleNamespace(
                structured_output={"action": "wait"}, usage=None))

        output = io.StringIO()
        with patch.object(supervisor, "_request", return_value=raw), \
             patch.object(supervisor, "OpenAICodexProvider", side_effect=factory), \
             contextlib.redirect_stdout(output):
            self.assertEqual(supervisor.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["structured_output"], {"action": "wait"})
        self.assertEqual(set(disabled(constructed[0])), EXTERNAL)
        self.assertFalse(constructed[0].prohibit_tool_execution)

    def test_architect_full_tool_policy_includes_plugins_once(self):
        provider = OpenAICodexProvider(repository_root=ROOT,
                                      prohibit_tool_execution=True,
                                      prohibit_external_integrations=True)
        values = disabled(provider)
        self.assertTrue(EXTERNAL <= set(values))
        self.assertIn("shell_tool", values)
        self.assertIn("unified_exec", values)
        self.assertEqual(len(values), len(set(values)))


if __name__ == "__main__":
    unittest.main()
