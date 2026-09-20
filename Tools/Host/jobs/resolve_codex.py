"""Find the newest usable codex.exe. One tested resolver, for every recipe that needs one.

Why this exists (2026-09-20): recipes called a bare `codex.exe`, which PATH resolves to an old
build under .../Programs/OpenAI/Codex/bin. That build refuses the `gpt-6-astra` default in
~/.codex/config.toml and exits 1 writing nothing, so the GER Agent's live contract check produced
no report at all.

Two traps this handles, both measured:

1.  **A bin folder can exist without the binary.** At least one hash folder on this host contains
    no `codex.exe`. Picking "newest by mtime" across folders selects it and fails.
2.  **Prerelease ordering is not numeric-prefix ordering.** `0.155.0-alpha.9.2` and
    `0.155.0-alpha.2.6` reduce to the same key if you only read the leading `0.155.0`, and the
    tie then falls to filesystem order. Audit 20260920-143913 reproduced that. A release also
    sorts ABOVE a prerelease of the same version: 0.155.0 > 0.155.0-alpha.9.2.

Usage:
    python -B resolve_codex.py                 # print the chosen path, exit 0
    python -B resolve_codex.py --verbose       # print every candidate and its key
    NSC_CODEX_EXE=<path>                       # explicit override, validated
    NSC_CODEX_BIN_ROOT=<dir>                   # where to look (default: the Codex app's bin root)

Exit codes: 0 chosen, 2 nothing usable found, 3 override set but unusable.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_BIN_ROOT = Path(
    os.environ.get("NSC_CODEX_BIN_ROOT",
                   os.path.expandvars(r"%LOCALAPPDATA%\OpenAI\Codex\bin"))
)
EXE_NAME = os.environ.get("NSC_CODEX_EXE_NAME", "codex.exe")
_PAD = 6


class NoCodex(Exception):
    """No usable codex binary. The message says where it looked."""


def version_key(version: str) -> tuple:
    """Sortable key for a codex version string, prereleases below their release.

    0.155.0            -> (0,155,0, 1)
    0.155.0-alpha.9.2  -> (0,155,0, 0, 9, 2)
    0.155.0-alpha.2.6  -> (0,155,0, 0, 2, 6)

    so 0.155.0 > 0.155.0-alpha.9.2 > 0.155.0-alpha.2.6, which plain numeric-prefix
    comparison gets wrong in two different ways.
    """
    text = version.strip()
    core, _, pre = text.partition("-")
    core_nums = [int(n) for n in re.findall(r"\d+", core)]
    while len(core_nums) < 3:
        core_nums.append(0)
    if not pre:
        return tuple(core_nums[:3]) + (1,)
    pre_nums = [int(n) for n in re.findall(r"\d+", pre)]
    return tuple(core_nums[:3]) + (0,) + tuple(pre_nums)


def _run_version(exe: Path) -> str:
    """`<exe> --version`, or "" if it cannot be asked."""
    cmd = [sys.executable, "-B", str(exe)] if str(exe).lower().endswith(".py") else [str(exe)]
    try:
        proc = subprocess.run(cmd + ["--version"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    out = (proc.stdout or proc.stderr or b"").decode(errors="replace").strip()
    return out.splitlines()[0] if out else ""


def _version_text(raw: str) -> str:
    """Pull the version out of `codex-cli 0.155.0-alpha.9.2`."""
    m = re.search(r"\d+(?:\.\d+)*(?:-[A-Za-z0-9.]+)?", raw)
    return m.group(0) if m else ""


def candidates(bin_root: Path | None = None) -> list[tuple[tuple, str, Path]]:
    """Every (key, version, path) under bin_root that actually holds the binary."""
    root = Path(bin_root) if bin_root is not None else DEFAULT_BIN_ROOT
    if not root.is_dir():
        raise NoCodex(f"Codex bin root not found: {root}. Is the Codex app installed?")
    found = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        exe = child / EXE_NAME
        if not exe.is_file():
            continue  # a hash folder with no binary - trap 1
        version = _version_text(_run_version(exe))
        if not version:
            continue
        found.append((version_key(version), version, exe))
    return found


def resolve(bin_root: Path | None = None) -> Path:
    override = os.environ.get("NSC_CODEX_EXE")
    if override:
        path = Path(override)
        if not path.is_file():
            raise NoCodex(f"NSC_CODEX_EXE is set but not a file: {path}")
        return path
    found = candidates(bin_root)
    if not found:
        root = Path(bin_root) if bin_root is not None else DEFAULT_BIN_ROOT
        raise NoCodex(f"no usable {EXE_NAME} under {root} "
                      "(folders exist but none contains a runnable binary)")
    found.sort(key=lambda t: t[0])
    return found[-1][2]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print the path of the newest usable codex.exe.")
    ap.add_argument("--verbose", action="store_true", help="list every candidate and its key")
    ap.add_argument("--bin-root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.bin_root) if args.bin_root else None
    try:
        if args.verbose:
            for key, version, exe in sorted(candidates(root)):
                print(f"{version:24} {key}  {exe}", file=sys.stderr)
        print(resolve(root))
        return 0
    except NoCodex as e:
        print(str(e), file=sys.stderr)
        return 3 if os.environ.get("NSC_CODEX_EXE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
