from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

def read(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"Expected repository file not found: {p}")
    return p.read_text(encoding="utf-8")

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")

def replace_once(path: str, old: str, new: str, marker: str | None = None) -> None:
    text = read(path)
    if marker and marker in text:
        print(f"already patched: {path}")
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}")
    text = text.replace(old, new, 1)
    write(path, text)
    print(f"patched: {path}")

# verification_crew.py ------------------------------------------------------

replace_once(
    "Pipeline/Reconciliation/verification_crew.py",
    '''REFINER_TIMEOUT_SECONDS = int(
    os.environ.get("RECONCILIATION_VERIFY_REFINER_TIMEOUT_SECONDS", "1200")
)
REFINER_MAX_TURNS = int(
''',
    '''REFINER_TIMEOUT_SECONDS = int(
    os.environ.get("RECONCILIATION_VERIFY_REFINER_TIMEOUT_SECONDS", "1800")
)
REFINER_MODEL = os.environ.get(
    "RECONCILIATION_VERIFY_REFINER_MODEL",
    "opus",
).strip() or "opus"
REFINER_MAX_TURNS = int(
''',
    marker='RECONCILIATION_VERIFY_REFINER_MODEL',
)

replace_once(
    "Pipeline/Reconciliation/verification_crew.py",
    '''        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
        "refined_raw": run_dir / "refined_candidate.raw.json",
''',
    '''        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
        "refiner_findings": run_dir / "REFINER_FINDINGS.json",
        "refined_raw": run_dir / "refined_candidate.raw.json",
''',
    marker='"refiner_findings": run_dir / "REFINER_FINDINGS.json"',
)

replace_once(
    "Pipeline/Reconciliation/verification_crew.py",
    '''def choose_refiner_model(rng: random.Random, pass1: dict[str, str]) -> str:
    # Prefer a model that was not used by both coverage auditors when possible.
    least_used = Counter(pass1.values())
    min_count = min(least_used.values())
    candidates = [model for model in MODEL_POOL if least_used.get(model, 0) == min_count]
    return rng.choice(candidates or MODEL_POOL)
''',
    '''def choose_refiner_model(rng: random.Random, pass1: dict[str, str]) -> str:
    # Auditors stay randomized/model-diverse, but synthesis is a different
    # workload. Use a stable stronger Refiner so a valid pass-1 audit is not
    # lost to a random slower/weaker synthesis assignment.
    _ = rng, pass1
    return REFINER_MODEL
''',
    marker='Use a stable stronger Refiner',
)

replace_once(
    "Pipeline/Reconciliation/verification_crew.py",
    '''def has_material_findings(merged: dict[str, Any]) -> bool:
    return int(merged.get("material_finding_count", 0)) > 0


# ============================================================
# BOUNDED REFINER
# ============================================================
''',
    '''def has_material_findings(merged: dict[str, Any]) -> bool:
    return int(merged.get("material_finding_count", 0)) > 0


def build_refiner_findings(merged: dict[str, Any]) -> dict[str, Any]:
    # The Refiner's mandatory job is blocker/error repair. Warnings and
    # suggestions remain in the full pass-1 merge and are independently
    # reassessed during pass 2.
    material = [
        report
        for report in merged.get("findings", [])
        if report.get("finding", {}).get("severity") in {"blocker", "error"}
    ]
    return {
        "schema_version": "1.0",
        "source_finding_count": int(merged.get("finding_count", 0)),
        "material_finding_count": len(material),
        "findings": material,
        "selection_policy": (
            "Refiner input contains blocker/error findings only. Warnings and "
            "suggestions remain in MERGED_FINDINGS_PASS1.json and are checked "
            "again by independent pass-2 auditors."
        ),
    }


# ============================================================
# BOUNDED REFINER
# ============================================================
''',
    marker='def build_refiner_findings(',
)

replace_once(
    "Pipeline/Reconciliation/verification_crew.py",
    '''        if has_material_findings(merged1) and not args.no_refine:
            refinement_performed = True
            refiner = run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["merged_pass1"],
                source_run_id=source_run_id,
                model=refiner_model,
            )
''',
    '''        if has_material_findings(merged1) and not args.no_refine:
            refinement_performed = True

            refiner_findings = build_refiner_findings(merged1)
            save_new_json(paths["refiner_findings"], refiner_findings)

            refiner = run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=source_run_id,
                model=refiner_model,
            )
''',
    marker='refiner_findings = build_refiner_findings(merged1)',
)

# recover_verification.py ---------------------------------------------------

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''import argparse
import sys
''',
    '''import argparse
import os
import sys
''',
    marker='import os\nimport sys',
)

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''    ROOT,
    RUNS_DIR,
    create_verification_paths,
    load_json,
    merge_findings,
''',
    '''    ROOT,
    RUNS_DIR,
    REFINER_MODEL,
    build_refiner_findings,
    create_verification_paths,
    load_json,
    merge_findings,
''',
    marker='    REFINER_MODEL,\n    build_refiner_findings,',
)

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''    render_verification_markdown,
    run_audit_pass,
    sanitize_refiner_input_tracking,
''',
    '''    render_verification_markdown,
    run_audit_pass,
    run_refiner,
    sanitize_refiner_input_tracking,
''',
    marker='    run_refiner,\n    sanitize_refiner_input_tracking,',
)

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
        "refined_raw": run_dir / "refined_candidate.raw.json",
''',
    '''        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
        "refiner_findings": run_dir / "REFINER_FINDINGS.json",
        "recovery_json": run_dir / "RECOVERY.json",
        "refined_raw": run_dir / "refined_candidate.raw.json",
''',
    marker='"recovery_json": run_dir / "RECOVERY.json"',
)

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''        for required in (
            paths["model_assignments"],
            paths["merged_pass1"],
            paths["refined_raw"],
        ):
''',
    '''        for required in (
            paths["model_assignments"],
            paths["merged_pass1"],
        ):
''',
    marker='paths["merged_pass1"],\n        ):',
)

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''        assignments = load_json(paths["model_assignments"])
        merged1 = load_json(paths["merged_pass1"])
        refined_payload = load_json(paths["refined_raw"])

        print()
        print("=" * 72)
        print("RESUMING PRESERVED RECONCILIATION VERIFICATION")
        print("=" * 72)
        print(f"Source reconciliation: {args.source_run_id}")
        print(f"Verification run: {args.verification_run_id}")
        print("Reusing completed pass-1 audits and completed Refiner output.")
        print("Pass 1 and the Refiner will NOT be rerun.")
        print("=" * 72)

        removed_forbidden = sanitize_forbidden_evidence(refined_payload)
''',
    '''        assignments = load_json(paths["model_assignments"])
        merged1 = load_json(paths["merged_pass1"])

        print()
        print("=" * 72)
        print("RESUMING PRESERVED RECONCILIATION VERIFICATION")
        print("=" * 72)
        print(f"Source reconciliation: {args.source_run_id}")
        print(f"Verification run: {args.verification_run_id}")
        print("Reusing completed pass-1 audits and merged findings.")
        print("Pass 1 will NOT be rerun.")

        actual_refiner_model = str(assignments.get("refiner", "")).strip()

        if paths["refined_raw"].exists():
            refined_payload = load_json(paths["refined_raw"])
            print("Completed Refiner output exists and will be reused.")
        else:
            if not paths["refiner_findings"].exists():
                save_new_json(
                    paths["refiner_findings"],
                    build_refiner_findings(merged1),
                )

            recovery_model = os.environ.get(
                "RECONCILIATION_VERIFY_RECOVERY_REFINER_MODEL",
                REFINER_MODEL,
            ).strip() or REFINER_MODEL
            original_model = str(assignments.get("refiner", "")).strip()

            print(
                "No completed Refiner output exists. This preserved run stopped "
                "during refinement, so only the Refiner will be rerun."
            )
            print(f"Original Refiner assignment: {original_model or '(unknown)'}")
            print(f"Recovery Refiner model: {recovery_model}")

            refiner = run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=args.source_run_id,
                model=recovery_model,
            )
            refined_payload = refiner["result"]
            save_new_json(paths["refined_raw"], refined_payload)
            actual_refiner_model = recovery_model

            if not paths["recovery_json"].exists():
                save_new_json(
                    paths["recovery_json"],
                    {
                        "schema_version": "1.0",
                        "reason": "refiner_timeout_or_missing_refined_raw",
                        "source_reconciliation_run_id": args.source_run_id,
                        "verification_run_id": args.verification_run_id,
                        "pass1_reused": True,
                        "original_refiner_model": original_model,
                        "recovery_refiner_model": recovery_model,
                    },
                )

        print("=" * 72)

        removed_forbidden = sanitize_forbidden_evidence(refined_payload)
''',
    marker='No completed Refiner output exists. This preserved run stopped',
)

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''            "model_assignments": {
                "pass1": assignments.get("pass1"),
                "refiner": assignments.get("refiner"),
                "pass2": assignments.get("pass2"),
            },
''',
    '''            "model_assignments": {
                "pass1": assignments.get("pass1"),
                "refiner": actual_refiner_model,
                "original_refiner_assignment": assignments.get("refiner"),
                "pass2": assignments.get("pass2"),
            },
''',
    marker='"original_refiner_assignment": assignments.get("refiner")',
)

replace_once(
    "Pipeline/Reconciliation/recover_verification.py",
    '''            "recovered_from_preserved_run": True,
''',
    '''            "recovered_from_preserved_run": True,
            "refiner_recovered": paths["recovery_json"].exists(),
''',
    marker='"refiner_recovered": paths["recovery_json"].exists()',
)

# smoke test ---------------------------------------------------------------

replace_once(
    "Pipeline/Reconciliation/verification_smoke_test.py",
    '''    merged = crew.merge_findings(audits)
    assert merged["material_finding_count"] == 1
    assert merged["findings"][0]["source_agent"] == "Deterministic Coverage Check"
''',
    '''    merged = crew.merge_findings(audits)
    assert merged["material_finding_count"] == 1
    assert merged["findings"][0]["source_agent"] == "Deterministic Coverage Check"

    refiner_findings = crew.build_refiner_findings(
        {
            "finding_count": 3,
            "findings": [
                {"finding": {"severity": "error", "title": "must fix"}},
                {"finding": {"severity": "warning", "title": "recheck later"}},
                {"finding": {"severity": "suggestion", "title": "optional"}},
            ],
        }
    )
    assert refiner_findings["source_finding_count"] == 3
    assert refiner_findings["material_finding_count"] == 1
    assert len(refiner_findings["findings"]) == 1
    assert refiner_findings["findings"][0]["finding"]["title"] == "must fix"
    assert crew.choose_refiner_model(random.Random(1), assignments) == crew.REFINER_MODEL
''',
    marker='refiner_findings = crew.build_refiner_findings(',
)

# README -------------------------------------------------------------------

readme_path = "Pipeline/Reconciliation/README.md"
readme = read(readme_path)
if "RECONCILIATION_VERIFY_REFINER_MODEL=opus" not in readme:
    anchor = '''RECONCILIATION_MODEL=sonnet
RECONCILIATION_TIMEOUT_SECONDS=1800
RECONCILIATION_MAX_TURNS=50
'''
    replacement = '''RECONCILIATION_MODEL=sonnet
RECONCILIATION_TIMEOUT_SECONDS=1800
RECONCILIATION_MAX_TURNS=50

# Multi-model verification
RECONCILIATION_VERIFY_REFINER_MODEL=opus
RECONCILIATION_VERIFY_REFINER_TIMEOUT_SECONDS=1800
RECONCILIATION_VERIFY_RECOVERY_REFINER_MODEL=opus
'''
    if anchor not in readme:
        raise RuntimeError("README environment-variable anchor not found")
    readme = readme.replace(anchor, replacement, 1)

    anchor2 = '''Difficulty is not the classifier: a hard but bounded task can still be `single_agent`.
'''
    extra = '''

## Verification refiner sizing and recovery

Independent auditors remain model-diverse and randomized. The Refiner is not
another vote: it is a synthesis step over the union of material findings, so it
defaults to `opus` for predictable capacity.

Only `blocker` and `error` findings are sent to the Refiner. Warnings and
suggestions remain preserved in the full pass-1 merge and are reassessed by the
independent pass-2 auditors.

If a verification run times out during refinement, the completed pass-1 audits
are not repeated. `recover_verification.py` can rerun only the missing Refiner
and then continue to pass 2.
'''
    if anchor2 in readme:
        readme = readme.replace(anchor2, anchor2 + extra, 1)
    write(readme_path, readme)
    print(f"patched: {readme_path}")
else:
    print(f"already patched: {readme_path}")

print()
print("Refiner timeout/recovery fix applied.")
print("Run the smoke test, then recover the preserved verification run.")
