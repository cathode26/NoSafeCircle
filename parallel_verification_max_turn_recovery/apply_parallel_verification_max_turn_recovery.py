from pathlib import Path

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent

SRC = HERE / "parallel_verification_crew.py"
DST = ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py"

if not DST.exists():
    raise RuntimeError(
        "Parallel verification crew was not found. "
        "Install the parallel verification patch first."
    )

existing = DST.read_text(encoding="utf-8")
incoming = SRC.read_text(encoding="utf-8")

if existing == incoming:
    print(f"already installed: {DST}")
elif (
    "PARALLEL RECONCILIATION VERIFICATION" in existing
    and "import verification_crew as base" in existing
):
    DST.write_text(incoming, encoding="utf-8")
    print(f"updated: {DST}")
else:
    raise RuntimeError(
        f"{DST} does not look like the expected parallel verifier. "
        "Refusing to overwrite it."
    )

print()
print("Max-turn recovery installed.")
print("Only parallel_verification_crew.py was changed.")
print("The original verification_crew.py was not modified.")
print("Verification prompts were not modified.")
print("Reconciliation scripts/prompts were not modified.")
print("No GDD file was read, copied, moved, replaced, or modified.")
print("Existing reconciliation/verification outputs were not modified.")
print("Tasks/*.yaml was not modified.")
