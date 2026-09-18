#!/usr/bin/env python
"""Revert each half of the mixed-provider model fix; confirm a test goes red.

The defect this fixes was invisible precisely because a test asserted the
buggy argv verbatim. So each piece of the fix is reverted here on its own and
the suite must notice. Both halves matter independently: fixing the transport
while the caller passes nothing reproduces the original bug exactly.

Runs against a COPY of the two files, never the working tree, so a kill cannot
leave a half-reverted checkout behind.

    PYTHONPATH=<clone> C:/Python313/python.exe -B \
        Pipeline/AssistantControl/mixed_provider_mutation_check.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLONE = HERE.parents[1]

TRANSPORT = "Pipeline/AssistantControl/decomposition_transport.py"
CALLER = "Pipeline/AssistantControl/decomposition.py"
SHARED = "Pipeline/TaskDecomposition/live_decomposition.py"
PRODUCTION = "Pipeline/TaskReviewAgent/host_decomposition_launcher.py"
PRODUCTION_SUITE = "Pipeline/TaskReviewAgent/tests/decomposition_session_pool_smoke_test.py"

# (label, what it reverts, file, old, new, test module)
MUTATIONS = [
    (
        "caller passes no models",
        "THE ORIGINAL DEFECT: a mixed pair launched with no --env at all",
        CALLER,
        "            provider_environment=unpooled_environment,\n",
        "",
        "Pipeline.AssistantControl.test_decomposition",
    ),
    (
        "resolver returns nothing (AssistantControl side)",
        "the same defect one layer down - an empty dict forwards no --env",
        SHARED,
        "    for provider in dict.fromkeys(provider_order):",
        "    for provider in []:",
        "Pipeline.AssistantControl.test_decomposition",
    ),
    (
        "transport drops the unpooled branch",
        "the transport half: models resolved on the host but never forwarded",
        TRANSPORT,
        "    elif provider_environment:",
        "    elif False:",
        "Pipeline.AssistantControl.test_decomposition_transport",
    ),
    (
        "pooled ambiguity guard removed",
        "two sources of truth for a pooled run's model, silently resolved",
        TRANSPORT,
        "    if pool_assignment is not None and provider_environment is not None:",
        "    if False:",
        "Pipeline.AssistantControl.test_decomposition_transport",
    ),
    (
        "env name allow-list removed",
        "--env becomes a general passthrough into the container",
        SHARED,
        "        if name not in MODEL_ENVIRONMENT_NAMES:",
        "        if False:",
        "Pipeline.AssistantControl.test_decomposition_transport",
    ),
    (
        "empty values forwarded",
        "NSC_CLAUDE_MODEL= overrides the container default with the empty string",
        SHARED,
        '        if value is None or value == "":\n            continue',
        "        if False:\n            continue",
        "Pipeline.AssistantControl.test_decomposition_transport",
    ),
    (
        "model value check removed",
        "a model id could carry whitespace or a leading dash into the argv",
        SHARED,
        "        if type(value) is not str or not _SAFE_MODEL.fullmatch(value):",
        "        if False:",
        "Pipeline.AssistantControl.test_decomposition_transport",
    ),
    # The same gap existed in the production launcher. Fixing one and leaving
    # the other is how this defect would have come straight back.
    (
        "production caller passes no models",
        "the production launcher's unpooled route, launched with no --env",
        PRODUCTION,
        "                provider_environment=(\n"
        "                    None if pool_assignment is not None\n"
        "                    else resolve_provider_model_environment(\n"
        "                        decomposition_provider_order(args.providers, permitted)\n"
        "                    )\n"
        "                ),\n",
        "",
        PRODUCTION_SUITE,
    ),
    (
        "production transport drops the unpooled branch",
        "models resolved on the host but never forwarded, production side",
        PRODUCTION,
        "    elif provider_environment:",
        "    elif False:",
        PRODUCTION_SUITE,
    ),
    (
        "production pooled ambiguity guard removed",
        "two sources of truth for a pooled production run's model",
        PRODUCTION,
        "    if pool_assignment is not None and provider_environment is not None:",
        "    if False:",
        PRODUCTION_SUITE,
    ),
    (
        "shared resolver returns nothing",
        "both launchers lose their models at once",
        SHARED,
        "    for provider in dict.fromkeys(provider_order):",
        "    for provider in []:",
        PRODUCTION_SUITE,
    ),
]


def run_module(workdir: Path, module: str, temp: Path):
    """`module` is a dotted unittest module, or a path to a script suite."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(workdir)
    env["TEMP"] = env["TMP"] = str(temp)
    if module.endswith(".py"):
        argv = [sys.executable, "-B", str(workdir / module)]
    else:
        argv = [sys.executable, "-B", "-m", "unittest", module]
    proc = subprocess.run(
        argv, cwd=str(workdir), capture_output=True, text=True, env=env, timeout=900,
    )
    # The script suites raise on the first failure rather than listing FAILs,
    # so a non-zero exit is the signal there.
    return proc.returncode == 0, proc.stdout + proc.stderr


def main() -> int:
    scratch = tempfile.TemporaryDirectory(prefix="mixed-provider-mutation-")
    workdir = Path(scratch.name) / "clone"
    temp = Path(scratch.name) / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    # Only Pipeline/ is copied: 30 MB against the checkout's 221 MB, eleven
    # times over. These suites build their own synthetic checkouts, so nothing
    # outside Pipeline/ is read.
    print(f"copying Pipeline/ to {workdir} (the working tree is never mutated)")
    shutil.copytree(
        CLONE / "Pipeline", workdir / "Pipeline",
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        symlinks=False,
    )

    originals = {name: (workdir / name).read_text(encoding="utf-8")
                 for name in (TRANSPORT, CALLER, SHARED, PRODUCTION)}
    survivors = []
    try:
        for label, why, filename, old, new, module in MUTATIONS:
            target = workdir / filename
            source = originals[filename]
            if old not in source:
                print(f"SKIP      {label}: anchor not found - the mutation is stale")
                survivors.append((label, "anchor not found"))
                continue
            target.write_text(source.replace(old, new, 1), encoding="utf-8", newline="")
            passed, output = run_module(workdir, module, temp)
            target.write_text(source, encoding="utf-8", newline="")
            if passed:
                print(f"SURVIVED  {label}  ({module.rsplit('.', 1)[-1]} still green)")
                print(f"          reverts: {why}")
                survivors.append((label, module))
            else:
                red = [ln for ln in output.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
                print(f"caught    {label}  -> {len(red) or 'nonzero exit'} red")
                for line in red[:2]:
                    print(f"              {line}")
    finally:
        scratch.cleanup()

    print()
    if survivors:
        print(f"{len(survivors)} mutation(s) SURVIVED - pinned by no test:")
        for label, module in survivors:
            print(f"  - {label} ({module})")
        return 1
    print(f"all {len(MUTATIONS)} pieces of the fix are pinned by a test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
