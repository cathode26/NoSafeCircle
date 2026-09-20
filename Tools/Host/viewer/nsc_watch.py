"""nsc_watch: one read-only health snapshot of the No Safe Circle pipeline, with alerts.

For the Watcher role (and any agent starting a session). Changes nothing. Starts no
visible windows (all subprocesses use CREATE_NO_WINDOW via nsc_viewer.run).

  python -B C:\\nscrev\\viewer-tools\\nsc_watch.py            # JSON snapshot + alerts
  python -B C:\\nscrev\\viewer-tools\\nsc_watch.py --api      # also ask the viewer for its state (can take 30-90 s)

Exit code: 0 = no alerts, 1 = alerts present, 2 = the check itself failed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nsc_viewer as nv  # noqa: E402

CODEX_HOME = Path.home() / ".codex"
QUOTA_ALERT_PERCENT = 80.0
WORKER_ALERT_HOURS = 2.0
DECOMPOSITION_ALERT_MINUTES = 70.0


def _age_hours(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - value).total_seconds() / 3600, 2)


def source_state(source: Path) -> dict:
    def git(*args: str) -> str:
        return nv.run(["git", "-C", str(source), *args], capture_output=True, text=True).stdout.strip()
    porcelain = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    return {
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "--short=9", "HEAD"),
        "dirty_files": len(porcelain),
        "ahead_of_origin": git("rev-list", "--count", "origin/main..main"),
    }


def docker_state() -> dict:
    version = nv.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True)
    if version.returncode != 0:
        return {"engine": "down"}
    listing = nv.run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"], capture_output=True, text=True).stdout
    running = [dict(zip(("name", "status"), line.split("\t", 1))) for line in listing.splitlines() if "\t" in line]
    return {"engine": version.stdout.strip(), "running": running}


def records_state(root: Path) -> dict:
    base = root / ".assistant-control"
    workers, waiting, approved, decompositions = [], [], [], []
    for path in sorted(base.glob("NSC-*.json")):
        name = path.name
        if "materialization" in name or name.count(".") > 1 and not name.endswith(".decomposition.json"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        task = record.get("task_id") or name.split(".")[0]
        if name.endswith(".decomposition.json"):
            if record.get("status") == "running":
                decompositions.append({"task": task, "run_id": record.get("run_id"),
                                       "age_hours": _age_hours(record.get("started_at_utc"))})
            continue
        worker = record.get("worker") or {}
        if worker.get("status") in {"running", "starting", "ready_pending"} or (
                (record.get("launch") or {}).get("status") == "ready_pending" and not worker.get("finished_at")):
            workers.append({"task": task, "run_id": worker.get("run_id") or (record.get("launch") or {}).get("run_id"),
                            "status": worker.get("status"), "age_hours": _age_hours(worker.get("started_at"))})
        status = record.get("status")
        if status == "awaiting_human":
            waiting.append({"task": task, "candidate": (record.get("candidate") or {}).get("commit"),
                            "checkout": record.get("checkout")})
        elif status == "approved":
            approved.append({"task": task, "candidate": (record.get("candidate") or {}).get("commit")})
    controller = {}
    for label, filename in (("controller", "graph-controller.json"), ("owner", "graph-controller-owner.json")):
        try:
            value = json.loads((base / filename).read_text(encoding="utf-8-sig"))
            controller[label] = {"status": value.get("status"), "updated_at": value.get("updated_at")}
        except (OSError, ValueError):
            controller[label] = None
    journal = base / "graph-lead-journal.md"
    last_heading = None
    if journal.is_file():
        headings = [line for line in journal.read_text(encoding="utf-8", errors="replace").splitlines()
                    if line.startswith("## ")]
        last_heading = headings[-1] if headings else None
    return {
        "workers_running": workers, "decompositions_running": decompositions,
        "candidates_waiting_for_vincent": waiting, "approved_not_integrated": approved,
        "retired_controller_records": controller,
        "journal": {"modified_hours_ago": round((time.time() - journal.stat().st_mtime) / 3600, 2)
                    if journal.is_file() else None, "last_heading": last_heading},
    }


def codex_quota() -> dict:
    sessions = CODEX_HOME / "sessions"
    candidates = sorted(sessions.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    for path in candidates:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                entry = json.loads(line)
                payload = entry.get("payload") or {}
            except ValueError:
                continue
            limits = payload.get("rate_limits") or (payload.get("info") or {}).get("rate_limits")
            if not isinstance(limits, dict):
                continue
            primary = limits.get("primary") or {}
            resets = primary.get("resets_at")
            return {
                "used_percent": primary.get("used_percent"),
                "window_minutes": primary.get("window_minutes"),
                "resets_at_utc": datetime.fromtimestamp(resets, timezone.utc).isoformat() if resets else None,
                "observed_in": path.name,
                "observed_at_utc": entry.get("timestamp"),
                "observed_hours_ago": _age_hours(entry.get("timestamp")),
                "note": "host Codex account as last seen by a host session; Docker volume logins may use another account",
            }
    return {"used_percent": None, "note": "no recent host Codex session with rate-limit data"}


def codex_automations() -> list[dict]:
    rows = []
    for path in sorted((CODEX_HOME / "automations").glob("*/automation.toml")):
        text = path.read_text(encoding="utf-8", errors="replace")

        def field(name: str) -> str | None:
            match = re.search(rf'^{name}\s*=\s*"([^"]*)"', text, flags=re.M)
            return match.group(1) if match else None
        rrule = field("rrule") or ""
        until = re.search(r"UNTIL=(\d{8}T\d{6}Z)", rrule)
        expired = False
        if until:
            expired = datetime.strptime(until.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
        rows.append({"id": path.parent.name, "name": field("name"), "status": field("status"),
                     "rrule": rrule, "until_passed": expired})
    return rows


def unity_processes() -> int:
    output = nv.run(["tasklist", "/FI", "IMAGENAME eq Unity.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True).stdout
    return sum(1 for line in output.splitlines() if line.lower().startswith('"unity.exe"'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=nv.LIVE_SOURCE)
    parser.add_argument("--checkout-root", type=Path, default=nv.LIVE_ROOT)
    parser.add_argument("--port", type=int, default=nv.DEFAULT_PORT)
    parser.add_argument("--api", action="store_true", help="also read the viewer /api/state (slow)")
    args = parser.parse_args()
    alerts: list[str] = []
    info: list[str] = []
    snapshot: dict = {"checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    snapshot["source"] = source_state(args.source)
    snapshot["docker"] = docker_state()
    records = records_state(args.checkout_root)
    snapshot["records"] = records
    processes = nv.describe_port(args.port, args.source, args.checkout_root)
    snapshot["viewer"] = {"port": args.port, "listening": bool(processes),
                          "live_pair": any(p.get("live_pair") for p in processes)}
    try:
        overlay = nv.check_overlays(args.source, args.checkout_root)
        snapshot["overlays"] = {"problems": overlay["problems"], "held": overlay["held"]["task_ids"],
                                "ger_active": overlay["held"]["active_ger_task_ids"],
                                "working_live": [e.get("task_id") for e in overlay["working_live"]],
                                "working_expired": [e.get("task_id") for e in overlay["working_expired"]]}
    except Exception as exc:  # noqa: BLE001 - report, don't crash the watcher
        snapshot["overlays"] = {"problems": [f"overlay check failed: {exc}"]}
    if args.api and processes:
        try:
            state = nv.http_json(args.port, "/api/state", 120)
            snapshot["viewer"]["inspection_error"] = state.get("inspection_error")
            snapshot["viewer"]["checkout_root"] = (state.get("viewer_identity") or {}).get("checkout_root")
        except Exception as exc:  # noqa: BLE001
            snapshot["viewer"]["api_error"] = str(exc)
    snapshot["codex_quota"] = codex_quota()
    snapshot["codex_automations"] = codex_automations()
    snapshot["unity_processes"] = unity_processes()

    # alerts: things someone must act on
    used = snapshot["codex_quota"].get("used_percent")
    if isinstance(used, (int, float)) and used >= QUOTA_ALERT_PERCENT:
        alerts.append(f"Codex quota {used}% used (resets {snapshot['codex_quota'].get('resets_at_utc')})")
    for automation in snapshot["codex_automations"]:
        if automation.get("status") == "ACTIVE" and not automation.get("until_passed"):
            alerts.append(f"Codex automation ACTIVE: {automation['id']} ({automation['rrule']})")
    for worker in records["workers_running"]:
        if (worker.get("age_hours") or 0) >= WORKER_ALERT_HOURS:
            alerts.append(f"worker running {worker['age_hours']} h: {worker['task']} {worker['run_id']}")
    for job in records["decompositions_running"]:
        if (job.get("age_hours") or 0) * 60 >= DECOMPOSITION_ALERT_MINUTES:
            alerts.append(f"decomposition running {job['age_hours']} h (container limit 1 h): {job['task']}")
    if snapshot["docker"].get("engine") == "down" and (records["workers_running"] or records["decompositions_running"]):
        alerts.append("Docker engine is down while workers/decompositions are recorded as running")
    if snapshot["overlays"].get("problems"):
        alerts.append("viewer overlay problems: " + "; ".join(snapshot["overlays"]["problems"]))
    if processes and not snapshot["viewer"]["live_pair"]:
        alerts.append(f"viewer on {args.port} is not the live Source/checkout root (shows zero live workers)")
    if snapshot["viewer"].get("inspection_error"):
        alerts.append(f"viewer inspection_error: {snapshot['viewer']['inspection_error']}")

    # info: worth one line in a report, not an alarm
    if records["candidates_waiting_for_vincent"]:
        info.append("Vincent test pending: " + ", ".join(w["task"] for w in records["candidates_waiting_for_vincent"]))
    if records["approved_not_integrated"]:
        info.append("approved, not integrated: " + ", ".join(a["task"] for a in records["approved_not_integrated"]))
    if not processes:
        info.append(f"viewer not running on {args.port}")
    if snapshot["unity_processes"]:
        info.append(f"{snapshot['unity_processes']} Unity process(es) running")
    if snapshot["overlays"].get("working_expired"):
        info.append("expired working markers (prune with nsc_viewer.py done): " + ", ".join(snapshot["overlays"]["working_expired"]))

    snapshot["alerts"] = alerts
    snapshot["info"] = info
    nv.emit(snapshot)
    return 1 if alerts else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "check_failed", "error": f"{type(exc).__name__}: {exc}"}))
        raise SystemExit(2)
