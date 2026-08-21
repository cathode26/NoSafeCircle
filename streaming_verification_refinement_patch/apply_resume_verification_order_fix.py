from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "streaming_verification_refinement_patch" / "resume_streaming_verification.py"
MARKER = "Coordinator creates stream_repairs before preserved repair subdirectories are copied."


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Resume verification initialization order is already fixed.")
        return 0

    old = '''    paths = base.create_verification_paths(source_run_id)\n    copy_preserved_inputs(\n        failed_dir=failed_dir,\n        paths=paths,\n        repairs=repairs,\n    )\n\n    merged1 = base.merge_findings(pass1_audits)\n    base.save_new_json(paths["merged_pass1"], merged1)\n    refiner_findings = base.build_refiner_findings(merged1)\n    base.save_new_json(paths["refiner_findings"], refiner_findings)\n\n    coordinator = stream_v2.StreamingRepairCoordinator(\n        source_candidate=source_candidate,\n        source_run_id=source_run_id,\n        run_dir=paths["run_dir"],\n    )\n    # The constructor created a fresh empty stream_repairs directory, but the preserved\n    # copies were already placed there. No new local repairs are submitted during resume.\n'''
    new = '''    paths = base.create_verification_paths(source_run_id)\n    coordinator = stream_v2.StreamingRepairCoordinator(\n        source_candidate=source_candidate,\n        source_run_id=source_run_id,\n        run_dir=paths["run_dir"],\n    )\n    # Coordinator creates stream_repairs before preserved repair subdirectories are copied.\n    copy_preserved_inputs(\n        failed_dir=failed_dir,\n        paths=paths,\n        repairs=repairs,\n    )\n\n    merged1 = base.merge_findings(pass1_audits)\n    base.save_new_json(paths["merged_pass1"], merged1)\n    refiner_findings = base.build_refiner_findings(merged1)\n    base.save_new_json(paths["refiner_findings"], refiner_findings)\n\n    # No new local repairs are submitted during resume.\n'''
    text = replace_once(text, old, new, "coordinator initialization order")
    TARGET.write_text(text, encoding="utf-8")
    print("Fixed resume verification stream directory initialization order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
