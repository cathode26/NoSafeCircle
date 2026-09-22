#!/usr/bin/env python
"""Run reset_task_smoke_test.py as N independent processes.

Extra shards are not parallelism by themselves. The workflow runs its Python
commands sequentially, with the reset suite inside one of them, so a shard
selector with no dispatcher saves nothing. This is the dispatcher.

Processes rather than threads, deliberately: `approved_identity_environment()`
clears and repopulates process-global `os.environ`, and it is shared with the
graph apply/undo consumers, so two threads overlapping there can spawn git with
no PATH. Separate processes isolate that for free and need no audit of it.

    python run_reset_shards.py                  # shards = workers = CPU count, max 4
    python run_reset_shards.py --shards 4 --workers 4
    python run_reset_shards.py --shards 4 --workers 1    # serial, same partition

Exit code is the first non-zero child exit, or 0. A shard that exceeds
--timeout is killed with its whole process tree and reported as a failure;
nothing is left running behind a green result.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import pathlib
import subprocess
import sys
import tempfile
import time

SUITE = pathlib.Path(__file__).resolve().parent / "reset_task_smoke_test.py"
DEFAULT_TIMEOUT = 1800


def read_inventory(repo: pathlib.Path) -> list[str]:
    """The case identities the suite says exist, collected before any shard runs.

    Fatal on failure, deliberately. The previous version ran this after the
    shards and only validated when the inventory command happened to succeed,
    so the one situation the check existed for -- not knowing what should have
    run -- was the situation it skipped.
    """
    listing = subprocess.run([sys.executable, "-B", str(SUITE), "--list"],
                             cwd=str(repo), capture_output=True, text=True)
    if listing.returncode != 0:
        sys.exit(f"*** inventory command failed (exit {listing.returncode}); "
                 f"refusing to run shards without knowing what should run.\n"
                 f"{(listing.stderr or '').strip()[:800]}")
    names = [line.split("\t")[0].strip()
             for line in (listing.stdout or "").splitlines() if line.strip()]
    if not names:
        sys.exit("*** inventory is empty; refusing to run shards, because "
                 "every partition trivially satisfies an empty expectation.")
    if len(set(names)) != len(names):
        sys.exit("*** inventory lists a duplicate case name; the partition "
                 "cannot be verified against it.")
    return names


def workers_default() -> int:
    """Match the runner rather than this host. A 22-core dev box would pick a
    partition that a 4-core runner cannot execute in parallel, and the measured
    comparison would then describe a machine CI does not have."""
    return min(4, os.cpu_count() or 1)


def run_shard(index: int, count: int, repo: pathlib.Path, timeout: int) -> dict:
    """One shard in its own process, with its own temp root."""
    scratch = tempfile.mkdtemp(prefix=f"reset-shard-{index}-")
    environment = dict(os.environ)
    environment["TEMP"] = scratch
    environment["TMP"] = scratch

    started = time.perf_counter()
    process = subprocess.Popen(
        [sys.executable, "-B", str(SUITE), "--shard", f"{index}/{count}"],
        cwd=str(repo), env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True)
    try:
        output, _ = process.communicate(timeout=timeout)
        code = process.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        # Kill the tree: a bare terminate() leaves git children running, and a
        # shard that outlived its budget must not look like a pass.
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                       capture_output=True)
        output, _ = process.communicate()
        code, timed_out = 124, True

    elapsed = time.perf_counter() - started
    names = [line[5:].strip() for line in (output or "").splitlines()
             if line.startswith("PASS ")]
    return {"index": index, "code": code, "seconds": elapsed,
            "passes": len(names), "names": names, "timed_out": timed_out,
            "output": output or "", "scratch": scratch}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--shards", type=int, default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    shards = args.shards or workers_default()
    workers = args.workers or shards
    repo = pathlib.Path(args.repo).resolve()
    if not SUITE.is_file():
        sys.exit(f"*** suite not found: {SUITE}")

    # Collected BEFORE anything is launched. When this ran afterwards it was
    # wrapped in a success test, so an unusable inventory skipped the check it
    # was supposed to perform and the driver exited 0 with nothing verified.
    inventory = read_inventory(repo)
    print(f"reset shards: {shards} shard(s), {workers} worker(s), "
          f"{len(inventory)} case(s) expected, repo {repo}", flush=True)
    started = time.perf_counter()
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [pool.submit(run_shard, i, shards, repo, args.timeout)
                   for i in range(shards)]
        for future in concurrent.futures.as_completed(pending):
            result = future.result()
            results.append(result)
            state = ("TIMEOUT" if result["timed_out"]
                     else "ok" if result["code"] == 0 else f"exit {result['code']}")
            print(f"  shard {result['index']}/{shards}: {state}, "
                  f"{result['seconds']:.1f}s, {result['passes']} cases",
                  flush=True)
    total = time.perf_counter() - started

    results.sort(key=lambda r: r["index"])
    cases = sum(r["passes"] for r in results)
    failed = [r for r in results if r["code"] != 0]

    if failed and not args.quiet:
        for result in failed:
            print(f"\n----- shard {result['index']} output -----")
            print(result["output"].strip()[-4000:])

    slowest = max(results, key=lambda r: r["seconds"])
    print(f"\ntotal wall clock : {total:.1f}s")
    print(f"slowest shard    : {slowest['index']} at {slowest['seconds']:.1f}s")
    print(f"cases reported   : {cases}")
    print(f"shards failed    : {len(failed)}")

    print(f"cases expected   : {len(inventory)}")

    # Identities, not counts: a partition that drops one case and duplicates
    # another has the right total and the wrong coverage.
    ran: list[str] = []
    for result in results:
        ran.extend(result["names"])
    missing = sorted(set(inventory) - set(ran))
    unexpected = sorted(set(ran) - set(inventory))
    repeated = sorted({name for name in ran if ran.count(name) > 1})

    for label, names in (("never ran", missing), ("not in the inventory",
                                                  unexpected),
                         ("ran more than once", repeated)):
        if names:
            print(f"*** {len(names)} case(s) {label}:")
            for name in names[:10]:
                print(f"      {name}")

    if failed:
        return failed[0]["code"]
    if missing or unexpected or repeated:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
