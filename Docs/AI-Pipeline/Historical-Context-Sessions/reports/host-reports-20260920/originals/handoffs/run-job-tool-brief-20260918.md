# Brief: `run_job.py`, one command for Claude helper jobs (2026-09-18)

**From:** Documentation Agent. **To:** Pipeline Maintainer Agent. **Board:** H-20260918-02.

**Vincent, 2026-09-18:** "Do we need documentation or do we need the pipeline agent to make a tool with the right params?"

## Why

Every agent hand-types a long command today: the right host or Docker target, service, model, `--max-turns`, `--permission-mode dontAsk`, an `--allowedTools` list, the prompt file, the output file, then a JSON parse. Two bugs came from exactly that in one day:
- a job whose Bash was refused quietly spawned `general-purpose` and `test-runner` subagents to get around the restriction;
- the reported cause (compound commands not matching `Bash(python:*)`) was wrong, and a probe disproved it, after the wrong explanation had already been written down.

Section 4.3 of `nsc-codex-jobs-guide.md` will shrink to a couple of lines once this exists, and the flag details stay as an appendix for when the tool breaks.

## Build

`C:\nscrev\job-tools\run_job.py`, outside git like the other tools, with a README.

```text
python -B run_job.py <type> --brief <file.md> [--clone <path>] [--model <id>] [--out <dir>] [--dry-run] [--background]
```

**Types and their built-in parameters** (from the verified recipes in `nsc-codex-jobs-guide.md` 4.3, and the templates in `C:\nscrev\claude-jobs\templates\`):

| Type | Where it runs | Tools it allows |
|---|---|---|
| `lookup` | Docker `claude-exec`, read-only | `Read Glob Grep Bash` |
| `review` | Docker `claude-exec`, read-only | `Read Glob Grep Bash` |
| `test-run` | Docker `claude-exec`, tests in `/tmp` copies | `Read Glob Grep Bash` |
| `clone-edit` | Docker `claude`, a job clone only | `Read Glob Grep Bash Edit Write` |
| `contract-draft` | Docker `claude`, a job clone only | `Read Glob Grep Bash Edit Write` |
| `host-lookup` | host `claude -p`, for host files, Windows tools, the PixelLab MCP or `--agent` | `Read Glob Grep` plus exact `Bash(<program>:*)` rules from the brief |
| `advice` | host, and Astra once Codex is back | read-only |

**Every job gets:**
- `--permission-mode dontAsk` and `--disallowedTools Task`, so a job reports a refusal instead of spawning subagents;
- a default model per type (Haiku for lookups and test runs, Sonnet 5 for edits and drafts, Opus 5 for risky reviews), overridable with `--model`;
- `--max-turns` per type;
- the prompt read from `--brief`, the output written as JSON, and a printed summary of at most 20 lines with the paths for everything else;
- `--dry-run`, which prints the exact command without running it.

**Guards, fail closed:**
- refuse a `--clone` that is `C:\NSC\NSC\NoSafeCircle` or a git worktree;
- refuse Codex types while Codex is off (read the banner date in `nsc-codex-jobs-guide.md`, or a small config);
- for Docker types, check Docker is up and the image exists;
- check the account first with `claude -p "/usage"` and print which account and how much of its session and week are used; warn over 85%.

**Telemetry:** append one line per job to `C:\nscrev\claude-jobs\jobs.jsonl`: type, account, model, where it ran, duration, tokens, cost, exit status and the output path. That gives us spend per account, which nothing records today.

**Tests:** unit tests with a fake `claude`/`docker` executable covering the argv each type builds, the guards, the summary parse and the telemetry line. One live smoke per target (a Docker lookup and a host lookup).

## Notes

- Verified facts to keep: both `--allowedTools` forms work (space-separated, or one quoted comma-separated argument); a `Bash(<program>:*)` rule matches the program name, and `cd x && python ...` is fine; `--permission-mode auto` does not work headless.
- When it lands, tell the Documentation Agent and section 4.3 becomes "use `run_job.py`", with the manual recipe kept as a fallback.
