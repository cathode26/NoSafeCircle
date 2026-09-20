"""nsc_viewer: control the No Safe Circle graph viewer and its display overlays.

Agents use this instead of hand-editing JSON or killing processes by guesswork.

Viewer process (Windows):
  status   [--port 8828]              is it running, is it the live Source/checkout root, is its data healthy
  list                                every viewer-like process on ports 8700-8999, flags stale/non-live ones
  start    [--port 8828]              start the viewer on the live pair (hidden, logs in .assistant-control\\viewer-logs)
  stop     [--port 8828] [--not-live-ok]
  restart  [--port 8828]
  task     NSC-###                    the viewer's row for one task (state, overlays, worker, candidate)

Display overlays (never change task contracts, dispatch, or records; each write is locked, validated and atomic):
  overlays                            show and validate all three overlay files
  hold     NSC-###                    grey "Outside Current Run"   (held-task-ids.json task_ids)
  unhold   NSC-###                    drop the hold WITHOUT marking GER released
  ger-start  NSC-###                  brown "GER in progress"       (task must be held)
  ger-pause  NSC-###                  back to grey, still held
  ger-finish NSC-### [--ready-child NSC-###]   release: purple "Task Unstarted"
  working  NSC-### --description "..." [--minutes 30]   blue "Task Working" for non-crew work (PixelLab, hand Unity runs)
  done     NSC-###                    remove the working marker
  complete NSC-### --note "..."       green, Vincent-confirmed complete (display only; does NOT unlock dependencies)
  uncomplete NSC-###

Every overlay write refuses task IDs that are not committed at Source HEAD, because an unknown ID puts the whole
viewer into inspection_error. Expired working markers are pruned on each working/done write.

Run from anywhere:  python -B C:\\nscrev\\viewer-tools\\nsc_viewer.py status
Options --source / --checkout-root default to the live pair; override them only for tests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True

LIVE_SOURCE = Path(r"C:\NSC\NSC\NoSafeCircle")
LIVE_ROOT = Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts")
DEFAULT_PORT = 8828
HELD_FILE = "held-task-ids.json"
EXTERNAL_FILE = "external-work-ids.json"
HUMAN_FILE = "human-complete-ids.json"
OVERLAY_LOCK = "ger-viewer-overlay.lock"
HELD_SCHEMA = "assistant-viewer-held-tasks/v1"
EXTERNAL_SCHEMA = "assistant-viewer-external-work/v1"
HUMAN_SCHEMA = "assistant-viewer-human-complete/v1"
TASK_ID = re.compile(r"^NSC-\d{3,5}$")

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run that never opens a console window on Windows."""
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.run(command, **kwargs)


class Refused(RuntimeError):
    """A safety check refused the action."""


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, default=str))


# ---------------------------------------------------------------------------
# repository helpers (imported from the Source so semantics match the viewer)
# ---------------------------------------------------------------------------

def repo(source: Path):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from Pipeline.AssistantControl.checkouts import write_record
    from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
    from Pipeline.TaskDesignGER.ger_viewer_marker import change_marker
    return write_record, _exclusive_file_lock, change_marker


def committed_task_ids(source: Path) -> set[str]:
    result = run(["git", "-C", str(source), "ls-tree", "--name-only", "HEAD", "Tasks/"],
                            capture_output=True, text=True, check=True)
    return {Path(line).stem for line in result.stdout.splitlines() if line.endswith(".yaml")}


def source_head(source: Path) -> str:
    return run(["git", "-C", str(source), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def require_task(task_id: str, source: Path) -> str:
    task_id = task_id.strip().upper()
    if not TASK_ID.fullmatch(task_id):
        raise Refused(f"{task_id!r} is not an NSC-### task ID")
    if task_id not in committed_task_ids(source):
        raise Refused(f"{task_id} is not committed at Source HEAD; the viewer would reject the overlay")
    return task_id


def records(root: Path) -> Path:
    path = root.resolve() / ".assistant-control"
    if not path.is_dir():
        raise Refused(f"No .assistant-control directory under {root}")
    return path


# ---------------------------------------------------------------------------
# process helpers (Windows)
# ---------------------------------------------------------------------------

def listeners(low: int, high: int) -> dict[int, set[int]]:
    output = run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    found: dict[int, set[int]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
            try:
                port = int(parts[1].rsplit(":", 1)[1])
                pid = int(parts[4])
            except ValueError:
                continue
            if low <= port <= high:
                found.setdefault(port, set()).add(pid)
    return found


def command_lines(pids: set[int]) -> dict[int, str]:
    if not pids:
        return {}
    ids = ",".join(str(pid) for pid in sorted(pids))
    script = (f"Get-CimInstance Win32_Process | Where-Object {{ @({ids}) -contains $_.ProcessId }} | "
              "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    output = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=60).stdout
    lines: dict[int, str] = {}
    for line in output.splitlines():
        if "\t" in line:
            pid, command = line.split("\t", 1)
            if pid.strip().isdigit():
                lines[int(pid)] = command.strip()
    return lines


def _flag(command: str, name: str) -> str | None:
    match = re.search(rf"{re.escape(name)}\s+(\"[^\"]+\"|'[^']+'|\S+)", command)
    return match.group(1).strip("\"'") if match else None


def classify(command: str) -> dict:
    kind = "other"
    if "Pipeline.AssistantControl" in command and re.search(r"\bviewer\b", command):
        kind = "assistantcontrol-viewer"
    elif "GauntletView" in command or "gauntlet-view" in command or "gauntlet_view" in command:
        kind = "legacy-gauntlet-viewer"
    source = _flag(command, "--source")
    root = _flag(command, "--checkout-root")
    return {"kind": kind, "source": source, "checkout_root": root}


def same_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return False


def describe_port(port: int, source: Path, root: Path) -> list[dict]:
    pids = listeners(port, port).get(port, set())
    commands = command_lines(pids)
    described = []
    for pid in sorted(pids):
        command = commands.get(pid, "")
        info = classify(command)
        info.update(pid=pid, port=port, command=command,
                    live_pair=same_path(info["source"], source) and same_path(info["checkout_root"], root))
        described.append(info)
    return described


def http_json(port: int, path: str, timeout: float):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def receipt_path(root: Path, port: int) -> Path:
    return records(root) / "viewer-logs" / f"nsc_viewer-{port}.json"


# ---------------------------------------------------------------------------
# viewer process commands
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    source, root, port = args.source, args.checkout_root, args.port
    processes = describe_port(port, source, root)
    report: dict = {"port": port, "url": f"http://127.0.0.1:{port}/", "listening": bool(processes),
                    "processes": processes, "expected_source": str(source), "expected_checkout_root": str(root)}
    receipt = receipt_path(root, port)
    report["receipt"] = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else None
    if processes:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=15) as response:
                report["page"] = response.status
        except (OSError, urllib.error.URLError) as exc:
            report["page"] = f"no answer: {exc}"
        try:
            state = http_json(port, "/api/state", args.timeout)
            counts: dict[str, int] = {}
            for row in state.get("tasks", []):
                counts[row.get("state")] = counts.get(row.get("state"), 0) + 1
            head = source_head(source)
            run = state.get("run") or {}
            seen = run.get("source_commit")
            report.update(
                viewer_identity=state.get("viewer_identity"),
                inspection_error=state.get("inspection_error"),
                source_head_seen=seen,
                source_head_now=head,
                run_mode=run.get("mode"),
                task_count=len(state.get("tasks", [])),
                state_counts=dict(sorted(counts.items(), key=lambda item: str(item[0]))),
                headline=(state.get("pipeline_activity") or {}).get("headline"),
            )
            problems = []
            identity = state.get("viewer_identity") or {}
            if identity and not same_path(identity.get("checkout_root"), LIVE_ROOT):
                problems.append("viewer is NOT on the live checkout root: it will show zero live workers")
            if state.get("inspection_error"):
                problems.append("inspection_error: a record or overlay is malformed (run `overlays`)")
            if seen and seen != head:
                problems.append("viewer snapshot is behind Source HEAD (wait 30 s for the cache, or restart)")
            report["problems"] = problems
        except (OSError, urllib.error.URLError, ValueError) as exc:
            report["api_state"] = (f"no answer within {args.timeout}s ({exc}); a fresh viewer can take 30-90 s "
                                   "to build its first snapshot")
    emit(report)
    return 0


def cmd_list(args) -> int:
    ports = listeners(8700, 8999)
    pids = set().union(*ports.values()) if ports else set()
    commands = command_lines(pids)
    rows = []
    for port in sorted(ports):
        for pid in sorted(ports[port]):
            command = commands.get(pid, "")
            info = classify(command)
            if info["kind"] == "other" and "python" not in command.lower():
                continue
            info.update(port=port, pid=pid,
                        live_pair=same_path(info["source"], args.source) and same_path(info["checkout_root"],
                                                                                      args.checkout_root))
            info["note"] = ("live viewer" if info["live_pair"] and port == DEFAULT_PORT else
                            "live pair on a non-standard port" if info["live_pair"] else
                            "NOT the live pair: stale or research viewer (ask Vincent before stopping)")
            rows.append(info)
    emit({"viewers": rows})
    return 0


def cmd_start(args) -> int:
    source, root, port = args.source, args.checkout_root, args.port
    existing = describe_port(port, source, root)
    if existing:
        if len(existing) == 1 and existing[0]["kind"] == "assistantcontrol-viewer" and existing[0]["live_pair"]:
            emit({"status": "already_running", "url": f"http://127.0.0.1:{port}/", "process": existing[0]})
            return 0
        raise Refused(f"port {port} is already used by another process: {existing}")
    logs = records(root) / "viewer-logs"
    logs.mkdir(exist_ok=True)
    stdout_path = logs / f"viewer-{port}.out.log"
    stderr_path = logs / f"viewer-{port}.err.log"
    command = [sys.executable, "-B", "-m", "Pipeline.AssistantControl", "--source", str(source),
               "--checkout-root", str(root), "viewer", "--port", str(port)]
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    with stdout_path.open("ab") as out, stderr_path.open("ab") as err:
        # CREATE_NO_WINDOW, never DETACHED_PROCESS: a detached process has NO console at all, so any
        # console child it spawns (git, ...) that doesn't redirect its own stdio gets a brand-new,
        # VISIBLE console. A hidden console lets console children inherit it and stay hidden too.
        flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        try:
            process = subprocess.Popen(command, cwd=str(source), env=environment, stdout=out, stderr=err,
                                       stdin=subprocess.DEVNULL, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB,
                                       startupinfo=startupinfo, close_fds=True)
        except OSError:
            process = subprocess.Popen(command, cwd=str(source), env=environment, stdout=out, stderr=err,
                                       stdin=subprocess.DEVNULL, creationflags=flags,
                                       startupinfo=startupinfo, close_fds=True)
    deadline = time.monotonic() + args.wait
    listening: list[dict] = []
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise Refused(f"viewer exited with code {process.returncode}; stderr tail:\n{tail}")
        if listeners(port, port).get(port):
            listening = describe_port(port, source, root)
            break
        time.sleep(2)
    if not listening:
        raise Refused(f"viewer did not start listening on {port} within {args.wait}s; see {stderr_path}")
    receipt = {"port": port, "pid": listening[0]["pid"], "source": str(source), "checkout_root": str(root),
               "command": command, "stdout_log": str(stdout_path), "stderr_log": str(stderr_path),
               "started_at_utc": datetime.now(timezone.utc).isoformat()}
    receipt_path(root, port).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    emit({"status": "started", "url": f"http://127.0.0.1:{port}/", "pid": receipt["pid"],
          "note": "first /api/state can take 30-90 s; tell Vincent to hard-refresh (Ctrl+F5)"})
    return 0


def cmd_stop(args) -> int:
    source, root, port = args.source, args.checkout_root, args.port
    processes = describe_port(port, source, root)
    receipt = receipt_path(root, port)
    if not processes:
        if receipt.is_file():
            receipt.unlink()
        emit({"status": "not_running", "port": port})
        return 0
    for process in processes:
        if process["kind"] == "other":
            raise Refused(f"port {port} belongs to a non-viewer process; refusing to stop it: {process}")
        if not process["live_pair"] and not args.not_live_ok:
            raise Refused(f"viewer on {port} is not the live pair ({process['source']} / {process['checkout_root']}); "
                          "get Vincent's OK, then rerun with --not-live-ok")
    for process in processes:
        run(["taskkill", "/PID", str(process["pid"]), "/T", "/F"], capture_output=True, text=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and listeners(port, port).get(port):
        time.sleep(1)
    if listeners(port, port).get(port):
        raise Refused(f"port {port} is still listening after stop")
    if receipt.is_file():
        receipt.unlink()
    emit({"status": "stopped", "port": port, "stopped": [p["pid"] for p in processes]})
    return 0


def cmd_restart(args) -> int:
    cmd_stop(args)
    return cmd_start(args)


def cmd_task(args) -> int:
    task_id = args.task_id.strip().upper()
    state = http_json(args.port, "/api/state", args.timeout)
    for row in state.get("tasks", []):
        if row.get("id") == task_id:
            keep = ("id", "title", "state", "in_scope", "kind", "execution_scope", "decomposition_state",
                    "decomposition_children", "depends_on", "held_overlay", "ger_overlay",
                    "external_work_overlay", "human_completion_overlay", "progress", "reason", "notes",
                    "checkout_path", "checkout_exists", "checkout_commit")
            summary = {key: row.get(key) for key in keep if key in row}
            for key in ("worker", "taskgraph"):
                value = row.get(key)
                if isinstance(value, dict):
                    summary[key] = {k: v for k, v in value.items() if not isinstance(v, (dict, list))}
            emit(summary)
            return 0
    raise Refused(f"{task_id} is not in the viewer snapshot")


# ---------------------------------------------------------------------------
# overlay commands
# ---------------------------------------------------------------------------

def _load(path: Path, schema: str, default: dict) -> dict:
    if not path.is_file():
        return dict(default)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        raise Refused(f"{path.name} has an unsupported schema")
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expiry(entry: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(entry.get("expires_at")))
    except ValueError:
        return None


def check_overlays(source: Path, root: Path) -> dict:
    known = committed_task_ids(source)
    base = records(root)
    report: dict = {}
    held = _load(base / HELD_FILE, HELD_SCHEMA, {"schema_version": HELD_SCHEMA, "task_ids": [],
                                                  "active_ger_task_ids": [], "released_ger_task_ids": []})
    sets = {name: held.get(name, []) for name in ("task_ids", "active_ger_task_ids", "released_ger_task_ids")}
    problems = []
    for name, ids in sets.items():
        if len(ids) != len(set(ids)):
            problems.append(f"{HELD_FILE}: duplicate IDs in {name}")
    if not set(sets["active_ger_task_ids"]) <= set(sets["task_ids"]):
        problems.append(f"{HELD_FILE}: active GER tasks must also be held")
    if set(sets["task_ids"]) & set(sets["released_ger_task_ids"]):
        problems.append(f"{HELD_FILE}: a task is both held and released")
    unknown = {i for ids in sets.values() for i in ids} - known
    if unknown:
        problems.append(f"{HELD_FILE}: unknown task IDs {sorted(unknown)}")
    report["held"] = sets
    external = _load(base / EXTERNAL_FILE, EXTERNAL_SCHEMA, {"schema_version": EXTERNAL_SCHEMA, "tasks": []})
    live, expired = [], []
    for entry in external.get("tasks", []):
        expiry = _expiry(entry)
        if entry.get("task_id") not in known:
            problems.append(f"{EXTERNAL_FILE}: unknown task ID {entry.get('task_id')}")
        if expiry is None or not str(entry.get("description", "")).strip():
            problems.append(f"{EXTERNAL_FILE}: entry needs expires_at and description: {entry}")
        (live if expiry and expiry > _now() else expired).append(entry)
    report["working_live"] = live
    report["working_expired"] = expired
    human = _load(base / HUMAN_FILE, HUMAN_SCHEMA, {"schema_version": HUMAN_SCHEMA, "tasks": []})
    for entry in human.get("tasks", []):
        if entry.get("task_id") not in known:
            problems.append(f"{HUMAN_FILE}: unknown task ID {entry.get('task_id')}")
        if not str(entry.get("note", "")).strip():
            problems.append(f"{HUMAN_FILE}: entry needs a note: {entry}")
    report["human_complete"] = human.get("tasks", [])
    report["problems"] = problems
    return report


def cmd_overlays(args) -> int:
    report = check_overlays(args.source, args.checkout_root)
    emit(report)
    return 1 if report["problems"] else 0


def _write_locked(args, filename: str, schema: str, default: dict, mutate) -> dict:
    write_record, lock, _ = repo(args.source)
    base = records(args.checkout_root)
    with lock(base / OVERLAY_LOCK, timeout_seconds=10):
        value = _load(base / filename, schema, default)
        mutate(value)
        write_record(base / filename, value)
    return value


def cmd_hold(args) -> int:
    task_id = require_task(args.task_id, args.source)

    def mutate(value: dict) -> None:
        held = set(value.get("task_ids", []))
        active = set(value.get("active_ger_task_ids", []))
        released = set(value.get("released_ger_task_ids", []))
        if args.command == "hold":
            held.add(task_id)
            released.discard(task_id)
        else:
            if task_id not in held:
                raise Refused(f"{task_id} is not held")
            held.discard(task_id)
            active.discard(task_id)
        if not active <= held or held & released:
            raise Refused("refusing to write overlapping GER marker sets")
        value.update(task_ids=sorted(held), active_ger_task_ids=sorted(active),
                     released_ger_task_ids=sorted(released))

    default = {"schema_version": HELD_SCHEMA, "task_ids": [], "active_ger_task_ids": [], "released_ger_task_ids": []}
    emit(_write_locked(args, HELD_FILE, HELD_SCHEMA, default, mutate))
    return 0


def cmd_ger(args) -> int:
    task_id = require_task(args.task_id, args.source)
    children = tuple(require_task(child, args.source) for child in (args.ready_child or []))
    _, _, change_marker = repo(args.source)
    action = {"ger-start": "start", "ger-pause": "pause", "ger-finish": "finish"}[args.command]
    emit(change_marker(args.checkout_root, action, task_id, children))
    return 0


def cmd_working(args) -> int:
    task_id = require_task(args.task_id, args.source)
    now = _now()

    def mutate(value: dict) -> None:
        tasks = [entry for entry in value.get("tasks", [])
                 if entry.get("task_id") != task_id and (_expiry(entry) or now) > now]
        if args.command == "working":
            if not args.description.strip():
                raise Refused("--description is required")
            expires = (now + timedelta(minutes=args.minutes)).isoformat().replace("+00:00", "Z")
            tasks.append({"task_id": task_id, "description": args.description.strip(), "expires_at": expires})
        elif not any(entry.get("task_id") == task_id for entry in value.get("tasks", [])):
            raise Refused(f"{task_id} has no working marker")
        value["tasks"] = sorted(tasks, key=lambda entry: entry["task_id"])

    emit(_write_locked(args, EXTERNAL_FILE, EXTERNAL_SCHEMA, {"schema_version": EXTERNAL_SCHEMA, "tasks": []}, mutate))
    return 0


def cmd_complete(args) -> int:
    task_id = require_task(args.task_id, args.source)

    def mutate(value: dict) -> None:
        tasks = [entry for entry in value.get("tasks", []) if entry.get("task_id") != task_id]
        if args.command == "complete":
            if not args.note.strip():
                raise Refused("--note is required (quote Vincent)")
            tasks.append({"task_id": task_id, "note": args.note.strip()})
        elif len(tasks) == len(value.get("tasks", [])):
            raise Refused(f"{task_id} has no human-complete marker")
        value["tasks"] = sorted(tasks, key=lambda entry: entry["task_id"])

    emit(_write_locked(args, HUMAN_FILE, HUMAN_SCHEMA, {"schema_version": HUMAN_SCHEMA, "tasks": []}, mutate))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=LIVE_SOURCE)
    parser.add_argument("--checkout-root", type=Path, default=LIVE_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    def with_port(name: str, help_text: str):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--port", type=int, default=DEFAULT_PORT)
        return command

    status = with_port("status", "is the viewer running and healthy")
    status.add_argument("--timeout", type=float, default=90.0)
    sub.add_parser("list", help="all viewer processes on 8700-8999")
    start = with_port("start", "start the live viewer")
    start.add_argument("--wait", type=float, default=60.0)
    stop = with_port("stop", "stop a viewer after identity checks")
    stop.add_argument("--not-live-ok", action="store_true")
    restart = with_port("restart", "stop then start the live viewer")
    restart.add_argument("--wait", type=float, default=60.0)
    restart.add_argument("--not-live-ok", action="store_true")
    task = with_port("task", "show the viewer row for one task")
    task.add_argument("task_id")
    task.add_argument("--timeout", type=float, default=90.0)
    sub.add_parser("overlays", help="show and validate overlay files")
    for name in ("hold", "unhold"):
        sub.add_parser(name).add_argument("task_id")
    for name in ("ger-start", "ger-pause", "ger-finish"):
        ger = sub.add_parser(name)
        ger.add_argument("task_id")
        ger.add_argument("--ready-child", action="append")
    working = sub.add_parser("working")
    working.add_argument("task_id")
    working.add_argument("--description", required=True)
    working.add_argument("--minutes", type=int, default=30)
    sub.add_parser("done").add_argument("task_id")
    complete = sub.add_parser("complete")
    complete.add_argument("task_id")
    complete.add_argument("--note", required=True)
    sub.add_parser("uncomplete").add_argument("task_id")

    args = parser.parse_args()
    handlers = {
        "status": cmd_status, "list": cmd_list, "start": cmd_start, "stop": cmd_stop, "restart": cmd_restart,
        "task": cmd_task, "overlays": cmd_overlays, "hold": cmd_hold, "unhold": cmd_hold,
        "ger-start": cmd_ger, "ger-pause": cmd_ger, "ger-finish": cmd_ger,
        "working": cmd_working, "done": cmd_working, "complete": cmd_complete, "uncomplete": cmd_complete,
    }
    try:
        return handlers[args.command](args)
    except (Refused, ValueError, FileNotFoundError, TimeoutError) as exc:
        emit({"status": "refused", "error": str(exc)})
        return 2
    except (urllib.error.URLError, OSError) as exc:
        emit({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
