#!/usr/bin/env python
"""A stand-in for the bundled Codex CLI. No provider calls, no network.

Driven entirely by environment variables so one binary can play every case:

    FAKE_CODEX_VERSION        what `--version` prints (default 0.155.0-alpha.2.6)
    FAKE_CODEX_MODE           ok | no_thread | model_unavailable | fail | hang | empty_out
    FAKE_CODEX_ANSWER         what to write to the -o file (default "READY")
    FAKE_CODEX_THREAD_ID      thread id for `exec` (default a fixed uuid-ish string)
    FAKE_CODEX_HANG_SECONDS   how long `hang` sleeps (default 60)
    FAKE_CODEX_ARGV_LOG       append one JSON line per invocation: {argv, stdin, cwd}
    FAKE_CODEX_EVENT_ANSWER   if set, the answer goes only into the JSONL events,
                              never into the -o file (exercises the fallback reader)
    FAKE_CODEX_NOISE_STDERR   printed to stderr before a SUCCESSFUL run. The real CLI
                              does this when it retries a transient stream error, so
                              "requires a newer version of Codex" can appear on stderr
                              of a call that then answers perfectly well.
"""

from __future__ import annotations

import json
import os
import sys
import time


def _log(argv, stdin_text):
    path = os.environ.get("FAKE_CODEX_ARGV_LOG")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"argv": argv, "stdin": stdin_text}) + "\n")


def _opt(argv, name):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def main() -> int:
    argv = sys.argv[1:]

    if "--version" in argv:
        print(os.environ.get("FAKE_CODEX_VERSION", "codex-cli 0.155.0-alpha.2.6"))
        return 0

    stdin_text = ""
    if "-" in argv:
        try:
            stdin_text = sys.stdin.read()
        except Exception:  # pragma: no cover - stdin closed
            stdin_text = ""
    _log(argv, stdin_text)

    mode = os.environ.get("FAKE_CODEX_MODE", "ok")
    out_path = _opt(argv, "-o")
    resuming = "resume" in argv
    answer = os.environ.get("FAKE_CODEX_ANSWER", "READY")

    if mode == "hang":
        time.sleep(float(os.environ.get("FAKE_CODEX_HANG_SECONDS", "60")))
        return 0

    if mode == "model_unavailable":
        print("stream error: `gpt-6-astra` requires a newer version of Codex", file=sys.stderr)
        return 1

    if mode == "fail":
        print("boom: something in the CLI broke", file=sys.stderr)
        return 7

    noise = os.environ.get("FAKE_CODEX_NOISE_STDERR")
    if noise:
        print(noise, file=sys.stderr)

    thread_id = os.environ.get("FAKE_CODEX_THREAD_ID", "01a0ae11-fake-4d1e-9b77-000000000001")
    if not resuming and mode != "no_thread":
        print(json.dumps({"type": "thread.started", "thread_id": thread_id}))

    event_only = os.environ.get("FAKE_CODEX_EVENT_ANSWER")
    if event_only:
        print(json.dumps({"type": "item.completed", "item": {"text": event_only}}))
    elif mode != "empty_out" and out_path:
        with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(answer + "\n")

    print(json.dumps({"type": "turn.completed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
