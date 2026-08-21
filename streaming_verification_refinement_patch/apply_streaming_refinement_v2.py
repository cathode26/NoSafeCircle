from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py"
MARKER = "STREAMING REFINEMENT V2 FIELD OPS"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Streaming refinement v2 field operations are already installed.")
        return 0

    import_anchor = "import verification_crew as base\n"
    import_replacement = import_anchor + "import streaming_refinement_v2 as stream_v2\n"
    text = replace_once(text, import_anchor, import_replacement, "stream v2 import")

    selective_anchor = '''# ============================================================
# SELECTIVE PASS 2
# ============================================================
'''
    override = '''# ============================================================
# STREAMING REFINEMENT V2 FIELD OPS
# ============================================================
# Keep the v1 coordinator above for audit/history compatibility, but route new
# verification runs through the field-level implementation. Existing main-flow
# call sites intentionally keep the same coordinator interface.
LegacyStreamingRepairCoordinator = StreamingRepairCoordinator
StreamingRepairCoordinator = stream_v2.StreamingRepairCoordinator


''' + selective_anchor
    text = replace_once(text, selective_anchor, override, "stream v2 coordinator override")

    text = text.replace(
        'print("Mechanical direct conflicts: "',
        'print("Mechanical field conflicts: "',
    )
    text = text.replace(
        'print("Final arbiter also checks semantic cross-record conflicts.")',
        'print("Only connected incompatible field clusters invoke arbiters; the final projection still runs semantic validation.")',
    )
    text = text.replace(
        '"launch isolated repair proposals against the immutable candidate. A final "\n                "conflict arbiter consolidates proposals before selective pass 2. A max-turn "',
        '"launch field-level repair proposals against the immutable candidate. Compatible "\n                "field operations merge deterministically; only connected incompatible field "\n                "clusters invoke arbiters before selective pass 2. A max-turn "',
    )

    TARGET.write_text(text, encoding="utf-8")
    print("Installed streaming refinement v2 field-level operations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
