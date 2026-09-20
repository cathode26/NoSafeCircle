import subprocess, runpy, sys
_orig = subprocess.run
def run(*a, **k):
    k.setdefault("creationflags", 0x08000000)
    return _orig(*a, **k)
subprocess.run = run
sys.argv = [r"C:\nscrev\reports\cleanup-safety-scan.py"]
runpy.run_path(r"C:\nscrev\reports\cleanup-safety-scan.py", run_name="__main__")
