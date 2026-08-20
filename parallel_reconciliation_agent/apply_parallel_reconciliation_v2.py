from pathlib import Path
import shutil

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent

SRC = HERE / "parallel_reconciliation_agent.py"
DST = ROOT / "Pipeline" / "Reconciliation" / "parallel_reconciliation_agent.py"
BASE = ROOT / "Pipeline" / "Reconciliation" / "reconciliation_agent.py"

if not BASE.exists():
    raise RuntimeError(
        "Run this from the NoSafeCircle repository root. "
        "Pipeline/Reconciliation/reconciliation_agent.py was not found."
    )

incoming = SRC.read_text(encoding="utf-8")

if DST.exists():
    existing = DST.read_text(encoding="utf-8")

    # Safe upgrade from the earlier five-domain draft or an identical v2 file.
    if existing == incoming:
        print(f"already installed: {DST}")
    elif "PARALLEL RECONCILIATION" in existing and "import reconciliation_agent as base" in existing:
        DST.write_text(incoming, encoding="utf-8")
        print(f"upgraded existing parallel entry point: {DST}")
    else:
        raise RuntimeError(
            f"{DST} already exists but does not look like the earlier parallel "
            "reconciliation draft. Refusing to overwrite it automatically."
        )
else:
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DST)
    print(f"created: {DST}")

print()
print("The original reconciliation_agent.py was NOT modified.")
print("reconcile.md was NOT modified.")
print("Verification prompts were NOT modified.")
print("No GDD file was read, copied, moved, installed, replaced, or modified.")
print("Existing reconciliation outputs were NOT modified.")
print("Tasks/*.yaml was NOT modified.")
