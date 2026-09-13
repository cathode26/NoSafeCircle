"""Docker CLI fixture responses only; never invokes Docker or paid providers."""
import hashlib
import json
import unittest
from pathlib import Path

from Pipeline.AssistantControl.docker_workers import (
    _canonical_host_path,
    inventory,
    remove_unused_project_resources,
    stop_containers,
)


class DockerBindingTests(unittest.TestCase):
    def setUp(self):
        self.checkout = Path.cwd().resolve()
        self.worker = {"run_id": "fixture", "compose_project": "assistant-crew-" + hashlib.sha256(b"fixture").hexdigest()[:20]}
        self.container = "a" * 64
        self.running = True
        self.calls = []
        self.mount = self.checkout
        self.network = "b" * 64

    def runner(self, args):
        self.calls.append(args)
        if args[0] == "ps":
            return self.container + "\n"
        if args[0] == "inspect":
            return json.dumps({"Id": self.container, "State": {"Running": self.running},
                               "Labels": {"com.docker.compose.project": self.worker["compose_project"]},
                               "Mounts": [{"Type": "bind", "Destination": "/workspace", "Source": str(self.mount)}]})
        if args[0] == "stop":
            self.assertEqual(self.container, args[-1])
            self.running = False
            return self.container
        if args[:2] == ["network", "ls"]:
            return self.network + "\n"
        if args[:2] == ["network", "inspect"]:
            return json.dumps({"Id": self.network, "Name": self.worker["compose_project"] + "_default",
                               "Labels": {"com.docker.compose.project": self.worker["compose_project"]},
                               "Containers": {}})
        if args[:2] == ["network", "rm"]:
            self.assertEqual(self.network, args[-1])
            return self.network
        if args[0] == "rm":
            self.assertEqual([self.container], args[1:])
            return self.container
        self.fail("Unexpected Docker action")

    def test_only_exact_bound_container_is_stopped_without_capacity_claim(self):
        result = stop_containers(self.checkout, self.worker, runner=self.runner)
        self.assertTrue(result["containers_stopped"])
        self.assertFalse(result["capacity_released"])
        self.assertFalse(result["host_exit_confirmed"])
        self.assertEqual(1, len([c for c in self.calls if c[0] == "stop"]))

    def test_foreign_checkout_or_project_cannot_be_stopped(self):
        self.mount = self.checkout / "another-project"
        with self.assertRaisesRegex(ValueError, "owned task"):
            stop_containers(self.checkout, self.worker, runner=self.runner)
        self.assertFalse(any(c[0] == "stop" for c in self.calls))
        with self.assertRaisesRegex(ValueError, "does not match"):
            inventory(self.checkout, {**self.worker, "run_id": "other"}, runner=self.runner)

    def test_docker_desktop_windows_mount_translation_matches_exact_checkout(self):
        # Exercise the Docker Desktop forms without requiring a live daemon.
        windows_checkout = r"C:\\NSC\\NoSafeCircle-Game-Checkouts-2\\NSC-069"
        for source in (
            r"C:\\NSC\\NoSafeCircle-Game-Checkouts-2\\NSC-069",
            "/host_mnt/c/NSC/NoSafeCircle-Game-Checkouts-2/NSC-069",
            "/run/desktop/mnt/host/c/NSC/NoSafeCircle-Game-Checkouts-2/NSC-069",
            "/mnt/host/c/NSC/NoSafeCircle-Game-Checkouts-2/NSC-069",
        ):
            self.assertEqual(
                _canonical_host_path(source),
                _canonical_host_path(windows_checkout),
            )

    def test_unknown_mount_translation_does_not_match_windows_checkout(self):
        self.assertNotEqual(
            _canonical_host_path("/some-runtime/c/NSC-069"),
            _canonical_host_path(r"C:\\NSC\\NoSafeCircle-Game-Checkouts-2\\NSC-069"),
        )

    def test_unavailable_docker_is_not_empty_inventory(self):
        def unavailable(args):
            raise RuntimeError("Fixture daemon unavailable")
        with self.assertRaises(RuntimeError):
            inventory(self.checkout, self.worker, runner=unavailable)

    def test_cleanup_removes_only_ended_project_objects_and_never_volumes(self):
        self.running = False
        result = remove_unused_project_resources(self.checkout, self.worker, runner=self.runner)
        self.assertEqual([self.container], result["containers_removed"])
        self.assertEqual([self.network], result["networks_removed"])
        self.assertEqual([], result["volumes_removed"])

    def test_cleanup_refuses_a_live_container(self):
        with self.assertRaisesRegex(ValueError, "not exited"):
            remove_unused_project_resources(self.checkout, self.worker, runner=self.runner)

    def test_cleanup_treats_disappeared_docker_objects_as_idempotent(self):
        self.running = False
        calls = {"inventory": 0}

        def disappeared(args):
            if args[0] == "ps":
                calls["inventory"] += 1
                return ""
            if args[:2] == ["network", "ls"]:
                return ""
            self.fail("No inspect or remove is needed after objects disappeared")

        result = remove_unused_project_resources(self.checkout, self.worker, runner=disappeared)
        self.assertFalse(result["cleanup_deferred"])
        self.assertEqual(1, calls["inventory"])

    def test_cleanup_docker_failure_is_deferred(self):
        def unavailable(args):
            raise RuntimeError("Docker daemon unavailable")

        result = remove_unused_project_resources(self.checkout, self.worker, runner=unavailable)
        self.assertTrue(result["cleanup_deferred"])
        self.assertEqual([], result["volumes_removed"])


if __name__ == "__main__":
    unittest.main()
