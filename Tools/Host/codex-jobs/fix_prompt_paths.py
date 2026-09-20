"""Repair 'C:' + newline + 'screv' (a heredoc-mangled C:\\nscrev path) in the spell check prompts."""
import pathlib

BROKEN = "C:" + chr(10) + "screv"
FIXED = "C:" + chr(92) + "nscrev"
for task in ("NSC-007", "NSC-008", "NSC-009"):
    path = pathlib.Path(r"C:\nscrev\codex-jobs") / f"codex-contract-check-{task}-rev3-20260917.prompt.md"
    text = path.read_text(encoding="utf-8")
    count = text.count(BROKEN)
    text = text.replace(BROKEN, FIXED)
    path.write_text(text, encoding="utf-8")
    print(task, "repaired", count, "| remaining broken:", text.count(BROKEN), "| has fixed path:", FIXED + chr(92) + "ger-contract-revisions" in text)
