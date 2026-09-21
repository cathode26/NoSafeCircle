import importlib.util, pathlib, subprocess, sys, os
REPO = r"C:\NSC\NSC\NoSafeCircle"
ROOT = pathlib.Path(r"C:\NSC\tools")
files = sorted(p for p in ROOT.rglob("*.py")
               if "__pycache__" not in p.parts and not p.name.endswith(".bak.py")
               and "tests" not in p.parts)
CODE = r'''
import importlib.util, sys
sys.path.insert(0, r"{repo}")
sys.path.insert(0, r"{parent}")
s = importlib.util.spec_from_file_location("probe_mod", r"{f}")
m = importlib.util.module_from_spec(s)
try:
    s.loader.exec_module(m); print("OK")
except SystemExit: print("OK (argparse exit at import)")
except Exception as e: print(type(e).__name__ + ": " + str(e)[:110])
'''
bad = []
for f in files:
    code = CODE.format(repo=REPO, parent=str(f.parent), f=str(f))
    r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, cwd=REPO, timeout=90)
    out = (r.stdout.decode(errors="replace").strip().splitlines() or ["<no output>"])[-1]
    if not out.startswith("OK"):
        bad.append((f.relative_to(ROOT), out))
print(f"import sweep: {len(files)-len(bad)}/{len(files)} import cleanly (cwd = repo root)")
for rel, out in bad:
    print(f"  FAIL {rel}\n       {out}")
