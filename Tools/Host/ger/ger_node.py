"""Drive one held task through GER packet preparation and the four provider rounds.

Usage:
    python ger_node.py NSC-045                       # fresh packet at current clean main
    python ger_node.py NSC-044 --existing-packet <dir> # continue rounds of an existing packet

Steps:
1. Confirm the task is held in the journal's GER-holds section and in held-task-ids.json.
2. Fresh mode: record canonical HEAD and prepare a new packet with task_content_ger.py.
3. Create or reuse the blob-exact snapshot of the packet's source commit (shared, locked).
4. Start the live viewer marker (safe to repeat for an active task).
5. Run the missing rounds 01..04 in order with ger_round.py; stop at the first failure.
6. Write NODE_STATUS.json. On failure the marker is paused and the task stays held.

Contract edits, commits, journal release and `finish` are done afterwards by the GER owner.
Never edits the repository, the journal, task contracts or the graph.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import time

CANONICAL = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
CHECKOUT_ROOT = pathlib.Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts")
CONTROL = CHECKOUT_ROOT / ".assistant-control"
GER_ROOT = pathlib.Path(r"C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER")
SNAPSHOTS = GER_ROOT / "_snapshots"
TOOLS = pathlib.Path(__file__).resolve().parent
PYTHON = sys.executable
ROUNDS = ["01-codex-generate", "02-claude-evaluate", "03-codex-refine", "04-claude-reaudit"]
SNAPSHOT_PATHS = ["AGENTS.md", "Tasks", "Docs", "Pipeline/TaskGraph", "Assets", "ProjectSettings", "Packages"]
# Full Assets/ scope. Older "<sha12>-blob" snapshots held only Assets/NoSafeCircle and Assets/Scenes.
SNAPSHOT_SUFFIX = "assets-blob"
RECOMMENDATIONS = ["commit_contract_then_decompose", "commit_contract", "needs_design", "blocked_not_design",
                   "release_without_change"]


def log(message: str) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


def run(command: list[str], cwd: pathlib.Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(command[:6])} failed ({result.returncode}): {result.stderr.strip()[:800]}")
    return result


def confirm_held(task_id: str) -> None:
    journal = (CONTROL / "graph-lead-journal.md").read_text(encoding="utf-8")
    match = re.search(r"^## [^\n]*GER holds[^\n]*\n(.*?)(?=^## )", journal, flags=re.S | re.M)
    if not match or not re.search(rf"\b{re.escape(task_id)}\b", match.group(1)):
        raise RuntimeError(f"{task_id} is not listed in the journal's GER-holds section")
    held = json.loads((CONTROL / "held-task-ids.json").read_text(encoding="utf-8"))
    if task_id not in held.get("task_ids", []):
        raise RuntimeError(f"{task_id} is not in held-task-ids.json task_ids")


PACKET_SOURCE_PATHS = ["Tasks", "Docs", "Pipeline/GDDRAG", "Pipeline/TaskDesignGER", "Pipeline/TaskGraph",
                       "Assets/NoSafeCircle/DoorPrototype/Art"]


def prepare_packet(task_id: str, feedback_file: pathlib.Path | None, problem_file: pathlib.Path | None = None,
                   focus: str = "auto") -> pathlib.Path:
    # Packet-relevant sources must be committed; unrelated uncommitted work on main (for example
    # Primary Sol's pipeline edits) never enters the packet or snapshot and is only recorded.
    relevant = run(["git", "-C", str(CANONICAL), "status", "--porcelain=v1", "--untracked-files=no", "--",
                    *PACKET_SOURCE_PATHS]).stdout.strip()
    if relevant:
        raise RuntimeError(f"packet source paths have uncommitted changes; not preparing a packet:\n{relevant}")
    unrelated = run(["git", "-C", str(CANONICAL), "status", "--porcelain=v1", "--untracked-files=no"]).stdout.strip()
    if unrelated:
        log(f"{task_id}: note - unrelated uncommitted tracked changes on main are excluded from the packet: "
            f"{unrelated.replace(chr(10), '; ')}")
    head = run(["git", "-C", str(CANONICAL), "rev-parse", "HEAD"]).stdout.strip()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    packet = GER_ROOT / f"{stamp}-{task_id}"
    command = [PYTHON, "-B", "Pipeline/TaskDesignGER/task_content_ger.py", task_id, "--output-dir", str(packet)]
    if feedback_file is not None:
        command += ["--feedback-file", str(feedback_file)]
    if problem_file is not None:
        command += ["--problem-file", str(problem_file)]
    if focus != "auto":
        command += ["--focus", focus]
    run(command, cwd=CANONICAL)
    identity = json.loads((packet / "SOURCE_IDENTITY.json").read_text(encoding="utf-8"))
    if identity["source_head"] != head:
        raise RuntimeError(f"packet source_head {identity['source_head']} != HEAD {head} observed before preparation")
    log(f"{task_id}: packet {packet} at {head}")
    return packet


def ensure_snapshot(sha: str) -> pathlib.Path:
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    snapshot = SNAPSHOTS / f"{sha[:12]}-{SNAPSHOT_SUFFIX}"
    identity = SNAPSHOTS / f"{sha[:12]}-{SNAPSHOT_SUFFIX}.SNAPSHOT_IDENTITY.json"
    lock = SNAPSHOTS / f"{sha[:12]}-{SNAPSHOT_SUFFIX}.lock"
    for _ in range(900):
        if identity.is_file():
            return snapshot
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            time.sleep(2)
            continue
        try:
            if identity.is_file():
                return snapshot
            if snapshot.exists():
                raise RuntimeError(f"partial snapshot without identity exists; inspect before retry: {snapshot}")
            snapshot.mkdir()
            archive = subprocess.Popen(["git", "-c", "core.autocrlf=false", "-C", str(CANONICAL), "archive",
                                        "--format=tar", sha, *SNAPSHOT_PATHS], stdout=subprocess.PIPE)
            with tarfile.open(fileobj=archive.stdout, mode="r|") as tar:
                tar.extractall(snapshot, filter="data")
            # Drain the trailing tar padding: tarfile stops reading at the end-of-archive blocks, and a full
            # pipe would otherwise leave git archive blocked on write while this process waits for it.
            archive.stdout.read()
            archive.stdout.close()
            if archive.wait() != 0:
                raise RuntimeError(f"git archive failed for {sha}")
            tree = run(["git", "-C", str(CANONICAL), "rev-parse", f"{sha}^{{tree}}"]).stdout.strip()
            count = sum(1 for path in snapshot.rglob("*") if path.is_file())
            identity.write_text(json.dumps({"source_head": sha, "source_tree": tree, "paths": SNAPSHOT_PATHS,
                                            "file_count": count, "bytes": "git blob bytes (core.autocrlf=false)"},
                                           indent=2) + "\n", encoding="utf-8")
            log(f"snapshot {snapshot} created ({count} files)")
            return snapshot
        finally:
            os.close(descriptor)
            lock.unlink(missing_ok=True)
    raise RuntimeError(f"timed out waiting for snapshot lock {lock}")


def marker(action: str, task_id: str) -> None:
    result = run([PYTHON, "-B", "-m", "Pipeline.TaskDesignGER.ger_viewer_marker", action, task_id,
                  "--checkout-root", str(CHECKOUT_ROOT)], cwd=CANONICAL, check=False)
    if result.returncode != 0:
        log(f"{task_id}: marker {action} failed: {result.stderr.strip()[:400]}")
    else:
        log(f"{task_id}: marker {action} ok")


RETRY_TRANSIENT_FAILURE = False
# A multi-day "usage limit" quota is deliberately absent: it needs the operator, not an automatic retry.
TRANSIENT_FAILURE_MARKERS = ("session limit", "rate limit", "at capacity")


def transient_failure(directory: pathlib.Path) -> bool:
    """True only when the provider refused the call (HTTP 429, a session/usage/rate limit, or capacity)."""
    texts = []
    raw = directory / "RAW_RESPONSE.json"
    if raw.is_file():
        try:
            data = json.loads(raw.read_text(encoding="utf-8", errors="replace"))
            if str(data.get("api_error_status")) == "429":
                return True
            texts.append(str(data.get("result", "")))
        except ValueError:
            texts.append(raw.read_text(encoding="utf-8", errors="replace")[-2000:])
    for name in ("STDERR.log", "FAILED.json"):
        if (directory / name).is_file():
            texts.append((directory / name).read_text(encoding="utf-8", errors="replace")[-4000:])
    blob = " ".join(texts).lower()
    return any(marker in blob for marker in TRANSIENT_FAILURE_MARKERS)


def round_complete(packet: pathlib.Path, name: str) -> bool:
    directory = packet / name
    if not directory.exists():
        return False
    if (directory / "FAILED.json").exists():
        if RETRY_TRANSIENT_FAILURE and transient_failure(directory):
            # The provider refused the call, so the round produced no review content. Keep the failed
            # directory as the record and run the same round again on the same packet.
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            retired = directory.with_name(f"{name}.failed-{stamp}")
            directory.rename(retired)
            log(f"round {name} failed on a transient provider error; kept as {retired.name}, retrying")
            return False
        raise RuntimeError(f"round {name} previously failed; use a fresh packet: {directory}")
    if not ((directory / "METADATA.json").is_file() and (directory / "OUTPUT.md").is_file()):
        raise RuntimeError(f"round {name} exists but is incomplete or still running: {directory}")
    return True


def recommendation(packet: pathlib.Path) -> str | None:
    output = packet / "04-claude-reaudit" / "OUTPUT.md"
    if not output.is_file():
        return None
    text = output.read_text(encoding="utf-8")
    tail = text[text.lower().rfind("final recommendation"):] if "final recommendation" in text.lower() else text
    # The earliest option named after the heading wins. List order must not decide: a needs_design
    # verdict can go on to say that a later re-audit could recommend commit_contract.
    found = None
    for word in sorted(RECOMMENDATIONS, key=len, reverse=True):
        index = tail.find(word)
        if index >= 0 and (found is None or index < found[0]):
            found = (index, word)
    return found[1] if found else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task_id")
    parser.add_argument("--existing-packet", type=pathlib.Path)
    parser.add_argument("--feedback-file", type=pathlib.Path)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--context", default="room",
                        choices=("art", "composition", "gameplay", "general", "planning", "room", "room_validation"),
                        help="ger_round.py context preset; checked before a packet is prepared")
    parser.add_argument("--addendum-file", type=pathlib.Path,
                        help="Task-category guidance; copied into the packet once and used by every round")
    parser.add_argument("--problem-file", type=pathlib.Path, help="Vincent-authored gameplay problem for the packet")
    parser.add_argument("--focus", choices=("auto", "visual", "gameplay"), default="auto")
    parser.add_argument("--retry-transient-failure", action="store_true",
                        help="Re-run a round that failed only on a provider 429/limit/capacity error; "
                             "the failed round directory is kept as <round>.failed-<UTC>")
    args = parser.parse_args()
    global RETRY_TRANSIENT_FAILURE
    RETRY_TRANSIENT_FAILURE = args.retry_transient_failure
    task_id = args.task_id
    status: dict = {"task_id": task_id, "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    packet = args.existing_packet
    try:
        confirm_held(task_id)
        if packet is None:
            packet = prepare_packet(task_id, args.feedback_file, args.problem_file, args.focus)
        packet = packet.resolve()
        identity = json.loads((packet / "SOURCE_IDENTITY.json").read_text(encoding="utf-8"))
        if identity["task_id"] != task_id:
            raise RuntimeError(f"packet is for {identity['task_id']}, not {task_id}")
        context_file = packet / "GER_CONTEXT.json"
        recorded = json.loads(context_file.read_text(encoding="utf-8")) if context_file.exists() else None
        if recorded and recorded.get("snapshot"):
            snapshot = SNAPSHOTS / recorded["snapshot"]  # resume on the snapshot the earlier rounds used
            if not (SNAPSHOTS / f"{snapshot.name}.SNAPSHOT_IDENTITY.json").is_file():
                raise RuntimeError(f"recorded snapshot is missing: {snapshot}")
        elif any((packet / name).exists() for name in ROUNDS):
            snapshot = SNAPSHOTS / f"{identity['source_head'][:12]}-blob"  # packet began before the full-Assets scope
            if not (SNAPSHOTS / f"{snapshot.name}.SNAPSHOT_IDENTITY.json").is_file():
                raise RuntimeError(f"legacy snapshot for this packet is missing: {snapshot}")
        else:
            snapshot = ensure_snapshot(identity["source_head"])
        status.update({"packet": str(packet), "snapshot": str(snapshot), "source_head": identity["source_head"]})
        # One context preset, addendum and snapshot per cycle: record them in the packet and refuse a change on resume.
        addendum_copy = packet / "GER_ADDENDUM.md"
        if args.addendum_file is not None:
            data = args.addendum_file.read_bytes()
            if addendum_copy.exists() and addendum_copy.read_bytes() != data:
                raise RuntimeError(f"packet already has a different GER_ADDENDUM.md: {addendum_copy}")
            addendum_copy.write_bytes(data)
        context = {"context": args.context, "addendum": addendum_copy.name if addendum_copy.exists() else None}
        if recorded is not None:
            if {key: recorded.get(key) for key in context} != context:
                raise RuntimeError(f"packet context {recorded} differs from this run {context}; keep one per cycle")
        else:
            context_file.write_text(json.dumps({**context, "snapshot": snapshot.name}, indent=2) + "\n", encoding="utf-8")
        status.update(context)
        marker("start", task_id)
        for name in ROUNDS:
            if round_complete(packet, name):
                log(f"{task_id}: {name} already complete")
                continue
            log(f"{task_id}: {name} starting")
            command = [PYTHON, "-B", str(TOOLS / "ger_round.py"), "--packet", str(packet), "--snapshot", str(snapshot),
                       "--round", name, "--timeout", str(args.timeout), "--context", args.context]
            if addendum_copy.exists():
                command += ["--addendum-file", str(addendum_copy)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            log(f"{task_id}: {name} exit {result.returncode} {result.stdout.strip()[-400:]} {result.stderr.strip()[-400:]}")
            if result.returncode != 0:
                raise RuntimeError(f"{name} failed: {result.stderr.strip()[-600:]}")
        status["status"] = "rounds_complete"
        status["reaudit_recommendation"] = recommendation(packet)
        log(f"{task_id}: rounds complete; re-audit recommendation {status['reaudit_recommendation']}")
        return_code = 0
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        status["status"] = "failed"
        status["error"] = str(error)
        log(f"{task_id}: FAILED {error}")
        marker("pause", task_id)
        return_code = 2
    status["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if packet is not None and pathlib.Path(packet).is_dir():
        (pathlib.Path(packet) / "NODE_STATUS.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
