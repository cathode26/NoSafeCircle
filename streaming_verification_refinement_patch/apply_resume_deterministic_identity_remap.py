from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "streaming_verification_refinement_patch" / "resume_streaming_verification.py"
MARKER = "def remap_preserved_deterministic_resolution_ids("


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Resume deterministic-ID remap is already installed.")
        return 0

    helper_anchor = '''def copy_preserved_inputs(
'''
    helper_block = '''def remap_preserved_deterministic_resolution_ids(
    repairs: dict[str, dict],
) -> list[dict[str, str]]:
    """Migrate old locally-scoped deterministic IDs without rerunning repair agents."""
    prefix = "deterministic-representation-"
    changes: list[dict[str, str]] = []
    specs_by_key = {spec.key: spec for spec in parallel.SPECS}

    for audit_key, envelope in sorted(repairs.items()):
        spec = specs_by_key.get(audit_key)
        if spec is None:
            continue
        slug = base.deterministic_auditor_slug(spec.agent_name)
        expected_prefix = prefix + slug + "-"
        repair = envelope.get("result", {})
        for resolution in repair.get("finding_resolutions", []):
            if str(resolution.get("source_agent", "")) != "Deterministic Coverage Check":
                continue
            old_id = str(resolution.get("finding_id", ""))
            if not old_id.startswith(prefix) or old_id.startswith(expected_prefix):
                continue
            local_requirement_id = old_id[len(prefix):]
            new_id = expected_prefix + local_requirement_id
            resolution["finding_id"] = new_id
            changes.append(
                {
                    "audit_key": audit_key,
                    "old_finding_id": old_id,
                    "new_finding_id": new_id,
                }
            )

    return changes


''' + helper_anchor
    text = replace_once(text, helper_anchor, helper_block, "resume remap helper")

    main_anchor = '''    repairs = load_repairs(failed_dir)
    old_assignments = base.load_json(failed_dir / "MODEL_ASSIGNMENTS.json")
'''
    main_replacement = '''    repairs = load_repairs(failed_dir)
    identity_remaps = remap_preserved_deterministic_resolution_ids(repairs)
    old_assignments = base.load_json(failed_dir / "MODEL_ASSIGNMENTS.json")
'''
    text = replace_once(text, main_anchor, main_replacement, "resume remap invocation")

    print_anchor = '''    print(f"Preserved field repairs: {len(repairs)}")
'''
    print_replacement = print_anchor + '''    print(f"Preserved deterministic finding IDs remapped: {len(identity_remaps)}")
'''
    text = replace_once(text, print_anchor, print_replacement, "resume remap reporting")

    TARGET.write_text(text, encoding="utf-8")
    print("Resume utility now remaps preserved deterministic finding IDs by originating auditor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
