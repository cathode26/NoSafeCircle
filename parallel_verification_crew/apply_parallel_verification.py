from pathlib import Path
import shutil

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent

SRC = HERE / "parallel_verification_crew.py"
DST = ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py"
BASE = ROOT / "Pipeline" / "Reconciliation" / "verification_crew.py"

if not BASE.exists():
    raise RuntimeError(
        "Run this from the NoSafeCircle repository root. "
        "Pipeline/Reconciliation/verification_crew.py was not found."
    )

incoming = SRC.read_text(encoding="utf-8")

if DST.exists():
    existing = DST.read_text(encoding="utf-8")
    if existing == incoming:
        print(f"already installed: {DST}")
    elif "PARALLEL RECONCILIATION VERIFICATION" in existing and "import verification_crew as base" in existing:
        DST.write_text(incoming, encoding="utf-8")
        print(f"upgraded existing parallel verifier: {DST}")
    else:
        raise RuntimeError(
            f"{DST} already exists with unrelated content. "
            "Refusing to overwrite it automatically."
        )
else:
    shutil.copy2(SRC, DST)
    print(f"created: {DST}")

print()
print("The original verification_crew.py was NOT modified.")
print("Verification prompts were NOT modified.")
print("reconciliation_agent.py / parallel_reconciliation_agent.py were NOT modified.")
print("reconcile.md was NOT modified.")
print("No GDD file was read, copied, moved, installed, replaced, or modified.")
print("Tasks/*.yaml was NOT modified.")
