from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_script(name: str) -> None:
    path = HERE / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.main()
    if result not in (None, 0):
        raise RuntimeError(f"{name} failed with result {result}")


def main() -> int:
    run_script("apply_verified_closure_fixes.py")
    run_script("apply_streaming_verification_refinement.py")
    print("All streaming verification + approved closure fixes are installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
