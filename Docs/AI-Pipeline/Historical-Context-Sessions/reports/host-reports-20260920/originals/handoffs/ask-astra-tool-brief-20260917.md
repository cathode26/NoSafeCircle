# Brief: `ask_astra.py`, one persistent Astra conversation for every agent (2026-09-17)

**From:** Documentation Agent. **To:** Pipeline Maintainer Agent. **Board:** H-20260917-19.

## Why

Vincent wants every agent to be able to reach Astra, Codex's best model:
- "use the best model on Codex called Astra for questions you are stuck on";
- "When things go back, Ask Codex, use a Astra for advice. If that advice doesnt help, then ask me."

He first suggested a GitHub issue that Astra checks every 10 minutes, or local files. The Documentation Agent recommended a direct call instead, and Vincent agreed ("awesome"):
- `cathode26/NoSafeCircle` is **public**, so questions would publish project internals;
- polling adds up to 10 minutes per answer;
- files in the repository would dirty the checkout the Game Agent merges into.

## Verified on 2026-09-17 (Documentation Agent)

- **The CLI.** Newest bundled Codex CLI: `C:\Users\VincentLiguori\AppData\Local\OpenAI\Codex\bin\<hash>\codex.exe`, version `codex-cli 0.155.0-alpha.2.6`. The hash folder changes on every app update, so pick the newest by modification time.
- **Starting a conversation.** `codex exec -m gpt-6-astra --skip-git-repo-check --sandbox read-only --json -o first.txt "<primer>"` prints a JSONL event `{"type":"thread.started","thread_id":"01a0ae11-..."}`.
- **Resuming it:**
  - `codex exec resume <thread_id> -m gpt-6-astra --skip-git-repo-check -c sandbox_mode=read-only --json -o answer.txt "<question>"` answered in **5 s**, and the answer showed it remembered the earlier turn.
  - `exec resume` accepts `-m`, `-c`, `--json`, `-o`, `--skip-git-repo-check` and `--ephemeral`. It has **no** `--sandbox` or `--cd` flag; use `-c sandbox_mode=read-only`.
  - The prompt can be `-`, which reads it from stdin.
- **What fails:** the standalone `...\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe` (0.151.0) and Docker Codex (0.152.1) answer "requires a newer version of Codex" for `gpt-6-astra`.

## What to build

Put it outside git, like `viewer-tools` and `ger-tools`: `C:\nscrev\astra\ask_astra.py` plus a `README.md`.

1. **`ask --from "<session title>" (--question-file <md> | --question "<text>") [--timeout-min 20]`**
   - Sends `From <agent>: <question>` into the persistent thread with `exec resume`, reading the prompt from stdin.
   - Prints the answer.
   - Exit codes: 0 answered; 2 still busy at timeout; 3 Codex failed; 4 Astra refused (model unavailable). For 4, print "use the one-shot advice job, nsc-codex-jobs-guide.md 4.4".
2. **`init [--new]`**
   - Starts the thread with the primer in `C:\nscrev\astra\primer.md` (draft below) and stores `C:\nscrev\astra\thread.json` with `thread_id`, `created_at`, `model`, `primer_sha256` and `codex_version`.
   - Refuses if a thread exists. With `--new`, first move the old file aside to `thread-<utc>.json`; never delete it.
3. **`status`:** thread id, the last question's time and asker, the lock holder, and the Codex path and version. Makes no model call.
4. **One question at a time.**
   - Lock file `C:\nscrev\astra\astra.lock` records owner, pid and start time.
   - Waiters poll every 10 s until `--timeout-min`.
   - A lock is stale after 30 min only if its pid is gone.
5. **Record everything.**
   - Append each exchange to `C:\nscrev\astra\log\<YYYY-MM-DD>.md`: UTC time, from, full question, full answer, duration, Codex version, exit status.
   - Also save the answer to `C:\nscrev\astra\answers\<utc>-<agent-slug>.md`.
   - Vincent reads the history there.
6. **Safety.**
   - Always `-m gpt-6-astra` and `-c sandbox_mode=read-only`. Never `--dangerously-bypass-*`.
   - `CREATE_NO_WINDOW` on every subprocess; UTF-8 without BOM; atomic write for `thread.json`; no temp under `C:\NSC`.
7. **Tests.**
   - Unit tests with a fake `codex.exe` (no provider calls): newest-binary pick, `init` and `resume` argv, lock waiting and stale-lock handling, log and answer files, exit codes 2, 3 and 4.
   - One live smoke: `init`, then `ask --from "Pipeline Maintainer Agent" --question "Reply with exactly OK"`. This is Codex spend covered by Vincent's advice-job approval; pause if host Codex quota is above 90% (`nsc_watch.py`).
   - Check that Astra can **read** a `C:\NSC\*.md` file from the read-only sandbox.
8. **Review:** your usual independent review (a Docker review job or `pipeline-reviewer`) before handing it back.

When it lands, tell the Documentation Agent. It will update CLAUDE.md, guide 4.4, the advice template and the agents.

## Primer draft (`C:\nscrev\astra\primer.md`)

```text
You are Astra, the senior technical advisor for No Safe Circle, a Unity game that a team of AI agents builds for Vincent. Agents send you questions they are stuck on, and problems that keep going wrong. Each message starts with "From <agent>:".

The agents: Game Agent (game code, merges, Unity), GER Agent (task contracts), Art Director Agent (2D art), Pipeline Maintainer Agent (pipeline tools), Documentation Agent (docs), Decomposition Agent (splitting tasks), Viewer Agent (graph viewer state).

You are read-only. Read files to answer, but never edit, commit, push, or run paid tools. Useful places:
- C:\NSC\CLAUDE.md and C:\NSC\nsc-*.md: how the team works;
- C:\NSC\NSC\NoSafeCircle: the repository (game design: Docs\GDD\No_Safe_Circle_GDD.md; task contracts: Tasks\);
- C:\nscrev\reports and C:\nscrev\codex-jobs: reports and check results.

Decisions Vincent has made are settled; don't reopen them. If the way forward needs Vincent (scope, spend, or a settled decision), say exactly what to ask him.

Answer briefly, citing files as path:line:
ANSWER or ROOT CAUSE: ...
NEXT STEP: one concrete step
NEEDS VINCENT: no | yes: <the exact question>

Reply now with exactly: READY
```
