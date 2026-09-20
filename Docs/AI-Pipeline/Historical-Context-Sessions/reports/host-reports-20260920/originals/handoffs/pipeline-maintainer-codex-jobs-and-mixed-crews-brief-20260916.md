# Pipeline Maintainer handoff: Codex jobs with adversarial review, and mixed-provider crews (2026-09-16)

From the Documentation Agent. Vincent asked for both features in the Documentation Agent session.

## Vincent's words

- "we should add the ability to have codex do tasks for us which will include adversarial review. We want codex to verify our work through the pipeline. IT should support generic tasks."
- "When our game agent does pipeline work, we want to prefer a mixed agent pipeline."
- "We can also task cheaper subagents through codex to do easy work, because we dont want to exhaust all of the tokens on claude."
- Standing preferences:
  - "if the task is easy, send it to a cheaper subagent", and "Dont waste tokens";
  - fixes should remove friction, not add hard gates.

## What exists today (checked 2026-09-16)

**Docker Codex one-shot jobs** are a manual recipe only: `C:\NSC\nsc-codex-jobs-guide.md`, section 2.
- A standalone clone with clone-local `core.autocrlf=true core.filemode=false core.longpaths=true`, then:

  ```text
  docker compose -p nosafecircle run --rm -T codex bash -lc 'cd /workspace && codex exec --sandbox danger-full-access --skip-git-repo-check -c model_reasoning_effort=high --color never --output-last-message /workspace/CODEX_JOB_REPORT.md -'
  ```

  run from the clone directory, with the prompt on stdin.
- No records, no status, no verdict parsing.

**Host Codex CLI:** `codex-cli 0.151.0` at `C:\Users\VincentLiguori\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe`.
- `codex exec` has `--sandbox read-only|workspace-write|danger-full-access`, `-C/--cd <dir>`, `--add-dir`, `--output-schema <JSON Schema file>` (structured final message), `--json` (JSONL events), `-o/--output-last-message`, `--ephemeral`, `-m`, and `-c model_reasoning_effort=...`.
- `codex exec review` reviews the current repository, with `--base <branch>`, `--commit <sha>`, `--uncommitted` and custom instructions (or `-` for stdin).

**GER already drives host Codex:** `C:\nscrev\ger-tools\ger_round.py` `run_codex` (about line 445) runs `codex exec --json --sandbox read-only --cd <snapshot> --skip-git-repo-check -c model_reasoning_effort=... --output-last-message <file>` and records CLI version and config. Reuse that pattern.

**Mixed crews already exist.** (Corrected 2026-09-16 after Vincent pointed to them; an earlier version of this brief wrongly said crews were single-provider.)
- `Pipeline/TaskReviewAgent/provider_profiles.py` defines four profiles: `all-claude`, `all-codex`, `claude-architect-balanced` and `codex-architect-balanced`. Design doc: `Docs/AI-Pipeline/PROVIDER_PROFILES_AND_BUDGET_ROUTING.md`. Tests: `Pipeline/TaskReviewAgent/tests/provider_profiles_test.py`.
- In the mixed profiles, `crew_role_routes` puts the implementer and test author on the implementer's provider (chosen by token balance) and the validator and lead developer on the opposite provider.
- `run_crew.py` takes `provider_topology` plus `role_routes` (about lines 1863-1875 and 2138-2141).
- The launchers `Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1` and `Start-AutonomousGraphRun.ps1` accept `-ProviderProfile`.
- AssistantControl's `crew_worker._bridge_options` allows a `provider_profile` key in worker configs (`crew_worker.py` about line 88; `candidate.py` about line 202).
- The two live worker configs (`worker-claude-sonnet-high.json`, `worker-codex-sol-high.json`) don't set it.
- `role_provider_overrides` (about lines 1984, 2134 and 2407) is a separate thing: the Claude-quota fallback to Codex.

**Decomposition already mixes providers:** `decompose --providers claude,codex`, where one authors and the other reviews.

---

## Feature A: generic Codex jobs, "do" and "review"

1. **One CLI any agent can call.** For example `python -m Pipeline.CodexJobs create|run|status|result|list|cancel`. The package name, or an AssistantControl subcommand instead, is your call.
2. **A job spec file** with:
   - `job_id`, `mode` (`do` or `review`), `title`, `requester` (the session title), `instructions` (a file path);
   - `source` (repo; default `C:\NSC\NSC\NoSafeCircle`), `base` (commit or branch);
   - `target` (review mode: a branch, commit range, files, or a report or doc to verify);
   - `runtime`: `docker` by default, or `host` for Windows-only work such as `test_viewer`, which needs `ctypes.WinDLL`. Neither runtime can run Unity;
   - `effort`, `model` (optional), `timeout_seconds`, `allowed_paths` (do mode), `checks` (commands to run), and an optional `task_id`.
   - **A `cheap` preset for easy work** (medium or low reasoning effort, or a cheaper Codex model if the account offers one; don't hard-code model names). Claude agents should be able to send easy work to Codex in one call instead of spending Claude tokens.
3. **Isolation.**
   - One standalone clone per job, never a worktree, under `C:\nscrev\codex-jobs\<job_id>\repo`, with the clone-local settings above and the push URL disabled.
   - **Do mode:** a single branch, `codex/<job_id>`.
   - **Review mode:** the target head checked out, and the clone must be unchanged after the run.
   - Never mount the canonical repo read-write (this broke Vincent's checkout on 9/15).
4. **Durable records** in `C:\nscrev\codex-jobs\<job_id>\`:
   - `job.json`;
   - `status.json`: queued, running, succeeded, failed, cut_off or needs_attention, plus timestamps, runtime identity, exit code, Codex version and session id;
   - `prompt.md` (the full composed prompt);
   - the event log;
   - `report.md` (the last message);
   - `result.json` (structured).
5. **Review mode is adversarial by default.**
   - **A built-in reviewer prompt:**
     - assume the work is wrong until proven;
     - reproduce the claims, and re-run the checks at base and head in its own clone;
     - grep for incomplete propagation;
     - rank findings, each with file:line, a concrete failure scenario, and whether it was reproduced or theoretical;
     - no style nits.
   - **A structured verdict** through `--output-schema`: `verdict` (APPROVE, FIX_FIRST or REJECT), `findings[]`, `tests_run[]`, `scope_check`. Validate it; an invalid or missing verdict is `needs_attention`, never a silent pass.
   - **Read-only enforcement.** Host runtime uses `--sandbox read-only` plus a job temp dir. Docker runtime compares the clone's HEAD, index and worktree before and after; any change is `review_integrity_violation`.
   - **Independence.** A fresh Codex session per review, given only the spec, target and any author report, never the author's transcript.
   - **Plain code review** may use `codex exec review --base/--commit`, with the adversarial instructions as the custom prompt.
6. **Chaining.** A do job can request a follow-up review: a separate review job on its branch, in a separate Codex session, recorded as linked jobs.
7. **Verifying our work.** Review jobs must work on branches and commits made by Claude agents: Pipeline Maintainer `fix/<topic>` branches, Game Agent merge candidates, crew candidates, and docs or reports that make claims about code.
8. **Advisory, not a gate.** Verdicts are recorded and shown; nothing refuses a merge or an approval because of them. The Game Agent and Vincent decide.
9. **Background-friendly.** `run --wait` exits when the job ends, so a Claude session can run it in the background and get notified. `status` is cheap.
10. **Windows safety.** Every subprocess gets `CREATE_NO_WINDOW`; logs go to files; Docker runs as `docker compose -p nosafecircle run --rm -T codex` from the clone directory.
11. **Quota.** Mark `cut_off` when the log shows a usage-limit stop. Record rate-limit data when present, and warn (advisory) when quota is high.
12. **Spend.** Real runs need an explicit `--authorize-provider-spend` flag, like other paid commands. The standing policy is Vincent's (open questions below).
13. **Tests** use a fake `codex` executable, with no real provider calls. Cover:
    - spec validation;
    - clone isolation;
    - record lifecycle;
    - verdict schema parsing;
    - integrity-violation detection;
    - cut-off detection;
    - no-window flags.
14. **Docs.** A README in the package. Tell the Documentation Agent when it lands, so the guides switch from the manual recipe.

## Feature B: mixed crews through AssistantControl (REVISED 2026-09-16: verify and enable, don't rebuild)

The profiles already exist (see "What exists today"). The work is to make them the Game Agent's everyday crew route:

1. **Verify end to end** that a worker config with `"provider_profile": "codex-architect-balanced"` (and `claude-architect-balanced`) run through AssistantControl `start-worker` or `run-worker` expands into the correct `provider_topology` and `role_routes`: validator and lead developer on the provider opposite the implementer. Check the credential volumes, `provider_allowlist`, and the `NSC_CODEX_RESUME_SANDBOX_ARGUMENT` requirement from the design doc. Use fake providers or dry-run preflight only; no paid run without Vincent's go.
2. **If it works,** check in example worker configs (e.g. `Pipeline/AssistantControl/worker-mixed-codex-architect.example.json`) and say exactly what the live `.assistant-control` config should contain. The Game Agent creates the live config.
3. **If it's broken** in the AssistantControl route, fix that, with the usual failing-before and passing-after tests.
4. **Surface it.** Candidate records and the viewer should show the provider per role. Check whether they already do.
5. **Until this is verified,** the interim is cross-provider review of the candidate: a Codex review (Feature A, or the manual recipe) for a Claude crew, or a fresh Claude review for a Codex crew.
6. **Probably small.** This may need no code at all; a cheap subagent or a Codex job can do much of the verification.

## Order and branches

- These come after your current items (viewer-step1 review and P34), unless Vincent reprioritizes.
- Feature A first, since it also provides the interim mixed path. Then Feature B.
- One branch per feature: `fix/codex-jobs` and `fix/mixed-provider-crews`.
- Each gets a fresh `pipeline-reviewer`. Once A exists, add a Codex review job on B for a cross-provider check.
- No real provider calls in tests. Any real Codex, Docker or Unity run needs Vincent's go.

## Open questions for Vincent (asked by the Documentation Agent)

1. **ANSWERED 2026-09-16:**
   - Codex review jobs on our own work and on merge candidates are **pre-approved**, including host runs for Windows-only tests.
   - They **pause once Codex weekly quota passes 90%**.
   - Codex "do" jobs still need Vincent's go.
   - **Unity checks stay with the Game Agent;** Codex never runs Unity.
   - For the CLI: review runs need no per-job go, but record the authorization source ("standing approval 2026-09-16"). Stop starting new jobs above 90% quota.
2. **Default mixed preset:** superseded. The profiles decide per role; the implementer is chosen by token balance and the validator is always the opposite provider. The remaining choice is `claude-architect-balanced` or `codex-architect-balanced`; the Documentation Agent recommends `codex-architect-balanced` to spare Claude tokens. Confirm what "architect" changes in the AssistantControl route.
