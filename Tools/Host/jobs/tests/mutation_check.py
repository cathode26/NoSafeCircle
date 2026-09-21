#!/usr/bin/env python
"""Break a guard on purpose; every break must turn the NAMED test red, by failing.

A guard with green tests proves nothing until you have seen the tests fail. That
mattered here more than usual: this checker family has been fixed nine times, and
each fix looked green while the next counterexample still passed. Green was never
the evidence.

**What a kill requires, and why each condition is here.**

Astra's round-7 finding 3 was that this harness scored a CRASH as a kill: the
pattern matched `FAIL:` and `ERROR:` alike, so a mutation that raised NameError
in the named test - detecting nothing - counted as caught. Every mutation total
in this file's history was measured with that instrument, which is why none of
them are quoted as evidence any more. A kill now requires all of:

  1. the suite ran to completion and printed its `Ran N tests` summary;
  2. N > 0 - a suite that collected nothing cannot have detected anything;
  3. ZERO errors in the run. An error is the mutation breaking execution, not a
     test observing a behaviour change;
  4. the process exited non-zero;
  5. the test NAMED for this mutation is among the FAILURES.

Condition 5 is not decoration either. A mutation killed by some OTHER test is
not evidence for the guard you think you are testing - it usually means the
fixture is refused for a second reason, which is exactly how two round-2
mutations survived undetected.

**Scope.** The old Markdown recogniser's mutation set is gone with it; its count
is deliberately not a target. These mutations cover the guards that now carry the
protocol: the strict decoder, the host binding, the single entry point, the
derived-view marker, and the record checks on a GER decision.

Works on a COPY in a temp directory - never the tracked files - so killing it
mid-run cannot leave a guard disabled.

Run:  python -B tests/mutation_check.py      (from Tools/Host/jobs)
Exit: 0 every mutation killed by the test that names it; 1 otherwise.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FAILURE = re.compile(r"^FAIL: (\S+)", re.MULTILINE)
ERROR = re.compile(r"^ERROR: (\S+)", re.MULTILINE)
RAN = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)

HERE = Path(__file__).resolve().parent
HOST = HERE.parent.parent

# The same tested interpretation every suite verdict goes through, rather than a
# second slightly different summary parser living here (Astra, message 8).
sys.path.insert(0, str(HOST))
from run_tool_tests import terminal_summary  # noqa: E402

# Mutated files, by key, relative to Tools/Host.
FILES = {
    "result": Path("review_result.py"),
    "legacy": Path("jobs/legacy_closure_markdown.py"),
    "ger_round": Path("ger/ger_round.py"),
    "ger_node": Path("ger/ger_node.py"),
    "apply_contract": Path("ger/apply_contract.py"),
}

# Suites a mutation can be expected to kill, by key.
SUITES = {
    "result": Path("tests/test_review_result.py"),
    "closure": Path("jobs/tests/test_check_closure_report.py"),
    "readers": Path("jobs/tests/test_legacy_readers.py"),
    "ger": Path("ger/tests/test_ger_round.py"),
    "node": Path("ger/tests/test_ger_node.py"),
    "contract": Path("ger/tests/test_apply_contract.py"),
}

# Copied so the suites import and navigate as they do in the tree. Never mutated.
SUPPORT = [
    Path("jobs/check_closure_report.py"),
    Path("ger/ger_decision_revision.py"),
    Path("ger/main_write.py"),
    Path("ger/tests/ger_fixtures.py"),
    Path("codex-jobs/templates/contract-closure-review-prompt.md"),
]

# (file key, what the mutation removes, find, replace, suite key, the test that must die)
MUTATIONS = [
    ("result", "the oversize limit",
     "    if len(raw) > MAX_BYTES:",
     "    if False:",
     "result", "test_oversize_refuses_before_parsing"),

    ("result", "duplicate-key detection",
     "                         object_pairs_hook=_no_duplicate_keys,",
     "                         object_pairs_hook=dict,",
     "result", "test_duplicate_keys_refuse"),

    ("result", "the refusal of NaN and Infinity",
     "                         parse_constant=_no_constants)",
     "                         parse_constant=float)",
     "result", "test_nan_and_infinity_refuse"),

    ("result", "the closed field set",
     "    unknown = sorted(set(obj) - set(FIELDS))",
     "    unknown = []",
     "result", "test_an_unknown_field_refuses"),

    ("result", "bool being rejected as schema_version",
     "    if isinstance(version, bool) or not isinstance(version, int):",
     "    if not isinstance(version, int):",
     "result", "test_schema_version_true_is_not_one"),

    ("result", "the hash format check",
     "    if len(digest) != 64 or not set(digest) <= _HEX:",
     "    if False:",
     "result", "test_bad_hash_shapes_refuse"),

    ("result", "the nonempty report requirement",
     "    if not report_markdown.strip():",
     "    if False:",
     "result", "test_an_empty_report_refuses"),

    ("result", "the ban on a recommendation in an incomplete review",
     "        if recommendation is not None:",
     "        if False:",
     "result", "test_incomplete_may_not_carry_a_recommendation"),

    ("result", "the family vocabulary check",
     "        if recommendation not in allowed:",
     "        if False:",
     "result", "test_the_two_vocabularies_do_not_cross"),

    ("result", "the lone-surrogate check",
     '        value.encode("utf-8")                    # type: ignore[union-attr]',
     "        pass",
     "result", "test_a_lone_high_surrogate_is_refused"),

    ("result", "the artifact hash binding",
     "    if result.reviewed_artifact_sha256 != expected_digest:",
     "    if False:",
     "result", "test_changed_reviewed_bytes_refuse"),

    ("result", "load's binding step, leaving a schema-only entry point",
     "    return bind(decode(raw),",
     "    return (lambda r, **_: r)(decode(raw),",
     "result", "test_load_enforces_the_binding"),

    ("legacy", "the derived-view guard in the closure reader",
     "    if review_result.is_derived_view(text):",
     "    if False:",
     "closure", "test_the_legacy_reader_refuses_the_derived_view"),

    ("result", "the shared derived-view test itself",
     "    return DERIVED_VIEW_MARKER in (text or \"\")",
     "    return False",
     "readers", "test_each_reader_refuses_the_same_text_marked_as_derived"),

    ("ger_round", "the rendered view's hash check",
     "    elif recorded_view != sha256_bytes(view.read_bytes()):",
     "    elif False:",
     "ger", "test_an_edited_human_view_is_refused"),

    ("ger_round", "the unfinished-review prerequisite check",
     '        unfinished = decision_not_finished(packet, prior, identity["task_id"])',
     "        unfinished = None",
     "ger", "test_build_prompt_refuses_an_unfinished_prior_decision"),

    ("ger_round", "a failed record validation blocking a prerequisite",
     '        return f"its record does not validate: {error}"',
     "        return None",
     "ger", "test_a_tampered_view_is_not_a_finished_prerequisite"),

    ("ger_node", "the retry gate on a successful provider call",
     '        if evidence.get("exit_code") == 0 and not evidence.get("is_error"):',
     "        if False:",
     "node", "test_a_successful_provider_call_is_never_transient"),

    ("apply_contract", "the refusal of a substantive override after a JSON review",
     "    if not human_exception:",
     "    if False:",
     "contract", "test_a_substantive_override_after_a_json_review_is_refused"),

    ("ger_round", "the recorded result hash check",
     "    if recorded != actual:",
     "    if False:",
     "ger", "test_a_tampered_result_is_refused"),

    ("ger_round", "the provider-evidence check on a published record",
     '        if metadata.get("exit_code") != 0:',
     "        if False:",
     "ger", "test_a_record_of_provider_failure_is_refused"),

    ("ger_round", "the refusal of an unknown protocol",
     '    if protocol != "json-v1":',
     "    if False:",
     "ger", "test_an_unknown_protocol_is_refused"),

    ("ger_round", "the refusal of a json-v1 record with no result file",
     "    if not result_path.is_file():",
     "    if False:",
     "ger", "test_a_declared_json_round_with_no_result_is_broken_not_legacy"),

    ("ger_round", "checks running before the record is published",
     "    problems = check_run(run, output)",
     "    problems = []",
     "ger", "test_a_nonzero_exit_does_not_publish_metadata"),
]


def stage(tmp: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    """A copy that keeps the layout the suites navigate by."""
    host = tmp / "Host"
    every = list(FILES.values()) + list(SUITES.values()) + SUPPORT
    for relative in every:
        target = host / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HOST / relative, target)
    return ({key: host / rel for key, rel in FILES.items()},
            {key: host / rel for key, rel in SUITES.items()})


def run(suite: Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-B", "-u", str(suite)],
                          capture_output=True, text=True, cwd=str(suite.parent))
    return proc.returncode, proc.stdout + proc.stderr


def score(code: int, output: str, must_die: str,
          expected_tests: int | None = None) -> tuple[bool, str]:
    """Was this mutation KILLED - detected by the named test failing an assertion?

    Pure, so it can be tested without running a suite. Returns (killed, reason);
    the reason names which condition was not met rather than saying only
    "survived".

    The summary is read by `run_tool_tests.terminal_summary`, the same tested
    interpretation every suite's own verdict goes through, rather than a second
    slightly different parser living here.

    Two conditions come from Astra's MJ-MUT findings:

    - **A `Ran N tests` line is not proof the reporter finished.** unittest prints
      it BEFORE its terminal verdict, so a run interrupted in between showed a
      named FAIL and a count and scored as a kill. `score(-9, truncated, target)`
      returned True. The terminal `FAILED` summary is now required.
    - **The collected count must match the baseline's.** A mutated run that
      collected one test - because the mutation broke collection - was accepted
      against a baseline of 65. `expected_tests` is the baseline count and is
      compared, not assumed.
    """
    tests, verdict, counts = terminal_summary(output)
    if tests is None:
        return False, "the suite printed no 'Ran N tests' summary; it did not complete"
    if verdict is None:
        return False, (f"the suite printed 'Ran {tests} tests' but never reached its "
                       f"terminal summary; it was interrupted, not conclusive")
    if tests == 0:
        return False, "the suite collected zero tests, so it detected nothing"
    if expected_tests is not None and tests != expected_tests:
        return False, (f"the suite collected {tests} tests but its baseline collected "
                       f"{expected_tests}; the mutation changed what runs, so what "
                       f"ran proves nothing about what it detects")

    errors = sorted(set(ERROR.findall(output)))
    if errors or counts.get("errors"):
        named = ", ".join(errors[:4]) or f"{counts.get('errors')} in the summary"
        return False, ("the mutation caused execution ERRORS, which is breakage, "
                       "not detection: " + named)
    if code == 0 or verdict != "FAILED":
        return False, "the suite stayed green"
    if not counts.get("failures"):
        return False, "the terminal summary reports no failures"

    failures = set(FAILURE.findall(output))
    if must_die not in failures:
        return False, (f"expected {must_die} to FAIL; what failed was "
                       + (", ".join(sorted(failures)) or "nothing identifiable"))
    return True, ""


def main() -> int:
    missing = [rel for rel in list(FILES.values()) + list(SUITES.values()) + SUPPORT
               if not (HOST / rel).is_file()]
    if missing:
        for rel in missing:
            print(f"missing {HOST / rel}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="protocol-mutation-") as tmpdir:
        files, suites = stage(Path(tmpdir))
        pristine = {key: path.read_text(encoding="utf-8") for key, path in files.items()}

        # Each baseline must itself be a COMPLETED, green, non-empty run, and its
        # collected count is kept. Astra MJ-MUT-02: a baseline exit of 0 alone
        # also accepts a run that collected nothing, and without the count a
        # mutated run collecting one test scored as a kill against a baseline of
        # sixty-five.
        expected: dict[str, int] = {}
        for key, suite in suites.items():
            code, output = run(suite)
            tests, verdict, counts = terminal_summary(output)
            problem = None
            if code != 0 or verdict != "OK":
                problem = "it is not green"
            elif tests is None:
                problem = "it printed no terminal summary"
            elif tests == 0:
                problem = "it collected zero tests"
            elif counts.get("errors") or counts.get("failures"):
                problem = "its summary reports failures or errors"
            if problem:
                print(f"the unmutated {key} suite cannot be a baseline: {problem}. "
                      f"Fix that before mutating.", file=sys.stderr)
                print(output[-2000:], file=sys.stderr)
                return 1
            expected[key] = tests
            print(f"baseline {key}: {tests} tests, {verdict}")
        print()

        survivors: list[str] = []
        for file_key, what, old, new, suite_key, must_die in MUTATIONS:
            path, text = files[file_key], pristine[file_key]
            if text.count(old) != 1:
                print(f"ANCHOR LOST  {what}: matched {text.count(old)}, expected 1")
                survivors.append(f"{what} (anchor lost)")
                continue

            path.write_text(text.replace(old, new), encoding="utf-8")
            try:
                code, output = run(suites[suite_key])
            finally:
                path.write_text(text, encoding="utf-8")

            killed, reason = score(code, output, must_die, expected[suite_key])
            if killed:
                print(f"killed       {what}")
            else:
                print(f"SURVIVED     {what}")
                print(f"             {reason}")
                survivors.append(what)

        print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} mutations killed")
        for survivor in survivors:
            print(f"  SURVIVOR: {survivor}")
        return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
