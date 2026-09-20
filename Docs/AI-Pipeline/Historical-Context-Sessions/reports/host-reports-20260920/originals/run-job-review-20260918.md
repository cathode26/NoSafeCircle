VERDICT: FIX FIRST

run_job.py is not safe to hand to agents yet. The clone guard and the account guard can each be bypassed with plain arguments, the read-only host types accept write tools, and `--dry-run` creates folders. I reproduced all of these.

Findings (most severe first):

- **[blocking] run_job.py:200-205, 250-251, 286-287: the clone guard accepts the real canonical repo under other path spellings. Reproduced.**
  - `guard_clone(Path(p), True, "clone-edit")` against the live filesystem returned ACCEPTED for `\\?\C:\NSC\NSC\NoSafeCircle`, `\\localhost\C$\NSC\NSC\NoSafeCircle` and `\\127.0.0.1\C$\NSC\NSC\NoSafeCircle`.
  - The plain, lower-case and `..` forms are refused.
  - `resolve()` keeps the `\\?\` and UNC prefixes, so `relative_to(C:\NSC)` raises ValueError and `is_under` returns False, which opens the guard.
  - `guard_out` uses the same `is_under` and then calls `mkdir`, so `--out \\?\C:\NSC\x` would create a folder under C:\NSC. I did not run that, because it would write there.
  - I did not run Docker from such a working directory, as that is forbidden. The guard-level bypass is proven; the end-to-end mount is theoretical.
  - No test covers alternate path forms. Every clone-guard test uses a plain path under the env-overridden fake root.

- **[blocking] run_job.py:935-940: `--allow-tool` adds any rule verbatim, so read-only host types get write tools. Reproduced.**
  - `advice --brief x --allow-tool Write --allow-tool Edit --allow-tool Bash --allow-tool Agent --dry-run` produces `--add-dir <FORBIDDEN_ROOT> <NSCREV> ... --allowedTools Read Glob Grep Write Edit Bash Agent --disallowedTools Task`.
  - In production that is Opus with Write, Edit and unrestricted Bash, `dontAsk`, and C:/NSC as an added directory. That is a read-write job against C:\NSC with no clone guard involved.
  - Only empty and multi-line rules are refused.
  - `test_allow_tool_passes_an_exact_command_prefix_rule` pins only the permissive behaviour. No test refuses `Write`, `Edit`, bare `Bash`, `Agent` or `Task`.
  - Related and theoretical: this session's own subagent tool is named `Agent`, not `Task`. Nobody has shown that `--disallowedTools Task` blocks `Agent` on claude 2.1.271. I could not check it, because that needs a provider run.
  - The `subagent_stats.spawned` warning is real: 94 of 100 live result files carry that field.

- **[blocking] run_job.py:449-456, 482-484: the 24-hour account cache fails open, and the Docker half of the account guard has no test. Reproduced.**
  - I wrote `{"claude":{"account":"cathode26@gmail.com","checked_at":9e12}}` to `account-cache.json` and set the fake container login to `x@outlook.com`.
  - `clone-edit` then printed "cached login of the claude container", never asked `auth status`, and ran the job with exit 0.
  - The control run without the cache file was refused.
  - A `checked_at` in the future never expires.
  - The cache is a plain file in JOBS_DIR that any agent can write.
  - An honest cache is also stale for up to 24 hours. The guide's own section 4.3 records a login flipping within one day.
  - `FAKE_DOCKER_ACCOUNT` exists in fake_docker.py, but no test uses it. If the Docker branch of `logged_in_account` always returned the Gmail address, all 71 tests would still pass.

- **[major] run_job.py:33-39, 183-191: env overrides relax guards in production. Reproduced.**
  - With `NSC_RUN_JOB_FORBIDDEN_ROOT` and `NSC_RUN_JOB_CANONICAL` pointed elsewhere, `clone-edit --clone <canonical>` ran with exit 0, and the compose working directory was the canonical folder.
  - `NSC_RUN_JOB_JOBS_DIR` selects which account cache is trusted.
  - `NSC_RUN_JOB_CLAUDE` and `NSC_RUN_JOB_DOCKER` choose the executable that answers `auth status`.
  - The whole `os.environ` is also passed to `docker compose`, so `COMPOSE_FILE` could re-point `.:/workspace`. That last one is theoretical.
  - The only barrier is the README sentence "Never set them for a real job."

- **[major] run_job.py:1074-1079 runs before 1083, and 1008-1025: a background job that is refused is invisible. Reproduced.**
  - `host-lookup --background` on a wrong account made the parent print "started in background" and exit 0. After 8 seconds there was no json, no log and no telemetry row.
  - The child's refusal goes to DEVNULL.
  - `--allow-account` and `--host-reason` are not forwarded to the child, so `--background --allow-account x` never runs.
  - `test_background_forwards_every_flag_to_the_child` leaves both flags out.

- **[major] run_job.py:292, 950: `--dry-run` writes to disk. Reproduced.**
  - After I deleted the jobs directory, a dry-run recreated it and created the job folder.
  - A fresh `--out` path was also created by the dry-run.
  - `test_dry_run_runs_nothing` checks only the record of the fake executables. No test checks the filesystem.

- **[major] run_job.py:1090-1098, 1113: telemetry misattributes which account spent what. Reproduced.**
  - With `--skip-account-check`, which every background child uses, the row has `account: null` even though `spending` is known.
  - For Docker jobs the row pairs `cathode26@gmail.com` with the host CLI's session and week figures. In my run the host was on the Outlook account at 97% and 99%, and the row recorded Gmail at 97/99.
  - The printed line carries a caveat about whose usage it is. The telemetry row does not.
  - Two of the four live `jobs.jsonl` rows already have a null account.
  - No failed job was recorded as a success. Real `error_max_turns` files have `is_error: true`, which gives exit 1 and an `error:` status.

- **[major] run_job.py:311, 334, 475, 491, 525, 555: the pre-flight subprocesses inherit the caller's stdin. Reproduced with the fakes only.**
  - When stdin was an open pipe, the tool hung on `auth status`.
  - A single test took 100 seconds and still reported OK.
  - My first probe hit the 300-second limit.
  - With `< /dev/null` the same test took 0.5 seconds.
  - Whether the real `claude -p /usage` blocks the same way is theoretical. Setting `stdin=DEVNULL` on those calls would fix it.

- **[minor] run_job.py:1083-1084: the account refusal is an uncaught traceback. Reproduced.**
  - It exits 1 with a traceback, not the `REFUSED:` message and exit 2 that the README and report promise for every guard.
  - It still fails closed.
  - The account tests assert only a non-zero exit, so they cannot see the difference.

- **[minor] run_job.py:1097, 1099: every Docker job that does not skip the check runs host `claude -p /usage` and host `auth status`.**
  - Both calls go to the scarce Outlook account's CLI.
  - Both spawn the host CLI, which the tool itself says flashes consoles. That contradicts "Docker jobs flash none."
  - Whether `/usage` costs tokens is unverified.

- **[minor] run_job.py:999-1001: `--timeout` kills only the docker client.**
  - The `--rm` container, and its spend, carry on.
  - This is theoretical.

- **[minor] run_job.py:892: `--name ..` and `--name account-cache` both pass the name check. Confirmed by reading, not run.**
  - `..` sets the output folder to NSCREV.
  - `account-cache` makes the job's json path the cache file itself.
  - Two jobs with the same brief stem overwrite each other's output.

- **[minor] run_job.py:348: the real guide no longer contains "No Codex until <date>".**
  - `--astra` is therefore refused permanently with "cannot tell". That fails closed, so it is safe.
  - `test_banner_reader_finds_the_real_guide_date_format` reads a fixture string, not the real guide.

- **[minor] The report and README are stale.**
  - They give 965 lines and 68 tests against the actual 1123 and 71.
  - The report never mentions `guard_account`, `--allow-account`, `--host-reason` or the cache.
  - Its statement that each guard exits 2 is false for the account guard.
  - The report still says no job was run and that `jobs.jsonl` does not exist, yet four live jobs are recorded there.

- **[minor] run_job.py:465: the cache write is not atomic, and `write_text` writes CRLF line endings.**

Tests re-run by reviewer:
- I ran `TEMP=TMP=C:/nscrev/tmp/rj; python -B tests/test_run_job.py`: 71 tests, OK, 19.0 s.
- The tool is not under git, so there is no base and head to compare.
- The suite depends on stdin. With an inherited open pipe, the single test `TestAccountGuard.test_unknown_account_fails_closed` took 100 s and still reported OK. With `< /dev/null` the same test took 0.5 s.
- My probes ran in the scratchpad, using the fakes through the suite's own `Fixture`. No provider, real Docker or Unity was run.

Test theatre, per guard:
- **Account guard, host half.** Removing it would be caught by `test_wrong_account_is_refused_before_the_job_runs` and `test_unknown_account_fails_closed`, though only as a non-zero exit.
- **Account guard, Docker half and the cache.** No test would catch a break.
- **Clone guard.** `test_refuses_canonical_checkout` and `test_refuses_anything_under_forbidden_root` catch removal of `is_under`. The `resolved == CANONICAL` half has no test and is redundant.
- **`--disallowedTools Task`.** Pinned by `test_every_type_has_dont_ask_and_no_task` and `test_each_docker_type_argv`. They assert on the dry-run argv, which is the same object as the run argv, and the flag is unconditional at line 613.

Item 3, per-type parameters:
- The service, model, `--max-turns` and tool list for every type match guide 4.3 and the brief.
- No `claude-exec` type has Edit or Write, and `compose.yaml` mounts `claude-exec` read-only.
- The `/usage` check failing or being unparseable is a warning only and does not defeat the account guard, because the guard comes from `auth status`.

Scope check:
- **Only intended files?** Yes, everything sits in job-tools.
- **New blocking gates?** Only the account refusal, which the caller says is intended.
- **Temp under C:\NSC?** None from the tool's tests or from me. The suite uses `C:\nscrev\tmp\run-job`. I read C:\NSC and wrote nothing there.
- **Identity ok?** Not applicable, as the tool makes no commits.
- **Windows hidden?** Yes. Every spawn uses `CREATE_NO_WINDOW` and none uses `DETACHED_PROCESS`. The caveat is the host-CLI spawns on Docker jobs, listed above.
- **Leftover processes?** I checked after the probes and none remain.
