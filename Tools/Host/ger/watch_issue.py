#!/usr/bin/env python3
"""Watch a GitHub issue for new comments.

Two modes:
- --state <file> (preferred): remembers every comment URL already seen. A comment whose body contains
  the GER owner's marker (default "<!-- claude-ger -->") is recorded as seen silently; any other
  unseen comment is printed, and only after it printed is it recorded as seen, which ends the watch.
  Comments posted between two watches are therefore never skipped. Run once with --seed to record the
  comments already read.
- --baseline <count> (legacy): exits when the comment count rises above the baseline.

Either mode also exits after --max-wait seconds as a heartbeat, so a background launcher wakes the
GER owner on either event. Output is UTF-8 (comments can contain emoji). Read-only on GitHub: it only
runs `gh issue view`.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time


def fetch(repo: str, issue: int) -> tuple[list | None, str]:
    result = subprocess.run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "comments"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return None, result.stderr.strip()
    return json.loads(result.stdout)["comments"], ""


def print_comments(comments: list) -> None:
    for comment in comments:
        print(f"--- {comment['author']['login']} {comment['createdAt']} {comment.get('url', '')}")
        print(comment["body"][:4000])
    sys.stdout.flush()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="cathode26/NoSafeCircle")
    parser.add_argument("--issue", type=int, default=127)
    parser.add_argument("--state", type=pathlib.Path, help="JSON list of comment URLs already seen")
    parser.add_argument("--seed", action="store_true", help="record every current comment as seen and exit")
    parser.add_argument("--marker", default="<!-- claude-ger -->")
    parser.add_argument("--baseline", type=int, help="legacy mode: number of comments already seen")
    parser.add_argument("--max-wait", type=int, default=1200)
    parser.add_argument("--poll", type=int, default=120)
    args = parser.parse_args()
    if (args.state is None) == (args.baseline is None):
        raise SystemExit("use exactly one of --state or --baseline")

    seen: set[str] = set()
    if args.state is not None:
        if args.seed:
            comments, error = fetch(args.repo, args.issue)
            if comments is None:
                raise SystemExit(f"gh error: {error}")
            args.state.write_text(json.dumps(sorted(c["url"] for c in comments), indent=2) + "\n", encoding="utf-8")
            print(f"SEEDED {len(comments)} comments into {args.state}")
            return 0
        if not args.state.is_file():
            raise SystemExit(f"state file missing; run with --seed first: {args.state}")
        seen = set(json.loads(args.state.read_text(encoding="utf-8")))

    started = time.time()
    errors = 0
    count = None
    while True:
        comments, error = fetch(args.repo, args.issue)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%SZ")
        if comments is None:
            errors += 1
            print(f"[{stamp}] gh error {errors}: {error}", flush=True)
            if errors >= 5:
                print("WATCH_RESULT: gh_error")
                return 2
        else:
            errors = 0
            count = len(comments)
            if args.state is not None:
                unseen = [c for c in comments if c["url"] not in seen]
                others = [c for c in unseen if args.marker not in c["body"]]
                if others:
                    print(f"WATCH_RESULT: new_comments count={len(others)} total={count} at {stamp}")
                    print_comments(others)
                if unseen:
                    seen.update(c["url"] for c in unseen)
                    args.state.write_text(json.dumps(sorted(seen), indent=2) + "\n", encoding="utf-8")
                if others:
                    return 0
            elif count > args.baseline:
                print(f"WATCH_RESULT: new_comments count={count} baseline={args.baseline} at {stamp}")
                print_comments(comments[args.baseline:])
                return 0
        if time.time() - started >= args.max_wait:
            print(f"WATCH_RESULT: heartbeat total={count} at {stamp}")
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
