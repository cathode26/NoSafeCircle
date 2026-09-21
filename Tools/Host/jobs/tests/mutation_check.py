#!/usr/bin/env python
"""Break check_closure_report.py on purpose; every break must turn some test red.

A guard with green tests proves nothing until you have seen the tests fail.
This mattered here more than usual: the closure checker has now been fixed
twice, and round 1's fix looked green while five of Astra's counterexamples
still passed. Green was never the evidence.

It earned its place immediately. Two of the round-2 tests passed for the WRONG
REASON - their fixtures ended with a trailing line, so removing the
fence-and-quote rule left them refused for non-terminality instead, and both
mutations survived. complete=False either way. That is the same defect class
the file exists to remove, reproduced in the tests written to close it. They
now assert the refusal's REASON, which is what they were always claiming.

Works on a COPY in a temp directory - never the tracked files - so killing it
mid-run cannot leave the checker with a guard disabled. The copy keeps the real
relative layout, because the suite reaches the prompt template through it.

Run:  python -B tests/mutation_check.py      (from Tools/Host/jobs)
Exit: 0 every mutation killed by the test that names it; 1 otherwise.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOBS = HERE.parent
HOST = JOBS.parent

TOOL = JOBS / "check_closure_report.py"
TESTS = HERE / "test_check_closure_report.py"
TEMPLATE = HOST / "codex-jobs" / "templates" / "contract-closure-review-prompt.md"

TOOL_FILE, TEMPLATE_FILE = "tool", "template"

# (file, what the mutation restores or removes, find, replace, the test that must die)
#
# Naming the expected test is not decoration. A mutation killed by some OTHER
# test is not evidence for the guard you think you are testing - it usually
# means the fixture is refused for a second reason, which is exactly how the
# two fence/quote cases first passed.
MUTATIONS = [
    (TOOL_FILE, "block quotes read as the report speaking",
     "        if QUOTE.match(line):\n            continue",
     "        if False:\n            continue",
     "test_a_verdict_inside_a_block_quote_is_an_example_not_a_verdict"),

    (TOOL_FILE, "fenced blocks read as the report speaking",
     "        opener = FENCE.match(line)",
     "        opener = None",
     "test_a_verdict_inside_a_fenced_block_is_an_example_not_a_verdict"),

    (TOOL_FILE, "round 1's window: the verdict need not be the last line",
     "            if number != last:",
     "            if False:",
     "test_a_one_line_retraction_after_the_footer_is_refused"),

    (TOOL_FILE, "round 1: a recommendation only has to START with a known name",
     "        if value not in RECOMMENDATIONS:",
     "        if not any(value.startswith(r) for r in RECOMMENDATIONS):",
     "test_the_echoed_options_line_is_not_a_choice"),

    (TOOL_FILE, "round 1: identities counted by distinct value, not occurrence",
     "    elif len(identities) > 1:",
     "    elif len({stated_value(r).lower() for _, r in identities}) > 1:",
     "test_the_same_identity_stated_twice_is_refused"),

    (TOOL_FILE, "round 1: the identity matched anywhere in the line, not exactly",
     'HEX16 = re.compile(r"^[0-9a-fA-F]{16}$")',
     'HEX16 = re.compile(r"[0-9a-fA-F]{16}")',
     "test_an_overlong_hash_is_not_a_contract_identity"),

    # The template is half the defect: a reviewer echoing it faithfully
    # produced two of Astra's counterexamples. These two prove the binding
    # between the format we hand out and the checker that judges it is live.
    (TEMPLATE_FILE, "the template trails text after the verdict again",
     "Final recommendation: <one of commit_contract, commit_contract_then_decompose, revise>",
     "Final recommendation: <one of commit_contract, commit_contract_then_decompose, revise>\n"
     "(Use revise only if a ledger item is UNRESOLVED as blocking or major.)",
     "test_nothing_in_the_template_follows_the_recommendation"),

    (TEMPLATE_FILE, "the template lists the options as the value again",
     "Final recommendation: <one of commit_contract, commit_contract_then_decompose, revise>",
     "Final recommendation: commit_contract | commit_contract_then_decompose | revise",
     "test_the_template_does_not_show_the_options_as_the_value"),
]


def stage(tmp: Path) -> dict[str, Path]:
    """A copy that keeps the layout the suite navigates by."""
    host = tmp / "Host"
    (host / "jobs" / "tests").mkdir(parents=True)
    (host / "codex-jobs" / "templates").mkdir(parents=True)

    staged = {
        TOOL_FILE: host / "jobs" / TOOL.name,
        TEMPLATE_FILE: host / "codex-jobs" / "templates" / TEMPLATE.name,
    }
    shutil.copy2(TOOL, staged[TOOL_FILE])
    shutil.copy2(TEMPLATE, staged[TEMPLATE_FILE])
    shutil.copy2(TESTS, host / "jobs" / "tests" / TESTS.name)
    return staged


def run(suite: Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-B", str(suite)],
                          capture_output=True, text=True, cwd=str(suite.parent))
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    for required in (TOOL, TESTS, TEMPLATE):
        if not required.is_file():
            print(f"missing {required}", file=sys.stderr)
            return 1

    with tempfile.TemporaryDirectory(prefix="closure-mutation-") as tmpdir:
        tmp = Path(tmpdir)
        staged = stage(tmp)
        suite = tmp / "Host" / "jobs" / "tests" / TESTS.name
        pristine = {key: path.read_text(encoding="utf-8") for key, path in staged.items()}

        code, output = run(suite)
        if code != 0:
            print("the unmutated suite is not green - fix that before mutating",
                  file=sys.stderr)
            print(output[-2000:], file=sys.stderr)
            return 1
        print(f"baseline: {output.strip().splitlines()[-1]}\n")

        survivors: list[str] = []
        for key, what, old, new, must_die in MUTATIONS:
            path, text = staged[key], pristine[key]
            if text.count(old) != 1:
                print(f"ANCHOR LOST  {what}: matched {text.count(old)}, expected 1")
                survivors.append(what)
                continue

            path.write_text(text.replace(old, new), encoding="utf-8")
            try:
                code, output = run(suite)
            finally:
                path.write_text(text, encoding="utf-8")

            if code == 0:
                print(f"SURVIVED     {what}")
                survivors.append(what)
            elif must_die not in output:
                print(f"WRONG TEST   {what}")
                print(f"             {must_die} was expected to fail and did not")
                survivors.append(f"{what} (killed by the wrong test)")
            else:
                print(f"killed       {what}")

        print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} mutations killed")
        for survivor in survivors:
            print(f"  SURVIVOR: {survivor}")
        return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
