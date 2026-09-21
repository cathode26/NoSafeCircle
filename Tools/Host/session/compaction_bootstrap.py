#!/usr/bin/env python
"""Re-point an NSC agent session at its stable-path queue, and at facts that rot.

Runs as a Claude Code SessionStart and PostCompact hook for C:\\NSC. It prints one
JSON object whose hookSpecificOutput.additionalContext is injected into the model's
context, so a session that has just been compacted (or just started) is handed the
things a compaction summary reports staler than they are.

Why it exists
-------------
Runbook rule 20 makes ``agent-state/<role>-todo.md`` the authority for what is next.
Runbook rule 27 says a compaction re-attaches files read BEFORE the squish and
presents them as current, scratchpad drafts included -- so the summary and any
attached copy can both be stale while the stable path is right.

A rule an agent must remember to apply is not applied when the agent has just lost
its context. This hook applies it instead.

Contract
--------
* Always exits 0 and always prints valid JSON. A bootstrap that breaks sessions is
  worse than no bootstrap, so every failure degrades to a shorter message.
* Never resolves which role is running. The session knows its own title (CLAUDE.md:
  "your identity is your session title"); guessing it here would be a new way to be
  wrong. The injected text names the path shape and lets the session fill it in.
* Read-only. It runs git plumbing and stats files; it writes nothing.
* A fact it could not measure is printed as unknown, never as a plausible
  default. The closing line tells the reader to prefer these numbers over the
  summary's, and that instruction is only safe for numbers actually measured.
  (Astra round 6: a failed `git status` was reported as "0 dirty path(s)".)
* The whole hook shares one deadline, checked BEFORE each git call. Four calls
  that each time out independently outlive the host's own hook timeout, and a
  budget checked only at the end cannot print anything once that happens.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

NSC = Path(os.environ.get("NSC_ROOT", r"C:\NSC"))
REPO = Path(os.environ.get("NSC_REPO", r"C:\NSC\NSC\NoSafeCircle"))
STATE = NSC / "agent-state"
TIMEOUT = 8       # whole-hook budget; a slow hook delays every session start
GIT_CALL_TIMEOUT = 4  # and no single call may spend the whole of it

# Set by main(). A shared deadline rather than a per-call timeout: four calls at
# GIT_CALL_TIMEOUT each outlast the host's hook timeout (15s in settings.json),
# and the budget check that used to live at the end of main() could then never
# run. None means "no deadline installed", which is how the tests and any direct
# caller of _git() get the plain per-call timeout.
_deadline = None


def _time_left():
    """Seconds left in the whole-hook budget, or the per-call timeout if unset."""
    if _deadline is None:
        return float(GIT_CALL_TIMEOUT)
    return _deadline - time.monotonic()


def _git(*args):
    """Run git in the canonical repo. Returns stripped stdout, or None.

    None means git DID NOT ANSWER. It never means git answered with nothing --
    callers must keep those apart, because a clean tree and an unavailable git
    both look empty, and reporting the second as the first is how this hook
    told an agent that a dirty tree was clean.
    """
    left = _time_left()
    if left <= 0.5:
        return None  # the budget is gone; spending more cannot help the caller
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True, text=True, timeout=min(GIT_CALL_TIMEOUT, left),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def repo_facts():
    """The facts a compaction summary is most likely to report stale."""
    head = _git("rev-parse", "--short", "HEAD")
    if not head:
        return "  canonical repo: unavailable (git did not answer)"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "?"

    # `dirty is None` is git failing; `dirty == ""` is a genuinely clean tree.
    # The old code collapsed both to 0 with `if dirty else 0`. An invented clean
    # is the expensive direction: run_unity_tests_clean.ps1 refuses a dirty tree,
    # so a session told "0 dirty" can be routed wrongly for its whole life.
    dirty = _git("status", "--porcelain")
    dirty_known = dirty is not None
    if dirty_known:
        dirty_desc = f"{len([ln for ln in dirty.splitlines() if ln.strip()])} dirty path(s)"
    else:
        dirty_desc = "dirty paths UNKNOWN (git status did not answer)"

    counts = _git("rev-list", "--left-right", "--count", "origin/main...main")
    rel_known = bool(counts and "\t" in counts)
    if rel_known:
        behind, ahead = counts.split("\t")[0], counts.split("\t")[1]
        rel = f"{ahead} ahead / {behind} behind origin/main"
    else:
        rel = "position vs origin/main unknown"

    if dirty_known and rel_known:
        tail = "  (measured by this hook just now -- prefer it over any figure in the summary)"
    else:
        tail = ("  (measured by this hook just now, EXCEPT the fields marked unknown --\n"
                "   those were NOT measured, so do not prefer them over anything)")
    return f"  canonical main: {head} on {branch}, {dirty_desc}, {rel}\n{tail}"


def queues():
    """Stable-path queues on disk, newest first, so a stale one is visible."""
    try:
        files = sorted(STATE.glob("*-todo.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return "  agent-state: unreadable"
    if not files:
        return "  agent-state: no *-todo.md files found"
    now = time.time()
    rows = []
    for p in files[:12]:
        age_h = (now - p.stat().st_mtime) / 3600.0
        rows.append(f"  {p.name:<34} touched {age_h:5.1f}h ago")
    return "\n".join(rows)


def build():
    return (
        "NSC SESSION BOOTSTRAP (runbook rules 20 and 27)\n"
        "\n"
        "Your live queue is C:\\NSC\\agent-state\\<your-role>-todo.md -- a stable path, and\n"
        "THE AUTHORITY FOR WHAT IS NEXT. Your role is your session title.\n"
        "\n"
        "RE-READ IT AT THAT PATH NOW if this session was just compacted. A compaction\n"
        "re-attaches files read before it and presents them as current, scratchpad drafts\n"
        "included. The stable-path live file wins -- over the summary, and over any file\n"
        "the compaction hands back. 'Where the summary and the files disagree, the files\n"
        "win' is too loose: a stale draft is also a file.\n"
        "\n"
        "Queues on disk:\n" + queues() + "\n"
        "\n"
        "Facts that rot, measured now:\n" + repo_facts() + "\n"
        "\n"
        "Also stable: C:\\nscrev\\reports\\handoffs\\BOARD.md (what was handed between agents),\n"
        "C:\\NSC\\nsc-agent-directory.md (who owns what). Detail belongs in files; a message\n"
        "costs the receiver its whole context on the wake-up turn.\n"
    )


def read_event():
    """The event name must be echoed back in hookSpecificOutput, so take it from the
    payload rather than assuming. Falls back to SessionStart, the commoner case."""
    try:
        raw = sys.stdin.read()
        name = json.loads(raw).get("hook_event_name")
        return name if isinstance(name, str) and name else "SessionStart"
    except Exception:
        return "SessionStart"


def main():
    global _deadline
    started = time.monotonic()
    _deadline = started + TIMEOUT
    event = "SessionStart"
    try:
        event = read_event()
        context = build()
        if time.monotonic() - started > TIMEOUT:
            context = ("NSC SESSION BOOTSTRAP: re-read C:\\NSC\\agent-state\\<your-role>-todo.md "
                       "at its stable path (runbook rules 20 and 27). Live-fact gathering timed out.")
    except Exception as exc:  # never break a session start
        context = ("NSC SESSION BOOTSTRAP: re-read C:\\NSC\\agent-state\\<your-role>-todo.md at its "
                   f"stable path (runbook rules 20 and 27). Bootstrap degraded: {exc!r}")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": context,
        },
        "suppressOutput": True,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
