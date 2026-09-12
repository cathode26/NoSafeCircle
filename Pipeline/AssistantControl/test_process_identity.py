"""Actual short-lived Windows processes; no providers or task workers."""
import os
import subprocess
import sys
import unittest

from Pipeline.AssistantControl.process_identity import identify, matches, terminate


@unittest.skipUnless(os.name == "nt", "Windows process API")
class IdentityTests(unittest.TestCase):
    def test_current_process_and_recycled_pid_identity(self):
        identity = identify(os.getpid())
        self.assertTrue(matches(identity))
        self.assertFalse(matches({**identity, "created_ticks": identity["created_ticks"] + 1}))
        self.assertFalse(matches({**identity, "image": "another executable"}))

    def test_exited_process_is_not_running(self):
        process = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            identity = identify(process.pid)
            self.assertTrue(matches(identity))
            process.communicate(timeout=5)
            self.assertFalse(matches(identity))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def test_invalid_pid_is_rejected(self):
        for value in (0, -1, True, "123"):
            with self.assertRaises(ValueError):
                identify(value)

    def test_termination_checks_identity_before_stopping_exact_fixture_process(self):
        process = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            identity = identify(process.pid)
            with self.assertRaisesRegex(ValueError, "identity changed"):
                terminate({**identity, "created_ticks": identity["created_ticks"] + 1})
            self.assertIsNone(process.poll())
            self.assertTrue(terminate(identity))
            process.wait(timeout=5)
            self.assertFalse(matches(identity))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdin.close()


if __name__ == "__main__":
    unittest.main()
