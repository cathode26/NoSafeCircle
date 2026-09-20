"""Make a contract-check prompt for a follow-up revision from the previous revision's prompt.

    python -B make_followup_prompt.py <TASK> <prev_rev> <new_rev> <reason-file> [<also-changed text>]

Replaces the "- Task:" line with "- Task: <TASK>. Why it changed: <reason>" and the "- Also changed" line.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
task, prev_rev, new_rev, reason_file = sys.argv[1:5]
also = sys.argv[5] if len(sys.argv) > 5 else "none"
source = ROOT / f"codex-contract-check-{task}-rev{prev_rev}-20260917.prompt.md"
target = ROOT / f"codex-contract-check-{task}-rev{new_rev}-20260917.prompt.md"
if target.exists():
    raise SystemExit(f"exists: {target}")
lines = source.read_text(encoding="utf-8").split("\n")
task_index = next(i for i, line in enumerate(lines) if line.startswith(f"- Task: {task}."))
reason = pathlib.Path(reason_file).read_text(encoding="utf-8").strip().replace("\n", " ")
lines[task_index] = f"- Task: {task}. Why it changed: {reason}"
also_index = next((i for i, line in enumerate(lines) if line.startswith("- Also changed")), None)
if also_index is not None:
    lines[also_index] = f"- Also changed: {also}"
target.write_text("\n".join(lines), encoding="utf-8")
print(target)
