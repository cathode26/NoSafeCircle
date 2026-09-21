#!/usr/bin/env python
"""Closure review through the Claude CLI, on the host or in Docker. Tracked, and JSON.

This is the source-tracked replacement for `C:/nscrev/claude-jobs/host_closure_review.py`
and `docker_closure_review.py`, which are alternate launchers for the same review
that `codex-jobs/run_closure_review.sh` runs through Codex. **The live files are
NOT changed by this; they remain a deployment gap, recorded in the cutover
inventory.** Nothing here edits them or claims they are fixed.

Two defects in those adapters are the reason this exists.

1. **They return 0 after a provider failure.** The only non-zero exits are an
   unreadable wrapper JSON and a usage-limit phrase found in the review text. A
   run with `is_error: true`, or one whose review is empty or truncated, reported
   success - so a caller that branched on the exit status was told a review had
   happened when it had not. The provider's own status is now checked FIRST, and
   nothing about the content can rescue it.

2. **They read the verdict out of prose**, by collecting lines containing "Final
   recommendation" and printing the last one. Here the reviewer declares one JSON
   object, validated through `review_result` and bound to the exact contract
   bytes it was given, exactly as the Codex path now does.

The two adapters differed only in the command they ran; everything else was
duplicated between them, including both defects. `--runner host|docker` selects
the command and the rest is shared, because two copies of this were how one fix
reached only one of them.

`interpret()` is separate from the launching so it can be tested without a
provider: every rule that decides whether a review happened lives there, and the
tests drive it with captured wrapper JSON rather than by spending a call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import closure_record  # noqa: E402
import nsc_paths  # noqa: E402
import review_result  # noqa: E402

FLAGS = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

GMAIL = "cathode26@gmail.com"

# Exit codes, matching run_closure_review.sh so a caller can branch the same way
# whichever launcher produced the review.
OK = 0
SETUP_REFUSED = 2
PROVIDER_FAILED = 4
EMPTY_RESULT = 6
NOT_ACTIONABLE = 7
USAGE_LIMIT = 3


def interpret(wrapper: bytes, *, task_id: str, contract: bytes,
              process_code: int = 0) -> tuple[int, str, object | None]:
    """Did a review happen, and what did it declare? (exit code, message, result).

    The order is the whole point. Process status, then emptiness, then the
    protocol - so a well-formed result can never excuse a failed run, and a
    failed run is never read for content.

    `process_code` is the CLI's own exit status, and it is checked first. Astra
    MJ-P3-01: main() captured it and used it only in the printed message, so a
    run that exited 9 with an otherwise valid wrapper returned 0 and published -
    printing "cli exit 9, closure review complete: commit_contract". The
    is_error field inside the wrapper cannot cover that, because a process that
    died may not have written an honest wrapper at all.
    """
    if process_code != 0:
        return (PROVIDER_FAILED,
                f"the CLI exited {process_code}; nothing it wrote is trustworthy",
                None)
    try:
        data = json.loads(wrapper.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        return SETUP_REFUSED, f"the CLI wrapper output is unreadable: {error}", None
    if not isinstance(data, dict):
        return SETUP_REFUSED, "the CLI wrapper output is not an object", None

    # 1. The provider's own account of the run. Nothing below can override it.
    if data.get("is_error"):
        return (PROVIDER_FAILED,
                f"the provider reported is_error (subtype {data.get('subtype')!r}); "
                f"no review was produced", None)

    raw = data.get("result")
    if not isinstance(raw, str) or not raw.strip():
        return EMPTY_RESULT, "the provider returned an empty result", None

    # 2. A usage limit is a transport refusal, not a review. Checked before the
    #    protocol so it is reported as itself rather than as malformed JSON.
    lowered = raw.lower()
    if "usage limit" in lowered or "rate limit" in lowered:
        if not raw.lstrip().startswith("{"):
            return (USAGE_LIMIT,
                    "the job reported a usage or rate limit: stop jobs and tell Vincent",
                    None)

    # 3. The protocol. Bound to the exact contract the reviewer was given.
    try:
        result = review_result.load(
            raw.encode("utf-8"),
            task_id=task_id,
            review_kind="closure",
            reviewed_artifact_kind="contract",
            reviewed_artifact_sha256=hashlib.sha256(contract).hexdigest())
    except review_result.ReviewResultError as error:
        return NOT_ACTIONABLE, f"{error.code}: {error.message}", None

    if not result.is_complete:
        return (NOT_ACTIONABLE,
                "the reviewer declared the review incomplete; there is no verdict", result)
    return OK, f"closure review complete: {result.recommendation}", result


def render(result) -> str:
    """The human view, derived and labelled. Never a decision source."""
    return "\n".join([
        review_result.DERIVED_VIEW_HEADER,
        "",
        f"# Closure review - {result.task_id}",
        "",
        f"- Review status: {result.review_status}",
        f"- Recommendation: {result.recommendation}",
        f"- Reviewed contract sha256: {result.reviewed_artifact_sha256}",
        "",
        "---",
        "",
        result.report_markdown.rstrip(),
        "",
    ])


def require_gmail_account(claude_exe: str) -> None:
    """Spend the Gmail account first: the host CLI's login has been the desktop one before."""
    if os.environ.get("ALLOW_ANY_CLAUDE_ACCOUNT") == "1":
        return
    status = subprocess.run([claude_exe, "auth", "status", "--text"], capture_output=True,
                            text=True, errors="replace", **FLAGS).stdout or ""
    if GMAIL not in status:
        raise SystemExit(f"the host claude CLI is not signed in to {GMAIL}; refusing to "
                         "spend the desktop account. Switch the CLI account, or set "
                         "ALLOW_ANY_CLAUDE_ACCOUNT=1 deliberately.\n" + status.strip()[:300])


def build_clone(repo: pathlib.Path, clone: pathlib.Path, task: str, commit: str,
                previous: str, extras: list[str]) -> None:
    """The review directory: the repo before the revision, plus the contracts."""
    if clone.exists():
        raise SystemExit(f"clone exists: {clone}")

    def git(*args: str) -> bytes:
        return subprocess.run(["git", *args], capture_output=True, check=True, **FLAGS).stdout

    subprocess.run(["git", "clone", "-q", "-c", "core.autocrlf=true", "-c",
                    "core.filemode=false", "-c", "core.longpaths=true",
                    str(repo), str(clone)], check=True, **FLAGS)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", "--detach", f"{commit}^"],
                   check=True, **FLAGS)
    (clone / "REVISED_CONTRACT.json").write_bytes(
        git("-C", str(repo), "show", f"{commit}:Tasks/{task}.yaml"))
    (clone / "PREVIOUS_CONTRACT.json").write_bytes(
        git("-C", str(repo), "show", f"{previous}:Tasks/{task}.yaml"))
    for extra in extras:
        (clone / f"REVISED_{pathlib.PurePosixPath(extra).name}").write_bytes(
            git("-C", str(repo), "show", f"{commit}:{extra}"))


def review_root(runner: str, clone: pathlib.Path) -> str:
    """The review directory AS THE REVIEWER SEES IT.

    Astra MJ-P3-02, and the reason consolidating two files needs care: they
    differed by more than the command. Docker mounts the clone at `/workspace`,
    so the container must be given container paths; the host CLI runs beside the
    clone and must be given host paths. My first version replaced `/workspace`
    with the host clone path for BOTH, handing the container
    `C:/nscrev/cj-JOB/REVISED_CONTRACT.json`, which is not a path it has.
    """
    return "/workspace" if runner == "docker" else str(clone).replace("\\", "/")


def localise_prompt(text: str, clone: pathlib.Path, max_turns: str, runner: str) -> str:
    """Copy the files the prompt names into the clone and point it at them."""
    root = review_root(runner, clone)
    inputs = clone / "_review_inputs"
    inputs.mkdir(exist_ok=True)
    for raw in sorted(set(re.findall(r"C:[/\\]nscrev[/\\][^\s;,)`'\"]+", text))):
        source = pathlib.Path(raw.rstrip("."))
        if source.is_file():
            shutil.copyfile(source, inputs / source.name)
            text = text.replace(raw.rstrip("."), f"{root}/_review_inputs/{source.name}")
    # A no-op for Docker, where root IS /workspace; the rewrite exists for the
    # host run, whose review directory is the clone's real path.
    text = text.replace("/workspace", root)

    if runner == "docker":
        where = ("You run in Docker with /workspace mounted read-only: it is a clone of "
                 "the repository at the commit before the revision, plus "
                 "REVISED_CONTRACT.json, PREVIOUS_CONTRACT.json and _review_inputs/. If "
                 "git refuses to run, first run `git config --global --add safe.directory "
                 "/workspace`. Treat everything as read-only: never edit, commit, push or "
                 "run any paid tool, and never touch anything outside /workspace.")
    else:
        where = (f"You review a contract revision on this machine. The review directory is "
                 f"{root}: a clone of the repository at the commit before the revision, plus "
                 "REVISED_CONTRACT.json, PREVIOUS_CONTRACT.json and _review_inputs/. Every "
                 "path in this prompt is absolute; your own working directory is elsewhere, "
                 "so address files by those absolute paths and run git as "
                 f"`git -C {root} ...`. Treat everything as read-only: never edit, commit, "
                 "push or run any paid tool, and never touch anything outside that review "
                 "directory.")

    return (
        where + "\n\n"
        f"You have at most {max_turns} turns. Work efficiently: diff the contracts first, "
        "use `grep -n` with context instead of reading large files whole, decide each "
        "ledger item and changed requirement once, and stop exploring early enough to "
        "always write the required final message.\n\n" + text)


READ_ONLY_BASH = ["Bash(git:*)", "Bash(grep:*)", "Bash(rg:*)", "Bash(sed:*)", "Bash(ls:*)",
                  "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)",
                  "Bash(diff:*)", "Bash(sort:*)", "Bash(uniq:*)", "Bash(cut:*)", "Bash(awk:*)",
                  "Bash(python3:*)", "Bash(python:*)", "Bash(sha256sum:*)", "Bash(cd:*)",
                  "Bash(pwd)", "Bash(jq:*)"]


def command(runner: str, model: str, max_turns: str, clone: pathlib.Path,
            host_cwd: pathlib.Path | None = None) -> tuple[list[str], pathlib.Path]:
    """The command each runner needs, and the directory it runs in."""
    if runner == "host":
        exe = shutil.which("claude") or r"C:\Users\VincentLiguori\.local\bin\claude.exe"
        require_gmail_account(exe)
        # Astra MJ-P3-04: this was hardcoded to C:/NSC even when --repo, --jobs
        # and --work all pointed somewhere else, so a fresh install on another
        # drive ran the CLI in a directory belonging to this machine. The
        # workspace is derived by the shared resolver, which is what deploying
        # the tools elsewhere is supposed to move.
        return ([exe, "-p", "--model", model, "--max-turns", max_turns,
                 "--permission-mode", "dontAsk", "--allowedTools", "Read", "Glob", "Grep",
                 *READ_ONLY_BASH, "--output-format", "json"],
                host_cwd or nsc_paths.workspace().path)
    return (["docker", "compose", "-p", "nosafecircle", "run", "--rm", "-T", "--no-deps",
             "claude-exec", "claude", "-p", "--model", model, "--max-turns", max_turns,
             "--permission-mode", "dontAsk", "--allowedTools", "Read", "Glob", "Grep",
             "Bash", "--output-format", "json"],
            clone)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runner", choices=("host", "docker"), required=True)
    ap.add_argument("--job", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--previous", required=True)
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--repo", type=pathlib.Path, default=pathlib.Path(r"C:\NSC\NSC\NoSafeCircle"))
    ap.add_argument("--jobs", type=pathlib.Path, default=pathlib.Path(r"C:\nscrev\codex-jobs"))
    ap.add_argument("--work", type=pathlib.Path, default=pathlib.Path(r"C:\nscrev\claude-jobs"))
    ap.add_argument("--host-cwd", type=pathlib.Path, default=None,
                    help="working directory for the host CLI; defaults to the workspace "
                         "the shared resolver derives, never a spelled-out machine path")
    args = ap.parse_args(argv)

    prompt_path = args.jobs / f"{args.job}.prompt.md"
    if not prompt_path.is_file():
        print(f"missing prompt {prompt_path}", file=sys.stderr)
        return SETUP_REFUSED
    clone = args.work.parent / f"cj-{args.job}"
    build_clone(args.repo, clone, args.task, args.commit, args.previous, args.extra)

    max_turns = os.environ.get("MAX_TURNS", "60")
    model = os.environ.get("MODEL", "claude-sonnet-5")
    text = localise_prompt(prompt_path.read_text(encoding="utf-8"), clone, max_turns,
                           args.runner)
    prompt_file = args.work / f"{args.job}.{args.runner}-prompt.md"
    prompt_file.write_text(text, encoding="utf-8")

    started_at = time.time()
    wrapper_path = args.work / f"{args.job}.{args.runner}.json"
    cmd, cwd = command(args.runner, model, max_turns, clone, args.host_cwd)
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    with open(prompt_file, "rb") as stdin, open(wrapper_path, "wb") as stdout, \
            open(args.work / f"{args.job}.{args.runner}.log", "wb") as stderr:
        code = subprocess.run(cmd, cwd=str(cwd), stdin=stdin, stdout=stdout,
                              stderr=stderr, env=env, **FLAGS).returncode

    contract = (clone / "REVISED_CONTRACT.json").read_bytes()
    status, message, result = interpret(wrapper_path.read_bytes(),
                                        task_id=args.task, contract=contract,
                                        process_code=code)
    print(f"[DONE] {args.job}: cli exit {code}, {message}")
    if status != OK:
        return status

    # The raw result is the record; the rendered view is written only now, after
    # it has validated, and is labelled so no reader treats it as a review. The
    # raw bytes are preserved exactly, BOM included - the reader hashes them.
    raw_result = json.loads(wrapper_path.read_text(encoding="utf-8"))["result"].encode("utf-8")
    result_path = args.jobs / f"{args.job}.result.json"
    result_path.write_bytes(raw_result)
    view = render(result)
    (args.jobs / f"{args.job}.report.md").write_text(view, encoding="utf-8")

    # The job record LAST, after every check and after both files exist. A crash
    # before this leaves no record, and a reader that finds none treats the job
    # as unfinished - which is the safe direction.
    closure_record.publish(result_path, closure_record.build(
        task_id=args.task,
        provider=f"claude-{args.runner}",
        reviewed_artifact_sha256=hashlib.sha256(contract).hexdigest(),
        result_bytes=raw_result,
        view_bytes=(args.jobs / f"{args.job}.report.md").read_bytes(),
        exit_code=code,
        # Claude's wrapper carries this explicitly; a missing field is NOT
        # defaulted to success, which is why interpret refuses it above.
        is_error=False,
        started_at=started_at,
        completed_at=time.time(),
        review_status=result.review_status,
        session_id=json.loads(wrapper_path.read_text(encoding="utf-8")).get("session_id")))
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
