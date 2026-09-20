# Report: `run_job.py` built (2026-09-17)

**From:** Pipeline Maintainer Agent. **Brief:** `C:\nscrev\reports\handoffs\run-job-tool-brief-20260918.md` (board H-20260918-02).

## What I built

| File | Lines | What |
|---|---|---|
| `C:\nscrev\job-tools\run_job.py` | 965 | the tool: 7 job types, built-in argv, guards, account check, summary, telemetry |
| `C:\nscrev\job-tools\README.md` | 235 | one usage block per type, what each guard refuses, where telemetry goes |
| `C:\nscrev\job-tools\tests\test_run_job.py` | 838 | 68 unit tests |
| `C:\nscrev\job-tools\tests\fake_claude.py` | 78 | fake `claude`: records argv/cwd/stdin, prints a result JSON, fakes `/usage` |
| `C:\nscrev\job-tools\tests\fake_docker.py` | 90 | fake `docker`: answers `version`/`images`, records `compose run` |

Nothing was written under `C:\NSC`, and nothing outside `C:\nscrev\job-tools\`
and `C:\nscrev\tmp\run-job\`. `C:\nscrev\claude-jobs\jobs.jsonl` does **not**
exist yet: the tool creates it on the caller's first live run. No Claude, Codex,
Docker or Unity job was run, and no provider was called.

```text
python -B run_job.py <type> --brief <file.md> [--clone <path>] [--model <id>]
   [--out <dir>] [--name <n>] [--max-turns <n>] [--agent <a>]
   [--allow-bash <program>] [--allow-tool <rule>] [--add-dir <dir>]
   [--dry-run] [--background] [--skip-account-check] [--timeout <s>] [--astra]
```

## The argv table per type

Docker types, cwd = the job clone, env `MSYS_NO_PATHCONV=1`, stdin = the brief,
stdout = `<jobs>/<name>.json`, stderr = `<jobs>/<name>.log`:

```text
docker compose -p nosafecircle run --rm -T --no-deps \
  -v <out folder>:/out <service> \
  claude -p --model <model> --max-turns <n> --permission-mode dontAsk \
  --allowedTools <tools> --disallowedTools Task --output-format json
```

| Type | Service | Model | `--max-turns` | `--allowedTools` |
|---|---|---|---|---|
| `lookup` | `claude-exec` (ro) | `claude-haiku-4-5-20251001` | 30 | `Read Glob Grep Bash` |
| `review` | `claude-exec` (ro) | `claude-sonnet-5` | 80 | `Read Glob Grep Bash` |
| `test-run` | `claude-exec` (ro) | `claude-haiku-4-5-20251001` | 30 | `Read Glob Grep Bash` |
| `clone-edit` | `claude` (rw) | `claude-sonnet-5` | 60 | `Read Glob Grep Bash Edit Write` |
| `contract-draft` | `claude` (rw) | `claude-sonnet-5` | 60 | `Read Glob Grep Bash Edit Write` |

Host types, cwd = `C:\nscrev` (no workspace-trust stall there):

```text
claude -p [--agent <a>] [--add-dir <dirs>] --model <model> --max-turns <n> \
  --permission-mode dontAsk --allowedTools <tools> --disallowedTools Task \
  --output-format json
```

| Type | Model | `--max-turns` | `--allowedTools` | `--add-dir` |
|---|---|---|---|---|
| `host-lookup` | `claude-haiku-4-5-20251001` | 30 | `Read Glob Grep` + `--allow-bash`/`--allow-tool` rules | only what you pass |
| `advice` | `claude-opus-5` | 40 | `Read Glob Grep` | `C:/NSC C:/nscrev` |

Models, max-turns and tool lists come from guide 4.3 and the header comment of
each template in `C:\nscrev\claude-jobs\templates\` (which carries the verified
`--max-turns`: lookup 30, review 80, test-run 30, clone-edit 60,
contract-draft 60).

A real dry-run against `C:\nscrev\cj-auditor-debt` prints exactly the guide's
shape:

```text
cd C:/nscrev/cj-auditor-debt
MSYS_NO_PATHCONV=1 docker compose -p nosafecircle run --rm -T --no-deps -v C:/nscrev/tmp/run-job/shapecheck:/out claude-exec claude -p --model claude-sonnet-5 --max-turns 80 --permission-mode dontAsk --allowedTools Read Glob Grep Bash --disallowedTools Task --output-format json \
  < C:/nscrev/claude-jobs/auditor-debt-review.prompt.md \
  > C:/nscrev/claude-jobs/shapecheck.json 2> C:/nscrev/claude-jobs/shapecheck.log
```

`--dry-run` prints that copy-pasteable line **and** the exact argv vector as
JSON. In the line the program shows by name (`docker`, `claude`) the way the
guide writes it; the argv block shows the absolute executable the tool actually
execs.

## Flags verified against real `--help` output

Read on this host, 2026-09-17. Docker 29.7.2 / Compose v2; `claude` 2.1.271
(`C:\Users\VincentLiguori\.local\bin\claude.exe`).

### `docker compose --help`

| Flag I emit | Line I matched |
|---|---|
| `compose` | `  compose ... Define and run multi-container applications with Docker` (`Usage:  docker compose [OPTIONS] COMMAND`) |
| `-p nosafecircle` | `  -p, --project-name string        Project name` |
| `run` | `  run                     Run a one-off command on a service` |

### `docker compose run --help`

| Flag I emit | Line I matched |
|---|---|
| service + command position | `Usage:  docker compose run [OPTIONS] SERVICE [COMMAND] [ARGS...]` |
| `--rm` | `      --rm                          Automatically remove the container` |
| `-T` | `  -T, --no-tty                      Disable pseudo-TTY allocation` |
| `--no-deps` | `      --no-deps                     Don't start linked services` |
| `-v <out>:/out` | `  -v, --volume stringArray          Bind mount a volume` |

### `claude --help`

| Flag I emit | Line I matched |
|---|---|
| `-p` | `  -p, --print                           Print response and exit (useful for pipes).` |
| `--agent <a>` | `  --agent <agent>                       Agent for the current session. Overrides the 'agent' setting.` |
| `--add-dir <dirs>` | `  --add-dir <directories...>            Additional directories to allow tool access to` |
| `--model <m>` | `  --model <model>                       Model for the current session. ... or a model's full name (e.g. 'claude-fable-5').` |
| `--permission-mode dontAsk` | `  --permission-mode <mode>              Permission mode to use for the session (choices: "acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan")` |
| `--allowedTools <tools...>` | `  --allowedTools, --allowed-tools <tools...>` / `Comma or space-separated list of tool names to allow (e.g. "Bash(git *) Edit")` |
| `--disallowedTools Task` | `  --disallowedTools, --disallowed-tools <tools...>` / `Comma or space-separated list of tool names to deny (e.g. "Bash(git *) Edit")` |
| `--output-format json` | `  --output-format <format>              Output format (only works with --print): "text" (default), "json" (single result), or "stream-json" (realtime streaming) (choices: "text", "json", "stream-json")` |

Three consequences of those exact lines, which the tool encodes:

- `--allowedTools`, `--disallowedTools` and `--add-dir` are **variadic**
  (`<tools...>`, `<directories...>`), so each must be followed by another flag
  and never by a positional. The tool always emits them in the order
  `--add-dir … --model … --max-turns … --permission-mode … --allowedTools … --disallowedTools Task --output-format json`, which terminates every variadic list with a flag, and it passes the prompt on stdin so there is no positional at all.
- `dontAsk` is a listed choice; `auto` is listed too but the guide records that
  it does not work headless, so the tool never emits it.
- `--output-format json` needs `--print`, which is why `-p` is always first.

### `--max-turns`: accepted but **not documented** in this version's help

`--max-turns` does **not** appear anywhere in `claude --help` for 2.1.271
(`claude --help | grep max-turns` returns nothing; only `--max-budget-usd` is
listed). I verified it is still accepted without running a job, using the fact
that this CLI rejects unknown options during parse and exits before any session
starts:

```text
$ claude --bogus-flag-xyz -p hi
error: unknown option '--bogus-flag-xyz'          # exit 1, control

$ claude --max-turns 3 --zzz-unknown-probe -p x
error: unknown option '--zzz-unknown-probe'       # exit 1: --max-turns parsed fine
```

The second probe errors on the *later* flag, which means `--max-turns 3` was
consumed as a known option and its value taken. I ran the same probe for
`--permission-mode dontAsk`, `--output-format json`, `--disallowedTools Task`,
`--allowedTools Read`, `--agent scribe`, `--model claude-haiku-4-5-20251001` and
`--add-dir C:/NSC` — all seven errored on `--zzz-unknown-probe`, so all seven are
accepted. No provider call, no session: the parse fails first.

**Caveat for the guide's appendix:** an undocumented flag can be removed without
a help-text change. If a future `claude` update starts answering
`error: unknown option '--max-turns'`, that is the flag to drop first.

### `MSYS_NO_PATHCONV=1`

Not a flag — a Git Bash environment variable that stops MSYS rewriting
`/out` into a Windows path inside the `-v` argument. The tool sets it in the
child's environment for Docker runs (so it works from PowerShell too) and shows
it as a prefix on the dry-run line, with a note that PowerShell drops it.

### Image naming

`docker images` on this host lists `nosafecircle-claude-exec:latest` and
`nosafecircle-claude:latest`, i.e. `<project>-<service>:latest` under
`-p nosafecircle`. The image guard checks exactly that name.

## The guards

Each fails closed, exits 2, prints `REFUSED:` and says what to do.

| Guard | Refuses | Says |
|---|---|---|
| clone identity | `C:\NSC\NSC\NoSafeCircle` or any path inside `C:\NSC` | the `git clone -q -c core.autocrlf=true -c core.filemode=false` line |
| git worktree | a clone whose `.git` is a **file**, not a directory | why (shared object store) + the clone line |
| not a repo / missing | no `.git`, or the path does not exist | clone the repo into a fresh folder under `C:\nscrev` |
| compose file | a clone with no `compose.yaml` | use a clone of the repository root |
| clone required | a Docker type without `--clone` | the clone line |
| Docker engine | `docker version` fails or returns nothing | "Start Docker Desktop, wait for it to report running, then try again" |
| Docker image | `docker images -q nosafecircle-<svc>:latest` empty | `docker compose -p nosafecircle build <service>` |
| Codex off | `--astra` while the banner blocks Codex | the banner date and "Do not retry and do not buy credits — that is Vincent's call. Run the Claude path instead (drop `--astra`)" |
| `--astra` scope | `--astra` on any type but `advice` | which type it belongs to |
| brief | missing, not a file, empty, or still carrying the template header comment | fill every `<...>`, delete the comment, use the Write tool |
| model | not an alias and not `claude-*` (so `gpt-6-astra` never reaches `claude`) | the aliases |
| host-only flags | `--agent`, `--allow-bash`, `--allow-tool`, `--add-dir` on a Docker type | why (no agent files mounted; the type carries its verified list) |
| bash rule shape | `--allow-bash` given a path or a command line | a `Bash(<program>:*)` rule matches the program name; pass `git`, not a path |
| output path | `--out` inside `C:\NSC` | output goes under `C:\nscrev\claude-jobs` |
| job name | `--name` with anything but `[A-Za-z0-9._-]` | use a safe name |
| executables | `claude`/`docker` off PATH, or an `NSC_RUN_JOB_*` override pointing at nothing | install it or unset the override |

**The Codex date is read, not hard-coded.** `read_codex_banner()` greps
`nsc-codex-jobs-guide.md` for `No Codex until (\d{4}-\d{2}-\d{2})` — today that
matches line 9, "No Codex until 2026-09-19: all Claude for everything" — and
compares it to today's date. A missing banner, an unreadable guide or an
unparseable date all **refuse** rather than assume Codex is back.

Verified against the live filesystem (read-only, no job run):
`--clone C:/NSC/NSC/NoSafeCircle` → refused as the canonical checkout;
`--clone C:/nscrev/branch-verify` (a real worktree) → refused as a worktree.

## The account check

Before each job: `claude -p "/usage" --output-format json`, from `C:\nscrev`,
with a 180 s timeout. It prints one line:

```text
account: gmail.user@gmail.com  session 42%  week 61%
```

and adds a `WARNING:` line for either figure over 85%, suggesting you stop jobs
on that account and tell Vincent. The parser is deliberately tolerant (it reads
`result` out of the JSON, falls back to raw text, finds an email or an
`Account:`-style label, and matches `session`/`week` near a percentage in either
order). **A failure to run or parse it is a warning, not a crash** — the job
still runs and telemetry records `null` for the account. It is the only command
that talks to the provider, and it is skippable with `--skip-account-check`;
`--dry-run` never calls it and `--background` skips it in the detached child.

## Telemetry

One JSON line appended per job to `C:\nscrev\claude-jobs\jobs.jsonl`: `ts`,
`type`, `name`, `account`, `session_pct`, `week_pct`, `model`, `where`
(`host` or `docker:<service>`), `service`, `clone`, `duration_s`, `tokens`
(input / output / cache_read / cache_creation), `cost_usd`, `exit_status`,
`exit_code`, `num_turns`, `max_turns`, `permission_denials`, and `paths`
(brief, json, log, out). The whole write is inside one `try/except Exception`
that prints `WARNING: telemetry not written (…)` — **a telemetry failure never
fails the job**, and a test proves it by pointing the telemetry path through a
regular file.

## The summary

At most 20 lines, hard-capped: the header line (`subtype`, `is_error`,
`turns=n/max`, `exit`), the verdict or result line, `tokens:`, `cost/duration/
model/where`, `permission denials: N (names)`, a warning if any subagent was
spawned, then as much of the result as fits, then the paths to the full JSON,
the log, the `/out` folder and the telemetry file. The verdict line is the first
line starting with `VERDICT`, `ANSWER`, `RESULT`, `EDIT`, `DRAFT`, `TESTS`,
`ADVICE`, `ROOT CAUSE`, `NEXT STEP`, `FINDINGS`, `SUMMARY`, `NOT FOUND` or
`REFUSED`, which covers every template's reply format; otherwise the first
non-empty line.

## What the tests cover

`C:/Python313/python.exe -B C:/nscrev/job-tools/tests/test_run_job.py` →
**68 tests, OK** (about 27 s). No network, no provider, no Docker, no Unity: the
two fake executables are `.py` files driven through `.cmd` shims written into
`C:\nscrev\tmp\run-job\tests\`, and every path is redirected with the
`NSC_RUN_JOB_*` overrides.

- **argv per type** — the full vector for all five Docker types (compose flags,
  the `-v <out>:/out` mount, service, then the inner `claude` argv) and both host
  types; `--model` alias, `--max-turns` and `--out` overrides; `--agent`;
  `--allow-bash` building `Bash(<program>:*)`; `--allow-tool` passing an exact
  command prefix verbatim; `advice` being Opus with `--add-dir` and no
  Bash/Edit/Write; and a loop asserting **every** type emits
  `--permission-mode dontAsk`, `--disallowedTools Task` and `--output-format json`.
- **guards** — canonical checkout, anything under `C:\NSC`, worktree
  (`.git` as a file), non-repo, missing clone, missing `compose.yaml`, Docker
  type without `--clone`, host type's clone guarded too; engine down; image
  missing; engine-and-image checked *before* the compose call (asserted on the
  recorded call order); Codex off with the banner date, the date coming from the
  banner and not a constant, fail-closed on a banner that is missing or
  unreadable, `--astra` on the wrong type, and `--astra` once the banner date has
  passed; brief missing / empty / still a template; bad model; host-only flags on
  a Docker type; `--allow-bash` given a path; `--out` inside `C:\NSC`; unsafe job
  name; unknown type; a missing executable override.
- **summary parse** — the 20-line cap for a 500-line result and end to end for a
  200-line one; the counts line and `permission denials: 3 (Task, Write)` plus
  the subagent warning; verdict-line selection across six shapes; no result JSON;
  garbage (non-JSON) output exiting 1 without a traceback; `is_error` exiting 1;
  the brief arriving as stdin and the `.json`/`.log` landing on disk.
- **telemetry** — one line with every field asserted individually; append (never
  rewrite) across two jobs; `exit_status` for error and no-result-json; no line
  on `--dry-run`; and a telemetry failure leaving the job at exit 0 with its
  summary intact.
- **account check** — the printed account and both percentages; the over-85%
  warnings; unparseable `/usage` continuing as a warning; `--skip-account-check`
  and `--dry-run` making no provider call at all; and four `parse_usage` shapes
  including a JSON-wrapped one and a no-match one.
- **`--background`** — returns at once, and the detached child still runs the
  job, writes telemetry and forwards every flag (`--model`, `--max-turns`,
  `--agent`, `--allow-bash`, `--allow-tool`, `--add-dir`, `--name`).

## What I did not do, and why

1. **No live smoke test.** Running one would spend the team's tokens; the brief
   leaves it to the caller. Commands are below. Everything short of the provider
   call is verified: real `--help` output, the real Docker engine and image list,
   the real worktree and canonical-checkout guards, and a real dry-run.
2. **`--astra` does not run Codex.** The brief lists `advice` as "host, and Astra
   once Codex is back", but this tool only builds `claude` command lines. So
   `advice` runs on host Claude Opus 5 (read-only, `--add-dir C:/NSC C:/nscrev`),
   which matches the guide's banner instruction to use Opus for advice while
   Codex is off. `--astra` is wired to the Codex-off guard and, once the banner
   date passes, refuses with a pointer to the guide's 4.4 recipe (the bundled
   `AppData\Local\OpenAI\Codex\bin\<hash>\codex.exe`, `-m gpt-6-astra`,
   `--sandbox read-only`, `--output-last-message`) rather than guessing at an
   argv I could not verify. Adding a real Codex path is a small follow-up once
   Codex is back and its CLI can be probed.
3. **`advice` runs on the host, not in `claude-exec`.** The brief's table says
   host; the guide's banner describes it as a read-only Docker job with
   `-v C:/NSC:/nsc:ro -v C:/nscrev:/nscrev:ro`. I followed the brief, since
   advice reads host reports and the journal. `--add-dir` replaces the `:ro`
   mounts. If you want the Docker form too, it is a new type, not a flag.
4. **One live smoke per target, not per type.** The brief asks for a Docker
   lookup and a host lookup; that is what the commands below do.
5. **`--brief` stays required.** The brief's synopsis marks it required and every
   template is a file, so there is no stdin-only mode.

## The live smoke test for the caller

Both commands are real jobs on the Gmail account and will spend tokens. Run the
dry-runs first; they cost nothing.

**1. Host lookup (cheapest — Haiku, read-only, no Docker).**

```bash
# the brief (Write tool, not printf/echo)
cat > /dev/null <<'NOTE'
Write C:/nscrev/claude-jobs/run-job-smoke-host.prompt.md with:
  Reply in exactly one line: ANSWER: <the first heading in C:/nscrev/job-tools/README.md>.
  Read only that file. If a tool is refused, say so and stop; do not start a subagent.
NOTE

C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py host-lookup \
  --brief C:/nscrev/claude-jobs/run-job-smoke-host.prompt.md \
  --max-turns 3 --dry-run

C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py host-lookup \
  --brief C:/nscrev/claude-jobs/run-job-smoke-host.prompt.md \
  --max-turns 3
```

**2. Docker lookup** (needs Docker Desktop running and an existing job clone;
`C:\nscrev\cj-auditor-debt` is one, or make a fresh one):

```bash
C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py lookup \
  --brief C:/nscrev/claude-jobs/run-job-smoke-docker.prompt.md \
  --clone C:/nscrev/cj-auditor-debt --max-turns 3 --dry-run

C:/Python313/python.exe -B C:/nscrev/job-tools/run_job.py lookup \
  --brief C:/nscrev/claude-jobs/run-job-smoke-docker.prompt.md \
  --clone C:/nscrev/cj-auditor-debt --max-turns 3
```

(Brief for the Docker one: *"Reply in exactly one line: ANSWER: \<the number of
services in /workspace/compose.yaml\>. Use only Read or Grep on that file. If a
tool is refused, say so and stop; do not start a subagent."*)

**What to check after each run:**

- the printed `account:` line names the **Gmail** account, not Outlook — if it
  says Outlook, stop: the host CLI is logged in to the wrong account;
- the summary is ≤ 20 lines and ends with the four paths;
- `C:\nscrev\claude-jobs\jobs.jsonl` gained exactly one line, with a non-null
  `cost_usd` and the right `where` (`host` / `docker:claude-exec`);
- `permission_denials` is `[]` and no subagent warning appeared.

## Follow-ups

- Tell the Documentation Agent (board H-20260918-02): section 4.3 becomes "use
  `run_job.py`", with the manual recipe kept as a fallback appendix. The
  `--max-turns` caveat above belongs in that appendix.
- Once Codex is back (banner date 2026-09-19), add the real Astra path behind
  `--astra`, probing `codex exec --help` from the bundled CLI first.
