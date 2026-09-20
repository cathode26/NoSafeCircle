# run_job.py — fixes for the Fable review of 2026-09-18

**Board:** H-20260918-02. **Review being answered:** `C:\nscrev\reports\run-job-review-20260918.md`
(VERDICT FIX FIRST). **Tool:** `C:\nscrev\job-tools\run_job.py`.
**Backup of the reviewed version:** `run_job.before-review-fixes-20260918T064051.bak.py`.

## State

- 101 tests, OK (71 before; 30 new, all in classes named `Review*`).
- `tests/review_mutation_check.py` reverts each of the 13 fixes one at a time and confirms a
  named test goes red: **all 13 caught**. This exists because the review's closing finding was
  that every defect it raised would pass the suite as it stood — a test written after the fix,
  against the fixed code, proves nothing on its own.
- The reviewer's three blocking reproductions were re-run verbatim and all now fail closed.

## The three blocking findings

### 1. The clone guard accepted other spellings of the canonical repo

`is_under` compared strings. `resolve()` keeps the `\\?\` and UNC prefixes, so `relative_to`
raised `ValueError` and the guard returned False — `\\?\C:\NSC\NSC\NoSafeCircle`,
`\\localhost\C$\...` and `\\127.0.0.1\C$\...` were all ACCEPTED.

Fixed by comparing **filesystem identity** — `(st_dev, st_ino)` — instead of text. Every
spelling of a directory returns the same pair, so the fix covers not just the three the reviewer
found but 8.3 short names, junctions, symlinks and case. `is_under` walks the child's own parents
against the parent's identity; a string comparison remains only for paths that do not exist yet
(`--out` for a folder not created), where there is nothing to stat.

Verified: all three reviewer spellings, plus the lowercase and `..` forms, now raise `Refused`.

### 2. `--allow-tool` added any rule verbatim

`advice --allow-tool Write --allow-tool Edit --allow-tool Bash --allow-tool Agent` produced an
Opus job with write tools, unrestricted Bash, `dontAsk` and `C:/NSC` on `--add-dir`.

Fixed with `guard_allow_tool`, which parses each rule as `Tool` or `Tool(specifier)` and refuses:
- `Task` and `Agent` in any form, on every job type. The reviewer was right that nobody has shown
  `--disallowedTools Task` blocks a tool named `Agent`; this refuses both rather than resting on it.
- a write tool (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`) on a job type whose built-in list
  does not already have it;
- **bare** `Bash` — a scoped `Bash(git log:*)` is still accepted, because that is the documented
  use of the flag and `--allow-bash git` is only shorthand for it;
- a tool that is neither in the type's list nor one of the read-only extras.

`guard_tool_list` re-checks the assembled list before it can become an `--allowedTools` argument,
whatever route a rule took to get there.

One thing the review got slightly wrong, noted so nobody re-files it: Docker types refuse
`--allow-tool` outright and always did, so the widening path only ever existed on host types.
That is now pinned by a test rather than left as an accident.

### 3. The 24-hour account cache failed open

**Removed, not repaired.** A `checked_at` in the future never expired; the file sits in `JOBS_DIR`
where any agent can write it; and the Docker branch of `logged_in_account` had no test at all, so
a branch that always returned the Gmail address would have kept all 71 tests green.

The cache saved one `auth status` call per job — about a second, no tokens. That is not worth a
guard that fails open on **which account pays**, particularly when guide 4.3 itself records a
container login flipping inside a day. The Docker branch now has three tests, including one using
`FAKE_DOCKER_ACCOUNT`, which existed but nothing had ever used.

## The majors, also fixed

| Finding | Fix |
|---|---|
| env overrides relaxed guards in production | every `NSC_RUN_JOB_*` override needs `NSC_RUN_JOB_TESTING=1`; ignored otherwise and listed in `_IGNORED_OVERRIDES`. A README sentence is not a guard |
| a refused background job was invisible | the account guard now runs **in the parent before spawning** — `--background` was a way round the one guard that decides who pays; the child's stderr goes to `<out>/background-stderr.log` instead of DEVNULL; `--allow-account` and `--host-reason` are forwarded |
| `--dry-run` wrote to disk | `guard_out(..., dry_run=True)` does not mkdir, and `JOBS_DIR.mkdir` is skipped |
| telemetry misattributed spend | `account` records the paying account even under `--skip-account-check` (every background child passes it, so the rows that most needed an owner had none); new `account_source` and `usage_account` fields, because `/usage` always runs on the host CLI and its figures are the host's |
| pre-flight subprocesses inherited stdin | `run_quiet` defaults `stdin=DEVNULL` — except when the caller passes `input=`, which `subprocess.run` rejects alongside `stdin`. That combination is itself now a test |
| the account refusal was a traceback | caught and printed as `REFUSED:` with exit 2, like every other guard |
| `--name ..` walked out of the job folder | a name that is only dots is refused |

## Not done, and why

- **`--timeout` kills only the docker client**, leaving the `--rm` container spending. Real, and
  the fix is `docker compose kill` on the run's container, which needs a container id this tool
  does not currently keep. Filed rather than rushed.
- **`--json` has no schema or version key.** Worth doing when something consumes it; nothing does yet.
- **Whether `--disallowedTools Task` blocks a tool named `Agent`** is still unverified — it needs a
  provider run. The guard now refuses both names, so the answer no longer gates anything here.

## One correction to the review

It reports "the host was on the Outlook account at 97% and 99%". `claude auth status --text` on
this host returns `cathode26@gmail.com`, checked twice today. The **finding** stands either way —
a Docker job's row pairs the container account with host figures — but the account named in that
bullet is wrong.

## Also from that review, and already dealt with

The review flagged `C:\NSC\astra-should-not-happen\tmp` appearing during its run and could not
explain it. That was mine: `ask_astra.py`'s scratch guard ran *after* `mkdir`, so it created the
folder and then refused. Fixed there (the check runs first, and `main` refuses a forbidden
`NSC_ASTRA_HOME` before touching disk), the folder is gone, and the mutation harness that
deliberately breaks that guard now cleans up after itself. Refusing while leaving debris is not
refusing. Good catch — it was invisible from inside my own session.
