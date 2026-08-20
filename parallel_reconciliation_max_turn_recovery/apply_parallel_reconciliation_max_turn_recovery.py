from pathlib import Path

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent

SRC = HERE / "parallel_reconciliation_agent.py"
DST = ROOT / "Pipeline" / "Reconciliation" / "parallel_reconciliation_agent.py"

if not DST.exists():
    raise RuntimeError(
        "Parallel reconciliation agent was not found. "
        "Install the parallel reconciliation patch first."
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
print("Parallel reconciliation max-turn recovery installed.")
print("Default parallel slots are now 9.")
print("Only parallel_reconciliation_agent.py was changed.")
print("The original reconciliation_agent.py was not modified.")
print("reconcile.md was not modified.")
print("Verification prompts were not modified.")
print("No GDD file was read, copied, moved, installed, replaced, or modified.")
print("Existing reconciliation outputs were not modified.")
print("Tasks/*.yaml was not modified.")
