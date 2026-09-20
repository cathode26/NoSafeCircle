#!/usr/bin/env python
"""run_job.py - one command per Claude helper job type.

Replaces the hand-typed recipes in nsc-codex-jobs-guide.md section 4.3: the
service, model, --max-turns and --allowedTools list are built in per job type,
every job gets --permission-mode dontAsk and --disallowedTools Task, the guards
fail closed, and one telemetry line lands in claude-jobs/jobs.jsonl.

Usage:
    C:/Python313/python.exe -B run_job.py <type> --brief <file.md> [options]

Standard library only. Windows host.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------
# Paths and environment overrides.
#
# The overrides exist so the unit tests can point every side effect at a
# scratch folder and at fake executables. A review on 2026-09-18 showed that a
# production caller could use the same variables to move FORBIDDEN_ROOT and
# CANONICAL somewhere harmless and then run a read-write job against the real
# canonical checkout: the guards were doing exactly what they were told, about
# the wrong paths. So the overrides now need one explicit opt-in that no real
# job sets. A README sentence saying "never set these" is not a guard.
# --------------------------------------------------------------------------

TESTING = os.environ.get("NSC_RUN_JOB_TESTING") == "1"

_IGNORED_OVERRIDES: list[str] = []


def _override(name: str, default: str) -> str:
    """An NSC_RUN_JOB_* override, honoured only under NSC_RUN_JOB_TESTING=1."""
    value = os.environ.get(name)
    if value is None:
        return default
    if not TESTING:
        _IGNORED_OVERRIDES.append(name)
        return default
    return value


NSCREV = Path(_override("NSC_RUN_JOB_NSCREV", r"C:\nscrev"))
JOBS_DIR = Path(_override("NSC_RUN_JOB_JOBS_DIR", str(NSCREV / "claude-jobs")))
TELEMETRY = Path(_override("NSC_RUN_JOB_TELEMETRY", str(JOBS_DIR / "jobs.jsonl")))
GUIDE = Path(_override("NSC_RUN_JOB_GUIDE", r"C:\NSC\nsc-codex-jobs-guide.md"))
CANONICAL = Path(_override("NSC_RUN_JOB_CANONICAL", r"C:\NSC\NSC\NoSafeCircle"))
FORBIDDEN_ROOT = Path(_override("NSC_RUN_JOB_FORBIDDEN_ROOT", r"C:\NSC"))
COMPOSE_PROJECT = _override("NSC_RUN_JOB_COMPOSE_PROJECT", "nosafecircle")

# Model ids, verified against `claude --help` ("--model <model> ... or a
# model's full name").
MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5",
}

USAGE_WARN_PCT = 85
SUMMARY_MAX_LINES = 20

READ_ONLY_DOCKER_TOOLS = ["Read", "Glob", "Grep", "Bash"]
READ_WRITE_DOCKER_TOOLS = ["Read", "Glob", "Grep", "Bash", "Edit", "Write"]
HOST_READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]

# Per-type built-in parameters. Sources: nsc-codex-jobs-guide.md 4.3 (the
# service / model / tools table) and the header comment of each template in
# C:\nscrev\claude-jobs\templates\ (which carries the verified --max-turns).
JOB_TYPES: dict[str, dict] = {
    "lookup": {
        "where": "docker",
        "service": "claude-exec",
        "model": MODELS["haiku"],
        "max_turns": 30,
        "tools": READ_ONLY_DOCKER_TOOLS,
        "needs_clone": True,
        "template": "lookup-job-prompt.md",
        "note": "read-only clone at /workspace",
    },
    "review": {
        "where": "docker",
        "service": "claude-exec",
        "model": MODELS["sonnet"],
        "max_turns": 80,
        "tools": READ_ONLY_DOCKER_TOOLS,
        "needs_clone": True,
        "template": "review-job-prompt.md",
        "note": "read-only clone at /workspace; use --model opus for identity, "
                "locking, provider-spend or merge code",
    },
    "test-run": {
        "where": "docker",
        "service": "claude-exec",
        "model": MODELS["haiku"],
        "max_turns": 30,
        "tools": READ_ONLY_DOCKER_TOOLS,
        "needs_clone": True,
        "template": "test-run-job-prompt.md",
        "note": "read-only clone; tests run in /tmp copies",
    },
    "clone-edit": {
        "where": "docker",
        "service": "claude",
        "model": MODELS["sonnet"],
        "max_turns": 60,
        "tools": READ_WRITE_DOCKER_TOOLS,
        "needs_clone": True,
        "template": "clone-edit-job-prompt.md",
        "note": "read-write clone at /workspace; job clone only",
    },
    "contract-draft": {
        "where": "docker",
        "service": "claude",
        "model": MODELS["sonnet"],
        "max_turns": 60,
        "tools": READ_WRITE_DOCKER_TOOLS,
        "needs_clone": True,
        "template": "contract-draft-job-prompt.md",
        "note": "read-write clone at /workspace; job clone only",
    },
    "host-lookup": {
        "where": "host",
        "service": None,
        "model": MODELS["haiku"],
        "max_turns": 30,
        "tools": HOST_READ_ONLY_TOOLS,
        "needs_clone": False,
        "template": None,
        "note": "host files, Windows tools, the PixelLab MCP or --agent; add "
                "Bash with --allow-bash <program>",
    },
    "advice": {
        "where": "host",
        "service": None,
        "model": MODELS["opus"],
        "max_turns": 40,
        "tools": HOST_READ_ONLY_TOOLS,
        "needs_clone": False,
        "template": None,
        "add_dir": [str(FORBIDDEN_ROOT).replace("\\", "/"), str(NSCREV).replace("\\", "/")],
        "codex_option": True,
        "note": "read-only stand-in for Astra while Codex is off; --astra "
                "selects the Codex path once Codex is back",
    },
}

DOCKER_TYPES = sorted(t for t, c in JOB_TYPES.items() if c["where"] == "docker")
HOST_TYPES = sorted(t for t, c in JOB_TYPES.items() if c["where"] == "host")


class Refused(Exception):
    """A guard refused the job. Message says what to do instead."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def fwd(p) -> str:
    """Windows path with forward slashes: what docker -v and claude both take."""
    return str(p).replace("\\", "/")


# Rule 9 (C:\NSC\nsc-quiet-windows-guide.md): a spawn that flashes a console window
# interrupts Vincent while he works, so every spawn here is windowless. Never
# DETACHED_PROCESS: that creates a console instead of suppressing one.
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# Measured by the Documentation Agent on 2026-09-17: a short host job adds 3-4
# conhost.exe windows, with CREATE_NO_WINDOW and with a hidden PowerShell window
# alike, because the CLI spawns its own children. Docker jobs add none. So a host
# job says so, and names the Docker type that would avoid it.
DOCKER_ALTERNATIVE = {"host-lookup": "lookup", "advice": "review"}


def warn_about_host_consoles(job_type: str, reason: str | None) -> int:
    alternative = DOCKER_ALTERNATIVE.get(job_type)
    instead = f" If `{alternative}` would do, use it instead." if alternative else ""
    said = f" Reason given: {reason}" if reason else " No reason given."
    print(f"NOTE: the host path flashes 3-4 console windows while it runs (the CLI's own "
          f"children; Docker jobs flash none).{instead}{said}")
    return 1


def run_quiet(*args, **kwargs):
    """subprocess.run with CREATE_NO_WINDOW and a closed stdin.

    stdin matters: these pre-flight calls (`auth status`, `/usage`, `docker
    compose run`) inherit the caller's stdin by default, and a reviewer running
    the suite with stdin on an open pipe watched `auth status` block until the
    300-second limit. A pre-flight check that can hang forever is a pre-flight
    check that gets skipped. Callers that really do pipe input pass their own.
    """
    kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    if "input" not in kwargs:  # subprocess.run rejects stdin and input together
        kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(*args, **kwargs)


def which(env_var: str, program: str) -> str:
    override = os.environ.get(env_var)
    if override:
        if not Path(override).exists():
            raise Refused(
                f"{env_var} points at {override}, which does not exist. "
                f"Unset {env_var} to use the installed {program}."
            )
        return override
    found = shutil.which(program)
    if not found:
        raise Refused(
            f"`{program}` is not on PATH. Install it or set {env_var} to its full path."
        )
    return found


def _identity(path: Path):
    """(device, inode) for a path that exists, else None.

    Windows populates both from the file index, so every spelling of the same
    directory gives the same pair: `C:\\NSC`, `c:\\nsc`, `\\\\?\\C:\\NSC`,
    `\\\\localhost\\C$\\NSC` and `\\\\127.0.0.1\\C$\\NSC` all match. String
    comparison does not - `resolve()` keeps the `\\\\?\\` and UNC prefixes, so
    `relative_to` raises ValueError and the guard silently opens. A review on
    2026-09-18 got three such spellings of the canonical repo past this guard.
    """
    try:
        st = path.stat()
    except (OSError, ValueError):
        return None
    dev, ino = getattr(st, "st_dev", 0), getattr(st, "st_ino", 0)
    return (dev, ino) if dev and ino else None


def same_path(a: Path, b: Path) -> bool:
    ia, ib = _identity(a), _identity(b)
    if ia is not None and ib is not None:
        return ia == ib
    return _norm_str(a) == _norm_str(b)


def _norm_str(path: Path) -> str:
    """Last-resort comparison for paths that do not exist yet."""
    text = str(path)
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\", "\\\\.\\"):
        if text.upper().startswith(prefix.upper()):
            text = text[len(prefix):]
            if prefix.endswith("UNC\\"):
                text = "\\\\" + text
            break
    try:
        text = str(Path(text).resolve())
    except (OSError, ValueError):
        pass
    return os.path.normcase(os.path.normpath(text))


def is_under(child: Path, parent: Path) -> bool:
    """True if `child` is `parent` or lives inside it, whatever the spelling.

    Walks the child's own parents comparing filesystem identity, so a UNC or
    `\\\\?\\` spelling cannot slip past. Falls back to string comparison only
    when a path does not exist (`--out` for a folder not created yet).
    """
    try:
        resolved = child.resolve()
    except (OSError, ValueError):
        resolved = child
    target = _identity(parent)
    if target is not None:
        for candidate in (resolved, *resolved.parents):
            if _identity(candidate) == target:
                return True
        # The child may not exist yet; fall through to the string comparison.
        if _identity(resolved) is not None:
            return False
    parent_text = _norm_str(parent)
    child_text = _norm_str(child)
    return child_text == parent_text or child_text.startswith(parent_text + os.sep)


# --------------------------------------------------------------------------
# guards - every one fails closed and says what to do
# --------------------------------------------------------------------------


def guard_brief(brief: Path) -> Path:
    if not brief.exists():
        raise Refused(
            f"brief {brief} does not exist. Copy a template from "
            f"{fwd(JOBS_DIR / 'templates')} and fill it in with the Write tool "
            "(printf/echo in Git Bash break Windows paths)."
        )
    if not brief.is_file():
        raise Refused(f"brief {brief} is not a file.")
    text = brief.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise Refused(f"brief {brief} is empty. Fill it in before running the job.")
    head = "\n".join(text.splitlines()[:8])
    if "delete this comment before running" in head or "Fill every <...>" in head:
        raise Refused(
            f"brief {brief} still has the template header comment. Fill every "
            "<...> and delete the comment, then run again."
        )
    return brief


def guard_clone(clone: Path, needed: bool, job_type: str) -> Path | None:
    if clone is None:
        if needed:
            raise Refused(
                f"{job_type} runs in Docker and needs --clone <path>. Make a job "
                "clone first:\n"
                f"  git clone -q -c core.autocrlf=true -c core.filemode=false "
                f"{fwd(CANONICAL)} {fwd(NSCREV / 'cj-<name>')}"
            )
        return None

    if not clone.exists():
        raise Refused(f"--clone {clone} does not exist.")
    if not clone.is_dir():
        raise Refused(f"--clone {clone} is not a directory.")

    resolved = clone.resolve()
    if same_path(resolved, CANONICAL) or is_under(resolved, FORBIDDEN_ROOT):
        raise Refused(
            f"--clone {resolved} is the canonical checkout (or inside "
            f"{FORBIDDEN_ROOT}). A job never runs there. Make a standalone job "
            "clone:\n"
            f"  git clone -q -c core.autocrlf=true -c core.filemode=false "
            f"{fwd(CANONICAL)} {fwd(NSCREV / 'cj-<name>')}"
        )

    dotgit = resolved / ".git"
    if not dotgit.exists():
        raise Refused(
            f"--clone {resolved} has no .git, so it is not a repository clone. "
            "Clone the repo into a fresh folder under C:/nscrev."
        )
    if dotgit.is_file():
        raise Refused(
            f"--clone {resolved} is a git worktree (.git is a file, not a "
            "directory). A job never runs in a worktree, because it shares the "
            "canonical object store. Make a standalone clone instead:\n"
            f"  git clone -q -c core.autocrlf=true -c core.filemode=false "
            f"{fwd(CANONICAL)} {fwd(NSCREV / 'cj-<name>')}"
        )
    return resolved


# A rule is `Tool` or `Tool(specifier)`. mcp__server__tool matches too.
TOOL_RULE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\((.*)\))?", re.DOTALL)

# Bash specifiers that constrain nothing: empty, or made only of wildcard/
# separator characters. `Bash(*)`, `Bash( )`, `Bash(:*)` and `Bash(**)` are all
# unrestricted shell wearing a specifier; `Bash(git status:*)` is not, because
# "git status" survives the strip.
_BASH_NOOP_SPECIFIER_RE = re.compile(r"[*:.]*")


def _bash_specifier_is_unconstrained(specifier: str | None) -> bool:
    if specifier is None:
        return True
    return _BASH_NOOP_SPECIFIER_RE.fullmatch(specifier.strip()) is not None


def split_tool_rule_value(value: str) -> list[str]:
    """Split one --allow-tool value into individual rules.

    A review on 2026-09-18 found that `TOOL_RULE_RE`'s greedy `(.*)` let
    `--allow-tool "Read(a),Bash,Agent,Write,Read(b)"` parse as a single rule
    named `Read` with everything up to the last `)` folded into its specifier
    - and `claude --help` says --allowedTools takes a "Comma or
    space-separated list", so the CLI would then split what this guard saw as
    one rule into five. Split here the same way the CLI does, so every rule is
    validated on its own, but never inside parentheses: `Bash(git status:*)`
    has a space that must stay put.
    """
    rules: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in value:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif depth == 0 and (ch == "," or ch.isspace()):
            if current:
                rules.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        rules.append("".join(current))
    return rules

# Never grantable, on any job type, by any flag: a job that can spawn its own
# subagents escapes every budget and guard this tool applies. `--disallowedTools
# Task` is the guide's rule; `Agent` is the same capability under this session's
# name for it, and nobody has shown that disallowing one disallows the other.
NEVER_GRANTABLE = {"task", "agent"}

WRITE_TOOLS = {"write", "edit", "multiedit", "notebookedit"}


def _rule_tool_name(rule: str) -> tuple[str, str | None]:
    match = TOOL_RULE_RE.fullmatch(rule.strip())
    if not match:
        raise Refused(
            f"--allow-tool {rule!r} is not a tool rule. Pass `Tool` or "
            "`Tool(specifier)`, for example `Bash(git status:*)`."
        )
    return match.group(1), match.group(2)


def guard_allow_tool(rule: str, base_tools: list[str], job_type: str) -> None:
    """Refuse a rule that would widen a job type past what its type means.

    A review on 2026-09-18 reproduced
    `advice --allow-tool Write --allow-tool Edit --allow-tool Bash`, which
    turned a read-only Opus advice job into a read-write one with unrestricted
    Bash and C:/NSC on --add-dir. --allow-tool is for narrowing additions like
    `Bash(git log:*)`, not for changing what a job type is.
    """
    rule = rule.strip()
    if not rule or "\n" in rule or "\r" in rule:
        raise Refused(f"--allow-tool {rule!r} is empty or spans lines.")

    name, specifier = _rule_tool_name(rule)
    lowered = name.lower()
    base_lowered = {t.split("(")[0].lower() for t in base_tools}

    if lowered in NEVER_GRANTABLE:
        raise Refused(
            f"--allow-tool {rule!r} would let the job spawn its own subagents, "
            "which no job type may do. Run a second job instead."
        )
    if lowered in WRITE_TOOLS and lowered not in base_lowered:
        raise Refused(
            f"--allow-tool {rule!r} adds a write tool to `{job_type}`, which is "
            f"a read-only job type (it has {', '.join(base_tools)}). Use a "
            "read-write type - `clone-edit` or `contract-draft` - in a job clone."
        )
    if lowered == "bash" and _bash_specifier_is_unconstrained(specifier):
        raise Refused(
            f"--allow-tool {rule!r} grants unrestricted shell (its specifier "
            "constrains nothing). Use `--allow-bash <program>` for a "
            "Bash(<program>:*) rule, or pass a scoped rule such as "
            "--allow-tool 'Bash(git log:*)'."
        )
    # `bash` is in this set because a SCOPED Bash rule is the documented use of
    # --allow-tool: `--allow-bash git` is just shorthand for `Bash(git:*)`. Bare
    # `Bash` never reaches here - the check above refuses it.
    if lowered not in base_lowered and lowered not in {
        "read", "glob", "grep", "bash", "notebookread", "webfetch", "websearch", "todowrite",
    } and not lowered.startswith("mcp__"):
        raise Refused(
            f"--allow-tool {rule!r} names `{name}`, which is not part of "
            f"`{job_type}` and is not one of the read-only extras. If the job "
            "really needs it, use a job type that has it."
        )


def guard_tool_list(tools: list[str], base_tools: list[str], job_type: str) -> None:
    """Belt-and-braces pass over the assembled --allowedTools list.

    Splits each entry the same way `split_tool_rule_value` does before
    parsing it, so a packed value that reached this list by some other route
    (not through `guard_allow_tool`) cannot hide a second rule inside the
    first one's specifier.
    """
    base_lowered = {t.split("(")[0].lower() for t in base_tools}
    for entry in tools:
        for rule in split_tool_rule_value(entry):
            name, _spec = _rule_tool_name(rule)
            lowered = name.lower()
            if lowered in NEVER_GRANTABLE:
                raise Refused(f"refusing to run: {rule!r} reached the tool list for `{job_type}`.")
            if lowered in WRITE_TOOLS and lowered not in base_lowered:
                raise Refused(
                    f"refusing to run: {rule!r} is a write tool and `{job_type}` is read-only."
                )


def guard_compose_file(clone: Path) -> None:
    if not (clone / "compose.yaml").exists():
        raise Refused(
            f"{clone} has no compose.yaml, so `docker compose` cannot run there. "
            "Use a clone of the repository root."
        )


def guard_out(out: Path, dry_run: bool = False) -> Path:
    resolved = out if out.is_absolute() else (Path.cwd() / out)
    # `is_under(resolved, FORBIDDEN_ROOT)` catches an --out UNDER C:\NSC.
    # `is_under(FORBIDDEN_ROOT, resolved)` catches the other direction: an
    # --out that is an ANCESTOR of C:\NSC (`C:\`, `C:/Users/..`,
    # `//localhost/C$`, `//?/C:/`), which a review on 2026-09-18 showed passes
    # today and would mount C:\NSC writable at /out/NSC. Both directions reuse
    # the same filesystem-identity walk, so no spelling of either relation
    # slips through as a plain string mismatch.
    if is_under(resolved, FORBIDDEN_ROOT) or is_under(FORBIDDEN_ROOT, resolved):
        raise Refused(
            f"--out {resolved} is inside, or an ancestor of, {FORBIDDEN_ROOT}. Job "
            f"output goes under {fwd(JOBS_DIR)}."
        )
    if not dry_run:  # --dry-run changes nothing on disk, folders included
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def guard_model(raw: str | None, default: str) -> str:
    if raw is None:
        return default
    if raw in MODELS:
        return MODELS[raw]
    if re.fullmatch(r"claude-[A-Za-z0-9._-]+", raw):
        return raw
    raise Refused(
        f"--model {raw!r} is not a model this tool will pass on. Use an alias "
        f"({', '.join(sorted(MODELS))}) or a full claude-* id."
    )


def guard_docker_engine(docker: str) -> str:
    try:
        proc = run_quiet(
            [docker, "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(
            f"could not ask Docker for its server version ({exc}). Start Docker "
            "Desktop and try again."
        ) from exc
    version = (proc.stdout or "").strip()
    if proc.returncode != 0 or not version:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise Refused(
            "the Docker engine did not answer"
            + (f": {detail[0]}" if detail else "")
            + ". Start Docker Desktop, wait for it to report running, then try again."
        )
    return version


def guard_docker_image(docker: str, service: str) -> str:
    image = f"{COMPOSE_PROJECT}-{service}:latest"
    try:
        proc = run_quiet(
            [docker, "images", "-q", image],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f"could not list Docker images ({exc}).") from exc
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        raise Refused(
            f"image {image} is not built. Build it first:\n"
            f"  docker compose -p {COMPOSE_PROJECT} build {service}"
        )
    return (proc.stdout or "").strip().splitlines()[0]


CODEX_BANNER_RE = re.compile(r"No Codex until\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def read_codex_banner(guide: Path = None) -> tuple[str | None, str]:
    """Return (YYYY-MM-DD or None, how we know). Never hard-code the date."""
    guide = guide or GUIDE
    try:
        text = guide.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"could not read {guide} ({exc})"
    match = CODEX_BANNER_RE.search(text)
    if not match:
        return None, f"no 'No Codex until <date>' banner in {guide}"
    return match.group(1), f"{guide} banner"


def guard_codex_available(today: _dt.date = None, guide: Path = None) -> None:
    today = today or _dt.date.today()
    until, how = read_codex_banner(guide)
    if until is None:
        raise Refused(
            f"cannot tell whether Codex is on: {how}. Codex jobs stay refused "
            "until the banner can be read (fail closed). Use the Claude path, "
            "or fix the guide."
        )
    try:
        until_date = _dt.date.fromisoformat(until)
    except ValueError:
        raise Refused(
            f"the Codex banner date {until!r} in {how} is not a date. Fix the "
            "banner; Codex jobs stay refused until it parses."
        ) from None
    if today < until_date:
        raise Refused(
            f"Codex is off until {until} ({how}); today is {today.isoformat()}. "
            "Do not retry and do not buy credits - that is Vincent's call. Run "
            "the Claude path instead (drop --astra)."
        )


# --------------------------------------------------------------------------
# account check - the one command that talks to the provider
# --------------------------------------------------------------------------


def parse_usage(raw: str) -> dict:
    """Pull account and session/week percentages out of `claude -p /usage`.

    Tolerant on purpose: an unparseable answer is a warning, never a crash.
    """
    text = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            text = str(data.get("result") or "")
            if not text:
                text = raw
    except (ValueError, TypeError):
        pass

    out: dict = {"account": None, "session_pct": None, "week_pct": None, "raw": text}

    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if email:
        out["account"] = email.group(0)
    else:
        label = re.search(r"(?:account|logged in as|email)\s*[:=]?\s*([^\s,;|]+)",
                          text, re.IGNORECASE)
        if label:
            out["account"] = label.group(1).strip().strip(".,")

    for key, word in (("session_pct", "session"), ("week_pct", r"week(?:ly)?")):
        pct = re.search(rf"{word}[^\n%]{{0,80}}?(\d{{1,3}})\s*%", text, re.IGNORECASE)
        if not pct:
            pct = re.search(rf"(\d{{1,3}})\s*%[^\n]{{0,40}}?{word}", text, re.IGNORECASE)
        if pct:
            try:
                value = int(pct.group(1))
            except ValueError:
                continue
            if 0 <= value <= 100:
                out[key] = value
    return out


# Vincent, 2026-09-17: "All outsourced work needs to be done through
# cathode26@gmail.com ... the pipeline should go through docker". The host CLI was
# logged in as the Outlook account, so a host job spent the wrong one without saying
# so. Where a job runs decides who pays: Docker carries its own login in a volume,
# the host CLI uses this machine's login.
OUTSOURCE_ACCOUNT = "cathode26@gmail.com"
EMAIL_LINE_RE = re.compile(r"^\s*Email:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


def parse_auth_email(text: str) -> str | None:
    match = EMAIL_LINE_RE.search(text or "")
    return match.group(1).strip() if match else None


# The 24-hour account cache was REMOVED on 2026-09-18 and must not come back
# in this shape. A review reproduced the bypass: writing
#   {"claude": {"account": "cathode26@gmail.com", "checked_at": 9e12}}
# to account-cache.json made every clone-edit job trust that answer without
# asking, because a checked_at in the future never expires. The file sits in
# JOBS_DIR, which every agent can write. Two smaller problems made it a bad
# trade anyway: the guide's own 4.3 records a container login flipping inside
# one day, so an honest cache was still wrong for up to 24 hours; and the
# Docker branch of logged_in_account had no test at all, so a cache that always
# returned the Gmail address would have kept the whole suite green.
#
# The cache saved one `auth status` call per job - about a second, and no
# tokens. That is not worth a guard that fails open on which account pays.


def logged_in_account(job: dict, timeout: int = 240) -> tuple[str | None, str]:
    """The account that will actually pay for this job: (email or None, how we know)."""
    if job["where"] == "host":
        claude = which("NSC_RUN_JOB_CLAUDE", "claude")
        try:
            proc = run_quiet([claude, "auth", "status", "--text"], capture_output=True,
                                  text=True, timeout=timeout, cwd=str(NSCREV))
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"host `claude auth status` did not run ({exc})"
        return parse_auth_email(proc.stdout or ""), "the host CLI login"

    service = job["service"]
    docker = which("NSC_RUN_JOB_DOCKER", "docker")
    argv = [docker, "compose", "-p", COMPOSE_PROJECT, "run", "--rm", "-T", "--no-deps",
            service, "claude", "auth", "status", "--text"]
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"
    try:
        proc = run_quiet(argv, capture_output=True, text=True, timeout=timeout,
                              cwd=str(job["cwd"]), env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"`claude auth status` in the {service} container did not run ({exc})"
    email = parse_auth_email(proc.stdout or "")
    return email, f"the login of the {service} container"


def guard_account(account: str | None, how: str, allow: str | None) -> str:
    """Refuse a job that would spend an account other than the outsourcing one."""
    if account is None:
        raise Refused(
            f"cannot tell which account this job would spend ({how}), so it is refused (fail closed). "
            "Check with `claude auth status --text`, or run a Docker type."
        )
    if account.casefold() == OUTSOURCE_ACCOUNT.casefold():
        return account
    if allow and allow.casefold() == account.casefold():
        print(f"WARNING: spending {account}, not {OUTSOURCE_ACCOUNT}, because --allow-account says so.")
        return account
    raise Refused(
        f"this job would spend {account} ({how}), not {OUTSOURCE_ACCOUNT}. Vincent's rule is that all "
        f"outsourced work goes through {OUTSOURCE_ACCOUNT}, which is the login inside Docker. Run a Docker "
        f"type instead (lookup, review, test-run, clone-edit, contract-draft), or, if it truly has to run "
        f"here, pass --allow-account {account} and tell Vincent why."
    )


def account_check(claude: str, cwd: Path, timeout: int = 180) -> dict:
    """Run `claude -p "/usage"`. Returns the parsed dict plus 'ok'/'warning'."""
    argv = [claude, "-p", "/usage", "--output-format", "json"]
    try:
        proc = run_quiet(
            argv, capture_output=True, text=True, timeout=timeout, cwd=str(cwd),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "warning": f"account check did not run: {exc}",
                "account": None, "session_pct": None, "week_pct": None}

    parsed = parse_usage(proc.stdout or "")
    if proc.returncode != 0:
        first = (proc.stderr or "").strip().splitlines()
        parsed["ok"] = False
        parsed["warning"] = (
            "account check exited "
            f"{proc.returncode}" + (f": {first[0]}" if first else "")
        )
        return parsed
    if parsed["account"] is None and parsed["session_pct"] is None \
            and parsed["week_pct"] is None:
        parsed["ok"] = False
        parsed["warning"] = "could not parse `claude -p /usage` output"
        return parsed
    parsed["ok"] = True
    parsed["warning"] = None
    return parsed


def host_account() -> str | None:
    """The account the host CLI is logged into, which is whose usage `/usage` reports."""
    try:
        claude = which("NSC_RUN_JOB_CLAUDE", "claude")
        proc = run_quiet([claude, "auth", "status", "--text"], capture_output=True,
                              text=True, timeout=120, cwd=str(NSCREV))
    except Exception:
        return None
    return parse_auth_email(proc.stdout or "")


def print_account_check(info: dict, how: str = None, usage_of: str = None) -> int:
    account = info.get("account") or "unknown account"
    def pct(v):
        return "?" if v is None else f"{v}%"
    source = f" ({how})" if how else ""
    # The percentages come from the host CLI. Say so when that is a different account
    # from the one paying for this job, so the numbers are never read as this job's.
    whose = ""
    if usage_of and usage_of.casefold() != str(account).casefold():
        whose = f" (usage shown is {usage_of}'s, not this job's)"
    print(f"account: {account}{source}  session {pct(info.get('session_pct'))}  "
          f"week {pct(info.get('week_pct'))}{whose}")
    printed = 1
    if info.get("warning"):
        print(f"WARNING: {info['warning']} - continuing (this is a warning, not a stop).")
        printed += 1
    for label, key in (("session", "session_pct"), ("week", "week_pct")):
        value = info.get(key)
        if value is not None and value > USAGE_WARN_PCT:
            print(f"WARNING: {label} usage is {value}% (over {USAGE_WARN_PCT}%). "
                  "Consider stopping jobs on this account and telling Vincent.")
            printed += 1
    return printed


# --------------------------------------------------------------------------
# argv construction
# --------------------------------------------------------------------------


def claude_argv(cfg: dict, model: str, max_turns: int, tools: list[str],
                agent: str | None, add_dir: list[str], claude_exe: str = "claude"
                ) -> list[str]:
    """The `claude -p ...` part, in the verified order.

    Host form from nsc-codex-jobs-guide.md 4.3:
      claude -p [--agent <a>] [--model <m>] --max-turns <n>
        --permission-mode dontAsk --allowedTools <tools> --output-format json
    plus --disallowedTools Task (guide 4.3: "Add --disallowedTools Task to job
    commands"). --allowedTools / --disallowedTools / --add-dir are variadic, so
    each is followed by another flag and never by a positional.
    """
    argv = [claude_exe, "-p"]
    if agent:
        argv += ["--agent", agent]
    if add_dir:
        argv += ["--add-dir", *add_dir]
    argv += ["--model", model]
    argv += ["--max-turns", str(max_turns)]
    argv += ["--permission-mode", "dontAsk"]
    argv += ["--allowedTools", *tools]
    argv += ["--disallowedTools", "Task"]
    argv += ["--output-format", "json"]
    return argv


def docker_argv(docker: str, service: str, out_dir: Path, inner: list[str]) -> list[str]:
    """`docker compose -p nosafecircle run --rm -T --no-deps -v <out>:/out <svc> ...`

    Every flag verified against `docker compose --help` / `run --help`.
    """
    return [
        docker, "compose", "-p", COMPOSE_PROJECT, "run", "--rm", "-T", "--no-deps",
        "-v", f"{fwd(out_dir)}:/out", service, *inner,
    ]


def shell_quote(token: str) -> str:
    if token and re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", token):
        return token
    return '"' + token.replace('\\', '\\\\').replace('"', '\\"') + '"'


def render_shell(argv: list[str], cwd: Path, brief: Path, json_path: Path,
                 log_path: Path, env_prefix: bool, label: str | None = None) -> str:
    """The Git Bash line to copy. `label` shows the program by name, the way the
    guide writes it, instead of the absolute path this tool actually execs; the
    dry-run also prints the exact argv vector next to it."""
    display = list(argv)
    if label:
        display[0] = label
    parts = []
    if env_prefix:
        parts.append("MSYS_NO_PATHCONV=1")
    parts += [shell_quote(a) for a in display]
    line = " ".join(parts)
    return (
        f"cd {shell_quote(fwd(cwd))}\n"
        f"{line} \\\n"
        f"  < {shell_quote(fwd(brief))} \\\n"
        f"  > {shell_quote(fwd(json_path))} 2> {shell_quote(fwd(log_path))}"
    )


# --------------------------------------------------------------------------
# summary and telemetry
# --------------------------------------------------------------------------

VERDICT_PREFIXES = (
    "VERDICT", "ANSWER", "RESULT", "EDIT", "DRAFT", "TESTS", "ADVICE",
    "ROOT CAUSE", "NEXT STEP", "FINDINGS", "SUMMARY", "NOT FOUND", "REFUSED",
)


def pick_verdict_line(result_text: str) -> str:
    lines = [ln.strip() for ln in (result_text or "").splitlines() if ln.strip()]
    for line in lines:
        upper = line.upper()
        if any(upper.startswith(p) for p in VERDICT_PREFIXES):
            return line
    return lines[0] if lines else "(no result text)"


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def read_result(json_path: Path) -> dict | None:
    try:
        text = json_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        # stream-json or a partial write: take the last parseable object
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                candidate = json.loads(line)
            except ValueError:
                continue
            if isinstance(candidate, dict):
                return candidate
        return None
    return data if isinstance(data, dict) else None


def build_summary(job: dict, data: dict | None, duration_s: float,
                  returncode: int) -> list[str]:
    """At most 20 lines: the verdict, the counts, and the paths."""
    head: list[str] = []
    tail: list[str] = []

    if data is None:
        head.append(
            f"{job['type']} {job['name']}: NO RESULT JSON (exit {returncode}) - "
            "read the log"
        )
    else:
        subtype = data.get("subtype")
        head.append(
            f"{job['type']} {job['name']}: {subtype} is_error={data.get('is_error')} "
            f"turns={data.get('num_turns')}/{job['max_turns']} exit={returncode}"
        )
        head.append(pick_verdict_line(str(data.get("result") or "")))
        usage = data.get("usage") or {}
        head.append(
            "tokens: in {in_} out {out} cache_read {cr} cache_create {cc}".format(
                in_=_int(usage.get("input_tokens")),
                out=_int(usage.get("output_tokens")),
                cr=_int(usage.get("cache_read_input_tokens")),
                cc=_int(usage.get("cache_creation_input_tokens")),
            )
        )
        cost = data.get("total_cost_usd")
        cost_text = (f"${cost:.4f}" if isinstance(cost, (int, float)) else "unknown")
        head.append(
            f"cost: {cost_text}   duration: {duration_s:.1f}s   "
            f"model: {job['model']}   where: {job['where']}"
        )
        denials = data.get("permission_denials") or []
        names = sorted({d.get("tool_name") for d in denials if isinstance(d, dict)
                        and d.get("tool_name")})
        head.append(
            f"permission denials: {len(denials)}"
            + (f" ({', '.join(names)})" if names else "")
        )
        spawned = ((data.get("subagent_stats") or {}).get("spawned"))
        if spawned:
            head.append(f"WARNING: subagents spawned: {spawned} (Task should be denied)")

    tail.append(f"full JSON: {fwd(job['json_path'])}")
    tail.append(f"log:       {fwd(job['log_path'])}")
    tail.append(f"out:       {fwd(job['out_dir'])}")
    tail.append(f"telemetry: {fwd(TELEMETRY)}")

    room = SUMMARY_MAX_LINES - len(head) - len(tail)
    body: list[str] = []
    if data is not None and room > 0:
        seen = {pick_verdict_line(str(data.get("result") or ""))}
        for line in str(data.get("result") or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            body.append("  " + stripped[:160])
            seen.add(stripped)
            if len(body) >= room:
                break
    return (head + body + tail)[:SUMMARY_MAX_LINES]


def write_telemetry(job: dict, data: dict | None, duration_s: float,
                    returncode: int, account: dict | None,
                    spending: str | None = None, how: str | None = None) -> None:
    """One JSON line per job. A telemetry failure never fails the job."""
    try:
        usage = (data or {}).get("usage") or {}
        if data is None:
            status = "no-result-json"
        elif data.get("is_error"):
            status = f"error:{data.get('subtype') or 'unknown'}"
        else:
            status = str(data.get("subtype") or "unknown")
        denials = (data or {}).get("permission_denials") or []
        record = {
            "ts": _dt.datetime.now(_dt.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": job["type"],
            "name": job["name"],
            # Which account PAYS. Recorded even when the usage check was
            # skipped: it used to be null on every --background child (they all
            # pass --skip-account-check), so the rows that most needed an owner
            # had none.
            "account": (account or {}).get("account") or spending,
            "account_source": how,
            # Which account the percentages DESCRIBE. `claude -p /usage` always
            # runs on the host, so for a Docker job these figures are the host
            # CLI's, not the container account's - the row used to pair the
            # container's address with the host's numbers and say nothing.
            "usage_account": (account or {}).get("usage_account"),
            "session_pct": (account or {}).get("session_pct"),
            "week_pct": (account or {}).get("week_pct"),
            "model": job["model"],
            "where": job["where"],
            "service": job.get("service"),
            "clone": fwd(job["clone"]) if job.get("clone") else None,
            "duration_s": round(duration_s, 3),
            "tokens": {
                "input": _int(usage.get("input_tokens")),
                "output": _int(usage.get("output_tokens")),
                "cache_read": _int(usage.get("cache_read_input_tokens")),
                "cache_creation": _int(usage.get("cache_creation_input_tokens")),
            },
            "cost_usd": (data or {}).get("total_cost_usd"),
            "exit_status": status,
            "exit_code": returncode,
            "num_turns": (data or {}).get("num_turns"),
            "max_turns": job["max_turns"],
            "permission_denials": sorted(
                {d.get("tool_name") for d in denials
                 if isinstance(d, dict) and d.get("tool_name")}
            ),
            "paths": {
                "brief": fwd(job["brief"]),
                "json": fwd(job["json_path"]),
                "log": fwd(job["log_path"]),
                "out": fwd(job["out_dir"]),
            },
        }
        TELEMETRY.parent.mkdir(parents=True, exist_ok=True)
        with open(TELEMETRY, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # never fail the job over bookkeeping
        print(f"WARNING: telemetry not written ({exc.__class__.__name__}: {exc})")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_job.py",
        description="Run one Claude helper job with the verified parameters "
                    "for its type (nsc-codex-jobs-guide.md 4.3).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Docker types: " + ", ".join(DOCKER_TYPES)
               + "\nHost types:   " + ", ".join(HOST_TYPES),
    )
    parser.add_argument("type", choices=sorted(JOB_TYPES))
    parser.add_argument("--brief", required=True, help="the filled prompt file")
    parser.add_argument("--clone", help="job clone (required for Docker types)")
    parser.add_argument("--model", help="alias (haiku/sonnet/opus) or full claude-* id")
    parser.add_argument("--out", help="folder mounted at /out (default "
                                      "<claude-jobs>/<name>)")
    parser.add_argument("--name", help="job name (default: the brief's stem)")
    parser.add_argument("--max-turns", type=int, dest="max_turns")
    parser.add_argument("--agent", help="custom agent, host types only")
    parser.add_argument("--allow-bash", action="append", default=[], metavar="PROGRAM",
                        help="host types: add Bash(PROGRAM:*) to --allowedTools "
                             "(repeatable)")
    parser.add_argument("--allow-tool", action="append", default=[], metavar="RULE",
                        help="host types: add a rule verbatim to --allowedTools, "
                             "e.g. \"Bash(git -C C:/NSC/NSC/NoSafeCircle log:*)\" "
                             "(repeatable)")
    parser.add_argument("--add-dir", action="append", default=[], metavar="DIR",
                        help="host types: extra readable directory (repeatable)")
    parser.add_argument("--astra", action="store_true",
                        help="advice: use the Codex/Astra path instead of Claude")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the exact command and exit")
    parser.add_argument("--background", action="store_true",
                        help="run detached; prints the paths and returns at once")
    parser.add_argument("--host-reason", metavar="TEXT",
                        help="why this job needs the host rather than Docker "
                             "(host files, Windows tools, the PixelLab MCP, --agent)")
    parser.add_argument("--allow-account", metavar="EMAIL",
                        help="run even though the account is not "
                             f"{OUTSOURCE_ACCOUNT}; must name that account exactly")
    parser.add_argument("--skip-account-check", action="store_true",
                        help="skip `claude -p /usage` (tests, dry runs)")
    parser.add_argument("--timeout", type=int, default=0,
                        help="seconds before the job is killed (0 = no limit)")
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    return parser


def resolve_job(args) -> dict:
    cfg = JOB_TYPES[args.type]

    if args.astra:
        if not cfg.get("codex_option"):
            raise Refused(f"--astra is only for `advice`, not `{args.type}`.")
        guard_codex_available()
        raise Refused(
            "Codex is back per the guide banner, but this tool only builds Claude "
            "job commands. Run the Astra recipe from nsc-codex-jobs-guide.md 4.4 "
            "by hand, then drop --astra here."
        )

    brief = guard_brief(Path(args.brief).expanduser())
    name = args.name or re.sub(r"\.prompt$", "", brief.stem)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise Refused(
            f"job name {name!r} has characters this tool will not pass on. Use "
            "--name with letters, digits, dot, dash or underscore."
        )
    # `.` and `..` pass the character check and then walk out of the job folder:
    # `--name ..` puts the output in NSCREV itself.
    if name.strip(".") == "":
        raise Refused(
            f"job name {name!r} is a directory traversal, not a name. It would "
            f"put this job's output straight into {fwd(JOBS_DIR.parent)}."
        )

    if args.agent and cfg["where"] != "host":
        raise Refused(
            f"--agent works only for host types ({', '.join(HOST_TYPES)}); the "
            "Docker containers have no agent files mounted."
        )
    if args.allow_bash and cfg["where"] != "host":
        raise Refused(
            "--allow-bash is for host types; Docker types already allow Bash "
            "inside the container."
        )
    if args.allow_tool and cfg["where"] != "host":
        raise Refused(
            "--allow-tool is for host types; each Docker type already carries "
            "its verified tool list."
        )

    clone = guard_clone(
        Path(args.clone).expanduser() if args.clone else None,
        cfg["needs_clone"], args.type,
    )

    model = guard_model(args.model, cfg["model"])
    max_turns = args.max_turns if args.max_turns else cfg["max_turns"]
    if max_turns < 1:
        raise Refused("--max-turns must be at least 1.")

    tools = list(cfg["tools"])
    for program in args.allow_bash:
        if not re.fullmatch(r"[A-Za-z0-9._+-]+", program):
            raise Refused(
                f"--allow-bash {program!r} is not a bare program name. A "
                "Bash(<program>:*) rule matches the program name; pass e.g. "
                "`git` or `python`, not a path or a whole command line."
            )
        rule = f"Bash({program}:*)"
        if rule not in tools:
            tools.append(rule)
    for raw in args.allow_tool:
        # A single --allow-tool value can pack several rules together
        # (`"Read(a),Bash,Agent,Write,Read(b)"`), which the CLI's own comma-
        # or-space-separated parsing would later split into five. Split here
        # first, so every rule this flag contributes is validated and
        # appended on its own - all of them must pass, or none of them run.
        for rule in split_tool_rule_value(raw):
            guard_allow_tool(rule, cfg["tools"], args.type)
            rule = rule.strip()
            if rule not in tools:
                tools.append(rule)

    # Belt and braces: whatever route a rule took to get here, the final list
    # is checked once more before it can become an --allowedTools argument.
    guard_tool_list(tools, cfg["tools"], args.type)

    add_dir = list(cfg.get("add_dir") or []) if cfg["where"] == "host" else []
    for extra in args.add_dir:
        if cfg["where"] != "host":
            raise Refused("--add-dir is for host types only.")
        add_dir.append(fwd(Path(extra).expanduser()))
    add_dir = list(dict.fromkeys(add_dir))

    out_dir = guard_out(
        Path(args.out).expanduser() if args.out else JOBS_DIR / name,
        dry_run=getattr(args, "dry_run", False),
    )
    if not getattr(args, "dry_run", False):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

    return {
        "type": args.type,
        "name": name,
        "where": cfg["where"] if cfg["where"] == "host"
                 else f"docker:{cfg['service']}",
        "service": cfg["service"],
        "model": model,
        "max_turns": max_turns,
        "tools": tools,
        "add_dir": add_dir,
        "agent": args.agent,
        "brief": brief,
        "clone": clone,
        "out_dir": out_dir,
        "json_path": JOBS_DIR / f"{name}.json",
        "log_path": JOBS_DIR / f"{name}.log",
        "cwd": clone if clone else NSCREV,
        "note": cfg["note"],
    }


def assemble_argv(job: dict) -> tuple[list[str], bool]:
    """Return (argv, needs_msys_prefix)."""
    if job["service"]:
        docker = which("NSC_RUN_JOB_DOCKER", "docker")
        inner = claude_argv(job, job["model"], job["max_turns"], job["tools"],
                            None, [], "claude")
        return docker_argv(docker, job["service"], job["out_dir"], inner), True
    claude = which("NSC_RUN_JOB_CLAUDE", "claude")
    return claude_argv(job, job["model"], job["max_turns"], job["tools"],
                       job["agent"], job["add_dir"], claude), False


def run_foreground(job: dict, argv: list[str], timeout: int) -> tuple[int, float]:
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"
    started = time.time()
    with open(job["brief"], "rb") as stdin, \
            open(job["json_path"], "wb") as stdout, \
            open(job["log_path"], "wb") as stderr:
        try:
            proc = run_quiet(
                argv, stdin=stdin, stdout=stdout, stderr=stderr,
                cwd=str(job["cwd"]), env=env,
                timeout=timeout if timeout > 0 else None,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            stderr.write(f"\nrun_job.py: killed after {timeout}s\n".encode())
            code = 124
        except OSError as exc:
            stderr.write(f"\nrun_job.py: could not start the job: {exc}\n".encode())
            code = 127
    return code, time.time() - started


def spawn_background(args) -> int:
    child = [sys.executable, "-B", str(Path(__file__).resolve()), args.type,
             "--brief", str(args.brief), "--_child", "--skip-account-check"]
    for flag, value in (("--clone", args.clone), ("--model", args.model),
                        ("--out", args.out), ("--name", args.name),
                        ("--agent", args.agent),
                        # Forwarded since 2026-09-18: without these two,
                        # `--background --allow-account x` and
                        # `--background --host-reason "..."` silently never ran.
                        ("--allow-account", args.allow_account),
                        ("--host-reason", args.host_reason)):
        if value:
            child += [flag, str(value)]
    if args.max_turns:
        child += ["--max-turns", str(args.max_turns)]
    if args.timeout:
        child += ["--timeout", str(args.timeout)]
    for program in args.allow_bash:
        child += ["--allow-bash", program]
    for rule in args.allow_tool:
        child += ["--allow-tool", rule]
    for extra in args.add_dir:
        child += ["--add-dir", extra]
    # CREATE_NO_WINDOW, not DETACHED_PROCESS: the child must outlive this process
    # without ever owning a console (rule 9).
    flags = CREATE_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # The child's stderr used to go to DEVNULL, so a child that refused left no
    # json, no log and no telemetry row - the parent had already printed
    # "started in background" and exited 0. Keep it: a refusal nobody can read
    # is the same as no refusal.
    spawn_log = Path(args.out).expanduser() if args.out else JOBS_DIR / (args.name or "background")
    spawn_log.mkdir(parents=True, exist_ok=True)
    spawn_err = spawn_log / "background-stderr.log"
    handle = open(spawn_err, "ab", buffering=0)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    handle.write(f"\n=== {stamp} spawn ===\n".encode("utf-8"))
    proc = subprocess.Popen(
        child, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=handle, creationflags=flags, cwd=str(NSCREV),
    )
    print(f"started in background, pid {proc.pid}")
    print(f"if nothing appears, read {fwd(spawn_err)}")
    return proc.pid


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        job = resolve_job(args)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    try:
        if job["service"]:
            guard_compose_file(job["clone"])
            docker = which("NSC_RUN_JOB_DOCKER", "docker")
            if not args.dry_run:
                version = guard_docker_engine(docker)
                image_id = guard_docker_image(docker, job["service"])
                print(f"docker engine {version}, image "
                      f"{COMPOSE_PROJECT}-{job['service']}:latest ({image_id[:12]})")
        command, msys = assemble_argv(job)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"# {job['type']}: {job['note']}")
        print(f"# where: {job['where']}   model: {job['model']}   "
              f"max-turns: {job['max_turns']}")
        print(render_shell(command, job["cwd"], job["brief"], job["json_path"],
                           job["log_path"], msys,
                           label="docker" if job["service"] else "claude"))
        print("# in PowerShell, drop the MSYS_NO_PATHCONV=1 prefix and the "
              "backslash line breaks." if msys else
              "# in PowerShell, drop the backslash line breaks.")
        print("\nargv:")
        print(json.dumps(command, indent=2))
        return 0

    if args.background and not args._child:
        # The account guard runs HERE, in the parent, before anything is spawned.
        # It used to run after this branch, and the child was launched with
        # --skip-account-check, so `--background` was a way round the one guard
        # that decides whose tokens a job spends. The child still skips it, to
        # avoid asking twice, which is only safe because the parent just asked.
        try:
            who, how = logged_in_account(job)
            guard_account(who, how, args.allow_account)
        except Refused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        spawn_background(args)
        print(f"full JSON: {fwd(job['json_path'])}")
        print(f"log:       {fwd(job['log_path'])}")
        print(f"out:       {fwd(job['out_dir'])}")
        return 0

    # Who pays is settled before the usage percentages, and it fails closed: a job that
    # cannot say whose tokens it spends does not run. It failed closed with an uncaught
    # traceback and exit 1 until 2026-09-18; every other guard prints REFUSED: and
    # exits 2, and a caller branching on the exit code could not tell this one apart.
    try:
        who, how = logged_in_account(job)
        spending = guard_account(who, how, args.allow_account)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    printed = 0
    if job["where"] == "host":
        printed += warn_about_host_consoles(job["type"], args.host_reason)

    account: dict | None = None
    printed += 1
    if args.skip_account_check:
        print(f"account: {spending} ({how})  usage not checked")
    else:
        try:
            claude = which("NSC_RUN_JOB_CLAUDE", "claude")
            account = account_check(claude, NSCREV)
            account["account"] = spending
            # `/usage` ran on the host CLI, so say so rather than letting the
            # figures inherit the paying account's name.
            account["usage_account"] = host_account()
            printed += print_account_check(account, how, host_account()) - 1
        except Refused as exc:
            print(f"account: {spending} ({how})  usage check skipped ({exc})")
        except Exception as exc:  # a broken check never stops the job
            print(f"account: {spending} ({how})  usage check failed "
                  f"({exc.__class__.__name__}: {exc})")

    returncode, duration = run_foreground(job, command, args.timeout)
    data = read_result(job["json_path"])

    # The cap is on everything this job prints, the account line included.
    for line in build_summary(job, data, duration, returncode)[:SUMMARY_MAX_LINES - printed]:
        print(line)

    write_telemetry(job, data, duration, returncode, account, spending, how)

    if returncode != 0:
        return returncode
    if data is None:
        return 1
    return 1 if data.get("is_error") else 0


if __name__ == "__main__":
    sys.exit(main())
