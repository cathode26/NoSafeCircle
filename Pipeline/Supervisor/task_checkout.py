from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TASK_ID_RE = re.compile(r"^NSC-\d{3,}$")
NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
DEFAULT_REMOTE = "https://github.com/cathode26/NoSafeCircle.git"


class OrchestrationError(RuntimeError):
    pass


def _run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise OrchestrationError(
            f"Command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    return _run(["git", *args], cwd=cwd, check=check).stdout.strip()


def _repo_root(source: Path) -> Path:
    source = source.resolve()
    root = _git(source, "rev-parse", "--show-toplevel")
    return Path(root).resolve()


def _validate_task_id(raw: str) -> str:
    task_id = raw.strip().upper()
    if not TASK_ID_RE.fullmatch(task_id):
        raise OrchestrationError(f"Invalid task ID: {raw!r}")
    return task_id


def _load_json_text(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OrchestrationError(f"{label} is not valid JSON-subset task data: {exc}") from exc
    if not isinstance(value, dict):
        raise OrchestrationError(f"{label} must contain one JSON object.")
    return value


def _remote_task(repo: Path, task_id: str) -> dict[str, Any]:
    raw = _git(repo, "show", f"origin/main:Tasks/{task_id}.yaml")
    task = _load_json_text(raw, f"Tasks/{task_id}.yaml at origin/main")
    if task.get("id") != task_id:
        raise OrchestrationError(f"Task file identity mismatch for {task_id}.")
    return task


def _assert_task_checkout_eligible(task: dict[str, Any]) -> None:
    failures = []
    if task.get("contract_disposition") != "active":
        failures.append(f"contract_disposition={task.get('contract_disposition')!r}")
    if task.get("kind") != "implementation":
        failures.append(f"kind={task.get('kind')!r}")
    if task.get("execution_scope") != "single_agent":
        failures.append(f"execution_scope={task.get('execution_scope')!r}")
    if task.get("decomposition_state") != "concrete":
        failures.append(f"decomposition_state={task.get('decomposition_state')!r}")
    if failures:
        raise OrchestrationError(
            "Task is not eligible for the bounded implementation checkout MVP: "
            + ", ".join(failures)
        )


def _slug(value: str) -> str:
    slug = NON_SLUG_RE.sub("-", value.casefold()).strip("-")
    return slug or "task"


def _default_checkout_path(repo: Path, task_id: str) -> Path:
    return repo.parent / f"NoSafeCircle-{task_id.replace('-', '')}"


def _default_branch(task_id: str, title: str) -> str:
    return f"{task_id.casefold()}-{_slug(title)}"


def _downloads_output(task_id: str) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return (
        Path.home()
        / "Downloads"
        / "NoSafeCircleOutput"
        / "TicketOrchestration"
        / task_id
        / timestamp
    )


def _entry_lines(entries: Any, id_field: str) -> list[str]:
    if not isinstance(entries, list) or not entries:
        return ["- None."]
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get(id_field) or "").strip()
        reference = str(entry.get("reference") or "").strip()
        requirement = str(entry.get("requirement") or "").strip()
        prefix = f"**{entry_id}** — " if entry_id else ""
        suffix = f" _(Reference: {reference})_" if reference else ""
        lines.append(f"- {prefix}{requirement}{suffix}")
    return lines or ["- None."]


def render_issue_body(task: dict[str, Any]) -> str:
    task_id = str(task["id"])
    title = str(task.get("title") or "")
    dependencies = task.get("depends_on") or []
    resources = task.get("exclusive_resources") or []
    evidence = task.get("gdd_evidence") or []

    parts = [
        f"<!-- no-safe-circle-task: {task_id} -->",
        f"# {task_id} — {title}",
        "",
        "## What this task accomplishes",
        str(task.get("execution_reason") or "No execution reason recorded."),
        "",
        "## Why this is a bounded task",
        str(task.get("decomposition_reason") or "No decomposition reason recorded."),
        "",
        "## Dependencies",
    ]
    parts.extend([f"- `{item}`" for item in dependencies] or ["- None."])

    parts += ["", "## Acceptance criteria"]
    parts.extend(_entry_lines(task.get("acceptance_criteria"), "criterion_id"))

    parts += ["", "## Completion / validation gates"]
    parts.extend(_entry_lines(task.get("completion_gates"), "gate_id"))

    parts += ["", "## Downstream integration obligations"]
    parts.extend(
        _entry_lines(task.get("downstream_integration_obligations"), "obligation_id")
    )

    parts += ["", "## Exclusive resources"]
    parts.extend([f"- `{item}`" for item in resources] or ["- None."])

    parts += ["", "## Canon / design evidence"]
    if evidence:
        for entry in evidence:
            if not isinstance(entry, dict):
                continue
            reference = str(entry.get("reference") or "").strip()
            requirement = str(entry.get("requirement") or "").strip()
            parts.append(f"- **{reference}** — {requirement}")
    else:
        parts.append("- None recorded.")

    parts += [
        "",
        "## TaskGraph authority",
        f"- Contract: `Tasks/{task_id}.yaml`",
        f"- Contract revision: `{task.get('contract_revision')}`",
        f"- Reconciliation key: `{task.get('reconciliation_key')}`",
        "",
        "## Operational convention",
        "- The TaskGraph contract above remains the durable definition of work.",
        "- This GitHub Issue is operational coordination only.",
        "- **Open + unassigned** = available.",
        "- **Open + assigned** = claimed / being worked.",
        "- **Closed** = orchestration finished; current conformance must still be read from TaskGraph evidence.",
        "",
        "Before implementation begins, the claiming orchestrator should add a **Claim / Planned Approach** comment.",
        "At the end, it should add the required structured **Closeout Report** and then close this Issue.",
        "",
    ]
    return "\n".join(parts)


def render_claim_comment(
    *,
    task: dict[str, Any],
    worker_id: str,
    base_commit: str,
    branch: str,
    checkout_path: Path,
) -> str:
    return "\n".join(
        [
            "## Claim / Planned Approach",
            "",
            f"- **Worker:** `{worker_id}`",
            f"- **Task:** `{task['id']} — {task.get('title', '')}`",
            f"- **Base `origin/main`:** `{base_commit}`",
            f"- **Branch:** `{branch}`",
            f"- **Checkout:** `{checkout_path}`",
            "",
            "### Planned approach",
            "<!-- REQUIRED: The orchestrator must replace this with a concrete description of how it intends to accomplish the task before implementation begins. -->",
            "",
            "### Expected validation",
            "<!-- REQUIRED: Describe the tests/runtime/human checks expected for this task. -->",
            "",
            "### Assumptions / risks",
            "None identified at claim time.",
            "",
        ]
    )


def _write_handoff(
    *,
    task: dict[str, Any],
    worker_id: str,
    base_commit: str,
    branch: str,
    checkout_path: Path,
) -> Path:
    output = _downloads_output(str(task["id"]))
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema_version": "1.0",
        "task_id": task["id"],
        "title": task.get("title"),
        "worker_id": worker_id,
        "base_main_commit": base_commit,
        "branch": branch,
        "checkout_path": str(checkout_path),
        "task_contract_path": f"Tasks/{task['id']}.yaml",
        "task_contract_revision": task.get("contract_revision"),
    }
    (output / "claim.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output / "issue-body.md").write_text(
        render_issue_body(task), encoding="utf-8", newline="\n"
    )
    (output / "claim-comment.md").write_text(
        render_claim_comment(
            task=task,
            worker_id=worker_id,
            base_commit=base_commit,
            branch=branch,
            checkout_path=checkout_path,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return output


def command_checkout(args: argparse.Namespace) -> int:
    task_id = _validate_task_id(args.task_id)
    source = _repo_root(Path(args.source))

    status = _git(source, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise OrchestrationError(
            "Source checkout is dirty. Use a clean repository before creating a task checkout."
        )

    _git(source, "fetch", "origin", "main")
    remote_url = args.remote or _git(source, "remote", "get-url", "origin")
    base_commit = _git(source, "rev-parse", "origin/main")

    task = _remote_task(source, task_id)
    _assert_task_checkout_eligible(task)

    checkout = (
        Path(args.checkout).resolve()
        if args.checkout
        else _default_checkout_path(source, task_id)
    )
    if checkout.exists():
        raise OrchestrationError(f"Checkout path already exists: {checkout}")

    branch = args.branch or _default_branch(task_id, str(task.get("title") or "task"))

    _run(["git", "clone", remote_url, str(checkout)], cwd=source.parent, capture=False)
    clone_head = _git(checkout, "rev-parse", "HEAD")
    if clone_head != base_commit:
        raise OrchestrationError(
            "Remote main moved while cloning. "
            f"Preflight main={base_commit}, cloned HEAD={clone_head}. "
            "Delete this new checkout after inspection and retry from current main."
        )

    _git(checkout, "switch", "-c", branch)
    validate = _run(
        [sys.executable, "Pipeline/TaskGraph/taskcontrol.py", "validate"],
        cwd=checkout,
    )
    if "taskcontrol validate: PASS" not in validate.stdout:
        raise OrchestrationError(
            "TaskGraph validation did not report PASS in the new checkout."
        )

    final_status = _git(checkout, "status", "--porcelain", "--untracked-files=all")
    if final_status:
        raise OrchestrationError("New task checkout is unexpectedly dirty.")

    output = _write_handoff(
        task=task,
        worker_id=args.worker_id,
        base_commit=base_commit,
        branch=branch,
        checkout_path=checkout,
    )

    print("TASK CHECKOUT: READY")
    print(f"task_id:       {task_id}")
    print(f"title:         {task.get('title')}")
    print(f"base_main:     {base_commit}")
    print(f"branch:        {branch}")
    print(f"checkout:      {checkout}")
    print(f"handoff:       {output}")
    print(f"issue_body:    {output / 'issue-body.md'}")
    print(f"claim_comment: {output / 'claim-comment.md'}")
    return 0


def _git_lines(repo: Path, *args: str) -> list[str]:
    text = _git(repo, *args)
    return [line for line in text.splitlines() if line.strip()]


def _closeout_template(
    *,
    task: dict[str, Any],
    worker_id: str,
    branch: str,
    head: str,
    comparison_base: str,
    commits: list[str],
    files: list[str],
    stat: str,
) -> str:
    commit_lines = [f"- `{line}`" for line in commits] or ["- No commits found in comparison range."]
    file_lines = [f"- `{line}`" for line in files] or ["- No changed files found in comparison range."]
    return "\n".join(
        [
            "## Closeout Report",
            "",
            f"- **Task:** `{task['id']} — {task.get('title', '')}`",
            f"- **Worker:** `{worker_id}`",
            f"- **Branch:** `{branch}`",
            f"- **Reported HEAD:** `{head}`",
            f"- **Comparison base:** `{comparison_base}`",
            "",
            "### Outcome",
            "<!-- REQUIRED: State what outcome was achieved in plain language. -->",
            "",
            "### What I changed",
            "<!-- REQUIRED: Describe the implemented behavior/content, not just filenames. -->",
            "",
            "### How I accomplished the task",
            "<!-- REQUIRED: Explain the implementation approach and important technical/content steps. -->",
            "",
            "### Decisions and choices I made",
            "<!-- REQUIRED: List choices made within implementation freedom. If none, write 'None.' -->",
            "",
            "### Missing or underspecified items I encountered",
            "<!-- REQUIRED: Explain anything the task/canon did not specify clearly. If none, write 'None.' -->",
            "",
            "### Additions beyond the original task",
            "<!-- REQUIRED: List anything added because it was needed to make the task work, and why. If none, write 'None.' -->",
            "",
            "### Validation performed",
            "<!-- REQUIRED: Record tests, Unity/runtime checks, human checks, and their results. -->",
            "",
            "### Remaining follow-ups / risks",
            "<!-- REQUIRED: List remaining work or risks. If none, write 'None.' -->",
            "",
            "### Commits in this task comparison",
            *commit_lines,
            "",
            "### Changed files in this task comparison",
            *file_lines,
            "",
            "### Diff stat",
            "```text",
            stat or "(no diff stat)",
            "```",
            "",
            "### TaskGraph closeout state",
            "<!-- REQUIRED AT FINAL CLOSE: Record the final `taskcontrol state <TASK-ID> --json` result observed after authoritative delivery/merge. Closing the Issue is operational only and must not invent conformance. -->",
            "",
        ]
    )


def command_draft_closeout(args: argparse.Namespace) -> int:
    task_id = _validate_task_id(args.task_id)
    repo = _repo_root(Path(args.checkout or "."))

    task_path = repo / "Tasks" / f"{task_id}.yaml"
    if not task_path.is_file():
        raise OrchestrationError(f"Task contract missing in checkout: {task_path}")
    task = _load_json_text(task_path.read_text(encoding="utf-8-sig"), str(task_path))

    _git(repo, "fetch", "origin", "main")
    branch = _git(repo, "branch", "--show-current")
    head = _git(repo, "rev-parse", "HEAD")
    base = _git(repo, "merge-base", "origin/main", "HEAD")
    commits = _git_lines(repo, "log", "--oneline", "--no-merges", f"{base}..HEAD")
    files = _git_lines(repo, "diff", "--name-status", f"{base}...HEAD")
    stat = _git(repo, "diff", "--stat", f"{base}...HEAD")

    output = _downloads_output(task_id)
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / "closeout-report.md"
    report_path.write_text(
        _closeout_template(
            task=task,
            worker_id=args.worker_id,
            branch=branch,
            head=head,
            comparison_base=base,
            commits=commits,
            files=files,
            stat=stat,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print("CLOSEOUT DRAFT: READY")
    print(f"task_id: {task_id}")
    print(f"report:  {report_path}")
    print("Fill every REQUIRED section before posting it to GitHub and closing the Issue.")
    return 0


def command_show(args: argparse.Namespace) -> int:
    task_id = _validate_task_id(args.task_id)
    repo = _repo_root(Path(args.source))
    _git(repo, "fetch", "origin", "main")
    task = _remote_task(repo, task_id)

    print(f"{task_id} — {task.get('title', '')}")
    print(f"contract_revision: {task.get('contract_revision')}")
    print(f"kind:              {task.get('kind')}")
    print(f"execution_scope:   {task.get('execution_scope')}")
    print(f"decomposition:     {task.get('decomposition_state')}")
    print(f"depends_on:        {', '.join(task.get('depends_on') or []) or '(none)'}")
    print("")
    print("What this task accomplishes:")
    print(f"  {task.get('execution_reason') or '(not recorded)'}")
    print("")
    print("Acceptance criteria:")
    for line in _entry_lines(task.get("acceptance_criteria"), "criterion_id"):
        print(f"  {line}")
    print("")
    print("Completion gates:")
    for line in _entry_lines(task.get("completion_gates"), "gate_id"):
        print(f"  {line}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Small human-directed GitHub-ticket orchestration helper for No Safe Circle."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    checkout = sub.add_parser(
        "checkout",
        help="Create an isolated GitHub-remote clone and task branch from current origin/main.",
    )
    checkout.add_argument("task_id")
    checkout.add_argument("--worker-id", required=True)
    checkout.add_argument("--source", default=".")
    checkout.add_argument("--checkout")
    checkout.add_argument("--branch")
    checkout.add_argument("--remote")
    checkout.set_defaults(func=command_checkout)

    closeout = sub.add_parser(
        "draft-closeout",
        help="Generate a structured closeout report outside the repository.",
    )
    closeout.add_argument("task_id")
    closeout.add_argument("--worker-id", required=True)
    closeout.add_argument("--checkout", default=".")
    closeout.set_defaults(func=command_draft_closeout)

    show = sub.add_parser("show", help="Print human-readable task details from origin/main.")
    show.add_argument("task_id")
    show.add_argument("--source", default=".")
    show.set_defaults(func=command_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OrchestrationError, OSError) as exc:
        print(f"TASK ORCHESTRATION: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
