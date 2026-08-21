from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "Pipeline" / "Reconciliation" / "streaming_refinement_v2.py"
PARALLEL = ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py"
MARKER = "standard Refiner guidance is inherited by field repair workers"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    module_text = MODULE.read_text(encoding="utf-8")
    if MARKER not in module_text:
        old_local = '''    candidate_rel = source_candidate.relative_to(base.ROOT).as_posix()
    findings_rel = findings_path.relative_to(base.ROOT).as_posix()
    return f"""# No Safe Circle Streaming Field Repair Worker
'''
        new_local = '''    candidate_rel = source_candidate.relative_to(base.ROOT).as_posix()
    findings_rel = findings_path.relative_to(base.ROOT).as_posix()
    # The standard Refiner guidance is inherited by field repair workers so
    # closure/ownership rules remain centralized in prompts/verification/refiner.md.
    refiner_guidance = base.load_prompt("refiner.md")
    return refiner_guidance + f"""\n\n---\n\n# No Safe Circle Streaming Field Repair Worker
'''
        module_text = replace_once(
            module_text,
            old_local,
            new_local,
            "local field-repair guidance inheritance",
        )

        old_cluster = '''    candidate_rel = source_candidate.relative_to(base.ROOT).as_posix()
    cluster_rel = cluster_input.relative_to(base.ROOT).as_posix()
    return f"""# No Safe Circle Streaming Field Conflict Arbiter
'''
        new_cluster = '''    candidate_rel = source_candidate.relative_to(base.ROOT).as_posix()
    cluster_rel = cluster_input.relative_to(base.ROOT).as_posix()
    refiner_guidance = base.load_prompt("refiner.md")
    return refiner_guidance + f"""\n\n---\n\n# No Safe Circle Streaming Field Conflict Arbiter
'''
        module_text = replace_once(
            module_text,
            old_cluster,
            new_cluster,
            "cluster guidance inheritance",
        )

        module_text = module_text.replace(
            "For ordinary acceptance criteria, validation requirements, dependencies, exclusive\nresources, evidence, notes, execution scope, confidence, etc., prefer field operations.\nResolve every supplied finding exactly once.",
            "For ordinary acceptance criteria, validation requirements, dependencies, exclusive\nresources, evidence, notes, execution scope, confidence, etc., prefer field operations.\nDo not change summary or seed_assessment unless a supplied finding directly targets them.\nResolve every supplied finding exactly once.",
            1,
        )
        MODULE.write_text(module_text, encoding="utf-8")
        print("Streaming v2 now inherits standard Refiner guidance.")
    else:
        print("Streaming v2 Refiner guidance inheritance is already installed.")

    parallel_text = PARALLEL.read_text(encoding="utf-8")
    old_log = '''                print(
                    "Mechanical direct conflicts: "
                    f"{stream_repairs.summary()['mechanical_conflict_count']}"
                )
                print("Final arbiter also checks semantic cross-record conflicts.")
'''
    new_log = '''                print(
                    "Mechanical field conflicts: "
                    f"{stream_repairs.summary()['mechanical_conflict_count']}"
                )
                print(
                    "Only connected incompatible field clusters invoke arbiters; "
                    "the final projection still runs semantic validation."
                )
'''
    if old_log in parallel_text:
        parallel_text = parallel_text.replace(old_log, new_log, 1)
        PARALLEL.write_text(parallel_text, encoding="utf-8")
        print("Updated streaming v2 conflict-gate telemetry.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
