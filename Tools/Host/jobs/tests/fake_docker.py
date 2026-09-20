#!/usr/bin/env python
"""Fake `docker`. Answers version / images, and records `compose run` argv.

No Docker engine, no container. Environment variables:
  FAKE_DOCKER_RECORD       file to append one JSON record per invocation
  FAKE_DOCKER_ENGINE_DOWN  "1" -> `docker version` fails like a stopped engine
  FAKE_DOCKER_NO_IMAGE     comma-separated image names to report as absent
  FAKE_DOCKER_RESULT       text for the result field of the job run
  FAKE_DOCKER_EXIT         exit code for `compose run` (default 0)
"""

import json
import os
import sys


def record(argv, stdin_text=None):
    path = os.environ.get("FAKE_DOCKER_RECORD")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({
            "exe": "docker",
            "argv": argv,
            "cwd": os.getcwd().replace("\\", "/"),
            "stdin": stdin_text,
            "msys_no_pathconv": os.environ.get("MSYS_NO_PATHCONV"),
        }) + "\n")


def main() -> int:
    argv = sys.argv[1:]

    if argv[:1] == ["version"]:
        record(argv)
        if os.environ.get("FAKE_DOCKER_ENGINE_DOWN") == "1":
            sys.stderr.write(
                "error during connect: Get http://docker/v1.51/version: "
                "open //./pipe/dockerDesktopLinuxEngine: The system cannot find "
                "the file specified.\n"
            )
            return 1
        print("29.7.2")
        return 0

    if argv[:1] == ["images"]:
        record(argv)
        wanted = argv[-1]
        absent = [x for x in os.environ.get("FAKE_DOCKER_NO_IMAGE", "").split(",") if x]
        if wanted in absent:
            return 0  # empty stdout = no such image
        print("57ffb68439a2")
        return 0

    # `docker compose ... run ... <service> claude auth status --text`: the account guard
    # asking who pays. FAKE_DOCKER_ACCOUNT overrides the email; "__none__" answers nothing.
    if argv[:1] == ["compose"] and argv[-3:] == ["auth", "status", "--text"]:
        record(argv)
        account = os.environ.get("FAKE_DOCKER_ACCOUNT", "cathode26@gmail.com")
        if account == "__none__":
            print("Login method: Claude Max account")
            return 0
        print("Login method: Claude Max account")
        print(f"Organization: {account}'s Organization")
        print(f"Email: {account}")
        return 0

    if argv[:1] == ["compose"]:
        try:
            stdin_text = sys.stdin.read()
        except Exception:
            stdin_text = ""
        record(argv, stdin_text)
        payload = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "num_turns": 4,
            "total_cost_usd": 0.0102,
            "result": os.environ.get(
                "FAKE_DOCKER_RESULT",
                "VERDICT APPROVE\nNo blocking findings.\n",
            ),
            "permission_denials": [],
            "subagent_stats": {"spawned": 0},
            "usage": {
                "input_tokens": 90,
                "output_tokens": 210,
                "cache_read_input_tokens": 4000,
                "cache_creation_input_tokens": 300,
            },
        }
        print(json.dumps(payload))
        sys.stderr.write("fake docker compose log line\n")
        return int(os.environ.get("FAKE_DOCKER_EXIT", "0"))

    record(argv)
    sys.stderr.write(f"fake docker: unsupported argv {argv}\n")
    return 64


if __name__ == "__main__":
    sys.exit(main())
