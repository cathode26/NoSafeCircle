import unittest

from Pipeline.AssistantControl.decomposition_transport import build_compose_command


class DecompositionTransportTests(unittest.TestCase):
    def test_builds_bounded_two_provider_command(self):
        command = build_compose_command(
            task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
            max_calls=2, run_id="nsc-025-run",
        )
        self.assertEqual(("docker", "compose", "-p", "assistant-nsc"), command[:4])
        self.assertIn("round-robin-decompose", command)
        self.assertEqual("NSC-025", command[command.index("--task-id") + 1])
        self.assertEqual("nsc-025-run", command[command.index("--run-id") + 1])

    def test_rejects_unbounded_or_same_provider_launches(self):
        for providers, calls in (("claude,claude", 2), ("claude,codex", 3)):
            with self.subTest(providers=providers, calls=calls), self.assertRaises(ValueError):
                build_compose_command(
                    task_id="NSC-025", project="assistant-nsc", providers=providers,
                    max_calls=calls, run_id="nsc-025-run",
                )


if __name__ == "__main__":
    unittest.main()
