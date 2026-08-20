from pathlib import Path

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent

SRC = HERE / "parallel_reconciliation_agent.py"
DST = ROOT / "Pipeline" / "Reconciliation" / "parallel_reconciliation_agent.py"

if not DST.exists():
    raise RuntimeError(
        "Parallel reconciliation agent was not found. "
        "Install the parallel reconciliation patches first."
    )

existing = DST.read_text(encoding="utf-8")
incoming = SRC.read_text(encoding="utf-8")

if existing == incoming:
    print(f"already installed: {DST}")
elif (
    "NINE-DOMAIN PARALLEL RECONCILIATION" in existing
    and "import reconciliation_agent as base" in existing
):
    DST.write_text(incoming, encoding="utf-8")
    print(f"updated: {DST}")
else:
    raise RuntimeError(
        f"{DST} does not look like the expected parallel reconciliation agent. "
        "Refusing to overwrite it."
    )

print()
print("24-turn minimum worker budget installed.")
print("Only parallel_reconciliation_agent.py was changed.")
print("No GDD file was read, copied, moved, installed, replaced, or modified.")
print("reconcile.md was not modified.")
print("Verification prompts were not modified.")
print("Existing outputs were not modified.")
print("Tasks/*.yaml was not modified.")
