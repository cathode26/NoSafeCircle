#!/usr/bin/env python
"""The shard dispatcher must not report success for a run it did not verify.

Run:
    python -B run_reset_shards_smoke_test.py

The dispatcher's whole justification is that sharding cannot quietly reduce
coverage: it asks the suite what cases exist and checks that they all ran. The
first version collected that inventory AFTER the shards and only validated when
the inventory command happened to succeed -- so the one situation it existed
for, not knowing what should have run, was the situation it skipped. Inventory
exit 9 with zero cases reported produced driver exit 0. Found by Codex in
review, not by this file, which did not exist yet.

Every case here drives the real `main()` against a stub suite, so the guard is
exercised rather than described. The stub makes this run in under a second; the
real suite takes about five minutes, and a guard nobody runs is the thing being
guarded against.
"""
from __future__ import annotations

import importlib.util
import io
import pathlib
import contextlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CASES = ["case_alpha", "case_beta", "case_gamma", "case_delta"]


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def load_dispatcher():
    spec = importlib.util.spec_from_file_location(
        "run_reset_shards_under_test", HERE / "run_reset_shards.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STUB = '''#!/usr/bin/env python
"""Stub suite: enough --list/--shard behaviour to drive the dispatcher."""
import sys

CASES = {cases!r}
LIST_EXIT = {list_exit}
LIST_EMPTY = {list_empty}
DROP = {drop!r}
FAIL_SHARD = {fail_shard!r}

argv = sys.argv[1:]
if "--list" in argv:
    if LIST_EXIT:
        sys.stderr.write("stub inventory failure\\n")
        raise SystemExit(LIST_EXIT)
    if not LIST_EMPTY:
        for name in CASES:
            print(f"{{name}}\\tundo\\t1.0")
    raise SystemExit(0)

index, count = 0, 1
if "--shard" in argv:
    index, count = (int(p) for p in argv[argv.index("--shard") + 1].split("/"))

mine = [c for n, c in enumerate(CASES) if n % count == index]
if FAIL_SHARD == index:
    for name in mine[:1]:
        print(f"PASS {{name}}")
    sys.stderr.write("stub shard failure\\n")
    raise SystemExit(3)
for name in mine:
    if name == DROP:
        continue
    print(f"PASS {{name}}")
print("stub: PASS")
raise SystemExit(0)
'''


def drive(*, list_exit=0, list_empty=False, drop=None, fail_shard=None,
          shards=2):
    """Run the real main() against a stub suite; return (exit code, output)."""
    module = load_dispatcher()
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="dispatcher-test-"))
    stub = scratch / "stub_suite.py"
    stub.write_text(STUB.format(cases=CASES, list_exit=list_exit,
                                list_empty=list_empty, drop=drop,
                                fail_shard=fail_shard), encoding="utf-8")
    module.SUITE = stub

    captured = io.StringIO()
    argv = ["--repo", str(scratch), "--shards", str(shards),
            "--workers", str(shards), "--quiet"]
    saved, sys.argv = sys.argv, ["run_reset_shards.py", *argv]
    try:
        with contextlib.redirect_stdout(captured):
            try:
                code = module.main()
            except SystemExit as exit_error:      # read_inventory refuses here
                code = exit_error.code
    finally:
        sys.argv = saved
    return code, captured.getvalue()


def test_every_case_running_once_is_the_only_success() -> None:
    code, output = drive()
    require(code == 0, f"a complete run must exit 0, got {code}\n{output}")
    require("cases expected   : 4" in output,
            f"the inventory size must be reported\n{output}")


def test_a_dropped_case_fails_even_though_every_shard_exited_zero() -> None:
    """The defect this file exists for: shards all pass, coverage is smaller."""
    code, output = drive(drop="case_gamma")
    require(code != 0,
            "a run that silently skipped a case must not exit 0; that is a "
            f"coverage reduction reported as a speed-up\n{output}")
    require("case_gamma" in output,
            f"the missing case must be named, not just counted\n{output}")


def test_a_failed_inventory_refuses_before_launching_anything() -> None:
    code, output = drive(list_exit=9)
    require(code != 0,
            f"an unusable inventory must refuse, got exit {code}\n{output}")
    require("shard 0/" not in output,
            "no shard may be launched when the expectation is unknown: "
            f"refusing afterwards is what produced the original defect\n{output}")


def test_an_empty_inventory_refuses_rather_than_passing_vacuously() -> None:
    code, output = drive(list_empty=True)
    require(code != 0,
            "an empty inventory must refuse: every partition satisfies an "
            f"empty expectation\n{output}")


def test_a_child_failure_propagates_its_own_exit_code() -> None:
    code, output = drive(fail_shard=1)
    require(code == 3,
            f"the child's exit code must survive, got {code}\n{output}")


def main() -> int:
    test_every_case_running_once_is_the_only_success()
    test_a_dropped_case_fails_even_though_every_shard_exited_zero()
    test_a_failed_inventory_refuses_before_launching_anything()
    test_an_empty_inventory_refuses_rather_than_passing_vacuously()
    test_a_child_failure_propagates_its_own_exit_code()
    print("run_reset_shards_smoke_test: PASS (5 tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
