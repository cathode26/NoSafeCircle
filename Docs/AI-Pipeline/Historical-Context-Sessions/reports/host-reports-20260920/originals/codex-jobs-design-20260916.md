# Feature A design: generic Codex jobs (`fix/codex-jobs`)

Pipeline Maintainer Agent, 2026-09-16. It implements the brief `C:\nscrev\reports\handoffs\pipeline-maintainer-codex-jobs-and-mixed-crews-brief-20260916.md`, Feature A. Vincent's rules apply: remove friction, add no gates (verdicts are advisory), and don't waste Claude tokens.

## Package

`Pipeline/CodexJobs/`, a new package with no file overlap with P3 (`AssistantControl`) or P34 (`run_crew.py`):
- `__init__.py`, `__main__.py` (argparse CLI), `jobs.py` (all logic);
- `templates/review_prompt.md`, `templates/do_prompt.md`, `templates/verdict.schema.json`, `templates/do_result.schema.json`;
- `README.md`;
- `tests/test_codex_jobs.py`, `tests/fake_codex.py`, `tests/fake_docker.py`.

Standard library only. Every subprocess gets `CREATE_NO_WINDOW` (0x08000000); `DETACHED_PROCESS` is never used. JSON records are written UTF-8 without a BOM, with an atomic replace. Start the templates from `C:\nscrev\codex-jobs\templates\adversarial-review-prompt.md` and `verdict.schema.json`, which agents already use by hand. Keep the verdict fields identical so the manual and CLI results match.

## CLI

`python -B -m Pipeline.CodexJobs [--jobs-root DIR] <command>`. The jobs root defaults to `$NSC_CODEX_JOBS_ROOT`, else `C:\nscrev\codex-jobs`. Refuse a jobs root inside the source repo.

| Command | Does |
|---|---|
| `create --mode do\|review --title T --requester R --instructions FILE [--source PATH] [--base REF] [--target REF\|A..B] [--report FILE] [--runtime docker\|host] [--preset cheap\|standard\|thorough] [--effort E] [--model M] [--timeout-seconds N] [--allowed-path P]... [--check CMD]... [--task-id NSC-###] [--follow-up-review] [--job-id ID]` or `create --spec FILE.json` | Validates, writes the records, and prints the job id. State: `queued`. |
| `run JOB_ID [--authorize-provider-spend] [--go-note TEXT] [--quota-override]` | Blocking, and exits when the job ends, so callers background it. **Review jobs** run under Vincent's standing go and need no flag. **Do jobs** need `--authorize-provider-spend`; without it `run` exits 2 and the job stays queued. See "Authorization and quota". |
| `do ...` / `review ...` | `create` plus `run` in one call, with the same authorization rules. |
| `quota` | Prints the last known Codex rate limits from job records, with their age. |
| `status JOB_ID [--json]`, `result JOB_ID`, `list [--limit N]` | Cheap reads. `result` prints the verdict or do summary and the paths. |
| `cancel JOB_ID` | Records the request, then kills the recorded process tree (`taskkill /PID <pid> /T /F`) and, for Docker, `docker stop nsc-codex-job-<job_id>`. |

Exit codes for `run`, `do` and `review`: 0 succeeded, 1 failed, 2 usage error or spend refusal, 3 needs_attention, 4 cut_off, 5 cancelled, 6 paused_quota (the job stays queued).

## Authorization and quota (Vincent, 2026-09-16, relayed by the Documentation Agent)

His policy:
- Codex **review** jobs on our own work and on merge candidates are pre-approved, including host runs for Windows-only tests.
- They pause once the Codex weekly quota passes 90%.
- Codex **do** jobs still need his go.
- Codex never runs Unity.

How the CLI applies it:
- **Record the authorization in every run**, in `status.json` and `result.json`: `authorization` = {`source`, `policy_text`, `go_note`, `recorded_at`}.
  - Review: `source` = `standing_go_review_jobs_2026-09-16`, and `policy_text` quotes the policy above.
  - Do: `source` = `per_job_go`, which needs `--authorize-provider-spend`. `--go-note "<Vincent's words>"` is optional but recorded.
- **Quota check before starting any job:**
  1. Find the newest `rate_limits` seen in any job's `status.json` under the jobs root.
  2. Take the longest window (the weekly one, usually `secondary`).
  3. If its `used_percent` is 90 or more, and its `resets_at` is still in the future (or unknown and the record is under 7 days old), don't start: exit 6 `paused_quota`, leave the job `queued`, and print the percent, reset time and record age.
  4. With no data, start with an advisory warning, `quota_unknown`.
- **Override:** `--quota-override` requires `--go-note`. It records the override in `authorization`, because only Vincent lifts the pause.
- **During a run:** when events report weekly usage of 90% or more, add the advisory warning `quota_above_90`. Let the run finish; the next start pauses.
- **Unity:** both prompts say "Never run Unity". Docker has no Unity; for host runs the prompt is the only guard.

Defaults:
- **source:** `C:\NSC\NSC\NoSafeCircle`.
- **Review target:** a ref, or `A..B`, which sets base = A and head = B. Refs must resolve in the source. The source may be an author's clone, such as `C:\nscrev\<topic>-fix`.
- **runtime:** `docker`.
- **Presets** set effort only and never hard-code model names: cheap = `low`, standard = `medium`, thorough = `high`. The default is `standard` for do jobs and `thorough` for reviews. `--effort` and `--model` override the preset. Both must match `^[A-Za-z0-9._-]+$`, because they go into a `bash -lc` string.
- **timeout:** 3600 s.
- **job_id:** `<mode>-<slug>-<UTC yyyymmddThhmmssZ>`, which must match `^[a-z0-9][a-z0-9._-]{2,90}$`.

## Records: `<jobs-root>/<job_id>/`

- `job.json`: the normalized spec, schema `nsc-codex-job/v1`, and `links` (`parent_job` / `follow_up_job`).
- `status.json`:
  - `state`: `queued`, `running`, `succeeded`, `failed`, `cut_off`, `needs_attention` or `cancelled`;
  - `reason`, `created_at`, `started_at`, `ended_at`;
  - `runner_pid`, `codex_pid`, `runtime`, `docker_container`, `exit_code`, `codex_version`, `session_id`;
  - `rate_limits` (last seen) and `warnings[]`.
  - `status` reports a `running` job whose runner PID is dead as `needs_attention: runner_exited`.
- `prompt.md`: the full composed prompt.
- `events.jsonl`: Codex `--json` stdout. `stderr.log` holds stderr.
- `report.md`: the last message.
- `result.json`:
  - review: the parsed verdict plus the integrity check;
  - do: `branch`, `base`, `head`, `commits[]`, `changed_paths[]`, `out_of_scope_paths[]`, and Codex's structured `checks_run[]`.
- `repo/`: the job clone. `tmp/` is TEMP/TMP for host runs.

## Isolation

- Clone with `git clone -q --no-hardlinks -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true <source> <job>/repo`, then set the push URL to `DISABLED`. Never use a worktree, and never mount the canonical repo.
- **Review:** `checkout --detach <head>`.
- **Do:** `switch -c codex/<job_id> <base>`.
- **Job files inside the clone:** `repo/.codex-job/` holds `schema.json`, `author-report.md` (a copy of `--report`), `instructions.md` and `last-message.md`. Append `/.codex-job/` to `repo/.git/info/exclude` so it never counts as a change. Docker sees the same files under `/workspace/.codex-job/`.

## Running Codex

Both runtimes pass the prompt on stdin, write stdout to `events.jsonl` and stderr to `stderr.log`, enforce the timeout (kill the tree, then `failed: timeout`), and record the PIDs.

**Host:**
- Command: `<codex> exec --json --skip-git-repo-check --color never --cd <repo> --sandbox <S> -c model_reasoning_effort=<effort> [-m <model>] --output-schema <repo>/.codex-job/schema.json --output-last-message <repo>/.codex-job/last-message.md -`.
- `S` is `workspace-write` for both modes. Reviews must re-run checks at base and head, and the integrity check below enforces "unchanged".
- Executable: `$NSC_CODEX_COMMAND` (a JSON argv prefix, used by tests), else `shutil.which("codex")`.
- The environment sets TEMP/TMP to `<job>/tmp`.
- If the host sandbox is unavailable, the job is `needs_attention`. Never fall back to `danger-full-access`.

**Docker:**
- Command: `docker compose -p nosafecircle run --rm -T --name nsc-codex-job-<job_id> codex bash -lc 'cd /workspace && codex exec --json --skip-git-repo-check --color never --sandbox danger-full-access -c model_reasoning_effort=<effort> [-m <model>] --output-schema /workspace/.codex-job/schema.json --output-last-message /workspace/.codex-job/last-message.md -'`.
- Run it with `cwd = <repo>`. The Docker argv prefix comes from `$NSC_DOCKER_COMMAND`, else `docker`.

**Both:**
- Parse `events.jsonl` for the session or thread id, the Codex version when present, and the last `rate_limits`. Add an advisory warning at 90% used or more.
- Detect a cut-off (usage limit, rate limit, quota, `insufficient_quota`) in error events or stderr; it wins over `failed`.
- Host `codex --version` is recorded before the run. For Docker it stays `null` unless the events carry it.

## Prompts

**Review (`templates/review_prompt.md`):**
- Say the work is wrong until proven.
- Reproduce every claim; re-run the checks at base and at head in this clone; grep for incomplete propagation.
- Rank findings, each with file:line, a concrete failure scenario, and reproduced or theoretical. No style nits.
- Leave the repository exactly as found: switching to base is fine, but end back on the head with a clean index and worktree. Scratch goes only in `$TMP` (host) or `/tmp` (Docker).
- No providers, Docker, Unity, pushes or commits.
- The final message must be JSON matching `schema.json`.
- Fill in: title, requester, base, head, author report path, instructions text, checks, and the runtime's repo path.
- Give Codex only these inputs, never an author transcript.

**Do (`templates/do_prompt.md`):**
- Edit only inside `allowed_paths`, or anywhere when the list is empty.
- Don't commit or push, and don't touch `.codex-job/` except its last message.
- Run the checks and report them honestly.
- The final message is JSON matching `do_result.schema.json`: `status` (done or blocked), `summary`, `changed_paths[]`, `checks_run[]` (`command`, `exit_code`, `summary`), and `notes`.

## After Codex exits

**Review:**
- **Integrity.** Record `rev-parse HEAD`, a sha256 of `git ls-files -s -z` and `git status --porcelain=v1 -z --untracked-files=all` before and after. Any difference is `needs_attention: review_integrity_violation`, with a diff summary in `result.json`.
- **Verdict.** Parse `last-message.md` as JSON and validate it by hand against the schema's required fields and enums. Missing or invalid is `needs_attention: invalid_verdict`, never a pass. A valid verdict is `succeeded`, whatever its value.

**Do:**
- If HEAD moved (Codex committed despite instructions), check every new commit's author and committer email ends in `.invalid`; otherwise `needs_attention: unsafe_commit_identity`.
- Collect changed paths. Any outside `allowed_paths` is `needs_attention: out_of_scope_changes`, and the runner does not commit.
- Otherwise stage exact paths and commit on `codex/<job_id>` with `Pipeline.TaskReviewAgent.git_identity_guard.validated_agent_git_identity()`, message `codex job <job_id>: <title>`.
- An invalid `do_result` is `needs_attention: invalid_result`. A `blocked` status is `needs_attention: blocked`, with the summary.

The runner never executes `checks` itself. Codex runs them and reports them; the requesting agent verifies.

**Follow-up review:** when a do job with `--follow-up-review` succeeds, create a linked queued review job with source = the do job's `repo`, target = `<base>..codex/<job_id>` and the default adversarial instructions. Print its `run` command. It never runs automatically, because spend is per run.

## Tests (fake Codex and fake Docker only; tiny throwaway git repos under TEMP, never the real repo)

1. Spec validation: mode, runtime, job id, instructions file, a review without a target, unsafe effort or model text, a jobs root inside the source.
2. Isolation: the clone sits under the jobs root with push `DISABLED`; review is detached at head, do is on `codex/<id>` at base; the source repo is unchanged; `.codex-job/` is excluded.
3. Lifecycle: create gives `queued`; a do job without the spend flag exits 2 and stays queued; a review job runs without a flag and records `standing_go_review_jobs_2026-09-16`; run ends `succeeded`; status, result, list and quota output; a dead runner PID shows `needs_attention`.
3b. Quota:
   - a prior job record with weekly `used_percent` 91 and a future `resets_at` makes the next run exit 6 and stay `queued`;
   - a past `resets_at` doesn't pause;
   - `--quota-override` without `--go-note` is a usage error, and with it runs and records the override;
   - no data gives `quota_unknown`.
4. Verdicts: valid APPROVE and FIX_FIRST succeed; bad JSON, a bad enum or a missing message give `needs_attention`.
5. Integrity: a fake review that edits a tracked file, or leaves an untracked file, gives `review_integrity_violation`.
6. Cut-off: a usage-limit error event with a nonzero exit gives `cut_off`; `rate_limits` are recorded; the 90% warning appears.
7. Do mode: an allowed edit is committed with the `.invalid` identity; an out-of-scope edit gives `needs_attention` and no commit; a Codex commit with a non-`.invalid` email gives `needs_attention`.
8. Docker argv shape and cwd; timeout kills the process and gives `failed: timeout`; cancel.
9. Follow-up review link.
10. Every subprocess call carries `CREATE_NO_WINDOW`: patch `subprocess.Popen` and `subprocess.run` to capture it.

Run with: `python -B -m unittest Pipeline.CodexJobs.tests.test_codex_jobs`, with TEMP and TMP under `C:\nscrev\tmp\codex-jobs`.

## README

It covers:
- usage examples for a fix-branch review, a trial-merge review and a cheap do job;
- the records, states and exit codes;
- the spend flag, and that Vincent's standing policy governs real runs;
- that verdicts are advisory;
- that Unity isn't available in either runtime.
