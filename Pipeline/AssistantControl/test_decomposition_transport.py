import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.decomposition_transport import (
    POOL_LEASE_MOUNT,
    build_compose_command,
)


REPOSITORY = "https://example.invalid/NoSafeCircle.git"


class DecompositionTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-decompose-transport-")
        self.addCleanup(temporary.cleanup)
        self.bundle = Path(temporary.name) / "nsc-025-run.leases.json"
        self.bundle.write_text("{}\n", encoding="utf-8", newline="\n")

    def assignment(self, **overrides) -> dict:
        return {
            "lease_bundle_path": str(self.bundle),
            "repository_identity": REPOSITORY,
            "provider_environment": {
                "NSC_CLAUDE_MODEL": "claude-sonnet-5",
                "NSC_OPENAI_CODEX_MODEL": "",
            },
            **overrides,
        }

    def test_builds_bounded_two_provider_command(self):
        command = build_compose_command(
            task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
            max_calls=2, run_id="nsc-025-run",
        )
        self.assertEqual(("docker", "compose", "-p", "assistant-nsc"), command[:4])
        self.assertIn("round-robin-decompose", command)
        self.assertEqual("NSC-025", command[command.index("--task-id") + 1])
        self.assertEqual("nsc-025-run", command[command.index("--run-id") + 1])

    def test_cross_provider_command_is_unchanged_and_refuses_a_pool_assignment(self):
        """The Claude/Codex route keeps the exact argv it has always built."""
        self.assertEqual(
            (
                "docker", "compose", "-p", "assistant-nsc", "run", "--rm", "-T",
                "round-robin-decompose", "python3",
                "Pipeline/TaskDecomposition/run_round_robin_decomposition.py",
                "--task-id", "NSC-025",
                "--providers", "claude,codex",
                "--max-calls", "2",
                "--run-id", "nsc-025-run",
            ),
            build_compose_command(
                task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
                max_calls=2, run_id="nsc-025-run",
            ),
        )
        # Two distinct providers are independent by provider identity; they
        # never consume a role-session reservation.
        with self.assertRaisesRegex(ValueError, "two distinct providers"):
            build_compose_command(
                task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
                max_calls=2, run_id="nsc-025-run", pool_assignment=self.assignment(),
            )

    def test_same_provider_requires_a_pool_reservation(self):
        for providers in ("claude,claude", "codex,codex"):
            with self.subTest(providers=providers):
                with self.assertRaisesRegex(ValueError, "lease reservation"):
                    build_compose_command(
                        task_id="NSC-025", project="assistant-nsc", providers=providers,
                        max_calls=2, run_id="nsc-025-run",
                    )

    def test_pooled_same_provider_command_mounts_leases_and_pins_the_model(self):
        command = build_compose_command(
            task_id="NSC-025", project="assistant-nsc", providers="claude,claude",
            max_calls=2, run_id="nsc-025-run", pool_assignment=self.assignment(),
        )
        self.assertEqual(
            ("docker", "compose", "-p", "assistant-nsc", "run", "--rm", "-T"), command[:7],
        )
        # The lease bundle is the only new mount and it is read-only.
        self.assertEqual(
            ("--volume", f"{self.bundle}:{POOL_LEASE_MOUNT}:ro"), command[7:9],
        )
        # The container cannot resolve another model than the leases reserved.
        self.assertEqual(("--env", "NSC_CLAUDE_MODEL=claude-sonnet-5"), command[9:11])
        self.assertNotIn("--env", command[11:])
        self.assertEqual("round-robin-decompose", command[11])
        self.assertEqual("claude,claude", command[command.index("--providers") + 1])
        self.assertEqual("2", command[command.index("--max-calls") + 1])
        self.assertEqual("nsc-025-run", command[command.index("--run-id") + 1])
        self.assertEqual(
            POOL_LEASE_MOUNT, command[command.index("--role-session-leases") + 1],
        )
        self.assertEqual(
            REPOSITORY, command[command.index("--scheduler-repository-identity") + 1],
        )

    def test_pooled_codex_pair_is_accepted_symmetrically(self):
        command = build_compose_command(
            task_id="NSC-025", project="assistant-nsc", providers="codex,codex",
            max_calls=2, run_id="nsc-025-run",
            pool_assignment=self.assignment(provider_environment={
                "NSC_OPENAI_CODEX_MODEL": "gpt-5.6-sol",
            }),
        )
        self.assertEqual(("--env", "NSC_OPENAI_CODEX_MODEL=gpt-5.6-sol"), command[9:11])
        self.assertEqual("codex,codex", command[command.index("--providers") + 1])
        self.assertEqual("round-robin-decompose", command[11])

    def test_rejects_unbounded_calls(self):
        for providers, assignment in (("claude,codex", None), ("claude,claude", self.assignment())):
            with self.subTest(providers=providers), self.assertRaises(ValueError):
                build_compose_command(
                    task_id="NSC-025", project="assistant-nsc", providers=providers,
                    max_calls=3, run_id="nsc-025-run", pool_assignment=assignment,
                )

    def test_rejects_unknown_providers_and_unsafe_identifiers(self):
        for providers in ("claude", "claude,codex,claude", "claude,gemini", "gemini,gemini"):
            with self.subTest(providers=providers), self.assertRaises(ValueError):
                build_compose_command(
                    task_id="NSC-025", project="assistant-nsc", providers=providers,
                    max_calls=2, run_id="nsc-025-run",
                )
        with self.assertRaisesRegex(ValueError, "project"):
            build_compose_command(
                task_id="NSC-025", project="assistant nsc", providers="claude,codex",
                max_calls=2, run_id="nsc-025-run",
            )
        with self.assertRaisesRegex(ValueError, "run id"):
            build_compose_command(
                task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
                max_calls=2, run_id="nsc 025 run",
            )

    def test_pooled_launch_requires_the_exact_reserved_bundle_file(self):
        for overrides in (
            {"lease_bundle_path": str(self.bundle) + ".missing"},
            {"lease_bundle_path": str(self.bundle.parent)},
            {"lease_bundle_path": ""},
            {"repository_identity": "  "},
        ):
            with self.subTest(**overrides), self.assertRaises(ValueError):
                build_compose_command(
                    task_id="NSC-025", project="assistant-nsc", providers="claude,claude",
                    max_calls=2, run_id="nsc-025-run",
                    pool_assignment=self.assignment(**overrides),
                )

    def test_pool_lease_mount_matches_the_production_launcher(self):
        from Pipeline.TaskReviewAgent.host_decomposition_launcher import (
            POOL_LEASE_MOUNT as LAUNCHER_MOUNT,
        )

        self.assertEqual(LAUNCHER_MOUNT, POOL_LEASE_MOUNT)


if __name__ == "__main__":
    unittest.main()
