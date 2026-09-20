"""Apply the full-cycle GER runbook update to canonical main as one exact-path commit.

Checks: tracked tree clean before editing, exact README anchors, required runbook
content, git diff --check, exact staged path set, commit identity and parent.
Never pushes.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
DRAFT = pathlib.Path(r"C:\nscrev\ger-tools\GER_AGENT_RUNBOOK.draft.md")
RUNBOOK = "Pipeline/TaskDesignGER/GER_AGENT_RUNBOOK.md"
README = "Pipeline/TaskDesignGER/README.md"
PATHS = [RUNBOOK, README]
IDENTITY = ["-c", "user.name=No Safe Circle Task Design GER",
            "-c", "user.email=task-design-ger@nosafecircle.invalid"]
MESSAGE = """TaskDesignGER: run GER through contract edits, decomposition and release

Vincent directed that Task Design GER carry each held node through to an
improved executable task contract committed on main and any needed D1B.2
decomposition, instead of stopping at a review-only brief. The runbook now has
the GER owner commit the audited contract edit, apply reviewed decomposition
plans through the supported graph path, and release executable work with the
viewer finish marker. It keeps the four immutable mixed-provider rounds, the
journal hold as the dispatch authority, and the rules never to push or to claim
approval or test results that did not happen. The README's packet description
now points to that cycle instead of requiring a separate acceptance step.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
"""

README_EDITS = [
    ("followed by one bounded refinement and a fresh re-audit by that\nevaluator.",
     "followed by one bounded refinement and a fresh re-audit in a new evaluator\nconversation."),
    ("It remains review-only and produces no graph delta or apply mode.",
     "The packet itself produces no graph delta or apply mode; the runbook's GER\nowner turns the audited result into contract edits and any needed decomposition."),
    ("An\nagent performs the creative GER passes using the packet; a separate graph edit\ncan follow only after Vincent accepts the proposed content.",
     "The\nGER owner performs the creative GER passes using the packet, then commits the\naudited task-contract edit and applies any needed decomposition as described in\nthe runbook; only genuine game-design decisions and exact-plan authorizations go\nto Vincent."),
]

REQUIRED_RUNBOOK_TEXT = [
    "01-codex-generate/", "02-claude-evaluate/", "03-codex-refine/", "04-claude-reaudit/",
    "`crew_sized`", "`needs_execution_decomposition`", "`needs_design`",
    "ger_viewer_marker start", "ger_viewer_marker pause", "ger_viewer_marker finish",
    "## Contract edit, decomposition, and release", "## Paste-ready agent prompt",
    "taskcontrol.py validate", ".invalid",
]


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def main() -> int:
    tracked_dirty = git("status", "--porcelain=v1", "--untracked-files=no").strip()
    if tracked_dirty:
        raise SystemExit(f"REFUSED: tracked changes present before edit:\n{tracked_dirty}")
    head_before = git("rev-parse", "HEAD").strip()
    branch = git("branch", "--show-current").strip()
    if branch != "main":
        raise SystemExit(f"REFUSED: canonical checkout is on {branch}, not main")

    draft = DRAFT.read_text(encoding="utf-8").replace("\r\n", "\n")
    missing = [text for text in REQUIRED_RUNBOOK_TEXT if text not in draft]
    if missing:
        raise SystemExit(f"REFUSED: draft missing required text: {missing}")

    readme_path = REPO / README
    readme = readme_path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for old, new in README_EDITS:
        count = readme.count(old)
        if count != 1:
            raise SystemExit(f"REFUSED: README anchor count {count} for: {old[:60]!r}")
        readme = readme.replace(old, new)

    (REPO / RUNBOOK).write_bytes(draft.rstrip("\n").encode("utf-8") + b"\n")
    readme_path.write_bytes(readme.rstrip("\n").encode("utf-8") + b"\n")

    changed = sorted(line for line in git("diff", "--name-only").splitlines() if line)
    if changed != sorted(PATHS):
        raise SystemExit(f"STOP: unexpected changed path set {changed}; files were written, inspect before retry")
    check = subprocess.run(["git", "-C", str(REPO), "diff", "--check"], capture_output=True, text=True)
    if check.returncode != 0:
        raise SystemExit(f"STOP: git diff --check failed:\n{check.stdout}")

    git("add", "--", *PATHS)
    staged = sorted(line for line in git("diff", "--cached", "--name-only").splitlines() if line)
    if staged != sorted(PATHS):
        raise SystemExit(f"STOP: unexpected staged path set {staged}")
    message_path = pathlib.Path(r"C:\nscrev\ger-tools\runbook_commit_message.txt")
    message_path.write_text(MESSAGE, encoding="utf-8")
    git(*IDENTITY, "commit", "-F", str(message_path))

    head_after = git("rev-parse", "HEAD").strip()
    parent = git("rev-parse", "HEAD^").strip()
    files = sorted(line for line in git("show", "--name-only", "--format=", "HEAD").splitlines() if line)
    author = git("log", "-1", "--format=%an <%ae> | %cn <%ce>").strip()
    print(f"[DONE] commit {head_after}")
    print(f"[STATE] parent {parent} (HEAD before edit {head_before}; moved={parent != head_before})")
    print(f"[STATE] files {files}")
    print(f"[STATE] identity {author}")
    print(f"[STATE] tracked tree clean: {not git('status', '--porcelain=v1', '--untracked-files=no').strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
