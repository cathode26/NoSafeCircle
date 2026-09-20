"""No-window subprocess helpers for GER Agent scripts (C:\\NSC\\nsc-quiet-windows-guide.md).

Import this instead of calling subprocess directly, so a script run from a Claude Bash tool never pops a console:

    import quiet
    head = quiet.git("-C", REPO, "rev-parse", "HEAD").stdout.decode().strip()
    quiet.run([sys.executable, "-B", "script.py"], cwd=somewhere)
"""
from __future__ import annotations

import subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def run(args, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(args, **kwargs)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], check=check)
