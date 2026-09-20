# Running Codex bulk jobs safely

Vincent wants bulk work in Codex so Claude's budget lasts: inventories, sweeps, drafts, mechanical fixes, test runs. This guide is how any role hands a job to Codex without breaking the real repo.

Written 2026-09-16 from the 9/15 Docker job (and what went wrong in it), the GER host rounds, and `compose.yaml`.

---

> **Codex returns in TWO steps - there are two Codex Pro accounts** (Vincent: "we have 2 codex pro accounts so 1 on the 19th the next on the 22nd"): the first resets **2026-09-19**, the second **2026-09-22 18:55 local**. Until the first, everything is Claude.
> - **Scope:** host and Docker Codex share the account. Both answered "You've hit your usage limit" on 2026-09-17, first seen about 07:04 UTC.
> - **What fails until then:** reviews (4.2), Astra advice (4.4), do jobs (4.1), contract closure reviews, GER rounds, Codex crew roles and Codex decomposition authoring.
> - **Don't** retry, and don't buy credits; that's Vincent's call.
>
> **Meanwhile, use Claude on the Gmail account** (Docker jobs, section 4.3):
> - **Reviews and contract checks:** the `review` job (Sonnet 5; Opus 5 for risky code). For a contract check, run it from the check's clone with the filled closure-review prompt.
> - **Advice instead of Astra:** fill `advice-prompt.md` and run it as a read-only `claude-exec` job with `--model claude-opus-5`.
>   - Add `-v "C:/NSC:/nsc:ro" -v "C:/nscrev:/nscrev:ro"` so it can read the docs and reports (verified).
>   - In the prompt, write paths as `/nsc/...` and `/nscrev/...`.
> - **Easy work:** the `lookup`, `test-run` and `clone-edit` jobs.
> - **Crews and decomposition:** all-Claude providers in Docker.
>   - For crews, use `worker-claude-sonnet-high.json` (provider `claude`, `claude-sonnet-5`), not `worker-codex-sol-high.json`. Both are in `.assistant-control`.
> - **ArchitectureReview** (the standalone batch in `Pipeline/ArchitectureReview/`, last run 2026-08-23; today's crews don't call it): if it's needed, run the Claude entry point, `docker compose -p nosafecircle run --rm claude-review python3 Pipeline/ArchitectureReview/architecture_review_claude.py`.
> - **GER rounds:** Claude for every node. The Codex nodes (generate, refine) need a tool change, which is queued with the Pipeline Maintainer.

## 1. Pick the right Codex

| Need | Use | Auth |
|---|---|---|
| A one-shot job that reads or writes a repo copy | **Docker `codex` service** (section 2) | volume `nosafecircle_codex-config` (runbook section 3.2) |
| GER rounds | host `codex exec` via `C:\NSC\tools\ger\ger_node.py` (GER guide) | host `%USERPROFILE%\.codex` |
| Decomposition | AssistantControl `decompose` (Decomposition guide), which runs Codex inside `round-robin-decompose` | volume |
| Crew execution | `worker-codex-sol-high.json` through the Task Orchestrator | volume |
| A long interactive orchestrator | Codex desktop app (Vincent starts it) | desktop account |

Docker Codex **cannot run Unity**; it is a Linux container. Anything that needs Unity validation comes back to the Windows host.

---

### 1a. Which Codex account am I actually signed in as? (2026-09-19)

**`codex login status` cannot answer this. It prints only `Logged in using ChatGPT` and never names the account** - byte-identical output before and after a wrong account is corrected. **So it is not evidence. Decode the token's identity claims instead.**

**Why this rule exists.** On 2026-09-19 the host Codex CLI was silently signed in as a **third** account - `vincent.liguori@xpress-solutions.net`, plan **`prolite`** - which is neither of the two Codex **Pro** accounts the rest of these documents assume. Nobody noticed, because `login status` looked normal. **A live Astra `init` was spent on the wrong account before it was found**, and it was found only by decoding the JWT. (Pipeline Maintainer, 2026-09-19.)

**Assume nothing from the account count.** `CLAUDE.md` describes two Codex Pro accounts; at least three logins have existed on this machine. **Check, per surface, before spending.**

**Docker volume** - verified working 2026-09-19. It reads `auth.json` in place and prints identity only: never a token, and it copies nothing out.

```powershell
cd C:\NSC\NSC\NoSafeCircle
docker compose -p nosafecircle run --rm -T -v C:\NSC\tools\jobs:/acct codex python3 /acct/whoami.py
```

**In the codex image `auth.json` is at `/home/agent/.codex/auth.json`, not `/root/`.** That one path detail is what makes the command above work.

**Host:** decode `~/.codex/auth.json` the same way.

> **The script lives at `C:/NSC/tools/jobs/whoami.py`** (moved there 2026-09-20; confirmed present from this session, and the Pipeline Maintainer verified it runs from the new path). Host use: `python -B C:\NSC\tools\jobs\whoami.py`.
>
> **A stale copy still sits at `C:/Users/VincentLiguori/AppData/Local/Temp/nsc-acct/`.** Ignore it; a temp folder is not a documentable location and Windows may clear it at any time. **If both ever disagree, the `C:/NSC/tools/jobs/` copy is the one the docs mean.**
>
> **And if the script is missing entirely, the method still stands:** read the identity claims out of `auth.json` and print email, name, plan and account id — **never the token.**

**All four logins, measured 2026-09-19 by the Pipeline Maintainer:**

| surface | account | plan |
|---|---|---|
| Host Claude CLI | `cathode26@gmail.com` | Max |
| Docker Claude | `cathode26@gmail.com` | Max |
| Host Codex | `Vincent.j.liguori@outlook.com` | pro |
| Docker Codex | `Vincent.j.liguori@outlook.com` | pro |

**These are a reading, not a standing fact.** A login can change between sessions - that is the whole point of the rule. Re-read before a batch.

---

## 2. The safe Docker pattern: always a separate clone

**Never** run a job against `C:\NSC\NSC\NoSafeCircle` itself.
- The plain `codex` service mounts the repo **read-write**. On 9/15 a job ran `git checkout` inside the container and switched Vincent's real checkout to another branch.
- That service also lacks `core.autocrlf`, so git inside saw 1,744 phantom changes. The same job crashed a tool call and made zero commits.

### 2.1 Prepare (host, Git Bash)

```bash
JOB=codex-art-inventory-$(date +%Y%m%d-%H%M)          # short topic + time
CLONE=C:/nscrev/codex-jobs/$JOB
git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true C:/NSC/NSC/NoSafeCircle "$CLONE"
git -C "$CLONE" config user.name  "No Safe Circle Codex Job"
git -C "$CLONE" config user.email "codex-job@nosafecircle.invalid"
git -C "$CLONE" switch -c codex/$JOB                    # the job's only branch
```

- The clone copies committed `main` only. Vincent's uncommitted edits are not included, which is intended.
- **Why the `-c` settings.** The host's `autocrlf=true` comes from the Git for Windows *system* config, which the Linux container never reads. Clone-local settings make git inside the container see the same clean tree (the other session confirmed this on 9/16).
- **Never use a git worktree for a container job.** A worktree's `.git` file points at a Windows path the container can't resolve. Always use a standalone clone.

### 2.2 Write the prompt to a file

Write it to `C:\nscrev\codex-jobs\$JOB.prompt.md`, never inline; long quoted heredocs fail silently.

A complete prompt ("Give complete prompts, never splice") includes:
- **Goal and scope.** Which files it may change. Read-only or commit?
- **Where it works:** `/workspace` is its own clone on branch `codex/<job>`. It must not switch branches or create others.
- **What to produce:** commits on that branch, and/or a report file `/workspace/CODEX_JOB_REPORT.md` (don't commit the report).
- **What not to do:** no push, no network except the model, no Docker, no touching other paths. It can't run Unity.
- **How to finish:** the final message summarizes what changed, commit SHAs, what it couldn't do, and anything unverified.
- **Repo rules** it must read: `AGENTS.md` and the relevant guide.

### 2.3 Run

```bash
cd "$CLONE"
docker compose -p nosafecircle run --rm -T codex bash -lc \
  'cd /workspace && codex exec --sandbox danger-full-access --skip-git-repo-check -c model_reasoning_effort=high --color never --output-last-message /workspace/CODEX_JOB_REPORT.md -' \
  < C:/nscrev/codex-jobs/$JOB.prompt.md > C:/nscrev/codex-jobs/$JOB.log 2>&1
```

- Running **from the clone directory** makes `/workspace` the clone, because compose uses the clone's own `compose.yaml`.
- **`-p nosafecircle` is required.** Without it the project name becomes the clone's folder name, which gives empty credential volumes and no login. With it the job uses `nosafecircle_codex-config`.
- This is the pattern the branch-recovery session used for the NSC-075 job on 2026-09-16: 16 minutes, 3 commits, only the owned files.
- `-T` means no TTY, so stdin carries the prompt. `-` tells `codex exec` to read the prompt from stdin.
- Reasoning effort: `medium` for mechanical work, `high` for design or review-grade work. Vincent's GER setting is `high`; `xhigh` roughly doubles time.
- Run it in the background from the Bash tool and monitor the log.
- **PowerShell alternative.** PowerShell 5.1 pipes native stdin as ASCII, which mangles non-ASCII text, so prefer Git Bash. Or use `cmd /c "docker compose ... - < C:\nscrev\codex-jobs\<job>.prompt.md > C:\nscrev\codex-jobs\<job>.log 2>&1"`.
- The 9/15 five-task job used 108,732 tokens and took about 8 minutes.
- Run at most two Docker Codex jobs at once. Parallel refreshes of one credential volume are untested.

### 2.4 Monitor

- `tail -f C:/nscrev/codex-jobs/$JOB.log`. The header shows model, sandbox, effort and session id.
- `docker ps --format '{{.Names}} {{.Status}}' | grep codex`
- Quota: see the Watcher check (`nsc-watcher-guide.md`). A job that stops with a usage-limit message in the log has not finished; record it as cut off.

### 2.5 Collect and review (never trust authorship)

```bash
git -C "$CLONE" log --oneline main..HEAD
git -C "$CLONE" status --short          # expect only CODEX_JOB_REPORT.md untracked
cat "$CLONE/CODEX_JOB_REPORT.md"
```

- **Review the diff yourself**, or have a fresh reviewer do it: `git -C "$CLONE" diff main...HEAD`.
- **Check claims against files.** A job's "tests pass" means nothing unless you ran them. Codex jobs have claimed work that wasn't done.
- **Bring it into the canonical repo as a branch** only when it is worth reviewing. This writes a ref only, not the working tree:

  ```bash
  git -C C:/NSC/NSC/NoSafeCircle fetch "$CLONE" codex/$JOB:codex/$JOB
  ```

- From there the **Integration Steward** handles merging (merge-tree inspection, trial merge, Vincent's go). Never merge a Codex branch straight into `main`.
- **Journal the job:** name, prompt path, log path, commits, verdict.

### 2.6 After the job

- **Keep the branch.** Once fetched into the canonical repo, the job branch follows the steward's rules. NSC-### work branches are never deleted (Vincent, 9/16).
- The clone folder can be removed once its branch is fetched and reviewed, but only with Vincent's OK. Claude's permission guard often refuses deletes; give Vincent the command.
- Keep the prompt and log files.

---

## 3. Branch discipline for Codex

On 9/14 Codex created 81 branches in a day: new ones per retry, suffixed `-provisional`, `-validation`, `-exact-unity`, `-current-main`, `-main-ready`, `-final-main`. Their names often didn't match their contents.

For every job:
- **One job, one branch** (`codex/<job>`). Retries add commits on the same branch. A new job gets a new branch, and the old one is recorded in the journal as superseded, not deleted.
- **No worktrees** in `C:\NSC\_worktrees` for Codex jobs. Use the clone folder.
- **Put the branch purpose in its first commit message**, and record the branch in the journal.

---

## 4. Easy work and adversarial reviews through Codex (Vincent, 2026-09-16)

Vincent (2026-09-16):
- "We can also task cheaper subagents through codex to do easy work, because we dont want to exhaust all of the tokens on claude."
- "we should add the ability to have codex do tasks for us which will include adversarial review. We want codex to verify our work through the pipeline. IT should support generic tasks."

**The tool is coming.** The Pipeline Maintainer Agent is building a generic Codex jobs command with `do` and `review` modes, durable records, structured verdicts and a cheap preset. Brief: `C:\nscrev\reports\handoffs\pipeline-maintainer-codex-jobs-and-mixed-crews-brief-20260916.md`. **Until it lands, use the manual recipes below.**

### 4.1 Easy work to Codex instead of Claude

- **Good fits:** inventories, greps across many files, mechanical edits, test runs, porting a known commit, drafting a report from files.
- **How to run it:** the section 2 recipe, with `-c model_reasoning_effort=medium` for mechanical work.
- **Choose a Claude Haiku or Sonnet subagent instead** when the step needs your session's context or Windows-only tools and isn't worth a job's setup, or when it must finish in seconds.
- **Always check the result yourself.** Never trust authorship.

### 4.2 Adversarial review of our own work by Codex

Use it for a Pipeline Maintainer fix branch, a Game Agent merge candidate, a crew candidate, or a doc that makes claims about code. The review is **advisory**: it informs Vincent and the merging agent, and it never blocks by itself.

**Merge candidates (Game Agent).** Vincent (2026-09-16) wants Codex, not the Game Agent, to verify merge candidates.
- **Review the trial-merge commit** in `C:\nscrev\branch-verify`: base = the `main` commit the trial merge sits on, head = the trial-merge commit. Reviewing that commit, not the side branch, checks the combination that will land.
- **Pick the runtime** that can run the relevant tests: host for Windows-only suites, Docker otherwise.
- **Codex can't run Unity.** Unity checks stay with the Game Agent (`run_unity_tests_clean.ps1` on the exact commit), unless Vincent explicitly allows a host Codex Unity run.
- **Timing:** the generic Codex jobs CLI is queued with the Pipeline Maintainer Agent. Don't wait for it; use these manual recipes until this section says otherwise.

Templates, in `C:\nscrev\codex-jobs\templates\`:
- `adversarial-review-prompt.md`: fill in the `<...>` fields;
- `verdict.schema.json`: the structured verdict (APPROVE, FIX_FIRST or REJECT, plus findings, tests_run and scope_check).

**Docker** (default; Linux-runnable checks):

```bash
JOB=codex-review-<topic>-$(date +%Y%m%d-%H%M)
CLONE=C:/nscrev/codex-jobs/$JOB
git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true <repo-or-author-clone> "$CLONE"
git -C "$CLONE" checkout -q --detach <head-sha>
cp C:/nscrev/codex-jobs/templates/verdict.schema.json "$CLONE/CODEX_VERDICT_SCHEMA.json"
# write the filled prompt to C:/nscrev/codex-jobs/$JOB.prompt.md with the Write tool
cd "$CLONE"
docker compose -p nosafecircle run --rm -T codex bash -lc \
  'cd /workspace && codex exec --sandbox danger-full-access --skip-git-repo-check -c model_reasoning_effort=high --color never --output-schema /workspace/CODEX_VERDICT_SCHEMA.json --output-last-message /workspace/CODEX_VERDICT.json -' \
  < C:/nscrev/codex-jobs/$JOB.prompt.md > C:/nscrev/codex-jobs/$JOB.log 2>&1
```

**Host** (for Windows-only checks such as `Pipeline.AssistantControl.test_viewer`, which needs `ctypes.WinDLL`; still no Unity):

```bash
"C:/Users/VincentLiguori/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe" exec --sandbox workspace-write --cd "$CLONE" --skip-git-repo-check -c model_reasoning_effort=high --color never --output-schema "$CLONE/CODEX_VERDICT_SCHEMA.json" --output-last-message "$CLONE/CODEX_VERDICT.json" - < C:/nscrev/codex-jobs/$JOB.prompt.md > C:/nscrev/codex-jobs/$JOB.log 2>&1
```

- **Sandbox on the host.** If the host sandbox is unavailable on Windows, stop and ask Vincent. Never switch the host run to `danger-full-access` on your own.
- **Host limits seen 2026-09-16 (Game Agent):**
  - host `workspace-write` can't write `.git`, so **"do" jobs that commit must run in Docker**; use the host only for reviews and test runs;
  - check Docker is running before a job (`docker info`);
  - host-sandbox runs produce environment errors (SID mapping, `TemporaryDirectory` ACL). Tell the reviewer to report these as environment noise under `scope_check`, not as findings.
- **401 or "Not logged in" on the host.**
  - Run `codex login status`. The login file can be caught mid-refresh: on 2026-09-17 around 05:10 UTC, three jobs failed with 401 while `auth.json` was being rewritten, and a minute later the status was "Logged in using ChatGPT".
  - Wait a minute and retry once. If it still fails, ask Vincent to run `codex login` (or sign in through the Codex app).
  - Never copy or edit `auth.json`.
- **Which account's quota?** `nsc_watch.py` reads only the **host** Codex account. Docker jobs use the login in the `nosafecircle_codex-config` volume, which **can** be a different account - they are separate logins and can drift. **Measured 2026-09-19: both carried the same `chatgpt_account_id` (`7cea98a0-d6da-4ac4-b5dc-9b54e0d7471b`), so they shared one quota pool and the host reading did reflect Docker spend.** That is a reading, not a guarantee. **Section 1a says how to check rather than leaving it unknowable** - which is the point: the old wording said the accounts "may differ" and gave no way to find out. Until the Codex jobs CLI records rate limits per job, watch Docker job logs for usage-limit stops, and apply the 90% pause to the host account only.
- **Plain code review option:** `codex exec review --base <branch>` or `--commit <sha>`, with the filled prompt as custom instructions.
- **Reading the result:** read `CODEX_VERDICT.json`. A missing or invalid verdict means the review didn't happen. Record the job name, head sha and verdict in the journal and in your two-line note to Vincent.
- **Spend: review jobs are pre-approved** (Vincent, 2026-09-16).
  - Codex reviews of our own work and of merge candidates run without asking, including host runs for Windows-only tests.
  - **Pause them once Codex weekly quota passes 90%;** check with `python -B C:\NSC\tools\viewer\nsc_watch.py`.
  - Codex **"do" jobs** (section 4.1 and bulk jobs) still need Vincent's go.
  - Record "standing approval 2026-09-16" in the journal line for each review.

### 4.3 Claude helper jobs in Docker, on the Gmail account (Vincent, 2026-09-17)

Vincent (2026-09-17): "we can use both accounts at the same time, so trying to use the pipeline for sub agents is a great way to keep you alive for a week until we have more tokens."

**Why.** Desktop agent sessions and their Agent-tool subagents spend the **Outlook** Claude account. Docker Claude (volume `nosafecircle_claude-config`) is logged in to the **Gmail** account, a Max plan. A Claude job in Docker spares the desktop account. Both accounts work at the same time.

**Where helper work goes, in this order:**
1. **Codex** (4.1, 4.2): easy bulk work and adversarial reviews.
2. **A Docker Claude job** (this section): Claude reviews, lookups, test runs, mechanical edits in a job clone, contract drafts.
3. **An Agent-tool subagent** (desktop account), only when the step needs:
   - Unity (`unity-runner`, `delivery-evidence`);
   - PixelLab (`pixellab-batch-recorder`);
   - files outside a repo clone (`scribe`, `doc-sync`, `BOARD.md`, the journal, `C:\NSC` docs);
   - Windows-only tests;
   - or your session's context.

**Approved** (Vincent, 2026-09-17) for helper work in your own lane; no per-job ask. Limits:
- One job at a time per agent. Crews and decomposition use the same Gmail account.
- If a job's result mentions a usage or rate limit, stop Docker Claude jobs, tell Vincent in one line, and use Codex. Never log Docker in to another account.
- A job never pushes, never runs in the canonical checkout or a worktree, and never runs Unity, `codex` or `claude`.

**Recipe.** Verified 2026-09-17 with two jobs:
- a read-only Sonnet 5 job, where Write was refused;
- a read-write Haiku 4.5 job, where `python3` ran and `git status` stayed clean.

1. **Make a job clone.** Use a standalone clone, never `C:\NSC\NSC\NoSafeCircle` or a worktree:
   ```bash
   git clone -q -c core.autocrlf=true -c core.filemode=false C:/NSC/NSC/NoSafeCircle C:/nscrev/cj-<name>
   git -C C:/nscrev/cj-<name> checkout -q <sha or branch>
   mkdir -p C:/nscrev/claude-jobs/<name>
   ```
   For a review, check that both commits are in the clone: `git -C C:/nscrev/cj-<name> cat-file -e <sha>`.
2. **Write the prompt.** Copy a template from `C:\nscrev\claude-jobs\templates\` to `C:\nscrev\claude-jobs\<name>.prompt.md` and fill every `<...>`.
   - The job sees only the clone (`/workspace`), `/tmp` and `/out`.
   - It can't see `C:\NSC` docs, agent files or other sessions, so put the facts it needs in the prompt.
3. **Run it from the clone folder** (Git Bash; in PowerShell drop `MSYS_NO_PATHCONV=1` and the backslash line breaks):
   ```bash
   cd /c/nscrev/cj-<name>
   MSYS_NO_PATHCONV=1 docker compose -p nosafecircle run --rm -T --no-deps \
     -v "C:/nscrev/claude-jobs/<name>:/out" <service> \
     claude -p --model <model> --max-turns <n> --permission-mode dontAsk \
     --allowedTools <tools> --output-format json \
     < /c/nscrev/claude-jobs/<name>.prompt.md \
     > /c/nscrev/claude-jobs/<name>.json 2> /c/nscrev/claude-jobs/<name>.log
   ```
   - `<service>`: `claude-exec` mounts the clone **read-only** (lookups, reviews, test runs). `claude` mounts it **read-write** (edits, drafts); run that one only from a job clone.
   - `<model>`: `claude-haiku-4-5-20251001` for lookups and test runs; `claude-sonnet-5` for edits, drafts and most reviews; `claude-opus-5` for reviews of identity, locking, provider-spend or merge code.
   - `<tools>`: `Read Glob Grep Bash` for `claude-exec`; add `Edit Write` for `claude`. Tools that aren't listed are refused, never asked.
   - For a long job, pass `run_in_background` to the Bash tool; you'll be told when it ends.
4. **Read the result:**
   ```bash
   python -B -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(d.get('subtype'), d.get('is_error'), d.get('num_turns'), [x.get('tool_name') for x in d.get('permission_denials') or []]); print(d.get('result'))" C:/nscrev/claude-jobs/<name>.json
   ```
   - `success` with `is_error False` means it finished; `error_max_turns` means it ran out of turns.
   - Files the job wrote to `/out` are in `C:\nscrev\claude-jobs\<name>\`.
   - Check the result before relying on it, as with any subagent. A job you briefed to write something never reviews it.
5. **Git inside the container** refuses to clone `/workspace` ("dubious ownership") until the job runs `git config --global --add safe.directory "*"`. The review and test-run templates do this. `git -C /workspace log` and `status` work without it.

| Template | Service | Model | Instead of |
|---|---|---|---|
| `lookup-job-prompt.md` | `claude-exec` | Haiku or Sonnet | Explore or Haiku lookup subagents |
| `review-job-prompt.md` | `claude-exec` | Sonnet; Opus for risky code | `pipeline-reviewer` and other Claude reviews |
| `test-run-job-prompt.md` | `claude-exec` (tests run in `/tmp` copies) | Haiku | `test-runner`, except Windows-only tests |
| `clone-edit-job-prompt.md` | `claude` | Sonnet | Sonnet "easy fix" subagents; porting a known commit |
| `contract-draft-job-prompt.md` | `claude` | Sonnet | `ger-drafter` |

**Coming:** the Pipeline Maintainer Agent is adding a Claude-in-Docker provider to the jobs CLI (board row H-20260917-11). Until it lands, use this recipe.

#### Host `claude -p` jobs, also on the Gmail account (verified 2026-09-17)

**Check the account before every job. Never assume it.** The host CLI's login changes: on 2026-09-17 it read `cathode26@gmail.com` in the morning, then `Vincent.j.liguori@outlook.com` for part of the day (about $19 of host jobs landed on the desktop account before the Pipeline Maintainer caught it, plus two GER Agent reviews run on the host around 21:00-21:10 UTC while Docker was down), and reads `cathode26@gmail.com` again now.

- **The rule** (Vincent, 2026-09-17): "All outsourced work needs to be done through cathode26@gmail.com. So the pipeline should go through docker and through cathode26@gmail.com."
- **The check:** `claude auth status --text` on the host, or inside the job's container. `claude -p "/usage"` confirms it a second way, since the reset times differ between the accounts.
- **If it isn't the Gmail account, don't run the job.** Tell Vincent; never re-login an account yourself.
- **Do the check yourself. `run_job.py` is NOT yet trusted for it** (2026-09-18): its adversarial review came back FIX FIRST, and one of the three blocking findings is that its 24h account cache **fails open** - a future `checked_at` never expires and any agent can write the file, so it can report the right account while the CLI is logged into the wrong one. Report: `C:/nscrev/reports/run-job-review-20260918.md`. This line will point at the tool again when the Pipeline Maintainer sends an APPROVE, not before.

**When to use it instead of a Docker job:** only when the job needs host files (`C:\NSC` docs, `C:\nscrev` reports, the journal), Windows tools, the PixelLab MCP (connected on the host), or one of our custom agents.
- **The reason, and the case that keeps recurring (recorded 2026-09-18): a Docker job mounts exactly one job clone.** A review whose evidence is spread across the host - several clones at once, `C:/nscrev/reports`, `C:/NSC/tools/jobs`, or a tool that lives in no repo at all - cannot see it from inside the container, so it runs on the host CLI. **That is still the Gmail account, so it costs nothing extra; only the Agent tool spends the desktop one.** Docker stays the default whenever the work really is confined to a clone.
- **Worked example:** the five `propagation_check.py` reviews and three `run_job.py` reviews of 2026-09-18 each had to read the tool (in `C:/NSC/tools/jobs`, not a repo), its tests, the earlier review reports, and `C:/nscrev/ci-134-fix` as a real-repo fixture. No single job clone holds those, so every one of them ran on the host CLI.
- **This is the distinction `CLAUDE.md`'s "files outside a repo clone" line leaves implicit:** out-of-clone work needs the **Agent tool** only when it also needs Unity, PixelLab, Windows-only tools or a session's own context. Out-of-clone work that is only *reading host files* belongs on the host CLI, which `CLAUDE.md` already puts on the Gmail account.
**Every host job pops a few console windows on Vincent's desktop** (measured 2026-09-17: 3 to 5 per short job, whatever the launch style; see `nsc-quiet-windows-guide.md`). Docker jobs pop none, so prefer Docker, batch host jobs, and don't run several while he's working.

```bash
cd /c/nscrev
claude -p [--agent <custom agent>] [--model <model>] --max-turns <n> --permission-mode dontAsk --allowedTools <tools> --output-format json \
  < C:/nscrev/claude-jobs/<name>.prompt.md > C:/nscrev/claude-jobs/<name>.json 2> C:/nscrev/claude-jobs/<name>.log
```

- **`--agent <name>`** runs a custom agent from `C:\Users\VincentLiguori\.claude\agents\`, with that agent's model and rules. It was verified with `scribe`.
  - Examples: `test-runner`, `unity-runner`, `pipeline-reviewer`, `scribe`.
  - The usual rules still apply; for example, one Unity at a time, and Unity stays with the Game Agent.
- **Least privilege.** A host job reaches real files, and nothing screens its actions. List only what it needs:
  - **Both list forms work:** space-separated values (`--allowedTools Read Glob Grep "Bash(git:*)"`) and one quoted comma-separated argument (`--allowedTools "Read,Grep,Bash(python:*)"`).
  - **A `Bash(<program>:*)` rule matches the program name in the command.** A compound command is fine: `cd C:/nscrev && python -c "..."` ran under `Bash(python:*)` with no denial (verified 2026-09-17 from the stream-json transcript). What does **not** match is a different program name, such as `python3`, `powershell`, or an absolute path to the exe. Name in the prompt the exact program the job should use.
  - **Stop jobs from working around a refusal.** On 2026-09-17 a job that couldn't run Bash spawned `general-purpose` and `test-runner` subagents instead, which is slower and escapes the list you set. Add `--disallowedTools Task` to job commands, and tell the job in its prompt to report the refusal instead of finding another route.
  - **read-only:** `Read Grep Glob`, plus exact command prefixes such as `"Bash(git -C C:/NSC/NSC/NoSafeCircle log:*)"` or `"Bash(gh run list:*)"`;
  - **writes:** add `Edit Write` only when the brief names the files, then check `git status` and the diff yourself.
  - **Don't use `--permission-mode auto`:** it doesn't work headless, and refused a plain Write in the test. Use `dontAsk` with an explicit list.
- **Write prompts with the Write tool.** `printf` or `echo` in Git Bash turn `\n` inside Windows paths into newlines; that broke a job on 2026-09-17.
- **Where to run:** from `C:\nscrev`; no workspace-trust stall there (verified). A folder never opened interactively can stall (runbook 3.4).
- **After:** read the result as in step 4 above. For a long job, pass `run_in_background`.
- **Docker job or host job?** Docker for work inside a repo clone, since the container isolates it; host for anything that needs the host.

### 4.4 Ask Astra when you're stuck or things go bad (Vincent, 2026-09-17)

Vincent (2026-09-17): "When things go [bad], Ask Codex, use a Astra for advice. If that advice doesnt help, then ask me." ("back" was a typo he corrected), and "I just mean use the best model on Codex called Astra for questions you are stuck on".

- **When:**
  - you're stuck on a question;
  - or things go bad: a failure you can't explain, or a problem that keeps coming back (a repeated "revise" contract check, FIX FIRST or REJECT review, or the same failure twice).
- **Ask Astra before Vincent.** Ask Vincent only if the advice needs his decision or doesn't solve the problem.
- **Approved:** no need to ask. It's a read-only Codex job at xhigh effort.
- **Template:** `C:\nscrev\codex-jobs\templates\advice-prompt.md`. Use part A for a question you're stuck on, or part B when things went bad: what happened, and each attempt's verdict and report path.
- **Run it on the host** (Git Bash). Reports and contracts are outside the repo:
  ```bash
  JOB=codex-advice-<item>-$(date +%Y%m%d-%H%M)
  CODEX=$(ls -t /c/Users/VincentLiguori/AppData/Local/OpenAI/Codex/bin/*/codex.exe | head -1)   # the Codex app's bundled CLI; its folder name changes on each update
  # fill the template into C:/nscrev/codex-jobs/$JOB.prompt.md with the Write tool
  "$CODEX" exec -m gpt-6-astra --sandbox read-only --cd C:/nscrev --skip-git-repo-check -c model_reasoning_effort=xhigh --color never --output-last-message C:/nscrev/codex-jobs/$JOB.report.md - < C:/nscrev/codex-jobs/$JOB.prompt.md > C:/nscrev/codex-jobs/$JOB.log 2>&1
  ```
- **Astra model** (verified 2026-09-17, after Vincent updated Codex): only the Codex app's bundled CLI runs `gpt-6-astra`.
  - That CLI is `AppData\Local\OpenAI\Codex\bin\<hash>\codex.exe` (0.155.0-alpha.2.6). The recipe picks the newest folder.
  - The standalone `AppData\Local\Programs\OpenAI\Codex\bin\codex.exe` (0.151.0) and Docker Codex (stable 0.152.1 after the 09-17 rebuild) answer "requires a newer version of Codex".
  - If Astra fails, run the same job without `-m gpt-6-astra` (the default `gpt-5.6-sol`, xhigh) and note that in the journal.
  - Don't guess other model names: `gpt-6.0-astra` is refused for ChatGPT accounts.
- **After:**
  - Put the ROOT CAUSE and NEXT STEP lines in the journal, then follow the next step.
  - Ask Vincent only if the report says NEEDS VINCENT, or the item comes back again after you followed the advice. Give him the report path and the exact question.

---

## 5. Handing work to the Codex desktop app

For long orchestration by Codex itself:
- Vincent opens a Codex desktop session and pastes the role's launch prompt from `C:\NSC\nsc-agent-launch-prompts.md`.
- Tell it to use the same journal, guides and rules.
- **Automations it creates must end** (`UNTIL=`). Pause them when done.
- Before relying on it overnight, check quota (Watcher check, section 2).
