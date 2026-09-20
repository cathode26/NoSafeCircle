# `ask_astra.py` — one persistent Astra conversation for every agent

Astra is `gpt-6-astra`. Every agent asks it through **one shared, long-lived Codex thread**, so it
keeps the project's context between questions instead of being re-briefed each time.

Board row: H-20260917-19. Brief: `C:\nscrev\reports\handoffs\ask-astra-tool-brief-20260917.md`.

    C:/Python313/python.exe -B C:/nscrev/astra/ask_astra.py init
    C:/Python313/python.exe -B C:/nscrev/astra/ask_astra.py ask --from "Game Agent" --question "..."
    C:/Python313/python.exe -B C:/nscrev/astra/ask_astra.py ask --from "GER Agent" --question-file q.md
    C:/Python313/python.exe -B C:/nscrev/astra/ask_astra.py status

In Vincent's PowerShell, `&&` is a parse error — use `;`.

## When to ask

Per `C:\NSC\CLAUDE.md`: when you are stuck, or when things go bad — a failure you cannot explain,
or a problem that keeps coming back (a repeated "revise", a FIX FIRST or REJECT twice, the same
failure twice). Ask Astra **before** asking Vincent. Then follow the advice.

## Exit codes

Branch on these; each means exactly one thing.

| code | meaning | what to do |
|---|---|---|
| 0 | answered | the answer is on stdout and in `answers/` |
| 2 | **busy** — another agent holds the thread and still did at the timeout | try later; `status` says who |
| 3 | Codex failed: no binary, non-zero exit, a hung call, or no thread yet | read stderr; `init` if there is no thread |
| 4 | Astra refused: this CLI cannot reach the model | use the one-shot advice job, `nsc-codex-jobs-guide.md` 4.4 |
| 64 | usage error | fix the arguments |

**64, not 2, for a usage error.** argparse exits 2 by default, which would have made "you typed it
wrong" indistinguishable from "Astra is busy" to anything branching on the code.

## One question at a time

The thread is a single conversation, so two questions at once would interleave. `astra.lock`
records owner, pid and start time; waiters poll every 10 s until `--timeout-min` (default 20) and
then exit 2. A lock is stale only when it is **both** older than 30 minutes **and** its pid is
gone — an old lock held by a live, slow agent is not stale and is never stolen.

`--call-timeout-min` (default 10) bounds one Codex call and is separate from the lock wait, so a
long queue cannot leave a real call with two seconds to answer in.

The liveness probe uses `OpenProcess`, never `os.kill(pid, 0)`: on Windows `os.kill` routes
anything that is not a console control event to `TerminateProcess`, so the obvious probe would
kill the process it was asking about. There is a test that spawns a child, probes it, and asserts
it is still running.

## Which Codex binary

Only the **bundled** CLI inside the Codex desktop app can reach `gpt-6-astra`:

    C:\Users\VincentLiguori\AppData\Local\OpenAI\Codex\bin\<hash>\codex.exe

The hash folder changes on every app update, so the binary is found, not configured. The brief
said "newest by modification time"; that is not enough, and would pick the wrong folder on this
machine — there are two hash folders installed in the same minute and **only one contains
`codex.exe` at all**. The scan therefore considers only folders that really have the binary, then
prefers the **highest version**, with mtime as the tiebreak.

Verified 2026-09-18:

| build | version | reaches Astra |
|---|---|---|
| bundled, in the Codex app | `0.155.0-alpha.2.6` | yes — this is the one the tool picks |
| standalone, on PATH | `0.151.0` | no |
| inside the Docker images | `0.154.0` | unverified; the brief tested `0.152.1`, which could not |

The alpha ships only inside the desktop app, not on npm, so no Docker rebuild can supply it. That
is why this tool runs on the host and is the one thing here that does.

## Safety

- `-m gpt-6-astra` and a read-only sandbox are pinned on every call, and the argv is checked
  before it runs: a missing model pin, a missing read-only setting, or any `--dangerously*`,
  `--yolo` or `--full-auto` flag refuses rather than runs.
- `CREATE_NO_WINDOW` on every subprocess — no console flashes on Vincent's screen.
- Nothing is written under `C:\NSC`. A forbidden `NSC_ASTRA_HOME` is refused **before** anything
  is created; an earlier version refused *after* `mkdir` and left the folder behind, which is how
  a reviewer found it.
- UTF-8 without BOM, LF endings, atomic write for `thread.json`.

## What it records

Vincent reads the history here.

    log/<YYYY-MM-DD>.md            every exchange: time, asker, full question, full answer, status
    answers/<utc>-<agent-slug>.md  one file per answer
    thread.json                    thread id, created, model, primer sha256, codex version
    last.json                      the last question's time, asker and status (status reads this)

`init --new` archives the old `thread.json` as `thread-<utc>.json` and never deletes it.

## Tests

    set TEMP=C:\nscrev\tmp\astra & set TMP=C:\nscrev\tmp\astra
    C:/Python313/python.exe -B tests/test_ask_astra.py        # 62 tests, no provider calls
    C:/Python313/python.exe -B tests/mutation_check.py        # 13 guards, each proven to fail

`tests/mutation_check.py` breaks one guard at a time and confirms a named test goes red. It exists
because the first run of the suite was green on the first try, which is when to suspect the tests
rather than trust them — and it immediately found one test that asserted the right outcome for the
wrong reason.

## Live smoke — passed

**2026-09-20, Pipeline Maintainer Agent.** The round trip works. `init`, then `ask --from
"Pipeline Maintainer Agent"` returned the exact requested string with exit 0, and Astra read a
`C:\NSC\*.md` file verbatim from the read-only sandbox. Re-verified the same day from both the
real path `C:\NSC\tools\astra\` and the junction `C:\nscrev\astra\`, after the tools were
committed under `Tools/Host/`. Evidence: `C:\nscrev\reports\tool-verification-20260920.md`.

**Known remaining bug, a false red:** the tool crashes while *printing* an answer containing
non-cp1252 characters and exits non-zero after having succeeded. The answer is safe on disk.

**Still owed:** its first review. Nothing has reviewed this tool at all.

## Environment overrides

Test support only — `NSC_ASTRA_HOME`, `NSC_ASTRA_PRIMER`, `NSC_ASTRA_CODEX_EXE`,
`NSC_ASTRA_CODEX_BIN_ROOT`, `NSC_ASTRA_CODEX_EXE_NAME`, `NSC_ASTRA_FAKE_ALIVE_PIDS`. None of them
relaxes a safety guard: the model, the read-only sandbox and the forbidden-flag check are not
configurable at all. `status` says so out loud when the pid override is active.
