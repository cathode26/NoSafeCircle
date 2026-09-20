#!/usr/bin/env python
"""Fake `claude`. Records its argv, cwd and stdin; prints a result JSON.

No provider, no network. Behaviour is steered by environment variables:
  FAKE_CLAUDE_RECORD   file to append one JSON record per invocation
  FAKE_CLAUDE_USAGE    text to print for `-p /usage` (default: a sample)
  FAKE_CLAUDE_RESULT   text for the result field of a job run
  FAKE_CLAUDE_EXIT     exit code (default 0)
  FAKE_CLAUDE_IS_ERROR "1" to report is_error true
  FAKE_CLAUDE_GARBAGE  "1" to print unparseable output instead of JSON
"""

import json
import os
import sys


def main() -> int:
    argv = sys.argv[1:]
    record = os.environ.get("FAKE_CLAUDE_RECORD")
    try:
        stdin_text = sys.stdin.read()
    except Exception:
        stdin_text = ""
    if record:
        with open(record, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({
                "exe": "claude",
                "argv": argv,
                "cwd": os.getcwd().replace("\\", "/"),
                "stdin": stdin_text,
                "msys_no_pathconv": os.environ.get("MSYS_NO_PATHCONV"),
            }) + "\n")

    # `claude auth status --text`: who would pay for this job. FAKE_CLAUDE_ACCOUNT
    # overrides the email so a test can pretend to be the wrong account.
    if "auth" in argv and "status" in argv:
        account = os.environ.get("FAKE_CLAUDE_ACCOUNT", "cathode26@gmail.com")
        if account == "__none__":
            print("Login method: Claude Max account")
            return 0
        print("Login method: Claude Max account")
        print(f"Organization: {account}'s Organization")
        print(f"Email: {account}")
        return 0

    if "/usage" in argv:
        usage = os.environ.get(
            "FAKE_CLAUDE_USAGE",
            "Account: gmail.user@gmail.com (Max)\n"
            "Current session: 42% used\n"
            "Current week (all models): 61% used\n",
        )
        print(json.dumps({"type": "result", "subtype": "success",
                          "is_error": False, "result": usage}))
        return int(os.environ.get("FAKE_CLAUDE_EXIT", "0"))

    if os.environ.get("FAKE_CLAUDE_GARBAGE") == "1":
        sys.stdout.write("not json at all\n")
        return int(os.environ.get("FAKE_CLAUDE_EXIT", "0"))

    result_text = os.environ.get(
        "FAKE_CLAUDE_RESULT",
        "ANSWER: two files write run_result.json.\nEVIDENCE:\n- a.py:10: writes it\n",
    )
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": os.environ.get("FAKE_CLAUDE_IS_ERROR") == "1",
        "num_turns": 7,
        "duration_ms": 1234,
        "total_cost_usd": 0.0421,
        "result": result_text,
        "session_id": "fake-session",
        "permission_denials": [],
        "subagent_stats": {"spawned": 0},
        "usage": {
            "input_tokens": 120,
            "output_tokens": 340,
            "cache_read_input_tokens": 5000,
            "cache_creation_input_tokens": 600,
        },
    }
    print(json.dumps(payload))
    sys.stderr.write("fake claude log line\n")
    return int(os.environ.get("FAKE_CLAUDE_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main())
