from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "refiner.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "coverage_auditor.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "evidence_auditor.md",
]
MARKER = "VERIFIED CLOSURE labels are pipeline bookkeeping, not GDD evidence"

BLOCK = f'''\n\n### Final provenance guard\n\n- {MARKER}.\n- Never emit `VERIFIED CLOSURE`, `2026-08-21 VERIFIED CLOSURE`, `verification-hardening`, or similar verifier/patch-round labels as a GDD reference, repository evidence source, dependency evidence source, or exclusive-resource evidence source unless that exact phrase literally exists in the cited authoritative file.\n- When the underlying behavior is supported by a real GDD passage, cite only that real passage (for example `Door and Pursuit Rules` or `Enemy Detection, Pursuit, and Target Loss`).\n- Pipeline prompts, patch scripts, verification artifacts, and prior repair prose may explain why a correction is being made, but they are never project/GDD evidence.\n'''


def main() -> int:
    changed = 0
    for path in TARGETS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            continue
        path.write_text(text.rstrip() + BLOCK + "\n", encoding="utf-8")
        changed += 1
    if changed:
        print(f"Installed final provenance guard in {changed} reconciliation/verification prompt(s).")
    else:
        print("Final provenance guard is already installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
