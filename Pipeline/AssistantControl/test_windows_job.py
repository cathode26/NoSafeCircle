"""Real Windows Job Object tests with only temporary Python fixtures."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
import uuid

from Pipeline.AssistantControl.process_identity import identify
from Pipeline.AssistantControl.windows_job import (
    WindowsJobError,
    active_count,
    create_and_assign,
    is_assigned,
    open_named,
    terminate_job,
)


@unittest.skipUnless(os.name == "nt", "Windows Job Objects")
class WindowsJobTests(unittest.TestCase):
    def start_fixture(self):
        code = (
            "import subprocess,sys,time\n"
            "print('ready', flush=True)\n"
            "sys.stdin.readline()\n"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(60)\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", code], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        self.assertEqual("ready\n", process.stdout.readline())
        return process

    def name(self):
        return "assistant-job-" + uuid.uuid4().hex

    def test_membership_requires_exact_identity_in_the_named_job(self):
        # Regression-only containment gate; both processes are disposable and
        # remain blocked before spawning descendants. Never assign the caller.
        processes = []
        job = None
        try:
            member = self.start_fixture()
            processes.append(member)
            unrelated = self.start_fixture()
            processes.append(unrelated)
            member_identity = identify(member.pid)
            unrelated_identity = identify(unrelated.pid)
            name = self.name()
            missing = self.name()
            job = create_and_assign(name, member_identity)
            self.assertIs(is_assigned(name, member_identity), True)
            self.assertIs(is_assigned(name, unrelated_identity), False)
            self.assertIs(is_assigned(missing, member_identity), False)
            for job_name in (name, missing):
                for changed in (
                    {**member_identity, "created_ticks": member_identity["created_ticks"] + 1},
                    {**member_identity, "image": member_identity["image"] + ".wrong"},
                ):
                    with self.subTest(job=job_name, identity=changed):
                        with self.assertRaisesRegex(WindowsJobError, "identity changed"):
                            is_assigned(job_name, changed)
            self.assertEqual(1, active_count(name))
            self.assertIsNone(unrelated.poll())
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                process.stdin.close()
                process.stdout.close()
            if job is not None:
                job.close()

    def test_assigns_parent_and_inherited_grandchild_and_terminates_both(self):
        process = self.start_fixture()
        job = None
        name = self.name()
        try:
            identity = identify(process.pid)
            job = create_and_assign(name, identity)
            process.stdin.write("go\n")
            process.stdin.flush()
            grandchild_pid = int(process.stdout.readline().strip())
            deadline = time.monotonic() + 5
            while active_count(name) < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertGreaterEqual(active_count(name), 2)
            self.assertTrue(terminate_job(name, timeout_seconds=5))
            process.wait(timeout=5)
            self.assertEqual(0, active_count(name))
            self.assertIsNotNone(grandchild_pid)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if job is not None:
                job.close()
            process.stdin.close()
            process.stdout.close()

    def test_close_does_not_kill_assigned_process_and_existing_name_is_refused(self):
        process = self.start_fixture()
        name = self.name()
        job = None
        try:
            job = create_and_assign(name, identify(process.pid))
            with self.assertRaisesRegex(WindowsJobError, "already exists"):
                create_and_assign(name, identify(process.pid))
            job.close()
            job = None
            self.assertIsNone(process.poll())
            with self.assertRaisesRegex(WindowsJobError, "disappeared"):
                open_named(name)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if job is not None:
                job.close()
            process.stdin.close()
            process.stdout.close()

    def test_wrong_identity_and_arbitrary_name_are_refused(self):
        process = self.start_fixture()
        try:
            with self.assertRaises(ValueError):
                create_and_assign("LocalSystemJob", identify(process.pid))
            identity = identify(process.pid)
            name = self.name()
            with self.assertRaisesRegex(WindowsJobError, "identity changed"):
                create_and_assign(name, {**identity, "created_ticks": identity["created_ticks"] + 1})
            job = create_and_assign(name, identity)
            self.assertEqual(1, active_count(name))
            terminate_job(name, timeout_seconds=5)
            job.close()
            with self.assertRaises(ValueError):
                active_count("Global\\arbitrary-job")
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
