from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

NORMALIZE_PATHS = [
    ROOT / "Docs" / "GDD" / "No_Safe_Circle_GDD.md",
    ROOT / "Pipeline" / "Reconciliation" / "verification_crew.py",
    ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "coverage_auditor.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "refiner.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "structure_auditor.md",
]


def run_script(name: str) -> None:
    path = HERE / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.main()
    if result not in (None, 0):
        raise RuntimeError(f"{name} failed with result {result}")


def normalize_lf() -> None:
    for path in NORMALIZE_PATHS:
        if not path.exists():
            continue
        data = path.read_bytes()
        normalized = data.replace(b"\r\n", b"\n")
        if normalized != data:
            path.write_bytes(normalized)


def main() -> int:
    run_script("apply_verified_closure_fixes.py")
    run_script("apply_reconciliation_evidence_guard.py")
    run_script("apply_streaming_verification_refinement.py")
    normalize_lf()
    print("All streaming verification + approved closure fixes are installed.")
    print("Installed reconciliation evidence-path precision guard.")
    print("Normalized patched text files to LF line endings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
