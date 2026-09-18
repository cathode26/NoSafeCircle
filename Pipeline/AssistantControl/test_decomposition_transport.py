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

    def test_cross_provider_command_refuses_a_pool_assignment(self):
        """Two distinct providers are independent by provider identity, so they
        never consume a role-session reservation.

        This test used to also assert the mixed-provider argv verbatim, under
        the name "keeps the exact argv it has always built". That assertion was
        the defect: the argv it pinned carried no ``--env``, so the container
        resolved its own default model while the run reported success. A test
        can hold a bug in place as firmly as it holds a feature.
        """
        with self.assertRaisesRegex(ValueError, "two distinct providers"):
            build_compose_command(
                task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
                max_calls=2, run_id="nsc-025-run", pool_assignment=self.assignment(),
            )

    def test_cross_provider_command_carries_the_resolved_models(self):
        """The whole point of the fix: a mixed pair gets its models too.

        ``provider_environment`` used to be read only from ``pool_assignment``,
        and a mixed pair is forbidden from having one - so ``claude,codex`` runs
        were launched with no ``--env`` at all and
        ``live_decomposition.provider_configuration`` fell back to
        ``claude-sonnet-5`` inside the container. Nothing failed; the run just
        silently used a different model than the caller asked for. The
        escalation ladder's top rung is a mixed-provider rung, so the rung that
        exists to escalate was the one that silently did not.
        """
        command = build_compose_command(
            task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
            max_calls=2, run_id="nsc-025-run",
            provider_environment={
                "NSC_CLAUDE_MODEL": "claude-opus-5",
                "NSC_OPENAI_CODEX_MODEL": "gpt-6-astra",
            },
        )
        self.assertEqual(
            ("docker", "compose", "-p", "assistant-nsc", "run", "--rm", "-T"), command[:7],
        )
        self.assertEqual(
            ("--env", "NSC_CLAUDE_MODEL=claude-opus-5",
             "--env", "NSC_OPENAI_CODEX_MODEL=gpt-6-astra"),
            command[7:11],
        )
        self.assertEqual("round-robin-decompose", command[11])
        # No lease bundle: a mixed pair carries no reservation.
        self.assertNotIn("--volume", command)
        self.assertNotIn("--role-session-leases", command)

    def test_cross_provider_command_without_models_is_unchanged(self):
        """Callers that pass nothing still build exactly the old argv."""
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

    def test_empty_model_values_are_skipped_not_forwarded_blank(self):
        """An unset model must not become ``NSC_CLAUDE_MODEL=``, which would
        override the container's own default with the empty string."""
        command = build_compose_command(
            task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
            max_calls=2, run_id="nsc-025-run",
            provider_environment={"NSC_CLAUDE_MODEL": "claude-opus-5",
                                  "NSC_OPENAI_CODEX_MODEL": ""},
        )
        self.assertEqual(("--env", "NSC_CLAUDE_MODEL=claude-opus-5"), command[7:9])
        self.assertEqual("round-robin-decompose", command[9])

    def test_a_pooled_run_refuses_a_second_source_of_models(self):
        """Two sources of truth for the model is the failure this whole area
        keeps having. A pooled run's model comes from its reservation, and a
        caller passing a different one gets a refusal, not a silent winner."""
        with self.assertRaisesRegex(ValueError, "one source"):
            build_compose_command(
                task_id="NSC-025", project="assistant-nsc", providers="claude,claude",
                max_calls=2, run_id="nsc-025-run",
                pool_assignment=self.assignment(),
                provider_environment={"NSC_CLAUDE_MODEL": "claude-opus-5"},
            )

    def test_model_environment_names_are_checked(self):
        """Only the two model variables may be injected. --env is a hole into
        the container, and this is not a general passthrough."""
        for name in ("PATH", "ANTHROPIC_API_KEY", "NSC_CLAUDE_MODEL=x", "", "A B"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "model environment"):
                    build_compose_command(
                        task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
                        max_calls=2, run_id="nsc-025-run",
                        provider_environment={name: "value"},
                    )

    def test_model_values_cannot_smuggle_an_argument(self):
        for value in ("a b", "a\nb", "--privileged", "a\tb"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "model value"):
                    build_compose_command(
                        task_id="NSC-025", project="assistant-nsc", providers="claude,codex",
                        max_calls=2, run_id="nsc-025-run",
                        provider_environment={"NSC_CLAUDE_MODEL": value},
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
