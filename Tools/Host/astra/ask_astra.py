#!/usr/bin/env python
"""ask_astra.py - one persistent Astra conversation that every agent shares.

Astra is `gpt-6-astra`, reachable only through the Codex app's *bundled* CLI. This
tool owns a single long-lived Codex thread: `init` starts it with the primer,
`ask` resumes it, `status` reports on it without spending anything.

    python -B C:/nscrev/astra/ask_astra.py init
    python -B C:/nscrev/astra/ask_astra.py ask --from "Game Agent" --question "..."
    python -B C:/nscrev/astra/ask_astra.py status

Exit codes (deliberately distinct, see EXIT_* below):
    0   answered
    2   still busy at timeout (someone else holds the thread) - retry later
    3   Codex failed (binary missing, non-zero exit, hung call, no thread yet)
    4   Astra refused: the model is unavailable to this CLI
    64  usage error (argparse). NOT 2, so that 2 only ever means "busy".

Standard library only. Windows host.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------
# Exit codes. `ask` is meant to be branched on by other tools and by agents,
# so each code means exactly one thing.
# --------------------------------------------------------------------------

EXIT_OK = 0
EXIT_BUSY = 2
EXIT_CODEX_FAILED = 3
EXIT_MODEL_UNAVAILABLE = 4
EXIT_USAGE = 64

MODEL = "gpt-6-astra"
FALLBACK_MESSAGE = "use the one-shot advice job, nsc-codex-jobs-guide.md 4.4"

# --------------------------------------------------------------------------
# Paths. The NSC_ASTRA_* overrides exist so the unit tests can point every side
# effect at a scratch folder and at a fake codex. They never relax a safety
# guard: the model, the sandbox mode and the forbidden-flag check below are not
# configurable at all.
# --------------------------------------------------------------------------

# The code and its shipped primer live wherever this file is; the runtime data does NOT.
# Those were the same folder while the tool lived in C:\nscrev, and that hid a defect:
# HOME conflated "where the code is" with "where we write". When the tool moved to
# C:\NSC\tools\astra (2026-09-19) the forbidden-root guard below correctly refused every
# command, because the code's new home is under C:\NSC. Separating them preserves that
# guard instead of weakening it - scratch still never lands under the canonical tree.
TOOL_DIR = Path(__file__).resolve().parent

HOME = Path(
    os.environ.get(
        "NSC_ASTRA_HOME",
        os.path.expandvars(r"%LOCALAPPDATA%\nsc-astra"),
    )
)
THREAD_FILE = HOME / "thread.json"
LOCK_FILE = HOME / "astra.lock"
LAST_FILE = HOME / "last.json"
# The primer ships with the tool, so it is read from TOOL_DIR rather than the data HOME.
PRIMER_FILE = Path(os.environ.get("NSC_ASTRA_PRIMER", str(TOOL_DIR / "primer.md")))
LOG_DIR = HOME / "log"
ANSWER_DIR = HOME / "answers"
TMP_DIR = HOME / "tmp"

CODEX_BIN_ROOT = Path(
    os.environ.get(
        "NSC_ASTRA_CODEX_BIN_ROOT",
        os.path.expandvars(r"%LOCALAPPDATA%\OpenAI\Codex\bin"),
    )
)

# Never let this tool's scratch land under the canonical tree.
FORBIDDEN_TEMP_ROOT = Path(r"C:\NSC")

# Test support: the scan looks for this filename inside each hash folder.
CODEX_EXE_NAME = os.environ.get("NSC_ASTRA_CODEX_EXE_NAME", "codex.exe")

STALE_LOCK_SECONDS = 30 * 60
POLL_SECONDS = 10

CREATE_NO_WINDOW = 0x08000000

# Any of these in a failed run's output means the CLI cannot reach the model.
MODEL_UNAVAILABLE_PATTERNS = (
    "requires a newer version of codex",
    "unknown model",
    "model not found",
    "unsupported model",
    "does not support the model",
)

# A safety net, not a feature: if any of these ever reach an argv we build, the
# tool refuses to run rather than asking Codex for write access.
FORBIDDEN_FLAG_SUBSTRINGS = ("--dangerously", "--yolo", "--full-auto")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(ts: _dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(ts: _dt.datetime) -> str:
    """Filename-safe UTC stamp (no colons - this is Windows)."""
    return ts.strftime("%Y%m%dT%H%M%SZ")


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "unknown"


def _write_text(path: Path, text: str) -> None:
    """UTF-8, no BOM, LF endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def _read_json(path: Path):
    try:
        return json.loads(_read_text(path))
    except (OSError, ValueError):
        return None


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _err(message: str) -> None:
    print(message, file=sys.stderr)


# --------------------------------------------------------------------------
# Is a pid alive?
#
# NOT os.kill(pid, 0): on Windows os.kill routes anything that is not a console
# control event to TerminateProcess, so the "liveness probe" would kill the
# process it is asking about. ctypes + OpenProcess is the safe form.
# --------------------------------------------------------------------------

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5


def _pid_alive(pid) -> bool:
    fake = os.environ.get("NSC_ASTRA_FAKE_ALIVE_PIDS")  # tests only
    if fake is not None:
        alive = {p.strip() for p in fake.split(",") if p.strip()}
        return str(pid) in alive
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if not hasattr(ctypes, "WinDLL"):  # non-Windows: assume alive, never steal
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # Access denied means the process exists and is not ours. Treat it as
        # alive: refusing to steal a lock is always the safe direction.
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == _STILL_ACTIVE
        return True
    finally:
        kernel32.CloseHandle(handle)


# --------------------------------------------------------------------------
# Finding the bundled Codex CLI
#
# The brief said "newest by modification time". That is not enough: this
# machine has two hash folders installed in the same minute and only one of
# them contains codex.exe at all. So: consider only folders that really have
# the binary, then prefer the highest version, with mtime as the tiebreak.
# --------------------------------------------------------------------------


def _version_key(version: str):
    """0.155.0-alpha.2.6 -> (0, 155, 0, ...). Unparseable sorts lowest."""
    numbers = [int(n) for n in re.findall(r"\d+", version or "")]
    return tuple(numbers) if numbers else (-1,)


def _codex_version(exe: Path) -> str:
    try:
        proc = subprocess.run(
            _launcher(exe) + ["--version"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or proc.stderr or "").strip().splitlines()[0] if (proc.stdout or proc.stderr) else ""


def _launcher(exe: Path) -> list:
    """Test support: a .py 'binary' is run through this interpreter."""
    if str(exe).lower().endswith(".py"):
        return [sys.executable, "-B", str(exe)]
    return [str(exe)]


def find_codex() -> Path:
    override = os.environ.get("NSC_ASTRA_CODEX_EXE")
    if override:
        path = Path(override)
        if not path.exists():
            raise FileNotFoundError(f"NSC_ASTRA_CODEX_EXE does not exist: {path}")
        return path

    if not CODEX_BIN_ROOT.is_dir():
        raise FileNotFoundError(
            f"Codex bin root not found: {CODEX_BIN_ROOT}. Is the Codex app installed?"
        )

    candidates = []
    for child in CODEX_BIN_ROOT.iterdir():
        if not child.is_dir():
            continue
        exe = child / CODEX_EXE_NAME
        if not exe.is_file():
            continue  # a hash folder without the binary - the mtime trap
        candidates.append(exe)

    if not candidates:
        raise FileNotFoundError(
            f"No {CODEX_EXE_NAME} under {CODEX_BIN_ROOT}. Only the bundled CLI can reach {MODEL}."
        )

    scored = []
    for exe in candidates:
        version = _codex_version(exe)
        scored.append((_version_key(version), exe.stat().st_mtime, exe))
    scored.sort(reverse=True)
    return scored[0][2]


# --------------------------------------------------------------------------
# The lock: one question at a time
# --------------------------------------------------------------------------


class Busy(Exception):
    def __init__(self, holder):
        super().__init__("astra is busy")
        self.holder = holder


def _lock_payload(owner: str) -> dict:
    return {
        "owner": owner,
        "pid": os.getpid(),
        "started_at": _iso(_utc_now()),
    }


def _lock_age_seconds(payload) -> float:
    if not payload or not payload.get("started_at"):
        return float("inf")
    try:
        started = _dt.datetime.strptime(payload["started_at"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return float("inf")
    started = started.replace(tzinfo=_dt.timezone.utc)
    return (_utc_now() - started).total_seconds()


def _lock_is_stale(payload) -> bool:
    """Stale == older than 30 minutes AND its pid is gone. Both, per the brief."""
    if payload is None:
        return True  # unreadable lock file
    return _lock_age_seconds(payload) > STALE_LOCK_SECONDS and not _pid_alive(payload.get("pid"))


def _try_acquire(owner: str) -> bool:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(_lock_payload(owner), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return True


def acquire_lock(owner: str, timeout_seconds: float, sleeper=time.sleep) -> None:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        if _try_acquire(owner):
            return
        holder = _read_json(LOCK_FILE)
        if _lock_is_stale(holder):
            age = _lock_age_seconds(holder)
            _err(
                f"astra: breaking a stale lock (owner={holder.get('owner') if holder else '?'}, "
                f"pid={holder.get('pid') if holder else '?'}, age={int(age) if age != float('inf') else '?'}s)"
            )
            try:
                LOCK_FILE.unlink()
            except OSError:
                pass
            if _try_acquire(owner):
                return
        if time.monotonic() >= deadline:
            raise Busy(holder)
        sleeper(min(POLL_SECONDS, max(0.0, deadline - time.monotonic())))


def release_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------
# Running Codex
# --------------------------------------------------------------------------


class CodexResult:
    def __init__(self, returncode, stdout, stderr, answer, argv, duration):
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.answer = answer or ""
        self.argv = argv
        self.duration = duration
        self.timed_out = False


def _assert_safe(argv) -> None:
    joined = " ".join(argv).lower()
    for bad in FORBIDDEN_FLAG_SUBSTRINGS:
        if bad in joined:
            raise RuntimeError(f"refusing to run: argv contains {bad!r}")
    if MODEL not in argv:
        raise RuntimeError(f"refusing to run: argv does not pin -m {MODEL}")
    if not any(
        a == "--sandbox" or a == "sandbox_mode=read-only" or a == "read-only" for a in argv
    ):
        raise RuntimeError("refusing to run: argv does not pin a read-only sandbox")


def _run_codex(exe: Path, args, stdin_text, timeout_seconds: float) -> CodexResult:
    argv = _launcher(exe) + list(args)
    _assert_safe(argv)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        result = CodexResult(
            None,
            exc.stdout if isinstance(exc.stdout, str) else "",
            exc.stderr if isinstance(exc.stderr, str) else "",
            "",
            argv,
            time.monotonic() - started,
        )
        result.timed_out = True
        return result
    except OSError as exc:
        result = CodexResult(None, "", str(exc), "", argv, time.monotonic() - started)
        return result
    return CodexResult(
        proc.returncode, proc.stdout, proc.stderr, "", argv, time.monotonic() - started
    )


def _thread_id_from_events(stdout: str):
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("thread_id"):
            return str(event["thread_id"])
        nested = event.get("thread")
        if isinstance(nested, dict) and nested.get("id"):
            return str(nested["id"])
    return None


def _looks_model_unavailable(result: CodexResult) -> bool:
    blob = f"{result.stdout}\n{result.stderr}".lower()
    return any(pattern in blob for pattern in MODEL_UNAVAILABLE_PATTERNS)


def _under_forbidden_root(path: Path) -> bool:
    """Windows paths compare case-insensitively; resolve() does not create anything."""
    resolved = path.resolve()
    forbidden = str(FORBIDDEN_TEMP_ROOT.resolve()).lower()
    return any(str(p).lower() == forbidden for p in (resolved, *resolved.parents))


def _assert_home_safe() -> None:
    """Refuse before touching disk. Checked first, so nothing is created and
    then rejected - an earlier version created the folder and *then* refused,
    which left `C:\\NSC\\astra-should-not-happen` behind for a reviewer to find."""
    if _under_forbidden_root(HOME):
        raise RuntimeError(f"refusing to work under {FORBIDDEN_TEMP_ROOT}: NSC_ASTRA_HOME={HOME}")


def _out_file(kind: str) -> Path:
    if _under_forbidden_root(TMP_DIR):
        raise RuntimeError(f"refusing to write scratch under {FORBIDDEN_TEMP_ROOT}: {TMP_DIR}")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    return TMP_DIR / f"{kind}-{_stamp(_utc_now())}-{os.getpid()}.txt"


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------


def cmd_init(args) -> int:
    if THREAD_FILE.exists():
        if not args.new:
            _err(
                f"astra: a thread already exists ({THREAD_FILE}). "
                f"Use `init --new` to start a fresh one; the old file is kept."
            )
            return EXIT_USAGE
        archived = THREAD_FILE.with_name(f"thread-{_stamp(_utc_now())}.json")
        os.replace(THREAD_FILE, archived)
        print(f"kept the old thread as {archived.name}")

    if not PRIMER_FILE.is_file():
        _err(f"astra: primer not found: {PRIMER_FILE}")
        return EXIT_CODEX_FAILED

    try:
        exe = find_codex()
    except FileNotFoundError as exc:
        _err(f"astra: {exc}")
        return EXIT_CODEX_FAILED

    primer = _read_text(PRIMER_FILE)
    out = _out_file("init")
    # The primer goes as an argv argument because that is the form that was
    # verified against the real CLI on 2026-09-17. `-` (stdin) is the verified
    # form for `exec resume`, and that is where this tool uses it.
    result = _run_codex(
        exe,
        [
            "exec",
            "-m",
            MODEL,
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--json",
            "-o",
            str(out),
            primer,
        ],
        None,
        args.call_timeout_min * 60,
    )

    answer = _read_text(out).strip() if out.is_file() else ""
    thread_id = _thread_id_from_events(result.stdout)

    if not thread_id:
        if _looks_model_unavailable(result):
            _err(f"astra: this Codex CLI cannot reach {MODEL}. {FALLBACK_MESSAGE}")
            return EXIT_MODEL_UNAVAILABLE
        _err("astra: Codex started no thread.")
        _err((result.stderr or result.stdout or "")[-2000:])
        return EXIT_CODEX_FAILED

    _write_json_atomic(
        THREAD_FILE,
        {
            "thread_id": thread_id,
            "created_at": _iso(_utc_now()),
            "model": MODEL,
            "primer_sha256": _sha256_file(PRIMER_FILE),
            "codex_version": _codex_version(exe),
            "codex_exe": str(exe),
        },
    )
    print(f"thread {thread_id}")
    if answer:
        print(answer)
    return EXIT_OK


# --------------------------------------------------------------------------
# ask
# --------------------------------------------------------------------------


def _record(asker: str, question: str, result: CodexResult, status: str, thread_id: str) -> Path:
    now = _utc_now()
    answer_path = ANSWER_DIR / f"{_stamp(now)}-{_slug(asker)}.md"
    _write_text(
        answer_path,
        f"# Astra answer for {asker}\n\n"
        f"- when: {_iso(now)}\n- thread: {thread_id}\n- status: {status}\n"
        f"- duration: {result.duration:.1f}s\n\n"
        f"## Question\n\n{question}\n\n## Answer\n\n{result.answer or '(none)'}\n",
    )
    _append_text(
        LOG_DIR / f"{now.strftime('%Y-%m-%d')}.md",
        f"\n---\n\n## {_iso(now)} - {asker}\n\n"
        f"- status: {status}\n- duration: {result.duration:.1f}s\n"
        f"- codex: {os.environ.get('NSC_ASTRA_LOGGED_VERSION', '')}\n"
        f"- answer file: {answer_path.name}\n\n"
        f"**Question**\n\n{question}\n\n**Answer**\n\n{result.answer or '(none)'}\n",
    )
    _write_json_atomic(
        LAST_FILE,
        {"at": _iso(now), "from": asker, "status": status, "answer_file": str(answer_path)},
    )
    return answer_path


def cmd_ask(args) -> int:
    asker = (args.from_agent or "").strip()
    if not asker:
        _err("astra: --from must name the asking agent")
        return EXIT_USAGE

    if args.question_file:
        path = Path(args.question_file)
        if not path.is_file():
            _err(f"astra: question file not found: {path}")
            return EXIT_USAGE
        question = _read_text(path).strip()
    else:
        question = (args.question or "").strip()
    if not question:
        _err("astra: the question is empty")
        return EXIT_USAGE

    thread = _read_json(THREAD_FILE)
    if not thread or not thread.get("thread_id"):
        _err(f"astra: no thread yet. Run `ask_astra.py init` first ({THREAD_FILE}).")
        return EXIT_CODEX_FAILED
    thread_id = thread["thread_id"]

    try:
        exe = find_codex()
    except FileNotFoundError as exc:
        _err(f"astra: {exc}")
        return EXIT_CODEX_FAILED
    os.environ["NSC_ASTRA_LOGGED_VERSION"] = _codex_version(exe)

    try:
        acquire_lock(asker, args.timeout_min * 60)
    except Busy as exc:
        holder = exc.holder or {}
        _err(
            f"astra: still busy after {args.timeout_min} min "
            f"(owner={holder.get('owner', '?')}, pid={holder.get('pid', '?')}, "
            f"since={holder.get('started_at', '?')}). Try again later."
        )
        return EXIT_BUSY

    try:
        out = _out_file("ask")
        result = _run_codex(
            exe,
            [
                "exec",
                "resume",
                thread_id,
                "-m",
                MODEL,
                "--skip-git-repo-check",
                "-c",
                "sandbox_mode=read-only",
                "--json",
                "-o",
                str(out),
                "-",
            ],
            f"From {asker}: {question}\n",
            args.call_timeout_min * 60,
        )
        result.answer = _read_text(out).strip() if out.is_file() else ""
        if not result.answer:
            # -o should always be written; fall back to the event stream so a
            # CLI change does not silently turn an answer into a failure.
            result.answer = _last_message_from_events(result.stdout)
    finally:
        release_lock()

    # An answer is an answer. Classify failures only when nothing came back,
    # so that Astra quoting "unknown model" in its prose cannot become exit 4.
    if result.answer:
        _record(asker, question, result, "answered", thread_id)
        print(result.answer)
        return EXIT_OK

    if _looks_model_unavailable(result):
        _record(asker, question, result, "model-unavailable", thread_id)
        _err(f"astra: this Codex CLI cannot reach {MODEL}. {FALLBACK_MESSAGE}")
        return EXIT_MODEL_UNAVAILABLE

    status = "timed-out" if result.timed_out else "codex-failed"
    _record(asker, question, result, status, thread_id)
    if result.timed_out:
        _err(f"astra: the Codex call did not finish within {args.call_timeout_min} min.")
    else:
        _err(f"astra: Codex failed (exit {result.returncode}).")
    _err((result.stderr or result.stdout or "")[-2000:])
    return EXIT_CODEX_FAILED


def _last_message_from_events(stdout: str) -> str:
    text = ""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") in ("item.completed", "turn.completed", "agent_message"):
            item = event.get("item") or event
            candidate = item.get("text") or item.get("message") or ""
            if isinstance(candidate, str) and candidate.strip():
                text = candidate.strip()
    return text


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def cmd_status(args) -> int:
    thread = _read_json(THREAD_FILE)
    if thread:
        print(f"thread:        {thread.get('thread_id')}")
        print(f"created:       {thread.get('created_at')}")
        print(f"model:         {thread.get('model')}")
        print(f"codex at init: {thread.get('codex_version')}")
        if PRIMER_FILE.is_file():
            current = _sha256_file(PRIMER_FILE)
            same = current == thread.get("primer_sha256")
            print(f"primer:        {'unchanged' if same else 'CHANGED since init'}")
    else:
        print(f"thread:        none - run `init` ({THREAD_FILE})")

    last = _read_json(LAST_FILE)
    if last:
        print(f"last question: {last.get('at')} from {last.get('from')} ({last.get('status')})")
    else:
        print("last question: none recorded")

    holder = _read_json(LOCK_FILE) if LOCK_FILE.exists() else None
    if holder:
        alive = _pid_alive(holder.get("pid"))
        age = _lock_age_seconds(holder)
        print(
            f"lock:          {holder.get('owner')} pid={holder.get('pid')} "
            f"since={holder.get('started_at')} age={int(age) if age != float('inf') else '?'}s "
            f"pid_alive={alive} stale={_lock_is_stale(holder)}"
        )
    elif LOCK_FILE.exists():
        print("lock:          present but unreadable (treated as stale)")
    else:
        print("lock:          free")

    try:
        exe = find_codex()
        print(f"codex:         {exe}")
        print(f"codex version: {_codex_version(exe) or 'unknown'}")
    except FileNotFoundError as exc:
        print(f"codex:         NOT FOUND - {exc}")

    if os.environ.get("NSC_ASTRA_FAKE_ALIVE_PIDS") is not None:
        print("NOTE:          NSC_ASTRA_FAKE_ALIVE_PIDS is set (test override active)")
    return EXIT_OK


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; 2 means 'busy' here, so remap it."""

    def error(self, message):
        self.print_usage(sys.stderr)
        _err(f"{self.prog}: error: {message}")
        raise SystemExit(EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="ask_astra.py", description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command", required=True)

    init = subs.add_parser("init", help="start the persistent thread with the primer")
    init.add_argument("--new", action="store_true", help="archive an existing thread and start over")
    init.add_argument("--call-timeout-min", type=float, default=10.0)
    init.set_defaults(func=cmd_init)

    ask = subs.add_parser("ask", help="ask Astra a question in the shared thread")
    ask.add_argument("--from", dest="from_agent", required=True, help="the asking agent's title")
    group = ask.add_mutually_exclusive_group(required=True)
    group.add_argument("--question", help="the question text")
    group.add_argument("--question-file", help="a markdown file holding the question")
    ask.add_argument(
        "--timeout-min",
        type=float,
        default=20.0,
        help="how long to wait for the lock before exiting 2 (default 20)",
    )
    ask.add_argument(
        "--call-timeout-min",
        type=float,
        default=10.0,
        help="how long to let one Codex call run before exiting 3 (default 10)",
    )
    ask.set_defaults(func=cmd_ask)

    status = subs.add_parser("status", help="report on the thread and the lock; makes no model call")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _assert_home_safe()
        return args.func(args)
    except RuntimeError as exc:  # a refused argv
        _err(f"astra: {exc}")
        return EXIT_CODEX_FAILED


if __name__ == "__main__":
    sys.exit(main())
