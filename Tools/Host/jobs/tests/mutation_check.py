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

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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
    "record": Path("jobs/closure_record.py"),
    "deploy": Path("deploy_tools.py"),
    "checker": Path("jobs/check_closure_report.py"),
    # Bash is not exempt. Two of the defects Codex reproduced on 2026-09-21 were
    # in this file, and both had been "fixed" on the Python path beside it - the
    # shell kept its own older behaviour because nothing ever broke it on purpose.
    "shell": Path("codex-jobs/run_closure_review.sh"),
    "adapter": Path("jobs/claude_closure_review.py"),
    "prompt": Path("codex-jobs/make_closure_prompt.py"),
}

# Suites a mutation can be expected to kill, by key.
SUITES = {
    "result": Path("tests/test_review_result.py"),
    "closure": Path("jobs/tests/test_check_closure_report.py"),
    "readers": Path("jobs/tests/test_legacy_readers.py"),
    "ger": Path("ger/tests/test_ger_round.py"),
    "node": Path("ger/tests/test_ger_node.py"),
    "contract": Path("ger/tests/test_apply_contract.py"),
    "job_record": Path("jobs/tests/test_closure_record.py"),
    "deploy": Path("tests/test_deploy_tools.py"),
    "shell": Path("codex-jobs/tests/test_run_closure_review.py"),
    "adapter": Path("jobs/tests/test_claude_closure_review.py"),
}

# Copied so the suites import and navigate as they do in the tree. Never mutated.
SUPPORT = [
    Path("deploy_manifest.json"),
    # What the shell suite's own deployment step copies. Without these it builds
    # a workspace missing its helpers and every case fails at setup, which is a
    # crash and not a kill.
    Path("jobs/resolve_codex.py"),
    Path("jobs/check_job_result.py"),
    Path("nsc_paths.py"),
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

    ("record", "the exact-integer check on a job's exit code",
     "    if type(exit_code) is not int or exit_code != 0:",
     "    if exit_code:",
     "job_record", "test_a_false_exit_code_is_not_a_zero_one"),

    ("record", "the agreement between the record and the decoded result",
     "    if not validated.is_complete:",
     "    if False:",
     "job_record", "test_an_incomplete_result_is_not_a_ready_job"),

    ("record", "the requirement that a Claude record carries is_error false",
     "        if is_error is not False:",
     "        if False:",
     "job_record", "test_a_claude_record_missing_is_error_refuses"),

    ("record", "the rendered view's hash check in the job record",
     '    if record["output_sha256"] != sha256(view_bytes):',
     "    if False:",
     "job_record", "test_an_edited_view_refuses"),

    ("record", "the record's subject binding",
     "    if record.get(\"task_id\") != task_id:",
     "    if False:",
     "job_record", "test_a_record_about_another_task_refuses"),

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

    # ---- Astra message 16: the guards added after the Codex-path reproduction.

    ('record', 'the refusal of a float that equals zero as an exit code',
     '    if type(exit_code) is not int or exit_code != 0:',
     '    if isinstance(exit_code, bool) or exit_code != 0:',
     'job_record', 'test_a_float_zero_exit_code_is_not_a_zero_one'),

    ('record', "the refusal to publish over a finished job's record",
     '    if final.exists():',
     '    if False:',
     'job_record', 'test_publishing_over_a_finished_record_is_refused'),

    ('record', 'the shared answer to what evidence already exists',
     '    return [p for p in (result, view_path(result), metadata_path(result)) if p.exists()]',
     '    return []',
     'job_record', 'test_existing_evidence_names_every_file_that_is_there'),

    ('checker', "the host's pre-launch expectation about the contract",
     '    if args.contract_sha256 is not None and args.contract_sha256 != expected:',
     '    if False:',
     'closure', 'test_a_contract_that_changed_under_the_run_is_exit_8'),

    ('checker', 'the requirement that publication carries an expectation',
     '    if args.provider and not args.contract_sha256:',
     '    if False:',
     'closure', 'test_publishing_a_record_requires_the_expectation'),

    # Reinstates the ORIGINAL shape: decide from a parse taken before the shared
    # reader, then call the shared reader and keep only its hash. A mutation that
    # merely read twice was not this bug, and the test that caught it was vacuous.
    ('apply_contract', 'the verdict coming from the snapshot the reader validated',
     '    try:\n        job = closure_record.read_job(report_path, task_id=task_id,\n                                      reviewed_artifact_sha256=contract_sha)\n    except (closure_record.RecordError, review_result.ReviewResultError) as failure:\n        # BOTH types. read_job checks the record and then calls\n        # review_result.load, which raises its own error class - so catching only\n        # RecordError let a result that fails the reviewer\'s binding raise out of\n        # this function instead of refusing. That is the third time in this work\n        # that a narrow except missed a second exception type from the same call;\n        # the shape to look for is a helper that delegates to another module.\n        code = getattr(failure, "code", "invalid")\n        error(f"--post-commit-check-report {report_path} is not a finished job "\n              f"({code}): {failure}. If this review was handed over by a person "\n              f"rather than generated here, say so with --post-commit-check-import "\n              f"naming who carried it; a missing or broken job record never "\n              f"becomes an import by itself.")\n    record.update({\n        "verdict": job.result.recommendation,',
     '    try:\n        early = review_result.load(report_path.read_bytes(), task_id=task_id,\n                                   review_kind="closure",\n                                   reviewed_artifact_kind="contract",\n                                   reviewed_artifact_sha256=contract_sha)\n    except Exception:\n        early = None\n    try:\n        job = closure_record.read_job(report_path, task_id=task_id,\n                                      reviewed_artifact_sha256=contract_sha)\n    except (closure_record.RecordError, review_result.ReviewResultError) as failure:\n        # BOTH types. read_job checks the record and then calls\n        # review_result.load, which raises its own error class - so catching only\n        # RecordError let a result that fails the reviewer\'s binding raise out of\n        # this function instead of refusing. That is the third time in this work\n        # that a narrow except missed a second exception type from the same call;\n        # the shape to look for is a helper that delegates to another module.\n        code = getattr(failure, "code", "invalid")\n        error(f"--post-commit-check-report {report_path} is not a finished job "\n              f"({code}): {failure}. If this review was handed over by a person "\n              f"rather than generated here, say so with --post-commit-check-import "\n              f"naming who carried it; a missing or broken job record never "\n              f"becomes an import by itself.")\n    record.update({\n        "verdict": early.recommendation if early else job.result.recommendation,',
     'contract', 'test_the_verdict_and_the_hash_come_from_one_load'),

    ('shell', "the refusal of a previous run's evidence",
     'python -B "$HELPERS/closure_record.py" --refuse-existing "$RESULT" || exit 2',
     'true',
     'shell', 'test_evidence_from_an_earlier_run_is_refused_before_launch'),

    ('shell', 'hashing the contract BEFORE the provider can see it',
     '--contract-sha256 "$CONTRACT_SHA"',
     '--contract-sha256 "$(python -B "$HELPERS/closure_record.py" --sha256 "$CLONE/REVISED_CONTRACT.json")"',
     'shell', 'test_a_provider_that_rewrites_the_contract_is_refused'),


    # ---- Fable's review: guards that no test was pinning.

    ('adapter', 'the sentinel that makes a MISSING is_error visible',
     '    is_error = data.get("is_error", "<missing>")',
     '    is_error = data.get("is_error", False)',
     'adapter', 'test_a_wrapper_with_no_is_error_is_not_a_success'),

    ('adapter', 'the requirement that a wrapper says is_error false EXPLICITLY',
     '    if is_error is not False:',
     '    if is_error:',
     'adapter', 'test_only_an_explicit_false_counts_as_success'),

    ('adapter', 'the success-subtype requirement',
     '    if data.get("subtype") != "success":',
     '    if False:',
     'adapter', 'test_a_subtype_other_than_success_fails'),

    ('adapter', 'the shared JSON-shape test in the usage-limit check',
     '        if not review_result.looks_like_result(raw):',
     '        if not raw.lstrip().startswith("{"):',
     'adapter', 'test_a_valid_result_that_mentions_a_rate_limit_is_still_a_review'),

    ('result', 'the nesting limit becoming a refusal instead of a crash',
     '    except RecursionError as exc:',
     '    except ZeroDivisionError as exc:',
     'result', 'test_a_deeply_nested_value_refuses_rather_than_crashing'),

    ('ger_node', 'the protocol-failure gate on retries',
     '        if record.get("kind") == "protocol":',
     '        if False:',
     'node', 'test_a_protocol_failure_is_never_transient'),

    ('ger_round', "the tamper check on a record's copied verdict",
     '        if field in metadata and metadata[field] != value:',
     '        if False:',
     'ger', 'test_a_record_whose_copied_verdict_was_edited_is_reported'),


    ('prompt', 'the prompt landing where the runner reads it',
     'OUT = nsc_paths.work().path / "codex-jobs"',
     'OUT = HERE',
     'shell', 'test_the_prompt_builder_writes_where_the_runner_reads'),


    # ---- Fable's re-check of 501551218: three minors.

    ('adapter', 'the two launchers agreeing on what a code means',
     'CONTRACT_CHANGED = 8',
     'CONTRACT_CHANGED = 9',
     'adapter', 'test_the_two_launchers_agree_on_what_each_code_means'),

    ('adapter', 'a moved contract being distinguishable from an ordinary refusal',
     '        return CONTRACT_CHANGED',
     '        return SETUP_REFUSED',
     'adapter', 'test_a_contract_changed_during_the_run_is_refused'),

    ('adapter', 'a usage limit having a number of its own',
     'USAGE_LIMIT = 9',
     'USAGE_LIMIT = 3',
     'adapter', 'test_the_two_launchers_agree_on_what_each_code_means'),

    ('adapter', 'the never-launched promise behind code 2',
     '        return EVIDENCE_UNPUBLISHABLE',
     '        return SETUP_REFUSED',
     'adapter', 'test_nothing_returns_the_never_launched_code_after_launching'),

    ('adapter', 'an unusable wrapper not claiming nothing was launched',
     '        return PROVIDER_FAILED, "the CLI wrapper output is not an object", None',
     '        return SETUP_REFUSED, "the CLI wrapper output is not an object", None',
     'adapter', 'test_interpret_is_reached_only_after_the_provider_has_written'),

    ('adapter', 'a refused publication being reported as its own outcome',
     '        return EVIDENCE_UNPUBLISHABLE\n    return OK',
     '        return OK\n    return OK',
     'adapter', 'test_a_record_that_appears_mid_run_is_a_refusal_not_a_traceback'),

    # ---- the deployment record: three states that looked identical before it.

    ('deploy', 'telling an EDITED deployment from a merely stale one',
     '        elif live_hash != was:',
     '        elif False:',
     'deploy', 'test_an_edited_deployment_is_MODIFIED_not_stale'),

    ('deploy', 'noticing that the tracked file has moved on',
     '        elif live_hash != tracked_hash:',
     '        elif False:',
     'deploy', 'test_a_merge_makes_the_deployment_stale'),

    ('deploy', 'the refusal to record a commit that does not describe the bytes',
     '    if dirty:',
     '    if False:',
     'deploy', 'test_it_refuses_to_deploy_from_a_dirty_checkout'),

    ('deploy', 'line-ending normalisation before hashing',
     '    return data.replace(b"\\r\\n", b"\\n").replace(b"\\r", b"\\n")',
     '    return data',
     'deploy', 'test_a_crlf_deployment_of_an_lf_file_is_current'),

    ('deploy', 'a deployment with no record not being called current',
     '            states[relative] = CURRENT if live_hash == tracked_hash else UNRECORDED',
     '            states[relative] = CURRENT',
     'deploy', 'test_a_deployment_with_no_record_cannot_be_called_current'),

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


def workers(requested: int | None = None) -> int:
    """How many mutations to run at once.

    Every unit of work is a subprocess that spends most of its life waiting, so
    this can exceed the core count without starving anything. Capped anyway: the
    shell suite spawns bash, git and python per test, and a machine thrashing its
    disk is not faster.
    """
    if requested:
        return max(1, requested)
    from_env = os.environ.get("NSC_MUTATION_WORKERS")
    if from_env and from_env.isdigit() and int(from_env) > 0:
        return int(from_env)
    return max(1, min(8, (os.cpu_count() or 2)))


def one_mutation(mutation, expected: dict[str, int]) -> tuple[str, bool, str]:
    """Stage a private tree, break one guard in it, run the named suite, score.

    A tree of its own per mutation is what makes concurrency safe here, and it
    also retires the old restore-after-each step: nothing is shared, so a crash
    cannot leave a guard disabled in a copy the next mutation would use.
    """
    file_key, what, old, new, suite_key, must_die = mutation
    with tempfile.TemporaryDirectory(prefix="protocol-mutation-") as tmpdir:
        files, suites = stage(Path(tmpdir))
        path = files[file_key]
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            return what, False, f"ANCHOR LOST: matched {text.count(old)}, expected 1"
        path.write_text(text.replace(old, new), encoding="utf-8")
        code, output = run(suites[suite_key])
    killed, reason = score(code, output, must_die, expected[suite_key])
    return what, killed, reason


def run(suite: Path) -> tuple[int, str]:
    # One stream, not two concatenated. unittest writes its summary to stderr
    # and a suite's own prints go to stdout, so `stdout + stderr` puts them in
    # an order neither stream had - which is the defect run_tool_tests.py
    # documents and fixes for ITSELF, while this file handed the reassembled
    # text to that same tested interpretation (Fable, 2026-09-21). Harmless for
    # today's suites and wrong on the day one of them prints something that
    # looks like a summary.
    proc = subprocess.run([sys.executable, "-B", "-u", str(suite)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, cwd=str(suite.parent))
    return proc.returncode, proc.stdout


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Break each guard on purpose and require the named test to fail.")
    parser.add_argument("--workers", type=int, default=None,
                        help="mutations to run at once; default min(8, cpus), "
                             "or NSC_MUTATION_WORKERS")
    args = parser.parse_args(argv)

    missing = [rel for rel in list(FILES.values()) + list(SUITES.values()) + SUPPORT
               if not (HOST / rel).is_file()]
    if missing:
        for rel in missing:
            print(f"missing {HOST / rel}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="protocol-mutation-") as tmpdir:
        files, suites = stage(Path(tmpdir))

        # Each baseline must itself be a COMPLETED, green, non-empty run, and its
        # collected count is kept. Astra MJ-MUT-02: a baseline exit of 0 alone
        # also accepts a run that collected nothing, and without the count a
        # mutated run collecting one test scored as a kill against a baseline of
        # sixty-five.
        expected: dict[str, int] = {}
        # Baselines share the one staged tree, unmutated, so they are safe to
        # overlap: nothing writes to it.
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=workers(args.workers)) as pool:
            baselines = {key: pool.submit(run, suite)
                         for key, suite in suites.items()}
        for key, future in baselines.items():
            code, output = future.result()
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

    # The staged tree above was only needed for the baselines; each mutation
    # stages its own. Outside the `with`, so the baseline copy is already gone.
    count = workers(args.workers)
    print(f"{len(MUTATIONS)} mutations, {count} at a time")
    started = time.time()

    outcomes: dict[str, tuple[bool, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        futures = {pool.submit(one_mutation, m, expected): m[1] for m in MUTATIONS}
        for future in concurrent.futures.as_completed(futures):
            what, killed, reason = future.result()
            outcomes[what] = (killed, reason)

    # Printed in TABLE order, not completion order, so two runs are diffable.
    survivors: list[str] = []
    for mutation in MUTATIONS:
        what = mutation[1]
        killed, reason = outcomes[what]
        if killed:
            print(f"killed       {what}")
        elif reason.startswith("ANCHOR LOST"):
            print(f"ANCHOR LOST  {what}: {reason[len('ANCHOR LOST: '):]}")
            survivors.append(f"{what} (anchor lost)")
        else:
            print(f"SURVIVED     {what}")
            print(f"             {reason}")
            survivors.append(what)

    print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} mutations killed "
          f"in {time.time() - started:.0f}s")
    for survivor in survivors:
        print(f"  SURVIVOR: {survivor}")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
