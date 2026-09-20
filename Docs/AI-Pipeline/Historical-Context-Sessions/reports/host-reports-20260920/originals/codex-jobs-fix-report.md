# Codex jobs fix report (Feature A)

Pipeline Maintainer Agent, 2026-09-17. Implements the design at
`C:\nscrev\reports\codex-jobs-design-20260916.md`, Feature A only (generic
Codex "do"/"review" job runner). Never merged or pushed. Never ran a real
Codex, Docker or Unity call.

## What was built

`Pipeline/CodexJobs/` in the standalone clone `C:\nscrev\codex-jobs-fix`
(branch `fix/codex-jobs`, base `bdf618744c5f286d9d4e78e2fe05e244e0366e5f`):

- `__init__.py`, `__main__.py`, `jobs.py` (all logic, standard library only).
- `templates/review_prompt.md`, `templates/do_prompt.md`,
  `templates/verdict.schema.json` (copied verbatim from the manual template
  at `C:\nscrev\codex-jobs\templates\verdict.schema.json` — fields
  untouched, so the manual recipe and the CLI produce comparable verdicts),
  `templates/do_result.schema.json` (new, matches the design's do-result
  shape).
- `README.md` — usage, records, exit codes, authorization/quota policy,
  isolation, Windows notes, and the event-format assumption below.
- `tests/test_codex_jobs.py`, `tests/fake_codex.py`, `tests/fake_docker.py`,
  `tests/_fake_engine.py` (shared fake behaviour, driven by
  `NSC_FAKE_CODEX_*` env vars) — the design's tests 1–10 plus 3b.

CLI: `create`, `run`, `do`, `review`, `status`, `result`, `list`, `quota`,
`cancel`, matching the design's table and exit codes (0/1/2/3/4/5/6).

## Where the design was ambiguous, and what I chose

- **Review `--base`/`--target` when only one is given.** Design says
  `--target` can be a ref or `A..B`. I require review mode to have both a
  base and a head: `A..B` sets both (an explicit `--base` overrides the
  `A` half); a plain `--target` sets only the head and still needs
  `--base`. Missing either is a usage error.
- **Do-mode default base.** Not specified; I default to `main` when
  `--base` is omitted (do jobs don't take `--target` at all).
- **`--spec FILE.json`.** The spec file fully replaces the other `create`
  flags rather than merging with them (simplest; documented in `--help`
  implicitly via the field names matching `job.json`).
- **Job re-run.** Only a `queued` job can `run`; anything else is a usage
  error naming the current state. No re-queue/retry command was in scope.
- **`cancel` vs. a concurrently-blocked `run`.** `cancel` writes a
  `CANCEL_REQUESTED` marker file next to the job's records, then
  best-effort kills the recorded `codex_pid` (and, for Docker, `docker stop
  nsc-codex-job-<id>`). The blocked `run` process itself notices the
  marker after its child process ends and is the only writer of the
  terminal `cancelled` state — this avoids two processes racing to write
  `status.json`.
- **Docker "cwd" and the container name in argv shape.** Tested for
  literal presence of `compose`, `-p nosafecircle`, `--name
  nsc-codex-job-<id>`, `codex`, `bash -lc`, and the embedded
  `codex exec ... --sandbox danger-full-access ... model_reasoning_effort=`
  string, plus `cwd == <job>/repo`, per the design's "Docker argv shape and
  cwd" test.
- **`quota` "longest window."** Implemented generically as
  `max(primary, secondary, key=window_minutes)` rather than assuming which
  key holds the weekly window — the one real sample found (below) had the
  weekly (10080-minute) window in `primary` with `secondary: null`.

## Real event-format sample used

Per the task's search order, found two useful real samples (not a
fabricated shape):

1. **`codex exec --json` stdout**, from
   `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\...\RAW_EVENTS.jsonl`
   (GER rounds): flat events —
   `{"type":"thread.started","thread_id":"01a0..."}`,
   `{"type":"turn.started"}`,
   `{"type":"item.started"/"item.completed","item":{...}}`,
   `{"type":"turn.completed","usage":{...}}`, and, from a usage-limit run,
   `{"type":"error","message":"You've hit your usage limit. ... try again
   at Sep 19th, 2026 4:00 PM."}` followed by
   `{"type":"turn.failed","error":{"message":"..."}}`. This is exactly what
   the cut-off detector and session/thread-id scan are built against.
2. **`rate_limits` shape**, from a real Codex rollout log under
   `C:\nscrev\codex-volume\sessions\...\rollout-...jsonl` (the CLI's own
   session recording, not `exec --json` stdout):
   `{"type":"event_msg","payload":{"type":"token_count","info":{...},
   "rate_limits":{"limit_id":"codex","primary":{"used_percent":0.0,
   "window_minutes":10080,"resets_at":1790121328},"secondary":null,
   "credits":{...},"plan_type":"prolite",...}}}`.

No sample of `codex exec --json` stdout itself carrying a `rate_limits` key
was found in the bounded search. Assumption, stated in the README too: the
parser does a recursive scan for a `"rate_limits"` dict anywhere in each
event's JSON tree (mirroring how `ger_round.py`'s `run_codex` already
recursively scans for `thread_id`/`session_id`/`model`), so it is
insensitive to whether a future `exec --json` build nests it under
`payload` or emits it flat. If real `exec --json` output never carries
`rate_limits` at all, `quota` and the pause check simply stay
`quota_unknown` until a job is run under a runtime/version that does emit
it — worth Vincent/GER confirming on a real run.

## Commits

- `b9fd10ef0` — "Codex jobs: failing tests for the CLI" (tests + fakes
  only). Before: `python -B -m unittest Pipeline.CodexJobs.tests.test_codex_jobs`
  → **40 tests, 40 errors** (`ImportError: cannot import name 'jobs'`),
  because `Pipeline/CodexJobs/jobs.py` didn't exist yet.
- `9d9136f29` — "Codex jobs: generic do/review job runner with durable
  records" (the implementation, templates, README, plus small fixes to the
  tests/fakes that surfaced while building against them — see "Bugs found
  while building" below). Head of `fix/codex-jobs`.

## Tests: after

```
TEMP=C:\nscrev\tmp\codex-jobs TMP=C:\nscrev\tmp\codex-jobs \
python -B -m unittest Pipeline.CodexJobs.tests.test_codex_jobs
```
→ **Ran 40 tests in ~33s. OK.**

Other verification, all clean:
- `python -B -m compileall -q Pipeline/CodexJobs` → exit 0.
- `git diff --check bdf618744` (from the clone) → no whitespace errors.
- `git ls-files --eol Pipeline/CodexJobs` → every blob `i/lf` (the one
  `w/crlf` is the working-tree conversion `core.autocrlf=true` applies on
  checkout; the stored blob is LF).

## CLI smoke transcript (summary)

All under a throwaway jobs root/source repo in `C:\nscrev\tmp\codex-jobs`,
never the real repo:
- `--help` → prints the 9 subcommands.
- `create --mode review ...` → prints a job id, `status.json.state ==
  "queued"`.
- `status JOB_ID` → `queued`; `list` → shows it; `quota` → `quota_unknown:
  no rate limit data recorded yet`.
- `run JOB_ID` with `NSC_CODEX_COMMAND` pointing at `fake_codex.py` (host
  runtime) → exit 0; `status --json` → `state: succeeded`,
  `authorization.source: standing_go_review_jobs_2026-09-16`; `result` →
  `verdict: APPROVE`, `integrity.ok: true` (before/after hashes identical).

## Bugs found and fixed while building (all in this same clone, pre-review)

Building jobs.py against the tests written in commit 1 surfaced real bugs
in the fakes/tests, not in the design:
- `_fake_engine.py`'s `--version` handling: the fake didn't special-case
  `--version`, so `_host_codex_version()`'s probe ran the *whole* fake
  engine (including any configured sleep and a blocking stdin read),
  stalling every host run by the probe's own side effects. Fixed by making
  `fake_codex.py` answer `--version` immediately, and by passing
  `stdin=subprocess.DEVNULL` to the real version-probe subprocess call in
  `jobs.py` as a defensive measure for production too.
- The Docker path embeds the whole `codex exec ...` invocation inside one
  `bash -lc '<script>'` argv string; the fake's flag scanner only checked
  literal argv elements, so it never found `--output-last-message` for
  Docker jobs. Fixed with a regex fallback over the trailing argv string
  plus a `/workspace/` → `cwd` path translation.
- `_git_status_paths()` routed `git status --porcelain` through the
  existing `_git_output()` helper, whose whole-output `.strip()` ate the
  leading space of the *first* status line, misaligning every subsequent
  fixed-width `line[3:]` slice (e.g. `" M src/widget.py"` → after strip
  `"M src/widget.py"` → `line[3:]` = `"rc/widget.py"`). Fixed by reading
  the raw stdout bytes directly for that one parse instead of through the
  stripping helper.
- `argparse(choices=...)` on `--mode`/`--runtime`/`--preset` made a bad
  value raise `SystemExit(2)` straight out of `argparse`, bypassing the
  intended `JobError` → printed message → exit 2 path (and, in-process,
  an uncaught `SystemExit`). Removed `choices=`; validation now happens in
  `validate_and_normalize()` with a normal `JobError`.
- The jobs-root/source isolation check originally refused *either*
  direction (jobs root inside source, or source inside jobs root), mirrored
  from `AssistantControl.Checkouts`. That's too strict here: a follow-up
  review's source is deliberately the *previous* job's own clone, which
  lives under the jobs root by design. Narrowed to refuse only "jobs root
  inside source" (what the design actually asked for).

**One incident worth flagging honestly:** while manually reproducing an
early timeout bug via ad hoc Python snippets run through the Bash tool
(before `jobs.py`'s `_run_process` cwd handling was finalized), one such
snippet — or an early buggy version of the code — caused a stray commit
("sneaky commit", author `Codex <codex@example.com>`, from the identity
test's fake-commit fixture) to land for real inside this fix clone
(`C:\nscrev\codex-jobs-fix`) instead of a throwaway test repo. It carried
no content beyond an earlier draft of the very files I was already adding
(no foreign data), and this clone has never been pushed or shared
(`origin`'s push URL is `DISABLED`). I removed it with `git reset --soft`
back to `b9fd10ef0` before building the real commit 2, verified the
current code no longer reproduces it (reran the full suite immediately
after resetting: 40/40 pass, no new commit appears), and did not use `git
reset --hard` or touch anything outside this disposable clone. Flagging
this so the reviewer specifically re-checks that `_run_process` always
passes an explicit `cwd=repo_dir` to `Popen` (it does, at
`Pipeline/CodexJobs/jobs.py`, the sole call site) and that the fakes'
`git commit` in `_fake_engine.py` can only ever run inside a job's own
throwaway clone.

## Risks / follow-ups

- **`rate_limits` shape unconfirmed for `exec --json` stdout itself**
  (see above) — worth a real review-job run to confirm the parser actually
  picks it up, under Vincent's standing review-job approval.
- **`sandbox_unavailable` (host sandbox missing)** is mentioned in the
  design narrative but wasn't in the required test list; not implemented
  as a distinct `needs_attention` reason. A host run where the sandbox is
  genuinely unavailable will currently surface as a generic Codex failure
  (`failed: codex exited N with no final message` or similar) rather than
  a named reason. Cheap follow-up if it turns out to matter in practice.
- **No real Codex/Docker run yet.** Everything above is fakes-only per the
  task's constraints. First real use should be a **review** job (covered
  by Vincent's standing go) on an existing `fix/<topic>` branch, host
  runtime, to validate the real event/rate-limit shapes end to end. A real
  **do** job additionally needs Vincent's per-job go.
- **Follow-up for the Documentation Agent** (not done here, out of lane):
  once this lands, the guides that describe the manual Docker recipe
  (`C:\NSC\nsc-codex-jobs-guide.md` section 2) should point at this CLI.

## Review fix round (2026-09-17)

Branch `fix/codex-jobs` in `C:\nscrev\codex-jobs-fix`, base `bdf618744`,
prior head `9d9136f29`. New head `76ba34d0c` (single commit; identity `No
Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`).
Never merged, pushed, or ran a real Codex/Docker/Unity call.

| # | Finding | Status | Commit |
|---|---|---|---|
| 1 | Stuck `running` on any exception; `-z` porcelain parsing | Fixed | 76ba34d0c |
| 2 | Branch escape in do mode | Fixed | 76ba34d0c |
| 3 | Docker timeout leaves the container running | Fixed | 76ba34d0c |
| 4 | Cancel doesn't stop a run before launch | Fixed | 76ba34d0c |
| 5 | Cut-off detection: stderr scan, exit/validity classification | Fixed | 76ba34d0c |
| 6 | Relative jobs root | Fixed | 76ba34d0c |
| 7 | Docker repo path in the prompt | Fixed | 76ba34d0c |
| 8 | Records: authorization in result.json; review diff summary | Fixed | 76ba34d0c |
| 9 | Fake-engine safety (`_host_codex_version` cwd, guarded git) | Fixed | 76ba34d0c |
| 10 | Runner commit identity (ambient env can't override) | Fixed | 76ba34d0c |
| 11 | Review prompt wording (scratch files, never modify clone) | Fixed | 76ba34d0c |
| 12 | Test cleanup (read-only rmtree on Windows) | Fixed | 76ba34d0c |

One existing test (`test_codex_commit_with_unsafe_identity_gives_needs_attention`)
had its exact-match assertion updated: finding 2 folds the old, narrower
`unsafe_commit_identity` reason into the broader `branch_integrity_violation`
check (an unsafe commit on the do branch is one of several ways the branch
can fail integrity). Propagated and re-grepped for other call sites of
`_finalize_review`/`_finalize_do`/`_host_codex_version`/`unsafe_commit_identity`;
none missed.

**Failing-before**, via `git stash push -- Pipeline/CodexJobs/jobs.py
Pipeline/CodexJobs/tests/_fake_engine.py Pipeline/CodexJobs/tests/fake_docker.py
Pipeline/CodexJobs/templates/review_prompt.md` (reverting production/fakes to
9d9136f29 while keeping the new tests), then running the new/changed test
classes:

```
StuckRunningTests, BranchEscapeTests, CancelBeforeLaunchTests,
CutoffScanTests, FakeEngineSafetyTests, RunnerIdentityTests
```
→ **Ran 12 tests, 9 failures + 1 error (10 of 12 fail)**. The two that did
not fail directly are covered by `StuckRunningTests`, where one case errors
out with an uncaught `FileNotFoundError` (the "stuck running" bug, reproduced
for real — status.json would be left at `running` forever) and the other
fails on the mis-parsed non-ASCII path (`caf/303/251.py` instead of
`café.py`). Stash popped immediately after to restore the fix; verified no
stray commit was left (`git reflog` before/after matched).

**Passing-after:**
```
TEMP=C:\nscrev\tmp\codex-jobs-fix2 TMP=C:\nscrev\tmp\codex-jobs-fix2 \
python -B -m unittest Pipeline.CodexJobs.tests.test_codex_jobs
```
→ **Ran 57 tests in ~51-59s. OK.** (40 original + 17 new, one existing
assertion updated per above.)

Other verification, all clean:
- `python -B -m compileall -q Pipeline/CodexJobs` (scratch `PYTHONPYCACHEPREFIX`) → exit 0.
- `git diff --check bdf618744` → no whitespace errors.
- `git ls-files --eol Pipeline/CodexJobs` → every non-empty blob `i/lf`.
- No `codexjobs-*` folders left under TEMP after the suite.
- `git status --porcelain` clean; `git reflog -6` shows only the one new
  commit on top of `9d9136f29` — no stray commits from any test run.

**Risks / follow-ups**, in addition to the ones above:
- The `branch_integrity_violation` reason string changed shape (it now
  embeds the specific cause, e.g. "commit <sha> on codex/<id> has unsafe
  identity (...)" or "HEAD is not on codex/<id> (currently ...)"); any
  caller matching the old exact `unsafe_commit_identity` string needs
  updating (only the CLI's own test suite did; no other repo code was found
  referencing it).
- `docker_stop_attempted` vs `docker_stopped` warnings are best-effort
  advisories, not gates; a real Docker daemon that's slow to stop within the
  30s timeout would still report `docker_stop_attempted` and move on.

## Review fix round 2 (2026-09-17)

Branch `fix/codex-jobs` in `C:\nscrev\codex-jobs-fix`, base `bdf618744`,
prior head `76ba34d0c`. New head `a79c3358eefe12e2dcc09d0005dea36f69a3ee21`
(single commit; identity `No Safe Circle TaskReviewAgent
<task-review-agent@nosafecircle.invalid>`). Never merged, pushed, or ran a
real Codex/Docker/Unity call. No dummy process left running afterward; no
real/unrelated process was ever targeted (every test spawns and kills only
its own `python -c "import time; time.sleep(60)"` child).

### Major (reproduced): `cancel` could kill an unrelated process

`cmd_cancel` (jobs.py, was around line 1388) ran
`taskkill /PID <codex_pid> /T /F` for any job not in state `queued` --
including a job already `succeeded`/`failed`/`cut_off`/`needs_attention`/
`cancelled`. Windows reuses PIDs, so a stale `codex_pid` from a finished
job can now belong to an unrelated live process (Unity and GitHub Desktop
are always open on this machine) -- killing it (and, via `/T`, its child
tree) is real collateral damage, not a hypothetical.

Root cause: `Pipeline/CodexJobs/jobs.py`, `cmd_cancel` had only one branch
(`state == "queued"`) before falling through to an unconditional
`_kill_process_tree(status["codex_pid"])` for every other state, with no
check that the PID still identified the same process `run()` started.

Fix (commit `a79c3358e`):
- `cmd_cancel` now has three branches: `queued` (unchanged: immediate
  `cancelled`), a terminal state (prints `job <id> already ended: <state>`,
  writes nothing, kills nothing, exit 0), and `running` (writes
  `CANCEL_REQUESTED` unconditionally, then only kills `codex_pid` if its
  live identity still matches).
- `run()` now records `codex_pid_identity` (in `record_pid`, right after
  `Popen`) and `runner_pid_identity` (in `cmd_run`, alongside the existing
  `runner_pid = os.getpid()`), both via
  `Pipeline.AssistantControl.process_identity.identify()` -- an existing
  Windows ctypes `OpenProcess`/`GetProcessTimes` helper already used by
  `background_jobs.py`, `crew_worker.py`, `graph_controller.py`,
  `worker_control.py`, etc. No new ctypes code was needed.
- New helper `_kill_if_identity_matches(pid, recorded_identity, label)`
  calls `process_identity.matches(recorded_identity)` (re-reads the live
  PID's creation time and compares) and only calls the existing
  `_kill_process_tree(pid)` (still `taskkill /T /F`, so a matched process's
  own children are still cleaned up) on an exact match; otherwise it prints
  a skip message to stderr and kills nothing. Off Windows, or with no
  recorded identity, it likewise refuses to kill and says so.
- Docker's `docker stop nsc-codex-job-<id>` is untouched -- it already
  targets the job's own container name, not a PID.

Tests (`Pipeline/CodexJobs/tests/test_codex_jobs.py`, new class
`SafeCancelTests`, `@unittest.skipUnless(os.name == "nt", ...)`):
1. `test_cancel_on_finished_job_does_not_kill_live_pid` -- a `succeeded`
   job's `status.json` names a live dummy process's PID (+ its real
   identity). `cancel` must not kill it.
2. `test_cancel_running_job_with_mismatched_identity_skips_kill` -- a
   `running` job whose recorded `codex_pid_identity` has a
   `created_ticks` off by one from the live dummy's actual creation time.
   No kill.
3. `test_cancel_running_job_with_matching_identity_kills_it` -- a `running`
   job whose recorded identity exactly matches the live dummy. Killed.

All three spawn their own `subprocess.Popen([sys.executable, "-c", "import
time; time.sleep(60)"], creationflags=CREATE_NO_WINDOW)` and only ever
touch that PID; `addCleanup` kills it if still alive.

Failing-before, test 1 only, via `git stash push --keep-index --
Pipeline/CodexJobs/jobs.py` (keeps the new test in the working tree, reverts
just `jobs.py` to `76ba34d0c`), then:

```
TEMP=C:\nscrev\tmp\codex-jobs-fix3 TMP=C:\nscrev\tmp\codex-jobs-fix3 \
python -B -m unittest Pipeline.CodexJobs.tests.test_codex_jobs.SafeCancelTests.test_cancel_on_finished_job_does_not_kill_live_pid
```

-> FAILED (`AssertionError: 1 is not None : cancel on an already-finished
job must not kill a live process` -- the dummy process's `poll()` returned
its exit code because `76ba34d0c`'s `cmd_cancel` killed it). `git stash pop`
immediately after to restore the fix; `git reflog` showed no stray commit.

### Minor 1: README stale reason name + undocumented fields

`README.md` (~line 124) still said a do-mode branch violation was
`needs_attention: unsafe_commit_identity` -- that name was already replaced
by `branch_integrity_violation` in review-fix-round 1 (commit `76ba34d0c`),
and the README was never updated. Fixed:
- Replaced the stale name with the current `branch_integrity_violation`
  (HEAD-off-branch / missing branch / non-ancestor base / unsafe identity
  on the branch) vs. `unsafe_runner_identity` (the runner's own commit)
  split, matching the actual code paths.
- Documented `diff_summary` (`head_moved`, `index_moved`,
  `changed_or_untracked_paths[]`) under `result.json`.
- Documented `cancel`'s per-state behavior (immediate for `queued`,
  identity-checked kill for `running`, no-op for terminal states) in both
  the Quick usage section and the Windows notes section.
- Documented the new `commits[]` shape for a `branch_integrity_violation`
  result (list of `{sha, author_email, committer_email}` instead of bare
  SHAs -- see minor 3) and `runner_pid_identity`/`codex_pid_identity` under
  `status.json`.

### Minor 2: `RelativeJobsRootTests` didn't exercise a real run

The single test in this class only called `create` and checked `job.json`
landed under the resolved absolute root -- it never called `run`, so it
passed identically against `76ba34d0c` (nothing about `run()`'s own
relative-path handling was covered). Fixed: the test now calls `create`
then `run` (fake codex, host runtime, do mode, no edits so it succeeds
trivially) under the relative `--jobs-root`, still from a `chdir`'d cwd, and
asserts `status.json.state == "succeeded"`, `report.md` is non-empty (the
last message was written under the resolved root), and `result.json.mode
== "do"` -- all read from the resolved absolute path.

### Minor 3: branch-violation `commits: []` hid the unsafe commit

`_check_do_branch_integrity` only computed `new_commits` inside the
ancestor-satisfied branch (the success path); every violation return before
that point (`HEAD is not on <branch>`, `branch does not exist`, `base is
not an ancestor`) returned `[]` even when `refs/heads/codex/<job_id>`
plainly had the unsafe commit sitting on it (e.g. the `branch_switch`
scenario: Codex commits unsafely on the codex branch, then checks out a
different branch -- HEAD is now off the codex branch, so the old code
short-circuited to `commits: []` before ever looking at what was on it).

Fix: factored the `base_sha..branch_ref` SHA lookup into
`_commit_shas_between()` and now compute it once, unconditionally, right
after resolving `branch_sha` -- before any of the violation checks -- so
`new_commits` (bare SHA list, used unchanged everywhere else in
`_finalize_do`) is populated in every violation branch, not just the
identity-check one. In `_finalize_do`'s violation-write path only, a new
`_commit_identity_details(repo_dir, shas)` expands those SHAs to
`{sha, author_email, committer_email}` before writing `result.json` -- this
enrichment is local to the violation case; the success-path `commits[]`
elsewhere in the file (used with `new_commits + [final_head]` etc.) is
untouched and stays a bare-SHA list, so no other call site needed changes.

Updated
`BranchEscapeTests.test_branch_switch_after_unsafe_commit_gives_needs_attention_and_no_commit`,
whose old assertion (`result["commits"] == []`) was itself asserting the
bug; it now asserts one commit record with a 40-char sha and
`author_email`/`committer_email` both `codex@example.com` (the fake
scenario's identity).

### Verification

```
TEMP=C:\nscrev\tmp\codex-jobs-fix3 TMP=C:\nscrev\tmp\codex-jobs-fix3 \
python -B -m unittest Pipeline.CodexJobs.tests.test_codex_jobs
```

-> Ran 60 tests in ~59-66s. OK. (57 prior + 3 new `SafeCancelTests`, one
existing assertion in `BranchEscapeTests` updated per minor 3, one existing
test rewritten per minor 2 -- no test count regression.)

- `PYTHONPYCACHEPREFIX=C:\nscrev\tmp\codex-jobs-fix3-pycache python -B -m
  compileall -q Pipeline/CodexJobs` -> exit 0.
- `git diff --check bdf618744` -> no whitespace errors (only an autocrlf
  LF->CRLF notice on README.md, not an error).
- `git ls-files --eol Pipeline/CodexJobs` -> every non-empty blob `i/lf`
  (the two `i/none` entries are the empty `__init__.py` files).
- `git reflog -3`: `a79c3358e` (this fix) directly on top of `76ba34d0c`
  (review round 1) on top of `9d9136f29` -- no stray commits.
- `git status --porcelain` clean after the run; no leftover `codexjobs-*`
  temp folders; no dummy `python.exe ... time.sleep(60)` processes found
  via `Get-CimInstance Win32_Process` after the suite.

### Creation-time helper used

Reused the existing `Pipeline.AssistantControl.process_identity` module
(`identify`/`matches`, Windows `ctypes` `OpenProcess`/`GetProcessTimes`,
already relied on by `background_jobs.py`, `crew_worker.py`,
`graph_controller.py`, `worker_control.py`, `worker_launcher.py`,
`worker_settlement.py`, `viewer.py`, `maintenance.py`) -- no new ctypes
code was added to `jobs.py`.

### Risks / follow-ups

- `commits[]` in `result.json` is now schema-inconsistent by design: a bare
  SHA list on every success/other-`needs_attention` path, but a list of
  `{sha, author_email, committer_email}` dicts specifically for
  `branch_integrity_violation`. Documented in the README; a future consumer
  parsing `commits[0]` as a string would need to branch on `reason` first.
- `runner_pid_identity`/`codex_pid_identity` are `None` on any platform
  other than Windows, or if `process_identity.identify()` raised for any
  reason (e.g. the process already exited before the identity snapshot
  could be taken) -- `cancel` already treats a missing recorded identity as
  "don't kill," so this fails closed, not open.
