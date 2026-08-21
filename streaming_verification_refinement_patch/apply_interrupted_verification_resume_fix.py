from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "streaming_verification_refinement_patch" / "resume_streaming_verification.py"

MARKER = "def load_failed_repair_keys(run_dir: Path) -> list[str]:"


def patch_resume_script() -> bool:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        return False

    old_load_tail = '''    if not repairs:\n        raise RuntimeError("No preserved streaming field repairs were found.")\n    return repairs\n'''
    new_load_tail = '''    return repairs\n\n\ndef load_failed_repair_keys(run_dir: Path) -> list[str]:\n    """Find interrupted local repairs that have findings but no completed repair output."""\n    root = run_dir / "stream_repairs"\n    if not root.exists():\n        return []\n\n    failed: set[str] = set()\n    for repair_dir in sorted(path for path in root.iterdir() if path.is_dir()):\n        findings = repair_dir / "REFINER_FINDINGS.json"\n        proposed = repair_dir / "PROPOSED_FIELD_REPAIR.json"\n        recovered = repair_dir / "RECOVERED_FIELD_REPAIR.json"\n        if findings.exists() and not proposed.exists() and not recovered.exists():\n            failed.add(repair_dir.name)\n\n    manifest_path = run_dir / "STREAM_REPAIR_MANIFEST.json"\n    if manifest_path.exists():\n        manifest = base.load_json(manifest_path)\n        for audit_key in manifest.get("failures", {}):\n            repair_dir = root / str(audit_key)\n            findings = repair_dir / "REFINER_FINDINGS.json"\n            proposed = repair_dir / "PROPOSED_FIELD_REPAIR.json"\n            recovered = repair_dir / "RECOVERED_FIELD_REPAIR.json"\n            if findings.exists() and not proposed.exists() and not recovered.exists():\n                failed.add(str(audit_key))\n\n    return sorted(failed)\n'''
    if old_load_tail not in text:
        raise RuntimeError("Unable to locate load_repairs tail.")
    text = text.replace(old_load_tail, new_load_tail, 1)

    old_copy = '''    for audit_key, envelope in sorted(repairs.items()):\n        target_dir = paths["run_dir"] / "stream_repairs" / audit_key\n        target_dir.mkdir(parents=True, exist_ok=False)\n        source_findings = failed_dir / "stream_repairs" / audit_key / "REFINER_FINDINGS.json"\n        if source_findings.exists():\n            shutil.copy2(source_findings, target_dir / "REFINER_FINDINGS.json")\n        base.save_new_json(target_dir / "REUSED_FIELD_REPAIR.json", envelope)\n'''
    new_copy = '''    source_root = failed_dir / "stream_repairs"\n    if source_root.exists():\n        for source_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):\n            source_findings = source_dir / "REFINER_FINDINGS.json"\n            if not source_findings.exists():\n                continue\n            audit_key = source_dir.name\n            target_dir = paths["run_dir"] / "stream_repairs" / audit_key\n            target_dir.mkdir(parents=True, exist_ok=False)\n            shutil.copy2(source_findings, target_dir / "REFINER_FINDINGS.json")\n            envelope = repairs.get(audit_key)\n            if envelope is not None:\n                base.save_new_json(target_dir / "REUSED_FIELD_REPAIR.json", envelope)\n'''
    if old_copy not in text:
        raise RuntimeError("Unable to locate preserved repair copy loop.")
    text = text.replace(old_copy, new_copy, 1)

    old_manifest_failures = '''        "failures": {},\n        "deterministic_conflict_report": coordinator.conflict_report,\n'''
    new_manifest_failures = '''        "failures": copy.deepcopy(coordinator.failures),\n        "deterministic_conflict_report": coordinator.conflict_report,\n'''
    if old_manifest_failures not in text:
        raise RuntimeError("Unable to locate resumed manifest failure field.")
    text = text.replace(old_manifest_failures, new_manifest_failures, 1)

    old_load_main = '''    pass1_audits = load_pass1(failed_dir)\n    repairs = load_repairs(failed_dir)\n    identity_remaps = remap_preserved_deterministic_resolution_ids(repairs)\n'''
    new_load_main = '''    pass1_audits = load_pass1(failed_dir)\n    repairs = load_repairs(failed_dir)\n    failed_repair_keys = load_failed_repair_keys(failed_dir)\n    if not repairs and not failed_repair_keys:\n        raise RuntimeError("No preserved or interrupted streaming field repairs were found.")\n    identity_remaps = remap_preserved_deterministic_resolution_ids(repairs)\n'''
    if old_load_main not in text:
        raise RuntimeError("Unable to locate resume input loading block.")
    text = text.replace(old_load_main, new_load_main, 1)

    old_coordinator = '''    coordinator._collected = True\n    coordinator.repairs = copy.deepcopy(repairs)\n    coordinator.failures = {}\n    coordinator._build_conflict_report()\n'''
    new_coordinator = '''    coordinator._collected = True\n    coordinator.repairs = copy.deepcopy(repairs)\n    coordinator.failures = {\n        key: "Preserved interrupted field repair; retry during resume."\n        for key in failed_repair_keys\n    }\n    coordinator._build_conflict_report()\n'''
    if old_coordinator not in text:
        raise RuntimeError("Unable to locate resumed coordinator initialization block.")
    text = text.replace(old_coordinator, new_coordinator, 1)

    old_prints = '''    print(f"Preserved field repairs: {len(repairs)}")\n    print(f"Preserved deterministic finding IDs remapped: {len(identity_remaps)}")\n    print(\n        "Mechanical field conflicts: "\n        f"{coordinator.summary()['mechanical_conflict_count']}"\n    )\n    print("No pass-1 auditors or local field-repair agents will be rerun.")\n'''
    new_prints = '''    print(f"Preserved field repairs: {len(repairs)}")\n    print(f"Interrupted field repairs to retry: {len(failed_repair_keys)}")\n    if failed_repair_keys:\n        print("Retry repair keys: " + ", ".join(failed_repair_keys))\n    print(f"Preserved deterministic finding IDs remapped: {len(identity_remaps)}")\n    print(\n        "Mechanical field conflicts: "\n        f"{coordinator.summary()['mechanical_conflict_count']}"\n    )\n    print("No pass-1 auditors will be rerun.")\n    if failed_repair_keys:\n        print("Only interrupted local field-repair agents will rerun before synthesis.")\n    else:\n        print("No local field-repair agents will be rerun.")\n'''
    if old_prints not in text:
        raise RuntimeError("Unable to locate resume status print block.")
    text = text.replace(old_prints, new_prints, 1)

    old_description = '''            "Resume a streaming-v2 verification that finished pass 1 and local field repairs "\n            "but failed during deterministic synthesis/semantic validation."\n'''
    new_description = '''            "Resume a streaming-v2 verification after pass 1, reusing completed local field "\n            "repairs and retrying only repairs interrupted before synthesis."\n'''
    if old_description in text:
        text = text.replace(old_description, new_description, 1)

    TARGET.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    if patch_resume_script():
        print("Installed interrupted-verification resume support.")
        print("  - Preserved Pass 1 auditors are reused.")
        print("  - Completed field repairs are reused.")
        print("  - Only field repairs interrupted by API/session limits are retried.")
    else:
        print("Interrupted-verification resume support is already installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
