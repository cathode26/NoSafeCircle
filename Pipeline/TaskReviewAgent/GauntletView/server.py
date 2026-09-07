#!/usr/bin/env python3
"""Read-only live view of an NSC gauntlet task graph.

Serves a Cytoscape.js page backed by three on-disk sources:

  Tasks/NSC-*.yaml                          structure (parent, depends_on, wave)
  .task-review-agent/autonomous-runs/.../   scheduler scope + events.jsonl
  .task-review-agent/outputs/<TASK>/<run>/  per-worker progress.jsonl

Nothing here writes to the repository or the run state. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# Canonical bounded task-ID rule; an unbounded \d+ is rejected by
# tests/task_id_width_smoke_test.py.
TASK_FILE_RE = re.compile(r"^NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})\.yaml$")
TAIL_BYTES = 96_000  # enough to hold the tail of a long worker run

# Worker terminal statuses seen in progress.jsonl -> node state.
TERMINAL_STATE = {
    "complete": "complete",
    "checks_pending": "checks_pending",
    "human_action_required": "human_action",
    "human_revalidation_required": "human_action",
    "blocked": "blocked",
    "failed": "failed",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------


def discover_roots(tasks: str | None, state: str | None) -> tuple[Path, Path]:
    """Find a checkout with Tasks/ and a directory holding .task-review-agent."""
    # Public defaults bind to this checkout; sibling private runs are never
    # selected implicitly. Operators select an external state root explicitly.
    checkout = HERE.parents[2]
    return (
        Path(tasks).resolve() if tasks else checkout / "Tasks",
        Path(state).resolve() if state else checkout,
    )


def newest_autonomous_run(state_root: Path) -> Path | None:
    root = state_root / ".task-review-agent" / "autonomous-runs"
    runs = list(root.glob("*/*/manifest.json"))
    if not runs:
        return None
    return max(runs, key=lambda p: p.stat().st_mtime).parent


# --------------------------------------------------------------------------
# cached readers
# --------------------------------------------------------------------------


class FileCache:
    """Re-parse a file only when its mtime or size changes."""

    def __init__(self) -> None:
        self._entries: dict[Path, tuple[float, int, Any]] = {}

    def get(self, path: Path, parse):
        try:
            stat = path.stat()
        except OSError:
            self._entries.pop(path, None)
            return None
        hit = self._entries.get(path)
        if hit is not None and hit[0] == stat.st_mtime and hit[1] == stat.st_size:
            return hit[2]
        try:
            value = parse(path)
        except Exception:
            value = None
        self._entries[path] = (stat.st_mtime, stat.st_size, value)
        return value


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_tail(path: Path, limit: int = TAIL_BYTES) -> list[dict]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > limit:
            handle.seek(size - limit)
            handle.readline()  # discard the partial first line
        raw = handle.read()
    out = []
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize_worker_run(path: Path) -> dict:
    """Condense one worker's progress.jsonl into current activity + outcome."""
    events = read_jsonl_tail(path)
    summary: dict[str, Any] = {
        "status": None,
        "finished": False,
        "turn": None,
        "action": None,
        "phase": None,
        "issue_state": None,
        "message": None,
        "issue_url": None,
        "last_timestamp": None,
        "worker_id": None,
        "elapsed_seconds": None,
    }
    for event in events:
        kind = event.get("event")
        fields = event.get("fields") or {}
        summary["last_timestamp"] = event.get("timestamp_utc") or summary["last_timestamp"]
        summary["worker_id"] = event.get("worker_id") or summary["worker_id"]
        if event.get("elapsed_seconds") is not None:
            summary["elapsed_seconds"] = event.get("elapsed_seconds")
        if fields.get("turn") is not None:
            summary["turn"] = fields.get("turn")
        if kind == "state_observed":
            summary["phase"] = fields.get("phase") or summary["phase"]
            summary["issue_state"] = fields.get("issue_state") or summary["issue_state"]
        if kind in ("pipeline_action_started", "supervisor_decision", "action_completed"):
            summary["action"] = fields.get("action") or summary["action"]
        if event.get("message"):
            summary["message"] = event.get("message")
        if kind == "terminal_state":
            summary["status"] = fields.get("status") or summary["status"]
            summary["issue_url"] = fields.get("issue_url") or summary["issue_url"]
        if kind == "run_finished":
            summary["status"] = fields.get("status") or summary["status"]
            summary["finished"] = True
    return summary


# --------------------------------------------------------------------------
# snapshot
# --------------------------------------------------------------------------


class Snapshot:
    def __init__(self, tasks_dir: Path, state_root: Path) -> None:
        self.tasks_dir = tasks_dir
        self.state_root = state_root
        self.outputs = state_root / ".task-review-agent" / "outputs"
        self.cache = FileCache()

    def load_contracts(self) -> dict[str, dict]:
        contracts: dict[str, dict] = {}
        for path in sorted(self.tasks_dir.iterdir()):
            if not TASK_FILE_RE.match(path.name):
                continue
            data = self.cache.get(path, read_json)
            if isinstance(data, dict) and data.get("id"):
                contracts[data["id"]] = data
        return contracts

    def latest_worker_run(self, task_id: str) -> dict | None:
        task_dir = self.outputs / task_id
        if not task_dir.is_dir():
            return None
        best: tuple[float, Path] | None = None
        try:
            entries = list(task_dir.iterdir())
        except OSError:
            return None
        for run_dir in entries:
            progress = run_dir / "progress.jsonl"
            try:
                mtime = progress.stat().st_mtime
            except OSError:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, progress)
        if best is None:
            return None
        summary = self.cache.get(best[1], summarize_worker_run)
        if summary is None:
            return None
        summary = dict(summary)
        summary["run_id"] = best[1].parent.name
        summary["updated_at"] = datetime.fromtimestamp(best[0], timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        summary["age_seconds"] = round(time.time() - best[0], 1)
        return summary

    def build(self) -> dict:
        contracts = self.load_contracts()

        run_dir = newest_autonomous_run(self.state_root)
        manifest = self.cache.get(run_dir / "manifest.json", read_json) if run_dir else None
        progress = self.cache.get(run_dir / "progress.json", read_json) if run_dir else None
        receipt = self.cache.get(run_dir / "graph-complete.json", read_json) if run_dir else None
        events = self.cache.get(run_dir / "events.jsonl", read_jsonl_tail) if run_dir else None
        events = events or []

        manifest = manifest if isinstance(manifest, dict) else {}
        scope = set(manifest.get("target_task_ids") or [])
        excluded = set(manifest.get("excluded_task_ids") or [])

        # Scheduler-reported activity, newest wins.
        launched: dict[str, dict] = {}
        for event in events:
            task_id = event.get("task_id")
            if not task_id:
                continue
            if event.get("event") == "worker_launched":
                launched[task_id] = {"launched_at": event.get("timestamp_utc")}
            elif event.get("event") in ("worker_finished", "worker_returned_to_pool"):
                launched.pop(task_id, None)

        tasks = []
        for task_id, contract in contracts.items():
            summary = self.latest_worker_run(task_id)

            state = "pending"
            if contract.get("contract_disposition") == "cancelled":
                state = "cancelled"
            elif task_id in excluded:
                state = "excluded"
            elif summary:
                if not summary.get("finished"):
                    state = "active"
                else:
                    state = TERMINAL_STATE.get(summary.get("status") or "", "blocked")
            if task_id in launched and state not in ("cancelled", "excluded"):
                state = "active"

            provenance = contract.get("provenance") or {}
            tasks.append(
                {
                    "id": task_id,
                    "title": contract.get("title") or task_id,
                    "parent": contract.get("parent"),
                    "depends_on": list(contract.get("depends_on") or []),
                    "kind": contract.get("kind"),
                    "disposition": contract.get("contract_disposition"),
                    "decomposition_state": contract.get("decomposition_state"),
                    "execution_scope": contract.get("execution_scope"),
                    "notes": contract.get("notes"),
                    "reason": contract.get("decomposition_reason"),
                    "resources": list(contract.get("exclusive_resources") or []),
                    "acceptance": [
                        c.get("requirement")
                        for c in (contract.get("acceptance_criteria") or [])
                        if isinstance(c, dict)
                    ],
                    "wave": provenance.get("wave"),
                    "column": provenance.get("column"),
                    "in_scope": task_id in scope,
                    "state": state,
                    "worker": summary,
                }
            )

        # Unmet dependencies keep a task pending; otherwise it is ready.
        done = {t["id"] for t in tasks if t["state"] in ("complete", "cancelled")}
        for task in tasks:
            if task["state"] == "pending" and all(d in done for d in task["depends_on"]):
                task["state"] = "ready"

        blocked_reasons = [
            e.get("reason") or e.get("message")
            for e in events[-40:]
            if e.get("event") == "scheduler_blocked"
        ]

        return {
            "generated_at": utc_now(),
            "tasks_dir": str(self.tasks_dir),
            "state_root": str(self.state_root),
            "run": {
                "dir": str(run_dir) if run_dir else None,
                "run_id": manifest.get("run_id"),
                "repository": manifest.get("github_repository"),
                "max_capacity": manifest.get("max_capacity"),
                "targets": sorted(scope),
                "excluded": sorted(excluded),
                "progress": progress if isinstance(progress, dict) else None,
                "complete": bool(receipt),
            },
            "scheduler": {
                "active": sorted(launched),
                "blocked_reasons": [r for r in blocked_reasons if r][-5:],
            },
            "events": events[-60:],
            "tasks": tasks,
        }

    def fingerprint(self) -> str:
        """Cheap change detector across every file the snapshot reads."""
        parts: list[str] = []
        try:
            for path in sorted(self.tasks_dir.iterdir()):
                if TASK_FILE_RE.match(path.name):
                    stat = path.stat()
                    parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            pass
        run_dir = newest_autonomous_run(self.state_root)
        if run_dir:
            for name in ("manifest.json", "progress.json", "events.jsonl", "graph-complete.json"):
                try:
                    stat = (run_dir / name).stat()
                except OSError:
                    continue
                parts.append(f"{name}:{stat.st_mtime_ns}:{stat.st_size}")
        try:
            for task_dir in self.outputs.iterdir():
                try:
                    parts.append(f"{task_dir.name}:{task_dir.stat().st_mtime_ns}")
                    runs = list(task_dir.iterdir())
                except OSError:
                    continue
                for run in runs:
                    try:
                        stat = (run / "progress.jsonl").stat()
                    except OSError:
                        continue
                    parts.append(f"{task_dir.name}/{run.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            pass
        return str(hash("|".join(parts)))


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    snapshot: Snapshot

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/vendor/"):
            target = (HERE / path.lstrip("/")).resolve()
            if HERE in target.parents and target.is_file():
                self._send(200, target.read_bytes(), "application/javascript; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")
            return
        if path == "/api/state":
            body = json.dumps(self.snapshot.build()).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/api/stream":
            self._stream()
            return
        self._send(404, b"not found", "text/plain")

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = None
        try:
            while True:
                current = self.snapshot.fingerprint()
                if current != last:
                    last = current
                    payload = json.dumps(self.snapshot.build())
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                else:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="Live NSC gauntlet task-graph view.")
    parser.add_argument("--tasks", help="path to a checkout's Tasks/ directory")
    parser.add_argument("--state", help="directory containing .task-review-agent")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    tasks_dir, state_root = discover_roots(args.tasks, args.state)
    if not tasks_dir.is_dir():
        raise SystemExit(f"Tasks directory not found: {tasks_dir}")

    Handler.snapshot = Snapshot(tasks_dir, state_root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True

    run_dir = newest_autonomous_run(state_root)
    print(f"  contracts : {tasks_dir}")
    print(f"  run state : {state_root}")
    print(f"  active run: {run_dir.name if run_dir else '(none found)'}")
    print(f"\n  http://127.0.0.1:{args.port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
