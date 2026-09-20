# `run_job.py` — one command per Claude helper job

Replaces the hand-typed recipes in `C:\NSC\nsc-codex-jobs-guide.md` section 4.3.
The service, model, `--max-turns` and `--allowedTools` list are built in per job
type; every job gets `--permission-mode dontAsk` and `--disallowedTools Task`;
the guards fail closed; one telemetry line lands in
`C:\nscrev\claude-jobs\jobs.jsonl`.

Outside git, like the other tools in `C:\nscrev\*-tools\`. Standard library only.

```text
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py <type> --brief <file.md> \
  [--clone <path>] [--model <id>] [--out <dir>] [--name <name>] [--max-turns <n>] \
  [--agent <a>] [--allow-bash <program>] [--allow-tool <rule>] [--add-dir <dir>] \
  [--dry-run] [--background] [--skip-account-check] [--timeout <s>] [--astra]
```

Always start with `--dry-run`: it prints the exact command (the copy-pasteable
Git Bash line **and** the argv vector) and runs nothing.

## Built-in parameters per type

| Type | Where | Service | Model | `--max-turns` | `--allowedTools` |
|---|---|---|---|---|---|
| `lookup` | Docker | `claude-exec` (ro) | `claude-haiku-4-5-20251001` | 30 | `Read Glob Grep Bash` |
| `review` | Docker | `claude-exec` (ro) | `claude-sonnet-5` | 80 | `Read Glob Grep Bash` |
| `test-run` | Docker | `claude-exec` (ro) | `claude-haiku-4-5-20251001` | 30 | `Read Glob Grep Bash` |
| `clone-edit` | Docker | `claude` (rw) | `claude-sonnet-5` | 60 | `Read Glob Grep Bash Edit Write` |
| `contract-draft` | Docker | `claude` (rw) | `claude-sonnet-5` | 60 | `Read Glob Grep Bash Edit Write` |
| `host-lookup` | host | — | `claude-haiku-4-5-20251001` | 30 | `Read Glob Grep` (+ your Bash rules) |
| `advice` | host | — | `claude-opus-5` | 40 | `Read Glob Grep` |

`--model` takes an alias (`haiku`, `sonnet`, `opus`) or a full `claude-*` id.
`--max-turns` overrides the default. Nothing else about the argv is tunable —
that is the point of the tool.

## Usage, one block per type

Make the job clone and fill the prompt first (templates in
`C:\nscrev\claude-jobs\templates\`, filled with the Write tool — `printf`/`echo`
in Git Bash break Windows paths):

```bash
git clone -q -c core.autocrlf=true -c core.filemode=false \
  C:/NSC/NSC/NoSafeCircle C:/nscrev/cj-<name>
git -C C:/nscrev/cj-<name> checkout -q <sha or branch>
```

### `lookup` — read-only question about a clone

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py lookup \
  --brief C:/nscrev/claude-jobs/<name>.prompt.md --clone C:/nscrev/cj-<name>
```

### `review` — Claude review of a branch, commit or contract

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py review \
  --brief C:/nscrev/claude-jobs/<name>.prompt.md --clone C:/nscrev/cj-<name> \
  --model opus        # identity, locking, provider-spend or merge code
```

### `test-run` — run the non-Unity suites in the container

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py test-run \
  --brief C:/nscrev/claude-jobs/<name>.prompt.md --clone C:/nscrev/cj-<name>
```

Tests run in `/tmp` copies; `/workspace` stays read-only.

### `clone-edit` — mechanical edit inside a job clone

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py clone-edit \
  --brief C:/nscrev/claude-jobs/<name>.prompt.md --clone C:/nscrev/cj-<name>
```

Read-write `claude` service. Only ever a job clone. Check `git -C <clone> status`
and the diff yourself afterwards.

### `contract-draft` — draft a task-contract revision

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py contract-draft \
  --brief C:/nscrev/claude-jobs/<name>.prompt.md --clone C:/nscrev/cj-<name>
```

### `host-lookup` — host files, Windows tools, the PixelLab MCP, or an agent

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py host-lookup \
  --brief C:/nscrev/claude-jobs/<name>.prompt.md \
  --allow-bash git --allow-bash python \
  --allow-tool "Bash(gh run list:*)" \
  --add-dir C:/NSC \
  --agent scribe        # optional: an agent from ~/.claude/agents/
```

- `--allow-bash <program>` adds `Bash(<program>:*)`. The rule matches the
  **program name**, so `cd C:/nscrev && python -c "..."` is fine under
  `Bash(python:*)`; `python3`, `powershell` and an absolute path to the exe are
  different names and will not match. Name the exact program in the prompt.
- `--allow-tool "<rule>"` passes an exact command prefix verbatim, e.g.
  `"Bash(git -C C:/NSC/NSC/NoSafeCircle log:*)"`.
- `--add-dir` makes a directory outside the working directory readable; without
  it a `Read` there prompts, and `dontAsk` denies the prompt.

### `advice` — read-only advice, the Astra stand-in while Codex is off

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py advice \
  --brief C:/nscrev/claude-jobs/<name>.prompt.md
```

Opus 5, `Read Glob Grep` only, with `--add-dir C:/NSC C:/nscrev` so it can read
the docs and reports. `--astra` selects the Codex path; see the guard below.

### `--background`

Runs the job detached and returns at once with the paths. The detached child
writes the result, the log and the telemetry line exactly as a foreground run
does, and skips the account check (the parent has nothing to print it to).

## What each guard refuses

Every guard fails closed, exits **2**, and prints `REFUSED:` with what to do.

| Guard | Refuses |
|---|---|
| clone identity | `--clone C:\NSC\NSC\NoSafeCircle`, or any path inside `C:\NSC` — prints the `git clone` line to make a job clone instead |
| git worktree | a clone whose `.git` is a **file**, not a directory: a worktree shares the canonical object store |
| not a repo | a `--clone` with no `.git` at all, or one that does not exist |
| compose file | a clone with no `compose.yaml`, since `docker compose` runs from the clone |
| clone required | a Docker type with no `--clone` |
| Docker engine | `docker version` not answering — "Start Docker Desktop, wait for it to report running" |
| Docker image | `nosafecircle-<service>:latest` not built — prints `docker compose -p nosafecircle build <service>` |
| Codex off | `--astra` while the `nsc-codex-jobs-guide.md` banner says "No Codex until \<date\>". The date is **read from the banner**, never hard-coded; an unreadable or unparseable banner also refuses (fail closed) |
| `--astra` scope | `--astra` on any type but `advice` |
| brief | a missing, non-file or empty `--brief`, or one that still has the template header comment ("Fill every `<...>` … delete this comment before running") |
| model | a `--model` that is not an alias or a `claude-*` id (so `gpt-6-astra` cannot be handed to `claude`) |
| host-only flags | `--agent`, `--allow-bash`, `--allow-tool` or `--add-dir` on a Docker type |
| bash rule shape | `--allow-bash` given a path or a whole command line instead of a bare program name |
| output path | an `--out` inside `C:\NSC` |
| job name | a `--name` with anything but letters, digits, `.`, `-`, `_` |
| executables | `claude` or `docker` not on PATH, or an `NSC_RUN_JOB_*` override pointing at a missing file |

## Which account pays, and the account check

Vincent's rule (2026-09-17): **all outsourced work goes through
cathode26@gmail.com**, which is the login inside Docker. Where a job runs decides
who pays — Docker carries its own login in a volume, while a host job uses this
machine's `claude` CLI login. On 2026-09-17 those were different accounts and
host jobs quietly spent the wrong one, so the tool now settles this first and
**fails closed**:

- it asks `claude auth status --text`, on the host or inside the job's container,
  and prints the account that will actually pay;
- a job that would spend any other account is **refused before anything runs**,
  and the message points at the Docker types;
- a job that cannot tell whose tokens it would spend is refused too;
- `--allow-account <email>` runs it anyway, but only if it names that exact
  account, and it prints a `WARNING:` line. Tell Vincent when you use it.
- the container's login is cached for 24h in `claude-jobs/account-cache.json`, so
  this costs one extra container start per day, not per job.

Then it runs `claude -p "/usage" --output-format json` — the one command that
talks to the provider — and prints:

```text
account: cathode26@gmail.com (the login of the claude-exec container)  session 42%  week 61%
```

`/usage` always reports the **host** CLI's account. When that is not the account
paying for this job, the line says so rather than letting you read the numbers as
this job's.

Over 85% on either figure it adds a `WARNING:` line suggesting you stop jobs on
that account and tell Vincent. A failure to run or parse `/usage` is a
**warning, not a crash**: the job still runs, and telemetry records `null` for
the account.

Skip it with `--skip-account-check`. `--dry-run` never calls it, and
`--background` skips it in the child.

## The summary

At most **20 lines**, always:

1. `<type> <name>: <subtype> is_error=… turns=n/max exit=…`
2. the verdict or result line (`VERDICT …`, `ANSWER: …`, `EDIT: …`,
   `ROOT CAUSE: …`, … — otherwise the first non-empty line)
3. `tokens: in … out … cache_read … cache_create …`
4. `cost: $… duration: …s model: … where: …`
5. `permission denials: N (names)`, and a warning if any subagent was spawned
6. as much of the result as fits, then the paths: the full JSON, the log, the
   `/out` folder and the telemetry file.

Exit code: `0` on a clean success, `1` when the result is an error or there is no
result JSON, the child's code if it failed, `2` for a guard refusal.

## Telemetry

One JSON line appended per job to **`C:\nscrev\claude-jobs\jobs.jsonl`**:

```json
{"ts":"2026-09-18T04:11:07Z","type":"review","name":"auditor-debt-review",
 "account":"gmail.user@gmail.com","session_pct":42,"week_pct":61,
 "model":"claude-sonnet-5","where":"docker:claude-exec","service":"claude-exec",
 "clone":"C:/nscrev/cj-auditor-debt","duration_s":841.2,
 "tokens":{"input":90,"output":210,"cache_read":4000,"cache_creation":300},
 "cost_usd":0.0102,"exit_status":"success","exit_code":0,"num_turns":4,
 "max_turns":80,"permission_denials":[],
 "paths":{"brief":"…prompt.md","json":"….json","log":"….log","out":"…/out"}}
```

That gives spend per account, which nothing else records. **A telemetry failure
never fails the job** — it prints `WARNING: telemetry not written (…)` and the
result still stands.

Read spend back with, for example:

```bash
C:/Python313/python.exe -B -c "import json;rows=[json.loads(l) for l in open(r'C:\nscrev\claude-jobs\jobs.jsonl',encoding='utf-8')];print(sum(r['cost_usd'] or 0 for r in rows))"
```

## Reading the result

```bash
C:/Python313/python.exe -B -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(d.get('subtype'), d.get('is_error'), d.get('num_turns'), [x.get('tool_name') for x in d.get('permission_denials') or []]); print(d.get('result'))" C:/nscrev/claude-jobs/<name>.json
```

Files the job wrote to `/out` are in `C:\nscrev\claude-jobs\<name>\`. Check the
result before relying on it, as with any subagent; a job briefed to write
something never reviews it.

## Tests

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/tests/test_run_job.py
```

68 unit tests. No network, no provider, no Docker: `tests/fake_claude.py` and
`tests/fake_docker.py` stand in for the real executables, and the `NSC_RUN_JOB_*`
environment overrides point every path at `C:\nscrev\tmp\run-job\tests\`.

| Override | Redirects |
|---|---|
| `NSC_RUN_JOB_CLAUDE` / `NSC_RUN_JOB_DOCKER` | the executables |
| `NSC_RUN_JOB_JOBS_DIR` / `NSC_RUN_JOB_TELEMETRY` | `claude-jobs\` and `jobs.jsonl` |
| `NSC_RUN_JOB_GUIDE` | the guide the Codex banner is read from |
| `NSC_RUN_JOB_CANONICAL` / `NSC_RUN_JOB_FORBIDDEN_ROOT` | the paths the clone guard refuses |
| `NSC_RUN_JOB_NSCREV` / `NSC_RUN_JOB_COMPOSE_PROJECT` | the host working directory and the compose project |

These exist for the tests. Never set them for a real job.
