"""Fill templates/contract-closure-review-prompt.md for one revision.

    python -B make_closure_prompt.py <job> <TASK> <reason-file> <decisions-text> <report-path|none> [<older report> ...]

The ledger lists every [blocking] and [major] finding line from the given previous reports (newest first).

The prompt is written to the WORK ROOT's codex-jobs directory, which is where
`run_closure_review.sh` looks for it. It used to be written beside this script,
so the two agreed only when the tools were deployed inside the work root - and
the launcher requires `jobs/` as its own sibling, which the work root has not
got. Fable, 2026-09-21: every deployment that satisfied one of those broke the
other, and the launcher exits 2 either way. The templates stay beside the script,
because they are part of the tool; the output belongs to the job.
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import nsc_paths  # noqa: E402

ROOT = HERE
OUT = nsc_paths.work().path / "codex-jobs"
job, task, reason_file, decisions = sys.argv[1:5]
reports = [r for r in sys.argv[5:] if r.lower() != "none"]
template = (ROOT / "templates" / "contract-closure-review-prompt.md").read_text(encoding="utf-8")
ledger = []
for report in reports:
    text = pathlib.Path(report).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        match = re.match(r"\s*-\s*\[(blocking|major)\]\s*(.+)", line)
        if match:
            summary = re.sub(r"\s+", " ", match.group(2)).strip()
            ledger.append(f"L{len(ledger) + 1} [{match.group(1)}] {summary[:420]}{'...' if len(summary) > 420 else ''} (from {pathlib.Path(report).name})")
body = (template
        .replace("<TASK_ID>", task)
        .replace("<PREVIOUS_SHA>", "the commit named in the job's first log line")
        .replace("<ONE_PARAGRAPH_REASON>", pathlib.Path(reason_file).read_text(encoding="utf-8").strip().replace("\n", " "))
        .replace("<REPORT_PATHS>", ", ".join(reports) if reports else "none (first check of this contract)")
        .replace("<DECISION_FILES_OR_NONE>", decisions)
        .replace("<LEDGER: one line each, \"L1 [blocking|major] <field>: <finding summary>\">",
                 "\n".join(ledger) if ledger else "none (first check of this contract; review the whole contract once, with the same task-local versus downstream-debt discipline)"))
OUT.mkdir(parents=True, exist_ok=True)
prompt = OUT / f"{job}.prompt.md"
prompt.write_text(body, encoding="utf-8")
print(f"{job}: {len(ledger)} ledger items -> {prompt}")
