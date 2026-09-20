VERDICT: FIX FIRST

Two of the three blocking findings are closed: the clone guard and the account cache. The `--allow-tool` guard is still open in two rule shapes. `--out` has a hole in the same guard that round 1 (mine) missed. No provider, Docker or Unity was run; every probe was a dry-run or used the suite's fakes in `C:\nscrev\review-tmp\run-job-r2`.

Findings (most severe first):

- **[blocking] run_job.py:367, 378-385, 435-445: several rules packed into one `--allow-tool` value pass the guard. The guard accepting the value is reproduced; the CLI splitting it is theoretical.**
  - `advice --brief x --allow-tool "Read(a),Bash,Agent,Write,Read(b)" --dry-run` exits 0 with `--allowedTools Read Glob Grep "Read(a),Bash,Agent,Write,Read(b)"`.
  - `"Glob(x) Write(y)"`, `"Grep(a) Task Read(b)"` and `"mcp__x(a),Write(b)"` pass the same way.
  - `TOOL_RULE_RE` takes the greedy `(.*)` as one specifier, so the name is `Read` and everything up to the last `)` is ignored. `guard_tool_list` uses the same parser, so it passes too.
  - `claude --help` on 2.1.271 says the value is a "Comma or space-separated list … (e.g. "Bash(git *) Edit")", so the CLI splits what the guard saw as one rule.
  - I did not run the split itself, because that needs a provider run.
  - No test covers a `,` or a `) ` inside a rule.

- **[blocking] run_job.py:416-421: only an empty Bash specifier is refused. Reproduced.**
  - `--allow-tool "Bash(*)"`, `"Bash( )"`, `"Bash(:*)"`, `"Bash(**)"` and `"bash(*)"` all reach the argv on `advice`, which is Opus with `dontAsk` and `--add-dir C:/NSC`.
  - `Bash(*)` is unrestricted shell, so round 1's blocking scenario is reached with a different rule shape.
  - Related, not blocking: `--allow-bash powershell`, `cmd`, `bash`, `python` and `sh` are accepted by design, so "read-only host type" is only nominal. The README should say so.

- **[blocking] run_job.py:456-465: `guard_out` refuses paths under `C:\NSC` but not paths that contain it. Reproduced by dry-run.**
  - `clone-edit --clone <ok> --out C:/ --dry-run` exits 0 with `-v C:/:/out`.
  - `C:\`, `C:/Users/..`, `//localhost/C$` and `//?/C:/` give the same result.
  - A read-write job would then have `C:\NSC` writable at `/out/NSC`.
  - This predates the fixes and I missed it in round 1. It is the same guard and the same kind of plain-argument bypass.
  - The Docker mount itself was not run, so that step is theoretical.

- **[major] tests/review_mutation_check.py:152-172: the harness rewrites the live `run_job.py` in place. The kill hazard is from reading the code; the line-ending change is reproduced.**
  - For about 12 seconds the tool that agents run has one guard switched off at a time.
  - If the harness is killed or hits a tool timeout, `finally` does not run and the disabled guard stays in the file silently.
  - The `.bak` has LF endings and head has CRLF, so all 1343 lines changed endings. That is either `write_text` in the harness or the author's editor.
  - The harness works unchanged on a copy, which is how I ran it.

- **[major] run_job.py:1193-1196, 1230: a background job with relative paths never runs, and the parent still reports success. Reproduced.**
  - `--background --brief reljob.prompt.md --out relout` from a working directory other than `NSCREV` makes the parent print "started in background" and exit 0.
  - The child runs with `cwd=NSCREV` and ends with `REFUSED: brief … does not exist`. There is no json and no telemetry row.
  - The refusal is visible only in `relout/background-stderr.log`.
  - `cwd=NSCREV` predates the fixes, but this is what remains of the "refused background job is invisible" major.

- **[major] README.md:165-166, 256: the README was not updated.**
  - It still documents the 24-hour cache and still says "Never set them" as the only barrier on the env overrides.
  - It has no mention of `NSC_RUN_JOB_TESTING`, `account_source`, `usage_account` or `background-stderr.log`.

- **[minor] run_job.py:1222: a background job without `--name` logs to the shared `JOBS_DIR/background/`, not the job's own folder. Reproduced.** The test covers only an explicit `--out`.

- **[minor] run_job.py:1278-1279: the comment is wrong, because the child asks `auth status` again. Reproduced.** I counted 2 container starts per background Docker job. That is the safe direction; it is just not what the comment says.

- **[minor] run_job.py:1318-1319: `host_account()` runs twice. Reproduced.** Every foreground job, Docker jobs included, spawns the host CLI three times: `/usage` plus two `auth status`. The round-1 console-flash minor is now worse.

- **[minor] run_job.py:334: `\\localhost.\C$\…` raises an uncaught `OSError` (WinError 1326), giving a traceback and exit 1. Reproduced.** It still fails closed.

- **[minor] tests/test_run_job.py:885: `SyntaxWarning: invalid escape sequence` in a docstring.**

- **[minor] Test gaps. By reading.**
  - `test_usage_percentages_say_which_account_they_describe` asserts only that the key is present.
  - No mutation reverts `usage_account`, the `JOBS_DIR.mkdir` skip on dry-run, or `same_path`.
  - The spelling tests skip when `C:\NSC` is absent and depend on the admin share.
  - There are no junction or 8.3 short-name tests. Both spellings pass when probed by hand.

- **[minor] `--timeout` leaving the container running.**
  - Deferring it is acceptable: `--max-turns` bounds the spend and the default is no timeout.
  - "Filed" is not true. `nsc-pipeline-problems.md` has no `run_job` entry and the README says nothing about it.
  - The stated obstacle is weak. `docker compose run --name <unique>` plus `docker kill` on timeout needs no stored container id.
  - Please file it, add a README sentence, and make the exit-124 log line say the container may still be running.

What held:
- **Clone guard.** About 35 spellings were refused:
  - the three round-1 spellings;
  - `\\?\UNC\`, `\\.\`, `\\[::1]\`, the computer name, and `NOSAFE~1`;
  - trailing dot, trailing space, `\.`, mixed separators and `::$INDEX_ALLOCATION`;
  - junctions to the repo, to `C:\NSC\NSC` and to `C:\NSC`;
  - the same junctions reached over UNC and `\\?\`;
  - a `subst Q:` drive, and a non-canonical clone under `C:\NSC` reached by every route.
- **Non-existent `--clone`.** It is refused before any comparison, so the string fallback cannot be reached. For `--out`, the walk up the path hits an existing ancestor first, so the fallback did not open anything I tried.
- **Account cache.** With the cache poisoned and the container on a wrong account, the job is refused with exit 2 and `auth status` is asked once. Nothing in `run_job.py` reads any file in `JOBS_DIR` as trusted input. A stale `account-cache.json` is still in the live folder and is inert.
- **stdin.** With an open pipe on stdin, 7 account tests ran in 2.5 s. No caller passes `input=`.
- **Dry-run.** It creates nothing, and a real run afterwards creates the folders itself.
- **Background account guard.** `--background` with a wrong account is refused in the parent. `--allow-account` reaches the child, and the telemetry row names the account that paid.
- **Live telemetry.** The four `jobs.jsonl` rows parse. The only consumer I found is a README one-liner that reads `cost_usd`.
- **Mutation harness.** All 13 mutations really disable the guard they name.

Tests re-run by reviewer:
- `python -B tests/test_run_job.py` with `TEMP=TMP=C:/nscrev/tmp/rr`: 101 tests, OK, 25 s.
- `review_mutation_check.py`, run on a copy in `C:\nscrev\review-tmp\run-job-r2\copy`: all 13 mutations caught, and the copy's hash was unchanged afterwards.
- The tool is not under git, so there is no base and head to compare. I read the `.bak` for the pre-fix code.
- The live `run_job.py` has the same sha256 (`500df5d5…`) before and after my run.

Scope check:
- **Only intended files?** Yes, everything is in `job-tools` and `tests`.
- **New blocking gates?** Only the tighter `--allow-tool` refusals and the env opt-in, both answers to round 1.
- **Temp under C:\NSC?** None. The top-level listings of `C:\NSC` and `C:\NSC\NSC` were identical before and after. No stray folders appeared in the live `claude-jobs` either.
- **My own side effects.** Three junctions and one `subst Q:` were created in my scratch folder and removed; the targets are intact.
- **Identity ok?** Not applicable, as the tool makes no commits.
- **Windows hidden?** Yes. Every spawn uses `CREATE_NO_WINDOW` and none uses `DETACHED_PROCESS`.
- **Leftover processes?** None.
