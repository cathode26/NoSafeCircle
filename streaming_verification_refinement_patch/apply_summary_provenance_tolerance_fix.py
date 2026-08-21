from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "Pipeline" / "Reconciliation"
RECON_AGENT = RECON / "reconciliation_agent.py"
RECON_PROMPT = RECON / "prompts" / "reconcile.md"

MARKER = "def sanitize_non_authoritative_summary_provenance("

PROMPT_OLD = "- Never emit `VERIFIED CLOSURE`, `2026-08-21 VERIFIED CLOSURE`, `verification-hardening`, or similar verifier/patch-round labels as a GDD reference, repository evidence source, dependency evidence source, or exclusive-resource evidence source unless that exact phrase literally exists in the cited authoritative file."
PROMPT_NEW = "- Never emit internal verifier/patch-round labels as GDD references, repository evidence sources, dependency evidence sources, exclusive-resource evidence sources, or summary authority. If wording came from pipeline instructions rather than the cited authoritative file, omit that wording and cite the real GDD/repository passage instead."

SANITIZER_BLOCK = r'''


def sanitize_non_authoritative_summary_provenance(
    payload: dict[str, Any],
) -> list[str]:
    """
    Remove contaminated summary bullets without weakening authoritative provenance checks.

    summary.major_findings is disposable human-facing synthesis. A worker can state a
    substantively correct finding while accidentally naming an internal verifier/patch
    label. Throwing away nine completed reconciliation workers for that prose mistake is
    unnecessary. Remove only the contaminated summary bullet and retain a clean warning.

    All remaining candidate fields still pass through validate_reconciliation_provenance,
    so GDD evidence, repository evidence, dependencies, locks, acceptance/validation
    requirements, unresolved questions, and other graph-bearing content remain strict.
    """
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        return []

    findings = summary.get("major_findings", [])
    if not isinstance(findings, list):
        return []

    cleaned: list[Any] = []
    removed: list[str] = []
    for finding in findings:
        if _collect_internal_provenance_paths(finding):
            removed.append(str(finding))
        else:
            cleaned.append(finding)

    if not removed:
        return []

    summary["major_findings"] = cleaned

    seed = payload.setdefault(
        "seed_assessment",
        {"status": "ready_with_warnings", "blockers": [], "warnings": []},
    )
    warnings = seed.setdefault("warnings", [])
    warning = (
        "Deterministic provenance guard removed "
        f"{len(removed)} non-authoritative summary finding(s) containing "
        "internal pipeline provenance language. Authoritative graph/evidence "
        "fields remain subject to strict provenance validation."
    )
    if warning not in warnings:
        warnings.append(warning)
    if seed.get("status") == "ready":
        seed["status"] = "ready_with_warnings"

    return removed
'''


def patch_prompt() -> bool:
    text = RECON_PROMPT.read_text(encoding="utf-8")
    if PROMPT_OLD in text:
        RECON_PROMPT.write_text(text.replace(PROMPT_OLD, PROMPT_NEW, 1), encoding="utf-8")
        return True
    if PROMPT_NEW in text:
        return False
    raise RuntimeError("Unable to locate final-provenance prompt line to de-prime.")


def patch_agent() -> bool:
    text = RECON_AGENT.read_text(encoding="utf-8")
    changed = False

    if MARKER not in text:
        anchor = "\ndef validate_reconciliation_provenance(payload: dict[str, Any]) -> None:\n"
        if text.count(anchor) != 1:
            raise RuntimeError("Expected exactly one provenance-validator anchor.")
        text = text.replace(anchor, SANITIZER_BLOCK + anchor, 1)
        changed = True

    old_order = (
        "    normalize_execution_scope_consistency(payload)\n"
        "    normalize_seed_assessment_consistency(payload)\n"
    )
    new_order = (
        "    normalize_execution_scope_consistency(payload)\n"
        "    sanitize_non_authoritative_summary_provenance(payload)\n"
        "    normalize_seed_assessment_consistency(payload)\n"
    )
    if old_order in text:
        text = text.replace(old_order, new_order, 1)
        changed = True
    elif new_order not in text:
        raise RuntimeError("Unable to locate semantic-validation provenance order anchor.")

    if changed:
        RECON_AGENT.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    prompt_changed = patch_prompt()
    agent_changed = patch_agent()

    if prompt_changed or agent_changed:
        print("Installed summary-provenance tolerance fix.")
        if prompt_changed:
            print("  - Removed internal-label priming from reconciliation prompt.")
        if agent_changed:
            print("  - Non-authoritative contaminated summary bullets are dropped with a warning.")
            print("  - Authoritative provenance validation remains strict.")
    else:
        print("Summary-provenance tolerance fix is already installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
